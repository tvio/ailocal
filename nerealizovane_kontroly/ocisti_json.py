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

    # --- DEDUPLIKACE A SJEDNOCENI KLICE -----------------------------------
    # Deterministicke, bez modelu. Zjisteno 22.9.2026:
    #
    # 1) UPLNE SHODNE OBJEKTY. Pozor na to, co je a co NENI duplicita:
    #    ACC ma 27 radku indikaci, ale nejsou to duplicity - je to
    #    9 indikaci x 3 vekove skupiny (dospeli/dospivajici/deti), ktere
    #    se lisi polem `skupina`. Proto se porovnava CELY objekt, ne text.
    #    Uplne shodnych je jen 6, vsechny v nezadoucich ucincich.
    #
    # 2) TYZ TEXT DOSTAL RUZNE KLICE. Generovani klice je nedeterministicke,
    #    takze tataz indikace ve trech vekovych skupinach dostala tri ruzne
    #    klice - a tim tri ruzne vektory, na ktere se stejny dotaz chyta
    #    ruzne:
    #        ACC "dedicna nemoc s hustym hlenem v plicich"
    #            deti        -> "dedicna nemoc s hustym hlenem v plicich"
    #            dospeli     -> "husty hlen v plicich"
    #            dospivajici -> "dedicna nemoc s hustym hlenem"
    #    Klic se proto sjednoti: pro tyz zdrojovy text vsude TYZ klic.
    #    Vybira se deterministicky - nejcastejsi, pri shode nejkratsi,
    #    at je vysledek stejny pri kazdem behu.
    odstraneno = sjednoceno = 0
    for sekce in ("indikace", "kontraindikace", "nezadouci_ucinky", "davkovani"):
        for f in sorted(LECIVA_DIR.glob(f"*/json/{sekce}.json")):
            try:
                polozky = json.loads(f.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if not isinstance(polozky, list):
                continue

            # 1) uplne shodne objekty pryc, poradi se zachova
            videne: set[str] = set()
            ocistene = []
            for x in polozky:
                k = json.dumps(x, ensure_ascii=False, sort_keys=True)
                if k in videne:
                    odstraneno += 1
                    continue
                videne.add(k)
                ocistene.append(x)

            # 2) tyz zdrojovy text -> tyz klic
            podle_textu: dict[str, Counter] = {}
            for x in ocistene:
                if not isinstance(x, dict) or not x.get("klic"):
                    continue
                zdroj = str(x.get("laicky") or x.get("doslovne") or "")
                podle_textu.setdefault(zdroj, Counter())[str(x["klic"])] += 1
            # nejcastejsi, pri shode nejkratsi - deterministicke
            volba = {z: min(c.items(), key=lambda kv: (-kv[1], len(kv[0]), kv[0]))[0]
                     for z, c in podle_textu.items() if len(c) > 1}
            zmeneno_tady = 0
            for x in ocistene:
                if not isinstance(x, dict) or not x.get("klic"):
                    continue
                zdroj = str(x.get("laicky") or x.get("doslovne") or "")
                if zdroj in volba and x["klic"] != volba[zdroj]:
                    ukazky.setdefault(f"{x['klic']} -> {volba[zdroj]}", "klic")
                    x["klic"] = volba[zdroj]
                    zmeneno_tady += 1
            sjednoceno += zmeneno_tady

            # POZOR: musi se rozhodovat podle TOHOTO souboru, ne podle
            # celkoveho souctu - jinak by se po prvni zmene prepisovaly
            # i soubory, ktere se nezmenily.
            if (len(ocistene) != len(polozky) or zmeneno_tady) and a.zapis:
                f.write_text(json.dumps(ocistene, ensure_ascii=False, indent=1),
                             encoding="utf-8")
    if odstraneno:
        zmeny["duplicitni_polozky"] = odstraneno
    if sjednoceno:
        zmeny["sjednoceny_klic"] = sjednoceno

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
