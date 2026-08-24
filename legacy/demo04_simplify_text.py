#!/usr/bin/env python3
"""UC4 – Strukturované zjednodušení sekcí SPC dokumentu.

Převede odborný text z extrakty_json na strukturovaný JSON.
Každá sekce má vlastní schéma – krátké položky, pole, kategorie.
Zdroj: extrakty_json (preferuje OpenAI zdroj).
Cíl: tabulka simplify (JSONB sloupec) v PostgreSQL.

Výstupní formáty per sekce:
  složení     → {"ucinne_latky": ["paracetamol 500 mg"]}
  indikace   → {"indikace": ["vysoký krevní tlak", ...]}
  kontraind. → {"kontraindikace": ["alergie na složky", ...]}
  dávkování  → {"davkovani": [{"pacient":..., "davka":..., "frekvence":...}]}
  ved. účinky → {"vedlejsi_ucinky": [{"frekvence":..., "ucinek":...}]}
  interakce  → {"interakce": [{"latka":..., "efekt":...}]}

Použití:
  uv run python demo04_simplify_text.py SPC_0500896_IFIRMASTA.pdf
  uv run python demo04_simplify_text.py SPC_0254048_PARALEN --section vedlejsi_ucinky
  uv run python demo04_simplify_text.py SPC_0254048_PARALEN --mode openai
  uv run python demo04_simplify_text.py SPC_0254048_PARALEN --mode local
  uv run python demo04_simplify_text.py SPC_0254048_PARALEN --no-save
"""

import json
import sys
import subprocess
import argparse
import requests
from pathlib import Path

from common.config import MODEL_CHAT, OLLAMA_TIMEOUT
from common.ollama_client import get_ollama_url
from common.db_postgres import (
    get_connection, get_json_extracts, insert_simplify, get_simplify_stats,
)

# --- Konfigurace ---
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_MODEL = "gpt-5.4-nano"
KEY_FILE = Path("key.yaml")


# ---------------------------------------------------------------------------
# Per-section JSON schémata pro OpenAI response_format
# ---------------------------------------------------------------------------

SECTION_SCHEMAS = {
    "slozeni": {
        "type": "json_schema",
        "json_schema": {
            "name": "slozeni",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "ucinne_latky": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Seznam účinných látek s dávkou, např. 'paracetamol 500 mg'",
                    },
                },
                "required": ["ucinne_latky"],
                "additionalProperties": False,
            },
        },
    },
    "indikace": {
        "type": "json_schema",
        "json_schema": {
            "name": "indikace",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "indikace": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Krátké indikace pro laika, např. 'vysoký krevní tlak'",
                    },
                },
                "required": ["indikace"],
                "additionalProperties": False,
            },
        },
    },
    "kontraindikace": {
        "type": "json_schema",
        "json_schema": {
            "name": "kontraindikace",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "kontraindikace": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Zkrácené případy kontraindikací, např. 'alergie na složky'",
                    },
                },
                "required": ["kontraindikace"],
                "additionalProperties": False,
            },
        },
    },
    "davkovani": {
        "type": "json_schema",
        "json_schema": {
            "name": "davkovani",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "davkovani": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "pacient": {"type": "string", "description": "Typ pacienta, např. 'dospělí', 'děti 6–12 let'"},
                                "davka": {"type": "string", "description": "Velikost dávky, např. '500 mg'"},
                                "frekvence": {"type": "string", "description": "Jak často, např. '3–4x denně'"},
                                "poznamka": {"type": "string", "description": "Doplňující podmínka, např. 'max 4 g/den'"},
                            },
                            "required": ["pacient", "davka", "frekvence", "poznamka"],
                            "additionalProperties": False,
                        },
                        "description": "Dávkování pro různé typy pacientů",
                    },
                },
                "required": ["davkovani"],
                "additionalProperties": False,
            },
        },
    },
    "vedlejsi_ucinky": {
        "type": "json_schema",
        "json_schema": {
            "name": "vedlejsi_ucinky",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "vedlejsi_ucinky": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "frekvence": {"type": "string", "description": "Jak časté, např. 'časté', 'vzácné'"},
                                "ucinek": {"type": "string", "description": "Nežádoucí účinek pro laika, např. 'bolest hlavy'"},
                            },
                            "required": ["frekvence", "ucinek"],
                            "additionalProperties": False,
                        },
                        "description": "Seznam nežádoucích účinků s frekvencí",
                    },
                },
                "required": ["vedlejsi_ucinky"],
                "additionalProperties": False,
            },
        },
    },
    "interakce": {
        "type": "json_schema",
        "json_schema": {
            "name": "interakce",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "interakce": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "latka": {"type": "string", "description": "Název látky/léku"},
                                "efekt": {"type": "string", "description": "Krátký popis efektu interakce pro laika"},
                            },
                            "required": ["latka", "efekt"],
                            "additionalProperties": False,
                        },
                        "description": "Seznam interakcí s jinými látkami",
                    },
                },
                "required": ["interakce"],
                "additionalProperties": False,
            },
        },
    },
}

# Per-section system prompty
SECTION_PROMPTS = {
    "slozeni": (
        "Z textu sekce složení vytvoř JSON pole účinných látek (jen účinné látky, ne pomocné). "
        "Každá položka = název látky + dávka. Žádné věty, jen krátké položky. "
        "Příklad: ['paracetamol 500 mg', 'kofein 65 mg']"
    ),
    "indikace": (
        "Z textu sekce indikace vytvoř JSON pole krátkých indikací srozumitelných pro laika. "
        "Každá položka = 2–5 slov, jednoduchý český jazyk BEZ odborných termínů. "
        "Přelož odborné názvy: esenciální hypertenze → vysoký krevní tlak, diabetes mellitus → cukrovka. "
        "Příklad: ['vysoký krevní tlak', 'bolest hlavy', 'horečka']"
    ),
    "kontraindikace": (
        "Z textu sekce kontraindikace vytvoř JSON pole zkrácených případů, kdy se lék nesmí užívat. "
        "Každá položka = krátký srozumitelný důvod v laicém jazyce (hypersenzitivita → alergie). "
        "Příklad: ['alergie na složky', 'těhotství 2.+3. trimestr', 'těžké poškození jater']"
    ),
    "davkovani": (
        "Z textu sekce dávkování vytvoř JSON pole objektů pro různé typy pacientů. "
        "Každý objekt má: pacient, davka, frekvence, poznamka. "
        "Příklad: [{\"pacient\": \"dospělí\", \"davka\": \"500–1000 mg\", \"frekvence\": \"3–4x denně\", \"poznamka\": \"max 4 g/den\"}]"
    ),
    "vedlejsi_ucinky": (
        "Z textu sekce nežádoucí účinky vytvoř JSON pole objektů s frekvencí a názvem účinku. "
        "Použij srozumitelné české frekvence: velmi časté, časté, méně časté, vzácné, velmi vzácné. "
        "Názvy účinků piš jednoduše česky (trombocytopenie → nízké krevní destičky, hepatotoxicita → poškození jater). "
        "Příklad: [{\"frekvence\": \"vzácné\", \"ucinek\": \"kožní vyrážka\"}]"
    ),
    "interakce": (
        "Z textu sekce interakce vytvoř JSON pole objektů s názvem látky a krátkým popisem efektu. "
        "Efekt piš jednoduše česky, srozumitelně pro laika. Názvy látek ponech v originále. "
        "Příklad: [{\"latka\": \"ibuprofen\", \"efekt\": \"snižuje účinek léku na tlak\"}]"
    ),
}

SYSTEM_PROMPT = (
    "Jsi asistent pro strukturovanou extrakci informací z farmaceutických SPC dokumentů. "
    "Tvou úlohou je převést odborný text na krátké strukturované položky srozumitelné pro laika. "
    "VŽDY nahraď odborné lékařské termíny jednoduchými českými slovy "
    "(např. 'esenciální hypertenze' → 'vysoký krevní tlak', 'hepatální insuficience' → 'selhání jater'). "
    "Vrať POUZE validní JSON, žádný jiný text."
)


def load_api_key() -> str:
    """Načte OpenAI API klíč z key.yaml."""
    if not KEY_FILE.exists():
        print(f"Chyba: soubor '{KEY_FILE}' nenalezen.", file=sys.stderr)
        sys.exit(1)
    text = KEY_FILE.read_text().strip()
    key = text.split("key:", 1)[-1].strip() if "key:" in text else ""
    if not key or not key.startswith("sk-"):
        print("Chyba: neplatný API klíč v key.yaml.", file=sys.stderr)
        sys.exit(1)
    return key


def simplify_openai(sekce_json: dict, section: str, *, api_key: str) -> dict:
    """Strukturované zjednodušení přes OpenAI s vynuceným JSON schema."""
    section_prompt = SECTION_PROMPTS.get(section, "Vytvoř JSON se strukturovaným obsahem sekce.")
    prompt = f"""{section_prompt}

--- STRUKTUROVANÝ JSON SEKCE ---
{json.dumps(sekce_json, ensure_ascii=False, indent=2)}
--- KONEC ---"""

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
        "response_format": SECTION_SCHEMAS[section],
    }
    resp = requests.post(OPENAI_API_URL, json=payload, headers=headers, timeout=60)
    resp.raise_for_status()
    return json.loads(resp.json()["choices"][0]["message"]["content"])


def simplify_local(sekce_json: dict, section: str, *, model: str, base_url: str) -> dict:
    """Strukturované zjednodušení lokálním modelem s Ollama JSON mode."""
    section_prompt = SECTION_PROMPTS.get(section, "Vytvoř JSON se strukturovaným obsahem sekce.")
    prompt = f"""{section_prompt}

--- STRUKTUROVANÝ JSON SEKCE ---
{json.dumps(sekce_json, ensure_ascii=False, indent=2)}
--- KONEC ---

Vrať POUZE validní JSON."""

    url = base_url or get_ollama_url()
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "format": "json",
    }
    resp = requests.post(f"{url}/api/chat", json=payload, stream=False, timeout=OLLAMA_TIMEOUT)
    resp.raise_for_status()
    return json.loads(resp.json()["message"]["content"])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="UC4 – Strukturované zjednodušení sekcí SPC dokumentu"
    )
    parser.add_argument("document", help="Název dokumentu (nebo PDF soubor)")
    parser.add_argument("--section", default=None, help="Jen konkrétní sekce (výchozí: všechny)")
    parser.add_argument("--source", default=None,
                        help="Zdroj JSON extrakcí – typ_modelu v extrakty_json (výchozí: openai*)")
    parser.add_argument("--mode", default="both", choices=["openai", "local", "both"],
                        help="Režim zjednodušení (výchozí: both)")
    parser.add_argument("--model", default=MODEL_CHAT, help=f"Lokální model (výchozí {MODEL_CHAT})")
    parser.add_argument("--no-save", action="store_true", help="Neukládat do DB")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    save = not args.no_save
    modes = ["openai", "local"] if args.mode == "both" else [args.mode]

    # Normalizace: odstraní .pdf příponu
    document_name = args.document
    if document_name.lower().endswith(".pdf"):
        document_name = document_name[:-4]

    print("=" * 60)
    print("UC4 – Strukturované zjednodušení sekcí")
    print("=" * 60)

    # --- Načtení zdrojových extrakcí z DB ---
    conn = get_connection()
    extracts = get_json_extracts(
        conn,
        document_name=document_name,
        typ_modelu=args.source,
    )
    conn.close()

    if not extracts:
        conn = get_connection()
        all_extracts = get_json_extracts(conn, document_name=document_name)
        conn.close()
        if all_extracts:
            openai_extracts = [e for e in all_extracts if "openai" in e["typ_modelu"]]
            extracts = openai_extracts or all_extracts
        else:
            # Auto-fallback: spustit demo03d extrakci automaticky
            pdf_path = Path("data/pdf") / f"{document_name}.pdf"
            if not pdf_path.exists():
                print(f"Chyba: žádné JSON extrakce pro '{document_name}' a PDF '{pdf_path}' neexistuje.", file=sys.stderr)
                sys.exit(1)

            print(f"\n⚠️  Žádné extrakce v DB – spouštím automatickou extrakci (demo03d, OpenAI)...")
            print(f"   PDF: {pdf_path}")
            result = subprocess.run(
                [sys.executable, "demo03d_json_extract.py", str(pdf_path), "--mode", "openai"],
                capture_output=False,
            )
            if result.returncode != 0:
                print(f"Chyba: demo03d selhalo (exit code {result.returncode}).", file=sys.stderr)
                sys.exit(1)

            # Znovu načíst extrakce z DB
            print(f"\n{'='*60}")
            print("Pokračuji se zjednodušením...")
            conn = get_connection()
            extracts = get_json_extracts(conn, document_name=document_name)
            conn.close()
            if not extracts:
                print(f"Chyba: extrakce stále chybí po demo03d.", file=sys.stderr)
                sys.exit(1)
            openai_extracts = [e for e in extracts if "openai" in e["typ_modelu"]]
            if openai_extracts:
                extracts = openai_extracts

    # Filtr na konkrétní sekci
    if args.section:
        extracts = [e for e in extracts if e["typ_sekce"] == args.section]
        if not extracts:
            print(f"Chyba: sekce '{args.section}' nenalezena pro '{document_name}'.", file=sys.stderr)
            sys.exit(1)

    # Preferovat OpenAI zdroj pokud není explicitně zadáno
    if not args.source:
        openai_extracts = [e for e in extracts if "openai" in e["typ_modelu"]]
        if openai_extracts:
            extracts = openai_extracts

    # Deduplikace – jedna sekce na document
    seen = set()
    unique_extracts = []
    for e in extracts:
        key = (e["document_name"], e["typ_sekce"])
        if key not in seen:
            seen.add(key)
            unique_extracts.append(e)
    extracts = unique_extracts

    zdroj_modelu = extracts[0]["typ_modelu"] if extracts else "?"
    print(f"\n📄 Dokument: {document_name}")
    print(f"📦 Zdroj:    {zdroj_modelu} (extrakty_json)")
    print(f"🔍 Sekce:    {', '.join(e['typ_sekce'] for e in extracts)}")
    print(f"⚙️  Režim:    {args.mode}")
    print(f"💾 DB:       {'ano' if save else 'ne'}")

    api_key = None
    if "openai" in modes:
        api_key = load_api_key()
        print(f"  ✓ OpenAI API klíč načten")

    base_url = get_ollama_url()
    if "local" in modes:
        print(f"  ✓ Ollama: {base_url}")

    total = 0
    success = 0

    for extract in extracts:
        section = extract["typ_sekce"]
        sekce_json = extract["sekce_json"]
        zdroj = extract["typ_modelu"]

        text_content = sekce_json.get("text_content", "")
        has_table = sekce_json.get("has_table", False)
        if not text_content or len(text_content.strip()) < 20:
            print(f"\n  ✗ [{section}] Prázdný text_content, přeskakuji")
            continue

        source_preview = json.dumps(sekce_json, ensure_ascii=False)
        print(f"\n{'='*60}")
        print(f"📋 Sekce: {section} (has_table={has_table}, {len(source_preview)} znaků JSON)")
        print(f"   Zdroj: {zdroj}")

        for mode in modes:
            total += 1
            typ_modelu = f"openai({OPENAI_MODEL})" if mode == "openai" else f"ollama({args.model})"
            try:
                print(f"\n  🤖 {typ_modelu}...")
                if mode == "openai":
                    result = simplify_openai(sekce_json, section, api_key=api_key)
                else:
                    result = simplify_local(sekce_json, section, model=args.model, base_url=base_url)

                if result and isinstance(result, dict):
                    # Spočítat položky ve výsledku
                    key = list(result.keys())[0] if result else "?"
                    items = result.get(key, [])
                    count = len(items) if isinstance(items, list) else 1

                    print(f"  ✓ [{section}/{typ_modelu}] {count} položek")
                    print(f"  📋 {json.dumps(result, ensure_ascii=False, indent=2)[:600]}")

                    if save:
                        conn = get_connection()
                        insert_simplify(
                            conn,
                            document_name=extract["document_name"],
                            typ_sekce=section,
                            typ_modelu=typ_modelu,
                            zdroj_modelu=zdroj,
                            source_json=sekce_json,
                            simplified_json=result,
                        )
                        conn.close()
                        print(f"  💾 Uloženo do DB")

                    success += 1
                else:
                    print(f"  ✗ [{section}/{typ_modelu}] Nevalidní výstup")

            except json.JSONDecodeError as e:
                print(f"  ✗ [{section}/{typ_modelu}] Nevalidní JSON: {e}")
            except requests.exceptions.HTTPError as e:
                print(f"  ✗ [{section}/{typ_modelu}] HTTP chyba: {e}")
            except Exception as e:
                print(f"  ✗ [{section}/{typ_modelu}] Chyba: {e}")

    # Souhrn
    print(f"\n{'='*60}")
    print(f"📊 Zjednodušeno: {success}/{total}")

    if save:
        conn = get_connection()
        stats = get_simplify_stats(conn)
        conn.close()
        if stats:
            print(f"\n💾 Simplify v DB: {len(stats)} záznamů")
            for s in stats:
                print(f"  • {s['document_name']} / {s['typ_sekce']} / {s['typ_modelu']}: "
                      f"source {s['source_len']} zn. → simplified {s['json_len']} zn.")

    print(f"\n✅ Hotovo!")


if __name__ == "__main__":
    main()
