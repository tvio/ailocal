#!/usr/bin/env python3
"""UC10 – Sumarizace zápisu z porady.

Z nestrukturovaného zápisu vytvoří strukturované shrnutí
s rozhodnutími, úkoly a otevřenými otázkami.

Použití:
  uv run python demo10_meeting_summary.py
  uv run python demo10_meeting_summary.py data/meetings/porada.txt
  uv run python demo10_meeting_summary.py --format json
"""

import sys
import json
import argparse
from pathlib import Path

from common.config import MODEL_CHAT
from common.ollama_client import get_ollama_url, chat


# Ukázkový zápis z porady (pokud uživatel nemá vlastní)
SAMPLE_MEETING = """\
Zápis z týmové porady – Projekt Alfa
Datum: 15.3.2026, 10:00–11:30
Účastníci: Jan Novák (vedoucí), Petra Svobodová (analytik), Martin Dvořák (vývojář), \
Lucie Černá (tester), Tomáš Horák (architekt)

Jan zahájil poradu a shrnul stav projektu. Říkal, že jsme pozadu oproti plánu asi o 2 týdny, \
hlavně kvůli zpoždění na backendu. Martin vysvětloval, že měl problémy s integrací nového API \
od dodavatele – dokumentace byla neúplná a musel se tím prokousávat sám. Tomáš navrhl, že by \
mohl pomoci s architekturou API wrapperu, aby se to zrychlilo.

Petra představila výsledky analýzy požadavků od zákazníka. Zákazník chce přidat modul pro \
reportování, který v původním zadání nebyl. Jan řekl, že to musíme probrat se zákazníkem \
na dalším callu a zjistit priority. Petra slíbila, že připraví odhad náročnosti do pátku.

Lucie hlásila, že automatické testy pokrývají zatím jen 40% kódu. Potřebuje od Martina \
API specifikaci, aby mohla dopsat integrační testy. Martin slíbil, že jí pošle Swagger \
dokumentaci do středy.

Diskutovali jsme o tom, jestli přejít na novou verzi frameworku (React 20). Tomáš je pro, \
říká že to zjednoduší práci s komponenty. Martin je proti, bojí se regresí. Jan rozhodl, \
že to zatím odložíme na fázi 2 a teď se soustředíme na dodání MVP.

Na konci Jan zmínil, že příští týden je firemní hackathon a kdo chce, může se přihlásit. \
Deadline přihlášek je v pondělí.

Příští porada: 22.3.2026, 10:00
"""

SUMMARY_SYSTEM_MD = """\
Jsi asistent pro zpracování zápisů z porad. Z nestrukturovaného textu vytvoříš přehledné shrnutí.

Formát výstupu (Markdown):

# Shrnutí porady
- **Datum:**
- **Účastníci:**
- **Hlavní téma:**

## Klíčová rozhodnutí
- (rozhodnutí 1)
- (rozhodnutí 2)

## Úkoly
| Kdo | Co | Termín |
|-----|-----|--------|
| ... | ... | ...    |

## Otevřené otázky
- (otázka 1)

## Rizika / varování
- (pokud existují)
"""

SUMMARY_SYSTEM_JSON = """\
Jsi asistent pro zpracování zápisů z porad. Z nestrukturovaného textu vytvoříš strukturovaný JSON.

Vrať POUZE validní JSON v tomto formátu:
{
  "datum": "...",
  "ucastnici": ["..."],
  "hlavni_tema": "...",
  "rozhodnuti": ["..."],
  "ukoly": [
    {"kdo": "...", "co": "...", "termin": "..."}
  ],
  "otevrene_otazky": ["..."],
  "rizika": ["..."],
  "pristi_porada": "..."
}
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="UC10 – Sumarizace zápisu z porady"
    )
    parser.add_argument("input", nargs="?", help="Cesta k textovému souboru se zápisem")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown", help="Formát výstupu")
    parser.add_argument("--model", default=MODEL_CHAT, help=f"Model (výchozí {MODEL_CHAT})")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Načtení zápisu
    if args.input:
        input_path = Path(args.input)
        if not input_path.exists():
            print(f"Chyba: soubor '{input_path}' neexistuje.", file=sys.stderr)
            sys.exit(1)
        meeting_text = input_path.read_text(encoding="utf-8")
        source = input_path.name
    else:
        meeting_text = SAMPLE_MEETING
        source = "vestavěný ukázkový zápis"
        print("ℹ️  Používám vestavěný ukázkový zápis z porady")

    print("=" * 60)
    print("UC10 – Sumarizace zápisu z porady")
    print("=" * 60)
    print(f"\n📄 Zdroj:   {source}")
    print(f"📝 Délka:   {len(meeting_text):,} znaků")
    print(f"📋 Formát:  {args.format}")
    print(f"🤖 Model:   {args.model}")

    # Výběr systémového promptu
    system = SUMMARY_SYSTEM_JSON if args.format == "json" else SUMMARY_SYSTEM_MD

    prompt = f"""Zpracuj následující zápis z porady a vytvoř strukturované shrnutí.

--- ZÁPIS ---
{meeting_text}
--- KONEC ZÁPISU ---

Strukturované shrnutí:"""

    base_url = get_ollama_url()
    print(f"  ✓ Ollama dostupná na {base_url}")

    print(f"\n⏳ Zpracovávám zápis...\n")
    print("-" * 60)
    result = chat(prompt, system=system, model=args.model, base_url=base_url, stream=True)

    # Pokud je JSON formát, zkusíme validovat
    if args.format == "json":
        try:
            start = result.find("{")
            end = result.rfind("}") + 1
            if start >= 0 and end > start:
                parsed = json.loads(result[start:end])
                print("\n\n✓ JSON je validní")
                if parsed.get("ukoly"):
                    print(f"\n📋 Nalezeno {len(parsed['ukoly'])} úkolů:")
                    for task in parsed["ukoly"]:
                        print(f"   → {task.get('kdo', '?')}: {task.get('co', '?')} (do {task.get('termin', '?')})")
        except json.JSONDecodeError:
            print("\n\n⚠️  JSON odpověď se nepodařilo validovat")

    print(f"\n{'='*60}")
    print("✅ Hotovo!")


if __name__ == "__main__":
    main()
