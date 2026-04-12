#!/usr/bin/env python3
"""UC9 – Klasifikace e-mailů / tiketů.

Automatická kategorizace příchozích požadavků do předdefinovaných kategorií.
Zero-shot i few-shot přístup.

Použití:
  uv run python demo09_classify_tickets.py
  uv run python demo09_classify_tickets.py --method few-shot
  uv run python demo09_classify_tickets.py --input data/emails/tikety.json
"""

import sys
import json
import argparse
from pathlib import Path

from common.config import MODEL_CHAT
from common.ollama_client import get_ollama_url, chat


# Předdefinované kategorie pro helpdesk
CATEGORIES = [
    "hardware",
    "software",
    "síť/připojení",
    "přístupy/oprávnění",
    "tiskárna",
    "e-mail",
    "jiné",
]

PRIORITIES = ["nízká", "střední", "vysoká", "kritická"]

# Ukázkové tikety (pokud uživatel nemá vlastní data)
SAMPLE_TICKETS = [
    {
        "id": 1,
        "subject": "Nefunguje mi tiskárna na 3. patře",
        "body": "Dobrý den, od rána nemůžu tisknout na sdílené tiskárně HP LaserJet na 3. patře. "
                "Svítí červená kontrolka a na displeji je hlášení Paper Jam. Potřebuji urgentně vytisknout smlouvy.",
    },
    {
        "id": 2,
        "subject": "Potřebuji přístup do SAP",
        "body": "Dobrý den, nastoupil jsem minulý týden na pozici účetní a stále nemám přístup do systému SAP. "
                "Moje nadřízená paní Nováková říkala, že by to mělo být hotové do pátku. Děkuji.",
    },
    {
        "id": 3,
        "subject": "Notebook se pořád vypíná",
        "body": "Můj služební notebook Dell Latitude se posledních pár dní náhodně vypíná, "
                "většinou při videohovorech v Teams. Žádná chybová hláška, prostě se vypne. "
                "Ventilátory jedou naplno. Myslím, že se přehřívá.",
    },
    {
        "id": 4,
        "subject": "Nemůžu se připojit k VPN",
        "body": "Od aktualizace Windows včera večer mi nefunguje VPN. Pořád hlásí 'Connection timeout'. "
                "Z domova se nemůžu dostat na firemní disky ani do intranetu. Zkoušel jsem restart.",
    },
    {
        "id": 5,
        "subject": "Outlook neposílá e-maily s přílohou",
        "body": "Když zkusím poslat e-mail s přílohou větší než cca 5 MB, Outlook hlásí chybu a zpráva zůstane "
                "v Outboxu. Bez přílohy to funguje normálně. Potřebuji poslat prezentaci klientovi.",
    },
    {
        "id": 6,
        "subject": "Prosba o instalaci Adobe Acrobat",
        "body": "Dobrý den, v rámci nového projektu potřebuji editovat PDF soubory. "
                "Mohl bych dostat nainstalovaný Adobe Acrobat Pro? Případně jinou alternativu. Děkuji.",
    },
    {
        "id": 7,
        "subject": "Podezřelý e-mail od ředitele",
        "body": "Dostal jsem e-mail údajně od ředitele s žádostí o urgentní převod peněz. "
                "Adresa odesílatele vypadá podezřele – je tam gmail místo firemní domény. "
                "Neklikal jsem na žádný odkaz. Co mám dělat?",
    },
]

ZERO_SHOT_SYSTEM = f"""\
Jsi IT helpdesk klasifikátor. Analyzuj příchozí tiket a vrať JSON odpověď.

Dostupné kategorie: {', '.join(CATEGORIES)}
Dostupné priority: {', '.join(PRIORITIES)}

Vrať POUZE validní JSON v tomto formátu:
{{
  "kategorie": "jedna z dostupných kategorií",
  "priorita": "jedna z dostupných priorit",
  "shrnutí": "stručné shrnutí problému (max 20 slov)",
  "doporučení": "stručné doporučení dalšího postupu"
}}
"""

FEW_SHOT_EXAMPLES = """
Příklad 1:
Předmět: Monitor bliká
Tělo: Můj monitor na pracovišti občas problikne, hlavně při otevření Excelu.
Odpověď: {"kategorie": "hardware", "priorita": "nízká", "shrnutí": "Problikávání monitoru při práci v Excelu", "doporučení": "Zkontrolovat kabel a ovladače grafické karty"}

Příklad 2:
Předmět: Nemůžu se přihlásit do systému
Tělo: Po změně hesla se nemůžu přihlásit do CRM systému. Heslo jsem měnil včera a do Windows se přihlásím normálně.
Odpověď: {"kategorie": "přístupy/oprávnění", "priorita": "vysoká", "shrnutí": "Nelze se přihlásit do CRM po změně hesla", "doporučení": "Reset hesla v CRM, synchronizace s AD"}

"""


def classify_ticket(ticket: dict, *, method: str, model: str, base_url: str) -> dict:
    """Klasifikuje jeden tiket. Vrátí strukturovanou odpověď."""
    if method == "few-shot":
        system = ZERO_SHOT_SYSTEM + "\n\nPříklady klasifikace:\n" + FEW_SHOT_EXAMPLES
    else:
        system = ZERO_SHOT_SYSTEM

    prompt = f'Předmět: {ticket["subject"]}\nTělo: {ticket["body"]}'

    response = chat(prompt, system=system, model=model, base_url=base_url)

    # Pokus o parsování JSON z odpovědi
    try:
        # Hledáme JSON v odpovědi (model může přidat text kolem)
        start = response.find("{")
        end = response.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(response[start:end])
    except json.JSONDecodeError:
        pass

    return {"raw_response": response, "parse_error": True}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="UC9 – Klasifikace e-mailů / tiketů"
    )
    parser.add_argument("--input", help="JSON soubor s tikety")
    parser.add_argument("--method", choices=["zero-shot", "few-shot"], default="zero-shot")
    parser.add_argument("--model", default=MODEL_CHAT, help=f"Model (výchozí {MODEL_CHAT})")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Načtení tiketů
    if args.input:
        input_path = Path(args.input)
        if not input_path.exists():
            print(f"Chyba: soubor '{input_path}' neexistuje.", file=sys.stderr)
            sys.exit(1)
        tickets = json.loads(input_path.read_text(encoding="utf-8"))
    else:
        tickets = SAMPLE_TICKETS
        print("ℹ️  Používám vestavěné ukázkové tikety (7 ks)")

    print("=" * 60)
    print("UC9 – Klasifikace e-mailů / tiketů")
    print("=" * 60)
    print(f"\n🤖 Model:   {args.model}")
    print(f"⚙️  Metoda:  {args.method}")
    print(f"📨 Tiketů:  {len(tickets)}")

    base_url = get_ollama_url()
    print(f"  ✓ Ollama dostupná na {base_url}\n")

    results = []
    for i, ticket in enumerate(tickets, 1):
        print(f"[{i}/{len(tickets)}] 📨 {ticket['subject']}")
        classification = classify_ticket(
            ticket, method=args.method, model=args.model, base_url=base_url,
        )
        results.append({"ticket_id": ticket.get("id", i), **classification})

        if "parse_error" in classification:
            print(f"  ⚠️  Nepodařilo se parsovat JSON:")
            print(f"     {classification.get('raw_response', '')[:150]}")
        else:
            print(f"  📁 Kategorie: {classification.get('kategorie', '?')}")
            print(f"  🔴 Priorita:  {classification.get('priorita', '?')}")
            print(f"  📝 Shrnutí:   {classification.get('shrnutí', '?')}")
        print()

    # Souhrnná tabulka
    print("=" * 60)
    print("📊 Souhrnná tabulka:")
    print("-" * 60)
    print(f"{'ID':<4} {'Kategorie':<20} {'Priorita':<12} {'Shrnutí'}")
    print("-" * 60)
    for r in results:
        tid = r.get("ticket_id", "?")
        cat = r.get("kategorie", "?")
        pri = r.get("priorita", "?")
        summ = r.get("shrnutí", r.get("raw_response", "?"))[:40]
        print(f"{tid:<4} {cat:<20} {pri:<12} {summ}")

    print(f"\n✅ Hotovo! Klasifikováno {len(results)} tiketů.")


if __name__ == "__main__":
    main()
