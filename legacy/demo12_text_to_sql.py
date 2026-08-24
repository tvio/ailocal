#!/usr/bin/env python3
"""UC12 – Generování SQL z přirozeného jazyka (Text-to-SQL).

Uživatel popíše dotaz česky, LLM vygeneruje SQL, který se spustí na reálné DB.

Použití:
  uv run python demo12_text_to_sql.py "Kolik objednávek bylo v březnu?"
  uv run python demo12_text_to_sql.py "Kteří zákazníci utratili nejvíc?" --execute
  uv run python demo12_text_to_sql.py --setup   # vytvoří ukázkové tabulky
  uv run python demo12_text_to_sql.py --interactive
"""

import sys
import argparse

import psycopg
from psycopg.rows import dict_row

from common.config import PG_DSN, MODEL_CHAT
from common.ollama_client import get_ollama_url, chat


# DDL pro ukázkové tabulky
SETUP_SQL = """\
-- Ukázkové tabulky pro Text-to-SQL demo

DROP TABLE IF EXISTS objednavky CASCADE;
DROP TABLE IF EXISTS zakaznici CASCADE;
DROP TABLE IF EXISTS produkty CASCADE;

CREATE TABLE zakaznici (
    id SERIAL PRIMARY KEY,
    jmeno TEXT NOT NULL,
    email TEXT,
    mesto TEXT,
    registrace DATE DEFAULT CURRENT_DATE
);

CREATE TABLE produkty (
    id SERIAL PRIMARY KEY,
    nazev TEXT NOT NULL,
    kategorie TEXT,
    cena NUMERIC(10,2) NOT NULL
);

CREATE TABLE objednavky (
    id SERIAL PRIMARY KEY,
    zakaznik_id INTEGER REFERENCES zakaznici(id),
    produkt_id INTEGER REFERENCES produkty(id),
    pocet INTEGER NOT NULL DEFAULT 1,
    datum DATE DEFAULT CURRENT_DATE,
    stav TEXT DEFAULT 'nová' CHECK (stav IN ('nová', 'zpracovaná', 'odeslaná', 'doručená', 'zrušená'))
);

-- Ukázková data
INSERT INTO zakaznici (jmeno, email, mesto, registrace) VALUES
    ('Jan Novák', 'jan@firma.cz', 'Praha', '2025-06-01'),
    ('Petra Svobodová', 'petra@email.cz', 'Brno', '2025-08-15'),
    ('Martin Dvořák', 'martin@dvarak.cz', 'Ostrava', '2025-09-20'),
    ('Lucie Černá', 'lucie@cerna.cz', 'Praha', '2025-11-01'),
    ('Tomáš Horák', 'tomas@firma.cz', 'Plzeň', '2026-01-10');

INSERT INTO produkty (nazev, kategorie, cena) VALUES
    ('Notebook Dell Latitude', 'elektronika', 28990.00),
    ('Monitor 27"', 'elektronika', 8990.00),
    ('Klávesnice mechanická', 'příslušenství', 2490.00),
    ('Myš bezdrátová', 'příslušenství', 890.00),
    ('Webcam HD', 'příslušenství', 1990.00),
    ('Toner HP', 'spotřební', 1290.00),
    ('Papír A4 (5 balení)', 'spotřební', 590.00);

INSERT INTO objednavky (zakaznik_id, produkt_id, pocet, datum, stav) VALUES
    (1, 1, 1, '2026-01-15', 'doručená'),
    (1, 3, 2, '2026-01-15', 'doručená'),
    (2, 2, 1, '2026-02-01', 'doručená'),
    (2, 4, 1, '2026-02-01', 'doručená'),
    (3, 6, 5, '2026-02-10', 'odeslaná'),
    (3, 7, 10, '2026-02-10', 'odeslaná'),
    (4, 1, 1, '2026-03-01', 'zpracovaná'),
    (4, 5, 1, '2026-03-01', 'zpracovaná'),
    (5, 3, 1, '2026-03-15', 'nová'),
    (1, 2, 2, '2026-03-20', 'nová'),
    (2, 6, 3, '2026-03-25', 'nová'),
    (3, 1, 1, '2026-03-28', 'zrušená');
"""

# Schéma pro systémový prompt (bez dat)
SCHEMA_DESCRIPTION = """\
Databáze obsahuje tyto tabulky:

CREATE TABLE zakaznici (
    id SERIAL PRIMARY KEY,
    jmeno TEXT NOT NULL,        -- celé jméno zákazníka
    email TEXT,
    mesto TEXT,                  -- město zákazníka
    registrace DATE             -- datum registrace
);

CREATE TABLE produkty (
    id SERIAL PRIMARY KEY,
    nazev TEXT NOT NULL,         -- název produktu
    kategorie TEXT,              -- 'elektronika', 'příslušenství', 'spotřební'
    cena NUMERIC(10,2) NOT NULL -- cena za kus v CZK
);

CREATE TABLE objednavky (
    id SERIAL PRIMARY KEY,
    zakaznik_id INTEGER REFERENCES zakaznici(id),
    produkt_id INTEGER REFERENCES produkty(id),
    pocet INTEGER NOT NULL DEFAULT 1,
    datum DATE DEFAULT CURRENT_DATE,
    stav TEXT  -- 'nová', 'zpracovaná', 'odeslaná', 'doručená', 'zrušená'
);
"""

SQL_SYSTEM = f"""\
Jsi SQL expert. Na základě otázky v češtině vygeneruješ PostgreSQL dotaz.

{SCHEMA_DESCRIPTION}

Pravidla:
- Generuj POUZE SELECT dotazy (žádné INSERT, UPDATE, DELETE, DROP).
- Vrať POUZE SQL dotaz, žádný jiný text.
- Používej české aliasy pro sloupce ve výstupu (AS "Zákazník" apod.).
- Pokud otázka nedává smysl vzhledem ke schématu, vysvětli proč.
"""


def setup_database(dsn: str) -> None:
    """Vytvoří ukázkové tabulky a data."""
    conn = psycopg.connect(dsn)
    try:
        conn.execute(SETUP_SQL)
        conn.commit()
        print("  ✓ Ukázkové tabulky vytvořeny (zakaznici, produkty, objednavky)")
        # Ověření
        counts = {}
        for table in ["zakaznici", "produkty", "objednavky"]:
            row = conn.execute(f"SELECT COUNT(*) AS cnt FROM {table}").fetchone()
            counts[table] = row[0]
        print(f"  ✓ Data: {counts['zakaznici']} zákazníků, {counts['produkty']} produktů, {counts['objednavky']} objednávek")
    finally:
        conn.close()


def generate_sql(question: str, *, model: str, base_url: str) -> str:
    """Vygeneruje SQL dotaz z české otázky."""
    return chat(question, system=SQL_SYSTEM, model=model, base_url=base_url)


def execute_sql(sql: str, dsn: str) -> list[dict] | str:
    """Spustí SQL dotaz (READ-ONLY) a vrátí výsledky."""
    # Bezpečnostní kontrola
    sql_upper = sql.upper().strip()
    forbidden = ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE", "GRANT", "REVOKE"]
    for keyword in forbidden:
        if keyword in sql_upper.split():
            return f"⛔ Zakázaný příkaz: {keyword}. Povoleny jsou pouze SELECT dotazy."

    conn = psycopg.connect(dsn, row_factory=dict_row)
    try:
        rows = conn.execute(sql).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        return f"Chyba při spuštění SQL: {e}"
    finally:
        conn.close()


def format_results(results: list[dict] | str) -> str:
    """Formátuje výsledky do čitelné tabulky."""
    if isinstance(results, str):
        return results

    if not results:
        return "(prázdný výsledek)"

    # Hlavička
    headers = list(results[0].keys())
    col_widths = {h: len(str(h)) for h in headers}
    for row in results:
        for h in headers:
            col_widths[h] = max(col_widths[h], len(str(row.get(h, ""))))

    # Formátování
    header_line = " | ".join(str(h).ljust(col_widths[h]) for h in headers)
    separator = "-+-".join("-" * col_widths[h] for h in headers)
    lines = [header_line, separator]
    for row in results:
        line = " | ".join(str(row.get(h, "")).ljust(col_widths[h]) for h in headers)
        lines.append(line)

    return "\n".join(lines)


def interactive_mode(*, model: str, base_url: str, dsn: str) -> None:
    """Interaktivní režim – uživatel zadává otázky opakovaně."""
    print("\n🔄 Interaktivní režim (napište 'konec' pro ukončení)\n")
    while True:
        try:
            question = input("❓ Vaše otázka: ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if question.lower() in ("konec", "exit", "quit", "q"):
            break

        if not question:
            continue

        print(f"\n⏳ Generuji SQL...")
        sql = generate_sql(question, model=model, base_url=base_url)
        # Vyčistíme SQL (odstraníme markdown backticky)
        clean_sql = sql.strip().strip("`").strip()
        if clean_sql.lower().startswith("sql"):
            clean_sql = clean_sql[3:].strip()

        print(f"\n📝 Vygenerovaný SQL:\n{clean_sql}\n")

        answer = input("▶️  Spustit? (a/n): ").strip().lower()
        if answer in ("a", "y", "ano", "yes"):
            results = execute_sql(clean_sql, dsn)
            print(f"\n📊 Výsledky:\n{format_results(results)}\n")
        print()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="UC12 – Generování SQL z přirozeného jazyka"
    )
    parser.add_argument("query", nargs="*", help="Otázka v češtině")
    parser.add_argument("--setup", action="store_true", help="Vytvořit ukázkové tabulky")
    parser.add_argument("--execute", action="store_true", help="Automaticky spustit vygenerovaný SQL")
    parser.add_argument("--interactive", action="store_true", help="Interaktivní režim")
    parser.add_argument("--model", default=MODEL_CHAT, help=f"Model (výchozí {MODEL_CHAT})")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    print("=" * 60)
    print("UC12 – Generování SQL z přirozeného jazyka")
    print("=" * 60)

    if args.setup:
        print("\n🔧 Vytvářím ukázkové tabulky...")
        setup_database(PG_DSN)
        print("\n✅ Setup hotov!")
        return

    base_url = get_ollama_url()
    print(f"\n🤖 Model:  {args.model}")
    print(f"  ✓ Ollama: {base_url}")

    if args.interactive:
        interactive_mode(model=args.model, base_url=base_url, dsn=PG_DSN)
        print("✅ Konec interaktivního režimu.")
        return

    if not args.query:
        print("\nChyba: zadejte otázku nebo použijte --setup / --interactive", file=sys.stderr)
        sys.exit(1)

    question = " ".join(args.query)
    print(f"\n❓ Otázka: {question}")

    print(f"\n⏳ Generuji SQL...\n")
    sql = generate_sql(question, model=args.model, base_url=base_url)

    # Vyčistíme SQL
    clean_sql = sql.strip().strip("`").strip()
    if clean_sql.lower().startswith("sql"):
        clean_sql = clean_sql[3:].strip()

    print(f"\n📝 Vygenerovaný SQL:\n{clean_sql}")

    if args.execute:
        print(f"\n▶️  Spouštím dotaz...")
        results = execute_sql(clean_sql, PG_DSN)
        print(f"\n📊 Výsledky:\n{format_results(results)}")

    print(f"\n{'='*60}")
    print("✅ Hotovo!")


if __name__ == "__main__":
    main()
