#!/usr/bin/env python3
"""Krok 3 pipeline: převod sekcí SPC do strukturovaného JSON.

Všechny sekce jedou na qwen3.5:122b (config.MODEL_SEKCE). Dělit úlohu
mezi menší a větší model se ukázalo jako zbytečné – 122b je MoE, takže
je zároveň nejlepší i nejrychlejší (~29 tok/s proti 10,5 u 32b a 4,5
u 72b). Měření viz poznatky.md 18.8.2026.

Výstup: data/leciva/<kod>_<NAZEV>/json/<sekce>.json
        data/leciva/<kod>_<NAZEV>/json/_stav.json

Stav se zapisuje VŽDY a explicitně, nikdy jako NULL – u aplikace pro
laiky se musí poznat "lék nemá nežádoucí účinky" od "extrakce selhala".

Použití:
  uv run python extrahuj_json.py --vse
  uv run python extrahuj_json.py --kody 0254048
  uv run python extrahuj_json.py --vse --sekce nezadouci_ucinky
  uv run python extrahuj_json.py --vse --znovu        # i hotové
"""

import sys
import json
import time
import argparse
from pathlib import Path
from collections import Counter

from common.config import LECIVA_DIR, adresar_leciva, MODEL_SEKCE
from common.sekce import SEKCE_SPC
from common.extrakce import extrahuj_sekci


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Extrakce sekcí SPC do JSON")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--vse", action="store_true")
    g.add_argument("--kody", nargs="+", metavar="KOD")
    p.add_argument("--sekce", nargs="+", choices=sorted(SEKCE_SPC),
                   help="jen vybrané sekce (výchozí: všechny)")
    p.add_argument("--model", default=None,
                   help="přebije rozdělení podle sekce (config.MODEL_SEKCE)")
    p.add_argument("--znovu", action="store_true",
                   help="přepsat i sekce, které už mají hotový JSON")
    return p.parse_args()


def main() -> int:
    a = parse_args()
    adresare = ([adresar_leciva(k) for k in a.kody] if a.kody
                else sorted(p for p in LECIVA_DIR.iterdir() if p.is_dir()))
    sekce_k_extrakci = a.sekce or list(SEKCE_SPC)

    print("=" * 78)
    print("KROK 3 – extrakce do JSON")
    if a.model:
        print(f"model natvrdo: {a.model}")
    else:
        for s_, m_ in MODEL_SEKCE.items():
            print(f"  {s_:18} {m_}")
    print("=" * 78)

    stavy = Counter()
    celkovy_cas = 0.0
    zacatek = time.perf_counter()
    hotovo = preskoceno = 0

    for adr in adresare:
        zdroj = adr / "sekce"
        if not zdroj.exists():
            continue
        cil = adr / "json"
        cil.mkdir(exist_ok=True)

        stav_souboru = cil / "_stav.json"
        stav = json.loads(stav_souboru.read_text(encoding="utf-8")) if stav_souboru.exists() else {}

        for nazev in sekce_k_extrakci:
            vystup = cil / f"{nazev}.json"
            if vystup.exists() and not a.znovu:
                preskoceno += 1
                stavy[stav.get(nazev, {}).get("stav", "?")] += 1
                continue

            # Přednostně ořezaná verze; ta plná je záloha pro porovnání.
            plny = zdroj / f"{nazev}.md"
            if not plny.exists():
                stav[nazev] = {"stav": "chybi_v_dokumentu",
                               "duvod": "sekce se v SPC nenašla"}
                stavy["chybi_v_dokumentu"] += 1
                continue

            model = a.model or MODEL_SEKCE[nazev]
            v = extrahuj_sekci(nazev, plny.read_text(encoding="utf-8"), model=model)
            celkovy_cas += v.cas_s
            stavy[v.stav] += 1

            if v.polozky:
                vystup.write_text(
                    json.dumps(v.polozky, ensure_ascii=False, indent=1), encoding="utf-8"
                )
            stav[nazev] = {
                "stav": v.stav,
                "duvod": v.duvod,
                "polozek": len(v.polozky),
                "model": v.model,
                "cas_s": round(v.cas_s, 1),
            }
            if v.surova_odpoved:
                stav[nazev]["surova_odpoved"] = v.surova_odpoved

            znacka = "ok " if v.stav == "neovereno" else "!! "
            print(f"{znacka}{adr.name[:30]:30} {nazev:18} "
                  f"{len(v.polozky):3} položek  {v.cas_s:6.1f}s  {v.stav}"
                  + (f"  – {v.duvod[:50]}" if v.duvod else ""))
            sys.stdout.flush()
            hotovo += 1

        stav_souboru.write_text(
            json.dumps(stav, ensure_ascii=False, indent=1), encoding="utf-8"
        )

    uplynulo = time.perf_counter() - zacatek
    print()
    print(f"Zpracováno {hotovo} sekcí, přeskočeno {preskoceno} (už hotové).")
    print(f"Čas: {uplynulo/60:.1f} min celkem, z toho {celkovy_cas/60:.1f} min v modelu.")
    if hotovo:
        print(f"     {celkovy_cas/hotovo:.1f} s na sekci")
    print("Stavy: " + ", ".join(f"{k}={v}" for k, v in stavy.most_common()))
    print()
    print("Stav 'neovereno' znamená: extrakce proběhla, ale NIKDO to neověřil.")
    print("Ověření dělá krok 4 – teprve pak je stav 'ok'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
