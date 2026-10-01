#!/usr/bin/env python3
"""Benchmark: KDO lepe zjednodusuje a klicuje - qwen3.5 vs cloud.

Izoluje presne ty dva kroky, ktere podle `poznatky.md` vyrabeji nesmysly
("kysele rinceni do krku", klic "onemocneni"): z odborneho `doslovne`
udelat `laicky` + `klic`. Extrakce ani cleneni sekci se tu neresi -
vstupem je uz hotove `doslovne` z korpusu, takze modely dostanou
BAJT PO BAJTU tentyz vstup a lisi se jen vystupem.

Metriky (vsechny deterministicke, zadny model nesoudi model):
  klic_pokryti podil polozek, ktere klic vubec dostaly
  opora_klic   podil klicu, ktere projdou `klic_ma_oporu()` proti zdroji
  klic_dlouhy  podil klicu delsich nez 4 slova (porusuje zadani)
  laik_bez_op  podil VYZNAMOVYCH SLOV laickeho tvaru bez opory ve zdroji
               -> proxy na vymyslena slova; srovnatelna mezi modely

POZOR: --cloud posila text polozek na OpenAI. SPC jsou verejne dokumenty
SUKL, takze to neni unik, ale je to vedome opusteni lokalniho behu.

Pouziti:
  uv run python bench_zjednoduseni.py --leciv 8
  uv run python bench_zjednoduseni.py --leciv 8 --cloud gpt-5-nano,gpt-6-luna
  uv run python bench_zjednoduseni.py --leciv 0 --cloud gpt-6-luna --bez-lokalu
  uv run python bench_zjednoduseni.py --lokal qwen3.5:122b,gemma4:26b --json x.json
"""

import io
import sys
import json
import time
import argparse
from pathlib import Path

from common.config import LECIVA_DIR, MODEL_HLAVNI
from common.extrakce import klic_ma_oporu, _slova, _ocisti_odpoved

SEKCE = ("indikace", "kontraindikace")

# Cenik per 1M tokenu (developers.openai.com/api/docs/pricing, 2026-09-23).
CENIK = {
    "gpt-5-nano": (0.05, 0.40),
    "gpt-6-luna": (0.10, 0.50),
    "gpt-5.4-nano": (0.20, 1.25),
    "gpt-6-sol": (2.00, 10.00),
}

POKYN = """Dostanes polozky ze souhrnu udaju o pripravku (SPC).
Ke KAZDE vrat laicky tvar a klic pro vyhledavani.

- laicky: TYZ stav receny tak, jak by ho popsal laik, bez latiny
  (hypersenzitivita -> alergie, astma bronchiale -> alergicke astma).
  Kdyz je termin srozumitelny i laikovi, zopakuj ho beze zmeny.
  NIKDY si nevymyslej slova, ktera ve zdroji nemaji oporu.

- klic: 1-4 slova pro VYHLEDAVANI, nazev stavu v 1. PADE
  ("akutni prujem", NE "akutniho prujmu").
  DRZ SE SLOV ZE ZADANEHO TEXTU, neprevadej je na odbornejsi:
  "kozni vyrazka se svedenim" -> "svediva kozni vyrazka",
  NE "chronicka idiopaticka kopriva".
  SKUPINU PACIENTU ZACHOVEJ, kdyz je v textu.
  Vynech slova, ktera nejsou nazvem stavu: lecba, doplnkova, prevence,
  dlouhodobe, pokud nelze.
  Klic musi stav ROZLISOVAT. "onemocneni" nebo "potize" je spatny klic,
  protoze sedi na cokoliv - v takovem pripade vrat null.
  Kdyz v textu zadny stav neni, vrat null.

Odpovidej CESKY S DIAKRITIKOU.
Vrat POUZE JSON: {"polozky": [{"i": 0, "laicky": "...", "klic": "..."}]}
Klic "i" je poradove cislo ze vstupu. Vrat VSECHNY polozky."""


def nacti_vzorek(limit: int) -> list[dict]:
    """Davky polozek z korpusu: jedna davka = jeden lek + jedna sekce."""
    vzorek = []
    leky = sorted(p.name for p in Path(LECIVA_DIR).iterdir() if p.is_dir())
    if limit:
        leky = leky[:limit]
    for lek in leky:
        for sekce in SEKCE:
            f = Path(LECIVA_DIR) / lek / "json" / f"{sekce}.json"
            if not f.exists():
                continue
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            polozky = data.get(sekce) if isinstance(data, dict) else data
            if not isinstance(polozky, list):
                continue
            texty = [str(x.get("doslovne", "")).strip()
                     for x in polozky
                     if isinstance(x, dict) and x.get("doslovne")]
            if texty:
                vzorek.append({"lek": lek, "sekce": sekce, "texty": texty})
    return vzorek


def _prompt(texty: list[str]) -> str:
    radky = "\n".join(f"{i}. {t}" for i, t in enumerate(texty))
    return f"--- POLOZKY ---\n{radky}\n--- KONEC ---"


def _rozbal(surova: str, n: int) -> list[dict]:
    """JSON modelu -> seznam n polozek; chybejici zustanou prazdne."""
    out: list[dict] = [{} for _ in range(n)]
    try:
        d = json.loads(_ocisti_odpoved(surova))
    except (json.JSONDecodeError, TypeError):
        return out
    pol = d.get("polozky") if isinstance(d, dict) else d
    if not isinstance(pol, list):
        return out
    for j, x in enumerate(pol):
        if not isinstance(x, dict):
            continue
        i = x.get("i", j)
        if not (isinstance(i, int) and 0 <= i < n):
            i = j
        if i < n:
            out[i] = x
    return out


def zmer_lokal(davka: dict, model: str):
    from common.ollama_client import chat_detail
    t0 = time.perf_counter()
    odp, m = chat_detail(_prompt(davka["texty"]), system=POKYN, model=model,
                         json_mode=True, options={"num_ctx": 16384})
    return (_rozbal(odp, len(davka["texty"])), m.vstup_tokenu, m.vystup_tokenu,
            time.perf_counter() - t0, 0)


def zmer_cloud(davka: dict, model: str, klient, effort: str = ""):
    # Bez omezeni utrati nano na 16 polozek 16 tis. reasoning tokenu, tedy
    # 96 % vystupu. `reasoning_effort` je proto hlavni nakladova paka.
    extra = {"reasoning_effort": effort} if effort else {}
    t0 = time.perf_counter()
    r = klient.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": POKYN},
                  {"role": "user", "content": _prompt(davka["texty"])}],
        response_format={"type": "json_object"},
        **extra,
    )
    u = r.usage
    det = getattr(u, "completion_tokens_details", None)
    reason = getattr(det, "reasoning_tokens", 0) or 0
    return (_rozbal(r.choices[0].message.content, len(davka["texty"])),
            u.prompt_tokens, u.completion_tokens, time.perf_counter() - t0, reason)


def vyhodnot(nazev: str, vzorek: list[dict], vysledky: list[list[dict]],
             vstup_tok: int, vystup_tok: int, cas: float, reason_tok: int) -> dict:
    n = klic_n = opora = dlouhy = 0
    laik_slov = laik_bez = 0
    podezrele: list[dict] = []
    for davka, vys in zip(vzorek, vysledky):
        for zdroj, x in zip(davka["texty"], vys):
            n += 1
            klic = x.get("klic")
            klic = str(klic).strip() if isinstance(klic, str) and klic.strip() else None
            if klic:
                klic_n += 1
                if klic_ma_oporu(klic, zdroj):
                    opora += 1
                elif len(podezrele) < 300:
                    podezrele.append({"lek": davka["lek"], "co": "klic",
                                      "zdroj": zdroj[:90], "vystup": klic})
                if len(klic.split()) > 4:
                    dlouhy += 1
            laik = x.get("laicky")
            if isinstance(laik, str) and laik.strip():
                sl, sz = _slova(laik), _slova(zdroj)
                bez = sorted(w for w in sl if not any(w[:4] == z[:4] for z in sz))
                laik_slov += len(sl)
                laik_bez += len(bez)
                if bez and len(podezrele) < 300:
                    podezrele.append({"lek": davka["lek"], "co": "laicky",
                                      "zdroj": zdroj[:90], "vystup": laik[:90],
                                      "bez_opory": bez})
    cena = 0.0
    if nazev in CENIK:
        vin, vout = CENIK[nazev]
        cena = vstup_tok / 1e6 * vin + vystup_tok / 1e6 * vout
    return {
        "model": nazev,
        "polozek": n,
        "klic_pokryti": round(klic_n / n, 3) if n else 0.0,
        "opora_klic": round(opora / klic_n, 3) if klic_n else 0.0,
        "klic_dlouhy": round(dlouhy / klic_n, 3) if klic_n else 0.0,
        "laik_bez_op": round(laik_bez / laik_slov, 3) if laik_slov else 0.0,
        "vstup_tok": vstup_tok,
        "vystup_tok": vystup_tok,
        "reason_tok": reason_tok,
        "cas_s": round(cas, 1),
        "cena_usd": round(cena, 4),
        "podezrele": podezrele,
    }


def _bez(vzorek, i):
    return [{} for _ in vzorek[i]["texty"]]


def _zprava(jmeno, vzorek, vys, vi, vo, cas, rt, model_pro_cenik):
    """vyhodnot() + prejmenovani; cenik se hleda podle holeho nazvu modelu."""
    z = vyhodnot(model_pro_cenik, vzorek, vys, vi, vo, cas, rt)
    z["model"] = jmeno
    return z


def main() -> int:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--leciv", type=int, default=8, help="kolik leciv; 0 = vsechna")
    ap.add_argument("--cloud", default="", help="carkou oddelene OpenAI modely")
    ap.add_argument("--lokal", default=MODEL_HLAVNI,
                    help="carkou oddelene lokalni modely")
    ap.add_argument("--bez-lokalu", action="store_true")
    ap.add_argument("--effort", default="",
                    help="reasoning_effort pro cloud: minimal|low|medium|high")
    ap.add_argument("--json", type=Path, default=Path("bench_zjednoduseni.json"))
    a = ap.parse_args()

    vzorek = nacti_vzorek(a.leciv)
    if not vzorek:
        print("CHYBA: vzorek je prazdny", file=sys.stderr)
        return 1
    polozek = sum(len(d["texty"]) for d in vzorek)
    print(f"vzorek: {len(vzorek)} davek / {polozek} polozek "
          f"/ {len({d['lek'] for d in vzorek})} leciv\n")

    zpravy = []
    behy: list[tuple[str, object]] = []
    if not a.bez_lokalu:
        behy += [(m.strip(), None) for m in a.lokal.split(",") if m.strip()]
    klient = None
    modely = [m.strip() for m in a.cloud.split(",") if m.strip()]
    if modely:
        from openai import OpenAI
        from common.config import nacti_openai_klic
        klient = OpenAI(api_key=nacti_openai_klic())
        behy += [(m, klient) for m in modely]

    # Syrove odpovedi se ukladaji PO KAZDE DAVCE. Prvni beh se zapisoval az
    # na konci a pad IDE ve 3/4 shodil vysledky dvou modelu vcetne
    # zaplacenych tokenu. Ze syroveho souboru jde metriky prepocitat
    # kdykoliv znovu, bez jedineho dalsiho volani.
    syrove = a.json.with_suffix(".syrove.json")
    stav: dict = {}
    if syrove.exists():
        try:
            stav = json.loads(syrove.read_text(encoding="utf-8"))
            print(f"navazuji na {syrove} ({len(stav)} modelu)\n")
        except json.JSONDecodeError:
            stav = {}

    for model, kl in behy:
        jmeno = f"{model}/{a.effort}" if (kl and a.effort) else model
        hotovo = stav.get(jmeno, {})
        vys = hotovo.get("vysledky", [])
        vi = hotovo.get("vstup_tok", 0)
        vo = hotovo.get("vystup_tok", 0)
        cas = hotovo.get("cas_s", 0.0)
        rt = hotovo.get("reason_tok", 0)
        if len(vys) >= len(vzorek):
            print(f"-> {jmeno}: uz hotovo, preskakuji\n", flush=True)
            zpravy.append(_zprava(jmeno, vzorek, vys, vi, vo, cas, rt, model))
            continue

        print(f"-> {jmeno} ({'OpenAI' if kl else 'lokalne'})"
              f"{f' (navazuji od {len(vys)})' if vys else ''}", flush=True)
        for k in range(len(vys), len(vzorek)):
            d = vzorek[k]
            try:
                r, i, o, c, rr = (zmer_cloud(d, model, kl, a.effort) if kl
                                  else zmer_lokal(d, model))
            except Exception as e:
                print(f"   CHYBA {d['lek']}: {type(e).__name__}: {e}"[:140],
                      flush=True)
                r, i, o, c, rr = _bez(vzorek, k), 0, 0, 0.0, 0
            vys.append(r)
            vi += i
            vo += o
            cas += c
            rt += rr
            stav[jmeno] = {"vysledky": vys, "vstup_tok": vi, "vystup_tok": vo,
                           "cas_s": cas, "reason_tok": rt}
            syrove.write_text(json.dumps(stav, ensure_ascii=False),
                              encoding="utf-8")
            print(f"   {k + 1}/{len(vzorek)} {d['lek'][:26]:26} "
                  f"{d['sekce'][:14]:14} {c:5.1f}s", flush=True)
        zpravy.append(_zprava(jmeno, vzorek, vys, vi, vo, cas, rt, model))
        print()

    hl = (f"{'model':16} {'polozek':>7} {'pokryti':>8} {'opora':>7} {'dlouhy':>7} "
          f"{'laik_bez_op':>11} {'vstup':>8} {'vystup':>8} {'reason':>7} "
          f"{'cas_s':>8} {'USD':>8}")
    print("=" * len(hl))
    print(hl)
    print("-" * len(hl))
    for z in zpravy:
        print(f"{z['model'][:16]:16} {z['polozek']:7} {z['klic_pokryti']:8.3f} "
              f"{z['opora_klic']:7.3f} {z['klic_dlouhy']:7.3f} "
              f"{z['laik_bez_op']:11.3f} {z['vstup_tok']:8} {z['vystup_tok']:8} "
              f"{z['reason_tok']:7} {z['cas_s']:8.1f} {z['cena_usd']:8.4f}")

    a.json.write_text(json.dumps(zpravy, ensure_ascii=False, indent=2),
                      encoding="utf-8")
    print(f"\nulozeno do {a.json}  (podezrele nalezy uvnitr)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
