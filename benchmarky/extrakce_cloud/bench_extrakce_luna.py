#!/usr/bin/env python3
"""Cena a realna ukazka CELE extrakce v cloudu (gpt-6-luna) na korpusu.

Rozhodnuto 29.9.2026: extrakce jde do cloudu CELA (doslovne + laicky
+ klic + frekvence + SOC jednim volanim, stejny prompt jako produkce -
common/extrakce.py). Tenhle skript odpovida na dve otazky:

  1) KOLIK TO STOJI na celem korpusu. Vstup = system + prompt sekce +
     orezany text (presne to, co jde do modelu), spocitany tiktokenem
     pres vsech ~23 500 sekci. Vystup se odhadne z pomeru vystup/vstup
     namereneho na realnych bezich.
  2) JAK TO VYPADA na malem, strednim a velkem SPC (podle souctu delky
     4 sekci po orezu: percentil 10, 50 a 95).

Volani: temperature 0, seed, reasoning_effort "none" (config).

Pouziti (z korene projektu):
  uv run python benchmarky/extrakce_cloud/bench_extrakce_luna.py --tokeny
  uv run python benchmarky/extrakce_cloud/bench_extrakce_luna.py --beh
  uv run python benchmarky/extrakce_cloud/bench_extrakce_luna.py --tokeny --beh
"""

import io
import sys
import json
import time
import argparse
from pathlib import Path
from statistics import median

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from common.config import DATA_DIR, OPENAI_MODEL          # noqa: E402
from common.sekce import SEKCE_SPC                         # noqa: E402
from common.extrakce import PROMPTY, SYSTEM_PROMPT, extrahuj_sekci  # noqa: E402

TADY = Path(__file__).parent
VYSLEDEK = TADY / "bench_extrakce_luna.json"

# gpt-6-luna, $ za 1M tokenu (overeno 23.9.2026, config.py). Batch API -50 %.
CENA_VSTUP, CENA_VYSTUP = 0.10, 0.50
BATCH_SLEVA = 0.5


def korpus() -> list[Path]:
    """Slozky SPC s rozparsovanymi sekcemi (jen pouzivane kody)."""
    import re
    import sqlite3
    c = sqlite3.connect(DATA_DIR / "spc" / "_stav.sqlite")
    ids = sorted(i for (i,) in c.execute(
        "SELECT DISTINCT identita FROM kody WHERE identita IS NOT NULL"))
    return [DATA_DIR / "spc" / re.sub(r"[^\w.-]+", "_", i)[:80] for i in ids]


def vstup_modelu(adr: Path, sekce: str) -> str | None:
    """Orezany text = to, co jde do modelu. _orez.md existuje jen kdyz se lisi."""
    orez = adr / "sekce" / f"{sekce}_orez.md"
    plny = adr / "sekce" / f"{sekce}.md"
    if orez.exists():
        return orez.read_text(encoding="utf-8")
    if plny.exists():
        return plny.read_text(encoding="utf-8")
    return None


def spocitej_tokeny() -> dict:
    import tiktoken
    enc = tiktoken.get_encoding("o200k_base")
    rezie = {s: len(enc.encode(SYSTEM_PROMPT)) + len(enc.encode(PROMPTY[s])) + 20
             for s in SEKCE_SPC}
    po_sekci = {s: {"volani": 0, "text_tok": 0, "znaku": 0} for s in SEKCE_SPC}
    delky = {}                      # adr -> soucet znaku 4 sekci
    for n, adr in enumerate(korpus(), 1):
        soucet = 0
        for s in SEKCE_SPC:
            t = vstup_modelu(adr, s)
            if not t or len(t.strip()) < 20:
                continue
            po_sekci[s]["volani"] += 1
            po_sekci[s]["text_tok"] += len(enc.encode(t))
            po_sekci[s]["znaku"] += len(t)
            soucet += len(t)
        delky[adr.name] = soucet
        if n % 1000 == 0:
            print(f"  ... {n}", flush=True)
    for s, v in po_sekci.items():
        v["rezie_tok_na_volani"] = rezie[s]
        v["vstup_tok"] = v["text_tok"] + v["volani"] * rezie[s]
    return {"po_sekci": po_sekci, "delky": delky}


def vyber_vzorek(delky: dict) -> dict:
    """Male / stredni / velke SPC podle percentilu delky, jen s konverzi 'ok'."""
    ok = []
    for jmeno, d in delky.items():
        k = DATA_DIR / "spc" / jmeno / "kontrola.json"
        if d and k.exists() and json.loads(k.read_text(encoding="utf-8")).get("verdikt") == "ok":
            ok.append((d, jmeno))
    ok.sort()
    return {nazev: ok[int(len(ok) * p)][1]
            for nazev, p in (("male", 0.10), ("stredni", 0.50), ("velke", 0.95))}


def beh(vzorek: dict) -> list[dict]:
    zaznamy = []
    for velikost, jmeno in vzorek.items():
        adr = DATA_DIR / "spc" / jmeno
        cil = TADY / "vystupy" / jmeno
        cil.mkdir(parents=True, exist_ok=True)
        for s in SEKCE_SPC:
            plny = adr / "sekce" / f"{s}.md"
            if not plny.exists():
                continue
            v = extrahuj_sekci(s, plny.read_text(encoding="utf-8"), model=OPENAI_MODEL)
            (cil / f"{s}.json").write_text(
                json.dumps(v.polozky, ensure_ascii=False, indent=1), encoding="utf-8")
            z = {"velikost": velikost, "spc": jmeno, "sekce": s, "stav": v.stav,
                 "duvod": v.duvod, "polozek": len(v.polozky),
                 "znaku": len(vstup_modelu(adr, s) or ""),
                 "vstup_tok": v.vstup_tokenu, "vystup_tok": v.vystup_tokenu,
                 "cas_s": round(v.cas_s, 1)}
            zaznamy.append(z)
            print(f"{velikost:8} {jmeno[:26]:26} {s:17} {z['znaku']:6} zn "
                  f"{z['vstup_tok']:6} -> {z['vystup_tok']:6} tok "
                  f"{z['polozek']:4} pol {z['cas_s']:6.1f}s {v.stav}", flush=True)
    return zaznamy


def odhad(tok: dict, zaznamy: list[dict]) -> dict:
    """Vystupni tokeny = vstupni text x pomer vystup/vstup z realnych behu."""
    out = {}
    for s, v in tok["po_sekci"].items():
        z = [x for x in zaznamy if x["sekce"] == s and x["vstup_tok"]]
        pomer = (sum(x["vystup_tok"] for x in z) / sum(x["vstup_tok"] for x in z)
                 if z else None)
        vystup = v["vstup_tok"] * pomer if pomer is not None else None
        out[s] = {"vstup_tok": v["vstup_tok"], "pomer_vystup_vstup": pomer,
                  "vystup_tok": vystup}
    vi = sum(x["vstup_tok"] for x in out.values())
    vo = sum(x["vystup_tok"] or 0 for x in out.values())
    cena = vi / 1e6 * CENA_VSTUP + vo / 1e6 * CENA_VYSTUP
    return {"po_sekci": out, "vstup_tok": vi, "vystup_tok": vo,
            "cena_sync_usd": cena, "cena_batch_usd": cena * BATCH_SLEVA}


def main() -> int:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--tokeny", action="store_true", help="spocitat tokeny korpusu")
    ap.add_argument("--beh", action="store_true", help="realna extrakce na 3 SPC")
    a = ap.parse_args()

    stare = json.loads(VYSLEDEK.read_text(encoding="utf-8")) if VYSLEDEK.exists() else {}
    if a.tokeny:
        stare["tokeny"] = spocitej_tokeny()
        stare["vzorek"] = vyber_vzorek(stare["tokeny"]["delky"])
    if a.beh:
        stare["beh"] = beh(stare["vzorek"])
    if "tokeny" in stare and "beh" in stare:
        stare["odhad"] = odhad(stare["tokeny"], stare["beh"])
    VYSLEDEK.write_text(json.dumps(stare, ensure_ascii=False, indent=1), encoding="utf-8")

    if "tokeny" in stare:
        print("\nVstup korpusu (tiktoken o200k_base, vč. promptu):")
        for s, v in stare["tokeny"]["po_sekci"].items():
            print(f"  {s:17} {v['volani']:5} volání  {v['vstup_tok']/1e6:6.2f} M tok")
        print(f"  vzorek: {stare['vzorek']}")
    if "odhad" in stare:
        o = stare["odhad"]
        print(f"\nOdhad: vstup {o['vstup_tok']/1e6:.1f} M, výstup {o['vystup_tok']/1e6:.1f} M tok")
        for s, v in o["po_sekci"].items():
            print(f"  {s:17} poměr výstup/vstup {v['pomer_vystup_vstup'] or 0:.2f}")
        print(f"  cena sync  {o['cena_sync_usd']:.2f} $")
        print(f"  cena Batch {o['cena_batch_usd']:.2f} $")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
