#!/usr/bin/env python3
"""Detektory chybnych polozek indikaci (2. 10. 2026) – bez modelu.

Kontext: SIMVASTATIN mel polozku indikace „diabetem mellitem" (laicky
„cukrovka") – vytrzeny kus vety „u pacientu s ... nebo s diabetem mellitem".
Simvastatin na cukrovku neni. Chyba je v EXTRAKCI (rozdeleni indikace na
polozky), ne v laickem tvaru ani klici. Cil: zjistit, jak casto a v jakych
vzorech se to deje, nez se zmeni prompt a indikace se preextrahuji.

Detektor 1 – NESOULAD S ATC: u kazde laicke indikace (napr. „cukrovka")
  rozlozeni ATC skupin leku, ktere ji maji. Polozka, jejiz lek je
  v NEOBVYKLE skupine (podil < PRAH_ATC), je podezrela.
Detektor 2 – TVAR POLOZKY: prvni slovo v 7./2. pade („diabetem",
  „onemocnenim"), zacina predlozkou (u, s, pri, pro...), nebo je kratka
  (1–2 slova) vedle dlouhe vety.

Vystup: souhrn na obrazovku + podezrele.jsonl (vstup pro soudce, detektor 3).

Pouziti:  uv run python benchmarky/indikace_fragmenty/detektory.py
"""

import io
import re
import sys
import json
from pathlib import Path
from collections import Counter, defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import psycopg                                    # noqa: E402
from common.config import PG_DSN                  # noqa: E402

TADY = Path(__file__).parent
MIN_SPC_SKUPINA = 8       # laicka indikace musi byt aspon u tolika SPC
PRAH_ATC = 0.05           # podil ATC skupiny leku v ramci indikace
PRAH_DOMINANTNI = 0.40    # a nejcastejsi skupina musi indikaci jasne „vlastnit"

# 7. a 2. pad na konci prvniho slova + typicke predlozky uvozujici skupinu
_PAD = re.compile(r"^[a-záčďéěíňóřšťúůýž-]+(em|ím|ou|ami|ými|ích|ech|ého|ému|ým)$", re.I)
_PREDLOZKA = re.compile(r"^(u|s|se|při|pro|po|ke|k|v|ve|z|ze|u\s+pacientů|u\s+nemocných)$", re.I)


def nacti() -> list[dict]:
    with psycopg.connect(PG_DSN) as c:
        rows = c.execute("""
            SELECT s.id, l.kod_sukl, l.nazev, l.atc, l.spc,
                   s.sekce_atributy->>'doslovne', s.sekce_atributy->>'laicky',
                   s.sekce_atributy->>'klic', s.extrakt_id
            FROM leciva_search s JOIN leciva l USING (kod_sukl)
            WHERE s.sekce = 'indikace'""").fetchall()
    k = ["id", "kod", "nazev", "atc", "spc", "doslovne", "laicky", "klic", "extrakt"]
    return [dict(zip(k, r)) for r in rows]


def detektor_atc(polozky: list[dict]) -> dict[int, str]:
    skup: dict[str, list[dict]] = defaultdict(list)
    for p in polozky:
        if p["laicky"] and p["atc"]:
            skup[" ".join(p["laicky"].lower().split()).rstrip(".")].append(p)
    ven = {}
    for laicky, rows in skup.items():
        spc = {r["spc"] for r in rows}
        if len(spc) < MIN_SPC_SKUPINA:
            continue
        # rozlozeni ATC (3 znaky) po SPC, ne po radcich
        atc_spc = Counter(a for _, a in {(r["spc"], r["atc"][:3]) for r in rows})
        celkem = sum(atc_spc.values())
        dom, dom_n = atc_spc.most_common(1)[0]
        if dom_n / celkem < PRAH_DOMINANTNI:
            continue
        for r in rows:
            if atc_spc[r["atc"][:3]] / celkem < PRAH_ATC:
                ven[r["id"]] = (f"ATC {r['atc'][:3]} u „{laicky}\" jen "
                                f"{atc_spc[r['atc'][:3]]}/{celkem} SPC (běžně {dom})")
    return ven


def detektor_tvar(polozky: list[dict]) -> dict[int, str]:
    po_extraktu = defaultdict(list)
    for p in polozky:
        po_extraktu[p["extrakt"]].append(p)
    ven = {}
    for p in polozky:
        d = (p["doslovne"] or "").strip()
        if not d:
            continue
        slova = d.split()
        prvni = slova[0].strip("(,").lower()
        if _PREDLOZKA.match(prvni):
            ven[p["id"]] = f"začíná předložkou „{prvni}\""
        elif _PAD.match(prvni) and d[:1].islower():
            ven[p["id"]] = f"první slovo v 7./2. pádě „{prvni}\""
        elif len(slova) <= 2:
            sousede = [len((x["doslovne"] or "").split()) for x in po_extraktu[p["extrakt"]]
                       if x["id"] != p["id"]]
            if sousede and max(sousede) >= 8:
                ven[p["id"]] = "krátká položka vedle dlouhé věty"
    return ven


def main() -> int:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    import argparse
    argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    pol = nacti()
    d1, d2 = detektor_atc(pol), detektor_tvar(pol)
    oba = set(d1) & set(d2)
    podle_id = {p["id"]: p for p in pol}
    spc = {p["spc"] for p in pol}

    print(f"Položek indikací: {len(pol)} ze {len(spc)} SPC")
    print(f"Detektor 1 (nesoulad s ATC):  {len(d1):5} položek, "
          f"{len({podle_id[i]['spc'] for i in d1})} SPC")
    druhy = Counter(v.split(' „')[0] if '„' in v else v for v in d2.values())
    print(f"Detektor 2 (tvar položky):    {len(d2):5} položek, "
          f"{len({podle_id[i]['spc'] for i in d2})} SPC  {dict(druhy)}")
    print(f"Oba detektory:                {len(oba):5} položek")

    top = Counter(v.split('„')[1].split('"')[0] for v in d1.values())
    print("\nNejčastější indikace s nesouladem ATC:", top.most_common(10))
    for nazev, slovnik in (("detektor 1", d1), ("detektor 2", d2)):
        print(f"\nUkázky – {nazev}:")
        for i in list(slovnik)[:: max(1, len(slovnik) // 8)][:8]:
            p = podle_id[i]
            print(f"  {p['nazev'][:22]:22} {p['atc'] or '':8} „{(p['doslovne'] or '')[:45]}\" "
                  f"→ „{(p['laicky'] or '')[:30]}\"  [{slovnik[i][:60]}]")

    # Stary vystup se NEPREPISUJE, ale odlozi s datem - je to stav „pred"
    # pro srovnani po preextrahovani. 6. 10. 2026 ho prepsalo pouhe
    # `--help` (skript nemel argumenty) a stav z 2. 10. byl pryc.
    cil = TADY / "podezrele.jsonl"
    if cil.exists():
        from datetime import datetime
        kdy = datetime.fromtimestamp(cil.stat().st_mtime).strftime("%Y%m%d_%H%M")
        cil.rename(TADY / f"podezrele_{kdy}.jsonl")
        print(f"Predchozi vystup odlozen: podezrele_{kdy}.jsonl")
    with cil.open("w", encoding="utf-8") as f:
        for i in sorted(set(d1) | set(d2)):
            p = dict(podle_id[i])
            p["duvod"] = "; ".join(x for x in (d1.get(i), d2.get(i)) if x)
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    print(f"\nPodezřelé zapsány: {TADY / 'podezrele.jsonl'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
