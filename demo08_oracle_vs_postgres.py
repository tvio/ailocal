#!/usr/bin/env python3
"""UC8 – Oracle 23ai vs. Postgres pgvector.

Porovnání vektorových schopností Oracle Free 23ai a PostgreSQL + pgvector.
Stejná data, stejné embeddingy, dva různé databázové enginy.

Použití:
  uv run python demo08_oracle_vs_postgres.py --setup          # vytvoří tabulky v obou DB
  uv run python demo08_oracle_vs_postgres.py --load data/pdf/  # načte data do obou DB
  uv run python demo08_oracle_vs_postgres.py "hledaný text"    # porovná vyhledávání
  uv run python demo08_oracle_vs_postgres.py --benchmark        # benchmark rychlosti

Poznámka:
  Oracle Free 23ai musí běžet v Dockeru. Pokud není dostupný,
  demo poběží jen s Postgres a ukáže, jak by Oracle vypadal.
"""

import sys
import time
import argparse

from common.config import PG_DSN, MODEL_EMBED, EMBED_DIMENSION
from common.ollama_client import get_ollama_url, embed_text, embed_texts
from common.db_postgres import get_connection as get_pg_connection, search_similar as pg_search


# Oracle konfigurace (pokud je dostupný)
ORACLE_DSN = "localhost:1521/FREEPDB1"
ORACLE_USER = "ailocal"
ORACLE_PASSWORD = "ailocal"


def oracle_available() -> bool:
    """Zkontroluje, zda je Oracle dostupný."""
    try:
        import oracledb
        conn = oracledb.connect(user=ORACLE_USER, password=ORACLE_PASSWORD, dsn=ORACLE_DSN)
        conn.close()
        return True
    except Exception:
        return False


def setup_oracle() -> None:
    """Vytvoří tabulku v Oracle s VECTOR sloupcem."""
    import oracledb
    conn = oracledb.connect(user=ORACLE_USER, password=ORACLE_PASSWORD, dsn=ORACLE_DSN)
    cursor = conn.cursor()
    cursor.execute("""
        BEGIN
            EXECUTE IMMEDIATE 'DROP TABLE document_chunks_ora CASCADE CONSTRAINTS';
        EXCEPTION
            WHEN OTHERS THEN NULL;
        END;
    """)
    cursor.execute(f"""
        CREATE TABLE document_chunks_ora (
            id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            document_name VARCHAR2(500) NOT NULL,
            chunk_index NUMBER NOT NULL,
            page_number NUMBER,
            content CLOB NOT NULL,
            embedding VECTOR({EMBED_DIMENSION}, FLOAT64),
            created_at TIMESTAMP DEFAULT SYSTIMESTAMP,
            UNIQUE(document_name, chunk_index)
        )
    """)
    conn.commit()
    conn.close()
    print("  ✓ Oracle: tabulka document_chunks_ora vytvořena")


def oracle_insert(document_name: str, chunk_index: int, page_number: int,
                  content: str, embedding: list[float]) -> None:
    """Vloží chunk do Oracle."""
    import oracledb
    conn = oracledb.connect(user=ORACLE_USER, password=ORACLE_PASSWORD, dsn=ORACLE_DSN)
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO document_chunks_ora
           (document_name, chunk_index, page_number, content, embedding)
           VALUES (:1, :2, :3, :4, TO_VECTOR(:5))""",
        (document_name, chunk_index, page_number, content, str(embedding)),
    )
    conn.commit()
    conn.close()


def oracle_search(query_embedding: list[float], top_k: int = 5) -> list[dict]:
    """Vyhledá nejpodobnější chunky v Oracle."""
    import oracledb
    conn = oracledb.connect(user=ORACLE_USER, password=ORACLE_PASSWORD, dsn=ORACLE_DSN)
    cursor = conn.cursor()
    cursor.execute(
        f"""SELECT id, document_name, content, page_number,
                   VECTOR_DISTANCE(embedding, TO_VECTOR(:1), COSINE) AS distance
            FROM document_chunks_ora
            ORDER BY VECTOR_DISTANCE(embedding, TO_VECTOR(:2), COSINE)
            FETCH FIRST :3 ROWS ONLY""",
        (str(query_embedding), str(query_embedding), top_k),
    )
    results = []
    for row in cursor:
        results.append({
            "id": row[0],
            "document_name": row[1],
            "content": row[2],
            "page_number": row[3],
            "similarity": 1 - row[4],  # distance → similarity
        })
    conn.close()
    return results


def benchmark_search(query_embedding: list[float], *, iterations: int = 10, top_k: int = 5) -> dict:
    """Benchmark vyhledávání v obou databázích."""
    results = {}

    # Postgres benchmark
    pg_conn = get_pg_connection()
    pg_times = []
    for _ in range(iterations):
        start = time.perf_counter()
        pg_search(pg_conn, query_embedding, top_k=top_k)
        pg_times.append(time.perf_counter() - start)
    pg_conn.close()
    results["postgres"] = {
        "avg_ms": sum(pg_times) / len(pg_times) * 1000,
        "min_ms": min(pg_times) * 1000,
        "max_ms": max(pg_times) * 1000,
    }

    # Oracle benchmark (pokud dostupný)
    if oracle_available():
        ora_times = []
        for _ in range(iterations):
            start = time.perf_counter()
            oracle_search(query_embedding, top_k=top_k)
            ora_times.append(time.perf_counter() - start)
        results["oracle"] = {
            "avg_ms": sum(ora_times) / len(ora_times) * 1000,
            "min_ms": min(ora_times) * 1000,
            "max_ms": max(ora_times) * 1000,
        }

    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="UC8 – Oracle 23ai vs. Postgres pgvector"
    )
    parser.add_argument("query", nargs="*", help="Dotaz pro vyhledávání")
    parser.add_argument("--setup", action="store_true", help="Vytvořit tabulky v Oracle")
    parser.add_argument("--benchmark", action="store_true", help="Benchmark rychlosti")
    parser.add_argument("--iterations", type=int, default=10, help="Počet iterací benchmarku")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--model", default=MODEL_EMBED)
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    print("=" * 60)
    print("UC8 – Oracle 23ai vs. Postgres pgvector")
    print("=" * 60)

    has_oracle = oracle_available()
    print(f"\n📊 PostgreSQL + pgvector: ✓ dostupný")
    print(f"📊 Oracle Free 23ai:     {'✓ dostupný' if has_oracle else '✗ nedostupný'}")

    if not has_oracle:
        print("\n⚠️  Oracle není dostupný. Demo poběží pouze s PostgreSQL.")
        print("   Pro plné porovnání přidejte Oracle Free do docker-compose.yml:")
        print("   image: container-registry.oracle.com/database/free:latest")

    if args.setup:
        if has_oracle:
            print("\n🔧 Vytvářím tabulky v Oracle...")
            setup_oracle()
        else:
            print("\n⚠️  Oracle není dostupný, nelze vytvořit tabulky.")
        return

    if args.benchmark:
        print(f"\n🏎️  Benchmark vyhledávání ({args.iterations} iterací, top-{args.top_k})...")
        base_url = get_ollama_url()
        test_query = "testovací dotaz pro benchmark"
        query_emb = embed_text(test_query, model=args.model, base_url=base_url)

        results = benchmark_search(query_emb, iterations=args.iterations, top_k=args.top_k)

        print(f"\n📊 Výsledky benchmarku:")
        print("-" * 50)
        for db_name, stats in results.items():
            print(f"\n  {db_name.upper()}:")
            print(f"    Průměr: {stats['avg_ms']:.2f} ms")
            print(f"    Min:    {stats['min_ms']:.2f} ms")
            print(f"    Max:    {stats['max_ms']:.2f} ms")

        if len(results) == 2:
            pg_avg = results["postgres"]["avg_ms"]
            ora_avg = results["oracle"]["avg_ms"]
            faster = "PostgreSQL" if pg_avg < ora_avg else "Oracle"
            ratio = max(pg_avg, ora_avg) / min(pg_avg, ora_avg)
            print(f"\n  🏆 {faster} je {ratio:.1f}× rychlejší")
        return

    if not args.query:
        print("\nChyba: zadejte dotaz, --setup nebo --benchmark", file=sys.stderr)
        sys.exit(1)

    query = " ".join(args.query)
    base_url = get_ollama_url()
    print(f"\n❓ Dotaz: {query}")
    print(f"🤖 Model: {args.model}")

    query_emb = embed_text(query, model=args.model, base_url=base_url)

    # Postgres vyhledávání
    print(f"\n{'='*60}")
    print("🐘 PostgreSQL + pgvector")
    print("-" * 60)
    pg_conn = get_pg_connection()
    start = time.perf_counter()
    pg_results = pg_search(pg_conn, query_emb, top_k=args.top_k)
    pg_time = (time.perf_counter() - start) * 1000
    pg_conn.close()

    if pg_results:
        for i, r in enumerate(pg_results):
            print(f"  [{i+1}] {r['similarity']:.4f} | {r['document_name']} | str. {r.get('page_number', '?')}")
            print(f"      {r['content'][:80]}...")
    else:
        print("  (žádné výsledky – spusťte nejdřív demo01)")
    print(f"  ⏱️  Čas: {pg_time:.2f} ms")

    # Oracle vyhledávání
    if has_oracle:
        print(f"\n{'='*60}")
        print("🔶 Oracle 23ai – AI Vector Search")
        print("-" * 60)
        start = time.perf_counter()
        ora_results = oracle_search(query_emb, top_k=args.top_k)
        ora_time = (time.perf_counter() - start) * 1000

        if ora_results:
            for i, r in enumerate(ora_results):
                print(f"  [{i+1}] {r['similarity']:.4f} | {r['document_name']} | str. {r.get('page_number', '?')}")
                print(f"      {r['content'][:80]}...")
        else:
            print("  (žádné výsledky – spusťte --setup a načtěte data)")
        print(f"  ⏱️  Čas: {ora_time:.2f} ms")

        # Porovnání
        print(f"\n{'='*60}")
        print("📊 Porovnání:")
        print(f"  PostgreSQL: {pg_time:.2f} ms")
        print(f"  Oracle:     {ora_time:.2f} ms")

    print(f"\n{'='*60}")
    print("✅ Hotovo!")


if __name__ == "__main__":
    main()
