#!/usr/bin/env python3
"""Srovnani lokalniho bge-m3 s cloudovymi embeddingy OpenAI.

Proc vznikl: MAALOX (0254348) ma reflux v indikaci popsany LAICKY
("vracení kyselého obsahu ze žaludku do úst"), ale slovo "reflux" tam
nepadne ani jednou. bge-m3 ho proto na dotaz "mám reflux" umisti az na
#19 ze 136. Otazka zni, jestli to silnejsi cloudovy model uhodne.

POZOR NA PENIZE: embeddingy jsou JINY produkt nez chat a jsou radove
levnejsi - text-embedding-3-small stoji 0,02 $ za milion tokenu,
3-large 0,13 $. Cely tenhle test je ~4000 tokenu, tedy zlomek centu.
Zakaz z CLAUDE.md se tyka gpt-4o (chat), ne embeddingu. Presto se
vysledky CACHUJI do souboru, aby opakovany beh nestal nic.

Pouziti:
  uv run python bench_embed_cloud.py                # jen spocita cenu
  uv run python bench_embed_cloud.py --spustit      # zavola API
"""

import io
import sys
import json
import argparse
from pathlib import Path

import psycopg
import numpy as np

from common.config import PG_DSN, nacti_openai_klic
from common.ollama_client import embed as embed_lokalne

CACHE = Path("data/bench_embed_cloud.json")

MODELY_CLOUD = ["text-embedding-3-small", "text-embedding-3-large"]

# Cena za milion tokenu v dolarech (stav 8/2026).
CENA = {"text-embedding-3-small": 0.02, "text-embedding-3-large": 0.13}

DOTAZY = ["mám reflux", "lék na reflux", "reflux",
          "pálení žáhy", "vrací se mi jídlo do krku"]

CILOVY_LEK = "MAALOX"


def nacti_indikace() -> list[tuple[str, str, str]]:
    with psycopg.connect(PG_DSN) as c:
        return c.execute("""
            SELECT s.kod_sukl, l.nazev, s.obsah_text
            FROM leciva_search s JOIN leciva l USING (kod_sukl)
            WHERE s.sekce = 'indikace'
            ORDER BY s.id
        """).fetchall()


def cos(a, b) -> float:
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)))


def poradi(dotaz_vec, texty, vektory, nazvy) -> list[tuple[int, float, str, str]]:
    """Serazene (poradi, cosine, nazev, text)."""
    sk = [(cos(dotaz_vec, v), n, t) for v, n, t in zip(vektory, nazvy, texty)]
    sk.sort(key=lambda x: -x[0])
    return [(i, c, n, t) for i, (c, n, t) in enumerate(sk, 1)]


def main() -> int:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    ap = argparse.ArgumentParser(description="bge-m3 vs cloudove embeddingy")
    ap.add_argument("--spustit", action="store_true", help="opravdu zavolat OpenAI")
    ap.add_argument("--znovu", action="store_true", help="ignorovat cache")
    a = ap.parse_args()

    radky = nacti_indikace()
    nazvy = [r[1] for r in radky]
    texty = [r[2] for r in radky]
    vse = texty + DOTAZY

    # Hruby odhad: ~1 token na 3 znaky ceskeho textu.
    znaku = sum(len(t) for t in vse)
    tokenu = znaku / 3
    print(f"Indikaci: {len(texty)}, dotazu: {len(DOTAZY)}")
    print(f"Znaku celkem: {znaku}, odhad tokenu: {tokenu:.0f}")
    for m in MODELY_CLOUD:
        print(f"  {m:26} odhad ceny: ${tokenu / 1e6 * CENA[m]:.6f}")

    if not a.spustit:
        print("\n(nic se nezavolalo - pro ostry beh pridej --spustit)")
        return 0

    # ---- cloud ----
    data = {}
    if CACHE.exists() and not a.znovu:
        data = json.loads(CACHE.read_text(encoding="utf-8"))
        print(f"\nCache {CACHE} nactena ({list(data)})")

    from openai import OpenAI
    klient = OpenAI(api_key=nacti_openai_klic())

    for model in MODELY_CLOUD:
        if model in data and not a.znovu:
            continue
        print(f"\nVolam OpenAI: {model} ({len(vse)} textu)...")
        odp = klient.embeddings.create(model=model, input=vse)
        data[model] = [d.embedding for d in odp.data]
        print(f"  skutecne spotrebovano tokenu: {odp.usage.total_tokens}"
              f"  (${odp.usage.total_tokens / 1e6 * CENA[model]:.6f})")
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(data), encoding="utf-8")

    # ---- lokalne ----
    print("\nPocitam bge-m3 lokalne...")
    data["bge-m3"] = embed_lokalne(vse)

    # ---- srovnani ----
    souhrn: dict[str, dict[str, tuple[int, float]]] = {}
    for i, dotaz in enumerate(DOTAZY):
        print("\n" + "=" * 74)
        print(f"DOTAZ: {dotaz!r}")
        print("=" * 74)
        for model in ["bge-m3"] + MODELY_CLOUD:
            v = data[model]
            vekt, dotaz_v = v[:len(texty)], v[len(texty) + i]
            por = poradi(dotaz_v, texty, vekt, nazvy)
            cil = next((p for p in por if p[2] == CILOVY_LEK), None)
            print(f"\n  {model}")
            for p, c, n, t in por[:3]:
                print(f"    #{p:<3} {c:.3f}  {n[:14]:14} {t[:40]}")
            if cil:
                print(f"    -> {CILOVY_LEK} je #{cil[0]} ze {len(texty)}, "
                      f"cosine {cil[1]:.3f}")
                souhrn.setdefault(dotaz, {})[model] = (cil[0], cil[1])

    # ---- souhrnna tabulka ----
    modely = ["bge-m3"] + MODELY_CLOUD
    print()
    print("=" * 74)
    print(f"SOUHRN: poradi leciva {CILOVY_LEK} ze {len(texty)} indikaci")
    print("=" * 74)
    print(f"{'dotaz':30}" + "".join(f"{m[:20]:>22}" for m in modely))
    for dotaz in DOTAZY:
        r = souhrn.get(dotaz, {})
        radek = f"{dotaz[:29]:30}"
        for m in modely:
            if m in r:
                radek += f"{'#' + str(r[m][0]):>8}{r[m][1]:>14.3f}"
            else:
                radek += f"{'-':>22}"
        print(radek)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
