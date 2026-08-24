#!/usr/bin/env python3
"""Krok 11: naplneni databaze z data/leciva/ a ze slovniku pojmu.

Co kam jde:

    api.json                 ->  leciva            (relacni data, zadny model)
    json/<sekce>.json        ->  extrakty          (cely vysledek extrakce)
    json/_stav.json          ->  extrakce_stav     (co se povedlo a co ne)
    json/<sekce>.json        ->  leciva_search     (1 radek = 1 hledatelna polozka)
    slovnik_pojmu.json       ->  slovnik_pojmu

DULEZITE - co NEJDE do hledaneho textu:
    sekce, frekvence, organovy_system jsou FILTRY. Kdyby byly v obsah_text,
    opakovaly by se pres stovky radku ("Gastrointestinalni poruchy" u kazde
    polozky) a znehodnotily fulltext i embedding. Do vektoru jde POUZE
    obsah_text.

Radek sekce='atributy':
    Jeden na lek, nepochazi z PDF ale z tabulky leciva. Slouzi k tomu, aby
    slo lek najit podle jmena, sily nebo kodu SUKL. Ma extrakt_id = NULL
    a kontext_text = NULL (identita uz je v obsah_text, bylo by to dvakrat).

Embeddingy tenhle skript NEPOCITA - to dela vytvor_embeddingy.py (krok 12).

Pouziti:
  uv run python naplni_db.py              # naplni, co jeste neni
  uv run python naplni_db.py --znovu      # smaze a naplni od nuly
  uv run python naplni_db.py --jen-ok     # jen sekce ve stavu 'ok'
"""

import io
import sys
import json
import argparse
from pathlib import Path
from collections import Counter

import psycopg

from common.config import LECIVA_DIR, PG_DSN, adresar_leciva
from common.sekce import SEKCE_SPC

SLOVNIK = Path("slovnik_pojmu.json")
SLOVNIK_RUCNI = Path("slovnik_rucni.json")

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


def vloz_lecivo(cur, adr: Path) -> str | None:
    f = adr / "api.json"
    if not f.exists():
        return None
    a = json.loads(f.read_text(encoding="utf-8"))
    kod = str(a.get("kodSUKL") or "").strip()
    if not kod:
        return None

    cur.execute("""
        INSERT INTO leciva (kod_sukl, nazev, doplnek, sila, lekova_forma, cesta,
                            atc, zpusob_vydeje, na_predpis, hrazeno,
                            registracni_cislo,
                            stav_registrace, je_dodavka, baleni, obal,
                            indikacni_skupina, ucinne_latky, api_json)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (kod_sukl) DO UPDATE SET
            nazev = EXCLUDED.nazev, api_json = EXCLUDED.api_json,
            hrazeno = EXCLUDED.hrazeno
    """, (kod, a.get("nazev"), a.get("doplnek"), a.get("sila"),
          a.get("lekovaFormaKod"), a.get("cestaKod"), a.get("ATCkod"),
          a.get("zpusobVydejeKod"), _na_predpis(a.get("zpusobVydejeKod")),
          kod in nacti_hrazene(),
          a.get("registracniCislo"), a.get("stavRegistraceKod"),
          a.get("jeDodavka"), a.get("baleni"), a.get("obalKod"),
          a.get("indikacniSkupinaKod"), _latky(a), json.dumps(a, ensure_ascii=False)))
    return kod


def radek_atributy(a: dict) -> str:
    """Identita leku jako hledatelny text: nazev, sila, forma, latky, kod."""
    casti = [a.get("nazev"), a.get("sila"), a.get("lekovaFormaKod")]
    casti += _latky(a)
    casti.append(a.get("kodSUKL"))
    return ", ".join(str(c) for c in casti if c)


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


def main() -> int:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    ap = argparse.ArgumentParser(description="Naplneni DB z data/leciva/")
    ap.add_argument("--kody", nargs="+", metavar="KOD")
    ap.add_argument("--znovu", action="store_true", help="smazat a naplnit od nuly")
    ap.add_argument("--jen-ok", action="store_true",
                    help="jen sekce ve stavu 'ok' (bez zamitnutych)")
    a = ap.parse_args()

    adresare = ([adresar_leciva(k) for k in a.kody] if a.kody
                else sorted(x for x in LECIVA_DIR.iterdir() if x.is_dir()))

    poc: Counter = Counter()
    with psycopg.connect(PG_DSN) as conn, conn.cursor() as cur:
        if a.znovu:
            # leciva staci - ostatni visi na ON DELETE CASCADE
            cur.execute("TRUNCATE leciva CASCADE; TRUNCATE slovnik_pojmu;")
            print("Tabulky vyprazdneny.")
        else:
            # POJISTKA: radky v leciva_search NEMAJI unikatni klic pres
            # obsah, takze druhy beh bez --znovu je proste PRISYPE a data
            # se tise zdvoji. Stalo se to 24.8. - evaluace pak hlasila
            # 1308 polozek misto 654 a vypadalo to jako chyba v datech.
            # Radsi skoncit, nez potichu rozbit korpus.
            uz_tam = cur.execute("SELECT count(*) FROM leciva_search").fetchone()[0]
            if uz_tam and not a.kody:
                print("CHYBA: leciva_search uz ma "
                      f"{uz_tam} radku. Bez --znovu by se data ZDVOJILA. "
                      "Pouzij:  uv run python naplni_db.py --znovu",
                      file=sys.stderr)
                return 1

        # --- slovnik pojmu -------------------------------------------------
        if SLOVNIK.exists():
            slovnik = json.loads(SLOVNIK.read_text(encoding="utf-8"))
            rucni = {}
            if SLOVNIK_RUCNI.exists():
                rucni = {k.lower(): v for k, v in
                         json.loads(SLOVNIK_RUCNI.read_text(encoding="utf-8")).items()
                         if not k.startswith("_")}
            for termin, laicky in slovnik.items():
                cur.execute("""
                    INSERT INTO slovnik_pojmu (termin, laicky, rucne_overeno)
                    VALUES (%s,%s,%s)
                    ON CONFLICT (termin) DO UPDATE SET
                        laicky = EXCLUDED.laicky,
                        rucne_overeno = EXCLUDED.rucne_overeno
                """, (termin.lower(), rucni.get(termin.lower(), laicky),
                      termin.lower() in rucni))
                poc["slovnik"] += 1

        # --- leciva a jejich sekce -----------------------------------------
        for adr in adresare:
            kod = vloz_lecivo(cur, adr)
            if not kod:
                continue
            poc["leciva"] += 1
            api = json.loads((adr / "api.json").read_text(encoding="utf-8"))

            # radek 'atributy' - identita leku, aby sel najit podle jmena
            cur.execute("""
                INSERT INTO leciva_search (kod_sukl, sekce, obsah_text)
                VALUES (%s,'atributy',%s)
            """, (kod, radek_atributy(api)))
            poc["radky_atributy"] += 1

            stav_f = adr / "json" / "_stav.json"
            stavy = json.loads(stav_f.read_text(encoding="utf-8")) if stav_f.exists() else {}

            for sekce in SEKCE_SPC:
                js = adr / "json" / f"{sekce}.json"
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

                # Ze zamitnute sekce se vyradi jen OZNACENE POLOZKY, ne cela
                # sekce. Kontrola oznacuje jednotlivosti - ACYLCOFFIN mel
                # 1 vadnou polozku ze 46 a driv se kvuli ni zahodilo vsech 46.
                # Pri --jen-ok jde do hledani vylucne stav 'ok'.
                vadne = set()
                if stav == "zamitnuto_kontrolou":
                    vadne = set((st.get("kontrola_modelem") or {}).get(
                        "chybne_indexy") or [])
                    if not vadne:
                        # Stary zaznam bez indexu - nezbyva nez vyradit celou.
                        poc["preskoceno_cela_sekce"] += 1
                        continue
                if a.jen_ok and stav != "ok":
                    poc["preskoceno_cela_sekce"] += 1
                    continue

                strana = strana_sekce(adr, sekce)
                for i, p in enumerate(polozky):
                    if i in vadne:
                        poc["preskocena_polozka"] += 1
                        continue
                    obsah, atr = text_polozky(sekce, p)
                    if not obsah:
                        continue
                    je_nu = sekce == "nezadouci_ucinky"
                    cur.execute("""
                        INSERT INTO leciva_search
                            (kod_sukl, extrakt_id, sekce, frekvence, frekvence_rank,
                             organovy_system, sekce_atributy, kontext_text,
                             obsah_text, strana_pdf)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """, (kod, extrakt_id, sekce,
                          p.get("frekvence") if je_nu and isinstance(p, dict) else None,
                          p.get("frekvence_rank") if je_nu and isinstance(p, dict) else None,
                          p.get("organovy_system") if je_nu and isinstance(p, dict) else None,
                          json.dumps(atr, ensure_ascii=False) if atr else None,
                          kontext(api), obsah, strana))
                    poc["radky_sekci"] += 1
                    if strana:
                        poc["se_stranou"] += 1

        conn.commit()

    print(f"{'leciv':24} {poc['leciva']}")
    print(f"{'extraktu':24} {poc['extrakty']}")
    print(f"{'radku atributy':24} {poc['radky_atributy']}")
    print(f"{'radku ze sekci':24} {poc['radky_sekci']} "
          f"(z toho {poc['se_stranou']} s cislem strany)")
    print(f"{'preskocene cele sekce':24} {poc['preskoceno_cela_sekce']}")
    print(f"{'preskocene polozky':24} {poc['preskocena_polozka']} (oznacene kontrolou)")
    print(f"{'slovnik pojmu':24} {poc['slovnik']}")
    print("\nStavy:")
    for k, v in sorted(poc.items()):
        if k.startswith("stav_"):
            print(f"    {k[5:]:24} {v}")
    print("\nEmbeddingy zatim NEJSOU - spust vytvor_embeddingy.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
