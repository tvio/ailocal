#!/usr/bin/env python3
"""Ocisteni uz vytezenych JSON dat na rizeny slovnik. BEZ MODELU.

Aplikuje na existujici data/leciva/*/json/:
    frekvence        -> jedna ze 6 hodnot ciselniku (opravi "neste znamo")
    organovy_system  -> kanonicky MedDRA SOC (opravi rozbite mezerovani,
                        znacky poznamek, zavorky i preklepy)
    laicky tvar      -> kanonicky tvar z ciselniku pojmu, ve VSECH sekcich
                        s dvojici odborny/laicky (nezadouci ucinky,
                        indikace, kontraindikace)

Proc samostatny skript a ne znovu-extrakce: preextrahovani tyhle chyby
NEOPRAVI. Overeno - "mediální" misto "mediastinální" se pri opakovanem
behu zopakovalo, a zaroven vznikly chyby nove. Ocisteni je oproti tomu
deterministicke, zadarmo a da se pustit opakovane.

Pouziti:
  uv run python ocisti_json.py            # ukaze, co by se zmenilo
  uv run python ocisti_json.py --zapis    # zapise
"""

import json
import argparse
from pathlib import Path
from collections import Counter

from common.config import LECIVA_DIR
from common.extrakce import normalizuj_frekvenci
from common.meddra import normalizuj_soc
from common.slovnik import uplatni, laicky_tvar, klic
from common.extrakce import SEKCE_S_LAICKYM_TVAREM


def main() -> int:
    p = argparse.ArgumentParser(description="Ocisteni JSON na rizeny slovnik")
    p.add_argument("--zapis", action="store_true")
    a = p.parse_args()

    zmeny = Counter()
    ukazky: dict[str, str] = {}
    nezname: Counter = Counter()
    souboru = 0

    for f in sorted(LECIVA_DIR.glob("*/json/nezadouci_ucinky.json")):
        polozky = json.loads(f.read_text(encoding="utf-8"))
        zmeneno = False

        for x in polozky:
            if not isinstance(x, dict):
                continue

            puvodni_f = x.get("frekvence")
            kanon, rank = normalizuj_frekvenci(puvodni_f)
            if kanon != puvodni_f:
                zmeny["frekvence"] += 1
                ukazky.setdefault(f"{puvodni_f} -> {kanon}", "frekvence")
                zmeneno = True
            x["frekvence"], x["frekvence_rank"] = kanon, rank

            puvodni_s = x.get("organovy_system")
            soc, jak = normalizuj_soc(puvodni_s)
            if jak == "nezname" and puvodni_s:
                nezname[str(puvodni_s)] += 1
            if soc != puvodni_s:
                zmeny["organovy_system"] += 1
                ukazky.setdefault(f"{puvodni_s} -> {soc}", "organovy_system")
                zmeneno = True
            x["organovy_system"] = soc
            x.pop("organovy_system_opraveno", None)
            if jak == "pribuzna":
                x["organovy_system_opraveno"] = True

        if zmeneno:
            souboru += 1
            if a.zapis:
                f.write_text(json.dumps(polozky, ensure_ascii=False, indent=1),
                             encoding="utf-8")

    # ---- ciselnik pojmu na VSECHNY sekce s laickym tvarem ----
    # Zvlast od smycky vyse, protoze ta resi jen nezadouci ucinky (frekvence
    # a MedDRA jinde nejsou), kdezto laicky tvar maji tri sekce.
    slovnik_zmen = 0
    slovnik_souboru = 0
    for sekce in sorted(SEKCE_S_LAICKYM_TVAREM):
        for f in sorted(LECIVA_DIR.glob(f"*/json/{sekce}.json")):
            polozky = json.loads(f.read_text(encoding="utf-8"))
            if not isinstance(polozky, list):
                continue
            pole = ("ucinek", "ucinek_laicky") if sekce == "nezadouci_ucinky"                    else ("doslovne", "laicky")
            pred = [x.get(pole[1]) if isinstance(x, dict) else None for x in polozky]
            uplatni(polozky)
            po = [x.get(pole[1]) if isinstance(x, dict) else None for x in polozky]

            zmenenych = sum(1 for a_, b_ in zip(pred, po) if a_ != b_)
            if zmenenych:
                slovnik_zmen += zmenenych
                slovnik_souboru += 1
                for a_, b_ in zip(pred, po):
                    if a_ != b_:
                        ukazky.setdefault(f"{a_} -> {b_}", "laicky")
                if a.zapis:
                    f.write_text(json.dumps(polozky, ensure_ascii=False, indent=1),
                                 encoding="utf-8")
    if slovnik_zmen:
        zmeny["laicky_tvar"] = slovnik_zmen
        souboru += slovnik_souboru

    print(f"Souboru se zmenou: {souboru}")
    for k, v in zmeny.most_common():
        print(f"  {k:20} {v} polozek")
    print("\nUkazky oprav:")
    for zmena in sorted(ukazky):
        print(f"  {zmena}")
    if nezname:
        print("\nNEPRIPOJENO na zadny kanonicky SOC (projit rucne):")
        for k, v in nezname.most_common():
            print(f"  {v:3}x  {k}")
    if not a.zapis:
        print("\n(nic se nezapsalo - pro zapis pridej --zapis)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
