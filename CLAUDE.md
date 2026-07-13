# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
uv sync

# Start infrastructure (Postgres 17 + pgvector + PgAdmin)
docker compose up -d

# Stop infrastructure
docker compose down

# Check Ollama availability (prints working URL or exits 1)
uv run python ollama_health.py

# Download sample data from SÚKL API (pharmaceutical SPC PDFs)
uv run python create_sample_data.py            # 5 drugs (default)
uv run python create_sample_data.py --count 10
uv run python create_sample_data.py --codes 0258021 0241858

# Run any demo script
uv run python demo01_pdf_to_vectors.py SPC_0254048_PARALEN.pdf
uv run python demo05_semantic_search.py "Jaké jsou vedlejší účinky Paralenu?"
uv run python demo12_text_to_sql.py --setup && uv run python demo12_text_to_sql.py "Kteří zákazníci utratili nejvíc?" --execute
```

## Architecture

This is a collection of 12 standalone demo scripts (Czech: "dema") demonstrating local LLM use cases for enterprise scenarios. Everything runs locally — no data leaves the network.

### Infrastructure

- **Postgres 17 + pgvector** (Docker): stores document chunks with 768-dim embeddings, section extracts, JSON extracts, and simplified texts across four tables: `document_chunks`, `extrakty`, `extrakty_json`, `simplify`.
- **Ollama**: local LLM runtime. `ollama_health.py` probes candidates in order (`127.0.0.1:11434`, then `192.168.1.215:11434`) and returns the first available URL. All `common/` modules call this at runtime.
- **PgAdmin**: http://localhost:5050 (`admin@ailocal.cz` / `admin`)
- **DB credentials**: `ailocal/ailocal` on `localhost:5432/ailocal`. A read-only role `readonly/readonly` exists for the Text-to-SQL sandbox (demo12).

### `common/` — shared modules

| Module | Purpose |
|---|---|
| `config.py` | Single source of truth for paths, model names (`MODEL_EMBED=nomic-embed-text`, `MODEL_CHAT=gemma3:12b`, `MODEL_LIGHT=ministral-3:latest`), DB DSN, chunk size (500 chars, 50 overlap) |
| `ollama_client.py` | Thin wrapper over Ollama REST API: `embed_text()`, `embed_texts()` (batch), `chat()`, `chat_with_history()`, `vision()` |
| `pdf_utils.py` | PDF text extraction (PyMuPDF) and chunking |
| `db_postgres.py` | All pgvector operations: insert/search chunks, insert/search extracts, hybrid search (RRF combining cosine + Czech fulltext), JSON extract CRUD, simplification storage |

### Demo pipeline progression

The demos build on each other in a logical sequence:
1. **demo01–02**: PDF → text chunks → embeddings → `document_chunks` table
2. **demo03–03d**: Extract specific SPC sections (regex vs. LLM vs. OpenAI vs. local) → `extrakty` / `extrakty_json` tables
3. **demo04**: Simplify medical text for lay readers → `simplify` table
4. **demo05–05x**: Semantic search / RAG over stored vectors, including hybrid search (semantic + Czech FTS via RRF)
5. **demo06–12**: Standalone demos (vision, MCP protocol, Oracle vs Postgres benchmarking, ticket classification, meeting summary, anomaly detection, text-to-SQL)

### Key patterns

- Every demo imports from `common/` — never add infrastructure logic directly to demo scripts.
- `ollama_client.get_ollama_url()` is called lazily at request time, not at import time; this allows scripts to import safely even when Ollama is offline.
- The DB schema is applied via `init-db.sql` mounted into the Docker container's `initdb.d/`; it is **not** re-run on existing volumes. To reset: `docker compose down -v && docker compose up -d`.
- `chat()` defaults to `stream=False`; pass `stream=True` to print tokens as they arrive.
- Hybrid search in `db_postgres.hybrid_search()` uses RRF (Reciprocal Rank Fusion) with configurable `sem_weight` (0–1).

### Models required in Ollama

```
nomic-embed-text   # embeddings (768-dim)
gemma3:12b         # primary chat/vision model
ministral-3:latest # lightweight model
qwen3:14b          # used in some demos
```

### Data directories (git-ignored, created locally)

- `data/pdf/` — downloaded SPC PDFs from SÚKL API
- `data/images/` — images for vision demo (demo06)
- `data/emails/`, `data/meetings/` — inputs for demo09/demo10
