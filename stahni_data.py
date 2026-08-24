#!/usr/bin/env python3
"""Stažení dat o léčivech ze SÚKL API.

Pro každé léčivo vznikne podadresář data/leciva/<kodSUKL>/ s:
  api.json  – detail z dokumentovaného API
  spc.pdf   – SPC dokument (pokud je k dispozici)

Mezistavy zůstávají jako soubory na disku, ne v databázi – levné ladění
a není potřeba znovu bombardovat API při každé změně pipeline.

Použití:
  # pilotní vzorek (3 léčiva: CZ, EU, bohatá tabulka NÚ):
  uv run python stahni_data.py --pilot

  # konkrétní kódy:
  uv run python stahni_data.py --kody 0207818 0028820

  # podle ATC whitelistu (viz zadani.md):
  uv run python stahni_data.py --whitelist --limit-skupiny 5
"""

import json
import sys
import time
import argparse
import logging
from pathlib import Path

from common.config import DATA_DIR, LECIVA_DIR, adresar_leciva
from common.sukl_api import SuklClient, je_na_predpis, postav_pool, vyber_dle_atc

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

POOL_CACHE = DATA_DIR / "pool_leciv.json"   # cache detailu vsech leciv (discovery)

# Pilotní vzorek – viz sekce "NEJDŘÍV PILOT" v zadani.md.
# Záměrně pokrývá tři různé případy, na kterých se pozná, jestli pipeline funguje.
PILOT = {
    "0254048": "PARALEN 500MG – CZ registrace, jednoduchý dokument",
    "0500896": "IFIRMASTA 300MG – EU registrace, test ořezu na Příloha II",
    "0500778": "OLANZAPIN VIATRIS – EU + bohatá MedDRA tabulka NÚ (~10 tis. znaků)",
}

# ATC whitelist – jen léky, které laik zná a bere doma (viz zadani.md).
# Limit na skupinu je nutný: C09/A10B/C10A jsou v registru tak časté,
# že bez stropu by zabraly většinu vzorku.
ATC_WHITELIST = {
    "N02BE": 5,   # paracetamol
    "N02BA": 2,   # kyselina acetylsalicylová
    "M01A": 6,    # ibuprofen a další NSAID
    "M02A": 3,    # masti/gely na bolest
    "A02A": 3,    # antacida
    "A02B": 5,    # vředová choroba + IPP
    "R05": 5,     # kašel a nachlazení
    "R06A": 5,    # antihistaminika
    "R01A": 3,    # nosní spreje
    "J01": 6,     # antibiotika
    "C10A": 3,    # statiny
    "A10B": 3,    # cukrovka
    "C09": 3,     # vysoký tlak
}


# Vzorek pro ZJIŠTĚNÍ FORMÁTŮ sekce 4.8 – po jednom léčivu z 20 různých
# ATC skupin. Účel je jiný než u whitelistu: ne reprezentativní vzorek pro
# demo, ale co největší rozmanitost dokumentů, ať se ukáže, kolik různých
# šablon SPC vlastně existuje. Na třech dokumentech jsme našli tři formáty,
# takže je potřeba vědět, jestli jich není deset.
ATC_VZOREK_FORMATU = [
    "N02BE",  # paracetamol
    "N02BA",  # kyselina acetylsalicylová
    "M01A",   # ibuprofen a NSAID
    "M02A",   # masti na bolest
    "A02A",   # antacida
    "A02B",   # IPP
    "A03",    # spasmolytika (No-Spa, Buscopan)
    "A06A",   # projímadla
    "A10B",   # cukrovka
    "A11",    # vitaminy
    "B01A",   # antitrombotika (Warfarin, Anopyrin)
    "C07A",   # beta-blokátory
    "C09",    # tlak – ACE/sartany
    "C10A",   # statiny
    "D07A",   # dermální kortikoidy
    "H03A",   # hormony štítné žlázy (Euthyrox)
    "J01",    # antibiotika
    "R01A",   # nosní spreje
    "R05",    # kašel a nachlazení
    "R06A",   # antihistaminika
]


def uloz_lecivo(client: SuklClient, kod: str, *, popis: str = "") -> dict:
    """Stáhne detail + SPC PDF jednoho léčiva. Vrátí souhrn pro výpis."""
    detail = client.detail_leciva(kod)
    adresar = adresar_leciva(kod, detail.get("nazev"))
    adresar.mkdir(parents=True, exist_ok=True)
    (adresar / "api.json").write_text(
        json.dumps(detail, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    pdf = client.stahni_spc(kod)
    if pdf:
        (adresar / "spc.pdf").write_bytes(pdf)

    je_eu = (detail.get("registracniCislo") or "").startswith("EU")
    souhrn = {
        "kod": kod,
        "nazev": detail.get("nazev", "?"),
        "sila": detail.get("sila", ""),
        "atc": detail.get("ATCkod", ""),
        "na_predpis": je_na_predpis(detail.get("zpusobVydejeKod", "")),
        "eu": je_eu,
        "pdf_kb": len(pdf) // 1024 if pdf else 0,
        "popis": popis,
    }
    znacka = "EU" if je_eu else "CZ"
    predpis = {True: "Rx", False: "OTC", None: "??"}[souhrn["na_predpis"]]
    if pdf:
        logger.info(
            "  ✓ %s  %-28s %-10s %s %s  SPC %d kB",
            kod, souhrn["nazev"][:28], souhrn["sila"], znacka, predpis, souhrn["pdf_kb"],
        )
    else:
        logger.warning(
            "  ⚠ %s  %-28s %-10s %s %s  SPC CHYBÍ",
            kod, souhrn["nazev"][:28], souhrn["sila"], znacka, predpis,
        )
    return souhrn


def vyber_dle_whitelistu(client: SuklClient, limit_skupiny: int | None) -> list[str]:
    """Discovery přes vyhledávací API – dotaz na každou ATC skupinu whitelistu.

    Klient posílá stavZruseni='N' + ochrannyPrvek='X', takže vrací jen
    platné registrace. Bez těch parametrů by přišly jen zrušené –
    viz common/sukl_api.py a poznatky.md (13.8.2026).
    """
    kody: list[str] = []
    for atc, limit in ATC_WHITELIST.items():
        n = limit_skupiny if limit_skupiny is not None else limit
        data = client.hledej(atc=atc, pocet=max(n * 6, 30), stranka=1)
        zaznamy = data.get("data") or []

        # Preferovat přípravky reálně dodávané na trh
        zive = [z for z in zaznamy if z.get("jeDodavka")] or zaznamy

        # Jeden lék má často desítky variant balení – brát jednu na název,
        # jinak by vzorek tvořilo deset velikostí toho samého přípravku.
        videne: set[str] = set()
        vybrane: list[str] = []
        for z in zive:
            nazev = (z.get("nazevLP") or "").strip().upper()
            if not nazev or nazev in videne:
                continue
            videne.add(nazev)
            vybrane.append(z["kodSUKL"])
            if len(vybrane) >= n:
                break

        logger.info("  %-6s %2d/%-2d léčiv (v registru %d)",
                    atc, len(vybrane), n, data.get("celkem", 0))
        kody.extend(vybrane)
    return kody


def vyber_vzorek_formatu(client: SuklClient) -> list[str]:
    """Po jednom léčivu z každé ATC skupiny – maximální rozmanitost dokumentů."""
    kody: list[str] = []
    for atc in ATC_VZOREK_FORMATU:
        try:
            data = client.hledej(atc=atc, pocet=20, stranka=1)
        except Exception as e:
            logger.warning("  %-6s chyba: %s", atc, e)
            continue
        zaznamy = [z for z in (data.get("data") or []) if z.get("jeDodavka")]                   or (data.get("data") or [])
        if not zaznamy:
            logger.warning("  %-6s nic nenalezeno", atc)
            continue
        z = zaznamy[0]
        kody.append(z["kodSUKL"])
        logger.info("  %-6s %s  %s", atc, z["kodSUKL"], (z.get("nazevLP") or "")[:34])
    return kody


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Stažení dat o léčivech ze SÚKL API")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--pilot", action="store_true", help="pilotní vzorek 3 léčiv")
    g.add_argument("--kody", nargs="+", metavar="KOD", help="konkrétní kódy SÚKL")
    g.add_argument("--whitelist", action="store_true", help="výběr podle ATC whitelistu")
    g.add_argument("--vzorek-formatu", action="store_true",
                   help="1 léčivo z 20 různých ATC skupin – na zjištění formátů SPC")
    p.add_argument("--limit-skupiny", type=int, default=None,
                   help="přepíše limit na ATC skupinu (jinak dle whitelistu)")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    client = SuklClient()

    if args.pilot:
        print("=" * 64)
        print("PILOTNÍ VZOREK – ověření pipeline před během na všech léčivech")
        print("=" * 64)
        for kod, popis in PILOT.items():
            print(f"  {kod}  {popis}")
        print()
        kody = list(PILOT.keys())
    elif args.kody:
        kody = args.kody
    elif args.vzorek_formatu:
        print("Vzorek pro zjištění formátů – 1 léčivo z 20 ATC skupin:")
        kody = vyber_vzorek_formatu(client)
        print()
    else:
        print("Discovery podle ATC whitelistu (vyhledávací API):")
        kody = vyber_dle_whitelistu(client, args.limit_skupiny)
        print()

    print(f"Stahuji {len(kody)} léčiv do {LECIVA_DIR}/ ...")
    souhrny = []
    for kod in kody:
        try:
            souhrny.append(uloz_lecivo(client, kod, popis=PILOT.get(kod, "")))
        except Exception as e:
            logger.error("  ✗ %s  chyba: %s", kod, e)
        time.sleep(0.2)   # ohleduplnost k veřejnému API

    print()
    print("=" * 64)
    s_pdf = sum(1 for s in souhrny if s["pdf_kb"])
    eu = sum(1 for s in souhrny if s["eu"])
    otc = sum(1 for s in souhrny if s["na_predpis"] is False)
    print(f"Staženo {len(souhrny)}/{len(kody)} léčiv, z toho {s_pdf} má SPC PDF")
    print(f"  EU registrace: {eu}    volně prodejné: {otc}    na předpis: {len(souhrny)-otc-eu if False else sum(1 for s in souhrny if s['na_predpis'])}")
    if s_pdf < len(souhrny):
        print("  ⚠ Léčiva bez SPC nelze použít pro extrakci – budou chybět v datech.")


if __name__ == "__main__":
    main()
