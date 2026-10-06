#!/usr/bin/env python3
"""Ciselnik pojmu: odborny termin -> laicky tvar.

PROC EXISTUJE UZ TED, kdyz je "Krok 5" v poradi az posledni:
Odlozene bylo ROZHODNUTI, jestli laicky tvar potrebuje vyhledavani (to se
pozna az z evaluace). Ciselnik jako DATA je ale potreba hned, ze dvou duvodu:

  1) Je to jediny auditovatelny artefakt. Zkontrolovat 419 dvojic v jednom
     souboru jde; zkontrolovat totez rozhazene v 738 polozkach napric
     23 leky nejde.
  2) Zjednoduseni dnes NEKONTROLUJE ani deterministicka kontrola (laicky
     tvar ve zdroji doslova neni), ani modelova (prompt ji rika, ze
     zjednoduseni se za chybu nepovazuje). Ciselnik tu diru zavira.

Zmereno pred stavbou: 419 unikatnich odbornych terminu, z toho 84 (20 %)
melo VIC ruznych laickych tvaru - vcetne rozsypanych ("Schuzeni nemoznosti
zustat v klidu"). Sjednoceni tedy neni kosmetika.

Vystup:
    slovnik_pojmu.json   VYGENEROVANY - prepisuje se pri kazdem behu
    slovnik_pojmu.md     ciselnik k RUCNIMU projiti

Rucni opravy patri do slovnik_rucni.json. Ten se NIKDY negeneruje
automaticky a ma prednost pred vygenerovanym slovnikem. Bez tohohle
oddeleni by prestavba slovniku prepsala praci cloveka tim, co
vygeneroval model.

Pouziti:
  uv run python postav_slovnik.py                  # jen posbirat a vypsat
  uv run python postav_slovnik.py --zkontroluj     # + overit modelem
  uv run python postav_slovnik.py --zkontroluj --zapis
"""

import io
import sys
import json
import time
import argparse
from pathlib import Path
from collections import Counter, defaultdict

from common.config import LECIVA_DIR, MODEL_KONTROLY
from common.slovnik import klic, ocisti_laicky

JSON_SOUBOR = Path("slovnik_pojmu.json")
MD_SOUBOR = Path("slovnik_pojmu.md")

# Kolik dvojic poslat modelu najednou. Vic = min volani, ale delsi vystup
# a vetsi sance, ze model nekterou dvojici preskoci.
DAVKA = 20

SYSTEM = (
    "Jsi kontrolor lékařských překladů do laické češtiny. "
    "Dostaneš dvojice: odborný termín a jeho laické vyjádření. "
    "U každé rozhodneš, jestli laický tvar VĚCNĚ ODPOVÍDÁ odbornému termínu. "
    "Vrať POUZE validní JSON, žádný jiný text."
)

POKYN = """U každé dvojice rozhodni, jestli laický tvar věcně odpovídá odbornému termínu.

Za CHYBNOU označ dvojici, kde laický tvar:
- říká něco jiného (trombocytopenie = "nízký počet ČERVENÝCH krvinek")
- je nesrozumitelný nebo rozsypaná čeština
- je obecnější tak, že se ztratil význam (bronchospazmus = "potíže")

Za chybnou NEOZNAČUJ dvojici, která je jen stručnější nebo jinak
formulovaná, pokud význam sedí.

Vrať JSON: {"chybne": [{"i": index dvojice, "proc": "kratke zduvodneni"}]}
Když jsou všechny v pořádku, vrať {"chybne": []}."""


# Odkud se sbira: sekce, pole s odbornym terminem, pole s laickym tvarem.
# Indikace a kontraindikace pribyly 24.8. - do te doby se sbiralo jen
# z nezadoucich ucinku a zbyle dve sekce nemel kdo hlidat.
ZDROJE = (
    ("nezadouci_ucinky", "ucinek", "ucinek_laicky"),
    ("indikace", "doslovne", "laicky"),
    ("kontraindikace", "doslovne", "laicky"),
)

# Ciselnik ma smysl jen pro termin, ktery se OPAKUJE. Zmereno: nezadouci
# ucinky maji prumerne 3,0 slova a 24 % se opakuje u vic leciv, kdezto
# indikace 8,9 slova a 11 %, kontraindikace 9,5 slova a 1 %. Dlouhe vety
# ("Pripravek Ablymico je indikovan jako doplnkova lecba k diete...") jsou
# u kazdeho leku jine, takze klic slovniku se na ne uz nikdy netrefi -
# jen by ciselnik nafoukly a znecitelnily.
MAX_SLOV_KLICE = 3


def posbirej() -> dict[str, Counter]:
    """Vsechny dvojice (odborny termin -> laicke tvary s cetnosti)."""
    pary: dict[str, Counter] = defaultdict(Counter)
    for sekce, pole_odborne, pole_laicke in ZDROJE:
        for f in sorted(LECIVA_DIR.glob(f"*/json/{sekce}.json")):
            for x in json.loads(f.read_text(encoding="utf-8")):
                if not isinstance(x, dict):
                    continue
                k = klic(x.get(pole_odborne))
                laicky = ocisti_laicky(x.get(pole_laicke))
                if not k or not laicky:
                    continue
                # U nezadoucich ucinku bereme vse (jsou to kratke terminy),
                # u zbylych sekci jen to, co je opravdu TERMIN a ne veta.
                if sekce != "nezadouci_ucinky" and len(k.split()) > MAX_SLOV_KLICE:
                    continue
                pary[k][laicky] += 1
    return pary


def vyber_kanonicky(varianty: Counter) -> str:
    """Kanonicky tvar = nejcastejsi; pri shode ten kratsi.

    Kratsi zamerne - laicky tvar ma byt strucny. Delsi varianty byvaji
    rozepsane definice ("Schuzeni nemoznosti zustat v klidu, rozcileni").
    """
    return sorted(varianty.items(), key=lambda kv: (-kv[1], len(kv[0])))[0][0]


def zkontroluj_davku(dvojice: list[tuple[str, str]], model: str) -> tuple[list, float]:
    from common.ollama_client import chat
    from common.extrakce import _ocisti_odpoved

    soupis = "\n".join(f"{i}. {o}  =>  {l}" for i, (o, l) in enumerate(dvojice))
    prompt = f"{POKYN}\n\n--- DVOJICE ---\n{soupis}\n--- KONEC ---"

    t0 = time.perf_counter()
    try:
        odpoved = chat(prompt, system=SYSTEM, model=model, json_mode=True)
        data = json.loads(_ocisti_odpoved(odpoved))
    except Exception as e:
        return [{"i": -1, "proc": f"CHYBA: {type(e).__name__}: {e}"[:100]}], \
               time.perf_counter() - t0
    cas = time.perf_counter() - t0

    chybne = data.get("chybne", []) if isinstance(data, dict) else []
    platne = [c for c in chybne
              if isinstance(c, dict) and isinstance(c.get("i"), int)
              and 0 <= c["i"] < len(dvojice)]
    return platne, cas


def zapis_md(zaznamy: list[dict]) -> None:
    r = []
    r.append("# Číselník pojmů – odborný termín → laický tvar\n")
    r.append("Vzniká z extrakce nežádoucích účinků (`postav_slovnik.py`),")
    r.append("**není psaný ručně**. Slouží ke dvěma věcem:\n")
    r.append("1. **Sjednocení** – aby měl termín jeden tvar napříč aplikací.")
    r.append("   Bez toho měl každý pátý termín víc různých laických podob.")
    r.append("2. **Kontrola** – zjednodušení neověří ani doslovné porovnání")
    r.append("   se zdrojem (překlad tam doslova není), ani kontrola sekcí")
    r.append("   (té je řečeno, že zjednodušení se za chybu nepovažuje).\n")
    r.append("Sloupec **?** označuje dvojice, které kontrolní model označil")
    r.append("jako věcně nesedící – ty je potřeba projít okem.\n")

    oznacene = [z for z in zaznamy if z.get("chyba")]
    vice = [z for z in zaznamy if len(z["varianty"]) > 1]
    r.append(f"- termínů celkem: **{len(zaznamy)}**")
    r.append(f"- mělo víc laických tvarů: **{len(vice)}**")
    rucne = [z for z in zaznamy if z.get("rucne")]
    if any("chyba" in z for z in zaznamy):
        r.append(f"- označeno kontrolou: **{len(oznacene)}**")
    if rucne:
        r.append(f"- ručně ověřeno člověkem: **{len(rucne)}** "
                 f"(soubor `slovnik_rucni.json`, přebíjí generovaný tvar)")
    r.append("")

    if oznacene:
        r.append("## K ručnímu projití\n")
        r.append("| ? | odborný termín | laický tvar | co vytkla kontrola |")
        r.append("|---|---|---|---|")
        for z in oznacene:
            r.append(f"| ⚠ | {z['termin']} | {z['laicky']} | {z['chyba']} |")
        r.append("")

    r.append("## Celý číselník\n")
    r.append("| odborný termín | laický tvar | výskytů | variant | ručně |")
    r.append("|---|---|---|---|---|")
    for z in sorted(zaznamy, key=lambda x: x["termin"]):
        jine = len(z["varianty"]) - 1
        r.append(f"| {z['termin']} | {z['laicky']} | {z['vyskytu']} "
                 f"| {jine if jine else ''} | {'✔' if z.get('rucne') else ''} |")

    if vice:
        r.append("\n## Termíny, které měly víc laických tvarů\n")
        r.append("Ponechaný tvar je **tučně**. Ostatní se zahodily – slouží")
        r.append("k posouzení, jestli byl vybrán ten správný.\n")
        for z in sorted(vice, key=lambda x: -len(x["varianty"])):
            r.append(f"**{z['termin']}**")
            for v, n in sorted(z["varianty"].items(), key=lambda kv: -kv[1]):
                znak = "**" if v == z["laicky"] else ""
                r.append(f"- {znak}{v}{znak}  ({n}×)")
            r.append("")

    MD_SOUBOR.write_text("\n".join(r) + "\n", encoding="utf-8")


def main() -> int:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    p = argparse.ArgumentParser(description="Číselník pojmů z extrahovaných dat")
    p.add_argument("--zkontroluj", action="store_true", help="ověřit dvojice modelem")
    p.add_argument("--model", default=MODEL_KONTROLY)
    p.add_argument("--zapis", action="store_true", help="zapsat json + md")
    a = p.parse_args()

    from common.slovnik import rucni_prepisy

    rucni = rucni_prepisy()
    pary = posbirej()

    # Rucni prepis VYHRAVA nad tim, co je v datech. Bez toho by prestavba
    # slovniku prepsala praci cloveka tim, co vygeneroval model.
    zaznamy = []
    for t, v in sorted(pary.items()):
        z = {"termin": t, "laicky": rucni.get(t) or vyber_kanonicky(v),
             "vyskytu": sum(v.values()), "varianty": dict(v),
             "rucne": t in rucni}
        zaznamy.append(z)

    # Rucni prepis muze existovat i pro termin, ktery v datech (uz) neni -
    # treba proto, ze se lecivo vyradilo. Zahodit ho nesmime.
    znama = {z["termin"] for z in zaznamy}
    for t, laicky in sorted(rucni.items()):
        if t not in znama:
            zaznamy.append({"termin": t, "laicky": laicky, "vyskytu": 0,
                            "varianty": {laicky: 0}, "rucne": True})

    vice = [z for z in zaznamy if len(z["varianty"]) > 1]
    print(f"Odborných termínů: {len(zaznamy)}")
    print(f"Z toho s víc laickými tvary: {len(vice)} ({len(vice)/len(zaznamy):.0%})")

    if a.zkontroluj:
        print(f"\nKontroluje {a.model}, po {DAVKA} dvojicích...")
        # Rucne overene dvojice se modelem uz nekontroluji - clovek ma
        # posledni slovo a nema smysl na nej poustet slabsi model.
        ke_kontrole = [z for z in zaznamy if not z.get("rucne")]
        dvojice = [(z["termin"], z["laicky"]) for z in ke_kontrole]
        celkem_cas = 0.0
        oznaceno = 0
        for zac in range(0, len(dvojice), DAVKA):
            davka = dvojice[zac:zac + DAVKA]
            chybne, cas = zkontroluj_davku(davka, a.model)
            celkem_cas += cas
            for c in chybne:
                if c["i"] < 0:
                    print(f"  {c['proc']}")
                    continue
                z = ke_kontrole[zac + c["i"]]
                z["chyba"] = str(c.get("proc", ""))[:160]
                oznaceno += 1
                print(f"  ⚠ {z['termin']:34} -> {z['laicky'][:40]:40} {z['chyba'][:60]}")
            sys.stdout.flush()
        print(f"\nOznačeno: {oznaceno} z {len(zaznamy)} "
              f"({oznaceno/len(zaznamy):.1%}), čas {celkem_cas/60:.1f} min")

    if a.zapis:
        JSON_SOUBOR.write_text(
            json.dumps({z["termin"]: z["laicky"] for z in zaznamy},
                       ensure_ascii=False, indent=1), encoding="utf-8")
        zapis_md(zaznamy)
        print(f"\nZapsáno: {JSON_SOUBOR} ({len(zaznamy)} dvojic), {MD_SOUBOR}")
    else:
        print("\n(nic se nezapsalo - pro zápis přidej --zapis)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
