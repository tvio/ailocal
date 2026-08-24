#!/usr/bin/env python3
"""UC5b – Sémantické vyhledávání v JSON extraktech sekcí (extrakty_json).

Na rozdíl od demo05a (chunky celého dokumentu) hledá přímo v strukturovaných
sekcích z demo03d. Embedding pokrývá text_content + rozpadlé tabulky dohromady,
takže dotaz "nevolnost" najde záznam i když v textu stojí "nauzea".

Dva kroky:
  1. --index   Spočítá a uloží embeddingy do sloupce extrakty_json.embedding
  2. (dotaz)   Sémantické hledání + volitelná RAG odpověď ze strukturovaného JSON

Příklady SPC dotazů:
  uv run python demo05b_semantic_extracts.py --index
  uv run python demo05b_semantic_extracts.py "nevolnost a zvracení po léku"
  uv run python demo05b_semantic_extracts.py "cukrovka kontraindikace" --section kontraindikace
  uv run python demo05b_semantic_extracts.py "dávkování děti do 10 let" --section davkovani
  uv run python demo05b_semantic_extracts.py "lék nelze kombinovat s warfarinem" --section interakce
  uv run python demo05b_semantic_extracts.py "poškození jater" --section vedlejsi_ucinky
  uv run python demo05b_semantic_extracts.py "účinná látka složení" --section slozeni
  uv run python demo05b_semantic_extracts.py "kdy lék nesmím užívat" --no-rag
"""

import json
import sys
import argparse

from common.config import MODEL_EMBED, MODEL_CHAT
from common.ollama_client import get_ollama_url, embed_text, chat
from common.db_postgres import (
    get_connection,
    get_extrakty_json_missing_embedding,
    update_extrakty_json_embedding,
    search_extrakty_json,
    get_extrakty_json_stats,
)

THRESHOLD_DEFAULT = 0.5

SECTION_LABELS = {
    "indikace": "Indikace",
    "kontraindikace": "Kontraindikace",
    "davkovani": "Dávkování",
    "vedlejsi_ucinky": "Nežádoucí účinky",
    "interakce": "Interakce",
    "slozeni": "Složení",
}

RAG_SYSTEM_PROMPT = """\
Jsi pomocný asistent, který odpovídá na otázky o lécích na základě strukturovaných dat z SPC dokumentů.
Pravidla:
- Odpovídej POUZE na základě poskytnutého kontextu.
- Vstup může obsahovat tabulky (pole headers + rows) – pracuj s nimi přímo.
- Odpovídej česky, srozumitelně pro laika – překládej odborné termíny.
- Na konci odpovědi uveď zdroj (dokument, sekce).
"""


def flatten_for_embedding(sekce_json: dict) -> str:
    """Sloučí text_content + tabulkové řádky do jednoho textu pro embedding.

    Zachovává strukturu tabulek jako 'hlavicka: hodnota' páry,
    aby sémantické vyhledávání fungovalo i přes tabulková data.
    """
    parts = []
    text = sekce_json.get("text_content", "").strip()
    if text:
        parts.append(text)

    for table in sekce_json.get("tables", []):
        headers = table.get("headers", [])
        for row in table.get("rows", []):
            pairs = [f"{h}: {v}" for h, v in zip(headers, row) if v and v not in ("—", "-", "")]
            if pairs:
                parts.append(", ".join(pairs))

    return "\n".join(parts)


def run_index(base_url: str, embed_model: str) -> None:
    """Spočítá embeddingy pro záznamy extrakty_json, které je ještě nemají."""
    conn = get_connection()
    missing = get_extrakty_json_missing_embedding(conn)
    conn.close()

    if not missing:
        print("Všechny záznamy v extrakty_json již mají embedding.")
        return

    print(f"Indexuji {len(missing)} záznamů bez embeddingu...")
    print()

    for row in missing:
        text = flatten_for_embedding(row["sekce_json"])
        if not text.strip():
            print(f"  ✗ [{row['document_name']} / {row['typ_sekce']}] prázdný text, přeskočeno")
            continue

        embedding = embed_text(text, model=embed_model, base_url=base_url)
        conn = get_connection()
        update_extrakty_json_embedding(conn, row_id=row["id"], embedding=embedding)
        conn.close()
        print(f"  ✓ [{row['document_name']} / {row['typ_sekce']} / {row['typ_modelu']}] "
              f"{len(text)} zn. → {len(embedding)}D embedding")

    print("\n✅ Indexování hotovo!")

    conn = get_connection()
    stats = get_extrakty_json_stats(conn)
    conn.close()
    indexed = sum(1 for s in stats)
    print(f"   Celkem v extrakty_json: {indexed} záznamů")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="UC5b – Sémantické vyhledávání v JSON extraktech sekcí"
    )
    parser.add_argument("query", nargs="*", help="Dotaz pro sémantické vyhledávání")
    parser.add_argument("--index", action="store_true",
                        help="Spočítá a uloží embeddingy do extrakty_json (nutné před prvním hledáním)")
    parser.add_argument("--section", default=None, choices=list(SECTION_LABELS.keys()),
                        help="Hledat jen v konkrétní sekci")
    parser.add_argument("--document", default=None,
                        help="Hledat jen v konkrétním dokumentu")
    parser.add_argument("--top-k", type=int, default=5,
                        help="Počet výsledků (výchozí 5)")
    parser.add_argument("--threshold", type=float, default=THRESHOLD_DEFAULT,
                        help=f"Minimální similarity 0–1 (výchozí {THRESHOLD_DEFAULT})")
    parser.add_argument("--model", default=MODEL_CHAT,
                        help=f"Generativní model pro RAG (výchozí {MODEL_CHAT})")
    parser.add_argument("--embed-model", default=MODEL_EMBED,
                        help=f"Embedding model (výchozí {MODEL_EMBED})")
    parser.add_argument("--no-rag", action="store_true",
                        help="Zobrazit jen nalezené sekce, bez LLM odpovědi")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    base_url = get_ollama_url()

    if args.index:
        print("=" * 60)
        print("UC5b – Indexování extrakty_json (embedding)")
        print("=" * 60)
        run_index(base_url, args.embed_model)
        return

    if not args.query:
        print("Chyba: zadejte dotaz, nebo použijte --index.", file=sys.stderr)
        print('Příklad: uv run python demo05b_semantic_extracts.py "nevolnost a zvracení"')
        sys.exit(1)

    query = " ".join(args.query)
    section_label = SECTION_LABELS.get(args.section, "všechny sekce") if args.section else "všechny sekce"

    print("=" * 60)
    print("UC5b – Sémantické vyhledávání v JSON extraktech")
    print("=" * 60)
    print(f"\n❓ Dotaz:    {query}")
    print(f"📂 Sekce:    {section_label}")
    print(f"📄 Dokument: {args.document or 'všechny'}")
    print(f"📊 Top-K:    {args.top_k}  |  Threshold: {args.threshold}")

    # 1. Embedding dotazu
    print("\n[1/3] Generuji embedding dotazu...")
    query_embedding = embed_text(query, model=args.embed_model, base_url=base_url)
    print(f"  ✓ {len(query_embedding)} dimenzí")

    # 2. Vyhledání v extrakty_json
    print(f"\n[2/3] Hledám v extrakty_json...")
    conn = get_connection()
    results = search_extrakty_json(
        conn, query_embedding,
        top_k=args.top_k,
        typ_sekce=args.section,
        document_name=args.document,
    )
    conn.close()

    if not results:
        print("  Žádné výsledky. Spusťte --index pro vytvoření embeddingů.")
        sys.exit(1)

    above = [r for r in results if r["similarity"] >= args.threshold]
    below = [r for r in results if r["similarity"] < args.threshold]

    print(f"\n  Nalezeno: {len(results)} sekcí, z toho {len(above)} nad prahem {args.threshold}:")
    print()
    for i, r in enumerate(results):
        sim = r["similarity"]
        flag = "✓" if sim >= args.threshold else "✗"
        sj = r["sekce_json"]
        has_table = sj.get("has_table", False)
        table_count = len(sj.get("tables", []))
        text_preview = sj.get("text_content", "")[:120].replace("\n", " ")
        table_info = f" [tabulka x{table_count}]" if has_table else ""
        print(f"  [{i+1}] {flag} similarity={sim:.4f} | {r['document_name']} / "
              f"{r['typ_sekce']}{table_info}")
        print(f"       Model: {r['typ_modelu']}")
        print(f"       {text_preview}...")
        print()

    if not above:
        print(f"  ⚠️  Nic nad prahem {args.threshold}. Zkuste nižší --threshold.")
        sys.exit(0)

    if args.no_rag:
        print("(--no-rag: LLM odpověď vynechána)")
        return

    # 3. RAG ze strukturovaného JSON
    print("[3/3] Generuji odpověď s RAG kontextem (ze strukturovaného JSON)...")
    context_parts = []
    for r in above:
        zdroj = f"[{r['document_name']} / sekce: {r['typ_sekce']} / model: {r['typ_modelu']}]"
        context_parts.append(
            f"{zdroj}\n{json.dumps(r['sekce_json'], ensure_ascii=False, indent=2)}"
        )
    context = "\n\n---\n\n".join(context_parts)

    prompt = f"""Strukturovaná data z SPC dokumentů (JSON):

{context}

---

Otázka: {query}

Odpověz na základě výše uvedených dat."""

    print("\n💬 Odpověď (RAG ze strukturovaného JSON):")
    print("-" * 40)
    chat(prompt, system=RAG_SYSTEM_PROMPT, model=args.model, base_url=base_url, stream=True)
    print(f"\n{'='*60}")
    print("✅ Hotovo!")


if __name__ == "__main__":
    main()
