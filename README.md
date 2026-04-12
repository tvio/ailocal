# ailocal – Dema použití lokálních LLM pro podnikovou praxi

Sada 12 samostatných demo skriptů ukazujících reálné možnosti lokálních LLM (Ollama) v podnikové praxi. Vše běží lokálně – žádná data neopouštějí firemní síť.

## Rychlý start

```bash
# 1. Nainstalovat závislosti
uv sync

# 2. Spustit infrastrukturu (Postgres + pgvector + PgAdmin)
docker compose up -d

# 3. Stáhnout ukázková data (SPC léků z SÚKL API)
uv run python create_sample_data.py

# 4. Zpracovat PDF do vektorů (UC1)
uv run python demo01_pdf_to_vectors.py SPC_0254048_PARALEN.pdf

# 5. Sémantické vyhledávání (UC5 – RAG)
uv run python demo05_semantic_search.py "Jaké jsou vedlejší účinky Paralenu?"
```

## Požadavky

- **Python 3.13+** s [uv](https://docs.astral.sh/uv/)
- **Docker** (pro Postgres + PgAdmin)
- **Ollama** s modely: `nomic-embed-text`, `gemma3:12b`, `qwen3:14b`, `minitral-3:latest`
- **GPU:** Nvidia RTX 3060 12GB (nebo remote Ollama na `192.168.1.215:11434`)

## Přehled dem

| Demo | Popis | Spuštění |
|------|-------|----------|
| **01** | PDF → vektory (chunking + embedding + pgvector) | `demo01_pdf_to_vectors.py SPC_0254048_PARALEN.pdf` |
| **02** | Více PDF → společná vektorová DB | `demo02_multi_pdf_vectors.py` |
| **03** | Extrakce konkrétní sekce z PDF (regex vs. LLM) | `demo03_pdf_section_extract.py SPC_0254048_PARALEN.pdf` |
| **04** | Zjednodušení odborného textu pro laika | `demo04_simplify_text.py SPC_0254048_PARALEN.pdf` |
| **05** | Sémantické vyhledávání – RAG pipeline | `demo05_semantic_search.py "otázka česky"` |
| **06** | Zpracování obrazu (vision – popis, OCR, kategorizace) | `demo06_image_analysis.py faktura.jpg` |
| **07** | MCP protokol – LLM s nástroji | `demo07_mcp_protocol.py "Kolik je 15% z 84000?"` |
| **08** | Oracle 23ai vs. Postgres pgvector – porovnání | `demo08_oracle_vs_postgres.py --benchmark` |
| **09** | Klasifikace e-mailů / helpdesk tiketů | `demo09_classify_tickets.py` |
| **10** | Sumarizace zápisu z porady | `demo10_meeting_summary.py` |
| **11** | Detekce anomálií v strukturovaných datech | `demo11_anomaly_detection.py` |
| **12** | Generování SQL z přirozeného jazyka | `demo12_text_to_sql.py --setup && demo12_text_to_sql.py "Kteří zákazníci utratili nejvíc?" --execute` |

## Infrastruktura

```bash
# Docker kontejnery
docker compose up -d      # Postgres 18 + pgvector + PgAdmin
docker compose down        # Zastavit

# PgAdmin: http://localhost:5050 (admin@ailocal.cz / admin)
# Postgres: localhost:5432 (ailocal / ailocal)
```

## Struktura projektu

```
ailocal/
├── common/                     # Sdílené moduly
│   ├── config.py               # Konfigurace (URL, modely, DB)
│   ├── ollama_client.py        # Ollama API wrapper (chat, embed, vision)
│   ├── pdf_utils.py            # Extrakce textu z PDF, chunking
│   └── db_postgres.py          # PostgreSQL + pgvector operace
├── data/                       # Vstupní data (stahují se ze SÚKL API)
│   └── pdf/                    # SPC příbalové letáky
├── demo01–demo12               # Jednotlivá dema (viz tabulka výše)
├── create_sample_data.py       # Stahování SPC z SÚKL API
├── chat_self.py                # Bonus: dva AI agenti si povídají
├── docker-compose.yml          # Postgres + pgvector + PgAdmin
├── init-db.sql                 # Inicializace DB schématu
└── pyproject.toml
```

## Data – SÚKL API

SPC dokumenty se stahují z veřejného API SÚKL (`https://prehledy.sukl.cz/dlp/v1`). Vychází z projektu [tvio/ai4](https://github.com/tvio/ai4).

```bash
uv run python create_sample_data.py                # 5 léků (výchozí)
uv run python create_sample_data.py --count 10     # 10 léků
uv run python create_sample_data.py --codes 0258021 0241858  # konkrétní kódy SÚKL
```
