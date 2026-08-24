#!/usr/bin/env python3
"""Cela pipeline od A do Z jako jeden spustitelny celek.

    stahni  ->  konvertuj  ->  sekce  ->  extrakce  ->  slovnik
                                             |             |
                                             +-> kontrola <+

Kroky odpovidaji cislovani v zadani.md a v docstringech skriptu.
Kazdy krok je samostatne spustitelny i zvlast - tenhle skript je jen
poskladá ve spravnem poradi a hlida, ze se nepreskoci zavislost.

DULEZITE - zpetna vazba slovniku:
    Extrakce slovnik POUZIVA (autoritativni laicky tvar) a zaroven ho PLNI
    (nove terminy). Proto se krok 5 pousti PO extrakci a pri dalsim behu
    uz extrakce tezi z toho, co se ve slovniku mezitim opravilo. Rucni
    opravy ve slovniku tak preziji preextrahovani - to je cely smysl.

STAVY - kazda sekce ma v json/_stav.json vzdy explicitni stav, nikdy NULL:
    ok                   overeno (doslovnou shodou nebo kontrolnim modelem)
    neovereno            extrakce probehla, nikdo neoveril
    castecna             cast polozek se zachranit dala, cast ne
    zamitnuto_kontrolou  kontrola nasla polozku bez opory ve zdroji
    chybi_v_dokumentu    sekce v SPC vubec neni
    selhala_extrakce     model neodpovedel pouzitelne
    prazdna              sekce existuje, ale nic z ni nevzeslo

Pouziti:
  uv run python pipeline.py --vse              # cely bezh, uz stazena data
  uv run python pipeline.py --vse --znovu      # i preextrahovani hotoveho
  uv run python pipeline.py --od extrakce      # jen od urciteho kroku dal
  uv run python pipeline.py --vse --bez-kontroly
  uv run python pipeline.py --stav             # jen ukazat, jak na tom jsme
"""

import io
import sys
import json
import time
import argparse
import subprocess
from pathlib import Path
from collections import Counter

from common.config import LECIVA_DIR

# Poradi je zavazne - kazdy krok cte to, co vyrobil predchozi.
KROKY = [
    ("konverze",  "Krok 1 – PDF -> Markdown (Docling)",        "konvertuj_spc.py"),
    ("sekce",     "Krok 2 – vytazeni sekci + orez na jadro",    "extrahuj_sekce.py"),
    ("extrakce",  "Krok 3 – sekce -> JSON (+ zjednoduseni)",    "extrahuj_json.py"),
    ("ocisteni",  "Krok 3b – rizene slovniky (bez modelu)",     "ocisti_json.py"),
    ("kontrola1", "Krok 4a – kontrola proti zdroji (bez modelu)", "zkontroluj_json.py"),
    ("kontrola2", "Krok 4b – kontrola JINYM modelem",           "zkontroluj_modelem.py"),
    ("slovnik",   "Krok 5 – ciselnik pojmu + kontrola prekladu", "postav_slovnik.py"),
]

# Argumenty, ktere se jednotlivym skriptum predavaji.
ARGY = {
    "konverze":  ["--vse"],
    "sekce":     ["--vse"],
    "extrakce":  ["--vse"],
    "ocisteni":  ["--zapis"],
    "kontrola1": ["--zapis"],
    "kontrola2": ["--vse", "--zapis"],
    "slovnik":   ["--zkontroluj", "--zapis"],
}

# Kroky, kterym ma smysl predat --znovu.
UMI_ZNOVU = {"extrakce"}


def spust(skript: str, argy: list[str]) -> tuple[int, float]:
    t0 = time.perf_counter()
    r = subprocess.run([sys.executable, skript, *argy], text=True,
                       encoding="utf-8", errors="replace")
    return r.returncode, time.perf_counter() - t0


def prehled_stavu() -> Counter:
    c: Counter = Counter()
    for f in LECIVA_DIR.glob("*/json/_stav.json"):
        for _, v in json.loads(f.read_text(encoding="utf-8")).items():
            c[v.get("stav", "?")] += 1
    return c


def vypis_stav() -> None:
    c = prehled_stavu()
    if not c:
        print("Zadne stavy - pipeline jeste nebezela.")
        return
    celkem = sum(c.values())
    print(f"{'stav':22} {'sekci':>6}  podil")
    print("-" * 40)
    for stav, n in c.most_common():
        print(f"{stav:22} {n:6}  {n/celkem:5.0%}")
    print("-" * 40)
    print(f"{'CELKEM':22} {celkem:6}")

    k_projiti = c.get("zamitnuto_kontrolou", 0) + c.get("castecna", 0)
    if k_projiti:
        print(f"\nK RUCNIMU PROJITI: {k_projiti} sekci - seznam je v todo.md")
    neovereno = c.get("neovereno", 0)
    if neovereno:
        print(f"NEOVERENO: {neovereno} sekci - dobehnout kroky 4a/4b")

    s = Path("slovnik_pojmu.json")
    if s.exists():
        print(f"\nSlovnik pojmu: {len(json.loads(s.read_text(encoding='utf-8')))} dvojic")
    else:
        print("\nSlovnik pojmu jeste neexistuje (krok 5)")


def main() -> int:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--vse", action="store_true", help="spustit vsechny kroky")
    p.add_argument("--od", choices=[k for k, _, _ in KROKY],
                   help="spustit od tohoto kroku dal")
    p.add_argument("--jen", nargs="+", choices=[k for k, _, _ in KROKY],
                   help="spustit jen tyhle kroky")
    p.add_argument("--znovu", action="store_true",
                   help="prepsat i to, co uz je hotove")
    p.add_argument("--bez-kontroly", action="store_true",
                   help="vynechat kroky 4a/4b (jen kdyz vim proc)")
    p.add_argument("--stav", action="store_true", help="jen ukazat stav a skoncit")
    a = p.parse_args()

    if a.stav:
        vypis_stav()
        return 0

    if not (a.vse or a.od or a.jen):
        p.error("vyber --vse, --od KROK nebo --jen KROK [KROK ...]")

    kroky = list(KROKY)
    if a.od:
        zac = [k for k, _, _ in KROKY].index(a.od)
        kroky = kroky[zac:]
    if a.jen:
        kroky = [k for k in kroky if k[0] in a.jen]
    if a.bez_kontroly:
        kroky = [k for k in kroky if not k[0].startswith("kontrola")]

    print("=" * 78)
    print("PIPELINE – " + " -> ".join(k for k, _, _ in kroky))
    print("=" * 78)

    celkem_cas = 0.0
    for klic, popis, skript in kroky:
        argy = list(ARGY[klic])
        if a.znovu and klic in UMI_ZNOVU:
            argy.append("--znovu")

        print(f"\n{'='*78}\n{popis}\n  {skript} {' '.join(argy)}\n{'='*78}")
        sys.stdout.flush()
        kod, cas = spust(skript, argy)
        celkem_cas += cas
        if kod != 0:
            print(f"\nKROK SELHAL ({skript}, navratovy kod {kod}). "
                  f"Dalsi kroky se NEPOUSTI – cetly by nekompletni data.",
                  file=sys.stderr)
            return kod
        print(f"\n[{popis} hotovo za {cas/60:.1f} min]")

    print(f"\n{'='*78}\nCELA PIPELINE HOTOVA za {celkem_cas/60:.1f} min\n{'='*78}")
    vypis_stav()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
