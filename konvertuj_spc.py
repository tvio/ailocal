#!/usr/bin/env python3
"""Krok 1 pipeline: SPC PDF -> Markdown (Docling), s ořezem EU dokumentů.

Výstup: data/leciva/<kodSUKL>/spc.md

Zároveň slouží jako kontrola PILOTU (viz zadani.md, sekce "NEJDŘÍV PILOT"):
vypíše, jestli konverze dopadla použitelně, než se pustí na všechna léčiva.

Použití:
  uv run python konvertuj_spc.py --pilot
  uv run python konvertuj_spc.py --vse
  uv run python konvertuj_spc.py --kody 0254048
"""

import sys
import time
import json
import argparse
import logging
from pathlib import Path

from common.config import LECIVA_DIR, adresar_leciva
from common.konverze import konvertuj_pdf, spocitej_md_tabulky

logging.basicConfig(level=logging.WARNING, format="%(message)s")

PILOT = ["0254048", "0500896", "0500778"]

# Nadpisy SPC, které musí být v dokumentu, aby byl použitelný.
# Když některý chybí, extrakce té sekce nemá z čeho brát.
POVINNE_SEKCE = {
    "4.1": "Terapeutické indikace",
    "4.2": "Dávkování a způsob podání",
    "4.3": "Kontraindikace",
    "4.8": "Nežádoucí účinky",
}


def zkontroluj(kod: str, vysl, md: str) -> dict:
    """Kontroly z pilotu – vrací slovník s výsledky pro souhrnný výpis."""
    nalezene = {}
    for cislo, nazev in POVINNE_SEKCE.items():
        # nadpis v markdownu, např. "## 4.8 Nežádoucí účinky"
        vzor = f"{cislo}"
        nalezene[cislo] = any(
            vzor in n and any(sl.lower() in n.lower() for sl in nazev.split()[:1])
            for n in vysl.nadpisy
        ) or f"\n#" in md and any(
            line.lstrip("#").strip().startswith(cislo) for line in md.splitlines()
        )
    return {
        "kod": kod,
        "znaku": len(md),
        "stran": vysl.strany_celkem,
        "nadpisu": len(vysl.nadpisy),
        "md_nadpisu": sum(1 for l in md.splitlines() if l.startswith("#")),
        "tabulek_docling": vysl.pocet_tabulek,
        "tabulek_md": spocitej_md_tabulky(md),
        "orezano": vysl.orezano,
        "stran_v_mape": len(vysl.strany_nadpisu),
        "sekce": nalezene,
    }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="SPC PDF -> Markdown přes Docling")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--pilot", action="store_true", help="jen pilotní vzorek")
    g.add_argument("--vse", action="store_true", help="všechna stažená léčiva")
    g.add_argument("--kody", nargs="+", metavar="KOD")
    p.add_argument("--bez-orezu", action="store_true",
                   help="neořezávat EU dokumenty (pro srovnání)")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    if args.pilot:
        kody = PILOT
    elif args.kody:
        kody = args.kody
    else:
        kody = sorted(p.name.split("_")[0] for p in LECIVA_DIR.iterdir() if p.is_dir())

    print("=" * 78)
    print("KROK 1 – konverze SPC do Markdownu (Docling)")
    print("=" * 78)

    vysledky = []
    for kod in kody:
        adresar = adresar_leciva(kod)
        pdf = adresar / "spc.pdf"
        if not pdf.exists():
            print(f"  ✗ {kod}  chybí spc.pdf")
            continue

        t0 = time.perf_counter()
        try:
            vysl = konvertuj_pdf(pdf, orezat_eu=not args.bez_orezu)
        except Exception as e:
            print(f"  ✗ {kod}  konverze selhala: {type(e).__name__}: {e}")
            continue
        cas = time.perf_counter() - t0

        (adresar / "spc.md").write_text(vysl.markdown, encoding="utf-8")
        if vysl.strany_nadpisu:
            (adresar / "strany.json").write_text(
                json.dumps(vysl.strany_nadpisu, ensure_ascii=False, indent=1),
                encoding="utf-8",
            )

        kontrola = zkontroluj(kod, vysl, vysl.markdown)
        kontrola["cas_s"] = cas
        vysledky.append(kontrola)

        if vysl.strana_prilohy_II:
            orez = f"str.{vysl.strana_prilohy_II} → {vysl.strany_konvertovane}/{vysl.strany_celkem}"
        else:
            orez = "ne (CZ)"
        print(f"  ✓ {kod}  {cas:6.1f}s  {len(vysl.markdown):7,} zn.  "
              f"{vysl.strany_celkem:3} str.  ořez: {orez}")

    if not vysledky:
        sys.exit(1)

    print()
    print("KONTROLA PILOTU")
    print("-" * 78)
    print(f"{'kód':9} {'nadpisy':>8} {'tab.':>5} {'str→map':>8} {'4.1':>4} {'4.2':>4} {'4.3':>4} {'4.8':>4}")
    for v in vysledky:
        s = v["sekce"]
        znak = lambda b: " ✓" if b else " ✗"
        print(f"{v['kod']:9} {v['md_nadpisu']:8} {v['tabulek_md']:5} {v['stran_v_mape']:8}"
              f"{znak(s['4.1']):>4}{znak(s['4.2']):>4}{znak(s['4.3']):>4}{znak(s['4.8']):>4}")

    print()
    celkem_cas = sum(v["cas_s"] for v in vysledky)
    print(f"Čas konverze: {celkem_cas:.1f}s celkem, "
          f"{celkem_cas/len(vysledky):.1f}s na dokument")
    print(f"  -> odhad pro 50 léčiv:  {celkem_cas/len(vysledky)*50/60:.1f} min")
    print(f"  -> odhad pro 500 léčiv: {celkem_cas/len(vysledky)*500/60:.1f} min")

    problemy = [v for v in vysledky if not all(v["sekce"].values())]
    if problemy:
        print()
        print("⚠ Léčiva s chybějící povinnou sekcí:")
        for v in problemy:
            chybi = [k for k, ok in v["sekce"].items() if not ok]
            print(f"    {v['kod']}: chybí {', '.join(chybi)}")


if __name__ == "__main__":
    main()
