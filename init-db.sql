-- Inicializace databaze localsemantic.
--
-- POZOR: tenhle skript se spousti POUZE na PRAZDNEM volume. Po zmene DDL
-- je nutne `docker compose down -v && docker compose up -d`, jinak se
-- schema neaktualizuje a vypada to jako chyba ve skriptu.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS unaccent;

-- Ceska FTS konfigurace. COPY = simple znamena BEZ stemmingu - cestina
-- nema v Postgresu slovnik, takze se hleda na tvary slov. unaccent resi
-- diakritiku, aby "kuze" naslo "kuze" i "kůže".
DO $$ BEGIN
  CREATE TEXT SEARCH CONFIGURATION czech_unaccent (COPY = simple);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
ALTER TEXT SEARCH CONFIGURATION czech_unaccent
    ALTER MAPPING FOR word, hword, hword_part WITH unaccent, simple;


-- ===========================================================================
-- TABULKA 1: leciva - relacni data z API SUKL, zadny model u toho nebyl
-- ===========================================================================
CREATE TABLE leciva (
    kod_sukl            TEXT PRIMARY KEY,
    nazev               TEXT NOT NULL,
    doplnek             TEXT,          -- "500MG TBL NOB 24"
    sila                TEXT,          -- "500MG" - BEZ mezery, presne jak vraci API
    lekova_forma        TEXT,          -- "TBL NOB"
    cesta               TEXT,          -- "POR"
    atc                 TEXT,          -- "N02BE01"
    zpusob_vydeje       TEXT,          -- kod: F=volny prodej, R=na predpis, ...
    na_predpis          BOOLEAN,       -- odvozene; NULL = z kodu to nejde urcit
    -- Hrazeny z verejneho zdravotniho pojisteni. Neni to atribut leciva
    -- z detailu, ale PRISLUSNOST DO SEZNAMU: SUKL vraci na
    -- /dlp/v1/lecive-pripravky?typSeznamu=scau seznam kodu hrazenych
    -- pripravku. Je v nem kod -> hrazeny. NENI to totez co na_predpis:
    -- ABLYMICO i AMOKSIKLAV jsou na predpis a hrazene nejsou.
    hrazeno             BOOLEAN,
    registracni_cislo   TEXT,
    stav_registrace     TEXT,
    je_dodavka          BOOLEAN,
    baleni              TEXT,
    obal                TEXT,
    indikacni_skupina   INTEGER,
    ucinne_latky        TEXT[],        -- nazvy, ne kody - kvuli hledani
    eu_registrace       BOOLEAN DEFAULT FALSE,
    api_json            JSONB,         -- cela odpoved API, at se da dohledat cokoli
    vytvoreno           TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX ON leciva (atc);
CREATE INDEX ON leciva (nazev);
CREATE INDEX ON leciva (na_predpis);
CREATE INDEX ON leciva (hrazeno);


-- ===========================================================================
-- TABULKA 2: extrakty - jedna extrakce jedne sekce jednoho leku
--
-- Model je 1:N schvalne: tentyz lek a tataz sekce muze byt vytazena vic
-- zpusoby (lokalni model, cloud) a da se pak porovnavat nebo prepinat.
-- Proto je v UNIQUE i model_extrakce.
-- ===========================================================================
CREATE TABLE extrakty (
    id                  BIGSERIAL PRIMARY KEY,
    kod_sukl            TEXT NOT NULL REFERENCES leciva(kod_sukl) ON DELETE CASCADE,
    sekce               TEXT NOT NULL,   -- indikace|kontraindikace|nezadouci_ucinky|davkovani
    sekce_cislo         TEXT,            -- "4.1", "4.8" - cislo bodu v SPC
    zdrojovy_text       TEXT,            -- text sekce, ze ktereho se extrahovalo
    zdrojovy_text_orez  TEXT,            -- co z nej po orezu na jadro slo do modelu
    polozky             JSONB NOT NULL,  -- vysledek extrakce (pole polozek)
    model_extrakce      TEXT NOT NULL,
    metadata            JSONB DEFAULT '{}',   -- cas, zdroj textu, format sekce...
    vytvoreno           TIMESTAMPTZ DEFAULT now(),
    UNIQUE (kod_sukl, sekce, model_extrakce)
);

CREATE INDEX ON extrakty (kod_sukl);
CREATE INDEX ON extrakty (sekce);
CREATE INDEX ON extrakty USING gin (polozky);


-- ===========================================================================
-- TABULKA 3: leciva_search - jeden radek = jedna hledatelna polozka
-- ===========================================================================
CREATE TABLE leciva_search (
    id               BIGSERIAL PRIMARY KEY,
    kod_sukl         TEXT   NOT NULL REFERENCES leciva(kod_sukl) ON DELETE CASCADE,
    extrakt_id       BIGINT REFERENCES extrakty(id) ON DELETE CASCADE,
                     -- NULL u radku sekce='atributy' (nepochazi z PDF)

    -- ---- FILTRACNI SLOUPCE (nikdy nesmi byt v hledanem textu) ----
    sekce            TEXT NOT NULL,
    frekvence        TEXT,      -- POUZE nezadouci_ucinky
    frekvence_rank   SMALLINT,  -- 1=velmi caste ... 9=neni znamo
    organovy_system  TEXT,      -- POUZE nezadouci_ucinky, MedDRA SOC
    sekce_atributy   JSONB,     -- doplnkova pole polozky (pacient, davka...)

    -- ---- TEXTY ----
    kontext_text     TEXT,      -- identita leku; NULL u sekce='atributy'
    obsah_text       TEXT NOT NULL,
    -- zobrazovany_text tu ZAMERNE NENI - sklada se az pri vypisu

    -- ---- HLEDACI SLOUPCE ----
    embedding        vector(1024),  -- bge-m3; do vektoru jde POUZE obsah_text
    -- POZOR: kontext_text (identita leku) tu ZAMERNE NENI.
    -- Do 24.8.2026 tu byl ve vaze A a rozbijelo to razeni: identita se
    -- opakuje na KAZDEM radku leciva, takze dotaz 'paracetamol' trefil
    -- 97 radku z 994 a spravnou odpoved (radek 'atributy') dal NAKONEC -
    -- ta ma kontext_text prazdny, takze jeji shoda spadla do vahy B.
    -- Po vyhozeni: 'paracetamol' trefi 2 radky, oba 'atributy'.
    -- Priznakove dotazy ('bolest hlavy') se nezmenily vubec.
    -- Identitu prirazuje FILTR, fulltext ji jen potvrzuje.
    search_fts       tsvector GENERATED ALWAYS AS (
                         setweight(to_tsvector('czech_unaccent', coalesce(obsah_text,'')), 'A')
                     ) STORED,

    -- ---- PROVENIENCE ----
    strana_pdf       INTEGER,
    vytvoreno        TIMESTAMPTZ DEFAULT now(),

    CONSTRAINT leciva_search_sekce_chk CHECK (
        sekce IN ('atributy','indikace','kontraindikace','nezadouci_ucinky','davkovani')),
    -- Filtracni sloupce nezadoucich ucinku nesmi byt vyplnene jinde -
    -- jinak by se filtr choval nepredvidatelne.
    CONSTRAINT leciva_search_nu_chk CHECK (
        sekce = 'nezadouci_ucinky'
        OR (frekvence IS NULL AND frekvence_rank IS NULL AND organovy_system IS NULL))
);

CREATE INDEX ON leciva_search USING hnsw (embedding vector_cosine_ops);
CREATE INDEX ON leciva_search USING gin  (search_fts);
CREATE INDEX ON leciva_search (kod_sukl);
CREATE INDEX ON leciva_search (sekce);
CREATE INDEX ON leciva_search (organovy_system);
CREATE INDEX ON leciva_search (frekvence_rank);
-- POZOR: v zadani je "USING gin (atributy)", ale sloupec se jmenuje
-- sekce_atributy (prejmenovany, aby se nepletl se sekci 'atributy').
CREATE INDEX ON leciva_search USING gin  (sekce_atributy);


-- ===========================================================================
-- TABULKA 4: extrakce_stav - explicitni evidence, co se povedlo a co ne
--
-- Proc to nejde resit NULLem: NULL znamena zaroven "lek opravdu nema
-- nezadouci ucinky" i "extrakce selhala". U aplikace pro laiky je ten
-- rozdil zasadni. Uplny popis stavu je v stavy.md.
-- ===========================================================================
CREATE TABLE extrakce_stav (
    id              BIGSERIAL PRIMARY KEY,
    kod_sukl        TEXT NOT NULL REFERENCES leciva(kod_sukl) ON DELETE CASCADE,
    extrakt_id      BIGINT REFERENCES extrakty(id) ON DELETE CASCADE,
    sekce           TEXT NOT NULL,

    stav            TEXT NOT NULL,
    pocet_polozek   INTEGER,
    format_sekce    TEXT,              -- A/B/C/D/E dle analyza_formatu.py
    zdroj_textu     TEXT,              -- 'docling_md' | 'pymupdf_raw'
    model_extrakce  TEXT,
    model_kontroly  TEXT,
    duvod           TEXT,              -- proc to selhalo, slovy - pro ladeni
    cas_extrakce_s  NUMERIC,
    vytvoreno       TIMESTAMPTZ DEFAULT now(),
    UNIQUE (kod_sukl, sekce, extrakt_id),

    -- CHECK je tu zamerne: chyba v nazvu stavu se ma projevit pri vkladani,
    -- ne az tim, ze filtr tise nic nevrati. (Preklep "chibi_v_dokumentu"
    -- v kodu se odhalil prave takhle.)
    CONSTRAINT extrakce_stav_stav_chk CHECK (stav IN (
        'ok',                   -- vytazeno a overeno, da se hledat
        'neovereno',            -- vytazeno, kontrola jeste nebezela
        'castecna',             -- cast polozek se zachranit dala, cast ne
        'zamitnuto_kontrolou',  -- kontrolni model data odmitl
        'chybi_v_dokumentu',    -- sekce v SPC NENI (legitimni stav, ne chyba)
        'selhala_extrakce',     -- model nevratil validni JSON / nedodrzel schema
        'prazdna'               -- sekce v dokumentu je, ale nema zadne polozky
    ))
);

CREATE INDEX ON extrakce_stav (kod_sukl);
CREATE INDEX ON extrakce_stav (stav);
CREATE INDEX ON extrakce_stav (format_sekce);


-- ===========================================================================
-- Slovnik pojmu: odborny termin -> laicky tvar.
-- V DB kvuli tomu, aby slo pri vypisu dohledat laicky tvar i pro termin,
-- ktery se do leciva_search dostal jen odborne.
-- ===========================================================================
CREATE TABLE slovnik_pojmu (
    termin          TEXT PRIMARY KEY,   -- malymi pismeny
    laicky          TEXT NOT NULL,
    rucne_overeno   BOOLEAN DEFAULT FALSE,  -- ze slovnik_rucni.json
    vytvoreno       TIMESTAMPTZ DEFAULT now()
);


-- ===========================================================================
-- beh_log: detailni log behu jednotlivych kroku.
-- Zapisuje se NEJDRIV do souboru (prubezne, at prezije pad) a do DB az
-- davkove po skonceni kroku. DDL je i v common/log_behu.py, aby tabulka
-- vznikla i na uz bezici databazi.
-- ===========================================================================
CREATE TABLE beh_log (
    id          BIGSERIAL PRIMARY KEY,
    beh_id      TEXT NOT NULL,      -- jeden spusteny krok = jedno beh_id
    cas         TIMESTAMPTZ NOT NULL,
    krok        TEXT NOT NULL,
    lecivo      TEXT,
    sekce       TEXT,
    akce        TEXT NOT NULL,
    stav        TEXT NOT NULL,      -- slovnik ze stavy.md
    hotovo      INTEGER,
    celkem      INTEGER,
    trvani_s    NUMERIC,
    poznamka    TEXT
);
CREATE INDEX ON beh_log (beh_id);
CREATE INDEX ON beh_log (lecivo);
CREATE INDEX ON beh_log (stav);


-- Read-only role pro pripadne Text-to-SQL / prohlizeni bez rizika.
DO $$ BEGIN
  CREATE ROLE readonly LOGIN PASSWORD 'readonly';
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
GRANT CONNECT ON DATABASE localsemantic TO readonly;
GRANT USAGE ON SCHEMA public TO readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO readonly;
