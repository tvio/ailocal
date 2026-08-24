#!/usr/bin/env python3
"""UC3b – Extrakce sekcí z PDF pomocí OpenAI API (GPT-5.4 Nano).

Na rozdíl od demo03 (lokální Ollama + regex) toto demo:
  - Posílá CELÝ dokument do modelu (400k tokenů kontext)
  - Nepoužívá regex – model sám najde a extrahuje sekci
  - Ukládá do stejné DB tabulky s typem "openai(gpt-5.4-nano)"

GPT-5.4 Nano – specifikace:
  - Kontext: 400 000 tokenů (~300k znaků CZ textu)
  - Max output: 128 000 tokenů
  - Cena: $0.20 / 1M input tokenů, $1.25 / 1M output tokenů
  - Optimalizován pro: klasifikaci, extrakci dat, ranking
  - Počet parametrů: neveřejný (odhad ~8–15B, distilled z GPT-5.4)

Porovnání s lokálním gemma3:12b:
  | | gemma3:12b (lokální) | GPT-5.4 Nano (API) |
  |---|---|---|
  | Kontext | ~8k tokenů | 400k tokenů |
  | Přístup | regex + LLM čištění | celý dokument → LLM |
  | Rychlost | 10–30s/sekce | 1–3s/sekce |
  | Cena | 0 (vlastní HW) | ~$0.01 za dokument |
  | Offline | ano | ne (potřeba internetu) |

Použití:
  # Všechny sekce:
  uv run python demo03b_openai_extract.py SPC_0254048_PARALEN.pdf

  # Jen jedna sekce:
  uv run python demo03b_openai_extract.py SPC_0254048_PARALEN.pdf --section indikace

  # Bez ukládání do DB:
  uv run python demo03b_openai_extract.py SPC_0254048_PARALEN.pdf --no-save
"""

import sys
import argparse
import requests
from pathlib import Path

from common.config import PDF_DIR
from common.ollama_client import get_ollama_url, embed_text
from common.pdf_utils import extract_full_text
from common.db_postgres import get_connection, insert_extrakt, get_extrakty_stats

# --- Konfigurace ---
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
MODEL = "gpt-5.4-nano"
KEY_FILE = Path("key.yaml")

# SPC sekce – stejné jako v demo03
SECTION_LABELS = {
    "indikace": "Terapeutické indikace (4.1)",
    "kontraindikace": "Kontraindikace (4.3)",
    "davkovani": "Dávkování a způsob podání (4.2)",
    "vedlejsi_ucinky": "Nežádoucí účinky (4.8)",
    "interakce": "Interakce s jinými léčivými přípravky (4.5)",
    "slozeni": "Kvalitativní a kvantitativní složení (2)",
}


def load_api_key() -> str:
    """Načte OpenAI API klíč z key.yaml (formát key:hodnota)."""
    if not KEY_FILE.exists():
        print(f"Chyba: soubor '{KEY_FILE}' nenalezen.", file=sys.stderr)
        print("Vytvořte soubor key.yaml s obsahem: key:sk-proj-...", file=sys.stderr)
        sys.exit(1)
    text = KEY_FILE.read_text().strip()
    key = text.split("key:", 1)[-1].strip() if "key:" in text else ""
    if not key or not key.startswith("sk-"):
        print("Chyba: neplatný API klíč v key.yaml.", file=sys.stderr)
        sys.exit(1)
    return key


def extract_section_openai(full_text: str, section: str, *, api_key: str) -> str:
    """Extrahuje sekci z celého dokumentu pomocí OpenAI API.

    Posílá celý text dokumentu – žádný regex preprocessing.
    Model sám najde a extrahuje požadovanou sekci.
    """
    label = SECTION_LABELS.get(section.lower(), section)

    system = (
        "Jsi odborný asistent pro extrakci informací z farmaceutických SPC dokumentů. "
        "Tvým úkolem je z poskytnutého textu vytáhnout POUZE požadovanou sekci. "
        "Vrať kompletní text sekce bez nadpisu a bez číslování. "
        "Pokud sekci nenajdeš, vrať pouze slovo NENALEZENO."
    )

    prompt = f"""Z následujícího SPC dokumentu vytáhni kompletní obsah sekce „{label}".
Vrať pouze čistý text sekce, nic jiného.

{full_text}"""

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
    }

    resp = requests.post(OPENAI_API_URL, json=payload, headers=headers, timeout=60)
    resp.raise_for_status()

    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="UC3b – Extrakce sekcí z PDF pomocí OpenAI GPT-5.4 Nano"
    )
    parser.add_argument("pdf", help="Název PDF souboru (hledá se v data/pdf/)")
    parser.add_argument("--section", default=None, help="Jen konkrétní sekce (výchozí: všechny)")
    parser.add_argument("--no-save", action="store_true", help="Neukládat do DB (výchozí: ukládá)")
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
    sections_to_extract = [args.section] if args.section else list(SECTION_LABELS.keys())

    print("=" * 60)
    print("UC3b – Extrakce sekcí z PDF (OpenAI GPT-5.4 Nano)")
    print("=" * 60)
    print(f"\n📄 Soubor:  {pdf_path}")
    print(f"🔍 Sekce:   {', '.join(sections_to_extract)}")
    print(f"🤖 Model:   {MODEL}")
    print(f"💾 DB:      {'ano' if save else 'ne'}")

    # Načtení API klíče
    api_key = load_api_key()
    print(f"  ✓ API klíč načten ({api_key[:12]}...)")

    # Extrakce celého textu z PDF
    print("\nExtrahuji text z PDF...")
    full_text = extract_full_text(pdf_path)
    print(f"  ✓ {len(full_text):,} znaků extrahováno")

    typ_extraktu = f"openai({MODEL})"
    base_url = get_ollama_url()  # pro embedding (nomic-embed-text běží lokálně)

    # Extrakce sekcí
    print(f"\n{'='*60}")
    extracted = {}
    for section in sections_to_extract:
        try:
            result = extract_section_openai(full_text, section, api_key=api_key)

            # Validace
            refusal_markers = ["nenalezeno", "chybí", "nemám", "nemohu"]
            is_refusal = any(m in result.lower() for m in refusal_markers)

            if result and len(result.strip()) > 20 and not is_refusal:
                print(f"  ✓ [{section}] {len(result)} znaků")
                extracted[section] = result
                if save:
                    embed_input = result[:6000] if len(result) > 6000 else result
                    vec = embed_text(embed_input, base_url=base_url)
                    conn = get_connection()
                    insert_extrakt(
                        conn,
                        document_name=document_name,
                        typ_sekce=section,
                        typ_extraktu=typ_extraktu,
                        sekce_text=result,
                        sekce_vector=vec,
                    )
                    conn.close()
                    print(f"  💾 [{section}/{typ_extraktu}] Uloženo do DB ({len(vec)} dim)")
            else:
                reason = "odmítnutí" if is_refusal else "příliš krátká odpověď"
                print(f"  ✗ [{section}] {reason}")

        except requests.exceptions.HTTPError as e:
            print(f"  ✗ [{section}] HTTP chyba: {e}")
        except requests.exceptions.Timeout:
            print(f"  ✗ [{section}] Timeout (60s)")
        print()

    # Souhrn
    print("=" * 60)
    print(f"📊 Extrahováno {len(extracted)}/{len(sections_to_extract)} sekcí")
    for sec, text in extracted.items():
        print(f"  • {sec}: {len(text)} znaků")

    if save:
        conn = get_connection()
        stats = get_extrakty_stats(conn)
        conn.close()
        print(f"\n💾 Extrakty v DB: {len(stats)} záznamů")
        for s in stats:
            print(f"  • {s['document_name']} / {s['typ_sekce']} / {s['typ_extraktu']}: {s['sekce_len']} znaků")

    print(f"\n✅ Hotovo!")


if __name__ == "__main__":
    main()
