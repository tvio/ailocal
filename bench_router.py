#!/usr/bin/env python3
"""Benchmark: router na ruznych lokalnich modelech - rychlost i spravnost.

Router je 92 % casu dotazu (poznatky.md 20.8.), takze jeho rychlost je
primo to, co uzivatel ceka. Zaroven neni deterministicky - stejny dotaz
z nej vyjde ruzne. Proto se tu kazdy dotaz pousti VICKRAT a meri se i
stabilita, ne jen jeden stastny beh.

Dve casti:
  A) PRAVIDLA - dotazy s overitelnym ocekavanim podle promptu routeru:
     sekce, filtry, zapor, diakritika, "nedomyslet si". Vystup se bere
     az PO zpracovani v `rozhodni()` (vcetne obnov_diakritiku), tedy
     presne to, co jde do hledani.
  B) END-TO-END - parafraze z evaluate.py pres router + hledani s prahem
     0,60, jako v hledej.py. Test 4 v evaluate.py ma filtr natvrdo
     a router vubec nevola; tady se meri, jestli se uzivatel k leku
     skutecne dostane.

Casy: `cas` je cele volani routeru (to ceka uzivatel), `tok/s` je
generovani vystupu z metrik Ollamy. U MoE rozhoduje aktivni cast
parametru, ne celkova velikost - odhadovat se to nesmi.

Pouziti:
  uv run python bench_router.py
  uv run python bench_router.py --modely gemma4:26b,gemma4:31b --opakovani 3
"""

import io
import sys
import json
import time
import argparse
import statistics
import unicodedata
from pathlib import Path
from collections import Counter

import common.ollama_client as oc
from common.config import MODEL_ROUTER
from common.router import rozhodni
from common.hledani import hledej, seskup

PRAH = 0.60
REZERVA = 60      # jako hledej.py

FILTRY = ("nazev", "kod_sukl", "ucinna_latka", "atc_prefix", "na_predpis",
          "hrazeno", "frekvence", "sila", "organovy_system",
          "frekvence_rank_max")


def _bez(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s or "")
                   if unicodedata.category(c) != "Mn").lower()


# --- Kontroly: (popis, funkce(filtr, dotaz_text) -> bool) -------------------
def sekce(*ocek):
    return (f"sekce={'+'.join(ocek)}",
            lambda f, t: set(f.sekce or []) == set(ocek))


def pole(klic, hodnota):
    """Textova pole se porovnavaji bez diakritiky a velikosti ('Paralen')."""
    def ok(f, t):
        v = getattr(f, klic)
        if isinstance(hodnota, str):
            return isinstance(v, str) and _bez(hodnota) in _bez(v)
        return v == hodnota
    return (f"{klic}={hodnota}", ok)


def text_ma(kus):
    """Presny podretezec VCETNE diakritiky - jeji ztrata stoji ~0,2 cosine."""
    return (f"text~'{kus}'", lambda f, t: kus in (t or "").lower())


def text_nema(kus):
    return (f"text!~'{kus}'", lambda f, t: kus not in (t or "").lower())


def kratky(n):
    return (f"text<={n} slov", lambda f, t: len((t or "").split()) <= n)


# Pravidlo 2 zadani: kdyz v dotazu neni nic o filtru, filtr se nepouzije.
# Kazdy pripad vyjmenuje, ktere filtry OCEKAVA; ostatni musi zustat None.
def nic_navic(*povolene):
    def ok(f, t):
        return all(getattr(f, k) is None for k in FILTRY if k not in povolene)
    return ("nic navíc", ok)


def _navic(f, povolene) -> list[str]:
    return [f"{k}={getattr(f, k)!r}" for k in FILTRY
            if k not in povolene and getattr(f, k) is not None]


# (dotaz, kontroly, povolene filtry pro vypis "navic")
PRIPADY = [
    # --- symptom bez leku = VZDY indikace
    ("bolí mě hlava", [sekce("indikace"), text_ma("hlav")], ()),
    ("po vepřovém mě bolí břicho", [sekce("indikace"), text_ma("břich")], ()),
    ("pálí mě žáha", [sekce("indikace"), text_ma("žáh")], ()),
    ("mám ucpaný nos", [sekce("indikace"), text_ma("nos")], ()),
    ("můj syn má horečku, co mu můžu dát",
     [sekce("indikace"), text_ma("horeč"), kratky(3)], ()),
    # --- vylozene nezadouci ucinek
    ("po tom léku mě bolí břicho", [sekce("nezadouci_ucinky"), text_ma("břich")], ()),
    ("Bolest zad nežádoucí účinek",
     [sekce("nezadouci_ucinky"), text_ma("bolest")], ()),
    # --- konkretni lek + priznak bez smeru = obe sekce
    ("paralen bolest břicha",
     [sekce("indikace", "nezadouci_ucinky"), pole("nazev", "paralen"),
      text_ma("břich")], ("nazev",)),
    # --- zapor je soucast priznaku
    ("nemůžu po prášcích spát", [text_ma("nemůž"), text_ma("spát")], ()),
    ("nechce se mi jíst", [sekce("indikace"), text_ma("nechce")], ()),
    # --- vydej a hrazeni jsou dve ruzne veci
    ("volně prodejný lék na rýmu",
     [sekce("indikace"), pole("na_predpis", False), text_ma("rým")], ("na_predpis",)),
    ("hrazené antibiotikum",
     [sekce("indikace"), pole("hrazeno", True)], ("hrazeno",)),
    ("nehrazený lék na průjem",
     [sekce("indikace"), pole("hrazeno", False), text_ma("průjem")], ("hrazeno",)),
    ("hrazený lék na předpis na alergii",
     [sekce("indikace"), pole("hrazeno", True), pole("na_predpis", True),
      text_ma("alergi")], ("hrazeno", "na_predpis")),
    ("mám alergii na pyl, co si můžu koupit bez receptu",
     [sekce("indikace"), pole("na_predpis", False), kratky(4)], ("na_predpis",)),
    # --- diakritika: uzivatel ji nenapsal, model ji ma DOPLNIT
    # (obnov_diakritiku tu nepomuze, nema odkud ji vzit)
    ("lek na zacpu", [sekce("indikace"), text_ma("zácp")], ()),
    ("neco na kasel", [sekce("indikace"), text_ma("kašel")], ()),
    # --- vata a "lecba" do dotaz_textu nepatri
    ("léčba roztroušené sklerózy",
     [sekce("indikace"), text_nema("léčb"), text_ma("roztrouš")], ()),
    # --- frekvence: presna hodnota, rank jen u vyslovneho "a castejsi"
    ("vzácné vedlejší účinky paralenu",
     [sekce("nezadouci_ucinky"), pole("frekvence", "vzácné"),
      pole("nazev", "paralen")], ("frekvence", "nazev")),
    ("velmi časté nežádoucí účinky ACC",
     [sekce("nezadouci_ucinky"), pole("frekvence", "velmi časté"),
      pole("nazev", "acc")], ("frekvence", "nazev")),
    ("časté a častější nežádoucí účinky",
     [sekce("nezadouci_ucinky"), pole("frekvence_rank_max", 2)],
     ("frekvence_rank_max",)),
    # --- atributy, organovy system, dalsi sekce
    ("Paralen 500 mg",
     [sekce("atributy"), pole("nazev", "paralen"), pole("sila", "500MG")],
     ("nazev", "sila")),
    ("co dělá Paralen se srdcem",
     [sekce("nezadouci_ucinky"), pole("nazev", "paralen"),
      pole("organovy_system", "Srdeční poruchy"), text_ma("srd")],
     ("nazev", "organovy_system")),
    ("kdy nesmím užívat Aerius",
     [sekce("kontraindikace"), pole("nazev", "aerius")], ("nazev",)),
    ("kolik tablet Paralenu můžu denně",
     [sekce("davkovani"), pole("nazev", "paralen")], ("nazev",)),
    ("lék s paracetamolem bez receptu",
     [pole("ucinna_latka", "paracetamol"), pole("na_predpis", False)],
     ("ucinna_latka", "na_predpis")),
]
# "nic navic" se pridava ke kazdemu pripadu automaticky.
PRIPADY = [(d, k + [nic_navic(*p)], p) for d, k, p in PRIPADY]


# --- Mereni -----------------------------------------------------------------
_posledni: list = []
_puvodni_detail = oc.chat_detail


def _chat_s_metrikou(prompt, **kw):
    """Nahrada ollama_client.chat, ktera si schova Metriky.

    `rozhodni()` importuje `chat` az pri volani, takze staci vymenit
    atribut modulu - router se nemusi kvuli benchmarku menit.
    """
    odp, m = _puvodni_detail(prompt, **kw)
    _posledni.append(m)
    return odp


def zavolej(dotaz: str, model: str):
    _posledni.clear()
    t0 = time.perf_counter()
    filtr, jistota, d = rozhodni(dotaz, model=model)
    cas = time.perf_counter() - t0
    m = _posledni[0] if _posledni else None
    return filtr, jistota, d, cas, m


def _otisk(f, t) -> str:
    """Co z routeru jde do hledani - pro mereni stability."""
    return json.dumps({"sekce": sorted(f.sekce or []), "text": t,
                       **{k: getattr(f, k) for k in FILTRY}},
                      ensure_ascii=False, sort_keys=True)


def zmer_model(model: str, opak: int, parafraze: list) -> dict:
    print(f"\n-> {model}", flush=True)
    # Zahrati: prvni volani nese nacteni vah. Do casu se nepocita,
    # ale nacteni se zapise zvlast - u studeneho startu je to to,
    # co uzivatel ceka nejdele.
    _, _, _, cas0, m0 = zavolej("bolí mě hlava", model)
    nacteni = m0.cas_nacteni_s if m0 else 0.0
    pamet = oc.nactene_modely().get(model, 0.0)
    print(f"   zahrati {cas0:.1f} s (nacteni vah {nacteni:.1f} s), "
          f"v pameti {pamet:.1f} GB", flush=True)

    casy, tok_s, vystup, chyby_json = [], [], [], 0
    pripady = []
    for dotaz, kontroly, povolene in PRIPADY:
        behy = []
        for _ in range(opak):
            f, jistota, d, cas, m = zavolej(dotaz, model)
            if "chyba" in d:
                chyby_json += 1
            t = d.get("dotaz_text", "")
            casy.append(cas)
            if m:
                tok_s.append(m.tok_za_s)
                vystup.append(m.vystup_tokenu)
            spln = {p: bool(fn(f, t)) for p, fn in kontroly}
            behy.append({"text": t, "sekce": f.sekce, "jistota": jistota,
                         "navic": _navic(f, povolene), "kontroly": spln,
                         "otisk": _otisk(f, t), "cas": round(cas, 2)})
        nejcastejsi = Counter(b["otisk"] for b in behy).most_common(1)[0][1]
        ok_vsech = sum(all(b["kontroly"].values()) for b in behy)
        pripady.append({"dotaz": dotaz, "ok_behu": ok_vsech,
                        "stabilni": nejcastejsi == opak, "behy": behy})
        znak = "OK " if ok_vsech == opak else f"{ok_vsech}/{opak}"
        spatne = sorted({p for b in behy for p, v in b["kontroly"].items() if not v})
        print(f"   {znak:4} {dotaz[:44]:44} "
              f"{'' if not spatne else 'X ' + ', '.join(spatne)}"[:150], flush=True)

    # B) end-to-end: router + hledani s prahem, jako hledej.py
    e2e_ok, e2e_det = 0, []
    for dotaz, ocekavane in parafraze:
        for _ in range(opak):
            f, _, d, cas, m = zavolej(dotaz, model)
            casy.append(cas)
            if m:
                tok_s.append(m.tok_za_s)
            o = hledej(d.get("dotaz_text") or dotaz, filtr=f, puvodni_dotaz=dotaz,
                       limit=REZERVA, prah=PRAH)
            nalez = [l.nazev for l in seskup(o.vysledky, leciv=5)]
            if any(e in nalez for e in ocekavane):
                e2e_ok += 1
            else:
                e2e_det.append(f"{dotaz!r} [{d.get('dotaz_text')!r}, "
                               f"{f.sekce}] -> {', '.join(nalez[:3]) or '(nic)'}")
    print(f"   end-to-end parafraze: {e2e_ok}/{len(parafraze) * opak}", flush=True)
    for x in e2e_det[:6]:
        print(f"      {x}", flush=True)

    n_kontrol = sum(len(k) for _, k, _ in PRIPADY) * opak
    ok_kontrol = sum(v for p in pripady for b in p["behy"]
                     for v in b["kontroly"].values())
    return {
        "model": model,
        "nacteni_s": round(nacteni, 1),
        "pamet_gb": round(pamet, 1),
        "cas_median_s": round(statistics.median(casy), 2),
        "cas_p90_s": round(sorted(casy)[int(len(casy) * 0.9) - 1], 2),
        "tok_s": round(statistics.median(tok_s), 1) if tok_s else 0.0,
        "vystup_median": int(statistics.median(vystup)) if vystup else 0,
        "pripadu_ok": sum(p["ok_behu"] == opak for p in pripady),
        "pripadu": len(pripady),
        "kontrol_ok": ok_kontrol,
        "kontrol": n_kontrol,
        "stabilnich": sum(p["stabilni"] for p in pripady),
        "chyby_json": chyby_json,
        "e2e_ok": e2e_ok,
        "e2e": len(parafraze) * opak,
        "e2e_selhani": e2e_det,
        "pripady": pripady,
    }


def main() -> int:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--modely", default=f"{MODEL_ROUTER},gemma4:31b,gemma4:26b")
    ap.add_argument("--opakovani", type=int, default=3)
    ap.add_argument("--json", type=Path, default=Path("bench_router.json"))
    a = ap.parse_args()

    from evaluate import PARAFRAZE
    oc.chat = _chat_s_metrikou

    modely = [m.strip() for m in a.modely.split(",") if m.strip()]
    print(f"{len(PRIPADY)} pripadu x {a.opakovani} + {len(PARAFRAZE)} parafrazi "
          f"x {a.opakovani}, modely: {', '.join(modely)}")

    zpravy = []
    for model in modely:
        zpravy.append(zmer_model(model, a.opakovani, PARAFRAZE))
        # Po kazdem modelu, at pad uprostred neshodi hotove vysledky.
        a.json.write_text(json.dumps(zpravy, ensure_ascii=False, indent=1),
                          encoding="utf-8")

    hl = (f"{'model':14} {'nacteni':>8} {'GB':>5} {'cas_med':>8} {'cas_p90':>8} "
          f"{'tok/s':>6} {'pripady':>8} {'kontroly':>9} {'stabilni':>8} "
          f"{'e2e':>7}")
    print("\n" + "=" * len(hl))
    print(hl)
    print("-" * len(hl))
    for z in zpravy:
        print(f"{z['model'][:14]:14} {z['nacteni_s']:7.1f}s {z['pamet_gb']:5.1f} "
              f"{z['cas_median_s']:7.2f}s {z['cas_p90_s']:7.2f}s {z['tok_s']:6.1f} "
              f"{z['pripadu_ok']:4}/{z['pripadu']:<3} "
              f"{z['kontrol_ok']:4}/{z['kontrol']:<4} "
              f"{z['stabilnich']:4}/{z['pripadu']:<3} "
              f"{z['e2e_ok']:3}/{z['e2e']:<3}")
    print(f"\npripady = OK ve VSECH {a.opakovani} behech; stabilni = vsechny behy "
          f"daly totez; e2e = parafraze pres router + hledani, prah {PRAH}")
    print(f"ulozeno do {a.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
