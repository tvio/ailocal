#!/usr/bin/env python3
"""Detektor 3 – soudce nad VZORKEM polozek indikaci (2. 10. 2026).

Vstup: podezrele.jsonl z detektory.py + kontrolni vzorek nepodezrelych.
Soudce = gemma4:26b lokalne (JINY model nez extrakce – luna), dostane CELY
text indikaci ze SPC a jednu polozku. Zaradi ji:

  indikace  samostatna nemoc / priznak / stav, na ktery se lek pouziva
  skupina   skupina nebo podminka pacientu („u pacientu s cukrovkou"),
            ne to, co lek leci
  kus       vytrzena cast vety, sama o sobe nedava smysl (pridavne jmeno,
            cast vyctu bez podstatneho jmena, „hltanu")
  jine      nic z toho (vysetreni, zpusob podani...)

Vystup: soudce.jsonl + souhrn podle detektoru (kolik je skutecne chyb).

Pouziti:  uv run python benchmarky/indikace_fragmenty/soudce.py
"""

import io
import sys
import json
import random
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import psycopg                                         # noqa: E402
from common.config import PG_DSN, MODEL_KONTROLY       # noqa: E402
from common.ollama_client import chat                  # noqa: E402
from common.extrakce import _ocisti_odpoved            # noqa: E402

TADY = Path(__file__).parent
random.seed(42)

SYSTEM = ("Jsi kontrolor extrakce dat ze souhrnů údajů o přípravku (SPC). "
          "Vrať POUZE validní JSON.")
POKYN = """Níže je text sekce 4.1 Terapeutické indikace z SPC a JEDNA položka,
kterou z něj někdo vytáhl jako samostatnou indikaci. Zařaď položku:

- "indikace": samostatná nemoc, příznak nebo stav, NA KTERÝ se lék používá
  (léčí ho, zmírňuje, předchází mu)
- "skupina": skupina nebo podmínka pacientů, U KTERÝCH se lék použije
  („u pacientů s cukrovkou", „u kuřáků"), ale lék ji neléčí
- "kus": vytržená část věty, sama o sobě nedává smysl (část výčtu bez
  podstatného jména, přívlastek, „hltanu")
- "jine": nic z toho

Vrať JSON: {"druh": "indikace|skupina|kus|jine", "proc": "krátce"}"""


def vzorek() -> list[dict]:
    pod = [json.loads(x) for x in (TADY / "podezrele.jsonl").read_text(encoding="utf-8").splitlines()]
    d1 = [p for p in pod if p["duvod"].startswith("ATC")]
    d2 = {}
    for p in pod:
        if p["duvod"].startswith("ATC"):
            continue
        druh = p["duvod"].split(" „")[0]
        d2.setdefault(druh, []).append(p)
    ven = [dict(p, skupina_vzorku="D1 ATC") for p in d1]
    for druh, rows in d2.items():
        ven += [dict(p, skupina_vzorku=f"D2 {druh}") for p in random.sample(rows, min(35, len(rows)))]
    podezrela_id = {p["id"] for p in pod}
    with psycopg.connect(PG_DSN) as c:
        rows = c.execute("""
            SELECT s.id, l.nazev, l.atc, s.sekce_atributy->>'doslovne',
                   s.sekce_atributy->>'laicky', s.extrakt_id
            FROM leciva_search s JOIN leciva l USING (kod_sukl)
            WHERE s.sekce = 'indikace'""").fetchall()
    kontrola = [r for r in rows if r[0] not in podezrela_id]
    for r in random.sample(kontrola, 60):
        ven.append({"id": r[0], "nazev": r[1], "atc": r[2], "doslovne": r[3],
                    "laicky": r[4], "extrakt": r[5], "duvod": "", "skupina_vzorku": "kontrola"})
    return ven


def main() -> int:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
    vz = vzorek()
    print(f"Vzorek {len(vz)} položek, soudce {MODEL_KONTROLY}")
    with psycopg.connect(PG_DSN) as c:
        texty = dict(c.execute("SELECT id, zdrojovy_text FROM extrakty WHERE id = ANY(%s)",
                               ([p["extrakt"] for p in vz],)).fetchall())
    out = (TADY / "soudce.jsonl").open("w", encoding="utf-8")
    for n, p in enumerate(vz, 1):
        prompt = (f"{POKYN}\n\n--- TEXT INDIKACÍ ---\n{(texty.get(p['extrakt']) or '')[:6000]}\n"
                  f"--- POLOŽKA ---\n{p['doslovne']}\n--- KONEC ---")
        try:
            d = json.loads(_ocisti_odpoved(chat(prompt, system=SYSTEM, model=MODEL_KONTROLY,
                                                json_mode=True)))
        except Exception as e:
            d = {"druh": "chyba", "proc": f"{type(e).__name__}: {e}"[:100]}
        p["soudce"] = d.get("druh")
        p["proc"] = d.get("proc")
        out.write(json.dumps(p, ensure_ascii=False) + "\n")
        out.flush()
        if n % 25 == 0:
            print(f"  ... {n}/{len(vz)}")
    out.close()

    rows = [json.loads(x) for x in (TADY / "soudce.jsonl").read_text(encoding="utf-8").splitlines()]
    print(f"\n{'skupina vzorku':42} {'n':>4}  indikace  skupina  kus  jine  chyba")
    for sk in sorted({r["skupina_vzorku"] for r in rows}):
        c = Counter(r["soudce"] for r in rows if r["skupina_vzorku"] == sk)
        n = sum(c.values())
        spatne = c["skupina"] + c["kus"]
        print(f"{sk:42} {n:4}  {c['indikace']:8} {c['skupina']:8} {c['kus']:4} {c['jine']:5} "
              f"{c['chyba']:5}   chybných {spatne / n:.0%}")
    print("\nUkázky skupina / kus:")
    for r in [r for r in rows if r["soudce"] in ("skupina", "kus")][:20]:
        print(f"  [{r['soudce']:7}] {r['nazev'][:20]:20} „{(r['doslovne'] or '')[:45]}\" – {str(r['proc'])[:70]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
