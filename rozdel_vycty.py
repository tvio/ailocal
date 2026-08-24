#!/usr/bin/env python3
"""Rozdeleni indikaci/kontraindikaci, ktere obsahuji VIC SAMOSTATNYCH POJMU.

PROC: embedding je JEDEN bod v prostoru vyznamu. Kdyz radek obsahuje ctyri
priznaky, bod padne doprostred mezi ne a je blizko k zadnemu. MAALOX ma
v jedne indikaci ctyri: paleni zahy, rihani, reflux, bolest na lacno.
Zmereno (bge-m3), o kolik si polepsi kazdy z nich vlastnim radkem:

    "mám reflux"               0,474 -> 0,555
    "pálí mě žáha"             0,633 -> 0,900
    "pořád říhám"              0,431 -> 0,663   (dnes POD prahem!)
    "bolí mě břicho na lačno"  0,619 -> 0,904

PROC MODELEM A NE REGEXEM: zmereno, ze naivni deleni na carkach uskodi
ve 3 z 5 pripadu -
    OLYNTH      "zanetem, jako je alergickym, jinym nez alergickym..."
                -> pridavna jmena k TEMUZ zanetu, ne samostatne pojmy
    AMOKSIKLAV  "alergie na cefalosporiny, karbapenemy nebo monobaktamy"
                -> rozdelenim se ztrati "alergie na"
    ACIFEIN     "bolesti hlavy, zubu"
                -> ze "zubu" samotneho nic nezbude
Model cestinu chape a umi doplnit "bolesti zubu". Polozek je v korpusu
7, takze je to levne a da se to projit ocima.

Pouziti:
  uv run python rozdel_vycty.py            # ukaze navrh
  uv run python rozdel_vycty.py --zapis
"""

import io
import re
import sys
import json
import argparse
from pathlib import Path

from common.config import LECIVA_DIR, MODEL_HLAVNI
from common.ollama_client import chat_detail
from common.extrakce import _ocisti_odpoved

SEKCE = ("indikace", "kontraindikace")

# Vycet se pozna podle uvozujici fraze. Zamerne UZKY vzor - lepe nekolik
# polozek minout nez rozsekat neco, co se rozsekat nema.
VZOR = re.compile(
    r"^(?P<pred>.{6,}?)[,:]\s*"
    r"(?:jako jsou|jako je|např\.|napr\.|zejména|zejmena|včetně|vcetne)\s+"
    r"(?P<vycet>.+)$", re.I)

POKYN = """Dostaneš jednu položku ze souhrnu údajů o léčivém přípravku.
Obsahuje odborný text (doslovne) a jeho laické vyjádření (laicky).

Rozhodni, jestli položka popisuje VÍC SAMOSTATNÝCH stavů, nebo JEDEN.

ROZDĚL jen tehdy, když jde o samostatné, navzájem nezávislé stavy:
  "bolesti, jako jsou bolesti hlavy, zubů a zad"
  -> "bolest hlavy" | "bolest zubů" | "bolest zad"
  Každý díl musí dávat smysl SÁM O SOBĚ. Když je díl neúplný ("zubů"),
  doplň ho do celého tvaru ("bolest zubů").

NEROZDĚLUJ, když je výčet jen upřesněním JEDNOHO stavu:
  "zánět nosu, ať už alergický, nealergický nebo virový"  -> JEDEN stav
  "alergie na cefalosporiny, karbapenemy nebo monobaktamy" -> JEDEN stav
     (rozdělením by se ztratilo "alergie na")

Úvodní obecná část ("léčba potíží spojených s přílišnou kyselinou")
je taky samostatný stav - nech ji jako první díl.

KAŽDÝ DÍL MUSÍ BÝT SAMOSTATNÝ NÁZEV STAVU, ne úryvek věty:
  - v 1. PÁDĚ ("bolest zad", NE "bolestí způsobených problémy se zády")
  - BEZ spojek a uvozovacích slov na začátku
    ("bolest hlavy", NE "zejména bolesti hlavy", NE "a bolest kloubů")
  - bez koncové tečky
Špatně: "zejména bolesti hlavy" | "a bolestí kloubů" | "rozlitého zánětu kůže"
Správně: "bolest hlavy"        | "bolest kloubů"    | "rozlitý zánět kůže"

doslovne a laicky MUSÍ mít po rozdělení STEJNÝ počet dílů a i-tý díl
odborný musí odpovídat i-tému dílu laickému.

Vrať POUZE JSON, nic jiného:
{"rozdelit": true, "casti": [{"doslovne": "...", "laicky": "..."}, ...]}
nebo
{"rozdelit": false}"""


def kandidati() -> list[tuple[Path, int, dict]]:
    ven = []
    for sekce in SEKCE:
        for f in sorted(Path(LECIVA_DIR).glob(f"*/json/{sekce}.json")):
            for i, x in enumerate(json.loads(f.read_text(encoding="utf-8"))):
                if isinstance(x, dict) and VZOR.match(str(x.get("laicky") or "")):
                    ven.append((f, i, x))
    return ven


def rozdel(x: dict) -> list[dict] | None:
    zprava = json.dumps({"doslovne": x.get("doslovne"), "laicky": x.get("laicky")},
                        ensure_ascii=False)
    odp, _ = chat_detail(zprava, model=MODEL_HLAVNI, system=POKYN)
    try:
        d = json.loads(_ocisti_odpoved(odp))
    except json.JSONDecodeError:
        return None
    if not d.get("rozdelit"):
        return None
    casti = [c for c in d.get("casti", [])
             if isinstance(c, dict) and c.get("doslovne") and c.get("laicky")]
    return casti if len(casti) > 1 else None


def main() -> int:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    ap = argparse.ArgumentParser(description="rozdeleni vicepojmovych polozek")
    ap.add_argument("--zapis", action="store_true")
    a = ap.parse_args()

    kand = kandidati()
    print(f"Kandidatu s vyctem: {len(kand)}\n")

    # Zmeny se sbiraji podle souboru, aby se kazdy prepsal jednou a indexy
    # se nerozjely pri vkladani.
    zmeny: dict[Path, dict[int, list[dict]]] = {}
    for f, i, x in kand:
        lek = f.parent.parent.name
        casti = rozdel(x)
        print(f"--- {lek} / {f.stem}")
        print(f"    PUVODNI: {str(x.get('laicky'))[:96]}")
        if not casti:
            print("    -> NEDELIT (jeden stav)\n")
            continue
        for c in casti:
            print(f"    -> {c['laicky'][:88]}")
        print()
        zmeny.setdefault(f, {})[i] = casti

    celkem = sum(len(v) for v in zmeny.values())
    novych = sum(len(c) for v in zmeny.values() for c in v.values())
    print(f"K rozdeleni: {celkem} polozek -> {novych} polozek")

    if not a.zapis:
        print("\n(nic se nezapsalo - pro zapis pridej --zapis)")
        return 0

    for f, podle_indexu in zmeny.items():
        polozky = json.loads(f.read_text(encoding="utf-8"))
        nove = []
        for i, x in enumerate(polozky):
            if i in podle_indexu:
                for c in podle_indexu[i]:
                    novy = dict(x)                    # zachova skupinu, stranu...
                    novy["doslovne"] = c["doslovne"]
                    novy["laicky"] = c["laicky"]
                    novy["rozdeleno_z_vyctu"] = True  # provenience
                    nove.append(novy)
            else:
                nove.append(x)
        f.write_text(json.dumps(nove, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Zapsano do {len(zmeny)} souboru.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
