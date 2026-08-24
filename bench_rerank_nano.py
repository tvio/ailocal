#!/usr/bin/env python3
"""Prerazeni (rerank) kandidatu z bge-m3 pomoci gpt-5-nano.

PROC: MAALOX ma reflux v indikaci popsany laicky ("vraceni kyseleho
obsahu ze zaludku do ust"), slovo "reflux" tam nepadne. bge-m3 ho proto
da az na #19 ze 136. Cloudove EMBEDDINGY to neresi (viz
bench_embed_cloud.py) - 3-large dostane MAALOX jen na #7.

gpt-5-nano embeddingy delat NEUMI:
    embeddings.create(model="gpt-5-nano")
    -> 403 "You are not allowed to generate embeddings from this model"

Umi ale neco jineho a pro tuhle ulohu vhodnejsiho: dostat kandidaty
a ROZHODNOUT, ktery lek na dotaz opravdu sedi. To je klasicky
retrieve-then-rerank: vektor zuzi 136 na 20, model 20 seradi.

POZOR NA PENIZE: gpt-5-nano je nejlevnejsi chat model a posila se mu
jen 20 kratkych radku. Skutecna spotreba se vypisuje.

Pouziti:
  uv run python bench_rerank_nano.py                     # odhad, nevola API
  uv run python bench_rerank_nano.py --spustit
  uv run python bench_rerank_nano.py --spustit --dotaz "mám reflux"
"""

import io
import sys
import json
import argparse

import psycopg

from common.config import PG_DSN, OPENAI_MODEL, nacti_openai_klic
from common.ollama_client import embed

KANDIDATU = 20
CILOVY_LEK = "MAALOX"

DOTAZY = ["mám reflux", "lék na reflux", "vrací se mi jídlo do krku"]

POKYN = """Jsi lékárník. Uživatel hledá lék na svůj problém.

Dostaneš PROBLÉM a očíslovaný seznam INDIKACÍ různých léků (text, na co
se lék používá). U každé rozhodni, jak dobře na ten problém sedí.

Hodnoť 0 až 10:
  10 = indikace ten problém přímo řeší, i když ho pojmenovává jinak
   5 = souvisí, ale není to totéž
   0 = nesouvisí

DŮLEŽITÉ: uživatel píše laicky, indikace jsou často odborné nebo naopak
opsané. Slova se nemusí shodovat vůbec - hodnoť VÝZNAM, ne slova.
Například "vracení kyselého obsahu ze žaludku do úst" JE reflux.

Vrať POUZE JSON pole, nic jiného:
[{"c": 1, "skore": 8}, {"c": 2, "skore": 0}, ...]"""


def kandidati(dotaz: str) -> list[tuple[int, str, str, float]]:
    """Top-N z bge-m3: (poradi, nazev, text, cosine)."""
    v = embed([dotaz])[0]
    with psycopg.connect(PG_DSN) as c:
        r = c.execute("""
            SELECT l.nazev, s.obsah_text, 1 - (s.embedding <=> %s::vector) AS cos
            FROM leciva_search s JOIN leciva l USING (kod_sukl)
            WHERE s.sekce = 'indikace'
            ORDER BY cos DESC LIMIT %s
        """, (str(v), KANDIDATU)).fetchall()
    return [(i, n, t, float(c)) for i, (n, t, c) in enumerate(r, 1)]


def preraz(dotaz: str, kand: list, klient) -> tuple[dict[int, int], dict]:
    radky = "\n".join(f"{i}. {t}" for i, _, t, _ in kand)
    zprava = f"PROBLÉM: {dotaz}\n\nINDIKACE:\n{radky}"
    r = klient.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "system", "content": POKYN},
                  {"role": "user", "content": zprava}],
    )
    txt = (r.choices[0].message.content or "").strip()
    if txt.startswith("```"):
        txt = txt.split("```")[1].removeprefix("json").strip()
    skore = {int(x["c"]): int(x["skore"]) for x in json.loads(txt)}
    return skore, r.usage


def main() -> int:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    ap = argparse.ArgumentParser(description="rerank kandidatu pres gpt-5-nano")
    ap.add_argument("--spustit", action="store_true")
    ap.add_argument("--dotaz", action="append")
    a = ap.parse_args()

    dotazy = a.dotaz or DOTAZY
    print(f"Model: {OPENAI_MODEL}, kandidatu na dotaz: {KANDIDATU}")
    if not a.spustit:
        print("(nic se nezavolalo - pro ostry beh pridej --spustit)")
        return 0

    from openai import OpenAI
    klient = OpenAI(api_key=nacti_openai_klic())

    vstup = vystup = 0
    for dotaz in dotazy:
        kand = kandidati(dotaz)
        skore, usage = preraz(dotaz, kand, klient)
        vstup += usage.prompt_tokens
        vystup += usage.completion_tokens

        # Prerazeni: vyssi skore vyhrava, pri shode rozhoduje puvodni poradi.
        serazene = sorted(kand, key=lambda k: (-skore.get(k[0], 0), k[0]))

        print("\n" + "=" * 74)
        print(f"DOTAZ: {dotaz!r}")
        print("=" * 74)
        print(f"{'':4}{'bge-m3':>8}  {'nano':>5}  {'nove':>5}  lek / indikace")
        for nove, (puv, nazev, text, cos) in enumerate(serazene[:6], 1):
            print(f"    {'#' + str(puv):>8}  {skore.get(puv, 0):>5}  "
                  f"{'#' + str(nove):>5}  {nazev[:13]:13} {text[:34]}")

        cil_puv = next((k for k in kand if k[1] == CILOVY_LEK), None)
        cil_nov = next((i for i, k in enumerate(serazene, 1)
                        if k[1] == CILOVY_LEK), None)
        if cil_puv:
            print(f"    -> {CILOVY_LEK}: bge-m3 #{cil_puv[0]} "
                  f"-> po prerazeni #{cil_nov} (skore {skore.get(cil_puv[0], 0)})")
        else:
            print(f"    -> {CILOVY_LEK} nebyl ani mezi {KANDIDATU} kandidaty "
                  f"- rerank ho zachranit NEMUZE")

    # gpt-5-nano: 0,05 $ / 1M vstup, 0,40 $ / 1M vystup (stav 8/2026)
    cena = vstup / 1e6 * 0.05 + vystup / 1e6 * 0.40
    print(f"\nTokeny: vstup {vstup}, vystup {vystup}  ->  ${cena:.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
