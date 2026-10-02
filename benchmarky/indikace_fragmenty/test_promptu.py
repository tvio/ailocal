#!/usr/bin/env python3
"""Stary vs. novy prompt indikaci (2. 10. 2026) – na stejnych sekcich, stejny soudce.

Sekce: vsechny, kde soudce.py nasel chybu (skupina/kus) + SIMVASTATIN +
vzorek podezrelych z detektory.py + nahodna kontrola.
Stara verze = polozky v DB (prvni pruchod korpusu, luna, prompt v1).
Nova verze  = synchronni extrakce lunou s PROMPT_INDIKACE_V2.
Soudce (gemma4:26b) hodnoti VSECHNY polozky obou verzi nad celym textem 4.1.

Metriky: podil skupina+kus, pocet polozek (nesmi se ztracet indikace),
u kontroly zmena = riziko, ze novy prompt kazi dobre sekce.

Pouziti:  uv run python benchmarky/indikace_fragmenty/test_promptu.py
"""

import io
import sys
import json
import random
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import psycopg                                                  # noqa: E402
from common.config import PG_DSN, MODEL_KONTROLY, OPENAI_MODEL  # noqa: E402
from common.ollama_client import chat                           # noqa: E402
import common.extrakce as ex                                    # noqa: E402
from soudce import SYSTEM, POKYN                                # noqa: E402

TADY = Path(__file__).parent
random.seed(7)


def vyber_sekci() -> dict[int, str]:
    rows = [json.loads(x) for x in (TADY / "soudce.jsonl").read_text(encoding="utf-8").splitlines()]
    sekce = {r["extrakt"]: "chyba" for r in rows if r["soudce"] in ("skupina", "kus")}
    podezrele = [r["extrakt"] for r in rows if r["skupina_vzorku"].startswith("D2")
                 and r["extrakt"] not in sekce]
    for e in random.sample(podezrele, min(20, len(podezrele))):
        sekce[e] = "podezrele"
    with psycopg.connect(PG_DSN) as c:
        simva = c.execute("""SELECT e.id FROM extrakty e JOIN leciva l USING (kod_sukl)
                             WHERE l.nazev = 'SIMVASTATIN RATIOPHARM' AND e.sekce = 'indikace'
                             LIMIT 1""").fetchone()
        vse = [r[0] for r in c.execute("SELECT id FROM extrakty WHERE sekce = 'indikace'")]
    if simva:
        sekce[simva[0]] = "simvastatin"
    for e in random.sample([x for x in vse if x not in sekce], 20):
        sekce[e] = "kontrola"
    return sekce


def soudce(text: str, polozka: str) -> str:
    prompt = (f"{POKYN}\n\n--- TEXT INDIKACÍ ---\n{text[:6000]}\n"
              f"--- POLOŽKA ---\n{polozka}\n--- KONEC ---")
    for _ in range(3):                      # Ollama na DGX obcas spadne
        try:
            return json.loads(ex._ocisti_odpoved(
                chat(prompt, system=SYSTEM, model=MODEL_KONTROLY, json_mode=True))).get("druh", "?")
        except Exception:
            continue
    return "chyba"


def main() -> int:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
    sekce = vyber_sekci()
    print(f"Sekcí: {len(sekce)}  {dict(Counter(sekce.values()))}")
    with psycopg.connect(PG_DSN) as c:
        texty = dict(c.execute("SELECT id, zdrojovy_text FROM extrakty WHERE id = ANY(%s)",
                               (list(sekce),)).fetchall())
        stare = {}
        for e, dosl, sk in c.execute("""SELECT extrakt_id, sekce_atributy->>'doslovne',
                                               sekce_atributy->>'skupina'
                                        FROM leciva_search WHERE extrakt_id = ANY(%s)
                                        ORDER BY id""", (list(sekce),)):
            stare.setdefault(e, []).append({"doslovne": dosl, "skupina": sk})

    puvodni = ex.PROMPTY["indikace"]
    ex.PROMPTY["indikace"] = ex.PROMPT_INDIKACE_V2          # jen v tomto procesu
    vysl = []
    out = (TADY / "test_promptu.jsonl").open("w", encoding="utf-8")
    try:
        for n, (e, druh) in enumerate(sekce.items(), 1):
            text = texty.get(e) or ""
            v = ex.extrahuj_sekci("indikace", text, model=OPENAI_MODEL)
            nove = [{"doslovne": p.get("doslovne"), "skupina": p.get("skupina"),
                     "laicky": p.get("laicky")} for p in v.polozky]
            z = {"extrakt": e, "druh": druh, "stare": stare.get(e, []), "nove": nove,
                 "vstup_tok": v.vstup_tokenu, "vystup_tok": v.vystup_tokenu}
            for verze in ("stare", "nove"):
                for p in z[verze]:
                    p["soudce"] = soudce(text, p["doslovne"] or "")
            vysl.append(z)
            out.write(json.dumps(z, ensure_ascii=False) + "\n")
            out.flush()
            if n % 10 == 0:
                print(f"  ... {n}/{len(sekce)}")
    finally:
        ex.PROMPTY["indikace"] = puvodni
        out.close()

    print(f"\n{'skupina sekcí':12} {'verze':6} {'položek':>7} {'indikace':>8} {'skupina':>7} "
          f"{'kus':>4} {'jiné':>4}  chybných")
    for druh in ("chyba", "podezrele", "kontrola", "simvastatin"):
        for verze in ("stare", "nove"):
            c = Counter(p["soudce"] for z in vysl if z["druh"] == druh for p in z[verze])
            nn = sum(c.values())
            if not nn:
                continue
            print(f"{druh:12} {verze:6} {nn:7} {c['indikace']:8} {c['skupina']:7} {c['kus']:4} "
                  f"{c['jine']:4}  {(c['skupina'] + c['kus']) / nn:6.0%}")
    cena = sum(z["vstup_tok"] * 0.10 + z["vystup_tok"] * 0.50 for z in vysl) / 1e6
    print(f"\nCena nové extrakce (sync): {cena:.4f} $")
    for z in vysl:
        if z["druh"] == "simvastatin":
            print("\nSIMVASTATIN – nové položky:")
            for p in z["nove"]:
                print(f"   [{p['soudce']:8}] {p['doslovne']}  | skupina: {p['skupina']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
