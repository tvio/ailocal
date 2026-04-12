#!/usr/bin/env python3
"""UC11 – Detekce anomálií v strukturovaných datech.

LLM jako "druhý pár očí" – kontrola tabulkových dat a hledání podezřelých záznamů.
Porovnání pravidlového přístupu (pandas-like) vs. LLM přístupu.

Použití:
  uv run python demo11_anomaly_detection.py
  uv run python demo11_anomaly_detection.py invoices.csv
  uv run python demo11_anomaly_detection.py --method both
"""

import csv
import sys
import io
import json
import argparse
from pathlib import Path
from collections import Counter

from common.config import MODEL_CHAT, CSV_DIR
from common.ollama_client import get_ollama_url, chat


# Syntetická data faktur (pokud uživatel nemá vlastní)
SAMPLE_INVOICES = """\
id,dodavatel,castka,mena,datum,popis
1,ABC Technologies,45000,CZK,2026-01-15,IT služby leden
2,ABC Technologies,45000,CZK,2026-02-15,IT služby únor
3,ABC Technologies,45000,CZK,2026-03-15,IT služby březen
4,XYZ Consulting,120000,CZK,2026-01-20,Poradenství Q1
5,XYZ Consulting,120000,CZK,2026-01-21,Poradenství Q1
6,Kancelářské potřeby s.r.o.,3500,CZK,2026-02-01,Tonery a papír
7,Kancelářské potřeby s.r.o.,3500,CZK,2026-02-15,Tonery a papír
8,Kancelářské potřeby s.r.o.,35000,CZK,2026-03-01,Tonery a papír
9,Global Services Ltd,89000,EUR,2026-02-10,Licence software
10,Global Services Ltd,89000,CZK,2026-03-10,Licence software
11,Jan Novák - OSVČ,250000,CZK,2026-03-20,Konzultace
12,ABC Technologies,45000,CZK,2026-03-15,IT služby březen
13,Catering Deluxe,15000,CZK,2026-03-25,Firemní akce
14,Neznámý dodavatel,1,CZK,2026-03-30,Test
15,XYZ Consulting,0,CZK,2026-03-31,Dobropis
"""


def parse_csv(csv_text: str) -> list[dict]:
    """Parsuje CSV text do seznamu slovníků."""
    reader = csv.DictReader(io.StringIO(csv_text.strip()))
    return list(reader)


def rule_based_check(invoices: list[dict]) -> list[dict]:
    """Pravidlový přístup – hledání anomálií pomocí jednoduchých pravidel."""
    anomalies = []

    # Pravidlo 1: Duplicitní faktury (stejný dodavatel, částka, popis)
    seen = {}
    for inv in invoices:
        key = (inv["dodavatel"], inv["castka"], inv["popis"])
        if key in seen:
            anomalies.append({
                "pravidlo": "DUPLICITA",
                "id": inv["id"],
                "popis": f"Možná duplicita s fakturou #{seen[key]} – stejný dodavatel, částka a popis",
            })
        else:
            seen[key] = inv["id"]

    # Pravidlo 2: Neobvykle vysoká částka (> 3× průměr)
    amounts = [float(inv["castka"]) for inv in invoices if float(inv["castka"]) > 0]
    if amounts:
        avg = sum(amounts) / len(amounts)
        for inv in invoices:
            amt = float(inv["castka"])
            if amt > 3 * avg:
                anomalies.append({
                    "pravidlo": "VYSOKÁ ČÁSTKA",
                    "id": inv["id"],
                    "popis": f"Částka {amt:,.0f} je {amt/avg:.1f}× vyšší než průměr ({avg:,.0f})",
                })

    # Pravidlo 3: Nulová nebo minimální částka
    for inv in invoices:
        amt = float(inv["castka"])
        if amt <= 1:
            anomalies.append({
                "pravidlo": "PODEZŘELÁ ČÁSTKA",
                "id": inv["id"],
                "popis": f"Částka {amt} je podezřele nízká",
            })

    # Pravidlo 4: Nesoulad měny u stejného dodavatele
    supplier_currencies: dict[str, set] = {}
    for inv in invoices:
        supplier_currencies.setdefault(inv["dodavatel"], set()).add(inv["mena"])
    for supplier, currencies in supplier_currencies.items():
        if len(currencies) > 1:
            related = [inv for inv in invoices if inv["dodavatel"] == supplier]
            for inv in related:
                anomalies.append({
                    "pravidlo": "NESOULAD MĚNY",
                    "id": inv["id"],
                    "popis": f"Dodavatel '{supplier}' fakturuje v různých měnách: {', '.join(currencies)}",
                })

    # Pravidlo 5: Náhlá změna částky u pravidelné faktury
    supplier_amounts: dict[str, list] = {}
    for inv in invoices:
        supplier_amounts.setdefault(inv["dodavatel"], []).append(float(inv["castka"]))
    for supplier, amts in supplier_amounts.items():
        if len(amts) >= 3:
            most_common = Counter(amts).most_common(1)[0][0]
            for inv in invoices:
                if inv["dodavatel"] == supplier:
                    amt = float(inv["castka"])
                    if amt != most_common and most_common > 0 and abs(amt - most_common) / most_common > 0.5:
                        anomalies.append({
                            "pravidlo": "ZMĚNA ČÁSTKY",
                            "id": inv["id"],
                            "popis": f"Částka {amt:,.0f} se liší od obvyklé {most_common:,.0f} u dodavatele '{supplier}'",
                        })

    return anomalies


def llm_check(invoices: list[dict], *, model: str, base_url: str) -> str:
    """LLM přístup – model analyzuje data a hledá anomálie."""
    # Převedeme na čitelný text
    csv_text = "id | dodavatel | castka | mena | datum | popis\n"
    csv_text += "-" * 80 + "\n"
    for inv in invoices:
        csv_text += f"{inv['id']} | {inv['dodavatel']} | {inv['castka']} | {inv['mena']} | {inv['datum']} | {inv['popis']}\n"

    system = (
        "Jsi interní auditor, který kontroluje firemní faktury. "
        "Hledáš anomálie, podezřelé vzory, duplicity, neobvyklé částky a další nesrovnalosti. "
        "Buď konkrétní – uveď čísla faktur a důvody podezření. "
        "Odpovídej česky a strukturovaně."
    )

    prompt = f"""Analyzuj následující seznam faktur a najdi VŠECHNY anomálie a podezřelé záznamy.

Hledej zejména:
- Duplicitní faktury
- Neobvykle vysoké nebo nízké částky
- Nesoulad měn
- Podezřelé vzory (např. zaokrouhlené částky, neznámí dodavatelé)
- Faktury těsně pod schvalovacími limity
- Cokoli dalšího, co vypadá podezřele

{csv_text}

Tvá analýza:"""

    return chat(prompt, system=system, model=model, base_url=base_url, stream=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="UC11 – Detekce anomálií v strukturovaných datech"
    )
    parser.add_argument("input", nargs="?", help="Název CSV souboru (hledá se v data/csv/)")
    parser.add_argument("--method", choices=["rules", "llm", "both"], default="both")
    parser.add_argument("--model", default=MODEL_CHAT, help=f"Model (výchozí {MODEL_CHAT})")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Načtení dat
    if args.input:
        input_path = Path(args.input)
        if not input_path.exists():
            input_path = CSV_DIR / args.input
        if not input_path.exists():
            print(f"Chyba: soubor '{args.input}' nenalezen (ani v {CSV_DIR}/).", file=sys.stderr)
            sys.exit(1)
        csv_text = input_path.read_text(encoding="utf-8")
    else:
        csv_text = SAMPLE_INVOICES
        print("ℹ️  Používám vestavěná syntetická data (15 faktur)")

    invoices = parse_csv(csv_text)

    print("=" * 60)
    print("UC11 – Detekce anomálií v strukturovaných datech")
    print("=" * 60)
    print(f"\n📊 Faktur:  {len(invoices)}")
    print(f"⚙️  Metoda:  {args.method}")

    # Přístup 1: Pravidlový
    if args.method in ("rules", "both"):
        print(f"\n{'='*60}")
        print("📐 Přístup 1: Pravidlová kontrola")
        print("-" * 60)
        rule_anomalies = rule_based_check(invoices)
        if rule_anomalies:
            print(f"  ⚠️  Nalezeno {len(rule_anomalies)} anomálií:\n")
            for a in rule_anomalies:
                print(f"  [{a['pravidlo']}] Faktura #{a['id']}: {a['popis']}")
        else:
            print("  ✓ Žádné anomálie nenalezeny.")

    # Přístup 2: LLM
    if args.method in ("llm", "both"):
        print(f"\n{'='*60}")
        print(f"🤖 Přístup 2: LLM analýza ({args.model})")
        print("-" * 60)
        base_url = get_ollama_url()
        print(f"  Ollama: {base_url}\n")
        llm_result = llm_check(invoices, model=args.model, base_url=base_url)

    # Porovnání
    if args.method == "both":
        print(f"\n{'='*60}")
        print("📊 Porovnání přístupů:")
        print("-" * 60)
        print(f"  Pravidlový: {len(rule_anomalies)} anomálií nalezeno")
        print(f"  LLM:        viz výše (nestrukturovaný výstup)")
        print()
        print("  💡 Pravidlový přístup je deterministický a rychlý,")
        print("     ale zachytí jen předem definované vzory.")
        print("  💡 LLM může najít neočekávané vzory,")
        print("     ale není 100% spolehlivý na numerická data.")

    print(f"\n{'='*60}")
    print("✅ Hotovo!")


if __name__ == "__main__":
    main()
