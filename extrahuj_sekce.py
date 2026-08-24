#!/usr/bin/env python3
"""Krok 2 pipeline: vytažení sekcí SPC do samostatných souborů.

Výstup: data/leciva/<kod>_<NAZEV>/sekce/<nazev_sekce>.md          úplná sekce
        data/leciva/<kod>_<NAZEV>/sekce/<nazev_sekce>_orez.md     ořez na jádro

Do modelu jde ořezaná verze, původní zůstává k porovnání – ať je vidět,
co ořez zahodil, a dá se ověřit, že neuřízl něco podstatného.

Mezistav zůstává na disku (viz zadani.md) – při ladění promptu pro
extrakci do JSONB se pak nemusí znovu konvertovat PDF.

Použití:
  uv run python extrahuj_sekce.py --vse
  uv run python extrahuj_sekce.py --kody 0254048
"""

import sys
import json
import argparse
from collections import Counter

from common.config import LECIVA_DIR, adresar_leciva
from common.sekce import vytahni_vsechny, orizni_na_jadro, SEKCE_SPC


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Vytažení sekcí SPC z markdownu/PDF")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--vse", action="store_true")
    g.add_argument("--kody", nargs="+", metavar="KOD")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    if args.kody:
        adresare = [adresar_leciva(k) for k in args.kody]
    else:
        adresare = sorted(p for p in LECIVA_DIR.iterdir() if p.is_dir())

    print("=" * 78)
    print("KROK 2 – vytažení sekcí SPC")
    print("=" * 78)
    print(f"{'léčivo':32} " + " ".join(f"{s[:9]:>11}" for s in SEKCE_SPC))
    print("-" * 90)

    zdroje = Counter()
    chybejici = Counter()
    uspora = Counter()
    zpracovano = 0

    for adr in adresare:
        if not (adr / "spc.md").exists():
            continue
        try:
            sekce = vytahni_vsechny(adr)
        except Exception as e:
            print(f"{adr.name[:31]:32} CHYBA: {type(e).__name__}: {e}")
            continue

        cil = adr / "sekce"
        cil.mkdir(exist_ok=True)
        prehled = {}
        bunky = []
        for nazev in SEKCE_SPC:
            s = sekce[nazev]
            if s.nalezena and s.text:
                (cil / f"{nazev}.md").write_text(s.text, encoding="utf-8")
                zdroje[s.zdroj] += 1
                znacka = "md" if s.zdroj == "docling_md" else "raw"

                # Ořezaná verze vedle původní. Do modelu jde tahle, původní
                # zůstává k porovnání – ať je vidět, co ořez zahodil.
                orez = orizni_na_jadro(s.text, nazev)
                if orez != s.text:
                    (cil / f"{nazev}_orez.md").write_text(orez, encoding="utf-8")
                    uspora[nazev] += len(s.text) - len(orez)
                    bunky.append(f"{len(s.text):>5}→{len(orez):<5}{znacka}")
                else:
                    # Ořez nic neubral – soubor _orez.md se nezakládá, ať
                    # se nepletou duplicity. Případný starý se smaže.
                    (cil / f"{nazev}_orez.md").unlink(missing_ok=True)
                    bunky.append(f"{len(s.text):>6}·{znacka}")
            else:
                chybejici[nazev] += 1
                orez = ""
                bunky.append(f"{'CHYBÍ':>11}")
            prehled[nazev] = {
                "nalezena": s.nalezena,
                "znaku": len(s.text),
                "znaku_po_orezu": len(orez),
                "zdroj": s.zdroj,
                "ma_tabulku": s.ma_tabulku,
                "cislo": s.cislo,
            }

        (cil / "_prehled.json").write_text(
            json.dumps(prehled, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        print(f"{adr.name[:31]:32} " + " ".join(f"{b:>11}" for b in bunky))
        zpracovano += 1

    print()
    print(f"Zpracováno {zpracovano} léčiv")
    print(f"Zdroj textu:  " + ", ".join(f"{k}={v}" for k, v in zdroje.most_common()))
    if uspora:
        print("Ořez na jádro (soubory <sekce>_orez.md vedle původních):")
        for k, v in uspora.most_common():
            print(f"    {k:20} ušetřeno {v:7} znaků")
        print(f"    {'CELKEM':20} ušetřeno {sum(uspora.values()):7} znaků")
    if chybejici:
        print(f"⚠ Nenalezené sekce: " + ", ".join(f"{k}={v}" for k, v in chybejici.most_common()))
        print("  Tyhle sekce dostanou v tabulce extrakce_stav stav 'chybi_v_dokumentu'")
        print("  – musí být odlišené od 'selhala_extrakce', viz zadani.md.")
    else:
        print("Všechny sledované sekce nalezeny u všech léčiv.")


if __name__ == "__main__":
    main()
