#!/usr/bin/env python3
"""Dopocet KLICU pro hledani u uz extrahovanych dat.

Klic je 1-4 slova v 1. pade, ktera pojmenovavaji stav. Slouzi VYHRADNE
k hledani - uzivateli se dal zobrazuje puvodni text, takze dohledatelnost
do SPC zustava.

Proc to je potreba: dlouha veta redi vyznam. Zmereno na 10 polozkach
(`test_klice.py`): vektorova podobnost +0,125 prumerne, u fulltextu
klesly nuly ze 7/10 na 4/10.

Nova leciva dostanou klic rovnou pri extrakci (je v sablone). Tenhle
skript je jen pro data, ktera uz v korpusu jsou.

Zpracovavaji se JEN polozky nad --min-slov, u kratkych klic nema smysl -
kratky text uz klicem je.

Pouziti:
  uv run python doplni_klice.py                 # ukaze, co by udelal
  uv run python doplni_klice.py --zapis
  uv run python doplni_klice.py --zapis --kody 0179727
"""

import io
import sys
import json
import time
import argparse
from pathlib import Path

from common.config import LECIVA_DIR, MODEL_HLAVNI
from common.ollama_client import chat_detail
from common.extrakce import _ocisti_odpoved, klic_ma_oporu

SEKCE = ("indikace", "kontraindikace")

POKYN = """Dostaneš jednu položku ze souhrnu údajů o přípravku (SPC).

Vrať KLÍČ pro vyhledávání: 1-4 slova, která pojmenovávají STAV nebo
NEMOC, kvůli které člověk ten lék hledá.

Klíč slouží k tomu, aby lék NAŠEL LAIK. Není to odborný název ani
zkrácená indikace - je to heslo do vyhledávače.

PRAVIDLA:

1. **1. PÁD**, jak by to napsal člověk do vyhledávače
   "akutní průjem"   NE "akutního průjmu"

2. **DRŽ SE SLOV, KTERÁ JSOU V ZADANÉM TEXTU.** Nepřeváděj je na
   odbornější. "kožní vyrážka se svěděním" -> "svědivá kožní vyrážka",
   NE "chronická idiopatická kopřivka". Odborný termín použij JEN
   tehdy, když je i v zadaném textu.

3. **SKUPINU PACIENTŮ ZACHOVEJ**, když je v textu.
   "...hubnutí u dětí starších 12 let"  ->  "hubnutí u dětí"

4. Vynech slova, která nejsou názvem stavu: "léčba", "doplňková",
   "prevence", "dlouhodobé", "pokud nelze", "spolu s".

5. Když v textu ŽÁDNÝ stav ani nemoc není (je to jen výhrada nebo
   podmínka použití), vrať null.

Vrať POUZE JSON: {"klic": "..."} nebo {"klic": null}"""


def vyrob_klic(text: str) -> tuple[str | None, float]:
    odp, m = chat_detail(text, model=MODEL_HLAVNI, system=POKYN)
    try:
        k = json.loads(_ocisti_odpoved(odp)).get("klic")
    except json.JSONDecodeError:
        k = None
    return (str(k).strip() if k else None), m.cas_celkem_s


def main() -> int:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    ap = argparse.ArgumentParser(description="dopocet klicu pro hledani")
    ap.add_argument("--zapis", action="store_true")
    ap.add_argument("--kody", nargs="+")
    ap.add_argument("--min-slov", type=int, default=6,
                    help="polozky kratsi nez tohle se preskoci (klicem uz jsou)")
    a = ap.parse_args()

    soubory = []
    for sekce in SEKCE:
        for f in sorted(Path(LECIVA_DIR).glob(f"*/json/{sekce}.json")):
            if a.kody and not any(k in f.parent.parent.name for k in a.kody):
                continue
            soubory.append(f)

    t0 = time.perf_counter()
    hotovo = preskoceno = zahozeno = 0
    zmeny: dict[Path, list] = {}

    for f in soubory:
        polozky = json.loads(f.read_text(encoding="utf-8"))
        lek = f.parent.parent.name
        zmeneno = False
        for x in polozky:
            if not isinstance(x, dict):
                continue
            if x.get("klic"):
                continue                       # uz ho ma
            zdroj = x.get("laicky") or x.get("doslovne") or ""
            if len(str(zdroj).split()) < a.min_slov:
                # Kratky text uz klicem JE - vlastni klic by nic nepridal.
                x["klic"] = None
                preskoceno += 1
                zmeneno = True
                continue

            k, cas = vyrob_klic(zdroj)
            # Deterministicka pojistka: klic bez opory v puvodnim textu
            # se zahazuje. Model ma sklon prekladat "nahoru".
            if k and not klic_ma_oporu(k, zdroj):
                print(f"  ZAHOZEN {lek[:20]:20} {k!r} "
                      f"(nema oporu v {str(zdroj)[:44]!r})")
                k = None
                zahozeno += 1
            x["klic"] = k
            hotovo += 1
            zmeneno = True
            print(f"  {lek[:20]:20} {f.stem[:14]:14} ({cas:4.1f} s) "
                  f"{str(zdroj)[:40]:42} -> {k!r}")
        if zmeneno:
            zmeny[f] = polozky

    cas = time.perf_counter() - t0
    print()
    print(f"Vyrobeno klicu:  {hotovo}")
    print(f"  z toho zahozeno pojistkou: {zahozeno}")
    print(f"Preskoceno (kratke, pod {a.min_slov} slov): {preskoceno}")
    print(f"Souboru ke zmene: {len(zmeny)}")
    print(f"Cas: {cas / 60:.1f} min")

    if not a.zapis:
        print("\n(nic se nezapsalo - pro zapis pridej --zapis)")
        return 0

    for f, polozky in zmeny.items():
        f.write_text(json.dumps(polozky, ensure_ascii=False, indent=1),
                     encoding="utf-8")
    print(f"Zapsano do {len(zmeny)} souboru.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
