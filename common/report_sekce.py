"""Přehled rozparsovaných sekcí celého korpusu -> data/spc/_report/sekce.html + sekce.csv.

Proč: korpus má tisíce složek, ručně se nedá ověřit, odkud která sekce
vzala text. Tady je to na jednom místě. Pravidlo výběru zdroje
(common/sekce.py, vytahni_vsechny):
  indikace, kontraindikace           -> vždy Docling (podnadpisy skupin)
  dávkování, NÚ S tabulkou           -> Docling (tabulka po buňkách)
  dávkování, NÚ BEZ tabulky          -> surový text PyMuPDF (zachová řádky)
  sekce nenalezená v Markdownu       -> surový text (záloha)
Vadnou TABULKU Doclingu surový text automaticky nenahrazuje – takové
případy jen označí kontrola konverze (sloupec „kontrola").

Volá extrahuj_sekce.py --korpus na konci běhu.
"""
import csv
import html
import json
import re
import sqlite3
from collections import Counter

from common.config import DATA_DIR

SEKCE = ["indikace", "davkovani", "kontraindikace", "nezadouci_ucinky"]


def vytvor_report_sekci() -> dict:
    spc = DATA_DIR / "spc"
    ven = spc / "_report"
    ven.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(spc / "_stav.sqlite")
    nazvy = dict(c.execute("SELECT identita, nazev FROM spc"))
    kody = {}
    for kod, ident in c.execute("SELECT kod, identita FROM kody WHERE identita IS NOT NULL"):
        kody.setdefault(ident, kod)

    radky, souhrn = [], Counter()
    for ident in sorted(kody):
        adr = spc / re.sub(r"[^\w.-]+", "_", ident)[:80]
        f = adr / "sekce" / "_prehled.json"
        if not f.exists():
            souhrn["bez_prehledu"] += 1
            continue
        p = json.loads(f.read_text(encoding="utf-8"))
        k = p.get("_konverze") or {}
        r = {"identita": ident, "nazev": nazvy.get(ident, ""), "kod": kody[ident],
             "kontrola": k.get("verdikt") or "", "duvody": "; ".join(k.get("duvody") or [])}
        for s in SEKCE:
            x = p.get(s) or {}
            zdroj = x.get("zdroj") if x.get("nalezena") else "NENALEZENA"
            r[s] = zdroj
            r[s + "_znaku"] = x.get("znaku", 0)
            r[s + "_tabulka"] = bool(x.get("ma_tabulku"))
            souhrn[(s, zdroj)] += 1
        radky.append(r)

    with open(ven / "sekce.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(radky[0].keys()) if radky else ["identita"],
                           delimiter=";")
        w.writeheader()
        w.writerows(radky)

    e = html.escape
    zdroje = ["docling_md", "pymupdf_raw", "NENALEZENA"]
    h = ["<!doctype html><meta charset=utf-8><title>Sekce korpusu</title><style>",
         "body{font:14px/1.45 system-ui,sans-serif;margin:1.5rem}table{border-collapse:collapse}",
         "td,th{border:1px solid #d8dde3;padding:.25rem .45rem;text-align:left}th{background:#f4f6f8}",
         ".md{color:#1e4f91}.raw{color:#7a5b00}.no{color:#9b1c1c;font-weight:600}",
         ".t{color:#6b7580;font-size:.85rem}</style>",
         f"<h1>Rozparsované sekce – {len(radky)} SPC</h1>",
         "<p class=t>Zdroj textu podle pravidla v common/sekce.py: indikace a kontraindikace "
         "vždy Docling; dávkování a NÚ s tabulkou Docling, bez tabulky surový text PyMuPDF "
         "(zachovává řádky); nenalezená v Markdownu -> surový text. Celá data: sekce.csv "
         "(filtrovat v Excelu).</p><table><tr><th>sekce"
         + "".join(f"<th>{z}" for z in zdroje) + "</tr>"]
    for s in SEKCE:
        h.append(f"<tr><td>{s}" + "".join(f"<td>{souhrn[(s, z)]}" for z in zdroje) + "</tr>")
    h.append("</table><h2>Nenalezené sekce</h2><table><tr><th>SPC<th>kód<th>chybí<th>odkazy</tr>")
    for r in radky:
        chybi = [s for s in SEKCE if r[s] == "NENALEZENA"]
        if chybi:
            h.append(f"<tr><td>{e(r['nazev'])}<br><span class=t>{e(r['identita'])}</span>"
                     f"<td>{r['kod']}<td class=no>{', '.join(chybi)}"
                     f"<td><a href='../{e(r['identita'])}/spc.pdf'>PDF</a> · "
                     f"<a href='../{e(r['identita'])}/spc.md'>md</a></tr>")
    h.append("</table><h2>Všechna SPC</h2><table><tr><th>SPC<th>kód"
             + "".join(f"<th>{s}" for s in SEKCE) + "<th>kontrola konverze</tr>")
    tr = {"docling_md": "md", "pymupdf_raw": "raw", "NENALEZENA": "no"}
    for r in radky:
        bunky = "".join(
            f"<td class={tr.get(r[s], '')}><a href='../{e(r['identita'])}/sekce/{s}.md'>"
            f"{e(r[s] or '')}</a> <span class=t>{r[s + '_znaku']}"
            f"{' tab' if r[s + '_tabulka'] else ''}</span>" for s in SEKCE)
        h.append(f"<tr><td>{e(r['nazev'])}<br><span class=t>{e(r['identita'])}</span>"
                 f"<td>{r['kod']}{bunky}<td class=t>{e(r['kontrola'])} {e(r['duvody'])}</tr>")
    h.append("</table>")
    (ven / "sekce.html").write_text("\n".join(h), encoding="utf-8")
    return {f"{s}/{z}": souhrn[(s, z)] for s in SEKCE for z in zdroje}
