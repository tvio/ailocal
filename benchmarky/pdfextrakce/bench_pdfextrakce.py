#!/usr/bin/env python3
"""Benchmark PDF -> Markdown na 100 SPC: Docling vs pymupdf4llm (vs Marker).

Prevadi se CELY dokument kazdym nastrojem - meri se cista kvalita
prevodniku, ne to, jak dobre se najdou hranice sekci.

Tri kroky, kazdy samostatne spustitelny, konverze navazuje na hotove:

  uv run python benchmarky/pdfextrakce/bench_pdfextrakce.py vzorek
  uv run python benchmarky/pdfextrakce/bench_pdfextrakce.py konverze
  uv run python benchmarky/pdfextrakce/bench_pdfextrakce.py konverze --varianty marker --jen 5
  uv run python benchmarky/pdfextrakce/bench_pdfextrakce.py report

Varianty:
  docling      referencni, jako produkce (pypdfium2, bez OCR, 1 prevodnik)
  p4l          pymupdf4llm, STARY rezim  (use_layout(False))
  p4l_layout   pymupdf4llm, VYCHOZI layout rezim (to, o cem se pise)
  marker       Marker, v oddelenem prostredi (uv run --with marker-pdf)

POZOR: reference je Docling, ne pravda. Kde se varianty lisi, rozhoduje
PDF - report proto u kazdeho leku odkazuje na stranu sekce v PDF.

Vystupy (pdf/, vystupy/, report/ jsou v .gitignore, skript je vyrobi):
  vzorek.json                 co se meri
  pdf/<lek>.pdf               stazena SPC
  vystupy/<lek>/<var>.md      markdown kazde varianty
  vystupy/casy.json           doba konverze
  report/index.html           prehled + odkazy na detail kazdeho leku
  vysledky.json               metriky (vstup pro poznatky.md)
"""

import io
import os
import re
import sys
import json
import time
import random
import argparse
import subprocess
from pathlib import Path
from collections import Counter

KOREN = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(KOREN))
os.chdir(KOREN)

import common.konverze as konverze          # nastavi TORCHDYNAMO_DISABLE

ADR = Path(__file__).resolve().parent
PDF = ADR / "pdf"
VYST = ADR / "vystupy"
REPORT = ADR / "report"
VZOREK = ADR / "vzorek.json"
CASY = VYST / "casy.json"
VARIANTY = ("docling", "p4l", "p4l_layout", "marker")

# Jen SKUTECNE HTML znacky (<u>, <br>, <sup>, </mark>...). Obecne <[^>]+>
# bralo jako znacku i "<" ve frekvencich ("az < 1/10") a mazalo text az
# k dalsimu ">". Docling pise "&lt;", pymupdf4llm doslova "<" - metrika
# tak pymupdf4llm falesne ubirala text (MAALOX 73 slov misto 167).
_ZNACKA = re.compile(r"</?[a-zA-Z][a-zA-Z0-9]{0,9}(\s[^<>]{0,80})?/?>")

FREKVENCE = re.compile(r"velmi\s+čast|čast[éá]|méně\s+čast|vzácn|není\s+známo",
                       re.IGNORECASE)


# =============================================================================
# 1) VZOREK
# =============================================================================
def _stahni(url: str, s) -> bytes:
    """Stahne PDF. Opakuje se JEN pri 429 a vypadku site - chyba 4xx se
    opakovanim nezmeni. Prvni verze opakovala 3x s pauzou 2 s i u 400
    a na kazdem neuspesnem kandidatovi tak ztratila ~6 s."""
    import requests
    for pokus in range(3):
        try:
            r = s.get(url, timeout=120)
        except requests.RequestException:
            time.sleep(2)
            continue
        if r.status_code == 429:
            time.sleep(5 * 2 ** pokus)
            continue
        if not r.ok:
            return b""
        return r.content if r.content[:5].startswith(b"%PDF") else b""
    return b""


def vzorek(pocet: int, seed: int) -> None:
    """Nasich 32 leciv + nahodne dalsi az do `pocet`, jedno SPC na pripravek.

    Deduplikace podle ID dokumentu z /dokumenty-metadata - vice kodu SUKL
    a registracnich cisel muze mit TOTEZ SPC (poznatky.md 24.9.).
    EU pripravky SUKL presmeruje na EMA; bere se odkaz z metadat.
    """
    import requests
    from common.config import SUKL_API, LECIVA_DIR

    PDF.mkdir(parents=True, exist_ok=True)
    s = requests.Session()
    polozky, videne_spc = [], set()

    for d in sorted(Path(LECIVA_DIR).iterdir()):
        if (d / "spc.pdf").exists():
            cil = PDF / f"{d.name}.pdf"
            if not cil.exists():
                cil.write_bytes((d / "spc.pdf").read_bytes())
            polozky.append({"lek": d.name, "kod": d.name.split("_")[0],
                            "zdroj": "korpus", "eu": False})
    nazvy_korpusu = {p["lek"].split("_", 1)[1] for p in polozky}
    print(f"z korpusu: {len(polozky)}", flush=True)

    pool = json.loads((KOREN / "data" / "pool_leciv.json").read_text(encoding="utf-8"))
    podle = {}
    for r in pool:
        if r.get("je_dodavka") and r.get("stav_registrace") == "R" and r.get("kod_sukl"):
            podle.setdefault(r["nazev"], []).append(r)
    kandidati = [n for n in sorted(podle)
                 if konverze_nazev(n) not in nazvy_korpusu]
    random.Random(seed).shuffle(kandidati)

    for n in kandidati:
        if len(polozky) >= pocet:
            break
        r = podle[n][0]
        try:
            meta = s.get(f"{SUKL_API}/dokumenty-metadata/{r['kod_sukl']}", timeout=30).json()
        except Exception:
            continue
        spc = next((x for x in meta if isinstance(x, dict) and x.get("typ") == "SPC"), None)
        if not spc:
            continue
        ident = spc.get("id") or spc.get("link")
        if ident in videne_spc:
            continue
        # /dokumenty/{id} vraci 400 - narodni SPC jen pres kod SUKL.
        # (Prvni beh tu mel id, stahly se jen EU odkazy a vzorek byl 68/68 EU.)
        url = (f"{SUKL_API}/dokumenty/{r['kod_sukl']}/spc" if spc.get("id")
               else spc.get("link"))
        obsah = _stahni(url, s)
        if not obsah:
            continue
        videne_spc.add(ident)
        lek = f"{r['kod_sukl']}_{konverze_nazev(n)}"
        (PDF / f"{lek}.pdf").write_bytes(obsah)
        polozky.append({"lek": lek, "kod": r["kod_sukl"], "zdroj": url,
                        "eu": bool(r.get("eu_registrace"))})
        print(f"  {len(polozky):3} {lek[:40]:40} {'EU' if r.get('eu_registrace') else 'CZ'} "
              f"{len(obsah) // 1024} kB", flush=True)
        if not spc.get("id"):
            time.sleep(0.3)         # ohled jen na EMA; SUKL API pauzu nepotrebuje

    VZOREK.write_text(json.dumps({"seed": seed, "polozky": polozky},
                                 ensure_ascii=False, indent=1), encoding="utf-8")
    eu = sum(p["eu"] for p in polozky)
    print(f"\nvzorek {len(polozky)} SPC (EU {eu}) -> {VZOREK}")


def konverze_nazev(n: str) -> str:
    from common.config import _bezpecny_nazev
    return _bezpecny_nazev(n)


# =============================================================================
# 2) KONVERZE
# =============================================================================
def _orez(lek: str) -> tuple[Path, int]:
    """PDF orizne pred Prilohou II jako produkce (EPAR ma i 100+ stran)."""
    tmp = VYST / "_orez"
    tmp.mkdir(parents=True, exist_ok=True)
    vstup, _, stran = konverze.orizni_pdf_pred_konverzi(PDF / f"{lek}.pdf",
                                                        cil=tmp / f"{lek}.pdf")
    return vstup, stran


def _preved(var: str, pdf: Path) -> str:
    if var == "docling":
        return konverze._prevodnik().convert(str(pdf)).document.export_to_markdown()
    if var in ("p4l", "p4l_layout"):
        import pymupdf4llm
        pymupdf4llm.use_layout(var == "p4l_layout")
        return pymupdf4llm.to_markdown(str(pdf), show_progress=False)
    if var == "marker":
        # Oddelene prostredi - Marker tahne vlastni torch a modely,
        # do zavislosti aplikace nepatri.
        cil = VYST / "_marker" / pdf.stem
        cil.mkdir(parents=True, exist_ok=True)
        subprocess.run(["uv", "run", "--no-project", "--with", "marker-pdf",
                        "marker_single", str(pdf), "--output_dir", str(cil),
                        "--disable_image_extraction"],
                       check=True, capture_output=True, text=True, encoding="utf-8")
        md = next(cil.rglob("*.md"))
        return md.read_text(encoding="utf-8")
    raise ValueError(var)


def konvertuj(varianty: list[str], jen: int) -> None:
    polozky = json.loads(VZOREK.read_text(encoding="utf-8"))["polozky"]
    if jen:
        # Podvzorek = NEJKRATSI dokumenty (Marker na CPU trva minuty na stranu).
        import pymupdf
        def stran(p):
            with pymupdf.open(str(PDF / f"{p['lek']}.pdf")) as d:
                return d.page_count
        polozky = sorted(polozky, key=stran)[:jen]
    casy = json.loads(CASY.read_text(encoding="utf-8")) if CASY.exists() else {}

    # Zahrati Doclingu mimo mereni - v produkci se deje jednou za beh.
    if "docling" in varianty:
        t0 = time.perf_counter()
        konverze._prevodnik().convert(str(_orez(polozky[0]["lek"])[0]))
        print(f"zahrati docling {time.perf_counter() - t0:.0f} s (nepocita se)", flush=True)

    for i, p in enumerate(polozky, 1):
        lek = p["lek"]
        vstup, stran = _orez(lek)
        (VYST / lek).mkdir(parents=True, exist_ok=True)
        radek = []
        for var in varianty:
            cil = VYST / lek / f"{var}.md"
            if cil.exists() and var in casy.get(lek, {}):
                continue
            t0 = time.perf_counter()
            try:
                md = _preved(var, vstup)
            except Exception as e:
                chyba = getattr(e, "stderr", "") or str(e)
                print(f"   {lek[:30]} {var}: CHYBA {type(e).__name__}: {chyba[-200:]}", flush=True)
                continue
            cas = time.perf_counter() - t0
            cil.write_text(md, encoding="utf-8")
            casy.setdefault(lek, {})[var] = round(cas, 2)
            casy[lek]["stran"] = stran
            CASY.write_text(json.dumps(casy, indent=1), encoding="utf-8")
            radek.append(f"{var} {cas:5.1f}s")
        print(f"{i:3}/{len(polozky)} {lek[:34]:34} {stran:3} str.  {'  '.join(radek)}",
              flush=True)


# =============================================================================
# 3) METRIKY
# =============================================================================
def _cisty(radek: str) -> str:
    """Radek bez markdownu/HTML - pro hledani nadpisu v jakemkoli formatu."""
    s = re.sub(r"[#*_|]", " ", _ZNACKA.sub(" ", radek)).replace("&lt;", "<").replace("&gt;", ">")
    return re.sub(r"\s+", " ", s).strip()


def sekce(md: str, od: str, do: str) -> str:
    """Text sekce od nadpisu `od` po `do` (napr. 4.8 -> 4.9).

    Nadpis se hleda az po odstraneni formatovani: Docling pise
    "## 4.8 Nezadouci ucinky", pymupdf4llm "**4.8** **Nezadouci ucinky**".
    Prvni verze benchmarku druhy tvar nepoznala a brala cely dokument.
    """
    radky = md.splitlines()
    # I samotne cislo na radku - v surovem textu PDF byva "4.8" a nazev
    # az na dalsim radku (CHAMPIX). Bez toho se sekce nenasla vubec.
    vzor_od = re.compile(rf"^{re.escape(od)}\.?(\s+[^\d\s]|$)")
    # Konec = JAKYKOLI dalsi cislovany bod ("4.2", "4.4", "5."), ne jen
    # ten ocekavany. DIENILLE nema "4.2" jako nadpis a vyrez 4.1 se tahl
    # pres cely dokument (66 "chybejicich podnadpisu" z 83 v celem vzorku).
    # Jen podbod ("4.2", i samotny na radku - DIENILLE) nebo hlavni bod
    # VELKYMI pismeny ("5. FARMAKOLOGICKE"). Obecne "1. text" by ukoncilo
    # sekci na prvni cislovane odrazce (CASARO spadlo na 4 % pokryti).
    vzor_do = re.compile(r"^(\d\.\d{1,2})\.?(\s+[^\d\s]|$)|^(\d{1,2})\.\s+[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ]{3,}")
    zac = next((i for i, r in enumerate(radky) if vzor_od.match(_cisty(r))), None)
    if zac is None:
        return ""
    kon = next((i for i in range(zac + 1, len(radky))
                if (m := vzor_do.match(_cisty(radky[i]))) and (m.group(1) or "") != od),
               len(radky))
    return "\n".join(radky[zac:kon])


def _bunka(s: str) -> str:
    s = _ZNACKA.sub(" ", s)
    s = re.sub(r"[^\w\s]|\d|_", " ", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def tabulky(md: str) -> list[list[list[str]]]:
    ven, akt = [], []
    for radek in md.splitlines():
        r = radek.strip()
        if r.startswith("|") and r.endswith("|"):
            bunky = [_bunka(b) for b in r[1:-1].split("|")]
            if all(re.fullmatch(r":?-{2,}:?", b.replace(" ", "")) or not b for b in
                   r[1:-1].split("|")):
                continue
            akt.append(bunky)
        elif akt:
            ven.append(akt)
            akt = []
    if akt:
        ven.append(akt)
    return ven


_ZAHLAVI = re.compile(
    r"col\s?\d+|frekvence|četnost|velmi časté|časté|méně časté|vzácné|velmi vzácné"
    r"|není známo|třída orgánových systémů|orgánový systém|meddra.*|"
    r"nežádoucí účin\w*|preferovaný termín|frekvence výskytu")


def _trojice(tab) -> Counter:
    """(text bunky, sloupec, popisek radku) PRESNE - viz poznatky 24.9.
    Odhali zamenu ucinku mezi radky i zkracenou bunku. Radek se stejnou
    hodnotou ve vsech bunkach = sloucena bunka pres celou sirku."""
    c = Counter()
    for t in tab:
        for r in t:
            nepr = [b for b in r if b]
            if not nepr:
                continue
            # Radek zahlavi (jen nazvy frekvenci / popisky sloupcu) se
            # nepocita - nastroje se lisi jen v tom, co napisou do rohu
            # ("Col1", "Frekvence", nic), a to neni vazba ucinek-frekvence.
            if all(_ZAHLAVI.fullmatch(b) for b in nepr):
                continue
            if len(set(nepr)) == 1:
                c[(nepr[0], 0, nepr[0])] += 1
                continue
            # "col1", "col2" doplnuje pymupdf4llm do prazdne hlavicky
            popisek = next((b for b in nepr if not re.fullmatch(r"col\s?\d+", b)), nepr[0])
            for i, b in enumerate(r):
                if b and len(b) >= 3 and not re.fullmatch(r"col\s?\d+", b):
                    c[(b, i, popisek)] += 1
    return c


def _slova(t: str) -> list[str]:
    return re.findall(r"[^\W\d_]{2,}", _ZNACKA.sub(" ", t).lower())


def tucne_radky(lek: str) -> set[str]:
    """Radky, ktere jsou v PDF zvyraznene - TUCNE, KURZIVOU nebo PODTRZENE.

    Proc: Docling oznaci jako "##" i obycejnou vetu. ACECOR "Pripravek je
    indikovan:" je v PDF normalnim rezem bez podtrzeni (overil uzivatel),
    Docling z ni udelal nadpis a metrika pak trestala pymupdf4llm za
    SPRAVNY vystup. Reference pro nadpisy je proto PDF, ne Docling.

    Pozor: podnadpisy skupin v SPC byvaji PODTRZENE ("Dospeli",
    "Pediatricke pouziti" u OMEPRAZOLU) - to neni vlastnost pisma, ale
    cara nakreslena pod textem. Prvni verze brala jen tucne a oznacila
    tyhle skutecne nadpisy za falesne.
    """
    import pymupdf
    ven = set()
    with pymupdf.open(str(PDF / f"{lek}.pdf")) as d:
        for p in d:
            cary = [g["rect"] for g in p.get_drawings()
                    if g["rect"].height < 1.5 and g["rect"].width > 10]
            for b in p.get_text("dict")["blocks"]:
                for l in b.get("lines", []):
                    spany = [s for s in l["spans"] if s["text"].strip()]
                    if not spany:
                        continue
                    styl = all(s["flags"] & (16 | 2) or "Bold" in s["font"]
                               or "Italic" in s["font"] for s in spany)
                    x0, _, x1, y1 = l["bbox"]
                    podtrzeno = any(abs(c.y0 - y1) < 3 and c.x0 < x1 and c.x1 > x0
                                    for c in cary)
                    if styl or podtrzeno:
                        ven.add(_cisty("".join(s["text"] for s in spany)).lower().rstrip(":. "))
    return ven


def slova_pdf_48(lek: str) -> Counter:
    """Slova sekce 4.8 ze SUROVEHO textu PDF - reference NEZAVISLA na Doclingu.

    Proc: CHAMPIX - pymupdf4llm (stary rezim) celou tabulku NU tise
    zahodil (0 z 94 vazeb, "nazofaryngitida" v celem vystupu 0x). Proti
    Doclingu by se to schovalo mezi rozdily formatu; proti textu PDF je
    to jednoznacne.
    """
    raw = konverze.surovy_text(_orez(lek)[0])
    return Counter(w for w in _slova(sekce(raw, "4.8", "4.9")) if len(w) >= 3)


def pokryti(pdf_slova: Counter, var: str) -> float | None:
    """Podil slov sekce 4.8 z PDF, ktera jsou i ve vystupu varianty.
    None = sekce se v PDF nenasla. NESMI se pocitat jako 100 % - prvni
    verze to delala a schovala tak CHAMPIX, kde tabulka zmizela celá."""
    if not pdf_slova:
        return None
    v = Counter(w for w in _slova(sekce(var, "4.8", "4.9")) if len(w) >= 3)
    return sum(min(n, v[w]) for w, n in pdf_slova.items()) / sum(pdf_slova.values())


def metriky(ref: str, var: str, tucne: set[str] | None = None) -> dict:
    ref48, var48 = sekce(ref, "4.8", "4.9"), sekce(var, "4.8", "4.9")
    tz, tv = tabulky(ref48), tabulky(var48)
    z, v = _trojice(tz), _trojice(tv)
    vazeb = sum(z.values())
    vazeb_ok = sum(min(n, v[k]) for k, n in z.items())

    # Podnadpisy v 4.1 a 4.3: Docling je dava jako "## ...". Ve variante
    # musi byt jako SAMOSTATNY radek (formatovani je jedno).
    # Pocita se jen nadpis, ktery je v PDF TUCNY - Docling dela "##"
    # i z obycejnych vet. Ty jdou do `falesne_nadpisy_docling`.
    nad = nad_ok = 0
    chybi_nad, falesne = [], []
    for od, do in (("4.1", "4.2"), ("4.3", "4.4")):
        rs, vs = sekce(ref, od, do), sekce(var, od, do)
        radky_v = {_cisty(r).lower().rstrip(":. ") for r in vs.splitlines()}
        for r in rs.splitlines()[1:]:
            if r.startswith("#"):
                t = _cisty(r).lower().rstrip(":. ")
                if t == "souhrn údajů o přípravku":
                    continue                  # hlavicka stranky, ne podnadpis
                if tucne is not None and t not in tucne:
                    falesne.append(t[:60])
                    continue
                nad += 1
                if t in radky_v:
                    nad_ok += 1
                else:
                    chybi_nad.append(t[:60])

    # Slepena slova v 4.8: slovo, ktere v referenci NENI nikde, ale da se
    # rozdelit na dve slova reference ("srdecniporuchy").
    slovnik = set(_slova(ref))
    slepena = sorted({w for w in set(_slova(var48)) - slovnik
                      if any(w[:i] in slovnik and w[i:] in slovnik
                             for i in range(2, len(w) - 1))})
    return {
        "nalezena_48": bool(var48), "znaku_48": len(var48),
        "tabulek_48": len(tv), "tabulek_48_ref": len(tz),
        "format2": any(sum(bool(FREKVENCE.search(b)) for b in t[0]) >= 2 for t in tz if t),
        "vazeb": vazeb, "vazeb_ok": vazeb_ok,
        "chybi_vazby": [f"{k[2][:30]} | sl.{k[1]} | {k[0][:60]}" for k in z if not v[k]][:12],
        "nadpisu": nad, "nadpisu_ok": nad_ok, "chybi_nadpisy": chybi_nad[:8],
        "falesne_nadpisy_docling": falesne[:8],
        "slepena": slepena[:30], "slepenych": len(slepena),
    }


def _strana_sekce(lek: str, cislo: str) -> int | None:
    """Strana v PDF, kde zacina sekce - pro odkaz z reportu."""
    import pymupdf
    vzor = re.compile(rf"(?m)^\s*{re.escape(cislo)}\.?\s+\S")
    with pymupdf.open(str(PDF / f"{lek}.pdf")) as d:
        for i, p in enumerate(d, 1):
            if vzor.search(p.get_text("text")):
                return i
    return None


# =============================================================================
# 4) REPORT
# =============================================================================
CSS = """body{font:14px/1.45 system-ui,sans-serif;margin:1.5rem;color:#1c2024}
table{border-collapse:collapse}td,th{border:1px solid #d8dde3;padding:.3rem .5rem;
vertical-align:top;text-align:left}th{background:#f4f6f8}.spatne{color:#9b1c1c;
font-weight:600}.ok{color:#197c3a}.tise{color:#6b7580}pre{white-space:pre-wrap;
font:12px/1.35 ui-monospace,Consolas,monospace;margin:0}.sloupce{display:grid;
gap:.6rem;grid-template-columns:repeat(var(--n),minmax(0,1fr))}.sloupce>div{border:1px
solid #d8dde3;border-radius:6px;padding:.5rem;overflow:auto;max-height:80vh}
h3{margin:.2rem 0 .4rem;font-size:.95rem}li{margin:.1rem 0}"""


def _esc(s) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _pct(a, b) -> str:
    return f"{a}/{b} ({a / b:.0%})" if b else "—"


def report() -> None:
    polozky = json.loads(VZOREK.read_text(encoding="utf-8"))["polozky"]
    casy = json.loads(CASY.read_text(encoding="utf-8")) if CASY.exists() else {}
    REPORT.mkdir(parents=True, exist_ok=True)
    vysl, souhrn = {}, {v: Counter() for v in VARIANTY}

    for p in polozky:
        lek = p["lek"]
        refp = VYST / lek / "docling.md"
        if not refp.exists():
            continue
        ref = refp.read_text(encoding="utf-8")
        tucne = tucne_radky(lek)
        pdf48 = slova_pdf_48(lek)
        vysl[lek] = {"eu": p["eu"], "stran": casy.get(lek, {}).get("stran"),
                     "strana_48": _strana_sekce(lek, "4.8"),
                     "strana_41": _strana_sekce(lek, "4.1"), "varianty": {}}
        for var in VARIANTY:
            f = VYST / lek / f"{var}.md"
            if not f.exists():
                continue
            text = f.read_text(encoding="utf-8")
            m = metriky(ref, text, tucne)
            pk = pokryti(pdf48, text)
            m["pokryti_pdf_48"] = round(pk, 3) if pk is not None else None
            m["cas_s"] = casy.get(lek, {}).get(var)
            vysl[lek]["varianty"][var] = m
            s = souhrn[var]
            s["leku"] += 1
            s["cas"] += m["cas_s"] or 0
            s["vazeb"] += m["vazeb"]
            s["vazeb_ok"] += m["vazeb_ok"]
            s["nadpisu"] += m["nadpisu"]
            s["nadpisu_ok"] += m["nadpisu_ok"]
            s["slepenych"] += m["slepenych"]
            s["bez_48"] += not m["nalezena_48"]
            s["falesnych_nadpisu"] += len(m["falesne_nadpisy_docling"])
            if m["pokryti_pdf_48"] is None:
                s["pdf_48_nenalezena"] += 1
            else:
                s["pokryti_soucet"] += m["pokryti_pdf_48"]
                s["pokryti_leku"] += 1
                s["ztrata_textu"] += m["pokryti_pdf_48"] < 0.9
            if m["format2"]:
                s["f2_vazeb"] += m["vazeb"]
                s["f2_ok"] += m["vazeb_ok"]
                s["f2_leku"] += 1
        _report_lek(lek, vysl[lek])

    # Pro ferove srovnani casu jen leky, ktere ma varianta i docling.
    for var in VARIANTY:
        spolecne = [l for l, v in vysl.items() if var in v["varianty"]]
        souhrn[var]["cas_docling_stejne"] = sum(
            vysl[l]["varianty"]["docling"]["cas_s"] or 0 for l in spolecne)

    (ADR / "vysledky.json").write_text(json.dumps(
        {"souhrn": {k: dict(v) for k, v in souhrn.items() if v["leku"]}, "leky": vysl},
        ensure_ascii=False, indent=1), encoding="utf-8")
    _report_index(vysl, souhrn)

    print(f"{'varianta':11} {'leku':>5} {'cas':>8} {'zrychl':>7} {'vazby 4.8':>18} "
          f"{'format 2':>16} {'podnadpisy':>16} {'slepena':>8} {'pokryti PDF':>12} {'ztrata<90%':>10}")
    for var in VARIANTY:
        s = souhrn[var]
        if not s["leku"]:
            continue
        zr = s["cas_docling_stejne"] / s["cas"] if s["cas"] else 0
        print(f"{var:11} {s['leku']:5} {s['cas']:7.0f}s {zr:6.1f}x "
              f"{_pct(s['vazeb_ok'], s['vazeb']):>18} {_pct(s['f2_ok'], s['f2_vazeb']):>16} "
              f"{_pct(s['nadpisu_ok'], s['nadpisu']):>16} {s['slepenych']:8} "
              f"{s['pokryti_soucet'] / max(s['pokryti_leku'], 1):11.1%} {s['ztrata_textu']:10}")
    print(f"\nreport: {REPORT / 'index.html'}")


def _report_index(vysl, souhrn) -> None:
    h = [f"<!doctype html><meta charset=utf-8><title>PDF extrakce</title><style>{CSS}</style>",
         "<h1>Benchmark PDF extrakce</h1>",
         "<p class=tise>Reference = Docling (ne pravda). Kde se varianty liší, rozhoduje PDF "
         "— v detailu léku je odkaz na stranu sekce.</p><h2>Souhrn</h2><table><tr>"
         "<th>varianta<th>léků<th>čas<th>zrychlení<th>vazby 4.8 (text+sloupec+řádek)"
         "<th>formát 2<th>podnadpisy 4.1+4.3<th>slepená slova 4.8<th>pokrytí textu PDF 4.8<th>léků se ztrátou textu (&lt;90 %)</tr>"]
    for var in VARIANTY:
        s = souhrn[var]
        if not s["leku"]:
            continue
        zr = s["cas_docling_stejne"] / s["cas"] if s["cas"] else 0
        h.append(f"<tr><td>{var}<td>{s['leku']}<td>{s['cas']:.0f} s<td>{zr:.1f}×"
                 f"<td>{_pct(s['vazeb_ok'], s['vazeb'])}<td>{_pct(s['f2_ok'], s['f2_vazeb'])}"
                 f"<td>{_pct(s['nadpisu_ok'], s['nadpisu'])}<td>{s['slepenych']}"
                 f"<td>{s['pokryti_soucet'] / max(s['pokryti_leku'], 1):.1%}<td>{s['ztrata_textu']}</tr>")
    h.append("</table><h2>Léky</h2><p class=tise>Seřazeno od nejhorší shody vazeb "
             "u p4l. Červeně pod 90 %.</p><table><tr><th>lék<th>stran<th>EU")
    vars_ = [v for v in VARIANTY if v != "docling" and souhrn[v]["leku"]]
    h += [f"<th>{v} pokrytí PDF<th>{v} vazby<th>{v} podnadpisy<th>{v} slepená" for v in vars_]
    h.append("</tr>")

    def klic(item):
        m = item[1]["varianty"].get("p4l")
        return (m["vazeb_ok"] / m["vazeb"]) if m and m["vazeb"] else 1.0

    for lek, v in sorted(vysl.items(), key=klic):
        h.append(f"<tr><td><a href='{_esc(lek)}.html'>{_esc(lek)}</a>"
                 f"<td>{v['stran']}<td>{'EU' if v['eu'] else ''}")
        for var in vars_:
            m = v["varianty"].get(var)
            if not m:
                h.append("<td>—<td>—<td>—<td>—")
                continue
            tr = "spatne" if m["vazeb"] and m["vazeb_ok"] / m["vazeb"] < 0.9 else ""
            tn = "spatne" if m["nadpisu"] and m["nadpisu_ok"] < m["nadpisu"] else ""
            pk = m["pokryti_pdf_48"]
            tp = "spatne" if pk is None or pk < 0.9 else ""
            h.append(f"<td class='{tp}'>{'4.8 v PDF nenalezena' if pk is None else f'{pk:.0%}'}"
                     f"<td class='{tr}'>{_pct(m['vazeb_ok'], m['vazeb'])}"
                     f"<td class='{tn}'>{m['nadpisu_ok']}/{m['nadpisu']}"
                     f"<td class='{'spatne' if m['slepenych'] else ''}'>{m['slepenych']}")
        h.append("</tr>")
    h.append("</table>")
    (REPORT / "index.html").write_text("\n".join(h), encoding="utf-8")


def _report_lek(lek: str, v: dict) -> None:
    pdf = f"../pdf/{lek}.pdf"
    vars_ = [x for x in VARIANTY if (VYST / lek / f"{x}.md").exists()]
    h = [f"<!doctype html><meta charset=utf-8><title>{_esc(lek)}</title><style>{CSS}</style>",
         f"<p><a href='index.html'>← přehled</a></p><h1>{_esc(lek)}</h1>",
         f"<p>PDF: <a href='{pdf}'>celé</a> · "
         f"<a href='{pdf}#page={v['strana_41'] or 1}'>4.1 (str. {v['strana_41']})</a> · "
         f"<a href='{pdf}#page={v['strana_48'] or 1}'>4.8 (str. {v['strana_48']})</a> · "
         f"markdowny: " + " ".join(f"<a href='../vystupy/{_esc(lek)}/{x}.md'>{x}</a>"
                                   for x in vars_) + "</p>"]
    fal = v["varianty"].get("docling", {}).get("falesne_nadpisy_docling")
    if fal:
        h.append("<p class=tise>Docling označil jako nadpis, ale v PDF to NENÍ tučné "
                 "(nepočítá se): " + _esc(" · ".join(fal)) + "</p>")
    for var, m in v["varianty"].items():
        if var == "docling":
            continue
        h.append(f"<h3>{var} — {m['cas_s']} s · vazby {_pct(m['vazeb_ok'], m['vazeb'])}"
                 f" · podnadpisy {m['nadpisu_ok']}/{m['nadpisu']}"
                 f" · tabulek v 4.8 {m['tabulek_48']} (Docling {m['tabulek_48_ref']})</h3><ul>")
        for x in m["chybi_vazby"]:
            h.append(f"<li class=spatne>vazba chybí: {_esc(x)}</li>")
        for x in m["chybi_nadpisy"]:
            h.append(f"<li class=spatne>podnadpis chybí: {_esc(x)}</li>")
        if m["slepena"]:
            h.append(f"<li class=spatne>slepená slova: {_esc(', '.join(m['slepena']))}</li>")
        h.append("</ul>")
    for od, do in (("4.8", "4.9"), ("4.1", "4.2")):
        h.append(f"<h2>Sekce {od} vedle sebe</h2><div class=sloupce style='--n:{len(vars_)}'>")
        for x in vars_:
            t = sekce((VYST / lek / f"{x}.md").read_text(encoding="utf-8"), od, do)
            h.append(f"<div><h3>{x}</h3><pre>{_esc(t) or '(sekce nenalezena)'}</pre></div>")
        h.append("</div>")
    (REPORT / f"{lek}.html").write_text("\n".join(h), encoding="utf-8")


def main() -> int:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="krok", required=True)
    v = sub.add_parser("vzorek")
    v.add_argument("--pocet", type=int, default=100)
    v.add_argument("--seed", type=int, default=24)
    k = sub.add_parser("konverze")
    k.add_argument("--varianty", default="docling,p4l,p4l_layout")
    k.add_argument("--jen", type=int, default=0, help="jen N nejkratsich dokumentu")
    sub.add_parser("report")
    a = ap.parse_args()

    if a.krok == "vzorek":
        vzorek(a.pocet, a.seed)
    elif a.krok == "konverze":
        konvertuj([x.strip() for x in a.varianty.split(",") if x.strip()], a.jen)
    else:
        report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
