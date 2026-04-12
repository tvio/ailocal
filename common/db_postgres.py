"""PostgreSQL + pgvector operace pro ukládání a vyhledávání chunků."""

import psycopg
from psycopg.rows import dict_row

from common.config import PG_DSN


def get_connection(dsn: str = PG_DSN) -> psycopg.Connection:
    """Vrátí nové připojení k PostgreSQL."""
    return psycopg.connect(dsn, row_factory=dict_row)


# ---------------------------------------------------------------------------
# Ukládání chunků
# ---------------------------------------------------------------------------

def insert_chunk(
    conn: psycopg.Connection,
    *,
    document_name: str,
    chunk_index: int,
    page_number: int | None,
    content: str,
    content_hash: str,
    embedding: list[float],
    metadata: dict | None = None,
) -> None:
    """Vloží jeden chunk s embeddingem do tabulky document_chunks."""
    conn.execute(
        """
        INSERT INTO document_chunks
            (document_name, chunk_index, page_number, content, content_hash, embedding, metadata)
        VALUES
            (%s, %s, %s, %s, %s, %s::vector, %s::jsonb)
        ON CONFLICT (document_name, chunk_index) DO UPDATE SET
            content = EXCLUDED.content,
            content_hash = EXCLUDED.content_hash,
            embedding = EXCLUDED.embedding,
            metadata = EXCLUDED.metadata
        """,
        (
            document_name,
            chunk_index,
            page_number,
            content,
            content_hash,
            str(embedding),
            psycopg.types.json.Json(metadata or {}),
        ),
    )


def insert_chunks_batch(
    conn: psycopg.Connection,
    document_name: str,
    chunks: list[dict],
    embeddings: list[list[float]],
) -> int:
    """Vloží dávku chunků najednou. Vrací počet vložených."""
    count = 0
    for chunk, emb in zip(chunks, embeddings):
        insert_chunk(
            conn,
            document_name=document_name,
            chunk_index=chunk["chunk_index"],
            page_number=chunk.get("page"),
            content=chunk["text"],
            content_hash=chunk["hash"],
            embedding=emb,
            metadata={"page": chunk.get("page")},
        )
        count += 1
    conn.commit()
    return count


# ---------------------------------------------------------------------------
# Vyhledávání
# ---------------------------------------------------------------------------

def search_similar(
    conn: psycopg.Connection,
    query_embedding: list[float],
    *,
    top_k: int = 5,
    document_name: str | None = None,
) -> list[dict]:
    """Vyhledá nejpodobnější chunky pomocí cosine similarity.

    Vrací: [{"id", "document_name", "content", "page_number", "similarity"}, ...]
    """
    if document_name:
        rows = conn.execute(
            """
            SELECT id, document_name, content, page_number, metadata,
                   1 - (embedding <=> %s::vector) AS similarity
            FROM document_chunks
            WHERE document_name = %s
            ORDER BY embedding <=> %s::vector
            LIMIT %s
            """,
            (str(query_embedding), document_name, str(query_embedding), top_k),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT id, document_name, content, page_number, metadata,
                   1 - (embedding <=> %s::vector) AS similarity
            FROM document_chunks
            ORDER BY embedding <=> %s::vector
            LIMIT %s
            """,
            (str(query_embedding), str(query_embedding), top_k),
        ).fetchall()
    return [dict(r) for r in rows]


def get_document_stats(conn: psycopg.Connection) -> list[dict]:
    """Vrátí statistiky dokumentů v databázi."""
    rows = conn.execute(
        """
        SELECT document_name,
               COUNT(*) AS chunk_count,
               MIN(created_at) AS first_inserted,
               MAX(created_at) AS last_inserted
        FROM document_chunks
        GROUP BY document_name
        ORDER BY document_name
        """
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Extrakty – sekce + zjednodušení (demo03, demo04, demo05b)
# ---------------------------------------------------------------------------

def insert_extrakt(
    conn: psycopg.Connection,
    *,
    document_name: str,
    typ_sekce: str,
    typ_extraktu: str,
    sekce_text: str,
    sekce_vector: list[float],
) -> None:
    """Vloží extrahovanou sekci do tabulky extrakty."""
    conn.execute(
        """
        INSERT INTO extrakty (document_name, typ_sekce, typ_extraktu, sekce_text, sekce_vector)
        VALUES (%s, %s, %s, %s, %s::vector)
        ON CONFLICT (document_name, typ_sekce, typ_extraktu) DO UPDATE SET
            sekce_text = EXCLUDED.sekce_text,
            sekce_vector = EXCLUDED.sekce_vector
        """,
        (document_name, typ_sekce, typ_extraktu, sekce_text, str(sekce_vector)),
    )
    conn.commit()


def update_extrakt_zjednoduseni(
    conn: psycopg.Connection,
    *,
    document_name: str,
    typ_sekce: str,
    typ_extraktu: str = "regex",
    zjednoduseni: str,
    zjednoduseni_vector: list[float],
) -> bool:
    """Doplní zjednodušený text a jeho embedding do existujícího extraktu."""
    cur = conn.execute(
        """
        UPDATE extrakty
        SET zjednoduseni = %s, zjednoduseni_vector = %s::vector
        WHERE document_name = %s AND typ_sekce = %s AND typ_extraktu = %s
        """,
        (zjednoduseni, str(zjednoduseni_vector), document_name, typ_sekce, typ_extraktu),
    )
    conn.commit()
    return cur.rowcount > 0


def hybrid_search(
    conn: psycopg.Connection,
    query_embedding: list[float],
    query_text: str,
    *,
    top_k: int = 5,
    sem_weight: float = 0.5,
) -> list[dict]:
    """Hybrid search – kombinace sémantického a fulltext vyhledávání (RRF).

    Vrací: [{"document_name", "typ_sekce", "sekce_text", "zjednoduseni",
             "sem_score", "fts_score", "combined_score"}, ...]
    """
    rows = conn.execute(
        """
        WITH semantic AS (
            SELECT id, 1 - (sekce_vector <=> %(vec)s::vector) AS sem_score,
                   ROW_NUMBER() OVER (ORDER BY sekce_vector <=> %(vec)s::vector) AS sem_rank
            FROM extrakty
            WHERE sekce_vector IS NOT NULL
            ORDER BY sekce_vector <=> %(vec)s::vector
            LIMIT %(limit)s
        ),
        fulltext AS (
            SELECT id,
                   ts_rank_cd(sekce_fts, websearch_to_tsquery('czech_unaccent', %(txt)s)) AS fts_score,
                   ROW_NUMBER() OVER (
                       ORDER BY ts_rank_cd(sekce_fts, websearch_to_tsquery('czech_unaccent', %(txt)s)) DESC
                   ) AS fts_rank
            FROM extrakty
            WHERE sekce_fts @@ websearch_to_tsquery('czech_unaccent', %(txt)s)
            LIMIT %(limit)s
        )
        SELECT e.id, e.document_name, e.typ_sekce, e.sekce_text, e.zjednoduseni,
               COALESCE(s.sem_score, 0) AS sem_score,
               COALESCE(f.fts_score, 0) AS fts_score,
               -- RRF (Reciprocal Rank Fusion)
               COALESCE(1.0 / (60 + s.sem_rank), 0) * %(sw)s
               + COALESCE(1.0 / (60 + f.fts_rank), 0) * (1 - %(sw)s) AS combined_score
        FROM extrakty e
        LEFT JOIN semantic s ON e.id = s.id
        LEFT JOIN fulltext f ON e.id = f.id
        WHERE s.id IS NOT NULL OR f.id IS NOT NULL
        ORDER BY combined_score DESC
        LIMIT %(limit)s
        """,
        {"vec": str(query_embedding), "txt": query_text, "limit": top_k, "sw": sem_weight},
    ).fetchall()
    return [dict(r) for r in rows]


def get_extrakty_stats(conn: psycopg.Connection) -> list[dict]:
    """Vrátí přehled extraktů v DB."""
    rows = conn.execute(
        """
        SELECT document_name, typ_sekce, typ_extraktu,
               LENGTH(sekce_text) AS sekce_len,
               LENGTH(zjednoduseni) AS zjednoduseni_len,
               sekce_vector IS NOT NULL AS has_sekce_vec,
               zjednoduseni_vector IS NOT NULL AS has_zjedn_vec
        FROM extrakty
        ORDER BY document_name, typ_sekce, typ_extraktu
        """
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Strukturované JSON extrakty (demo03d)
# ---------------------------------------------------------------------------

def insert_extrakt_json(
    conn: psycopg.Connection,
    *,
    document_name: str,
    typ_sekce: str,
    typ_modelu: str,
    sekce_json: dict,
) -> None:
    """Vloží strukturovanou JSON extrakci do tabulky extrakty_json."""
    conn.execute(
        """
        INSERT INTO extrakty_json (document_name, typ_sekce, typ_modelu, sekce_json)
        VALUES (%s, %s, %s, %s::jsonb)
        ON CONFLICT (document_name, typ_sekce, typ_modelu) DO UPDATE SET
            sekce_json = EXCLUDED.sekce_json
        """,
        (document_name, typ_sekce, typ_modelu, psycopg.types.json.Json(sekce_json)),
    )
    conn.commit()


def get_extrakty_json_stats(conn: psycopg.Connection) -> list[dict]:
    """Vrátí přehled JSON extraktů v DB."""
    rows = conn.execute(
        """
        SELECT document_name, typ_sekce, typ_modelu,
               sekce_json ? 'has_table' AS has_table_key,
               (sekce_json->>'has_table')::boolean AS has_table,
               LENGTH(sekce_json->>'text_content') AS text_len,
               jsonb_array_length(COALESCE(sekce_json->'tables', '[]'::jsonb)) AS table_count,
               created_at
        FROM extrakty_json
        ORDER BY document_name, typ_sekce, typ_modelu
        """
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Zjednodušené texty (demo04)
# ---------------------------------------------------------------------------

def get_extrakty_json_missing_embedding(conn: psycopg.Connection) -> list[dict]:
    """Vrátí záznamy z extrakty_json, které ještě nemají embedding."""
    rows = conn.execute(
        """
        SELECT id, document_name, typ_sekce, typ_modelu, sekce_json
        FROM extrakty_json
        WHERE embedding IS NULL
        ORDER BY document_name, typ_sekce
        """
    ).fetchall()
    return [dict(r) for r in rows]


def update_extrakty_json_embedding(
    conn: psycopg.Connection,
    *,
    row_id: int,
    embedding: list[float],
) -> None:
    """Uloží embedding do záznamu extrakty_json."""
    conn.execute(
        "UPDATE extrakty_json SET embedding = %s::vector WHERE id = %s",
        (str(embedding), row_id),
    )
    conn.commit()


def search_extrakty_json(
    conn: psycopg.Connection,
    query_embedding: list[float],
    *,
    top_k: int = 5,
    typ_sekce: str | None = None,
    document_name: str | None = None,
    typ_modelu: str | None = None,
) -> list[dict]:
    """Sémantické vyhledávání v extrakty_json přes cosine similarity.

    Vrací: [{"id", "document_name", "typ_sekce", "typ_modelu", "sekce_json", "similarity"}, ...]
    """
    conditions = ["embedding IS NOT NULL"]
    params: list = []
    if typ_sekce:
        conditions.append("typ_sekce = %s")
        params.append(typ_sekce)
    if document_name:
        conditions.append("document_name = %s")
        params.append(document_name)
    if typ_modelu:
        conditions.append("typ_modelu = %s")
        params.append(typ_modelu)

    where = "WHERE " + " AND ".join(conditions)
    vec = str(query_embedding)

    rows = conn.execute(
        f"""
        SELECT id, document_name, typ_sekce, typ_modelu, sekce_json,
               1 - (embedding <=> %s::vector) AS similarity
        FROM extrakty_json
        {where}
        ORDER BY embedding <=> %s::vector
        LIMIT %s
        """,
        (vec, *params, vec, top_k),
    ).fetchall()
    return [dict(r) for r in rows]


def get_json_extracts(
    conn: psycopg.Connection,
    *,
    document_name: str | None = None,
    typ_modelu: str | None = None,
) -> list[dict]:
    """Načte JSON extrakce z extrakty_json. Vrací sekce jako zdroj pro simplify."""
    conditions = []
    params = []
    if document_name:
        conditions.append("document_name = %s")
        params.append(document_name)
    if typ_modelu:
        conditions.append("typ_modelu = %s")
        params.append(typ_modelu)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = conn.execute(
        f"""
        SELECT document_name, typ_sekce, typ_modelu, sekce_json
        FROM extrakty_json
        {where}
        ORDER BY document_name, typ_sekce
        """,
        tuple(params),
    ).fetchall()
    return [dict(r) for r in rows]


def insert_simplify(
    conn: psycopg.Connection,
    *,
    document_name: str,
    typ_sekce: str,
    typ_modelu: str,
    zdroj_modelu: str,
    source_json: dict,
    simplified_json: dict,
) -> None:
    """Vloží strukturované zjednodušení do tabulky simplify."""
    conn.execute(
        """
        INSERT INTO simplify (document_name, typ_sekce, typ_modelu, zdroj_modelu,
                              source_json, simplified_json)
        VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb)
        ON CONFLICT (document_name, typ_sekce, typ_modelu, zdroj_modelu) DO UPDATE SET
            source_json = EXCLUDED.source_json,
            simplified_json = EXCLUDED.simplified_json
        """,
        (document_name, typ_sekce, typ_modelu, zdroj_modelu,
         psycopg.types.json.Json(source_json), psycopg.types.json.Json(simplified_json)),
    )
    conn.commit()


def get_simplify_stats(conn: psycopg.Connection) -> list[dict]:
    """Vrátí přehled zjednodušených textů v DB."""
    rows = conn.execute(
        """
        SELECT document_name, typ_sekce, typ_modelu, zdroj_modelu,
               LENGTH(source_json::text) AS source_len,
               LENGTH(simplified_json::text) AS json_len,
               created_at
        FROM simplify
        ORDER BY document_name, typ_sekce, typ_modelu
        """
    ).fetchall()
    return [dict(r) for r in rows]


def delete_document(conn: psycopg.Connection, document_name: str) -> int:
    """Smaže všechny chunky daného dokumentu. Vrací počet smazaných."""
    cur = conn.execute(
        "DELETE FROM document_chunks WHERE document_name = %s",
        (document_name,),
    )
    conn.commit()
    return cur.rowcount
