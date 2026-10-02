#!/usr/bin/env python3
"""Tabulky NÚ ze STRUKTURNÍHO STROMU PDF (tagged PDF) jako reference.

94 ze 100 SPC ve vzorku jsou tagovaná PDF (exporty z Wordu). Značky
Table/TR/TH/TD nesou tabulku tak, jak ji autor postavil – bez odhadu
z vzhledu stránky. Tady se z nich vytáhnou tabulky sekce 4.8 a změří se
proti nim Docling a pymupdf4llm.

Čte PyMuPDF: get_text("xml", flags=TEXT_COLLECT_STRUCTURE) vrací prvky
<struct raw="TD"> s textem uvnitř.

POZOR: značky přesně kopírují to, jak autor dokument POSTAVIL. Nadpisy
jsou nespolehlivé (PARALEN má jako H1 větu „Jedna tableta obsahuje…",
skutečný nadpis „4.2 Dávkování" je P) – proto se tu berou jen TABULKY.

Výstup: vystupy/<lek>/struktura.md (4.8 z tabulek značek, k prohlédnutí)
        struktura_pdf.json

  uv run python benchmarky/pdfextrakce/struktura_pdf.py
"""

import io
import re
import sys
import json
import importlib.util
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

ADR = Path(__file__).resolve().parent
_sp = importlib.util.spec_from_file_location("bench", ADR / "bench_pdfextrakce.py")
b = importlib.util.module_from_spec(_sp)
_sp.loader.exec_module(b)
_sp = importlib.util.spec_from_file_location("arbitr", ADR / "arbitr_pdf.py")
arb = importlib.util.module_from_spec(_sp)
_sp.loader.exec_module(arb)

BUNKA = {"TD", "TH"}


def _text(e) -> str:
    return re.sub(r"\s+", " ", "".join(c.get("c", "") for c in e.iter("char"))).strip()


def _prvky(pdf: Path):
    """Strukturní prvky nejvyšší úrovně pod Document, v pořadí napříč
    stránkami. Tabulka rozdělená zlomem stránky přijde jako dva kusy."""
    import pymupdf
    with pymupdf.open(str(pdf)) as d:
        for p in d:
            x = p.get_text("xml", flags=pymupdf.TEXT_COLLECT_STRUCTURE)
            try:
                koren = ET.fromstring(x)
            except ET.ParseError:
                continue
            for s in koren.iter("struct"):
                if s.get("raw") == "Document":
                    yield from (c for c in s if c.tag == "struct")
                    break
            else:
                yield from (c for c in koren if c.tag == "struct")


def _bbox(e):
    try:
        return [float(x) for x in e.get("bbox", "").split()]
    except ValueError:
        return None


def _tabulka(e) -> list[list[str]]:
    """Řádky tabulky se SPRÁVNÝM číslem sloupce.

    Word do značek NEZAPÍŠE buňku sloučenou přes víc řádků (RowSpan).
    ANAGRELIDE: levá buňka „Třídy orgánových systémů / MedDRA" přes dva
    řádky -> záhlaví má ve značkách 5 buněk místo 6 a „Velmi časté" se
    posune do 1. sloupce. Pořadí buňky v řádku proto NEURČUJE sloupec.
    Sloupec se bere z polohy: MuPDF dává každému prvku bbox; hranice
    sloupců = buňky nejplnějšího řádku.
    """
    radky = []
    for tr in e.iter("struct"):
        if tr.get("raw") != "TR":
            continue
        bunky = [(_text(td), _bbox(td)) for td in tr
                 if td.tag == "struct" and td.get("raw") in BUNKA]
        if any(t for t, _ in bunky):
            radky.append(bunky)
    if not radky:
        return []
    vzor = max(radky, key=len)
    sloupce = [bb for _, bb in vzor]
    if not all(bb and len(bb) == 4 for bb in sloupce):
        return [[t for t, _ in r] for r in radky]        # bez polohy: pořadí
    ven = []
    for r in radky:
        rad = [""] * len(sloupce)
        for t, bb in r:
            if not bb or len(bb) != 4:
                continue
            stred = (bb[0] + bb[2]) / 2
            i = min(range(len(sloupce)),
                    key=lambda k: 0 if sloupce[k][0] <= stred <= sloupce[k][2]
                    else min(abs(stred - sloupce[k][0]), abs(stred - sloupce[k][2])))
            rad[i] = (rad[i] + " " + t).strip()
        ven.append(rad)
    return ven


def tabulky_48(pdf: Path) -> dict:
    """Tabulky sekce 4.8 ze značek + diagnostika."""
    tagovane = b"/StructTreeRoot" in pdf.read_bytes()
    ven = {"tagovane": tagovane, "sekce_nalezena": False, "tabulky": [], "tabulek_celkem": 0}
    if not tagovane:
        return ven
    v48 = False
    for e in _prvky(pdf):
        raw = e.get("raw")
        if raw == "Table":
            ven["tabulek_celkem"] += 1
            if v48:
                t = _tabulka(e)
                if t:
                    ven["tabulky"].append(t)
            continue
        t = _text(e)
        if re.match(r"^4\.8\.?(\s|$)", t):
            v48 = True
            ven["sekce_nalezena"] = True
        elif v48 and re.match(r"^(4\.9|5\.)\.?(\s|$)", t):
            break
    return ven


def jako_md(tabulky: list[list[list[str]]]) -> str:
    """Tabulky jako Markdown, ať jdou změřit TÝMIŽ funkcemi jako varianty."""
    ven = ["4.8 Nežádoucí účinky (tabulky ze strukturního stromu PDF)", ""]
    for t in tabulky:
        n = max(len(r) for r in t)
        for i, r in enumerate(t):
            r = r + [""] * (n - len(r))
            ven.append("| " + " | ".join(x.replace("|", "/") for x in r) + " |")
            if i == 0:
                ven.append("|" + "---|" * n)
        ven.append("")
    ven.append("4.9 Předávkování")
    return "\n".join(ven)


def slova_po_frekvencich(md: str) -> dict[str, Counter]:
    """Frekvence -> slova ve sloupci té frekvence (tabulky formátu 2 v 4.8).

    Měří se po SLOVECH, ne po buňkách: nástroje dělí buňky a řádky různě
    (úlomek „enie" z „trombocytop-enie" je samostatná buňka) a párování
    podle textu buňky pak spáruje nesouvisející buňky. První verze tak
    hlásila u Doclingu i pymupdf4llm TYTÉŽ „chyby" – artefakt metriky.
    """
    ven: dict[str, Counter] = {}
    hlav = None
    for radek in b.sekce(md, "4.8", "4.9").splitlines():
        r = radek.strip()
        if not (r.startswith("|") and r.endswith("|")):
            hlav = None
            continue
        bunky = r[1:-1].split("|")
        if all(re.fullmatch(r"\s*:?-{2,}:?\s*", x) or not x.strip() for x in bunky):
            continue
        f = [arb._frek(b._bunka(x)) for x in bunky]
        if sum(bool(x) for x in f) >= 2:
            hlav = f
            continue
        if not hlav or len({b._bunka(x) for x in bunky if b._bunka(x)}) <= 1:
            continue                         # bez záhlaví / řádek přes celou šířku
        for i, x in enumerate(bunky):
            if i < len(hlav) and hlav[i]:
                ven.setdefault(hlav[i], Counter()).update(
                    w for w in b._bunka(x).split() if len(w) >= 3)
    return ven


def shoda_frekvenci(ref: dict[str, Counter], var: dict[str, Counter]) -> dict:
    """Slova ze značek: správná frekvence / jiná frekvence / chybí."""
    celkem = spravne = jinde = 0
    vse_ref, vse_var = Counter(), Counter()
    for c in ref.values():
        vse_ref.update(c)
    for c in var.values():
        vse_var.update(c)
    for w, n in vse_ref.items():
        ok = sum(min(ref[f][w], var.get(f, Counter())[w]) for f in ref)
        pritomno = min(n, vse_var[w])
        celkem += n
        spravne += ok
        jinde += pritomno - ok
    return {"slov": celkem, "spravne": spravne, "jina_frekvence": jinde,
            "chybi": celkem - spravne - jinde}


def main() -> int:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    polozky = json.loads(b.VZOREK.read_text(encoding="utf-8"))["polozky"]
    souhrn = Counter()
    leky = {}
    for p in polozky:
        lek = p["lek"]
        # Značky z ORIGINÁLU: ořez před Přílohou II (insert_pdf do nového
        # souboru) strukturní strom zahodí – tagovaných pak vyšlo 83 místo 94.
        s = tabulky_48(b.PDF / f"{lek}.pdf")
        souhrn["leku"] += 1
        souhrn["tagovanych"] += s["tagovane"]
        souhrn["s_tabulkou_ve_znackach"] += s["tabulek_celkem"] > 0
        if not s["tabulky"]:
            leky[lek] = {k: v for k, v in s.items() if k != "tabulky"}
            continue
        souhrn["s_tabulkou_48"] += 1
        ref = jako_md(s["tabulky"])
        (b.VYST / lek / "struktura.md").write_text(ref, encoding="utf-8")
        z = {"tabulek_48": len(s["tabulky"])}
        f_ref = slova_po_frekvencich(ref)
        for var in ("docling", "p4l", "p4l_layout"):
            f = b.VYST / lek / f"{var}.md"
            if not f.exists():
                continue
            md = f.read_text(encoding="utf-8")
            zz = b._trojice(b.tabulky(ref))
            vv = b._trojice(b.tabulky(b.sekce(md, "4.8", "4.9")))
            ok = sum(min(n, vv[k]) for k, n in zz.items())
            celk = sum(zz.values())
            fr = shoda_frekvenci(f_ref, slova_po_frekvencich(md)) if f_ref else None
            z[var] = {"vazeb": celk, "vazeb_ok": ok, "frekvence": fr}
            souhrn[f"{var}_vazeb"] += celk
            souhrn[f"{var}_ok"] += ok
            if fr:
                for k in ("slov", "spravne", "jina_frekvence", "chybi"):
                    souhrn[f"{var}_f_{k}"] += fr[k]
                souhrn[f"{var}_f_leku_jinde"] += fr["jina_frekvence"] > 0.05 * fr["slov"]
        leky[lek] = {**{k: v for k, v in s.items() if k != "tabulky"}, **z}

    (ADR / "struktura_pdf.json").write_text(
        json.dumps({"souhrn": dict(souhrn), "leky": leky}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    s = souhrn
    print(f"léků {s['leku']}, tagovaných {s['tagovanych']}, s tabulkou ve značkách "
          f"{s['s_tabulkou_ve_znackach']}, s tabulkou v 4.8 {s['s_tabulkou_48']}\n")
    print("Formát 2 – slova tabulek pod frekvencí (reference = značky PDF):")
    print(f"{'varianta':11} {'slov':>6} {'správná frekv.':>16} {'JINÁ frekv.':>13} {'chybí':>8} {'léků >5 % jinde':>16}")
    for var in ("docling", "p4l", "p4l_layout"):
        n = s[f"{var}_f_slov"]
        if not n:
            continue
        print(f"{var:11} {n:6} {s[f'{var}_f_spravne']:9} ({s[f'{var}_f_spravne'] / n:.1%})"
              f" {s[f'{var}_f_jina_frekvence']:6} ({s[f'{var}_f_jina_frekvence'] / n:.1%})"
              f" {s[f'{var}_f_chybi']:8} {s[f'{var}_f_leku_jinde']:10}")
    print("\nLéky, kde varianta dává >5 % slov pod JINOU frekvencí než značky:")
    for lek, z in leky.items():
        for var in ("docling", "p4l"):
            fr = (z.get(var) or {}).get("frekvence")
            if fr and fr["jina_frekvence"] > 0.05 * fr["slov"]:
                print(f"  {lek[8:30]:22} {var:8} jinde {fr['jina_frekvence']}/{fr['slov']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
