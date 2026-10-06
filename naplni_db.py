#!/usr/bin/env python3
"""Krok 4 pipeline: naplneni databaze z korpusu data/spc/.

Co kam jde:

    data/detaily_leciv/<kod>.json     ->  leciva        (vsechny kody, zadny model)
    data/spc/<spc>/json/<sekce>.json  ->  extrakty      (cely vysledek extrakce)
    data/spc/<spc>/json/_stav.json    ->  extrakce_stav (co se povedlo a co ne)
    data/spc/<spc>/json/<sekce>.json  ->  leciva_search (1 radek = 1 hledatelna polozka)

Extrakty a hledaci radky se nahravaji JEDNOU ZA SPC, u zastupce (nejmensi
kod SUKL); ostatni kody tehoz SPC maji jen radek v `leciva`.

DULEZITE - co NEJDE do hledaneho textu:
    sekce, frekvence, organovy_system jsou FILTRY. Kdyby byly v obsah_text,
    opakovaly by se pres stovky radku ("Gastrointestinalni poruchy" u kazde
    polozky) a znehodnotily fulltext i embedding. Do vektoru jde POUZE
    obsah_text.

Radek sekce='atributy':
    Jeden na SPC, nepochazi z PDF ale z registru. Slouzi k tomu, aby slo
    lek najit podle jmena, sily nebo kodu SUKL. Ma extrakt_id = NULL
    a kontext_text = NULL (identita uz je v obsah_text, bylo by to dvakrat).

Embeddingy tenhle skript NEPOCITA - to dela vytvor_embeddingy.py (krok 5).
Hledaci slovnik (tabulka slovnik_dotazu) se NEMAZE - viz vyprazdni_korpus().

Do 6. 10. 2026 umel skript i puvodni korpus 32 leciv (data/leciva, prepinace
--znovu a --kody); ta cesta je smazana.

Pouziti:
  uv run python naplni_db.py --korpus                  # cely korpus od nuly (~40 min)
  uv run python naplni_db.py --korpus --limit-spc 50   # zkouska na 50 SPC
  uv run python naplni_db.py --obnov-sekci davkovani   # jen jedna sekce, ostatni nechat
  uv run python naplni_db.py --jen-vek                 # jen prepocitat vek pouziti
"""

import io
import sys
import json
import argparse
from pathlib import Path
from collections import Counter

import psycopg

from common.config import PG_DSN
from common.sekce import SEKCE_SPC

# Kody zpusobu vydeje, ktere znamenaji "na predpis". Pozor: hodnota
# NEUVEDENO neznamena volny prodej, znamena ze to z dat nejde urcit -
# proto se mapuje na NULL, ne na False.
VYDEJ_NA_PREDPIS = {"R": True, "L": True, "O": True, "V": True,
                    "F": False, "FR": False, "OTC": False}


def _na_predpis(kod: str | None) -> bool | None:
    return VYDEJ_NA_PREDPIS.get((kod or "").strip().upper())


# Kod latky -> nazev. API u leciva vraci jen KODY ([1064]), ne nazvy.
# Bez prekladu se do DB ulozilo "1064" misto "paracetamol" a dotaz
# "volne prodejny lek s paracetamolem" nenasel NIC, prestoze filtr byl
# spravny - hledal "paracetamol" v poli, kde bylo "1064". Rozbijelo to
# i hledani: radek 'atributy' obsahoval "PARALEN, 500MG, TBL NOB, 1064".
_LATKY_CACHE: dict[int, str] | None = None
_LATKY_SOUBOR = Path("data/ciselnik_latky.json")


def nacti_ciselnik_latek(*, znovu: bool = False) -> dict[int, str]:
    """Ciselnik latek ze SUKL, cachovany na disk (6951 polozek)."""
    global _LATKY_CACHE
    if _LATKY_CACHE is not None and not znovu:
        return _LATKY_CACHE

    if _LATKY_SOUBOR.exists() and not znovu:
        _LATKY_CACHE = {int(k): v for k, v in
                        json.loads(_LATKY_SOUBOR.read_text(encoding="utf-8")).items()}
        return _LATKY_CACHE

    from common.sukl_api import SuklClient

    seznam = SuklClient().ciselnik_latky()
    _LATKY_CACHE = {int(x["kod"]): str(x.get("nazev") or x["kod"]) for x in seznam}
    _LATKY_SOUBOR.parent.mkdir(parents=True, exist_ok=True)
    _LATKY_SOUBOR.write_text(
        json.dumps({str(k): v for k, v in _LATKY_CACHE.items()},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    return _LATKY_CACHE


_HRAZENE_SOUBOR = Path("data/hrazene_scau.json")
_HRAZENE_CACHE: set[str] | None = None


def nacti_hrazene(*, znovu: bool = False) -> set[str]:
    """Kody SUKL hrazenych pripravku, cachovane na disk (~8600 polozek).

    Hrazenost NENI atribut v detailu leciva - SUKL ji vyjadruje tim, ze
    kod je v seznamu `typSeznamu=scau`. Proto se stahuje zvlast.

    POZOR: hrazenost NENI totez co "na predpis". Z naseho korpusu je na
    predpis 13 leciv, ale hrazenych jen 7 - ABLYMICO i AMOKSIKLAV jsou
    na predpis a hrazene nejsou.
    """
    global _HRAZENE_CACHE
    if _HRAZENE_CACHE is not None and not znovu:
        return _HRAZENE_CACHE

    if _HRAZENE_SOUBOR.exists() and not znovu:
        _HRAZENE_CACHE = set(json.loads(_HRAZENE_SOUBOR.read_text(encoding="utf-8")))
        return _HRAZENE_CACHE

    from common.sukl_api import SuklClient
    _HRAZENE_CACHE = set(SuklClient().seznam_kodu("scau"))
    _HRAZENE_SOUBOR.parent.mkdir(parents=True, exist_ok=True)
    _HRAZENE_SOUBOR.write_text(json.dumps(sorted(_HRAZENE_CACHE), ensure_ascii=False),
                               encoding="utf-8")
    return _HRAZENE_CACHE


def _latky(api: dict) -> list[str]:
    """Ucinne latky jako NAZVY. Kody se prelozi pres ciselnik SUKL."""
    v = api.get("leciveLatky") or []
    if v and isinstance(v[0], dict):
        return [str(x.get("nazev") or x.get("kod")) for x in v]
    ciselnik = nacti_ciselnik_latek()
    ven = []
    for x in v:
        try:
            ven.append(ciselnik.get(int(x), str(x)))
        except (TypeError, ValueError):
            ven.append(str(x))
    return ven


def kontext(a: dict) -> str:
    """Identita leku pripojena k polozkam sekci - aby slo hledat
    'nezadouci ucinky paralenu' jednim dotazem."""
    casti = [a.get("nazev"), a.get("sila")] + _latky(a)
    return ", ".join(str(c) for c in casti if c)


# Nad tuhle delku uz se odborny tvar do hledaneho textu NEPRIPOJUJE.
# Duvod: u kratkych terminu pomaha ("nizky pocet desticek (trombocytopenie)"),
# ale u dlouhych vet zdvojnasobi delku a ROZREDI VEKTOR - embedding
# prumeruje pres celou vetu a konkretni pojem se ztrati. ABLYMICO melo
# takhle 776 znaku v jedne polozce.
MAX_DELKA_ODBORNEHO = 60


def _spoj(laicky: str, odborne: str) -> str:
    """Text pro hledani: laicky tvar, u kratkych terminu i odborny."""
    if not laicky:
        return odborne
    if not odborne or laicky.lower() == odborne.lower():
        return laicky
    if len(odborne) > MAX_DELKA_ODBORNEHO:
        return laicky
    return f"{laicky} ({odborne})"


def strana_sekce(adr: Path, sekce: str) -> int | None:
    """Cislo strany v PDF, kde sekce zacina.

    Bez nej nefunguje odkaz "spc.pdf#page=7", coz je jedna z veci, kterou
    ma demo ukazovat jako DOKLAD PUVODU. Mapa nadpis -> strana vznika pri
    konverzi (strany.json), jen se dosud nepropisovala do DB.
    """
    f = adr / "strany.json"
    if not f.exists():
        return None
    cislo = SEKCE_SPC.get(sekce)
    if not cislo:
        return None
    strany = json.loads(f.read_text(encoding="utf-8"))
    # Nadpis zacina cislem bodu: "4.1 Terapeuticke indikace"
    for nadpis, strana in strany.items():
        if nadpis.strip().startswith(cislo):
            return strana
    return None


# --- Sjednoceni klice (2. 10. 2026) ---------------------------------------
# Klic vyrabi model u kazdeho leku zvlast a nedeterministicky: tentyz laicky
# tvar „zapal plic" mel klic „pneumonie" 34x, „zapal plic" 5x, zadny 1x.
# Klic shodny s dotazem da cosine 1,0, odborny 0,80 -> KLACID 11. misto.
# PRAVIDLO (bez modelu, po radcich): laicky tvar 1-4 slova -> klic = laicky
# tvar; delsi laicky (cela veta) -> klic od modelu zustava (tam je to zkratka).
# Rozhoduje se pri plneni DB, JSON z extrakce zustava netknuty.
KLIC_MAX_SLOV = 4
# VYPNUTO 2. 10. 2026 – zmereno HORSI: parafraze 20/20 -> 19/20, presnost
# 66 -> 63 %. Laicky klic zrovnopravnil prave indikace s VYTRZENYMI kusky
# („diabetem mellitem" u SIMVASTATINU -> klic „cukrovka" -> cosine 1,0).
# Odborny klic chybu jen nahodou skryval. Koren je v extrakci (poznatky 2. 10.).
SEKCE_SJEDNOCENY_KLIC: tuple[str, ...] = ()


def klic_hledani(sekce: str, p) -> str | None:
    """Klic pro hledani (vlastni vektor + fulltext). U davkovani skupina pacientu."""
    if not isinstance(p, dict):
        return None
    if sekce == "davkovani":
        return p.get("klic") or p.get("pacient")
    if sekce in SEKCE_SJEDNOCENY_KLIC:
        laicky = " ".join(str(p.get("laicky") or "").split()).rstrip(".")
        if laicky and len(laicky.split()) <= KLIC_MAX_SLOV:
            return laicky
    return p.get("klic")


def sjednot_klice() -> int:
    """Pravidlo klic_hledani() na STAVAJICI DB, bez preplneni.

    Zmenenym radkum se smaze embedding_klic; vytvor_embeddingy.py ho
    dopocita (rezim pro chybejici klice). search_fts je generovany sloupec,
    prepocita se sam.
    """
    with psycopg.connect(PG_DSN) as conn, conn.cursor() as cur:
        cur.execute(rf"""
            WITH n AS (
                SELECT id, regexp_replace(trim(sekce_atributy->>'laicky'), '[.]+$', '') AS laicky
                FROM leciva_search
                WHERE sekce IN ('indikace', 'kontraindikace')
                  AND sekce_atributy->>'laicky' IS NOT NULL)
            UPDATE leciva_search s
               SET klic = n.laicky, embedding_klic = NULL
              FROM n
             WHERE s.id = n.id
               AND n.laicky <> ''
               AND array_length(regexp_split_to_array(n.laicky, '\s+'), 1) <= {KLIC_MAX_SLOV}
               AND coalesce(s.klic, '') IS DISTINCT FROM n.laicky""")
        n = cur.rowcount
        conn.commit()
    print(f"Sjednoceno {n} klicu (klic = laicky tvar 1-{KLIC_MAX_SLOV} slova). "
          f"Ted vytvor_embeddingy.py (dopocita vektory klicu).")
    return 0


def text_polozky(sekce: str, p) -> tuple[str, dict | None]:
    """Z polozky udela (obsah_text, sekce_atributy).

    obsah_text je to JEDINE, co jde do vektoru - musi to byt cisty obsah
    bez filtracnich hodnot.
    """
    if isinstance(p, str):
        return p.strip(), None

    if sekce == "nezadouci_ucinky":
        # Do textu jde laicky tvar, pokud existuje - uzivatel hleda laicky.
        # Odborny termin se prida taky, at se najde i odbornym dotazem.
        laicky = (p.get("ucinek_laicky") or "").strip()
        odborne = (p.get("ucinek") or "").strip()
        text = _spoj(laicky, odborne)
        atr = {k: v for k, v in p.items()
               if k in ("ucinek", "ucinek_laicky", "laicky_ze_slovniku")}
        return text, atr or None

    if sekce in ("indikace", "kontraindikace"):
        text = _spoj((p.get("laicky") or "").strip(),
                     (p.get("doslovne") or "").strip())
        return text, {k: v for k, v in p.items() if v} or None

    if sekce == "davkovani":
        casti = [p.get("pacient"), p.get("davka"), p.get("frekvence")]
        text = " ".join(str(c) for c in casti if c).strip()
        return text, {k: v for k, v in p.items() if v}

    return json.dumps(p, ensure_ascii=False), None



# ===========================================================================
# KORPUS (data/spc, 30.9.2026) - jedno SPC pro vice kodu SUKL
# ===========================================================================
# Extrakce je po SPC (data/spc/<slozka>/json), leciva po kodech
# (data/detaily_leciv/<kod>.json). Do DB jdou VSECHNY kody (tabulka leciva,
# sloupec spc), ale extrakty a hledaci radky JEN JEDNOU za SPC - u zastupce.
# Zastupce = nejmensi kod SPC (deterministicky, stejny pri kazdem behu).
# Filtry Rx/hrazeno/ATC se pak berou ze zastupce - v ramci SPC se lisi
# jen vyjimecne (ruzna baleni teze registrace).

SPC_DIR = Path("data/spc")
DETAILY_DIR = Path("data/detaily_leciv")


def mapa_kod_spc() -> dict[str, str]:
    """kod SUKL -> slozka SPC (data/spc/<slozka>/) z inventare konverze."""
    import re
    import sqlite3
    c = sqlite3.connect(SPC_DIR / "_stav.sqlite")
    return {kod: re.sub(r"[^\w.-]+", "_", ident)[:80]
            for kod, ident in c.execute(
                "SELECT kod, identita FROM kody WHERE identita IS NOT NULL")}


def vloz_lecivo_z_detailu(cur, a: dict, spc: str, zastupce: bool) -> str | None:
    kod = str(a.get("kodSUKL") or "").strip()
    if not kod:
        return None
    cur.execute("""
        INSERT INTO leciva (kod_sukl, nazev, doplnek, sila, lekova_forma, cesta,
                            atc, zpusob_vydeje, na_predpis, hrazeno,
                            registracni_cislo, stav_registrace, je_dodavka, baleni,
                            obal, indikacni_skupina, ucinne_latky, api_json,
                            spc, zastupce)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (kod, a.get("nazev"), a.get("doplnek"), a.get("sila"),
          a.get("lekovaFormaKod"), a.get("cestaKod"), a.get("ATCkod"),
          a.get("zpusobVydejeKod"), _na_predpis(a.get("zpusobVydejeKod")),
          kod in nacti_hrazene(),
          a.get("registracniCislo"), a.get("stavRegistraceKod"),
          a.get("jeDodavka"), a.get("baleni"), a.get("obalKod"),
          a.get("indikacniSkupinaKod"), _latky(a), json.dumps(a, ensure_ascii=False),
          spc, zastupce))
    return kod


def radek_atributy_spc(detaily: list[dict]) -> str:
    """Identita SPC jako hledatelny text: VSECHNY nazvy, sily a formy baleni.
    Jedno SPC casto pokryva vic sil (5 mg i 10 mg) - lek se ma najit
    i podle sily, kterou zastupce nema."""
    videne: list[str] = []
    for a in detaily:
        for c in [a.get("nazev"), a.get("sila"), a.get("lekovaFormaKod")] + _latky(a):
            if c and str(c) not in videne:
                videne.append(str(c))
    videne.append(detaily[0].get("kodSUKL"))
    return ", ".join(videne)


def nahraj_sekce(cur, kod: str, adr: Path, json_adr: Path, api: dict, poc: Counter,
                 jen_ok: bool, sekce_k_nahrani=None) -> None:
    """Extrakty + stav + hledaci radky jednoho leciva/SPC. Sdili 32 leciv i korpus."""
    stav_f = json_adr / "_stav.json"
    stavy = json.loads(stav_f.read_text(encoding="utf-8")) if stav_f.exists() else {}

    for sekce in (sekce_k_nahrani or SEKCE_SPC):
        js = json_adr / f"{sekce}.json"
        st = stavy.get(sekce, {})
        stav = st.get("stav", "neovereno")

        if not js.exists():
            cur.execute("""
                INSERT INTO extrakce_stav (kod_sukl, sekce, stav, duvod)
                VALUES (%s,%s,%s,%s)
                ON CONFLICT (kod_sukl, sekce, extrakt_id) DO NOTHING
            """, (kod, sekce, stav if stav != "neovereno" else "prazdna",
                  st.get("duvod")))
            poc[f"stav_{stav}"] += 1
            continue

        polozky = json.loads(js.read_text(encoding="utf-8"))
        sekce_md = adr / "sekce" / f"{sekce}.md"
        orez_md = adr / "sekce" / f"{sekce}_orez.md"

        cur.execute("""
            INSERT INTO extrakty (kod_sukl, sekce, sekce_cislo, zdrojovy_text,
                                  zdrojovy_text_orez, polozky, model_extrakce,
                                  metadata)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (kod_sukl, sekce, model_extrakce) DO UPDATE SET
                polozky = EXCLUDED.polozky
            RETURNING id
        """, (kod, sekce, SEKCE_SPC[sekce],
              sekce_md.read_text(encoding="utf-8") if sekce_md.exists() else None,
              orez_md.read_text(encoding="utf-8") if orez_md.exists() else None,
              json.dumps(polozky, ensure_ascii=False),
              st.get("model") or "neznamy",
              json.dumps(st, ensure_ascii=False)))
        extrakt_id = cur.fetchone()[0]
        poc["extrakty"] += 1

        cur.execute("""
            INSERT INTO extrakce_stav (kod_sukl, extrakt_id, sekce, stav,
                                       pocet_polozek, model_extrakce,
                                       model_kontroly, duvod, cas_extrakce_s)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (kod_sukl, sekce, extrakt_id) DO UPDATE SET
                stav = EXCLUDED.stav
        """, (kod, extrakt_id, sekce, stav, len(polozky),
              st.get("model"),
              (st.get("kontrola_modelem") or {}).get("model"),
              st.get("duvod"), st.get("cas_s")))
        poc[f"stav_{stav}"] += 1

        vadne = set()
        if stav == "zamitnuto_kontrolou":
            vadne = set((st.get("kontrola_modelem") or {}).get("chybne_indexy") or [])
            if not vadne:
                poc["preskoceno_cela_sekce"] += 1
                continue
        if jen_ok and stav != "ok":
            poc["preskoceno_cela_sekce"] += 1
            continue

        strana = strana_sekce(adr, sekce)
        radky = []
        for i, p in enumerate(polozky):
            if i in vadne:
                poc["preskocena_polozka"] += 1
                continue
            obsah, atr = text_polozky(sekce, p)
            if not obsah:
                continue
            je_nu = sekce == "nezadouci_ucinky" and isinstance(p, dict)
            radky.append((kod, extrakt_id, sekce,
                          p.get("frekvence") if je_nu else None,
                          p.get("frekvence_rank") if je_nu else None,
                          p.get("organovy_system") if je_nu else None,
                          json.dumps(atr, ensure_ascii=False) if atr else None,
                          kontext(api), obsah,
                          klic_hledani(sekce, p)
                          or (p.get("pacient") if sekce == "davkovani"
                              and isinstance(p, dict) else None),
                          strana))
        cur.executemany("""
            INSERT INTO leciva_search
                (kod_sukl, extrakt_id, sekce, frekvence, frekvence_rank,
                 organovy_system, sekce_atributy, kontext_text,
                 obsah_text, klic, strana_pdf)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, radky)
        poc["radky_sekci"] += len(radky)
        if strana:
            poc["se_stranou"] += len(radky)


# Tabulky, ktere do korpusu NEPATRI a plneni je nesmi smazat.
#   slovnik_dotazu  hledaci slovnik - zaznamy pridane uzivateli z GUI
#                   (/api/slovnik, common/dotazy.py). Po smazani by se
#                   nevratily, vychozi soubor obsahuje jen puvodni napln.
TABULKY_NEMAZAT = ("slovnik_dotazu",)


def vyprazdni_korpus(cur) -> None:
    """Smaze data korpusu pred plnenim od nuly. Hledaci slovnik NECHA BYT.

    `leciva CASCADE` vezme vse, co na leciva visi cizim klicem (extrakty,
    leciva_search, extrakce_stav). Tabulky z TABULKY_NEMAZAT cizi klic
    nemaji, takze se jich to netyka - a POJISTKA niz to overi: kdyby jim
    po mazani ubyl jediny radek (nekdo prida cizi klic nebo tabulku do
    TRUNCATE), skript skonci chybou a transakce se vrati.
    """
    def pocty() -> dict[str, int]:
        ven = {}
        for tab in TABULKY_NEMAZAT:
            if cur.execute("SELECT to_regclass(%s)", (tab,)).fetchone()[0]:
                ven[tab] = cur.execute(f"SELECT count(*) FROM {tab}").fetchone()[0]
        return ven

    pred = pocty()
    cur.execute("TRUNCATE leciva CASCADE; TRUNCATE slovnik_pojmu;")
    po = pocty()
    if po != pred:
        raise RuntimeError(f"Mazani korpusu zasahlo chranene tabulky: pred {pred}, po {po}. "
                           "Nic se nezapsalo (transakce vracena).")
    for tab, n in po.items():
        print(f"Ponechano beze zmeny: {tab} ({n} zaznamu)", flush=True)


def aktualizuj_vek(cur) -> Counter:
    """Vek pouziti leku (common/vek.py) do leciva - pro VSECHNY kody SPC.

    Pousti se po kazdem plneni korpusu i po obnove sekce (vek zavisi na
    4.1, 4.2 a 4.3). Bez modelu, par desitek sekund.
    """
    from common.vek import vek_spc

    cur.execute("ALTER TABLE leciva ADD COLUMN IF NOT EXISTS vek_od REAL; "
                "ALTER TABLE leciva ADD COLUMN IF NOT EXISTS pro_deti BOOLEAN; "
                "ALTER TABLE leciva ADD COLUMN IF NOT EXISTS vek_duvody JSONB; "
                "ALTER TABLE leciva ADD COLUMN IF NOT EXISTS jen_deti BOOLEAN; "
                "CREATE INDEX IF NOT EXISTS leciva_vek_idx ON leciva (vek_od); "
                "CREATE INDEX IF NOT EXISTS leciva_pro_deti_idx ON leciva (pro_deti);")
    # Forma zastupce: jedno SPC casto popisuje tablety i injekce (NOVALGIN)
    spcs = cur.execute("SELECT spc, lekova_forma, nazev FROM leciva "
                       "WHERE spc IS NOT NULL AND zastupce").fetchall()
    poc: Counter = Counter()
    for spc, forma, nazev in spcs:
        adr = SPC_DIR / spc / "json"

        def nacti(s):
            f = adr / f"{s}.json"
            return json.loads(f.read_text(encoding="utf-8")) if f.exists() else []

        r = vek_spc(nacti("davkovani"), nacti("indikace"), nacti("kontraindikace"), forma,
                    nazev)
        cur.execute("UPDATE leciva SET vek_od = %s, pro_deti = %s, jen_deti = %s, "
                    "vek_duvody = %s WHERE spc = %s",
                    (r["vek_od"], r["pro_deti"], r["jen_deti"],
                     json.dumps(r["duvody"], ensure_ascii=False), spc))
        poc["jen_deti"] += bool(r["jen_deti"])
        poc[f"pro_deti={r['pro_deti']}"] += 1
        poc["vek_znam" if r["vek_od"] is not None else "vek_nevim"] += 1
    print(f"Vek: {dict(poc)}", flush=True)
    return poc


def obnov_sekci(sekce: str, jen_ok: bool) -> int:
    """Znovu nahraje JEDNU sekci korpusu u vsech zastupcu SPC, ostatni nechá.

    Proc: po preextrahovani jedne sekce (30.9.: davkovani bez orezu) by
    --korpus smazal vse a embeddingy celych 451 tis. radku by se pocitaly
    znovu (~2 h). Takhle se smazou a znovu vlozi jen radky te sekce
    a vytvor_embeddingy.py dopocita jen je (radky bez vektoru).
    """
    import time
    t0 = time.perf_counter()
    poc: Counter = Counter()
    with psycopg.connect(PG_DSN) as conn, conn.cursor() as cur:
        zastupci = cur.execute("SELECT kod_sukl, spc, api_json FROM leciva "
                               "WHERE zastupce AND spc IS NOT NULL ORDER BY spc").fetchall()
        # extrakty maji ON DELETE CASCADE na leciva_search i extrakce_stav
        cur.execute("DELETE FROM leciva_search WHERE sekce = %s", (sekce,))
        poc["smazano_radku"] = cur.rowcount
        cur.execute("DELETE FROM extrakce_stav WHERE sekce = %s", (sekce,))
        cur.execute("DELETE FROM extrakty WHERE sekce = %s", (sekce,))
        print(f"Smazano {poc['smazano_radku']} radku sekce {sekce}, "
              f"nahravam {len(zastupci)} SPC", flush=True)
        for n, (kod, spc, api) in enumerate(zastupci, 1):
            adr = SPC_DIR / spc
            nahraj_sekce(cur, kod, adr, adr / "json", api, poc, jen_ok, [sekce])
            if n % 1000 == 0:
                conn.commit()
                print(f"  ... {n}/{len(zastupci)}", flush=True)
        conn.commit()
        aktualizuj_vek(cur)
        conn.commit()
    print(f"Nahrano {poc['radky_sekci']} radku sekce {sekce} za "
          f"{time.perf_counter() - t0:.0f} s. Ted vytvor_embeddingy.py (jen chybejici).")
    return 0


def main_korpus(jen_ok: bool, limit_spc: int | None) -> int:
    """Nahraje korpus data/spc. VZDY od nuly (TRUNCATE) - prirustkove plneni
    je v todo (mesicni job)."""
    import time
    mapa = mapa_kod_spc()
    po_spc: dict[str, list[str]] = {}
    for kod, spc in sorted(mapa.items()):
        po_spc.setdefault(spc, []).append(kod)
    spcs = sorted(po_spc)
    if limit_spc:
        spcs = spcs[:limit_spc]

    poc: Counter = Counter()
    t0 = time.perf_counter()
    with psycopg.connect(PG_DSN) as conn, conn.cursor() as cur:
        # Schema z doby pred korpusem nema sloupce spc/zastupce.
        cur.execute("ALTER TABLE leciva ADD COLUMN IF NOT EXISTS spc TEXT; "
                    "ALTER TABLE leciva ADD COLUMN IF NOT EXISTS zastupce BOOLEAN DEFAULT TRUE; "
                    "CREATE INDEX IF NOT EXISTS leciva_spc_idx ON leciva (spc);")
        vyprazdni_korpus(cur)
        print(f"Tabulky vyprazdneny. SPC: {len(spcs)}, kodu: "
              f"{sum(len(po_spc[s]) for s in spcs)}", flush=True)

        for n, spc in enumerate(spcs, 1):
            adr = SPC_DIR / spc
            detaily = []
            for kod in po_spc[spc]:
                f = DETAILY_DIR / f"{kod}.json"
                if f.exists():
                    detaily.append(json.loads(f.read_text(encoding="utf-8")))
                else:
                    poc["kod_bez_detailu"] += 1
            if not detaily:
                poc["spc_bez_detailu"] += 1
                continue
            zastupce = detaily[0]           # kody serazene -> nejmensi kod
            for a in detaily:
                if vloz_lecivo_z_detailu(cur, a, spc, a is zastupce):
                    poc["leciva"] += 1
            kod = zastupce["kodSUKL"]
            poc["spc"] += 1

            cur.execute("INSERT INTO leciva_search (kod_sukl, sekce, obsah_text) "
                        "VALUES (%s,'atributy',%s)", (kod, radek_atributy_spc(detaily)))
            poc["radky_atributy"] += 1

            nahraj_sekce(cur, kod, adr, adr / "json", zastupce, poc, jen_ok)
            if n % 250 == 0:
                conn.commit()
                print(f"  ... {n}/{len(spcs)} SPC, {poc['radky_sekci']} radku, "
                      f"{time.perf_counter() - t0:.0f} s", flush=True)
        conn.commit()
        aktualizuj_vek(cur)
        conn.commit()

    print(f"\n{'SPC (zastupcu)':24} {poc['spc']}")
    print(f"{'kodu v leciva':24} {poc['leciva']}  (bez detailu: {poc['kod_bez_detailu']})")
    print(f"{'extraktu':24} {poc['extrakty']}")
    print(f"{'radku atributy':24} {poc['radky_atributy']}")
    print(f"{'radku ze sekci':24} {poc['radky_sekci']} (z toho {poc['se_stranou']} s cislem strany)")
    print("\nStavy:")
    for k, v in sorted(poc.items()):
        if k.startswith("stav_"):
            print(f"    {k[5:]:24} {v}")
    print(f"\nCas {time.perf_counter() - t0:.0f} s. Embeddingy zatim NEJSOU - "
          f"spust vytvor_embeddingy.py")
    return 0

def main() -> int:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    ap = argparse.ArgumentParser(description="Naplneni DB z korpusu data/spc/")
    ap.add_argument("--jen-ok", action="store_true",
                    help="jen sekce ve stavu 'ok' (bez zamitnutych)")
    ap.add_argument("--korpus", action="store_true",
                    help="cely korpus z data/spc, VZDY od nuly (hledaci slovnik zustava)")
    ap.add_argument("--limit-spc", type=int, help="s --korpus: jen prvnich N SPC (zkouska)")
    ap.add_argument("--obnov-sekci", choices=sorted(SEKCE_SPC),
                    help="korpus: znovu nahrat JEN tuto sekci, ostatni nechat (bez TRUNCATE)")
    ap.add_argument("--sjednot-klice", action="store_true",
                    help="korpus: klic = laicky tvar (1-4 slova) na stavajici DB, nic nemazat")
    ap.add_argument("--jen-vek", action="store_true",
                    help="korpus: jen prepocitat vek pouziti (common/vek.py), nic nemazat")
    a = ap.parse_args()
    if a.sjednot_klice:
        return sjednot_klice()
    if a.jen_vek:
        with psycopg.connect(PG_DSN) as conn, conn.cursor() as cur:
            aktualizuj_vek(cur)
            conn.commit()
        return 0
    if a.obnov_sekci:
        return obnov_sekci(a.obnov_sekci, a.jen_ok)
    if a.korpus:
        return main_korpus(a.jen_ok, a.limit_spc)

    ap.error("chybi rezim: --korpus, --obnov-sekci SEKCE, --jen-vek nebo --sjednot-klice")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
