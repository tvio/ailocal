"""Benchmark: převod textové pasáže SPC do JSON pole.

Otázky, na které to má odpovědět:
  1) Kolik času žere načtení vstupu a kolik generování výstupu?
     (rozhoduje o tom, jestli má smysl zkracovat vstup, nebo výstup)
  2) Změní se něco, když se sníží num_ctx?
  3) Jak jsou na tom modely mezi sebou a proti OpenAI?
  4) Kolik ušetří kompaktnější tvar výstupního JSON?

Použití:
    uv run python bench_extrakce.py                    # základní sada
    uv run python bench_extrakce.py --openai           # + OpenAI (posílá text ven!)
    uv run python bench_extrakce.py --modely qwen2.5:32b,gemma4:31b
    uv run python bench_extrakce.py --ctx 8192,32768   # vliv num_ctx
    uv run python bench_extrakce.py --lecivo 0500896 --sekce nezadouci_ucinky

POZOR: --openai posílá text sekce na server OpenAI. SPC jsou veřejné
dokumenty SÚKL, takže to není únik, ale je to vědomé opuštění lokálního běhu.
"""

import argparse
import json
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path

from common.config import adresar_leciva, OPENAI_MODEL
from common.ollama_client import chat_detail, get_ollama_url
from common.extrakce import SYSTEM_PROMPT, PROMPTY

# --- Varianty tvaru výstupu -------------------------------------------------
# Liší se jen tím, KOLIK toho model musí vygenerovat. Obsahově jde pořád
# o tytéž účinky. Cílem je změřit, jak moc je čas svázaný s délkou výstupu.

VARIANTY = {
    "ploche": (
        "Každý objekt má klíče: ucinek, ucinek_laicky, frekvence, organovy_system. "
        "Vrať ploché pole všech účinků."
    ),
    "seskupene": (
        "Vrať objekt, kde klíč je název orgánového systému, hodnota je objekt, "
        "kde klíč je frekvence a hodnota je pole objektů {\"u\": účinek, "
        "\"l\": laický tvar}. Názvy orgánového systému a frekvence tak napíšeš "
        "jen jednou, ne u každé položky."
    ),
    "jen_ucinky": (
        "Vrať POUZE pole objektů {\"u\": účinek, \"l\": laický tvar}. "
        "Frekvenci ani orgánový systém neuváděj – ty se čtou jinak."
    ),
    "holy_seznam": (
        "Vrať POUZE pole řetězců s názvy účinků, nic jiného. "
        "Bez frekvence, bez orgánového systému, bez laického tvaru."
    ),
}


@dataclass
class Vysledek:
    model: str
    varianta: str
    num_ctx: int | None
    ok: bool
    polozek: int
    vstup_tok: int
    vystup_tok: int
    cas_vstup_s: float
    cas_vystup_s: float
    cas_celkem_s: float
    tok_za_s: float
    chyba: str = ""


def _spocitej_polozky(surova: str) -> int:
    """Kolik položek model vrátil – napříč všemi tvary výstupu."""
    try:
        d = json.loads(surova)
    except json.JSONDecodeError:
        return -1
    if isinstance(d, list):
        return len(d)
    if isinstance(d, dict):
        if len(d) == 1:
            v = next(iter(d.values()))
            if isinstance(v, list):
                return len(v)
        # seskupený tvar: sečti listy ve dvou úrovních
        n = 0
        for v in d.values():
            if isinstance(v, list):
                n += len(v)
            elif isinstance(v, dict):
                n += sum(len(x) for x in v.values() if isinstance(x, list))
        return n
    return -1


def zmer_ollama(model: str, varianta: str, text: str, sekce: str,
                num_ctx: int | None) -> Vysledek:
    zadani = f"{PROMPTY[sekce].split('Každý objekt')[0]}\n{VARIANTY[varianta]}"
    prompt = f"{zadani}\n\n--- TEXT SEKCE ---\n{text}\n--- KONEC ---"
    options = {"num_ctx": num_ctx} if num_ctx else None

    try:
        odpoved, m = chat_detail(
            prompt, system=SYSTEM_PROMPT, model=model,
            json_mode=True, options=options,
        )
    except Exception as e:
        return Vysledek(model, varianta, num_ctx, False, 0, 0, 0, 0, 0, 0, 0,
                        f"{type(e).__name__}: {e}"[:120])

    return Vysledek(
        model, varianta, num_ctx, True, _spocitej_polozky(odpoved),
        m.vstup_tokenu, m.vystup_tokenu,
        round(m.cas_vstup_s, 1), round(m.cas_vystup_s, 1),
        round(m.cas_celkem_s, 1), round(m.tok_za_s, 1),
    )


def zmer_openai(varianta: str, text: str, sekce: str) -> Vysledek:
    from openai import OpenAI

    from common.config import nacti_openai_klic

    klient = OpenAI(api_key=nacti_openai_klic())

    zadani = f"{PROMPTY[sekce].split('Každý objekt')[0]}\n{VARIANTY[varianta]}"
    prompt = f"{zadani}\n\n--- TEXT SEKCE ---\n{text}\n--- KONEC ---"

    t0 = time.perf_counter()
    try:
        r = klient.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "system", "content": SYSTEM_PROMPT},
                      {"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
    except Exception as e:
        return Vysledek(f"openai/{OPENAI_MODEL}", varianta, None, False,
                        0, 0, 0, 0, 0, 0, 0, f"{type(e).__name__}: {e}"[:120])
    cas = time.perf_counter() - t0

    u = r.usage
    return Vysledek(
        f"openai/{OPENAI_MODEL}", varianta, None, True,
        _spocitej_polozky(r.choices[0].message.content),
        u.prompt_tokens, u.completion_tokens,
        0.0, round(cas, 1), round(cas, 1),
        round(u.completion_tokens / cas, 1) if cas else 0.0,
    )


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--lecivo", default="0500896", help="kód SÚKL (výchozí IFIRMASTA)")
    p.add_argument("--sekce", default="nezadouci_ucinky")
    p.add_argument("--modely", default="qwen2.5:32b",
                   help="čárkou oddělený seznam; prázdné = žádný lokální")
    p.add_argument("--varianty", default="ploche,seskupene,jen_ucinky,holy_seznam")
    p.add_argument("--ctx", default="", help="čárkou oddělené num_ctx; prázdné = serverové")
    p.add_argument("--openai", action="store_true", help="přidat OpenAI (posílá text ven)")
    p.add_argument("--json", type=Path, help="uložit výsledky do JSON")
    a = p.parse_args()

    soubor = adresar_leciva(a.lecivo) / "sekce" / f"{a.sekce}.md"
    if not soubor.exists():
        print(f"CHYBA: {soubor} neexistuje", file=sys.stderr)
        return 1
    text = soubor.read_text(encoding="utf-8")

    modely = [m.strip() for m in a.modely.split(",") if m.strip()]
    varianty = [v.strip() for v in a.varianty.split(",") if v.strip()]
    ctxy: list[int | None] = [int(c) for c in a.ctx.split(",") if c.strip()] or [None]

    print(f"lečivo {a.lecivo}, sekce {a.sekce}, {len(text)} znaků")
    if modely:
        print(f"ollama: {get_ollama_url()}")
    print()

    hlavicka = (f"{'model':22} {'varianta':12} {'ctx':>7} {'polozek':>8} "
                f"{'vstup_tok':>10} {'vystup_tok':>11} {'t_vstup':>8} "
                f"{'t_vystup':>9} {'tok/s':>6}")
    print(hlavicka)
    print("-" * len(hlavicka))

    vysledky: list[Vysledek] = []
    for model in modely:
        for ctx in ctxy:
            for var in varianty:
                v = zmer_ollama(model, var, text, a.sekce, ctx)
                vysledky.append(v)
                if v.ok:
                    print(f"{v.model[:22]:22} {v.varianta:12} {str(v.num_ctx or '-'):>7} "
                          f"{v.polozek:8} {v.vstup_tok:10} {v.vystup_tok:11} "
                          f"{v.cas_vstup_s:8.1f} {v.cas_vystup_s:9.1f} {v.tok_za_s:6.1f}")
                else:
                    print(f"{v.model[:22]:22} {v.varianta:12} {str(v.num_ctx or '-'):>7} "
                          f"  CHYBA: {v.chyba}")
                sys.stdout.flush()

    if a.openai:
        for var in varianty:
            v = zmer_openai(var, text, a.sekce)
            vysledky.append(v)
            if v.ok:
                print(f"{v.model[:22]:22} {v.varianta:12} {'-':>7} "
                      f"{v.polozek:8} {v.vstup_tok:10} {v.vystup_tok:11} "
                      f"{v.cas_vstup_s:8.1f} {v.cas_vystup_s:9.1f} {v.tok_za_s:6.1f}")
            else:
                print(f"{v.model[:22]:22} {v.varianta:12} {'-':>7}   CHYBA: {v.chyba}")
            sys.stdout.flush()

    if a.json:
        a.json.write_text(
            json.dumps([asdict(v) for v in vysledky], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\nuloženo do {a.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
