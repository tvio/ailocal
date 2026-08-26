#!/usr/bin/env python3
"""Podrobny log jednoho hledani - co se deje krok za krokem.

Na rozdil od hledej.py neukazuje jen VYSLEDEK, ale cely postup: co vratil
router, cim se dotaz rozsiril, kolik radku pustil filtr, jak dopadla
podobnost u jednotlivych radku a co odriznul prah.

Slouzi ke dvema vecem:
  - vysvetlit pri predvadeni, PROC vysel prave tenhle vysledek
  - ladit, kdyz neco nesedi

Pouziti:
  uv run python log_hledani.py "mám průjem"
  uv run python log_hledani.py "mám průjem" --radku 15
"""

import io
import sys
import time
import argparse

import psycopg

from common.config import PG_DSN
from common.router import rozhodni
from common.dotazy import rozsir
from common.hledani import hledej, seskup
from common.ollama_client import embed


def cara(nadpis: str) -> None:
    print()
    print("=" * 78)
    print(nadpis)
    print("=" * 78)


def main() -> int:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    ap = argparse.ArgumentParser(description="podrobny log jednoho hledani")
    ap.add_argument("dotaz", nargs="+")
    ap.add_argument("--prah", type=float, default=0.55)
    ap.add_argument("--radku", type=int, default=12, help="kolik radku vypsat")
    a = ap.parse_args()
    dotaz = " ".join(a.dotaz)

    cara(f"DOTAZ UZIVATELE:  {dotaz!r}")

    # --- 1. router -----------------------------------------------------
    t0 = time.perf_counter()
    filtr, jistota, syrove = rozhodni(dotaz)
    t_router = time.perf_counter() - t0
    dotaz_text = syrove.get("dotaz_text") or dotaz

    cara(f"1. ROUTER  (jazykovy model, {t_router:.1f} s)")
    print("Z vety oddelil, co je FILTR a co se ma hledat vyznamove.\n")
    print(f"  filtr        {filtr.popis() or '(zadny)'}")
    print(f"  text pro vektor  {dotaz_text!r}")
    print(f"  jistota      {jistota}")
    if filtr.je_presny():
        print("  POZN: filtr obsahuje rizenou hodnotu -> prah se NEUPLATNI")

    # --- 2. rozsireni dotazu -------------------------------------------
    varianty = rozsir(dotaz_text)
    if dotaz not in varianty:
        varianty.append(dotaz)

    cara(f"2. ROZSIRENI DOTAZU  ({len(varianty)} variant)")
    print("Do vektoru nejde jen text od routeru. Bere se NEJLEPSI shoda")
    print("pres vsechny varianty, takze horsi varianta nemuze uskodit.\n")
    for i, v in enumerate(varianty, 1):
        if v == dotaz_text:
            zdroj = "router"
        elif v == dotaz:
            zdroj = "puvodni veta uzivatele (pojistka proti orezani)"
        else:
            zdroj = "slovnik_dotazu.json"
        print(f"  {i}. {v!r:52} <- {zdroj}")

    # --- 3. filtr v SQL ------------------------------------------------
    kde, par = [], {}
    if filtr.sekce:
        kde.append("s.sekce = ANY(%(sekce)s)")
        par["sekce"] = filtr.sekce
    if filtr.na_predpis is not None:
        kde.append("l.na_predpis = %(np)s")
        par["np"] = filtr.na_predpis
    if filtr.hrazeno is not None:
        kde.append("l.hrazeno = %(hr)s")
        par["hr"] = filtr.hrazeno
    podminka = f"WHERE {' AND '.join(kde)}" if kde else ""

    with psycopg.connect(PG_DSN) as c:
        celkem = c.execute("SELECT count(*) FROM leciva_search").fetchone()[0]
        po_filtru = c.execute(
            f"SELECT count(*) FROM leciva_search s JOIN leciva l USING (kod_sukl) {podminka}",
            par).fetchone()[0]

    cara("3. FILTR  (SQL WHERE, jeste PRED hledanim)")
    print("Co filtr nepusti, se do vysledku nemuze dostat ani se skvelym skore.\n")
    print(f"  radku v databazi celkem   {celkem}")
    print(f"  radku po filtru           {po_filtru}")

    # --- 4. podobnost --------------------------------------------------
    t0 = time.perf_counter()
    vektory = embed(varianty)
    t_embed = time.perf_counter() - t0

    t0 = time.perf_counter()
    o = hledej(dotaz_text, filtr=filtr, limit=200, prah=0.0, puvodni_dotaz=dotaz)
    t_sql = time.perf_counter() - t0

    cara(f"4. PODOBNOST  (embedding {t_embed:.2f} s, SQL {t_sql:.2f} s)")
    print("Kazdemu radku se spocita kosinova podobnost a fulltextovy rank.")
    print(f"Prah je {a.prah} - co je pod nim, se zahodi.\n")
    print(f"  {'':3} {'cosine':>7} {'fts':>7}  {'prah':>5}  lek / nalezeny text")
    for i, v in enumerate(o.vysledky[:a.radku], 1):
        znak = "OK " if v.cosine >= a.prah else "pod"
        print(f"  {i:2}. {v.cosine:7.3f} {v.fts:7.3f}  {znak:>5}  "
              f"{v.nazev[:13]:13} {v.obsah_text[:38]}")
    if len(o.vysledky) > a.radku:
        print(f"  ... a dalsich {len(o.vysledky) - a.radku} radku")

    # --- 5. prah + seskupeni -------------------------------------------
    o2 = hledej(dotaz_text, filtr=filtr, limit=200, prah=a.prah, puvodni_dotaz=dotaz)
    skupiny = seskup(o2.vysledky, leciv=10,
                     pasazi_na_lecivo=200 if o2.cely_usek else 3)

    cara("5. PRAH A SESKUPENI PO LECIVECH")
    print(f"  proslo prahem   {len(o2.vysledky)} radku z {len(o.vysledky)}")
    print(f"  po seskupeni    {len(skupiny)} leciv (jeden lek jednou, s nejlepsi pasazi)\n")
    for i, l in enumerate(skupiny, 1):
        v = l.nejlepsi
        print(f"  {i}. {v.cosine:.3f}  {l.nazev} {l.sila or ''}".rstrip())
        print(f"           {v.obsah_text[:64]}")
        if v.strana_pdf:
            print(f"           zdroj: SPC strana {v.strana_pdf}")

    cara("CELKOVY CAS")
    print(f"  router      {t_router:6.2f} s   <- jazykovy model, nejdrazsi cast")
    print(f"  embedding   {t_embed:6.2f} s")
    print(f"  SQL         {t_sql:6.2f} s   <- vlastni hledani")
    print(f"  celkem      {t_router + t_embed + t_sql:6.2f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
