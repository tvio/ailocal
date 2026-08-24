#!/usr/bin/env python3
"""Krok 4 (cast 2): kontrola extrakce JINYM modelem.

Navazuje na deterministickou kontrolu (zkontroluj_json.py), ktera uz odbavila
to, co jde overit doslovnym porovnanim se zdrojem. Sem jde jen zbytek:

  a) sekce, kde deterministicka kontrola nasla neshodu
  b) indikace a kontraindikace - ty deterministicky overit NELZE, protoze
     jsou zamerne prevyprane laickym jazykem

Model je JINY nez ten, ktery extrahoval (config.MODEL_KONTROLY vs
MODEL_HLAVNI). Model si neodsouhlasi vlastni chybu - to je cely smysl.

Uloha je zamerne uzka: pro kazdou polozku jen "ma to oporu ve zdroji?".
Zadne prepisovani, zadne navrhy oprav - jen seznam indexu a duvod.
Kratky vystup je i rychly vystup.

Pouziti:
  uv run python zkontroluj_modelem.py --vzorek 3      # zkusit na par sekcich
  uv run python zkontroluj_modelem.py --vse
  uv run python zkontroluj_modelem.py --vse --model gpt-5-nano   # cloud
  uv run python zkontroluj_modelem.py --vse --zapis
"""

import sys
import json
import time
import argparse
from pathlib import Path
from collections import Counter

from common.config import LECIVA_DIR, adresar_leciva, MODEL_KONTROLY, OPENAI_MODEL
from common.sekce import orizni_na_jadro

SYSTEM = (
    "Jsi kontrolor extrakce dat z farmaceutických dokumentů. "
    "Dostaneš zdrojový text sekce a položky, které z něj někdo vytáhl. "
    "Tvůj úkol je JEDINÝ: u každé položky rozhodnout, jestli má oporu ve "
    "zdrojovém textu. Nic nepřepisuj a nic nedoplňuj. "
    "Vrať POUZE validní JSON, žádný jiný text."
)

POKYN = """Zkontroluj, jestli každá položka opravdu vychází ze zdrojového textu.

Za CHYBNOU považuj položku, která:
- ve zdroji vůbec není (někdo si ji vymyslel)
- má u sebe jinou frekvenci, než pod jakou je ve zdroji uvedená
- má u sebe jiný orgánový systém, než pod kterým je ve zdroji uvedená
- říká něco věcně jiného než zdroj

Za chybnou NEPOVAŽUJ položku, která je jen:
- řečená jinými slovy nebo zjednodušená pro laika
- zkrácená, pokud význam zůstal
- přeložený odborný termín (trombocytopenie = nízký počet krevních destiček)

Vrať JSON: {"chybne": [{"i": index polozky, "proc": "kratke zduvodneni"}]}
Když je všechno v pořádku, vrať {"chybne": []}."""


def sekce_ke_kontrole(adr: Path) -> list[str]:
    """Ktere sekce daneho leciva potrebuji kontrolu modelem."""
    stav_f = adr / "json" / "_stav.json"
    if not stav_f.exists():
        return []
    stav = json.loads(stav_f.read_text(encoding="utf-8"))
    ven = []
    for sekce, v in stav.items():
        if v.get("stav") == "ok":
            continue          # deterministicka kontrola uz to potvrdila
        if not (adr / "json" / f"{sekce}.json").exists():
            continue
        ven.append(sekce)
    return ven


def _zavolej_model(prompt: str, model: str, cloud: bool) -> str:
    if cloud:
        from openai import OpenAI

        from common.config import nacti_openai_klic

        klient = OpenAI(api_key=nacti_openai_klic())
        r = klient.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": SYSTEM},
                      {"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        return r.choices[0].message.content or ""

    from common.ollama_client import chat

    return chat(prompt, system=SYSTEM, model=model, json_mode=True)


def zkontroluj_sekci(adr: Path, sekce: str, model: str, *, cloud: bool) -> dict:
    zdroj = orizni_na_jadro(
        (adr / "sekce" / f"{sekce}.md").read_text(encoding="utf-8"), sekce)
    polozky = json.loads((adr / "json" / f"{sekce}.json").read_text(encoding="utf-8"))

    # Polozky ocislovane, at se model muze odkazat indexem misto opisovani.
    soupis = "\n".join(
        f"{i}. " + (json.dumps(p, ensure_ascii=False) if isinstance(p, dict) else str(p))
        for i, p in enumerate(polozky))
    prompt = (f"{POKYN}\n\n--- ZDROJOVÝ TEXT ---\n{zdroj}\n"
              f"--- POLOŽKY K OVĚŘENÍ ---\n{soupis}\n--- KONEC ---")

    t0 = time.perf_counter()
    try:
        odpoved = _zavolej_model(prompt, model, cloud)
    except Exception as e:
        return {"chyba": f"{type(e).__name__}: {e}"[:120],
                "cas_s": round(time.perf_counter() - t0, 1)}
    cas = time.perf_counter() - t0

    from common.extrakce import _ocisti_odpoved

    try:
        data = json.loads(_ocisti_odpoved(odpoved))
    except json.JSONDecodeError as e:
        return {"chyba": f"nevalidní JSON: {e}", "surova": odpoved[:200],
                "cas_s": round(cas, 1)}

    chybne = data.get("chybne", []) if isinstance(data, dict) else []
    if not isinstance(chybne, list):
        chybne = []

    # Index musi ukazovat na existujici polozku. Kdyz ne, model si ho vymyslel
    # a je to signal, ze kontrole nelze verit - proto se to pocita zvlast.
    platne = [c for c in chybne
              if isinstance(c, dict) and isinstance(c.get("i"), int)
              and 0 <= c["i"] < len(polozky)]
    return {"polozek": len(polozky), "chybne": platne,
            "zahozeno_indexu": len(chybne) - len(platne),
            "model": model, "cas_s": round(cas, 1)}


def main() -> int:
    p = argparse.ArgumentParser(description="Kontrola extrakce jiným modelem")
    p.add_argument("--kody", nargs="+", metavar="KOD")
    p.add_argument("--vse", action="store_true")
    p.add_argument("--vzorek", type=int, help="jen prvních N sekcí (na zkoušku)")
    p.add_argument("--model", default=MODEL_KONTROLY)
    p.add_argument("--zapis", action="store_true")
    a = p.parse_args()

    cloud = a.model.startswith("gpt-")
    if cloud and a.model != OPENAI_MODEL:
        print(f"POZOR: cloud model {a.model}, config doporučuje {OPENAI_MODEL} "
              f"(rozpočet!)", file=sys.stderr)

    adresare = ([adresar_leciva(k) for k in a.kody] if a.kody
                else sorted(x for x in LECIVA_DIR.iterdir() if x.is_dir()))

    ukoly = [(adr, sek) for adr in adresare for sek in sekce_ke_kontrole(adr)]
    if a.vzorek:
        ukoly = ukoly[: a.vzorek]

    print(f"Kontroluje: {a.model}" + ("  (CLOUD)" if cloud else ""))
    print(f"Sekcí ke kontrole: {len(ukoly)}")
    print("-" * 78)

    souhrn: Counter = Counter()
    celkem_cas = 0.0
    for adr, sekce in ukoly:
        v = zkontroluj_sekci(adr, sekce, a.model, cloud=cloud)
        celkem_cas += v.get("cas_s", 0)

        if "chyba" in v:
            souhrn["chyba"] += 1
            print(f"!! {adr.name[:28]:28} {sekce:18} CHYBA: {v['chyba'][:44]}")
            sys.stdout.flush()
            continue

        n = len(v["chybne"])
        souhrn["sekci"] += 1
        souhrn["polozek"] += v["polozek"]
        souhrn["oznaceno"] += n
        souhrn["zahozeno_indexu"] += v["zahozeno_indexu"]
        znacka = "ok " if n == 0 else "?? "
        print(f"{znacka}{adr.name[:28]:28} {sekce:18} "
              f"{n}/{v['polozek']} označeno  {v['cas_s']:6.1f}s")
        for c in v["chybne"][:3]:
            print(f"      [{c['i']}] {str(c.get('proc'))[:88]}")
        sys.stdout.flush()

        if a.zapis:
            stav_f = adr / "json" / "_stav.json"
            stav = json.loads(stav_f.read_text(encoding="utf-8"))
            blok = stav.setdefault(sekce, {})
            blok["kontrola_modelem"] = {
                "model": a.model, "oznaceno": n, "polozek": v["polozek"],
                # Indexy jsou podstatne: bez nich by se pri plneni DB musela
                # vyradit CELA sekce kvuli jedne vadne polozce. ACYLCOFFIN
                # mel 1 vadnou ze 46 - to je 45 dobrych ucinku pryc.
                "chybne_indexy": sorted(c["i"] for c in v["chybne"]),
                "duvody": [str(c.get("proc", ""))[:200] for c in v["chybne"]],
            }
            if n == 0 and blok.get("stav") == "neovereno":
                blok["stav"] = "ok"
            elif n:
                blok["stav"] = "zamitnuto_kontrolou"
            stav_f.write_text(json.dumps(stav, ensure_ascii=False, indent=1),
                              encoding="utf-8")

    print()
    print(f"Sekcí: {souhrn['sekci']}, chyb volání: {souhrn['chyba']}")
    podil = (f" ({souhrn['oznaceno'] / souhrn['polozek']:.1%})"
             if souhrn["polozek"] else "")
    print(f"Položek: {souhrn['polozek']}, označeno jako chybné: "
          f"{souhrn['oznaceno']}{podil}")
    if souhrn["zahozeno_indexu"]:
        print(f"Zahozeno neplatných indexů (model si je vymyslel): "
              f"{souhrn['zahozeno_indexu']}")
    if souhrn["sekci"]:
        print(f"Čas: {celkem_cas / 60:.1f} min, "
              f"{celkem_cas / souhrn['sekci']:.1f} s na sekci")
    if not a.zapis:
        print("\n(nic se nezapsalo - pro zápis přidej --zapis)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
