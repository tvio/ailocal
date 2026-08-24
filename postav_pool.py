#!/usr/bin/env python3
"""Stazeni detailu vsech leciv ze SUKL do lokalniho poolu (discovery).

Seznam z API vraci jen KODY, ATC je az v detailu - filtrovat podle ATC
tedy jde jen stazenim detailu. Trva desitky minut, proto se cachuje.
Stahnout jednou, vybirat opakovane.

  uv run python postav_pool.py
"""
import io
import sys
import logging
from pathlib import Path

from common.sukl_api import SuklClient, postav_pool

CACHE = Path("data/pool_leciv.json")

if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    pool = postav_pool(SuklClient(), cache=CACHE, vlaken=16)
    print(f"Pool ma {len(pool)} leciv, ulozen do {CACHE}")
