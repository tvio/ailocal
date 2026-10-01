#!/usr/bin/env python3
"""Benchmark konverze PDF -> Markdown: kde je v Doclingu doopravdy cas.

Otazky:
  1) Bezi OCR zbytecne? SPC ze SUKL jsou digitalni PDF, ne skeny, ale
     DocumentConverter s vychozimi PdfPipelineOptions ma `do_ocr=True`.
  2) Kolik stoji layout model pro tabulky (`do_table_structure`)?
  3) Co zvladne sam PyMuPDF / pymupdf4llm a kde presne selze?

Merit se musi VZDY cas I VERNOST. Zrychleni, ktere rozbije tabulky
nezadoucich ucinku, je k nicemu - tam je 23 z 32 tabulek korpusu.

VERNOST TABULEK NU (sekce 4.8) se meri PO BUNKACH proti Doclingu:
kazda neprazdna bunka Doclingu se hleda ve variante (a) kdekoli
v tabulce, (b) VE STEJNEM SLOUPCI. U formatu 2 (sloupce = frekvence,
viz extrakce.POPIS_FORMATU) je sloupec to, co urcuje frekvenci, takze
(b) meri primo vazbu frekvence -> ucinek. Format 2 se pozna podle
hlavicky se dvema a vice frekvencemi.

POZOR (24.9.2026): Docling se tu musi importovat PRES common.konverze,
ktery nastavi TORCHDYNAMO_DISABLE. Driv to tu chybelo a benchmark padal
na InvalidCxxCompiler - coz se mylne zapsalo jako vada produkce.

Pouziti:
  uv run python bench_konverze.py                 # 3 leciva, vsechny varianty
  uv run python bench_konverze.py --leciv 0 --varianty plny,bez_ocr,pymupdf4llm
  uv run python bench_konverze.py --md-dir tmp_md # ulozit markdowny k prohlidce
"""

import io
import re
import sys
import time
import json
import argparse
import tempfile
import functools
from pathlib import Path

# Nastavi TORCHDYNAMO_DISABLE drive, nez Docling natahne torch.
import common.konverze as konverze
from common.config import LECIVA_DIR

VARIANTY = ("plny", "bez_ocr", "bez_ocr_bez_tabulek", "pymupdf", "pymupdf4llm")
DOCLING = {"plny": (True, True), "bez_ocr": (False, True),
           "bez_ocr_bez_tabulek": (False, False)}

FREKVENCE = re.compile(r"velmi\s+čast|čast[éá]|méně\s+čast|vzácn|není\s+známo",
                       re.IGNORECASE)


@functools.lru_cache(maxsize=None)
def _prevodnik(ocr: bool, tabulky: bool):
    """Jeden prevodnik na variantu. Vytvorit ho znamena nacist modely -
    kdyby se to delalo u kazdeho PDF, meril by se load, ne konverze."""
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend

    opts = PdfPipelineOptions()
    opts.do_ocr = ocr
    opts.do_table_structure = tabulky
    return DocumentConverter(format_options={
        InputFormat.PDF: PdfFormatOption(
            pipeline_options=opts, backend=PyPdfiumDocumentBackend)})


def _tabulek_v_md(md: str) -> int:
    return len(re.findall(r"^\|.+\|\s*$\n^\|[\s:|-]+\|\s*$", md, re.MULTILINE))


def konvertuj(varianta: str, pdf: Path) -> tuple[str, int]:
    if varianta == "pymupdf":
        import pymupdf
        with pymupdf.open(str(pdf)) as d:
            return "\n".join(p.get_text() for p in d), 0
    if varianta == "pymupdf4llm":
        import pymupdf4llm
        md = pymupdf4llm.to_markdown(str(pdf), show_progress=False)
        return md, _tabulek_v_md(md)
    d = _prevodnik(*DOCLING[varianta]).convert(str(pdf)).document
    return d.export_to_markdown(), len(getattr(d, "tables", []) or [])


# --- vernost tabulek NU -------------------------------------------------------
def sekce_48(md: str) -> str:
    """Text sekce 4.8 (od nadpisu 4.8 po 4.9). Kdyz se nenajde, cely text."""
    z = re.search(r"(?mi)^[#*\s]*4\.8\.?\s*\**\s*Ne", md)
    if not z:
        return md
    k = re.search(r"(?mi)^[#*\s]*4\.9\.?\s*\**\s*P", md[z.end():])
    return md[z.start(): z.end() + k.start()] if k else md[z.start():]


def _bunka(s: str) -> str:
    """Jen pismena a mezery. Docling pise odkaz na poznamku "reakce 1",
    pymupdf4llm "reakce<sup>1</sup>" - to neni ztrata textu a porovnani
    to nesmi pocitat jako chybejici bunku (prvni verze to delala)."""
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"[^\w\s]|\d|_", " ", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def tabulky(md: str) -> list[list[list[str]]]:
    """Markdown tabulky -> [tabulka][radek][bunka]. Oddelovac |---| vynechan."""
    ven, akt = [], []
    for radek in md.splitlines():
        r = radek.strip()
        if r.startswith("|") and r.endswith("|"):
            bunky = [_bunka(b) for b in r[1:-1].split("|")]
            if all(re.fullmatch(r":?-{2,}:?", b.replace(" ", "")) or not b
                   for b in bunky) and any(bunky):
                continue
            akt.append(bunky)
        elif akt:
            ven.append(akt)
            akt = []
    if akt:
        ven.append(akt)
    return ven


def je_format2(tab: list[list[list[str]]]) -> bool:
    return any(sum(bool(FREKVENCE.search(b)) for b in t[0]) >= 2 for t in tab if t)


def _trojice(tab: list[list[list[str]]]) -> list[tuple[str, int, str]]:
    """Kazda bunka jako (text, sloupec, popisek radku) - PRESNE.

    Popisek radku = prvni neprazdna bunka (organovy system nebo frekvence
    podle formatu). Zamena ucinku mezi radky "caste" a "vzacne" zmeni
    popisek, zkraceni bunky zmeni text - oboji se tu projevi.
    Radek, kde jsou vsechny neprazdne bunky stejne (sloucena bunka pres
    celou sirku, Docling ji kopiruje do vsech sloupcu), se bere jako
    jedna bunka ve sloupci 0.
    """
    ven = []
    for t in tab:
        for r in t:
            nepr = [b for b in r if b]
            if not nepr:
                continue
            if len(set(nepr)) == 1:
                ven.append((nepr[0], 0, nepr[0]))
                continue
            popisek = nepr[0]
            ven += [(b, i, popisek) for i, b in enumerate(r) if b and len(b) >= 3]
    return ven


def shoda_vazeb(zaklad: str, varianta: str) -> dict:
    """Prisna vernost tabulek NU: kolik trojic (text, sloupec, radek)
    z Doclingu je ve variante PRESNE. Nahradila shoda_bunek(), ktera
    hledala "stejny sloupec, kterykoli radek" a tolerovala obsazeni -
    a proto neodhalila zamenu radku ani zkracenou bunku (pripominka
    Codexu, overeno testem v overit_metriku())."""
    from collections import Counter
    z = Counter(_trojice(tabulky(sekce_48(zaklad))))
    v = Counter(_trojice(tabulky(sekce_48(varianta))))
    celkem = sum(z.values())
    ok = sum(min(n, v[k]) for k, n in z.items())
    chybi = [f"{k[2][:25]} | sl.{k[1]} | {k[0][:45]}" for k in z if not v[k]][:4]
    return {"vazeb": celkem, "vazeb_ok": ok, "chybi_vazby": chybi}


def overit_metriku() -> None:
    """Metrika MUSI odhalit zamenu radku a zkraceni bunky."""
    zaklad = ("## 4.8 Nezadouci ucinky\n"
              "| Frekvence | Ucinek |\n|---|---|\n"
              "| Časté | vyrážka, bolest hlavy, nevolnost |\n"
              "| Vzácné | anafylaxe |\n## 4.9 Predavkovani\n")
    zamena = zaklad.replace("vyrážka, bolest hlavy, nevolnost", "XX").replace(
        "anafylaxe", "vyrážka, bolest hlavy, nevolnost").replace("XX", "anafylaxe")
    zkraceni = zaklad.replace("vyrážka, bolest hlavy, nevolnost", "vyrážka")
    for nazev, md in (("shodne", zaklad), ("zamena radku", zamena),
                      ("zkraceni bunky", zkraceni)):
        s = shoda_vazeb(zaklad, md)
        stara = shoda_bunek(zaklad, md)
        print(f"  {nazev:16} nova {s['vazeb_ok']}/{s['vazeb']}   "
              f"stara {stara['sloupec']}/{stara['bunek']}")


def shoda_bunek(zaklad: str, varianta: str) -> dict:
    """Kolik bunek tabulek NU z Doclingu je ve variante kdekoli / ve stejnem sloupci."""
    tz, tv = tabulky(sekce_48(zaklad)), tabulky(sekce_48(varianta))
    vsude = {b for t in tv for r in t for b in r if b}
    po_sloupcich: dict[int, set] = {}
    for t in tv:
        for r in t:
            for i, b in enumerate(r):
                if b:
                    po_sloupcich.setdefault(i, set()).add(b)
    celkem = kdekoli = sloupec = 0
    chybi = []
    for t in tz:
        for r in t:
            for i, b in enumerate(r):
                if len(b) < 3:
                    continue
                celkem += 1
                # Bunka se muze ve variante rozdelit nebo slit s vedlejsi -
                # proto i obsazeni, ne jen presna shoda.
                if b in vsude or any(b in x or x in b for x in vsude if len(x) >= 3):
                    kdekoli += 1
                v_sl = po_sloupcich.get(i, set())
                if b in v_sl or any(b in x or (x in b and len(x) >= 3) for x in v_sl):
                    sloupec += 1
                elif len(chybi) < 3:
                    chybi.append(f"sl.{i}: {b[:50]}")
    return {"bunek": celkem, "kdekoli": kdekoli, "sloupec": sloupec,
            "radku_z": sum(len(t) for t in tz), "radku_v": sum(len(t) for t in tv),
            "format2": je_format2(tz), "chybi": chybi}


def main() -> int:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--leciv", type=int, default=3, help="0 = vsechna")
    ap.add_argument("--varianty", default=",".join(VARIANTY))
    ap.add_argument("--json", type=Path, default=Path("bench_konverze.json"))
    ap.add_argument("--md-dir", type=Path, help="kam ulozit markdowny variant")
    a = ap.parse_args()

    pdfy = sorted(Path(LECIVA_DIR).glob("*/spc.pdf"))
    if a.leciv:
        pdfy = pdfy[:a.leciv]
    varianty = [v.strip() for v in a.varianty.split(",") if v.strip()]
    print(f"{len(pdfy)} PDF, varianty: {', '.join(varianty)}\n", flush=True)

    tmp = Path(tempfile.mkdtemp(prefix="bench_konverze_"))
    # Zahrati: nacteni modelu Doclingu stoji desitky sekund a do casu
    # konverze nepatri - v produkci se deje jednou na cely beh.
    for v in varianty:
        if v in DOCLING and pdfy:
            t0 = time.perf_counter()
            konvertuj(v, pdfy[0])
            print(f"zahrati {v}: {time.perf_counter() - t0:.1f} s (nepocita se)", flush=True)
    print()

    vse = []
    for pdf in pdfy:
        lek = pdf.parent.name
        # Orez EU dokumentu jako v produkci - jinak by se merily prilohy,
        # ktere se nikdy nekonvertuji.
        vstup, _, stran = konverze.orizni_pdf_pred_konverzi(
            pdf, cil=tmp / f"{lek}.pdf")
        print(f"--- {lek}  ({stran} stran)", flush=True)
        md_zaklad = None
        for v in varianty:
            t0 = time.perf_counter()
            try:
                md, tab = konvertuj(v, vstup)
            except Exception as e:
                print(f"    {v:20} CHYBA: {type(e).__name__}: {e}"[:130], flush=True)
                vse.append({"lek": lek, "varianta": v, "ok": False})
                continue
            r = {"lek": lek, "varianta": v, "ok": True, "stran": stran,
                 "cas_s": round(time.perf_counter() - t0, 1),
                 "znaku": len(md), "tabulek": tab}
            if a.md_dir:
                (a.md_dir / v).mkdir(parents=True, exist_ok=True)
                (a.md_dir / v / f"{lek}.md").write_text(md, encoding="utf-8")
            if v == "plny":
                md_zaklad = md
            elif md_zaklad is not None:
                r["shodne_s_plnym"] = md == md_zaklad
                if v != "pymupdf":
                    r.update(shoda_bunek(md_zaklad, md))
            vse.append(r)
            info = ""
            if "shodne_s_plnym" in r:
                info = "  shodne s plnym" if r["shodne_s_plnym"] else "  LISI SE"
            if r.get("bunek"):
                info += (f"  bunky NU {r['sloupec']}/{r['bunek']} ve sloupci, "
                         f"{r['kdekoli']}/{r['bunek']} kdekoli"
                         f"{'  [format 2]' if r['format2'] else ''}")
            print(f"    {v:20} {r['cas_s']:6.1f}s {r['znaku']:7} znaku "
                  f"{tab:3} tabulek{info}", flush=True)
        a.json.write_text(json.dumps(vse, ensure_ascii=False, indent=1), encoding="utf-8")

    print("\n" + "=" * 78)
    print(f"{'varianta':20} {'cas':>8} {'zrychl':>7} {'tabulek':>8} "
          f"{'shodne':>7} {'bunky ve sloupci':>17}")
    print("-" * 78)
    zaklad = sum(r["cas_s"] for r in vse if r.get("ok") and r["varianta"] == "plny")
    for v in varianty:
        rr = [r for r in vse if r.get("ok") and r["varianta"] == v]
        if not rr:
            continue
        c = sum(r["cas_s"] for r in rr)
        sh = [r["shodne_s_plnym"] for r in rr if "shodne_s_plnym" in r]
        b = sum(r.get("bunek", 0) for r in rr)
        s = sum(r.get("sloupec", 0) for r in rr)
        print(f"{v:20} {c:7.1f}s {zaklad / c if c else 0:6.1f}x "
              f"{sum(r['tabulek'] for r in rr):8} "
              f"{(f'{sum(sh)}/{len(sh)}' if sh else '-'):>7} "
              f"{(f'{s}/{b} ({s / b:.0%})' if b else '-'):>17}")
    f2 = [r for r in vse if r.get("format2") and r["varianta"] == "pymupdf4llm"]
    if f2:
        b = sum(r["bunek"] for r in f2)
        s = sum(r["sloupec"] for r in f2)
        print(f"\nformat 2 (sloupce = frekvence), pymupdf4llm: {len(f2)} leciv, "
              f"bunky ve sloupci {s}/{b} ({s / b:.0%})")
    print(f"\nulozeno do {a.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
