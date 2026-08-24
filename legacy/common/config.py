"""Společná konfigurace pro všechna dema."""

from pathlib import Path

# --- Datové adresáře ---
DATA_DIR = Path("data")
PDF_DIR = DATA_DIR / "pdf"
IMAGES_DIR = DATA_DIR / "images"
CSV_DIR = DATA_DIR / "csv"

# --- Ollama ---
OLLAMA_TIMEOUT = 120

# Modely
MODEL_EMBED = "qwen3-embedding:8b"      # embedding, nativní dimenze (viz EMBED_DIMENSION)
#MODEL_CHAT = "qwen2.5:72b"         # generativní (český text, extrakce, vision)
MODEL_CHAT = "qwen3:32b"       #test, mensi na pomalou pamet
MODEL_LIGHT = "ministral-3:latest"     # lehký model

EMBED_DIMENSION = 4096

# --- PostgreSQL ---
PG_HOST = "localhost"
PG_PORT = 5432
PG_USER = "ailocal"
PG_PASSWORD = "ailocal"
PG_DATABASE = "ailocal"

PG_DSN = f"postgresql://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DATABASE}"

# --- Chunking ---
CHUNK_SIZE = 300          # znaků na chunk
CHUNK_OVERLAP = 50        # překryv mezi chunky
