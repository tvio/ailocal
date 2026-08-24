#!/usr/bin/env python3
"""Kontrola ořezu sekcí – ukáže, co ořez ZAHODIL.

Ořez na jádro je záměrná ztráta informace, takže se musí dát ověřit,
že neuřízl něco podstatného. Tenhle skript proto nevypisuje, co zůstalo
(to je v <sekce>_orez.md), ale co zmizelo.

Použití:
  uv run python zkontroluj_orez.py                    # souhrn za všechna léčiva
  uv run python zkontroluj_orez.py --detail           # + odříznutý text
  uv run python zkontroluj_orez.py --kody 0260415     # jen vybraná léčiva
  uv run python zkontroluj_orez.py --sekce davkovani  # jen jedna sekce
  uv run python zkontroluj_orez.py --podezrele        # jen ty, co stojí za oko
"""

import sys
import argparse
from pathlib import Path

from common.config import LECIVA_DIR, adresar_leciva
from common.sekce import SEKCE_SPC

# Ořez, po kterém zbyde míň než tohle, si zaslouží ruční pohled.
PRAH_KRATKE = 150
# Ořez, který zahodil víc než tolik procent, taky.
PRAH_PODIL = 0.75


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Co ořez sekcí zahodil")
    p.add_argument("--kody", nargs="+", metavar="KOD")
    p.add_argument("--sekce", choices=sorted(SEKCE_SPC), help="jen jedna sekce")
    p.add_argument("--detail", action="store_true", help="vypsat odříznutý text")
    p.add_argument("--podezrele", action="store_true",
                   help="jen sekce, kde ořez zahodil hodně nebo zbylo málo")
    p.add_argument("--znaku", type=int, default=600,
                   help="kolik znaků odříznutého textu vypsat (--detail)")
    return p.parse_args()


def main() -> int:
    a = parse_args()
    adresare = ([adresar_leciva(k) for k in a.kody] if a.kody
                else sorted(p for p in LECIVA_DIR.iterdir() if p.is_dir()))
    sekce = [a.sekce] if a.sekce else list(SEKCE_SPC)

    print(f"{'léčivo':30} {'sekce':18} {'původní':>8} {'jádro':>7} {'zbylo':>6}  poznámka")
    print("-" * 92)

    podezrelych = 0
    celkem = 0
    for adr in adresare:
        d = adr / "sekce"
        if not d.exists():
            continue
        for nazev in sekce:
            plny = d / f"{nazev}.md"
            orez = d / f"{nazev}_orez.md"
            if not plny.exists():
                continue
            t = plny.read_text(encoding="utf-8")
            o = orez.read_text(encoding="utf-8") if orez.exists() else t
            if len(o) == len(t):
                continue          # ořez nic neudělal, není co kontrolovat

            celkem += 1
            podil = len(o) / len(t) if t else 1.0
            pozn = []
            if len(o) < PRAH_KRATKE:
                pozn.append("zbylo málo")
            if 1 - podil > PRAH_PODIL:
                pozn.append("zahozeno hodně")
            je_podezrele = bool(pozn)
            podezrelych += je_podezrele

            if a.podezrele and not je_podezrele:
                continue

            print(f"{adr.name[:30]:30} {nazev:18} {len(t):8} {len(o):7} "
                  f"{podil:5.0%}  {', '.join(pozn)}")

            if a.detail:
                # Ořez je vždy prefix původního textu (řeže se odzadu),
                # takže odříznutá část je prostě zbytek za jádrem.
                zahozeno = t[len(o):].strip() if t.startswith(o[:200]) else "(nelze určit)"
                for radek in zahozeno[: a.znaku].splitlines():
                    print(f"      | {radek}")
                if len(zahozeno) > a.znaku:
                    print(f"      | ... (dalších {len(zahozeno) - a.znaku} znaků)")
                print()

    print()
    print(f"Ořez zasáhl {celkem} sekcí, z toho {podezrelych} stojí za ruční pohled.")
    if podezrelych and not a.podezrele:
        print("Projít je: uv run python zkontroluj_orez.py --podezrele --detail")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
