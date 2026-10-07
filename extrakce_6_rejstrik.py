#!/usr/bin/env python3
"""Rejstrik korpusu pro cloveka: najit slozku SPC podle NAZVU nebo KODU SUKL.

PROC: slozky data/spc/<id> jsou pojmenovane podle identity dokumentu z API
(cz_63634, eu_xarelto-epar-...). Clovek zna kod SUKL (0218102) nebo nazev
(VIBROCIL) a musel si ID prekladat pres API.

Vyrobi:
    data/leky/<NAZEV SILA>_<kod>  -> odkaz (junction) na data/spc/<id>
                                    v Total Commanderu staci zacit psat
                                    nazev nebo kod (quick search)
    data/spc/_rejstrik.csv        kod; nazev; sila; forma; spc; zastupce
                                    (Excel, grep, Ctrl+F)

Junction na Windows nepotrebuje admin prava, nezabira misto a obsah se
nekopiruje. Na Linuxu (server) se misto nej udela symlink.
Slozka data/leky se pri kazdem behu postavi znovu (mesicni zmeny).

Pouziti:
  uv run python extrakce_6_rejstrik.py
  uv run python extrakce_6_rejstrik.py --najdi vibrocil       # bez Total Commanderu
  uv run python extrakce_6_rejstrik.py --najdi 0218102
"""

import io
import os
import re
import sys
import csv
import json
import shutil
import argparse
import unicodedata
from pathlib import Path

from extrakce_4_db import mapa_kod_spc

SPC_DIR = Path("data/spc")
DETAILY = Path("data/detaily_leciv")
LEKY = Path("data/leky")
REJSTRIK = SPC_DIR / "_rejstrik.csv"


def _bezpecne(s: str) -> str:
    """Nazev pro souborovy system: bez znaku, ktere Windows v nazvu nesnese."""
    return re.sub(r'[<>:"/\\|?*]+', "_", s).strip(" .")[:90]


def _bez_diakritiky(s: str) -> str:
    return "".join(z for z in unicodedata.normalize("NFD", s)
                   if unicodedata.category(z) != "Mn").lower()


def radky() -> list[dict]:
    mapa = mapa_kod_spc()
    zastupci = {}
    for kod, spc in sorted(mapa.items()):
        zastupci.setdefault(spc, kod)          # nejmensi kod = zastupce (jako extrakce_4_db)
    ven = []
    for kod, spc in sorted(mapa.items()):
        f = DETAILY / f"{kod}.json"
        a = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
        ven.append({"kod": kod, "nazev": a.get("nazev") or "", "sila": a.get("sila") or "",
                    "forma": a.get("lekovaFormaKod") or "", "spc": spc,
                    "zastupce": "ano" if zastupci[spc] == kod else ""})
    return ven


def odkaz(cil: Path, zdroj: Path) -> None:
    if sys.platform == "win32":
        import _winapi
        _winapi.CreateJunction(str(zdroj.resolve()), str(cil))
    else:
        os.symlink(zdroj.resolve(), cil, target_is_directory=True)


def postav(r: list[dict]) -> None:
    with REJSTRIK.open("w", encoding="utf-8-sig", newline="") as f:   # BOM kvuli Excelu
        w = csv.DictWriter(f, fieldnames=list(r[0]), delimiter=";")
        w.writeheader()
        w.writerows(r)

    # junction se maze jako prazdny adresar (os.rmdir), NE rekurzivne -
    # rmtree by sel do cile a smazal data SPC
    if LEKY.exists():
        for p in LEKY.iterdir():
            os.rmdir(p) if p.is_dir() else p.unlink()
    LEKY.mkdir(parents=True, exist_ok=True)
    n = 0
    for x in r:
        zdroj = SPC_DIR / x["spc"]
        if not zdroj.exists():
            continue
        jmeno = _bezpecne(f"{x['nazev']} {x['sila']}".strip() + f"_{x['kod']}")
        odkaz(LEKY / jmeno, zdroj)
        n += 1
    print(f"{REJSTRIK}: {len(r)} radku")
    print(f"{LEKY}/: {n} odkazu na slozky SPC")


def najdi(r: list[dict], co: str) -> None:
    c = _bez_diakritiky(co)
    for x in r:
        if c in x["kod"] or c in _bez_diakritiky(f"{x['nazev']} {x['sila']}"):
            print(f"{x['kod']}  {x['nazev']} {x['sila']} {x['forma']:8} "
                  f"-> data/spc/{x['spc']}{'  (zastupce)' if x['zastupce'] else ''}")


def main() -> int:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    ap = argparse.ArgumentParser(description="Rejstrik korpusu: nazev/kod -> slozka SPC")
    ap.add_argument("--najdi", help="cast nazvu nebo kodu (bez ohledu na diakritiku)")
    a = ap.parse_args()
    r = radky()
    if a.najdi:
        najdi(r, a.najdi)
    else:
        postav(r)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
