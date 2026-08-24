#!/usr/bin/env python3
"""UC3c – Extrakce sekcí z PDF lokálním modelem BEZ regex hledání sekce.

Na rozdíl od demo03 (regex najde sekci, LLM ji jen vyčistí) toto demo:
  - Nepoužívá regex k VYHLEDÁNÍ sekce – o to se stará model
  - Dokument se ale rozseká na větší kusy (CHUNK_CHARS, hranice slov) a sekce
    se v nich hledá postupně – u velkých PDF by se celý text nevešel do
    kontextového okna modelu najednou
  - Ukládá do stejné DB tabulky s typem "ollama-full({model})"

Účel: Porovnání s demo03 (regex+LLM) a demo03b (OpenAI API).

⚠️  num_ctx se nenastavuje explicitně – použije se server default
    (OLLAMA_CONTEXT_LENGTH v systemd override.conf na Ollama serveru, teď 32768).
    CHUNK_CHARS je nastavené výrazně pod tímhle limitem, ať zbyde rezerva na
    system prompt a generovanou odpověď.

Použití:
  uv run python demo03c_local_full_extract.py SPC_0254048_PARALEN.pdf
  uv run python demo03c_local_full_extract.py SPC_0254048_PARALEN.pdf --section indikace
  uv run python demo03c_local_full_extract.py SPC_0254048_PARALEN.pdf --no-save
"""

import sys
import time
import argparse
from pathlib import Path

from common.config import MODEL_CHAT, PDF_DIR
from common.ollama_client import get_ollama_url, chat, embed_text
from common.pdf_utils import extract_full_text, chunk_text
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

# Velikost kusu pro LLM okno – výrazně větší než embedding CHUNK_SIZE (300 zn.),
# protože tady nejde o sémantickou granularitu, ale o to, kolik textu se najednou
# vejde modelu do kontextu spolu se system promptem a rezervou na odpověď.
CHUNK_CHARS = 15000
CHUNK_OVERLAP_CHARS = 2000  # ať se sekce nerozdělí přesně na hranici kusu

REFUSAL_MARKERS = ["nenalezeno", "chybí", "nemám", "nemohu", "omlouvám", "nemůžu"]


def _is_valid_result(text: str) -> bool:
    """Ověří, že odpověď modelu není prázdná, příliš krátká, nebo odmítnutí."""
    if not text or len(text.strip()) <= 20:
        return False
    return not any(m in text.lower() for m in REFUSAL_MARKERS)


def extract_section_local(full_text: str, section: str, *, model: str, base_url: str) -> str:
    """Extrahuje sekci z dokumentu lokálním modelem – bez regex vyhledání sekce.

    Dokument se rozseká na části (chunk_text, hranice slov), protože velké PDF
    by se nevešly do kontextového okna modelu najednou. Sekce se hledá postupně
    v jednotlivých částech, vrací se první platný nález.
    """
    label = SECTION_LABELS.get(section.lower(), section)

    system = (
        "Jsi odborný asistent pro extrakci informací z farmaceutických SPC dokumentů. "
        "Tvým úkolem je z poskytnutého textu vytáhnout POUZE požadovanou sekci. "
        "Vrať kompletní text sekce bez nadpisu a bez číslování. "
        "Pokud sekci nenajdeš, vrať pouze slovo NENALEZENO."
    )

    parts = chunk_text(full_text, chunk_size=CHUNK_CHARS, overlap=CHUNK_OVERLAP_CHARS)

    for i, part in enumerate(parts, 1):
        prompt = f"""Následující text je část {i}/{len(parts)} SPC dokumentu (dokument je rozdělený na více částí po sobě jdoucích, hledaná sekce nemusí být v téhle části).
Pokud tahle část obsahuje sekci „{label}", vytáhni její kompletní obsah.
Pokud tahle část sekci neobsahuje, odpověz pouze slovem NENALEZENO.

{part}"""
        t0 = time.perf_counter()
        result = chat(prompt, system=system, model=model, base_url=base_url)
        part_s = time.perf_counter() - t0
        print(f"      … část {i}/{len(parts)}: {part_s:.1f}s")
        if _is_valid_result(result):
            return result

    return "NENALEZENO"


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
    n_parts = len(chunk_text(full_text, chunk_size=CHUNK_CHARS, overlap=CHUNK_OVERLAP_CHARS))
    print(f"  ⚠️  Text rozsekán na {n_parts} část(í) po ~{CHUNK_CHARS:,} zn. (bez regex hledání sekce)")

    typ_extraktu = f"ollama-full({model})"

    # Extrakce sekcí
    print(f"\n{'='*60}")
    extracted = {}
    for section in sections_to_extract:
        try:
            t0 = time.perf_counter()
            result = extract_section_local(
                full_text, section, model=model, base_url=base_url,
            )
            extract_s = time.perf_counter() - t0

            if _is_valid_result(result):
                print(f"  ✓ [{section}] {len(result)} znaků ({extract_s:.1f}s extrakce celkem)")
                extracted[section] = result
                if save:
                    embed_input = result[:6000] if len(result) > 6000 else result
                    t0 = time.perf_counter()
                    vec = embed_text(embed_input, base_url=base_url)
                    embed_s = time.perf_counter() - t0
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
                    print(f"  💾 [{section}/{typ_extraktu}] Uloženo do DB ({len(vec)} dim, {embed_s:.1f}s embedding)")
            else:
                print(f"  ✗ [{section}] nenalezeno v žádné části (nebo odmítnutí/krátká odpověď) ({extract_s:.1f}s)")

        except Exception as e:
            print(f"  ✗ [{section}] Chyba: {e}")

        hotovo = ", ".join(extracted.keys()) if extracted else "zatím nic"
        stav = "hotovo a uloženo" if save else "hotovo (bez ukládání, --no-save)"
        print(f"  → dosud {stav}: {len(extracted)}/{len(sections_to_extract)} ({hotovo})")
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
