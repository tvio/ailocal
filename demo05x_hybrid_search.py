#!/usr/bin/env python3
"""UC5b – Hybrid search: sémantické + fulltext vyhledávání.

Kombinuje pgvector (cosine similarity) s PostgreSQL fulltext (tsvector/tsquery)
pomocí Reciprocal Rank Fusion (RRF). Hledá v tabulce extrakty (demo03 + demo04).

Použití:
  uv run python demo05b_hybrid_search.py "paracetamol dávkování"
  uv run python demo05b_hybrid_search.py "co mi pomůže na bolest hlavy"
  uv run python demo05b_hybrid_search.py "kontraindikace" --weight 0.3
  uv run python demo05b_hybrid_search.py "paracetamol" --method fulltext
"""

import sys
import argparse

from common.config import MODEL_CHAT
from common.ollama_client import get_ollama_url, chat, embed_text
from common.db_postgres import get_connection, hybrid_search, get_extrakty_stats


def search_semantic_only(conn, query_embedding, *, top_k=5):
    """Čistě sémantické vyhledávání v extraktech."""
    rows = conn.execute(
        """
        SELECT id, document_name, typ_sekce, sekce_text, zjednoduseni,
               1 - (sekce_vector <=> %s::vector) AS sem_score
        FROM extrakty
        WHERE sekce_vector IS NOT NULL
        ORDER BY sekce_vector <=> %s::vector
        LIMIT %s
        """,
        (str(query_embedding), str(query_embedding), top_k),
    ).fetchall()
    return [dict(r) for r in rows]


def search_fulltext_only(conn, query_text, *, top_k=5):
    """Čistě fulltext vyhledávání v extraktech."""
    rows = conn.execute(
        """
        SELECT id, document_name, typ_sekce, sekce_text, zjednoduseni,
               ts_rank_cd(sekce_fts, websearch_to_tsquery('czech_unaccent', %s)) AS fts_score
        FROM extrakty
        WHERE sekce_fts @@ websearch_to_tsquery('czech_unaccent', %s)
        ORDER BY fts_score DESC
        LIMIT %s
        """,
        (query_text, query_text, top_k),
    ).fetchall()
    return [dict(r) for r in rows]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="UC5b – Hybrid search (sémantické + fulltext)"
    )
    parser.add_argument("query", help="Dotaz v přirozeném jazyce")
    parser.add_argument("--top-k", type=int, default=5, help="Počet výsledků (výchozí 5)")
    parser.add_argument("--weight", type=float, default=0.5,
                        help="Váha sémantiky (0.0=jen fulltext, 1.0=jen sémantika, výchozí 0.5)")
    parser.add_argument("--method", choices=["hybrid", "semantic", "fulltext", "compare"],
                        default="compare", help="Metoda vyhledávání (výchozí: compare)")
    parser.add_argument("--model", default=MODEL_CHAT, help=f"Model pro RAG odpověď (výchozí {MODEL_CHAT})")
    parser.add_argument("--no-rag", action="store_true", help="Bez generování RAG odpovědi")
    return parser.parse_args()


def print_results(results: list[dict], label: str) -> None:
    """Vypíše výsledky vyhledávání."""
    print(f"\n{'─'*60}")
    print(f"  {label} ({len(results)} výsledků)")
    print(f"{'─'*60}")
    if not results:
        print("  (žádné výsledky)")
        return
    for i, r in enumerate(results, 1):
        # Skóre
        scores = []
        if "sem_score" in r and r["sem_score"]:
            scores.append(f"sem={r['sem_score']:.4f}")
        if "fts_score" in r and r["fts_score"]:
            scores.append(f"fts={r['fts_score']:.4f}")
        if "combined_score" in r and r["combined_score"]:
            scores.append(f"combined={r['combined_score']:.4f}")
        score_str = " | ".join(scores) if scores else "—"

        # Dokument
        doc = r.get("document_name", "?")
        sekce = r.get("typ_sekce", "?")
        text = r.get("sekce_text", "")[:150].replace("\n", " ")

        print(f"\n  [{i}] {doc} / {sekce}  ({score_str})")
        print(f"      {text}...")
        if r.get("zjednoduseni"):
            zjedn = r["zjednoduseni"][:100].replace("\n", " ")
            print(f"      💡 Zjednodušeno: {zjedn}...")


def generate_rag_answer(query: str, results: list[dict], *, model: str, base_url: str) -> str:
    """Vygeneruje odpověď na základě nalezených extraktů."""
    context_parts = []
    for r in results:
        doc = r.get("document_name", "?")
        sekce = r.get("typ_sekce", "?")
        text = r.get("zjednoduseni") or r.get("sekce_text", "")
        context_parts.append(f"[{doc} / {sekce}]:\n{text}")

    context = "\n\n".join(context_parts)

    system = (
        "Jsi odborný asistent pro informace o lécích. "
        "Odpovídej POUZE na základě poskytnutého kontextu. "
        "Pokud kontext neobsahuje odpověď, řekni to. "
        "Pokud existuje zjednodušená verze, preferuj ji. "
        "Odpovídej česky, stručně a přesně. Na konci uveď zdroje."
    )

    prompt = f"""Kontext z databáze léků:

{context}

Otázka: {query}

Odpověď:"""

    return chat(prompt, system=system, model=model, base_url=base_url, stream=True)


def main() -> None:
    args = parse_args()

    print("=" * 60)
    print("UC5b – Hybrid search (sémantické + fulltext)")
    print("=" * 60)
    print(f"\n❓ Dotaz:   {args.query}")
    print(f"⚙️  Metoda:  {args.method}")
    if args.method in ("hybrid", "compare"):
        print(f"⚖️  Váha:    sémantika={args.weight:.1f}, fulltext={1-args.weight:.1f}")

    # Kontrola dat v DB
    conn = get_connection()
    stats = get_extrakty_stats(conn)
    if not stats:
        print("\n⚠️  Tabulka extrakty je prázdná!")
        print("  Nejdřív spusťte: uv run python demo03_pdf_section_extract.py SPC_0254048_PARALEN.pdf --save --all-sections")
        conn.close()
        sys.exit(1)
    print(f"📊 Extraktů v DB: {len(stats)}")

    base_url = get_ollama_url()
    print(f"  ✓ Ollama: {base_url}")

    # Embedding dotazu (pro sémantiku)
    query_embedding = None
    if args.method in ("semantic", "hybrid", "compare"):
        print("\n  Generuji embedding dotazu...")
        query_embedding = embed_text(args.query, base_url=base_url)

    # Vyhledávání
    best_results = []

    if args.method == "compare":
        # Porovnání všech tří metod
        sem_results = search_semantic_only(conn, query_embedding, top_k=args.top_k)
        print_results(sem_results, "🔮 Sémantické vyhledávání")

        fts_results = search_fulltext_only(conn, args.query, top_k=args.top_k)
        print_results(fts_results, "📝 Fulltext vyhledávání")

        hybrid_results = hybrid_search(
            conn, query_embedding, args.query,
            top_k=args.top_k, sem_weight=args.weight,
        )
        print_results(hybrid_results, "⚡ Hybrid search (RRF)")
        best_results = hybrid_results

    elif args.method == "semantic":
        sem_results = search_semantic_only(conn, query_embedding, top_k=args.top_k)
        print_results(sem_results, "🔮 Sémantické vyhledávání")
        best_results = sem_results

    elif args.method == "fulltext":
        fts_results = search_fulltext_only(conn, args.query, top_k=args.top_k)
        print_results(fts_results, "📝 Fulltext vyhledávání")
        best_results = fts_results

    elif args.method == "hybrid":
        hybrid_results = hybrid_search(
            conn, query_embedding, args.query,
            top_k=args.top_k, sem_weight=args.weight,
        )
        print_results(hybrid_results, "⚡ Hybrid search (RRF)")
        best_results = hybrid_results

    conn.close()

    # RAG odpověď
    if not args.no_rag and best_results:
        print(f"\n{'='*60}")
        print(f"💬 RAG odpověď (model: {args.model})")
        print("-" * 60)
        generate_rag_answer(args.query, best_results, model=args.model, base_url=base_url)

    print(f"\n\n{'='*60}")
    print("✅ Hotovo!")


if __name__ == "__main__":
    main()
