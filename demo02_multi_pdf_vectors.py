#!/usr/bin/env python3
"""UC2 – Více PDF → společná vektorová DB.

Zpracuje všechny PDF soubory z adresáře a uloží je do společné vektorové databáze.

Použití:
  uv run python demo02_multi_pdf_vectors.py
  uv run python demo02_multi_pdf_vectors.py --chunk-size 800
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
        description="UC2 – Zpracování více PDF do společné vektorové DB"
    )
    parser.add_argument("directory", nargs="?", default=str(PDF_DIR), help=f"Adresář s PDF (výchozí {PDF_DIR})")
    parser.add_argument("--chunk-size", type=int, default=CHUNK_SIZE)
    parser.add_argument("--overlap", type=int, default=CHUNK_OVERLAP)
    parser.add_argument("--model", default=MODEL_EMBED)
    return parser.parse_args()


def process_single_pdf(
    pdf_path: Path,
    *,
    chunk_size: int,
    overlap: int,
    model: str,
    base_url: str,
    conn,
) -> int:
    """Zpracuje jeden PDF soubor. Vrátí počet uložených chunků."""
    document_name = pdf_path.stem

    # Extrakce textu
    pages = extract_text_from_pdf(pdf_path)
    if not pages:
        print(f"  ⚠️  {pdf_path.name}: prázdný dokument, přeskakuji")
        return 0

    total_chars = sum(len(p["text"]) for p in pages)
    print(f"  📄 {pdf_path.name}: {len(pages)} stránek, {total_chars:,} znaků")

    # Chunking
    chunks = chunk_pages(pages, chunk_size=chunk_size, overlap=overlap)
    print(f"     → {len(chunks)} chunků")

    # Embedding (po dávkách)
    batch_size = 20
    all_embeddings = []
    for i in range(0, len(chunks), batch_size):
        batch_texts = [c["text"] for c in chunks[i:i + batch_size]]
        batch_embs = embed_texts(batch_texts, model=model, base_url=base_url)
        all_embeddings.extend(batch_embs)

    # Uložení
    count = insert_chunks_batch(conn, document_name, chunks, all_embeddings)
    print(f"     → {count} chunků uloženo ✓")
    return count


def main() -> None:
    args = parse_args()
    directory = Path(args.directory)

    if not directory.is_dir():
        print(f"Chyba: '{directory}' není adresář.", file=sys.stderr)
        sys.exit(1)

    pdf_files = sorted(directory.glob("*.pdf"))
    if not pdf_files:
        print(f"Chyba: v '{directory}' nejsou žádné PDF soubory.", file=sys.stderr)
        sys.exit(1)

    print("=" * 60)
    print("UC2 – Více PDF → společná vektorová DB")
    print("=" * 60)
    print(f"\n📂 Adresář:    {directory}")
    print(f"📄 PDF souborů: {len(pdf_files)}")
    print(f"📏 Chunk size:  {args.chunk_size}, overlap: {args.overlap}")
    print(f"🤖 Model:       {args.model}")

    base_url = get_ollama_url()
    print(f"  ✓ Ollama dostupná na {base_url}")

    conn = get_connection()
    total_chunks = 0

    try:
        print(f"\nZpracovávám {len(pdf_files)} dokumentů:\n")
        for i, pdf_path in enumerate(pdf_files, 1):
            print(f"[{i}/{len(pdf_files)}]")
            count = process_single_pdf(
                pdf_path,
                chunk_size=args.chunk_size,
                overlap=args.overlap,
                model=args.model,
                base_url=base_url,
                conn=conn,
            )
            total_chunks += count
            print()

        # Statistiky
        print("=" * 60)
        print(f"📊 Celkem uloženo: {total_chunks} chunků z {len(pdf_files)} dokumentů")
        print("-" * 60)
        stats = get_document_stats(conn)
        for s in stats:
            print(f"  📄 {s['document_name']}: {s['chunk_count']} chunků")
    finally:
        conn.close()

    print(f"\n✅ Hotovo! Spusťte demo05 pro sémantické vyhledávání přes všechny dokumenty.")


if __name__ == "__main__":
    main()
