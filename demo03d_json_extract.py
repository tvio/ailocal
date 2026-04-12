#!/usr/bin/env python3
"""UC3d – Strukturovaná extrakce sekcí z PDF do JSON.

Extrahuje sekce z SPC dokumentu do fixovaného JSON formátu.
Rozpoznává tabulky v sekcích a ukládá je strukturovaně.

Dva režimy:
  1. OpenAI (GPT-5.4 Nano) – response_format s JSON schema, celý dokument
  2. Lokální (Ollama gemma3:12b) – regex preprocessing + JSON mode

Výstup se ukládá do tabulky extrakty_json (JSONB sloupec).

JSON schema výstupu:
  {
    "section_id": "4.8",
    "section_name": "Nežádoucí účinky",
    "has_table": true,
    "text_content": "Souhrn nežádoucích účinků...",
    "tables": [
      {
        "title": "Frekvence nežádoucích účinků",
        "headers": ["Orgánový systém", "Velmi časté", "Časté"],
        "rows": [["Poruchy nervového systému", "bolest hlavy", "závrať"]]
      }
    ]
  }

Použití:
  # OpenAI – všechny sekce:
  uv run python demo03d_json_extract.py SPC_0254048_PARALEN.pdf --mode openai

  # Lokální – všechny sekce:
  uv run python demo03d_json_extract.py SPC_0254048_PARALEN.pdf --mode local

  # Oba režimy najednou:
  uv run python demo03d_json_extract.py SPC_0254048_PARALEN.pdf --mode both

  # Jen jedna sekce, bez DB:
  uv run python demo03d_json_extract.py SPC_0254048_PARALEN.pdf --section vedlejsi_ucinky --no-save
"""

import json
import sys
import argparse
import requests
from pathlib import Path

from common.config import MODEL_CHAT, PDF_DIR
from common.ollama_client import get_ollama_url, chat
from common.pdf_utils import extract_full_text
from common.db_postgres import get_connection, insert_extrakt_json, get_extrakty_json_stats

# --- Konfigurace ---
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_MODEL = "gpt-5.4-nano"
KEY_FILE = Path("key.yaml")

# SPC sekce s čísly
SECTION_LABELS = {
    "indikace": ("4.1", "Terapeutické indikace"),
    "kontraindikace": ("4.3", "Kontraindikace"),
    "davkovani": ("4.2", "Dávkování a způsob podání"),
    "vedlejsi_ucinky": ("4.8", "Nežádoucí účinky"),
    "interakce": ("4.5", "Interakce s jinými léčivými přípravky"),
    "slozeni": ("2", "Kvalitativní a kvantitativní složení"),
}

# JSON schema pro response_format (OpenAI)
SECTION_JSON_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "spc_section",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "section_id": {"type": "string", "description": "Číslo sekce (např. 4.1, 4.8)"},
                "section_name": {"type": "string", "description": "Název sekce"},
                "has_table": {"type": "boolean", "description": "Obsahuje sekce tabulku?"},
                "text_content": {"type": "string", "description": "Textový obsah sekce (bez tabulek)"},
                "tables": {
                    "type": "array",
                    "description": "Tabulky nalezené v sekci",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string", "description": "Název/popis tabulky"},
                            "headers": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Záhlaví sloupců",
                            },
                            "rows": {
                                "type": "array",
                                "items": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "description": "Řádky tabulky",
                            },
                        },
                        "required": ["title", "headers", "rows"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["section_id", "section_name", "has_table", "text_content", "tables"],
            "additionalProperties": False,
        },
    },
}

SYSTEM_PROMPT = (
    "Jsi odborný asistent pro extrakci informací z farmaceutických SPC dokumentů. "
    "Tvým úkolem je z poskytnutého textu vytáhnout požadovanou sekci a vrátit ji "
    "jako strukturovaný JSON. "
    "Pokud sekce obsahuje tabulku (frekvence, dávkování apod.), rozpoznej ji "
    "a ulož do pole 'tables' se záhlavím a řádky. "
    "Text mimo tabulky ulož do 'text_content'. "
    "Pokud tabulka neexistuje, nastav has_table=false a tables=[]. "
    "Pokud sekci nenajdeš, vrať text_content='NENALEZENO' a has_table=false."
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


def make_prompt(section_key: str, full_text: str) -> str:
    """Vytvoří prompt pro extrakci sekce."""
    sec_id, sec_name = SECTION_LABELS[section_key]
    return f"""Z následujícího SPC dokumentu vytáhni sekci „{sec_id} {sec_name}" jako strukturovaný JSON.

Pravidla:
- section_id = "{sec_id}"
- section_name = "{sec_name}"
- Pokud sekce obsahuje tabulku, rozlož ji na headers + rows.
- Text mimo tabulky dej do text_content.
- Vrať POUZE validní JSON, nic jiného.

--- SPC DOKUMENT ---
{full_text}
--- KONEC ---"""


def extract_section_openai(full_text: str, section_key: str, *, api_key: str) -> dict | None:
    """Extrahuje sekci přes OpenAI API s vynuceným JSON schema."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": make_prompt(section_key, full_text)},
        ],
        "temperature": 0,
        "response_format": SECTION_JSON_SCHEMA,
    }

    resp = requests.post(OPENAI_API_URL, json=payload, headers=headers, timeout=90)
    resp.raise_for_status()

    content = resp.json()["choices"][0]["message"]["content"]
    return json.loads(content)


def extract_section_local(text: str, section_key: str, *, model: str, base_url: str) -> dict | None:
    """Extrahuje sekci lokálním modelem s regex preprocessingem + JSON mode.

    Lokální model dostane regex výřez (ne celý dokument) a instrukci
    vrátit JSON. Ollama JSON mode zajistí validní JSON výstup.
    """
    # Regex preprocessing – použijeme extract_section_regex z demo03
    from demo03_pdf_section_extract import extract_section_regex

    raw = extract_section_regex(text, section_key)
    if not raw:
        return None

    sec_id, sec_name = SECTION_LABELS[section_key]

    prompt = f"""Přepiš následující text sekce SPC dokumentu jako strukturovaný JSON.

Požadovaný formát:
{{
  "section_id": "{sec_id}",
  "section_name": "{sec_name}",
  "has_table": true/false,
  "text_content": "text mimo tabulky",
  "tables": [
    {{
      "title": "název tabulky",
      "headers": ["sloupec1", "sloupec2"],
      "rows": [["hodnota1", "hodnota2"]]
    }}
  ]
}}

Pokud text neobsahuje tabulku, nastav has_table=false a tables=[].
Vrať POUZE validní JSON.

--- TEXT SEKCE ---
{raw}
--- KONEC ---"""

    # Ollama JSON mode
    url = base_url or get_ollama_url()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "format": "json",
        "options": {"num_ctx": 8192},
    }

    resp = requests.post(f"{url}/api/chat", json=payload, stream=False, timeout=120)
    resp.raise_for_status()
    content = resp.json()["message"]["content"]

    return json.loads(content)


def validate_result(result: dict) -> bool:
    """Kontrola, že JSON má požadovanou strukturu a není odmítnutí."""
    if not isinstance(result, dict):
        return False
    if "text_content" not in result:
        return False
    text = result.get("text_content", "")
    if not text or text.strip() == "NENALEZENO" or len(text.strip()) < 20:
        return False
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="UC3d – Strukturovaná extrakce sekcí z PDF do JSON"
    )
    parser.add_argument("pdf", help="Název PDF souboru (hledá se v data/pdf/)")
    parser.add_argument("--section", default=None, help="Jen konkrétní sekce (výchozí: všechny)")
    parser.add_argument("--mode", default="both", choices=["openai", "local", "both"],
                        help="Režim extrakce (výchozí: both)")
    parser.add_argument("--model", default=MODEL_CHAT, help=f"Lokální model (výchozí {MODEL_CHAT})")
    parser.add_argument("--no-save", action="store_true", help="Neukládat do DB")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        pdf_path = PDF_DIR / args.pdf
    if not pdf_path.exists():
        print(f"Chyba: soubor '{args.pdf}' nenalezen (ani v {PDF_DIR}/).", file=sys.stderr)
        sys.exit(1)

    document_name = pdf_path.stem
    save = not args.no_save
    sections = [args.section] if args.section else list(SECTION_LABELS.keys())
    modes = ["openai", "local"] if args.mode == "both" else [args.mode]

    print("=" * 60)
    print("UC3d – Strukturovaná extrakce sekcí do JSON")
    print("=" * 60)
    print(f"\n📄 Soubor:  {pdf_path}")
    print(f"🔍 Sekce:   {', '.join(sections)}")
    print(f"⚙️  Režim:   {args.mode}")
    print(f"💾 DB:      {'ano' if save else 'ne'}")

    # Extrakce textu
    print("\nExtrahuji text z PDF...")
    full_text = extract_full_text(pdf_path)
    print(f"  ✓ {len(full_text):,} znaků extrahováno")

    api_key = None
    if "openai" in modes:
        api_key = load_api_key()
        print(f"  ✓ OpenAI API klíč načten")

    base_url = get_ollama_url()
    if "local" in modes:
        print(f"  ✓ Ollama: {base_url}")

    # Extrakce
    total = 0
    success = 0
    for mode in modes:
        typ_modelu = f"openai({OPENAI_MODEL})" if mode == "openai" else f"ollama({args.model})"
        print(f"\n{'='*60}")
        print(f"🤖 {typ_modelu}")
        print(f"{'='*60}")

        for section in sections:
            total += 1
            sec_id, sec_name = SECTION_LABELS[section]
            try:
                if mode == "openai":
                    result = extract_section_openai(full_text, section, api_key=api_key)
                else:
                    result = extract_section_local(
                        full_text, section, model=args.model, base_url=base_url,
                    )

                if result and validate_result(result):
                    has_table = result.get("has_table", False)
                    tables = result.get("tables", [])
                    text_len = len(result.get("text_content", ""))
                    table_info = f", {len(tables)} tabulek" if has_table else ""
                    print(f"  ✓ [{section}] {text_len} zn. textu{table_info}")

                    if save:
                        conn = get_connection()
                        insert_extrakt_json(
                            conn,
                            document_name=document_name,
                            typ_sekce=section,
                            typ_modelu=typ_modelu,
                            sekce_json=result,
                        )
                        conn.close()
                        print(f"  💾 [{section}/{typ_modelu}] Uloženo do DB")

                    success += 1

                    # Ukázka JSON (zkrácená)
                    preview = json.dumps(result, ensure_ascii=False, indent=2)
                    if len(preview) > 300:
                        preview = preview[:300] + "\n    ..."
                    print(f"  📋 {preview}")
                else:
                    print(f"  ✗ [{section}] Nenalezeno nebo nevalidní JSON")

            except json.JSONDecodeError as e:
                print(f"  ✗ [{section}] Nevalidní JSON: {e}")
            except requests.exceptions.HTTPError as e:
                print(f"  ✗ [{section}] HTTP chyba: {e}")
            except requests.exceptions.Timeout:
                print(f"  ✗ [{section}] Timeout")
            except Exception as e:
                print(f"  ✗ [{section}] Chyba: {e}")
            print()

    # Souhrn
    print("=" * 60)
    print(f"📊 Úspěšně extrahováno: {success}/{total}")

    if save:
        conn = get_connection()
        stats = get_extrakty_json_stats(conn)
        conn.close()
        if stats:
            print(f"\n💾 JSON extrakty v DB: {len(stats)} záznamů")
            for s in stats:
                table_info = f", {s['table_count']} tab." if s.get('table_count') else ""
                print(f"  • {s['document_name']} / {s['typ_sekce']} / {s['typ_modelu']}: "
                      f"{s.get('text_len', '?')} zn.{table_info}")

    print(f"\n✅ Hotovo!")


if __name__ == "__main__":
    main()
