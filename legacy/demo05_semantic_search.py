#!/usr/bin/env python3
"""UC5 – Sémantické vyhledávání (RAG).

Kompletní RAG pipeline:
  1. Uživatel položí otázku česky
  2. Otázka se převede na embedding
  3. pgvector najde nejpodobnější chunky (cosine similarity)
  4. Nalezené chunky se předají jako kontext LLM modelu
  5. Model vygeneruje odpověď na základě kontextu

Použití:
  uv run python demo05_semantic_search.py "Jaké jsou vedlejší účinky?"
  uv run python demo05_semantic_search.py "Jaké jsou indikace?" --top-k 3

  # Bez RAG – odpověď jen ze znalostí modelu, žádné vyhledávání (pro srovnání):
  uv run python demo05_semantic_search.py "Jaké jsou kontraindikace?" --no-rag

  # Jen similarity search – vypíše nalezené chunky, chat model se nevolá:
  uv run python demo05_semantic_search.py "Jaké jsou kontraindikace?" --search-only

  # Jiný embedding model pro dotaz:
  uv run python demo05_semantic_search.py "Jaké jsou indikace?" --embed-model qwen3-embedding:8b

  uv run python demo05_semantic_search.py --list-docs
"""

import re
import sys
import argparse

from common.config import MODEL_EMBED, MODEL_CHAT
from common.ollama_client import get_ollama_url, embed_text, chat
from common.db_postgres import get_connection, search_similar, get_document_stats


RAG_SYSTEM_PROMPT = """\
Jsi pomocný asistent, který odpovídá na otázky na základě poskytnutého kontextu.
Pravidla:
- Odpovídej POUZE na základě poskytnutého kontextu.
- Pokud kontext neobsahuje odpověď, řekni to upřímně.
- Odpovídej česky, stručně a srozumitelně.
- Na konci uveď, z kterých zdrojů (dokumentů) jsi čerpal.
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="UC5 – Sémantické vyhledávání s RAG"
    )
    parser.add_argument("query", nargs="*", help="Otázka pro vyhledávání")
    parser.add_argument("--top-k", type=int, default=5, help="Počet vrácených chunků (výchozí 5)")
    parser.add_argument("--model", default=MODEL_CHAT, help=f"Generativní model (výchozí {MODEL_CHAT})")
    parser.add_argument("--embed-model", default=MODEL_EMBED, help=f"Embedding model (výchozí {MODEL_EMBED})")
    parser.add_argument("--document", default=None, help="Filtrovat podle názvu dokumentu")
    parser.add_argument("--no-rag", action="store_true", help="Odpovědět BEZ kontextu (pro porovnání)")
    parser.add_argument("--search-only", action="store_true",
                        help="Jen similarity search, bez volání chat modelu (nevygeneruje odpověď)")
    parser.add_argument("--list-docs", action="store_true", help="Zobrazit dokumenty v databázi")
    return parser.parse_args()


def list_documents() -> None:
    """Zobrazí přehled dokumentů uložených v databázi."""
    conn = get_connection()
    try:
        stats = get_document_stats(conn)
        if not stats:
            print("Databáze je prázdná. Nejdřív spusťte demo01 pro načtení dat.")
            return
        print("\n📚 Dokumenty v databázi:")
        print("-" * 50)
        for s in stats:
            print(f"  📄 {s['document_name']}: {s['chunk_count']} chunků")
    finally:
        conn.close()


def main() -> None:
    args = parse_args()

    if args.list_docs:
        list_documents()
        return

    if not args.query:
        print("Chyba: zadejte otázku jako argument.", file=sys.stderr)
        print('Příklad: uv run python demo05_semantic_search.py "Jaké jsou vedlejší účinky?"')
        sys.exit(1)

    query = " ".join(args.query)

    print("=" * 60)
    print("UC5 – Sémantické vyhledávání (RAG)")
    print("=" * 60)
    print(f"\n❓ Otázka: {query}")
    print(f"🤖 Model:  {args.model}")
    print(f"🧬 Embed:  {args.embed_model}")
    print(f"📊 Top-K:  {args.top_k}")

    if args.no_rag:
        # Odpověď BEZ kontextu (pro porovnání)
        print("\n" + "=" * 60)
        print("🚫 Režim BEZ RAG (model odpovídá jen ze svých znalostí)")
        print("=" * 60)
        base_url = get_ollama_url()
        print("\n💬 Odpověď modelu:")
        print("-" * 40)
        answer = chat(
            query,
            system="Odpovídej česky, stručně a srozumitelně.",
            model=args.model,
            base_url=base_url,
            stream=True,
        )
        print()
        return

    # --- RAG pipeline ---

    # 1. Embedding dotazu
    print("\n[1/3] Generuji embedding dotazu...")
    base_url = get_ollama_url()
    query_embedding = embed_text(query, model=args.embed_model, base_url=base_url)
    print(f"  ✓ Embedding vygenerován (dimenze: {len(query_embedding)})")

    # 2. Vyhledání podobných chunků
    print(f"\n[2/3] Hledám {args.top_k} nejpodobnějších chunků v pgvector...")
    conn = get_connection()
    try:
        results = search_similar(
            conn, query_embedding,
            top_k=args.top_k,
            document_name=args.document,
        )
    finally:
        conn.close()

    if not results:
        print("  ⚠️  Žádné výsledky. Nejdřív spusťte demo01 pro načtení dat.")
        sys.exit(1)

    print(f"  ✓ Nalezeno {len(results)} chunků:")
    print()
    for i, r in enumerate(results):
        sim = r["similarity"]
        # celý chunk na jeden řádek – sjednotí whitespace (newlines, víc mezer) na jednu mezeru
        content_oneline = re.sub(r"\s+", " ", r["content"]).strip()
        doc = r["document_name"]
        page = r.get("page_number", "?")
        print(f"  [{i+1}] Similarity: {sim:.4f} | Dokument: {doc} | Str. {page}")
        print(f"      {content_oneline}")
        print()

    if args.search_only:
        print("✅ Hotovo! (--search-only: chat model se nevolal)")
        return

    # 3. Sestavení kontextu a generování odpovědi
    print("[3/3] Generuji odpověď s kontextem (RAG)...")
    context_parts = []
    for i, r in enumerate(results):
        source = f"[Zdroj: {r['document_name']}, str. {r.get('page_number', '?')}]"
        context_parts.append(f"{source}\n{r['content']}")
    context = "\n\n---\n\n".join(context_parts)

    prompt = f"""Kontext z dokumentů:

{context}

---

Otázka: {query}

Odpověz na základě výše uvedeného kontextu."""

    print("\n💬 Odpověď modelu (s RAG):")
    print("-" * 40)
    answer = chat(
        prompt,
        system=RAG_SYSTEM_PROMPT,
        model=args.model,
        base_url=base_url,
        stream=True,
    )
    print("\n" + "=" * 60)
    print("✅ Hotovo!")


if __name__ == "__main__":
    main()
