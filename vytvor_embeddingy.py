#!/usr/bin/env python3
"""Krok 12: embeddingy pro leciva_search.

Do vektoru jde POUZE obsah_text. Filtracni sloupce (sekce, frekvence,
organovy_system) do nej NEPATRI - opakovaly by se pres stovky radku
a znehodnotily by vektorovy prostor. Kontext leku (kontext_text) taky ne:
"PARALEN 500MG" u kazde polozky by prevazil vlastni obsah a vsechny
polozky jednoho leku by si byly navzajem podobne.

Model bge-m3 (1024 dim) - vejde se do limitu 2000 dim pro HNSW index.
Generativni model embedding NEUMI, /api/embed vraci 501.

Prubeh se loguje do souboru i do DB (viz common/log_behu.py).

Pouziti:
  uv run python vytvor_embeddingy.py             # jen chybejici
  uv run python vytvor_embeddingy.py --znovu     # prepocitat vse
  uv run python vytvor_embeddingy.py --davka 32
"""

import io
import sys
import time
import argparse

import psycopg

from common.config import PG_DSN, MODEL_EMBED, EMBED_DIMENSION
from common.log_behu import LogBehu
from common.ollama_client import embed

# Kolik textu poslat Ollame najednou. Vic = min rezie na volani, ale delsi
# odezva a horsi granularita logu.
DAVKA = 64


def main() -> int:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    ap = argparse.ArgumentParser(description="Embeddingy pro leciva_search")
    ap.add_argument("--znovu", action="store_true", help="prepocitat i hotove")
    ap.add_argument("--davka", type=int, default=DAVKA)
    ap.add_argument("--model", default=MODEL_EMBED)
    a = ap.parse_args()

    log = LogBehu("embedding")
    celkem_vlozeno = 0

    try:
        with psycopg.connect(PG_DSN) as conn:
            with conn.cursor() as cur:
                kde = "" if a.znovu else "WHERE embedding IS NULL"
                cur.execute(f"SELECT count(*) FROM leciva_search {kde}")
                celkem = cur.fetchone()[0]

            if not celkem:
                log.zaznam(None, None, "embedding", stav="prazdna",
                           hotovo=0, celkem=0,
                           poznamka="neni co pocitat, vse uz ma embedding")
                log.zaviri()
                return 0

            print(f"Model {a.model}, {EMBED_DIMENSION} dim, "
                  f"{celkem} radku po {a.davka}\n")

            # Zpracovava se po lecivech, aby slo v logu poznat, kde to je.
            with conn.cursor() as cur:
                cur.execute(f"""
                    SELECT DISTINCT l.kod_sukl, l.nazev
                    FROM leciva_search s JOIN leciva l USING (kod_sukl)
                    {kde.replace('embedding', 's.embedding')}
                    ORDER BY 1
                """)
                leciva = cur.fetchall()

            for kod, nazev in leciva:
                t0 = time.perf_counter()
                with conn.cursor() as cur:
                    podminka = "" if a.znovu else "AND embedding IS NULL"
                    cur.execute(f"""
                        SELECT id, sekce, obsah_text FROM leciva_search
                        WHERE kod_sukl = %s {podminka} ORDER BY id
                    """, (kod,))
                    radky = cur.fetchall()

                if not radky:
                    continue

                hotovo = 0
                chyba = ""
                for zac in range(0, len(radky), a.davka):
                    davka = radky[zac:zac + a.davka]
                    try:
                        vektory = embed([r[2] for r in davka], model=a.model)
                    except Exception as e:
                        chyba = f"{type(e).__name__}: {e}"[:100]
                        break

                    with conn.cursor() as cur:
                        cur.executemany(
                            "UPDATE leciva_search SET embedding = %s WHERE id = %s",
                            [(str(v), r[0]) for v, r in zip(vektory, davka)])
                    conn.commit()
                    hotovo += len(davka)

                celkem_vlozeno += hotovo
                log.zaznam(f"{kod}_{nazev}"[:30], None, "embedding",
                           stav="ok" if not chyba else "selhala_extrakce",
                           hotovo=hotovo, celkem=len(radky),
                           trvani_s=time.perf_counter() - t0, poznamka=chyba)

            # Kontrola, ze nezustal radek bez vektoru - hledani by ho tise
            # vynechalo a nikdo by si toho nevsiml.
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM leciva_search WHERE embedding IS NULL")
                bez = cur.fetchone()[0]
                cur.execute("SELECT count(*) FROM leciva_search")
                vsech = cur.fetchone()[0]

            log.zaznam(None, None, "kontrola",
                       stav="ok" if bez == 0 else "castecna",
                       hotovo=vsech - bez, celkem=vsech,
                       poznamka="" if bez == 0 else f"{bez} radku ZUSTALO bez vektoru")
    finally:
        log.zaviri()

    print(f"\nSpocitano {celkem_vlozeno} embeddingu.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
