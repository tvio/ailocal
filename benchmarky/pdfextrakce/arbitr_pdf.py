#!/usr/bin/env python3
"""Rozhodci podle PDF: kdo ma pravdu, kdyz Docling a pymupdf4llm dají
ucinek do RUZNE frekvence (tabulky formatu 2, sloupce = frekvence).

Proc: AUBAGIO - Docling posunul ucinky o sloupec doleva ("Chripka"
do Velmi caste), pymupdf4llm je mel spravne v Caste. Overeno polohou
slov v PDF. Reference "Docling" tedy neni pravda; tady rozhoduje PDF.

Postup pro kazdou bunku, kde se frekvence lisi:
  1. v PDF (strany sekce 4.8) najit prvni slovo bunky,
  2. na teze strane najit radek zahlavi (nazvy frekvenci) NAD nim,
  3. sloupec = zahlavi, v jehoz rozsahu lezi levy okraj slova
     (hranice = pulka mezi stredy sousednich zahlavi).

Pouziti:
  uv run python benchmarky/pdfextrakce/arbitr_pdf.py
"""

import io
import re
import sys
import json
import importlib.util
from pathlib import Path

ADR = Path(__file__).resolve().parent
sp = importlib.util.spec_from_file_location("bench", ADR / "bench_pdfextrakce.py")
b = importlib.util.module_from_spec(sp)
sp.loader.exec_module(b)

KANON = ["velmi časté", "časté", "méně časté", "vzácné", "velmi vzácné", "není známo"]


def _frek(s: str) -> str | None:
    s = re.sub(r"\s+", " ", s.lower()).strip(" :")
    for k in sorted(KANON, key=len, reverse=True):
        if s.startswith(k):
            return k
    return None


def bunky_s_frekvenci(md: str) -> dict[str, str]:
    """text bunky -> frekvence podle zahlavi sloupce (jen format 2)."""
    ven = {}
    for t in b.tabulky(b.sekce(md, "4.8", "4.9")):
        hlav = None
        for r in t:
            f = [_frek(x) for x in r]
            if sum(bool(x) for x in f) >= 2:          # radek zahlavi
                hlav = f
                continue
            if not hlav:
                continue
            for i, x in enumerate(r):
                if x and len(x) >= 4 and i < len(hlav) and hlav[i]:
                    ven.setdefault(x, hlav[i])
    return ven


def zahlavi_stranky(p) -> list[tuple[float, float, str]]:
    """[(y, stred_x, frekvence)] pro kazde zahlavi sloupce na strance.
    Viceslovne nazvy ("Velmi", "casté") se skladaji ze slov pod/vedle sebe."""
    slova = p.get_text("words")
    ven = []
    for i, w in enumerate(slova):
        t = w[4].lower().strip(":")
        if t in ("velmi", "méně", "není"):
            dalsi = next((v for v in slova[i + 1:i + 4]
                          if v[4].lower().strip(":") in ("časté", "vzácné", "známo")), None)
            if dalsi is None:
                continue
            f = _frek(f"{t} {dalsi[4].lower()}")
            x0, x1 = min(w[0], dalsi[0]), max(w[2], dalsi[2])
            ven.append((w[1], (x0 + x1) / 2, f))
        elif t in ("časté", "vzácné"):
            predchozi = slova[i - 1][4].lower() if i else ""
            if predchozi in ("velmi", "méně"):
                continue                      # uz slozeno vyse
            ven.append((w[1], (w[0] + w[2]) / 2, t))
    return ven


def sloupec_v_pdf(doc, strany, text: str) -> str | None:
    prvni = text.split()[0]
    for s in strany:
        p = doc[s - 1]
        hl = zahlavi_stranky(p)
        if len(hl) < 2:
            continue
        for w in p.get_text("words"):
            if b._bunka(w[4]).split()[:1] != [prvni]:
                continue
            nad = [h for h in hl if h[0] < w[1]]
            if not nad:
                continue
            y = max(h[0] for h in nad)                 # nejblizsi radek zahlavi nad
            radek = sorted([h for h in nad if abs(h[0] - y) < 25], key=lambda h: h[1])
            if len(radek) < 2:
                continue
            for i, (_, stred, f) in enumerate(radek):
                lev = (radek[i - 1][1] + stred) / 2 if i else -1e9
                prav = (stred + radek[i + 1][1]) / 2 if i + 1 < len(radek) else 1e9
                if lev <= w[0] < prav:
                    return f
    return None


def main() -> int:
    import pymupdf
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    vysl = json.loads((ADR / "vysledky.json").read_text(encoding="utf-8"))["leky"]
    celkem = {"docling": 0, "p4l": 0, "nikdo": 0, "nerozhodnuto": 0}
    detail = []
    for lek, v in vysl.items():
        if not v["varianty"].get("docling", {}).get("format2"):
            continue
        d = bunky_s_frekvenci((b.VYST / lek / "docling.md").read_text(encoding="utf-8"))
        p = bunky_s_frekvenci((b.VYST / lek / "p4l.md").read_text(encoding="utf-8"))
        spory = [(t, fd, p[t]) for t, fd in d.items() if t in p and p[t] != fd]
        if not spory:
            continue
        s48 = v.get("strana_48") or 1
        with pymupdf.open(str(b.PDF / f"{lek}.pdf")) as doc:
            strany = range(s48, min(s48 + 4, doc.page_count + 1))
            for t, fd, fp in spory:
                f = sloupec_v_pdf(doc, strany, t)
                kdo = ("nerozhodnuto" if f is None else "docling" if f == fd
                       else "p4l" if f == fp else "nikdo")
                celkem[kdo] += 1
                detail.append({"lek": lek, "text": t[:70], "docling": fd, "p4l": fp,
                               "pdf": f, "pravdu_ma": kdo})
    print("Spory o frekvenci (format 2), kdo ma pravdu podle PDF:")
    for k, n in celkem.items():
        print(f"  {k:13} {n}")
    for x in detail[:25]:
        print(f"  {x['lek'][8:26]:18} {x['pravdu_ma']:12} docling={x['docling']:12} "
              f"p4l={x['p4l']:12} pdf={x['pdf']}  | {x['text'][:45]}")
    (ADR / "arbitr_pdf.json").write_text(json.dumps({"souhrn": celkem, "spory": detail},
                                                    ensure_ascii=False, indent=1),
                                         encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
