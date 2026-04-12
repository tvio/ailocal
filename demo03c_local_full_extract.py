#!/usr/bin/env python3
"""UC3c – Extrakce sekcí z PDF lokálním modelem BEZ regexu.

Na rozdíl od demo03 (regex + LLM čištění) toto demo:
  - Posílá CELÝ dokument do lokálního modelu (Ollama)
  - Nepoužívá regex – model sám najde a extrahuje sekci
  - Ukládá do stejné DB tabulky s typem "ollama-full({model})"

Účel: Porovnání s demo03 (regex+LLM) a demo03b (OpenAI API).
Ukázka limitů lokálního modelu na velkém kontextu.

⚠️  Na 12 GB VRAM s gemma3:12b a num_ctx=8192 se vejde ~10–12k znaků.
    Větší dokumenty budou tiše oříznuty nebo způsobí swapování.

Použití:
  uv run python demo03c_local_full_extract.py SPC_0254048_PARALEN.pdf
  uv run python demo03c_local_full_extract.py SPC_0254048_PARALEN.pdf --section indikace
  uv run python demo03c_local_full_extract.py SPC_0254048_PARALEN.pdf --no-save
"""

import sys
import argparse
from pathlib import Path

from common.config import MODEL_CHAT, PDF_DIR
from common.ollama_client import get_ollama_url, chat, embed_text
from common.pdf_utils import extract_full_text
from common.db_postgres import get_connection, insert_extrakt, get_extrakty_stats

# SPC sekce – stejné jako v demo03
SECTION_LABELS = {
    "indikace": "Terapeutické indikace (4.1)",
    "kontraindikace": "Kontraindikace (4.3)",
    "davkovani": "Dávkování a způsob podání (4.2)",
    "vedlejsi_ucinky": "Nežádoucí účinky (4.8)",
    "interakce": "Interakce s jinými léčivými přípravky (4.5)",
    "slozeni": "Kvalitativní a kvantitativní složení (2)",
}


def extract_section_local(full_text: str, section: str, *, model: str, base_url: str) -> str:
    """Extrahuje sekci z celého dokumentu lokálním modelem.

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

    return chat(prompt, system=system, model=model, base_url=base_url)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="UC3c – Extrakce sekcí z PDF lokálním modelem (bez regexu)"
    )
    parser.add_argument("pdf", help="Název PDF souboru (hledá se v data/pdf/)")
    parser.add_argument("--section", default=None, help="Jen konkrétní sekce (výchozí: všechny)")
    parser.add_argument("--model", default=MODEL_CHAT, help=f"Model (výchozí {MODEL_CHAT})")
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
    model = args.model
    sections_to_extract = [args.section] if args.section else list(SECTION_LABELS.keys())

    print("=" * 60)
    print("UC3c – Extrakce sekcí z PDF (lokální model, bez regexu)")
    print("=" * 60)
    print(f"\n📄 Soubor:  {pdf_path}")
    print(f"🔍 Sekce:   {', '.join(sections_to_extract)}")
    print(f"🤖 Model:   {model} (lokální Ollama)")
    print(f"💾 DB:      {'ano' if save else 'ne'}")

    # Extrakce celého textu z PDF
    print("\nExtrahuji text z PDF...")
    full_text = extract_full_text(pdf_path)
    print(f"  ✓ {len(full_text):,} znaků extrahováno")

    base_url = get_ollama_url()
    print(f"  ✓ Ollama: {base_url}")
    print(f"  ⚠️  Celý text ({len(full_text):,} zn.) jde do modelu BEZ regex ořezu")

    typ_extraktu = f"ollama-full({model})"

    # Extrakce sekcí
    print(f"\n{'='*60}")
    extracted = {}
    for section in sections_to_extract:
        try:
            result = extract_section_local(
                full_text, section, model=model, base_url=base_url,
            )

            # Validace
            refusal_markers = ["nenalezeno", "chybí", "nemám", "nemohu", "omlouvám", "nemůžu"]
            is_refusal = any(m in result.lower() for m in refusal_markers) if result else True

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

        except Exception as e:
            print(f"  ✗ [{section}] Chyba: {e}")
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
