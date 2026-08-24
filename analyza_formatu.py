#!/usr/bin/env python3
"""Zjistí, kolik různých formátů sekce 4.8 (nežádoucí účinky) se v SPC vyskytuje.

Motivace: na třech dokumentech jsme našli tři různé formáty. Než se napíše
prompt pro extrakci do JSONB, je potřeba vědět, na co ho psát – jinak se
bude ladit na formát, který má polovina dokumentů jiný.

Zároveň hlásí podezření na ZÁMĚNU FREKVENCÍ, kterou Docling dělá
u dokumentů bez tabulky (viz poznatky.md 14.8.2026) – tam, kde je
označení frekvence bez obsahu, se hodnota nejspíš slepila s předchozí.

Použití:
  uv run python analyza_formatu.py
"""

import re
import json
from pathlib import Path
from collections import Counter

from common.config import LECIVA_DIR

# Označení frekvence podle EU SmPC – hledá se v hlavičce tabulky i v textu.
FREKVENCE = ["velmi časté", "časté", "méně časté", "vzácné", "velmi vzácné", "není známo"]

NADPIS_48 = re.compile(r"^#{1,6}\s*4\.8\b.*$", re.MULTILINE)
NADPIS_49 = re.compile(r"^#{1,6}\s*4\.9\b", re.MULTILINE)
# "Časté:" na vlastním řádku, hodnota až na dalším – TENHLE formát Docling
# rozbíjí (slepí hodnotu s předchozím řádkem a posune frekvence).
KLIC_SAMOSTATNY = re.compile(
    r"^#*\s*(" + "|".join(FREKVENCE) + r")\s*:\s*$", re.IGNORECASE | re.MULTILINE
)
# "Časté: nevolnost, průjem" – frekvence i hodnota na JEDNOM řádku.
# Bezpečný formát, slepit se nemá co.
# POZOR: nesmí se použít \s* před hodnotou – \s matchuje i \n, takže by
# to chytlo i formát, kde je hodnota až na dalším řádku (a ten je rizikový).
KLIC_INLINE = re.compile(
    r"^#*[ \t]*(" + "|".join(FREKVENCE) + r")[ \t]*:[ \t]*\S+",
    re.IGNORECASE | re.MULTILINE,
)


def vytahni_48(md: str) -> str | None:
    m = NADPIS_48.search(md)
    if not m:
        return None
    zbytek = md[m.end():]
    konec = NADPIS_49.search(zbytek)
    return zbytek[: konec.start()] if konec else zbytek[:40000]


def radky_tabulky(sekce: str) -> list[str]:
    return [l.strip() for l in sekce.splitlines() if l.strip().startswith("|")]


def klasifikuj(sekce: str) -> tuple[str, dict]:
    """Vrátí (nazev_formatu, detaily)."""
    tab = radky_tabulky(sekce)
    samostatne = KLIC_SAMOSTATNY.findall(sekce)
    inline = KLIC_INLINE.findall(sekce)

    detail = {
        "radku_tabulky": len(tab),
        "klicu_samostatnych": len(samostatne),
        "klicu_inline": len(inline),
    }

    if tab:
        # hlavička = první řádek tabulky; obsahuje-li víc označení frekvence,
        # jde o matici (sloupce = frekvence)
        hlavicka = tab[0].lower()
        pocet_v_hlavicce = sum(1 for f in FREKVENCE if f in hlavicka)
        detail["frekvenci_v_hlavicce"] = pocet_v_hlavicce
        if pocet_v_hlavicce >= 3:
            return "A) matice – sloupce = frekvence", detail
        return "B) tabulka – řádek na účinek", detail

    # Rozlišení dvou variant klíč–hodnota je zásadní: u samostatného klíče
    # Docling slepuje hodnoty a mění frekvence (viz poznatky.md), u inline
    # zápisu se slepit nemá co.
    if len(samostatne) >= 3 and len(samostatne) > len(inline):
        return "C) klíč–hodnota, hodnota na dalším řádku ⚠", detail
    if len(inline) >= 3:
        return "D) klíč–hodnota inline (bezpečné)", detail

    if len(sekce.strip()) < 900:
        return "E) krátká próza (pár vět)", detail
    return "F) delší próza / jiné", detail


def podezreni_na_zamenu(sekce: str) -> list[str]:
    """Najde označení frekvence, za kterým nenásleduje žádný obsah.

    To je podpis chyby, kdy Docling slepí hodnotu s předchozím řádkem –
    hodnota se pak přiřadí ŠPATNÉ frekvenci. Viz poznatky.md.
    """
    problemy = []
    radky = [l.strip() for l in sekce.splitlines() if l.strip()]
    for i, r in enumerate(radky):
        cisty = r.lstrip("#").strip().rstrip(":").strip().lower()
        if cisty not in FREKVENCE:
            continue
        if not r.rstrip().endswith(":"):
            continue
        dalsi = radky[i + 1] if i + 1 < len(radky) else ""
        dalsi_cisty = dalsi.lstrip("#").strip().rstrip(":").strip().lower()
        # za označením frekvence následuje nadpis nebo jiné označení = prázdná hodnota
        if dalsi.startswith("#") or dalsi_cisty in FREKVENCE or not dalsi:
            problemy.append(r)
    return problemy


def main() -> None:
    print("=" * 78)
    print("ANALÝZA FORMÁTŮ SEKCE 4.8 (nežádoucí účinky)")
    print("=" * 78)

    formaty = Counter()
    vysledky = []
    for adr in sorted(LECIVA_DIR.iterdir()):
        md_soubor = adr / "spc.md"
        if not adr.is_dir() or not md_soubor.exists():
            continue
        md = md_soubor.read_text(encoding="utf-8")
        sekce = vytahni_48(md)
        if sekce is None:
            formaty["F) sekce 4.8 nenalezena"] += 1
            vysledky.append((adr.name, "F) sekce 4.8 nenalezena", {}, []))
            continue
        format_, detail = klasifikuj(sekce)
        zameny = podezreni_na_zamenu(sekce)
        formaty[format_] += 1
        vysledky.append((adr.name, format_, detail, zameny))

    print(f"\n{'léčivo':34} {'formát':40} {'tab.':>5} {'záměny':>7}")
    print("-" * 78)
    for nazev, format_, detail, zameny in vysledky:
        print(f"{nazev[:33]:34} {format_[:39]:40} "
              f"{detail.get('radku_tabulky', 0):5} {len(zameny):7}")

    print()
    print("SOUHRN FORMÁTŮ")
    print("-" * 78)
    celkem = sum(formaty.values())
    for f, n in formaty.most_common():
        print(f"  {n:3}/{celkem}  ({n/celkem*100:4.0f} %)  {f}")

    riziko = [(n, z) for n, _, _, z in vysledky if z]
    if riziko:
        print()
        print("⚠ PODEZŘENÍ NA ZÁMĚNU FREKVENCÍ (Docling slepil hodnoty)")
        print("-" * 78)
        for nazev, zameny in riziko:
            print(f"  {nazev[:40]:42} {len(zameny)} prázdných označení: "
                  f"{', '.join(z.strip()[:18] for z in zameny[:3])}")
        print()
        print("  U těchto dokumentů NEBRAT obsah 4.8 z markdownu –")
        print("  použít surový text z PyMuPDF, ten řádkování zachovává.")


if __name__ == "__main__":
    main()
