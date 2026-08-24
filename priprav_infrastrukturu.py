#!/usr/bin/env python3
"""Zalozi soubory, ktere docker compose potrebuje, ale nejsou v gitu.

Jde hlavne o `pgpass`. Ten je v .gitignore (obsahuje heslo), takze po
naklonovani repozitare chybi - a to je zradne: Docker si na miste
chybejiciho bind-mountu vyrobi ADRESAR, pgadmin pak nenabehne a chyba
na to nijak neukazuje. Overeno v praxi, stalo to hodinu hledani.

Skript je idempotentni, da se poustet opakovane.

Pouziti:
  uv run python priprav_infrastrukturu.py
"""

import shutil
import sys
from pathlib import Path

from common.config import PG_HOST, PG_PORT, PG_DATABASE, PG_USER, PG_PASSWORD

PGPASS = Path("pgpass")

# Vsechny soubory, ktere docker-compose bind-mountuje. Kdyz nekterykoli
# chybi, Docker na jeho miste vyrobi ADRESAR - a to plati pro VSECHNY,
# ne jen pro pgpass. Overeno: pgadmin-servers.json byl na disku jako
# prazdny adresar po starem behu.
BIND_MOUNTY = [Path("pgpass"), Path("pgadmin-servers.json"), Path("init-db.sql")]


def main() -> int:
    # Kdyz uz Docker stihl vyrobit adresar, musi se smazat - jinak se
    # soubor nezalozi a chyba se bude opakovat.
    for cesta in BIND_MOUNTY:
        if cesta.is_dir():
            print(f"POZOR: {cesta} je ADRESAR (vyrobil ho Docker), mazu ho")
            shutil.rmtree(cesta)

    chybi = [c for c in BIND_MOUNTY if c != PGPASS and not c.exists()]
    if chybi:
        print("CHYBI soubory, ktere jsou v gitu - obnov je pres git checkout:",
              file=sys.stderr)
        for c in chybi:
            print(f"    {c}", file=sys.stderr)
        return 1

    # Format: host:port:database:user:password
    # Hostname je 'postgres' - jmeno sluzby v docker-compose, ne localhost,
    # protoze pgadmin se pripojuje zevnitr site kontejneru.
    radek = f"postgres:{PG_PORT}:{PG_DATABASE}:{PG_USER}:{PG_PASSWORD}\n"

    if PGPASS.exists() and PGPASS.read_text(encoding="utf-8") == radek:
        print(f"{PGPASS} uz je v poradku")
    else:
        PGPASS.write_text(radek, encoding="utf-8")
        print(f"{PGPASS} zalozen")

    print(f"\nPripojeni z hostitele: {PG_HOST}:{PG_PORT}/{PG_DATABASE} "
          f"({PG_USER}/{PG_PASSWORD})")
    print("pgAdmin: http://localhost:5050  (admin@localsemantic.cz / admin)")
    print("\nSpusteni:")
    print("    docker compose up -d")
    print("Po ZMENE init-db.sql je nutne smazat i volume, jinak se schema")
    print("neaktualizuje (init skript bezi jen na prazdnem volume):")
    print("    docker compose down -v && docker compose up -d")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
