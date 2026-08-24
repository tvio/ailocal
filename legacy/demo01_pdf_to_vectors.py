#!/usr/bin/env python3
"""UC1 – PDF → vektory (jeden dokument).

Kompletní pipeline:
  1. Načtení PDF souboru
  2. Extrakce textu po stránkách
  3. Rozdělení na chunky s překryvem
  4. Embedding přes lokální Ollama model (nomic-embed-text)
  5. Uložení chunků + vektorů do PostgreSQL s pgvector

Použití:
  uv run python demo01_pdf_to_vectors.py SPC_0254048_PARALEN.pdf
  uv run python demo01_pdf_to_vectors.py SPC_0254048_PARALEN.pdf --chunk-size 800 --overlap 100
"""

import sys
import argparse
from pathlib import Path

from common.config import CHUNK_SIZE, CHUNK_OVERLAP, MODEL_EMBED, PDF_DIR
from common.ollama_client import get_ollama_url, embed_texts
from common.pdf_utils import extract_text_from_pdf, chunk_pages
from common.db_postgres import get_connection, insert_chunks_batch, get_document_stats


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="UC1 – Zpracování PDF do vektorů a uložení do pgvector"
    )
    parser.add_argument("pdf", help="Název PDF souboru (hledá se v data/pdf/)")
    parser.add_argument("--chunk-size", type=int, default=CHUNK_SIZE, help=f"Velikost chunku (výchozí {CHUNK_SIZE})")
    parser.add_argument("--overlap", type=int, default=CHUNK_OVERLAP, help=f"Překryv chunků (výchozí {CHUNK_OVERLAP})")
    parser.add_argument("--model", default=MODEL_EMBED, help=f"Embedding model (výchozí {MODEL_EMBED})")
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

    # 1. Ověření Ollama
    print("=" * 60)
    print("UC1 – PDF → vektory")
    print("=" * 60)
    print(f"\n📄 Soubor:     {pdf_path}")
    print(f"📏 Chunk size: {args.chunk_size} znaků, overlap: {args.overlap}")
    print(f"🤖 Model:      {args.model}")

    print("\n[1/5] Ověřuji dostupnost Ollama...")
    base_url = get_ollama_url()
    print(f"  ✓ Ollama dostupná na {base_url}")

    # 2. Extrakce textu
    print("\n[2/5] Extrahuji text z PDF...")
    pages = extract_text_from_pdf(pdf_path)
    total_chars = sum(len(p["text"]) for p in pages)
    print(f"  ✓ {len(pages)} stránek, celkem {total_chars:,} znaků")

    # Ukázka první stránky
    if pages:
        preview = pages[0]["text"][:200].replace("\n", " ")
        print(f"  📖 Ukázka (str. 1): {preview}...")

    # 3. Chunking
    print(f"\n[3/5] Rozděluju na chunky (size={args.chunk_size}, overlap={args.overlap})...")
    chunks = chunk_pages(pages, chunk_size=args.chunk_size, overlap=args.overlap)
    print(f"  ✓ {len(chunks)} chunků vytvořeno")

    # Ukázka prvních chunků
    for i, ch in enumerate(chunks[:3]):
        preview = ch["text"][:80].replace("\n", " ")
        print(f"  📌 Chunk {i}: [str. {ch['page']}] {preview}...")

    # 4. Embedding
    print(f"\n[4/5] Generuji embeddingy ({args.model})...")
    print(f"  ⏳ Zpracovávám {len(chunks)} chunků (může trvat desítky sekund)...")

    # Embedujeme po dávkách (Ollama zvládne batch)
    batch_size = 20
    all_embeddings = []
    for i in range(0, len(chunks), batch_size):
        batch_texts = [c["text"] for c in chunks[i:i + batch_size]]
        batch_embs = embed_texts(batch_texts, model=args.model, base_url=base_url)
        all_embeddings.extend(batch_embs)
        done = min(i + batch_size, len(chunks))
        print(f"  ... {done}/{len(chunks)} hotovo")

    print(f"  ✓ {len(all_embeddings)} embeddingů vygenerováno (dimenze: {len(all_embeddings[0])})")

    # 5. Uložení do pgvector
    print("\n[5/5] Ukládám do PostgreSQL + pgvector...")
    conn = get_connection()
    try:
        count = insert_chunks_batch(conn, document_name, chunks, all_embeddings)
        print(f"  ✓ {count} chunků uloženo do tabulky document_chunks")

        # Statistiky
        print("\n" + "=" * 60)
        print("📊 Statistiky databáze:")
        print("-" * 60)
        stats = get_document_stats(conn)
        for s in stats:
            print(f"  {s['document_name']}: {s['chunk_count']} chunků")
    finally:
        conn.close()

    print("\n✅ Hotovo! Data jsou připravena pro sémantické vyhledávání (UC5).")


if __name__ == "__main__":
    main()
