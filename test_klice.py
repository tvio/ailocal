#!/usr/bin/env python3
"""POKUS: pomohl by KLIC pro hledani u dlouhych indikaci?

Levne overeni na 10 polozkach PRED tim, nez se sahne do extrakce celeho
korpusu. Zjistuje trojici veci:

  1. umi model vyrobit pouzitelny klic (1-4 slova, 1. pad)?
  2. o kolik se zlepsi VEKTOROVA podobnost proti laickemu dotazu?
  3. o kolik se zlepsi FULLTEXT (dnes je na cestinu rozbity - v TSV je
     'prujmu' ve 2. pade, takze dotaz "průjem" nenajde nic)

Nic nezapisuje do dat ani do DB.

Pouziti:
  uv run python test_klice.py
"""

import io
import sys
import json

import psycopg
import numpy as np

from common.config import PG_DSN, MODEL_HLAVNI
from common.ollama_client import chat_detail, embed
from common.extrakce import _ocisti_odpoved

# Deset nejdelsich indikaci + k nim dotaz, jak by ho polozil laik.
# Dotazy jsou napsane RUCNE podle toho, co v te indikaci opravdu stoji -
# ne odvozene z klice, jinak by pokus meril sam sebe.
VZOREK = {
    11706: "chci zhubnout",
    10833: "mám vysoký cholesterol",
    10587: "mám nepravidelný srdeční rytmus",
    11707: "lék na hubnutí pro děti",
    10834: "vysoký cholesterol",
    10586: "mám vysoký tlak",
    10945: "mám průjem",
    10923: "svědí mě kůže a mám vyrážku",
    11139: "mám vřed na žaludku",
    10991: "prevence vředů po leku proti bolesti",
}

POKYN = """Dostaneš indikaci léčivého přípravku, jak je zapsaná v SPC.

Vrať KLÍČ pro vyhledávání: 1-4 slova, která pojmenovávají STAV nebo
NEMOC, kvůli které člověk ten lék hledá.

Klíč slouží k tomu, aby lék NAŠEL LAIK. Není to odborný název a není to
zkrácená indikace - je to heslo do vyhledávače.

PRAVIDLA:

1. **1. PÁD**, jak by to napsal člověk do vyhledávače
   "akutní průjem"   NE "akutního průjmu"

2. **DRŽ SE SLOV, KTERÁ JSOU V ZADANÉM TEXTU.** Nepřeváděj je na
   odbornější. Když text říká "kožní vyrážka se svěděním", klíč je
   "svědivá kožní vyrážka" - NE "chronická idiopatická kopřivka".
   Odborný termín použij JEN tehdy, když je i v zadaném textu.

3. **SKUPINU PACIENTŮ ZACHOVEJ**, když je v textu.
   "...hubnutí u dětí starších 12 let"  ->  "nadváha u dětí"
   NE "silná nadváha" - ztratilo by se, pro koho ten lék je.

4. Vynech slova, která nejsou názvem stavu: "léčba", "doplňková",
   "prevence", "dlouhodobé", "pokud nelze", "spolu s".

5. Když v textu ŽÁDNÝ stav ani nemoc není (je to jen výhrada nebo
   podmínka použití), vrať null.

Vrať POUZE JSON: {"klic": "..."} nebo {"klic": null}"""


def cos(a, b) -> float:
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)))


def main() -> int:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

    with psycopg.connect(PG_DSN) as c:
        radky = c.execute("""
            SELECT s.id, l.nazev, s.obsah_text
            FROM leciva_search s JOIN leciva l USING (kod_sukl)
            WHERE s.id = ANY(%s)
        """, (list(VZOREK),)).fetchall()
    podle_id = {r[0]: r for r in radky}

    print("=" * 78)
    print("1. VYROBA KLICU MODELEM")
    print("=" * 78)
    klice = {}
    for sid in VZOREK:
        _, nazev, text = podle_id[sid]
        odp, m = chat_detail(text, model=MODEL_HLAVNI, system=POKYN)
        try:
            k = json.loads(_ocisti_odpoved(odp)).get("klic")
        except json.JSONDecodeError:
            k = None
        klice[sid] = k
        print(f"  {nazev[:14]:14} ({len(text.split()):2} slov, {m.cas_celkem_s:.1f} s)")
        print(f"      text:  {text[:66]}")
        print(f"      KLIC:  {k!r}")

    pouzitelne = {s: k for s, k in klice.items() if k}
    print(f"\n  klicu vyrobeno: {len(pouzitelne)} z {len(VZOREK)}")

    # --- 2. vektorova podobnost ---
    print()
    print("=" * 78)
    print("2. VEKTOROVA PODOBNOST  (dotaz laika proti textu vs proti klici)")
    print("=" * 78)
    print(f"  {'dotaz':32}{'dnes':>8}{'klic':>8}{'lepsi z obou':>14}{'zmena':>9}")
    zlepseni = []
    for sid, dotaz in VZOREK.items():
        k = klice.get(sid)
        if not k:
            continue
        _, nazev, text = podle_id[sid]
        v = embed([dotaz, text, k])
        a, b = cos(v[0], v[1]), cos(v[0], v[2])
        zlepseni.append(max(a, b) - a)
        print(f"  {dotaz[:30]:32}{a:8.3f}{b:8.3f}{max(a, b):14.3f}{max(a, b) - a:+9.3f}")
    if zlepseni:
        print(f"\n  prumerne zlepseni: {sum(zlepseni) / len(zlepseni):+.3f}"
              f"   nejvic {max(zlepseni):+.3f}   nejmene {min(zlepseni):+.3f}")

    # --- 3. fulltext ---
    print()
    print("=" * 78)
    print("3. FULLTEXT  (dnes je na cestinu rozbity - chybi stemming)")
    print("=" * 78)
    print(f"  {'dotaz':32}{'dnes':>8}{'s klicem':>10}")
    with psycopg.connect(PG_DSN) as c:
        nulove_dnes = nulove_klic = 0
        for sid, dotaz in VZOREK.items():
            k = klice.get(sid)
            if not k:
                continue
            _, _, text = podle_id[sid]
            a, b = c.execute("""
                WITH d AS (
                    SELECT replace(websearch_to_tsquery('czech_unaccent', %s)::text,
                                   '&', '|')::tsquery AS q
                )
                SELECT ts_rank_cd(setweight(to_tsvector('czech_unaccent', %s), 'A'), d.q),
                       ts_rank_cd(setweight(to_tsvector('czech_unaccent', %s), 'A'), d.q)
                FROM d
            """, (dotaz, text, k)).fetchone()
            nulove_dnes += a == 0
            nulove_klic += b == 0
            print(f"  {dotaz[:30]:32}{a:8.3f}{b:10.3f}")
        n = len(pouzitelne)
        print(f"\n  dotazu bez jedine shody:  dnes {nulove_dnes}/{n}"
              f"   s klicem {nulove_klic}/{n}")

    # --- 4. falesne shody ---
    # Klic je kratky a obecny, tedy presne ten typ textu, ktery podle
    # drivejsiho mereni "plave nahoru ke vsemu". Merim proto i to, jestli
    # nepritahne CIZI dotazy - ne jen jestli pomuze tomu spravnemu.
    print()
    print("=" * 78)
    print("4. FALESNE SHODY  (pritahne klic i CIZI dotazy?)")
    print("=" * 78)
    dotazy = list(VZOREK.values())
    v_dot = embed(dotazy)
    horsi = 0
    print(f"  {'polozka / klic':38}{'spravny':>9}{'nejlepsi cizi':>15}{'odstup':>9}")
    for sid, spravny in VZOREK.items():
        k = klice.get(sid)
        if not k:
            continue
        _, nazev, text = podle_id[sid]
        vk = embed([k])[0]
        vt = embed([text])[0]
        for popis, vec in (("dnes (text)", vt), ("s klicem  ", vk)):
            sk = [cos(v_dot[i], vec) for i in range(len(dotazy))]
            i_spr = dotazy.index(spravny)
            cizi = max(s2 for i, s2 in enumerate(sk) if i != i_spr)
            odstup = sk[i_spr] - cizi
            if popis.startswith("s klicem") and odstup < 0:
                horsi += 1
            print(f"  {(nazev[:12] + ' ' + popis)[:36]:38}"
                  f"{sk[i_spr]:9.3f}{cizi:15.3f}{odstup:+9.3f}")
    print()
    print(f"  polozek, kde CIZI dotaz porazi spravny (s klicem): {horsi}")

    print()
    print("=" * 78)
    print("ZAVER")
    print("=" * 78)
    print("  Klic pomuze, kdyz:")
    print("   - model ho umi vyrobit u vetsiny polozek")
    print("   - vektorova podobnost stoupne vyrazne (radove +0,1 a vic)")
    print("   - fulltext prestane vracet nuly")
    print("  Kdyby ne, nema smysl sahat do extrakce celeho korpusu.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
