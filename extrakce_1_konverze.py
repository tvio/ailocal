#!/usr/bin/env python3
"""Konverze SPC do Markdownu přes Docling Serve (DGX Spark) – celý korpus.

Opakovaně spustitelné: stav každého dokumentu je v SQLite a nový běh
pokračuje tam, kde předchozí skončil (i po pádu, zatuhnutí nebo Ctrl+C).
Po každém dokumentu se hned pouští kontroly kvality proti PDF
(`common/kontrola_konverze.py`).

ROZSAH (povinně jeden):
  --obchodovana    platné (PLATNE_STAVY) a obchodované (je_dodavka) – ~9 200 kódů
  --vse            všechny kódy v platném stavu registrace
  --kod 0254048    jeden kód SÚKL (i opakovaně – převede znovu)

POSTUP – kroky navazují:
  0. SEZNAM LÉČIV: /aktualni-davky; při novém měsíčním vydání SÚKL stáhne
     seznam kódů + detaily z VEŘEJNÉHO API (/dlp/v1, ~5 min). API webu
     (/prehledy/v1) má týdenní přírůstky – NEMÍCHAT.
  1. INVENTÁŘ: u každého kódu /dokumenty-metadata -> identita SPC
     (CZ: id dokumentu, EU: odkaz na EPAR). DEDUPLIKACE podle identity –
     všechna balení EU přípravku mají TENTÝŽ EPAR, stahuje se jednou.
  2. KONVERZE: po unikátních SPC: stáhnout -> ořez před Přílohou II ->
     Docling Serve -> spc.md + strany.json -> kontroly -> stav.
  3. WORD: SPC, která SÚKL má jen jako .doc, převede MS Word na DOCX
     (obsah – Docling čte strukturu přímo) a PDF (GUI a čísla stránek).
     Běží po kroku 2, jedno po druhém.

POŘADÍ: podle registračního čísla, EU prokládané CZ (1 EU, 10 CZ) –
EMA má limit, SÚKL ne. EU kódy téhož přípravku (EU/1/xx/yyy/001, /002…)
mají jeden EPAR – inventář volá metadata jen pro jeden z nich.

DÁVKY: unikátní SPC jsou v tomto pořadí rozdělená do dávek
po --velikost-davky (výchozí 100). Čísla dávek jsou STABILNÍ – nezávisí
na tom, co už je hotové. Log ukazuje, ve které dávce se běží.
  --davka 17           jen dávka 17 (i hotové v ní převede znovu)
  --od-davky 17        dávky 17 až konec (hotové přeskočí)

ZATUHNUTÍ: každý dokument loguje ZAČÍNÁ a HOTOVO/CHYBA. Dokument, který
má ZAČÍNÁ bez konce, je ten, na kterém to stojí. Stav se do DB zapisuje
až po dokončení, takže přerušené dokumenty zůstávají 'ceka' a nový běh
(stejný příkaz) je vezme znovu.

OSTATNÍ:
  --paralelne 4        souběžných požadavků na Docling Serve
  --znovu-chyby        zkusit znovu dokumenty ve stavu chyba/timeout
  --stav               jen vypsat souhrn, podezřelé, chyby a kde se stálo
                       (report podezřelých data/spc/_report/podezrele.html
                       se vytváří na konci KAŽDÉHO běhu)
  --prekontroluj       přepočítat kontroly nad hotovými Markdowny (bez konverze)
  --jen-inventar       jen krok 0 + 1 (seznam léčiv + inventář)
  --bez-obnovy         nepřestahovat seznam léčiv (jinak se obnoví při novém
                       měsíčním vydání SÚKL – common/seznam_leciv.py)
  --ema-rozestup 10    min. s mezi dvěma staženími z EMA; + Retry-After při 429

Výstup: data/spc/<identita>/{spc.pdf, spc.md, strany.json, kontrola.json}
        data/spc/_stav.sqlite     stav inventáře i konverze
        logs/konverze_serve_<čas>.log

Příklady:
  uv run python extrakce_1_konverze.py --kod 0254048
  uv run python extrakce_1_konverze.py --obchodovana
  uv run python extrakce_1_konverze.py --obchodovana --od-davky 17
  uv run python extrakce_1_konverze.py --stav
"""

import io
import re
import sys
import json
import time
import sqlite3
import logging
import argparse
import threading
import subprocess
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

import common.konverze as konverze            # nastavi TORCHDYNAMO_DISABLE
from common.config import SUKL_API, DATA_DIR, DOCLING_SERVE_URL
from common.kontrola_konverze import zkontroluj, strana_sekce
from common.seznam_leciv import PLATNE_STAVY

VYSTUP = DATA_DIR / "spc"
DB = VYSTUP / "_stav.sqlite"
TIMEOUT_PDF = 600          # s na jedno PDF (EPAR má i 100 stran)

# Nastavení převodu = produkce (common/konverze.py) a benchmark Codexu.
VOLBY = {
    "to_formats": ["md", "json"],        # json kvůli číslům stránek nadpisů
    "pipeline": "standard",
    "pdf_backend": "pypdfium2",
    "do_ocr": "false",
    "do_table_structure": "true",
    "table_mode": "accurate",
    "table_cell_matching": "true",
    "image_export_mode": "placeholder",
    "include_images": "false",
}

log = logging.getLogger("konverze")


# =============================================================================
# stav (SQLite) – zapisuje JEN hlavní vlákno
# =============================================================================
def db() -> sqlite3.Connection:
    VYSTUP.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB)
    c.executescript("""
        CREATE TABLE IF NOT EXISTS kody (
            kod TEXT PRIMARY KEY, nazev TEXT, eu INTEGER,
            identita TEXT, url TEXT, stav TEXT, chyba TEXT, zmeneno TEXT);
        CREATE TABLE IF NOT EXISTS spc (
            identita TEXT PRIMARY KEY, url TEXT, kod TEXT, nazev TEXT, eu INTEGER,
            stav TEXT DEFAULT 'ceka', pokusu INTEGER DEFAULT 0,
            cas_s REAL, stran INTEGER, znaku INTEGER, tabulek INTEGER,
            verdikt TEXT, duvody TEXT, chyba TEXT, zmeneno TEXT);
    """)
    return c


def ted() -> str:
    return datetime.now().isoformat(timespec="seconds")


def slozka(identita: str) -> Path:
    return VYSTUP / re.sub(r"[^\w.-]+", "_", identita)[:80]


# =============================================================================
# 1) INVENTÁŘ
# =============================================================================


def rozsah_kodu(a) -> tuple[list[dict], bool]:
    """Kódy v rozsahu + zda přišlo nové vydání seznamu léčiv.

    Seznam se na začátku běhu OBNOVÍ z veřejného API (common/seznam_leciv.py),
    když SÚKL vydal nové měsíční vydání. Seznam z 24. 8. byl o vydání
    pozadu a 5 kódů mezitím zaniklo.
    """
    if a.bez_obnovy or a.kod:
        pool = json.loads((DATA_DIR / "pool_leciv.json").read_text(encoding="utf-8"))
        nove = False
    else:
        from common.seznam_leciv import obnov_seznam
        pool, _, nove = obnov_seznam()
    if a.kod:
        z = [r for r in pool if r.get("kod_sukl") == a.kod]
        if not z:
            sys.exit(f"kód {a.kod} v pool_leciv.json není")
        return z[:1], False
    z = [r for r in pool if r.get("kod_sukl") and r.get("stav_registrace") in PLATNE_STAVY]
    if a.obchodovana:
        z = [r for r in z if r.get("je_dodavka")]
    return z, nove


def vycisti(c: sqlite3.Connection, kody: list[dict]) -> None:
    """Kódy v inventáři, které už NEJSOU v rozsahu (zanikly, přestaly být
    obchodované, změnil se stav registrace), se odstraní. Jejich SPC zůstávají
    na disku; spotřebovávají je jen kódy, které v inventáři jsou."""
    platne = {r["kod_sukl"] for r in kody}
    pryc = [k for (k,) in c.execute("SELECT kod FROM kody") if k not in platne]
    if pryc:
        c.executemany("DELETE FROM kody WHERE kod=?", [(k,) for k in pryc])
        c.commit()
        log.info("INVENTÁŘ: %d kódů už není v rozsahu – odstraněno (např. %s)",
                 len(pryc), ", ".join(pryc[:5]))


def _identita(kod: str, s: requests.Session) -> tuple[str | None, str | None, str]:
    """(identita, url ke stažení, stav). Stav: ok | bez_spc | chyba."""
    for pokus in range(3):
        try:
            r = s.get(f"{SUKL_API}/dokumenty-metadata/{kod}", timeout=30)
            if r.status_code == 429:
                time.sleep(5 * 2 ** pokus)
                continue
            if not r.ok:
                return None, None, "bez_spc" if r.status_code == 404 else f"chyba HTTP {r.status_code}"
            spc = next((x for x in r.json() if isinstance(x, dict) and x.get("typ") == "SPC"), None)
            if not spc:
                return None, None, "bez_spc"
            if spc.get("id"):
                # /dokumenty/{id} vrací 400 – CZ se stahuje přes kód
                return f"cz_{spc['id']}", f"{SUKL_API}/dokumenty/{kod}/spc", "ok"
            if spc.get("link"):
                # Odkaz na EMA = EPAR (EU registrace). Jiný odkaz NENÍ SPC:
                # neregistrované LP (stav F/I – léčebný program, mimořádné
                # opatření) odkazují na WEBOVOU STRÁNKU SÚKL o povolení
                # (sukl.gov.cz/neregistrovane-lecive-pripravky/…), 25.9.
                if "ema.europa.eu" not in spc["link"]:
                    return None, spc["link"], "bez_spc"
                jm = spc["link"].rstrip("/").rsplit("/", 1)[-1].removesuffix(".pdf")
                return f"eu_{jm}", spc["link"], "ok"
            return None, None, "bez_spc"
        except requests.RequestException as e:
            if pokus == 2:
                return None, None, f"chyba {type(e).__name__}"
            time.sleep(2)
    return None, None, "chyba 429"


_EU_ZAKLAD = re.compile(r"(EU/\d/\d+/\d+)")


def reg_zaklad(reg: str | None) -> str:
    """Registrační číslo bez koncovky balení: EU/1/97/053/003 -> EU/1/97/053.
    CZ číslo zůstává celé (07/227/22-C)."""
    m = _EU_ZAKLAD.match(reg or "")
    return m.group(1) if m else (reg or "")


def inventar(c: sqlite3.Connection, kody: list[dict], vynutit: bool,
             obnovit: bool = False) -> None:
    """Identita SPC ke každému kódu.

    EU: jeden EPAR na přípravek – všechny kódy se stejným ZÁKLADEM
    registračního čísla (EU/1/xx/yyy, koncovka /001 = balení) mají
    TENTÝŽ dokument. Ověřeno 25.9. na 1 806 EU kódech: 839 skupin,
    každá přesně 1 SPC. Metadata se proto volají jen pro první kód
    skupiny, ostatní identitu převezmou.

    CZ: NE. 121 z 4 563 CZ registračních čísel má pod různými kódy
    RŮZNÉ dokumenty (většinou jiné verze téhož SPC, 74× shoda textu
    > 98 %). Jeden dokument na číslo by části kódů tiše dal jinou verzi.
    CZ se proto ptá u každého kódu – stahuje a převádí se stejně jen
    jednou na identitu dokumentu.
    """
    # obnovit = nové vydání seznamu: identitu SPC ověřit u všech kódů znovu
    # (nová verze dokumentu = nové id -> nové SPC ke konverzi). EU skupiny
    # dál převezmou identitu podle registračního čísla.
    hotove = set() if obnovit else {
        k for (k,) in c.execute("SELECT kod FROM kody WHERE stav IN ('ok','bez_spc')")}
    zbyva = [r for r in kody if vynutit or r["kod_sukl"] not in hotove]

    # EU: identita už známá pro základ registračního čísla -> bez volání
    eu_zname = {}
    for kod, ident, url in c.execute(
            "SELECT kod, identita, url FROM kody WHERE identita LIKE 'eu_%'"):
        eu_zname.setdefault(kod, (ident, url))
    reg_kodu = {r["kod_sukl"]: reg_zaklad(r.get("registracni_cislo")) for r in kody}
    zaklad_ident = {reg_kodu[k]: v for k, v in eu_zname.items() if k in reg_kodu}
    prevzate, volat, videne_eu = [], [], set()
    for r in zbyva:
        z = reg_kodu[r["kod_sukl"]]
        if z.startswith("EU/") and not vynutit:
            if z in zaklad_ident and not obnovit:
                prevzate.append((r, *zaklad_ident[z]))
                continue
            if z in videne_eu:              # jiný kód téže skupiny už se volá
                prevzate.append((r, None, None))
                continue
            videne_eu.add(z)
        volat.append(r)
    log.info("INVENTÁŘ: %d kódů v rozsahu, %d už známých, zjišťuje se %d "
             "(volání API %d, EU převzato z registračního čísla %d)",
             len(kody), len(kody) - len(zbyva), len(zbyva), len(volat), len(prevzate))
    if not zbyva:
        return
    zbyva = volat
    s = requests.Session()
    t0 = time.time()
    vynechano_v12 = 0
    # 6 souběžných dotazů na veřejné API – dost na rychlost, ne na zátěž
    with ThreadPoolExecutor(6) as ex:
        buducnost = {ex.submit(_identita, r["kod_sukl"], s): r for r in zbyva}
        for i, f in enumerate(as_completed(buducnost), 1):
            r = buducnost[f]
            ident, url, stav = f.result()
            # Homeopatika (ATC V12) bez SPC se NEEVIDUJÍ – registrují se
            # zjednodušeně a SPC nemají (25.9.: 332 z 357 obchodovaných).
            # Zatím mimo rozsah, viz todo.md. V12 S SPC (Oscillococcinum,
            # Traumeel… – registrace s indikací) se evidují normálně.
            if stav == "bez_spc" and (r.get("atc") or "").startswith("V12"):
                vynechano_v12 += 1
                continue
            c.execute("INSERT OR REPLACE INTO kody VALUES (?,?,?,?,?,?,?,?)",
                      (r["kod_sukl"], r["nazev"], int(bool(r.get("eu_registrace"))),
                       ident, url, "ok" if stav == "ok" else stav.split()[0],
                       None if stav in ("ok", "bez_spc") else stav, ted()))
            if ident:
                c.execute("""INSERT OR IGNORE INTO spc (identita, url, kod, nazev, eu, zmeneno)
                             VALUES (?,?,?,?,?,?)""",
                          (ident, url, r["kod_sukl"], r["nazev"],
                           int(bool(r.get("eu_registrace"))), ted()))
            if i % 200 == 0 or i == len(zbyva):
                c.commit()
                zb = (time.time() - t0) / i * (len(zbyva) - i)
                log.info("  inventář %d/%d  (zbývá ~%d min)", i, len(zbyva), zb / 60)
    c.commit()
    # EU kódy převzaté ze skupiny: identitu dostanou od kódu, který se volal
    zaklad_ident.update({reg_kodu[k]: (i, u) for k, i, u in c.execute(
        "SELECT kod, identita, url FROM kody WHERE identita LIKE 'eu_%'") if k in reg_kodu})
    for r, ident, url in prevzate:
        if ident is None:
            ident, url = zaklad_ident.get(reg_kodu[r["kod_sukl"]], (None, None))
        c.execute("INSERT OR REPLACE INTO kody VALUES (?,?,?,?,?,?,?,?)",
                  (r["kod_sukl"], r["nazev"], 1, ident, url,
                   "ok" if ident else "bez_spc",
                   "převzato z registračního čísla" if ident else None, ted()))
    c.commit()
    n_spc = c.execute("SELECT count(*) FROM spc").fetchone()[0]
    stavy = dict(c.execute("SELECT stav, count(*) FROM kody GROUP BY stav").fetchall())
    log.info("INVENTÁŘ HOTOV: kódy %s -> %d unikátních SPC (homeopatik bez SPC "
             "vynecháno: %d)", stavy, n_spc, vynechano_v12)


# =============================================================================
# 2) KONVERZE jednoho dokumentu (běží ve vlákně, do DB nesahá)
# =============================================================================
# EMA (EU EPARy) při 4 souběžných staženích vracela 429: v prvním plném
# běhu 826 z 839 EU SPC. Stahování z EMA proto jde JEDNO PO DRUHÉM
# s rozestupem a při 429 se čeká (Retry-After) a zkouší znovu.
# Docling na Sparku běží dál paralelně – omezuje se jen stahování.
_EMA_ZAMEK = threading.Lock()
# Mezi dvěma staženími z EMA vždy aspoň 10 s (EU hned po EU) a navíc
# Retry-After. Změřeno: samotný 10s rozestup 429 nezabrání (přišlo po 5
# staženích), ale EMA zatěžuje méně; tempo pak dorovná Retry-After.
_ema_rozestup = [10.0]                   # --ema-rozestup
_ema_posledni = [0.0]


VYPADEK = {502, 503, 504}     # dočasná nedostupnost serveru – opakovat


def posli_doclingu(s: requests.Session, **kw) -> requests.Response:
    """POST na Docling Serve s opakováním při výpadku (502/503/504 – tunel,
    přetížený server; 25.9. DOCETAXEL KABI 504). Vypršení čtení
    (requests.Timeout) se NEOPAKUJE – dlouhý dokument by čekal znovu
    TIMEOUT_PDF a skončil stejně."""
    for pokus in range(3):
        try:
            r = s.post(f"{DOCLING_SERVE_URL}/v1/convert/file", **kw)
        except requests.ConnectionError:
            if pokus == 2:
                raise
            r = None
        if r is not None and r.status_code not in VYPADEK:
            r.raise_for_status()
            return r
        pauza = 30.0 * (pokus + 1)
        log.info("Docling Serve %s – zkusím znovu za %.0f s (pokus %d/3)",
                 r.status_code if r is not None else "nedostupný", pauza, pokus + 1)
        time.sleep(pauza)
    r.raise_for_status()
    return r


def stahni(url: str, s: requests.Session) -> requests.Response:
    ema = "ema.europa.eu" in url
    for pokus in range(6):
        if ema:
            with _EMA_ZAMEK:
                cekej = _ema_posledni[0] + _ema_rozestup[0] - time.time()
                if cekej > 0:
                    time.sleep(cekej)
                r = s.get(url, timeout=(10, 180))
                _ema_posledni[0] = time.time()
        else:
            r = s.get(url, timeout=(10, 180))
        if r.status_code in VYPADEK and pokus < 3:
            # Krátký výpadek serveru (EMA 25.9.: 4× 503, 1× 502 z ~800
            # stažení) – nesouvisí s tempem, opakování ho vyřeší.
            pauza = 30.0 * (pokus + 1)
            log.info("%d od %s – výpadek, zkusím znovu za %.0f s (pokus %d/3)",
                     r.status_code, "EMA" if ema else "SÚKL", pauza, pokus + 1)
            time.sleep(pauza)
            continue
        if r.status_code != 429:
            r.raise_for_status()
            return r
        # EMA posílá Retry-After jako DESETINNÉ číslo ("10.000", "6.971").
        # První verze četla jen celé (isdigit) a místo 10 s čekala 30–180 s
        # – proto šlo stahování 25. 9. dopoledne ~1 dok/min. Změřeno:
        # s přesným Retry-After 7,2 dok/min, 11× 429 na 25 dokumentů.
        retry = r.headers.get("Retry-After", "").strip()
        try:
            pauza = max(float(retry), 1.0)
        except ValueError:
            pauza = 30.0 * (pokus + 1)
        log.info("429 od %s – čekám %.0f s podle Retry-After (pokus %d/6)",
                    "EMA" if ema else "SÚKL", pauza, pokus + 1)
        if ema:
            with _EMA_ZAMEK:                 # ať mezitím nestahuje nikdo jiný
                time.sleep(pauza)
        else:
            time.sleep(pauza)
    r.raise_for_status()
    return r


class NeniPdf(Exception):
    """SPC není PDF (např. .doc). Není to chyba převodu – jiný formát."""


def _atomicky(cesta: Path, obsah) -> None:
    tmp = cesta.with_name(cesta.name + ".tmp")
    if isinstance(obsah, bytes):
        tmp.write_bytes(obsah)
    else:
        tmp.write_text(obsah, encoding="utf-8")
    tmp.replace(cesta)


def _strany(json_doc: dict) -> dict[str, int]:
    """Nadpis -> číslo stránky (jako konverze.konvertuj_pdf)."""
    ven: dict[str, int] = {}
    for t in (json_doc or {}).get("texts", []):
        if t.get("label") in ("section_header", "title") and (t.get("text") or "").strip():
            prov = t.get("prov") or []
            if prov and prov[0].get("page_no"):
                ven.setdefault(t["text"].strip(), prov[0]["page_no"])
    return ven


def zpracuj(rad: dict, s: requests.Session) -> dict:
    ident = rad["identita"]
    adr = slozka(ident)
    adr.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()

    pdf = adr / "spc.pdf"
    if not pdf.exists():
        r = stahni(rad["url"], s)
        if not r.content[:5].startswith(b"%PDF"):
            # SÚKL má část SPC jen jako Word (.doc – CAVINTON). Uloží se
            # s původní příponou a dokument dostane stav neni_pdf, ne chyba.
            jm = re.search(r'filename="?([^";]+)', r.headers.get("content-disposition", ""))
            pripona = Path(jm.group(1)).suffix.lower() if jm else ".bin"
            _atomicky(adr / f"spc{pripona}", r.content)
            raise NeniPdf(pripona)
        _atomicky(pdf, r.content)

    vstup, _, stran = konverze.orizni_pdf_pred_konverzi(pdf, cil=adr / "spc_orez.pdf")
    odp = posli_doclingu(s, files={"files": (f"{ident}.pdf", vstup.read_bytes(), "application/pdf")},
                         data=VOLBY, timeout=(10, TIMEOUT_PDF))
    d = odp.json()
    doc = d.get("document") or {}
    md = doc.get("md_content")
    if d.get("status") != "success" or not (md or "").strip():
        raise ValueError(f"Docling: {d.get('status')} {d.get('errors')}"[:200])
    # Pojistka jako v produkci: kdyby ořez PDF nezabral
    md, _ = konverze.orizni_eu_dokument(md)
    strany = _strany(doc.get("json_content"))

    import pymupdf
    with pymupdf.open(str(vstup)) as dd:
        po_strankach = [p.get_text("text") for p in dd]
    # Značky se čtou z ORIGINÁLU – ořez před Přílohou II je zahodí.
    kontrola = zkontroluj(md, vstup, "\n".join(po_strankach),
                          strana_sekce(po_strankach, "4.8"), pdf_original=pdf)

    _atomicky(adr / "spc.md", md)
    _atomicky(adr / "strany.json", json.dumps(strany, ensure_ascii=False, indent=1))
    _atomicky(adr / "kontrola.json", json.dumps(kontrola, ensure_ascii=False, indent=1))
    return {"cas_s": round(time.perf_counter() - t0, 1), "stran": stran, "znaku": len(md),
            "tabulek": konverze.spocitej_md_tabulky(md), "kontrola": kontrola,
            "server_s": d.get("processing_time")}


# =============================================================================
# 2b) SPC, která SÚKL má jen jako WORD (.doc) – CAVINTON
# =============================================================================
# .doc je strukturovaný dokument (tabulky jako tabulky). Převod do PDF by
# strukturu zahodil a Docling by ji zpětně ODHADOVAL z vzhledu stránky.
# Proto: Word -> DOCX (zdroj obsahu, Docling čte strukturu přímo)
#        Word -> PDF se značkami (GUI: odkaz na stranu; kontroly)
PS_WORD = Path(__file__).parent / "common" / "doc_na_pdf.ps1"
_NADPIS_TUCNE = re.compile(r"^\d{1,2}(\.\d{1,2})?\.?\s+\S")


def povys_nadpisy(md: str) -> str:
    """Tučný číslovaný řádek -> nadpis `##`.

    Docling u DOCX dělá `##` jen ze stylu „Nadpis". Autoři SPC ho
    nepoužívají – CAVINTON má „**4.8 Nežádoucí účinky**". common/sekce.py
    hledá sekce podle `##`, bez povýšení by 4.x nenašel.
    """
    ven = []
    for radek in md.splitlines():
        r = radek.strip()
        if r.startswith("**") and r.endswith("**") and not r.startswith("|"):
            t = re.sub(r"\s+", " ", r.replace("*", "")).strip()
            if _NADPIS_TUCNE.match(t):
                ven.append(f"## {t}")
                continue
        ven.append(radek)
    return "\n".join(ven)


def strany_z_pdf(md: str, po_strankach: list[str]) -> dict[str, int]:
    """Nadpis `##` -> strana, dohledáním textu nadpisu v PDF (DOCX stránky
    nemá). Hledá se od strany předchozího nadpisu dál, ať se opakovaný
    text („Pediatrická populace") přiřadí správnému výskytu."""
    norm = lambda s: re.sub(r"\s+", " ", s).strip().lower()
    stranky = [norm(t) for t in po_strankach]
    ven: dict[str, int] = {}
    od = 0
    for radek in md.splitlines():
        if not radek.startswith("#"):
            continue
        nadpis = radek.lstrip("#").strip()
        klic = norm(nadpis)[:40]
        for i in range(od, len(stranky)):
            if klic and klic in stranky[i]:
                ven.setdefault(nadpis, i + 1)
                od = i
                break
    return ven


def zpracuj_word(rad: dict, s: requests.Session) -> dict:
    adr = slozka(rad["identita"])
    zdroj = next((p for p in adr.glob("spc.*")
                  if p.suffix.lower() in (".doc", ".docx", ".rtf")), None)
    if zdroj is None:
        raise FileNotFoundError("chybí stažený Word soubor")
    t0 = time.perf_counter()
    docx, pdf = adr / "obsah.docx", adr / "spc.pdf"
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                    "-File", str(PS_WORD), str(zdroj.resolve()),
                    str(docx.resolve()), str(pdf.resolve())],
                   check=True, capture_output=True, text=True, timeout=300)
    odp = posli_doclingu(s,
                 files={"files": (f"{rad['identita']}.docx", docx.read_bytes(),
                                  "application/vnd.openxmlformats-officedocument."
                                  "wordprocessingml.document")},
                 data={"to_formats": ["md", "json"], "image_export_mode": "placeholder"},
                 timeout=(10, TIMEOUT_PDF))
    odp.raise_for_status()
    d = odp.json()
    md = (d.get("document") or {}).get("md_content") or ""
    if d.get("status") != "success" or not md.strip():
        raise ValueError(f"Docling DOCX: {d.get('status')} {d.get('errors')}"[:200])
    md = povys_nadpisy(md)

    import pymupdf
    with pymupdf.open(str(pdf)) as dd:
        po_strankach = [p.get_text("text") for p in dd]
        stran = dd.page_count
    kontrola = zkontroluj(md, pdf, "\n".join(po_strankach),
                          strana_sekce(po_strankach, "4.8"), pdf_original=pdf)
    kontrola["zdroj"] = f"word {zdroj.suffix} -> docx (obsah) + pdf (stránky)"
    _atomicky(adr / "spc.md", md)
    _atomicky(adr / "strany.json", json.dumps(strany_z_pdf(md, po_strankach),
                                              ensure_ascii=False, indent=1))
    _atomicky(adr / "kontrola.json", json.dumps(kontrola, ensure_ascii=False, indent=1))
    return {"cas_s": round(time.perf_counter() - t0, 1), "stran": stran, "znaku": len(md),
            "tabulek": konverze.spocitej_md_tabulky(md), "kontrola": kontrola}


def konvertuj_word(c: sqlite3.Connection, jen_identity: set[str] | None) -> None:
    """Všechna SPC ve stavu neni_pdf (Word). Jedno po druhém – Word nesnese
    souběžný přístup."""
    rady = [dict(zip(("identita", "nazev", "kod"), r)) for r in c.execute(
        "SELECT identita, nazev, kod FROM spc WHERE stav='neni_pdf' ORDER BY identita")]
    if jen_identity is not None:
        rady = [r for r in rady if r["identita"] in jen_identity]
    if not rady:
        return
    log.info("WORD: %d SPC jen jako Word -> DOCX (obsah) + PDF (stránky)", len(rady))
    s = requests.Session()
    for i, r in enumerate(rady, 1):
        log.info("ZAČÍNÁ   [word] %s %s (kód %s)", r["identita"], r["nazev"], r["kod"])
        try:
            v = zpracuj_word(r, s)
            k = v["kontrola"]
            c.execute("""UPDATE spc SET stav='ok', pokusu=pokusu+1, cas_s=?, stran=?, znaku=?,
                         tabulek=?, verdikt=?, duvody=?, chyba=NULL, zmeneno=? WHERE identita=?""",
                      (v["cas_s"], v["stran"], v["znaku"], v["tabulek"], k["verdikt"],
                       "; ".join(["zdroj Word"] + k["duvody"]), ted(), r["identita"]))
            log.info("HOTOVO   [word %d/%d] %s %s  %d str. %.1f s  %s%s", i, len(rady),
                     r["identita"], r["nazev"][:30], v["stran"], v["cas_s"],
                     k["verdikt"].upper(), f" ({'; '.join(k['duvody'])})" if k["duvody"] else "")
        except Exception as e:
            c.execute("UPDATE spc SET chyba=?, zmeneno=? WHERE identita=?",
                      (f"word: {type(e).__name__}: {e}"[:300], ted(), r["identita"]))
            log.error("CHYBA    [word %d/%d] %s %s  %s: %s", i, len(rady), r["identita"],
                      r["nazev"][:30], type(e).__name__, str(e)[:200])
        c.commit()


# =============================================================================
# 3) ŘÍZENÍ BĚHU
# =============================================================================
CZ_MEZI_EU = 10          # po každém EU dokumentu tolik CZ


def poradi(vse: list[dict]) -> list[dict]:
    """Fronta: podle registračního čísla, EU PROKLÁDANÉ CZ (1 EU, 10 CZ, …).

    Proč: EMA pustí jen malou dávku stažení a pak vrací 429 (poznatky
    25.9.). Seřazeno podle identity šly všechny EU na konec a stahovaly
    se naráz – 826× 429. Proložené CZ dokumenty (SÚKL, bez limitu) dají
    EMA mezi dvěma EU staženími přirozený odstup; zbytek hlídá
    _ema_rozestup + Retry-After.
    Pořadí se počítá z CELÉHO seznamu (ne jen z nehotových), takže čísla
    dávek jsou stabilní, dokud se nezmění inventář.
    """
    pool = json.loads((DATA_DIR / "pool_leciv.json").read_text(encoding="utf-8"))
    reg = {r["kod_sukl"]: reg_zaklad(r.get("registracni_cislo")) for r in pool if r.get("kod_sukl")}
    klic = lambda r: (reg.get(r["kod"], "~"), r["identita"])
    eu = sorted((r for r in vse if r["identita"].startswith("eu_")), key=klic)
    cz = sorted((r for r in vse if not r["identita"].startswith("eu_")), key=klic)
    ven = []
    while eu or cz:
        if eu:
            ven.append(eu.pop(0))
        ven += cz[:CZ_MEZI_EU]
        del cz[:CZ_MEZI_EU]
    return ven


def konvertuj(c: sqlite3.Connection, a, jen_identity: set[str] | None) -> int:
    # Rozpracované dokumenty se do DB NEZAPISUJÍ – do dokončení zůstávají
    # 'ceka', takže je po pádu nový běh prostě vezme znovu. Který dokument
    # zatuhl, ukáže log: řádek ZAČÍNÁ bez HOTOVO/CHYBA.
    vse = c.execute("SELECT identita, url, kod, nazev, stav FROM spc").fetchall()
    vse = poradi([dict(zip(("identita", "url", "kod", "nazev", "stav"), r)) for r in vse])
    V = a.velikost_davky
    davek = (len(vse) + V - 1) // V
    for i, r in enumerate(vse):
        r["davka"] = i // V + 1

    stavy_ke_zpracovani = {"ceka"} | ({"chyba", "timeout"} if a.znovu_chyby else set())
    if jen_identity is not None:                      # --kod: vždy znovu
        fronta = [r for r in vse if r["identita"] in jen_identity]
    elif a.davka:
        fronta = [r for r in vse if r["davka"] == a.davka]
    else:
        fronta = [r for r in vse if r["davka"] >= a.od_davky and r["stav"] in stavy_ke_zpracovani]

    log.info("KONVERZE: %d unikátních SPC v %d dávkách po %d; ke zpracování %d "
             "(Docling Serve %s, souběžně %d)",
             len(vse), davek, V, len(fronta), DOCLING_SERVE_URL, a.paralelne)
    if not fronta:
        return 0

    zamek = threading.Lock()
    s = requests.Session()
    s.mount("http://", requests.adapters.HTTPAdapter(pool_maxsize=a.paralelne * 2))
    t0 = time.time()
    hotovo = chyb = podezrelych = 0
    posledni_davka = None

    bezi: dict[str, tuple[float, dict]] = {}      # identita -> (začátek, řádek)

    def uloha(r):
        with zamek:
            bezi[r["identita"]] = (time.time(), r)
            log.info("ZAČÍNÁ   [dávka %d] %s %s (kód %s)",
                     r["davka"], r["identita"], r["nazev"], r["kod"])
        try:
            return zpracuj(r, s)
        finally:
            with zamek:
                bezi.pop(r["identita"], None)

    # HLÍDAČ: každou minutu vypíše dokumenty, které běží přes 2 minuty.
    # Zatuhnutí je pak vidět přímo v logu, bez párování ZAČÍNÁ/HOTOVO
    # mezi souběžnými dokumenty.
    konec = threading.Event()

    def hlidac():
        while not konec.wait(60):
            with zamek:
                dlouho = [(time.time() - t0_, r) for t0_, r in bezi.values()
                          if time.time() - t0_ > 120]
            for trva, r in sorted(dlouho, key=lambda x: -x[0]):
                log.warning("BĚŽÍ DLOUHO %.0f min: [dávka %d] %s %s (timeout po %d min)",
                            trva / 60, r["davka"], r["identita"], r["nazev"],
                            TIMEOUT_PDF // 60)

    threading.Thread(target=hlidac, daemon=True).start()

    with ThreadPoolExecutor(a.paralelne) as ex:
        buducnost = {ex.submit(uloha, r): r for r in fronta}
        for f in as_completed(buducnost):
            r = buducnost[f]
            if r["davka"] != posledni_davka:
                log.info("=== DÁVKA %d/%d (pokračovat od ní: --od-davky %d)",
                         r["davka"], davek, r["davka"])
                posledni_davka = r["davka"]
            try:
                v = f.result()
                k = v["kontrola"]
                c.execute("""UPDATE spc SET stav='ok', pokusu=pokusu+1, cas_s=?, stran=?,
                             znaku=?, tabulek=?, verdikt=?, duvody=?, chyba=NULL, zmeneno=?
                             WHERE identita=?""",
                          (v["cas_s"], v["stran"], v["znaku"], v["tabulek"], k["verdikt"],
                           "; ".join(k["duvody"]) or None, ted(), r["identita"]))
                hotovo += 1
                podezrelych += k["verdikt"] != "ok"
                log.info("HOTOVO   [%d/%d] %s %s  %d str. %.1f s  %s%s",
                         hotovo + chyb, len(fronta), r["identita"], r["nazev"][:30],
                         v["stran"], v["cas_s"], k["verdikt"].upper(),
                         f" ({'; '.join(k['duvody'])})" if k["duvody"] else "")
            except NeniPdf as e:
                c.execute("UPDATE spc SET stav='neni_pdf', chyba=?, zmeneno=? WHERE identita=?",
                          (f"formát {e}", ted(), r["identita"]))
                hotovo += 1
                log.warning("NENÍ PDF [%d/%d] %s %s  formát %s – uloženo, nepřevádí se",
                            hotovo + chyb, len(fronta), r["identita"], r["nazev"][:30], e)
            except Exception as e:
                stav = "timeout" if isinstance(e, requests.Timeout) else "chyba"
                c.execute("""UPDATE spc SET stav=?, pokusu=pokusu+1, chyba=?, zmeneno=?
                             WHERE identita=?""",
                          (stav, f"{type(e).__name__}: {e}"[:300], ted(), r["identita"]))
                chyb += 1
                log.error("CHYBA    [%d/%d] %s %s  %s: %s",
                          hotovo + chyb, len(fronta), r["identita"], r["nazev"][:30],
                          stav.upper(), f"{type(e).__name__}: {e}"[:200])
            c.commit()                       # stav po KAŽDÉM dokumentu

            n = hotovo + chyb
            if n % 25 == 0 or n == len(fronta):
                uplynulo = time.time() - t0
                zbyva = uplynulo / n * (len(fronta) - n)
                log.info("--- PRŮBĚH %d/%d  ok %d, chyb %d, podezřelých %d  |  %.0f min, "
                         "zbývá ~%.0f min (hotovo kolem %s)", n, len(fronta), hotovo, chyb,
                         podezrelych, uplynulo / 60, zbyva / 60,
                         datetime.fromtimestamp(time.time() + zbyva).strftime("%H:%M"))
    konec.set()
    return chyb


def nedokoncene_v_logu() -> tuple[Path | None, list[str]]:
    """Z posledního logu: dokumenty se ZAČÍNÁ bez HOTOVO/CHYBA.
    Po pádu nebo zatuhnutí přesně ty, na kterých se stálo."""
    logy = sorted(Path("logs").glob("konverze_serve_*.log"))
    if not logy:
        return None, []
    zacate: dict[str, str] = {}
    for radek in logy[-1].read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.search(r"(ZAČÍNÁ|HOTOVO|CHYBA|NENÍ PDF)\s+\[[^\]]+\]\s+(\S+)", radek)
        if not m:
            continue
        if m.group(1) == "ZAČÍNÁ":
            zacate[m.group(2)] = radek
        else:
            zacate.pop(m.group(2), None)
    return logy[-1], list(zacate.values())


def prekontroluj(c: sqlite3.Connection) -> None:
    """Přepočítá kontroly nad HOTOVÝMI Markdowny – bez nové konverze.
    Pro případ, že se opraví kontrola (DEPREX: řádky přes celou šířku)."""
    import pymupdf
    rady = c.execute("SELECT identita, nazev FROM spc WHERE stav='ok' ORDER BY identita").fetchall()
    log.info("PŘEKONTROLA %d hotových SPC", len(rady))
    pred = dict(c.execute("SELECT verdikt, count(*) FROM spc WHERE stav='ok' GROUP BY verdikt"))
    for i, (ident, nazev) in enumerate(rady, 1):
        adr = slozka(ident)
        pdf = adr / "spc_orez.pdf" if (adr / "spc_orez.pdf").exists() else adr / "spc.pdf"
        md = (adr / "spc.md").read_text(encoding="utf-8")
        with pymupdf.open(str(pdf)) as d:
            st = [p.get_text("text") for p in d]
        k = zkontroluj(md, pdf, "\n".join(st), strana_sekce(st, "4.8"),
                       pdf_original=adr / "spc.pdf")
        _atomicky(adr / "kontrola.json", json.dumps(k, ensure_ascii=False, indent=1))
        c.execute("UPDATE spc SET verdikt=?, duvody=? WHERE identita=?",
                  (k["verdikt"], "; ".join(k["duvody"]) or None, ident))
        if i % 100 == 0:
            c.commit()
            log.info("  překontrola %d/%d", i, len(rady))
    c.commit()
    po = dict(c.execute("SELECT verdikt, count(*) FROM spc WHERE stav='ok' GROUP BY verdikt"))
    log.info("PŘEKONTROLA HOTOVA: před %s, po %s", pred, po)


def report_na_konci() -> None:
    """Report podezřelých na konci KAŽDÉHO běhu – po měsíčním jobu musí být
    vidět, co prověřit (data/spc/_report/podezrele.html)."""
    from common.report_konverze import vytvor_report
    pocty = vytvor_report()
    log.info("REPORT: data/spc/_report/podezrele.html  %s", pocty)


def vypis_stav(c: sqlite3.Connection) -> None:
    kody = dict(c.execute("SELECT stav, count(*) FROM kody GROUP BY stav").fetchall())
    spc = dict(c.execute("SELECT stav, count(*) FROM spc GROUP BY stav").fetchall())
    ver = dict(c.execute("SELECT verdikt, count(*) FROM spc WHERE stav='ok' GROUP BY verdikt").fetchall())
    print(f"kódy SÚKL:   {kody}")
    print(f"unikátní SPC: {sum(spc.values())}  {spc}")
    print(f"kontrola:    {ver}")
    cas = c.execute("SELECT sum(cas_s), count(*) FROM spc WHERE stav='ok'").fetchone()
    if cas[1]:
        print(f"čas:         {cas[0] / 60:.0f} min celkem, {cas[0] / cas[1]:.1f} s/SPC")
    print("\nPODEZŘELÉ (k ruční kontrole, data/spc/<identita>/kontrola.json):")
    for r in c.execute("SELECT identita, nazev, duvody FROM spc WHERE verdikt='podezreni' "
                       "ORDER BY identita LIMIT 60"):
        print(f"  {r[0]:28} {(r[1] or '')[:30]:30} {r[2]}")
    soubor, nedok = nedokoncene_v_logu()
    if soubor:
        print(f"\nPOSLEDNÍ LOG {soubor}: začaté a NEDOKONČENÉ (zde to stálo/spadlo):")
        for r in nedok:
            print(f"  {r}")
        if not nedok:
            print("  žádné – poslední běh doběhl nebo stojí mimo konverzi")
        else:
            davky = sorted({int(m.group(1)) for r in nedok
                            if (m := re.search(r"\[dávka (\d+)\]", r))})
            print(f"  -> pokračovat: stejný příkaz (nebo --od-davky {davky[0]})")
    print("\nCHYBY:")
    for r in c.execute("SELECT identita, nazev, stav, chyba FROM spc WHERE stav IN "
                       "('chyba','timeout') ORDER BY identita LIMIT 60"):
        print(f"  {r[0]:28} {(r[1] or '')[:30]:30} {r[2]}: {(r[3] or '')[:90]}")


def nastav_log() -> Path:
    Path("logs").mkdir(exist_ok=True)
    soubor = Path("logs") / f"konverze_serve_{datetime.now():%Y%m%d_%H%M%S}.log"
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%H:%M:%S")
    for h in (logging.FileHandler(soubor, encoding="utf-8"),
              logging.StreamHandler(io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                                     line_buffering=True))):
        h.setFormatter(fmt)
        log.addHandler(h)
    log.setLevel(logging.INFO)
    return soubor


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--obchodovana", action="store_true")
    g.add_argument("--vse", action="store_true")
    g.add_argument("--kod")
    g.add_argument("--stav", action="store_true")
    g.add_argument("--prekontroluj", action="store_true",
                   help="přepočítat kontroly nad hotovými Markdowny, bez konverze")
    ap.add_argument("--paralelne", type=int, default=4)
    ap.add_argument("--velikost-davky", type=int, default=100)
    ap.add_argument("--davka", type=int)
    ap.add_argument("--od-davky", type=int, default=1)
    ap.add_argument("--znovu-chyby", action="store_true")
    ap.add_argument("--jen-inventar", action="store_true")
    ap.add_argument("--bez-obnovy", action="store_true",
                    help="neobnovovat seznam léčiv z API (použít uložený)")
    ap.add_argument("--ema-rozestup", type=float, default=10.0,
                    help="s mezi stahováními z EMA (při 429 zvýšit)")
    a = ap.parse_args()

    _ema_rozestup[0] = a.ema_rozestup
    c = db()
    if a.stav:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
        vypis_stav(c)
        return 0
    if a.prekontroluj:
        nastav_log()
        prekontroluj(c)
        report_na_konci()
        return 0
    if not (a.obchodovana or a.vse or a.kod):
        ap.error("vyber rozsah: --obchodovana, --vse, --kod KOD, nebo --stav")

    soubor = nastav_log()
    log.info("=" * 70)
    log.info("START %s  log: %s", " ".join(sys.argv[1:]), soubor)

    kody, nove_vydani = rozsah_kodu(a)
    if not a.kod:
        vycisti(c, kody)
    inventar(c, kody, vynutit=bool(a.kod), obnovit=nove_vydani)   # server nepotřebuje
    if a.jen_inventar:
        return 0

    try:
        v = requests.get(f"{DOCLING_SERVE_URL}/version", timeout=10).json()
        log.info("Docling Serve %s: docling %s", DOCLING_SERVE_URL, v.get("docling"))
    except Exception as e:
        log.error("Docling Serve %s NEODPOVÍDÁ (%s) – běží SSH tunel / server?",
                  DOCLING_SERVE_URL, type(e).__name__)
        return 2

    jen = None
    if a.kod:
        jen = {i for (i,) in c.execute("SELECT identita FROM kody WHERE kod=? AND identita "
                                       "IS NOT NULL", (a.kod,))}
        if not jen:
            log.error("kód %s nemá SPC (viz inventář)", a.kod)
            return 1

    try:
        chyb = konvertuj(c, a, jen)
        konvertuj_word(c, jen)          # Word až po PDF – jeden po druhém
    except KeyboardInterrupt:
        log.warning("PŘERUŠENO uživatelem – pokračovat stejným příkazem, rozpracované "
                    "se vrátí do fronty")
        return 130
    report_na_konci()
    log.info("KONEC. Souhrn: uv run python extrakce_1_konverze.py --stav")
    if chyb:
        log.info("Chyby zkusit znovu: uv run python extrakce_1_konverze.py %s --znovu-chyby",
                 " ".join(x for x in sys.argv[1:] if x != "--znovu-chyby"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
