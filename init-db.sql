-- Inicializace databáze pro ailocal dema
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS unaccent;

-- Česká FTS konfigurace s unaccent (odstraní diakritiku při hledání)
DO $$ BEGIN
  CREATE TEXT SEARCH CONFIGURATION czech_unaccent (COPY = simple);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
ALTER TEXT SEARCH CONFIGURATION czech_unaccent ALTER MAPPING FOR word WITH unaccent, simple;

-- Tabulka pro uložení chunků dokumentů s vektory
CREATE TABLE IF NOT EXISTS document_chunks (
    id SERIAL PRIMARY KEY,
    document_name TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    page_number INTEGER,
    content TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    embedding vector(768),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(document_name, chunk_index)
);

-- Index pro vektorové vyhledávání (cosine similarity)
CREATE INDEX IF NOT EXISTS idx_chunks_embedding
    ON document_chunks USING hnsw (embedding vector_cosine_ops);

-- Index pro filtrování podle dokumentu
CREATE INDEX IF NOT EXISTS idx_chunks_document
    ON document_chunks (document_name);

-- Tabulka pro extrakty sekcí a zjednodušené texty (demo03, demo04, demo05b)
CREATE TABLE IF NOT EXISTS extrakty (
    id                  SERIAL PRIMARY KEY,
    document_name       TEXT NOT NULL,
    typ_sekce           TEXT NOT NULL,           -- indikace, davkovani, kontraindikace, vedlejsi_ucinky, slozeni
    typ_extraktu        TEXT NOT NULL DEFAULT 'regex', -- regex / llm
    sekce_text          TEXT NOT NULL,            -- originální odborný text sekce
    zjednoduseni        TEXT,                     -- zjednodušený text pro laika (demo04)
    sekce_vector        vector(768),              -- embedding originální sekce
    zjednoduseni_vector vector(768),              -- embedding zjednodušeného textu
    sekce_fts           tsvector                  -- fulltext index originální sekce
        GENERATED ALWAYS AS (to_tsvector('czech_unaccent', sekce_text)) STORED,
    zjednoduseni_fts    tsvector                  -- fulltext index zjednodušení
        GENERATED ALWAYS AS (to_tsvector('czech_unaccent', COALESCE(zjednoduseni, ''))) STORED,
    created_at          TIMESTAMPTZ DEFAULT now(),
    UNIQUE(document_name, typ_sekce, typ_extraktu)
);

-- Vektorový index pro sémantické vyhledávání v extraktech
CREATE INDEX IF NOT EXISTS idx_extrakty_sekce_vector
    ON extrakty USING hnsw (sekce_vector vector_cosine_ops);

CREATE INDEX IF NOT EXISTS idx_extrakty_zjednoduseni_vector
    ON extrakty USING hnsw (zjednoduseni_vector vector_cosine_ops);

-- GIN indexy pro fulltext vyhledávání
CREATE INDEX IF NOT EXISTS idx_extrakty_sekce_fts
    ON extrakty USING gin (sekce_fts);

CREATE INDEX IF NOT EXISTS idx_extrakty_zjednoduseni_fts
    ON extrakty USING gin (zjednoduseni_fts);

-- Index pro filtrování
CREATE INDEX IF NOT EXISTS idx_extrakty_document
    ON extrakty (document_name);

-- Tabulka pro strukturované JSON extrakce sekcí (demo03d)
CREATE TABLE IF NOT EXISTS extrakty_json (
    id              SERIAL PRIMARY KEY,
    document_name   TEXT NOT NULL,
    typ_sekce       TEXT NOT NULL,           -- indikace, davkovani, kontraindikace, vedlejsi_ucinky, slozeni, interakce
    typ_modelu      TEXT NOT NULL,           -- openai(gpt-5.4-nano), ollama(gemma3:12b)
    sekce_json      JSONB NOT NULL,          -- strukturovaný výstup (text, tabulky, metadata)
    embedding       vector(768),             -- embedding text_content + tabulky (pro demo05b)
    created_at      TIMESTAMPTZ DEFAULT now(),
    UNIQUE(document_name, typ_sekce, typ_modelu)
);

CREATE INDEX IF NOT EXISTS idx_extrakty_json_document
    ON extrakty_json (document_name);

CREATE INDEX IF NOT EXISTS idx_extrakty_json_gin
    ON extrakty_json USING gin (sekce_json);

CREATE INDEX IF NOT EXISTS idx_extrakty_json_embedding
    ON extrakty_json USING hnsw (embedding vector_cosine_ops);

-- Tabulka pro strukturované zjednodušení sekcí (demo04)
CREATE TABLE IF NOT EXISTS simplify (
    id              SERIAL PRIMARY KEY,
    document_name   TEXT NOT NULL,
    typ_sekce       TEXT NOT NULL,           -- indikace, davkovani, vedlejsi_ucinky, ...
    typ_modelu      TEXT NOT NULL,           -- kdo zjednodušil: ollama(gemma3:12b), openai(gpt-5.4-nano)
    zdroj_modelu    TEXT NOT NULL,           -- odkud JSON zdroj: openai(gpt-5.4-nano), ollama(gemma3:12b)
    source_json     JSONB NOT NULL,          -- původní sekce_json z extrakty_json (pro přímé porovnání)
    simplified_json JSONB NOT NULL,          -- strukturovaný JSON výstup (per-section schema)
    created_at      TIMESTAMPTZ DEFAULT now(),
    UNIQUE(document_name, typ_sekce, typ_modelu, zdroj_modelu)
);

CREATE INDEX IF NOT EXISTS idx_simplify_document
    ON simplify (document_name);

CREATE INDEX IF NOT EXISTS idx_simplify_json_gin
    ON simplify USING gin (simplified_json);

-- Read-only role pro UC12 (Text-to-SQL sandbox)
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'readonly') THEN
        CREATE ROLE readonly LOGIN PASSWORD 'readonly';
    END IF;
END
$$;
GRANT CONNECT ON DATABASE ailocal TO readonly;
GRANT USAGE ON SCHEMA public TO readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO readonly;
