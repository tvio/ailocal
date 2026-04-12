#!/usr/bin/env python3
"""UC5a – Sémantické vyhledávání v chunkcích celého dokumentu.

Prohledává tabulku document_chunks (demo01) – celý text dokumentu rozbitý
na překrývající se chunky s embeddingy. Hledání probíhá bez znalosti struktury
dokumentu, relevantní chunky mohou pocházet z libovolné sekce.

Pipeline:
  1. Dotaz → embedding (nomic-embed-text)
  2. pgvector cosine similarity → top-K chunků
  3. Chunky jako kontext → LLM odpověď (RAG)

Příklady SPC dotazů:
  uv run python demo05a_semantic_chunks.py "pacient s jaterním selháním, může užívat?"
  uv run python demo05a_semantic_chunks.py "riziko při předávkování paracetamolem"
  uv run python demo05a_semantic_chunks.py "dávkování pro děti do 10 let"
  uv run python demo05a_semantic_chunks.py "alkohol a tento lék"
  uv run python demo05a_semantic_chunks.py "kdy přestat užívat lék"
  uv run python demo05a_semantic_chunks.py "interakce s warfarinem" --document SPC_0254048_PARALEN
  uv run python demo05a_semantic_chunks.py "co je účinná látka" --no-rag
  uv run python demo05a_semantic_chunks.py --list-docs
"""

import sys
import argparse

from common.config import MODEL_EMBED, MODEL_CHAT
from common.ollama_client import get_ollama_url, embed_text, chat
from common.db_postgres import get_connection, search_similar, get_document_stats

THRESHOLD_DEFAULT = 0.5

RAG_SYSTEM_PROMPT = """\
Jsi pomocný asistent, který odpovídá na otázky o lécích na základě poskytnutého kontextu z SPC dokumentů.
Pravidla:
- Odpovídej POUZE na základě poskytnutého kontextu.
- Pokud kontext neobsahuje přesnou odpověď, řekni to upřímně.
- Odpovídej česky, srozumitelně pro laika – vysvětluj odborné termíny.
- Na konci každé odpovědi uveď zdroj (název dokumentu a stránku).
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="UC5a – Sémantické vyhledávání v chunkcích dokumentů"
    )
    parser.add_argument("query", nargs="*", help="Otázka nebo hledaný výraz")
    parser.add_argument("--top-k", type=int, default=5,
                        help="Počet chunků k načtení (výchozí 5)")
    parser.add_argument("--threshold", type=float, default=THRESHOLD_DEFAULT,
                        help=f"Minimální similarity skóre 0–1 (výchozí {THRESHOLD_DEFAULT})")
    parser.add_argument("--document", default=None,
                        help="Hledat jen v konkrétním dokumentu (jinak cross-document)")
    parser.add_argument("--model", default=MODEL_CHAT,
                        help=f"Generativní model (výchozí {MODEL_CHAT})")
    parser.add_argument("--embed-model", default=MODEL_EMBED,
                        help=f"Embedding model (výchozí {MODEL_EMBED})")
    parser.add_argument("--no-rag", action="store_true",
                        help="Zobrazit jen nalezené chunky, bez LLM odpovědi")
    parser.add_argument("--list-docs", action="store_true",
                        help="Zobrazit dokumenty v DB a skončit")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    base_url = get_ollama_url()

    if args.list_docs:
        conn = get_connection()
        stats = get_document_stats(conn)
        conn.close()
        if not stats:
            print("DB je prázdná. Spusťte demo01.")
            return
        print("\n📚 Dokumenty v document_chunks:")
        for s in stats:
            print(f"  📄 {s['document_name']}: {s['chunk_count']} chunků")
        return

    if not args.query:
        print("Chyba: zadejte dotaz.", file=sys.stderr)
        print('Příklad: uv run python demo05a_semantic_chunks.py "riziko předávkování"')
        sys.exit(1)

    query = " ".join(args.query)

    print("=" * 60)
    print("UC5a – Sémantické vyhledávání v chunkcích")
    print("=" * 60)
    print(f"\n❓ Dotaz:     {query}")
    print(f"📄 Dokument:  {args.document or 'všechny (cross-document)'}")
    print(f"📊 Top-K:     {args.top_k}  |  Threshold: {args.threshold}")

    # 1. Embedding dotazu
    print("\n[1/3] Generuji embedding dotazu...")
    query_embedding = embed_text(query, model=args.embed_model, base_url=base_url)
    print(f"  ✓ {len(query_embedding)} dimenzí")

    # 2. Vyhledání chunků
    print(f"\n[2/3] Hledám v pgvector (document_chunks)...")
    conn = get_connection()
    results = search_similar(
        conn, query_embedding,
        top_k=args.top_k,
        document_name=args.document,
    )
    conn.close()

    if not results:
        print("  Žádné výsledky. Spusťte demo01 pro načtení dokumentů.")
        sys.exit(1)

    # Filtr dle prahu
    above = [r for r in results if r["similarity"] >= args.threshold]
    below = [r for r in results if r["similarity"] < args.threshold]

    # Zkontroluj, zda dotaz vypadá jako přesné klíčové slovo (krátký, žádné mezery)
    if len(query.split()) <= 2:
        print(f"\n  ℹ️  Tip: vektorový search hledá sémanticky podobný obsah, ne přesné klíčové slovo.")
        print(f"     Pro přesné hledání názvů látek (fenobarbital, warfarin...) použij hybrid search (demo05c).")

    print(f"\n  Nalezeno: {len(results)} chunků, z toho {len(above)} nad prahem {args.threshold}:")
    print()
    for i, r in enumerate(results):
        sim = r["similarity"]
        flag = "✓" if sim >= args.threshold else "✗"
        doc = r["document_name"]
        page = r.get("page_number") or "?"
        preview = r["content"][:120].replace("\n", " ")
        # Vyznač přímý výskyt hledaného výrazu v chunku
        hit = "🎯" if any(w.lower() in r["content"].lower() for w in query.split()) else "  "
        print(f"  [{i+1}] {flag}{hit} similarity={sim:.4f} | {doc} str.{page}")
        print(f"       {preview}...")
        print()

    if not above:
        print(f"  ⚠️  Žádný chunk nepřekročil práh {args.threshold}. Zkuste nižší --threshold nebo jiný dotaz.")
        sys.exit(0)

    if args.no_rag:
        print("(--no-rag: LLM odpověď vynechána)")
        return

    # 3. RAG – LLM odpověď
    print("[3/3] Generuji odpověď s RAG kontextem...")
    context_parts = []
    for r in above:
        zdroj = f"[{r['document_name']}, str. {r.get('page_number') or '?'}]"
        context_parts.append(f"{zdroj}\n{r['content']}")
    context = "\n\n---\n\n".join(context_parts)

    prompt = f"""Kontext z SPC dokumentů:

{context}

---

Otázka: {query}

Odpověz na základě výše uvedeného kontextu."""

    print("\n💬 Odpověď (RAG):")
    print("-" * 40)
    chat(prompt, system=RAG_SYSTEM_PROMPT, model=args.model, base_url=base_url, stream=True)
    print(f"\n{'='*60}")
    print("✅ Hotovo!")


if __name__ == "__main__":
    main()
