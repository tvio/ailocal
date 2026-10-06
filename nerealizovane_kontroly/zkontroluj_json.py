#!/usr/bin/env python3
"""Krok 4 (cast 1): DETERMINISTICKA kontrola extrakce proti zdrojovemu textu.

Overuje to, co jde overit BEZ modelu a tedy zadarmo a spolehlive:

    nezadouci_ucinky   je 'ucinek' doslova ve zdrojovem textu sekce?
                       je 'organovy_system' ve zdrojovem textu?
                       vyskytuje se 'frekvence' ve zdrojovem textu?
    davkovani          je 'davka' doslova ve zdrojovem textu?

U indikaci a kontraindikaci se kontroluje pole 'doslovne'. Laicky tvar
('laicky', 'ucinek_laicky') se doslovne overit NEDA - je to preklad,
ve zdroji doslova neni. Ten resi ciselnik pojmu (postav_slovnik.py).

Porovnava se PO NORMALIZACI (mala pismena, bez diakritiky, bez mezer
a interpunkce), protoze zdrojova PDF maji rozbite mezerovani znaku
("zp u sob") a doslovna shoda by na tom padala.

Vysledek se zapisuje do json/_stav.json jako blok 'kontrola'. Sekce,
kde vsechno sedi, dostane stav 'ok'. Ostatni zustavaji 'neovereno'
a jdou na modelovou kontrolu.

Pouziti:
  uv run python zkontroluj_json.py                 # souhrn
  uv run python zkontroluj_json.py --detail        # + vypis podezrelych polozek
  uv run python zkontroluj_json.py --kody 0254048
  uv run python zkontroluj_json.py --zapis         # zapsat stav do _stav.json
"""

import re
import json
import argparse
import unicodedata
from pathlib import Path
from collections import Counter

from common.config import LECIVA_DIR, adresar_leciva
from common.sekce import orizni_na_jadro

# Sekce, u kterych ma doslovna kontrola smysl. Indikace a kontraindikace
# jsou zamerne prevypravene, tam by doslovna shoda hlasila same chyby.
KONTROLOVANE = {
    "nezadouci_ucinky": ["ucinek", "organovy_system", "frekvence"],
    "davkovani": ["davka"],
    # Od 19.8.2026 maji i tyhle sekce doslovny tvar, takze uz JDE overit
    # proti zdroji. Driv to byl jen laicky retezec a kontrola je musela
    # preskocit uplne.
    "indikace": ["doslovne"],
    "kontraindikace": ["doslovne"],
}

# Klice, u kterych se NEporovnava doslovny text, ale jen CISLA v nem.
# Duvod: model davku legitimne sklada a prepisuje jednotky - ze zdrojove
# tabulky "25-50 | 100-200" a hlavicky "mikrogramu/den" udela
# "uvodni davka: 25-50 mcg; udrzovaci davka: 100-200 mcg". Doslovna shoda
# tam hlasila 27 z 27 polozek jako chybu, prestoze data byla spravna.
# Cisla ale sedet MUSI - a prave preklep v cisle je u davkovani to
# nebezpecne, ne prepsana jednotka.
JEN_CISLA = {"davkovani": {"davka"}}

# Pismo mimo latinku v ceskem textu = chyba modelu. ADVANTAN mel u 5 z 36
# polozek "Celkove poruchy a reakce v mesте aplikace" - CYRILICI uprostred
# slova. Doslovna kontrola to chytila az jako vedlejsi efekt, tohle je
# primy test a stoji nic.
# POZOR: recka abeceda se sem NESMI pridat. "gamma-GT" se pise "γ-GT"
# a je to legitimni lekarsky zapis - pridani \u0370-\u03FF delalo falesny
# poplach na "Zvysene jaterni enzymy (transaminazy, γ-GT)".
NELATINKA = re.compile(r"[Ѐ-ӿ一-鿿]")

# Kratke hodnoty nekontrolovat - "1 ml" nebo "kasel" se ve zdroji najde
# nahodou skoro vzdy a kontrola by nic neznamenala.
MIN_DELKA = 4


def cisla(s: str, *, obe_cteni: bool = False) -> list[str]:
    """Cisla v textu, pro porovnani davky bez ohledu na formulaci.

    Mezera mezi cislicemi je v ceskych PDF NEJEDNOZNACNA:
        "500 - 1 000 mg"  -> tisice, model to zapise "1000"
        "| 150 300 |"     -> rozsah 150-300, kteremu tabulka snedla pomlcku
    Rozlisit to nejde. Proto se na strane ZDROJE (obe_cteni=True) vraci
    obe varianty - jednotliva cisla i slepenec - a shoda staci s jednou
    z nich. Na strane modelu se vraci jen to, co tam doslova je.
    """
    t = str(s).replace(chr(160), " ")
    ven = re.findall(r"\d+(?:[.,]\d+)?", t)
    if obe_cteni:
        slepene = re.sub(r"(?<=\d)[ ](?=\d{3}(?!\d))", "", t)
        ven += re.findall(r"\d+(?:[.,]\d+)?", slepene)
    return ven


def norm(s: str) -> str:
    """Na porovnani: mala pismena, bez diakritiky, bez mezer a interpunkce."""
    if not s:
        return ""
    bez = "".join(z for z in unicodedata.normalize("NFKD", str(s))
                  if not unicodedata.combining(z))
    return re.sub(r"[^a-z0-9]", "", bez.lower())


def zkontroluj_lecivo(adr: Path) -> dict:
    """Vrati {sekce: {"celkem": n, "chybne": [(klic, hodnota), ...]}}."""
    vysledek = {}
    for sekce, klice in KONTROLOVANE.items():
        js = adr / "json" / f"{sekce}.json"
        md = adr / "sekce" / f"{sekce}.md"
        if not js.exists() or not md.exists():
            continue

        # Model videl orezanou verzi, takze proti ni se i porovnava.
        zdroj = norm(orizni_na_jadro(md.read_text(encoding="utf-8"), sekce))
        polozky = json.loads(js.read_text(encoding="utf-8"))

        zdroj_cisla = set(cisla(orizni_na_jadro(md.read_text(encoding="utf-8"), sekce),
                                obe_cteni=True))

        chybne = []
        for p in polozky:
            if not isinstance(p, dict):
                continue
            # Cizi pismo je chyba bez ohledu na klic
            for klic, hodnota in p.items():
                if isinstance(hodnota, str) and NELATINKA.search(hodnota):
                    chybne.append((f"{klic}/cizi-pismo", hodnota))

            for klic in klice:
                hodnota = p.get(klic)
                if not hodnota or len(str(hodnota)) < MIN_DELKA:
                    continue
                if klic in JEN_CISLA.get(sekce, set()):
                    chybejici = [c for c in cisla(hodnota) if c not in zdroj_cisla]
                    if chybejici:
                        chybne.append((f"{klic}/cislo", f"{hodnota}  [chybi: {chybejici}]"))
                elif norm(hodnota) not in zdroj:
                    chybne.append((klic, str(hodnota)))
        vysledek[sekce] = {"celkem": len(polozky), "chybne": chybne}
    return vysledek


def main() -> int:
    p = argparse.ArgumentParser(description="Deterministicka kontrola extrakce")
    p.add_argument("--kody", nargs="+", metavar="KOD")
    p.add_argument("--detail", action="store_true", help="vypsat podezrele polozky")
    p.add_argument("--zapis", action="store_true", help="zapsat vysledek do _stav.json")
    a = p.parse_args()

    adresare = ([adresar_leciva(k) for k in a.kody] if a.kody
                else sorted(x for x in LECIVA_DIR.iterdir() if x.is_dir()))

    print(f"{'lecivo':30} {'sekce':18} {'polozek':>8} {'nesedi':>7} {'shoda':>7}")
    print("-" * 76)

    souhrn = Counter()
    duvody = Counter()
    for adr in adresare:
        v = zkontroluj_lecivo(adr)
        if not v:
            continue
        stav_soubor = adr / "json" / "_stav.json"
        stav = json.loads(stav_soubor.read_text(encoding="utf-8")) if stav_soubor.exists() else {}

        for sekce, r in v.items():
            n, chybnych = r["celkem"], len(r["chybne"])
            shoda = (n - chybnych) / n if n else 1.0
            souhrn["polozek"] += n
            souhrn["chybnych"] += chybnych
            souhrn["sekci"] += 1
            souhrn["sekci_cistych"] += (chybnych == 0)
            for klic, _ in r["chybne"]:
                duvody[f"{sekce}.{klic}"] += 1

            znacka = "" if chybnych == 0 else "  <-"
            print(f"{adr.name[:30]:30} {sekce:18} {n:8} {chybnych:7} {shoda:6.0%}{znacka}")

            if a.detail and r["chybne"]:
                for klic, hodnota in r["chybne"][:8]:
                    print(f"      {klic:18} {hodnota[:70]!r}")
                if len(r["chybne"]) > 8:
                    print(f"      ... a dalsich {len(r['chybne']) - 8}")

            if a.zapis:
                blok = stav.setdefault(sekce, {})
                blok["kontrola"] = {
                    "typ": "deterministicka",
                    "polozek": n,
                    "nesedi": chybnych,
                    "shoda": round(shoda, 3),
                }
                # Stav 'ok' jen kdyz sedi VSECHNO. Jinak zustava 'neovereno'
                # a sekce jde na modelovou kontrolu.
                if chybnych == 0 and blok.get("stav") == "neovereno":
                    blok["stav"] = "ok"

        if a.zapis:
            stav_soubor.write_text(json.dumps(stav, ensure_ascii=False, indent=1),
                                   encoding="utf-8")

    print()
    print(f"Sekci: {souhrn['sekci']}, z toho bez jedine neshody: {souhrn['sekci_cistych']}")
    print(f"Polozek: {souhrn['polozek']}, nesedi: {souhrn['chybnych']} "
          f"({souhrn['chybnych']/souhrn['polozek']:.1%})" if souhrn['polozek'] else "")
    if duvody:
        print("Kde to nesedi:")
        for k, v_ in duvody.most_common():
            print(f"    {k:34} {v_}")
    if not a.zapis:
        print("\n(nic se nezapsalo - pro zapis do _stav.json pridej --zapis)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
