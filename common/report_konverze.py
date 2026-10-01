"""Report podezřelých SPC po konverzi -> data/spc/_report/podezrele.html.

Volá se na KONCI KAŽDÉHO BĚHU konvertuj_serve.py (i po --prekontroluj),
ať je po měsíčním běhu vidět, co prověřit. Skupiny: 4.8 nenalezena,
nízké pokrytí, frekvence proti značkám, frekvence podle geometrie;
v každé seřazeno od nejzávažnějšího. Odkazy na PDF (strana 4.8), md,
kontrola.json a web SÚKL.
"""
import html
import json
import sqlite3
from pathlib import Path

from common.config import DATA_DIR


def vytvor_report() -> dict[str, int]:
    """Zapíše report a vrátí počty podle skupin."""
    ADR = DATA_DIR / "spc" / "_report"
    ADR.mkdir(parents=True, exist_ok=True)
    SPC = DATA_DIR / "spc"
    c = sqlite3.connect(SPC / "_stav.sqlite")
    rady = []
    for ident, nazev, kod, duvody, stran in c.execute(
            "SELECT identita, nazev, kod, duvody, stran FROM spc WHERE verdikt='podezreni'"):
        k = json.loads((SPC / ident / "kontrola.json").read_text(encoding="utf-8"))
        s = k.get("sloupce", {})
        pk = k.get("pokryti_48")
        if k.get("zdroj_48") == "pymupdf_raw" and any("nenalezena" in d for d in k.get("duvody", [])):
            typ, zav = "4.8 v PDF nenalezena", 1.0
        elif pk is None and k.get("zdroj_48") != "pymupdf_raw":
            typ, zav = "4.8 v PDF nenalezena", 1.0
        elif pk is None:
            typ, zav = ("frekvence proti značkám" if s.get("metoda") == "znacky"
                        else "frekvence (geometrie)"), 0.0
        elif pk < 0.9:
            typ, zav = "nízké pokrytí 4.8", 1 - pk
        elif s.get("metoda") == "znacky":
            typ, zav = "frekvence proti značkám", s.get("jina_frekvence", 0) / max(s.get("slov", 1), 1)
        else:
            typ, zav = "frekvence (geometrie)", s.get("spatne", 0) / max(s.get("overeno", 1), 1)
        strana = None
        try:
            strany = json.loads((SPC / ident / "strany.json").read_text(encoding="utf-8"))
            strana = next((p for h, p in strany.items() if h.strip().startswith("4.8")), None)
        except Exception:
            pass
        rady.append((typ, zav, ident, nazev, kod, duvody, pk, s, strana, stran))

    TYPY = ["4.8 v PDF nenalezena", "nízké pokrytí 4.8", "frekvence proti značkám", "frekvence (geometrie)"]
    e = html.escape
    h = ["<!doctype html><meta charset=utf-8><title>Podezřelá SPC</title><style>",
         "body{font:14px/1.45 system-ui,sans-serif;margin:1.5rem}table{border-collapse:collapse;width:100%}",
         "td,th{border:1px solid #d8dde3;padding:.3rem .5rem;text-align:left;vertical-align:top}",
         "th{background:#f4f6f8}.z{font-weight:600;color:#9b1c1c}.t{color:#6b7580;font-size:.85rem}</style>",
         f"<h1>Podezřelá SPC po konverzi ({len(rady)} z {c.execute('select count(*) from spc').fetchone()[0]})</h1>",
         "<p class=t>Seřazeno od nejzávažnějšího v každé skupině. Odkazy: PDF na straně sekce 4.8, "
         "převedený Markdown, výsledek kontroly, detail na webu SÚKL. Reference kontroly je PDF, ne Docling.</p><ul>"]
    h += [f"<li><a href='#{i}'>{t}</a>: {sum(1 for r in rady if r[0] == t)}</li>" for i, t in enumerate(TYPY)]
    h.append("</ul>")
    for i, t in enumerate(TYPY):
        sk = sorted((r for r in rady if r[0] == t), key=lambda r: -r[1])
        h.append(f"<h2 id={i}>{t} ({len(sk)})</h2><table><tr><th>#<th>SPC<th>kód<th>stran"
                 "<th>závažnost<th>důvod<th>příklady<th>odkazy</tr>")
        for n, (_, zav, ident, nazev, kod, duvody, pk, s, strana, stran) in enumerate(sk, 1):
            pr = "<br>".join(e(x) for x in (s.get("priklady") or [])[:3])
            pdf = f"../{ident}/spc.pdf" + (f"#page={strana}" if strana else "")
            h.append(f"<tr><td>{n}<td><b>{e(nazev or '')}</b><br><span class=t>{e(ident)}</span>"
                     f"<td>{e(kod or '')}<td>{stran or ''}<td class=z>{zav:.0%}<td>{e(duvody or '')}"
                     f"<td class=t>{pr}<td><a href='{pdf}'>PDF{f' s.{strana}' if strana else ''}</a> · "
                     f"<a href='../{ident}/spc.md'>md</a> · <a href='../{ident}/kontrola.json'>kontrola</a> · "
                     f"<a href='https://prehledy.sukl.gov.cz/prehled_leciv.html#/leciva/{kod}'>SÚKL</a></tr>")
        h.append("</table>")
    (ADR / "podezrele.html").write_text("\n".join(h), encoding="utf-8")
    return {t: sum(1 for r in rady if r[0] == t) for t in TYPY}
