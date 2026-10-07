#!/usr/bin/env python3
"""Soubezne dotazy a rozdelovani zateze mezi stroje s Ollamou.

Odpovida na tri otazky:
  1) Jak dlouho ceka N uzivatelu naraz na ROUTER (uzke hrdlo hledani)?
     Zmereno 7. 10. 2026 na samotnem Sparku: 1 dotaz 1,6 s, 2 soubezne
     3,0 s, 4 = 6,1 s, 8 = 11,6 s - Ollama je vyrizuje po jednom.
  2) Jak se dotazy rozdeli mezi stroje (common/ollama_client.py)?
     Pustit znovu, az bude druhy stroj dostupny - cekani ma klesnout
     zhruba na polovinu.
  3) FUNGUJE VYBER STROJE a nahradni cesta pri vypadku? (--simulace)
     Dva falesne stroje na localhostu, zadna Ollama neni potreba:
     prednost prvniho, preliti na druhy, vypadek uprostred, navrat.

Pouziti (z korene projektu):
  uv run python benchmarky/soubeh/bench_soubeh.py              # skutecne stroje, router
  uv run python benchmarky/soubeh/bench_soubeh.py --hledani    # cele hledani pres API
  uv run python benchmarky/soubeh/bench_soubeh.py --soubezne 1 2 4 8 16
  uv run python benchmarky/soubeh/bench_soubeh.py --simulace   # test logiky bez Ollamy
"""

import io
import os
import sys
import json
import time
import argparse
import statistics
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

KOREN = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(KOREN))

DOTAZY = ["hrazený lék na reflux", "volně prodejný lék na bolest hlavy",
          "nežádoucí účinky paralen", "lék na kašel pro děti", "mám vysoký tlak",
          "bolí mě v krku", "dávkování vibrocil", "pálí mě žáha",
          "mám cukrovku", "lék s ibuprofenem", "horečka dítě šest let",
          "kontraindikace aspirin", "mám rýmu", "nemůžu spát", "mám alergii",
          "bolí mě klouby"]


def vypis_uzly(oc) -> None:
    for u in oc.stav_uzlu():
        stav = "dostupný" if u["dostupny"] else f"NEDOSTUPNÝ ({u['chyba']})"
        print(f"   {u['nazev']:8} {u['url']:28} {stav:26} vyřízeno {u['vyrizeno']:3} "
              f"selhalo {u['selhalo']:2} odezva {u['odezva_s']} s  "
              f"v paměti: {', '.join(u['modely_v_pameti']) or '-'}")


def zmer(funkce, urovne: list[int], oc) -> None:
    print(f"{'současně':>9} {'celkem':>8} {'medián':>8} {'nejdelší':>9} {'dotazů/s':>9}")
    for n in urovne:
        dotazy = [DOTAZY[i % len(DOTAZY)] for i in range(n)]
        pred = {u["nazev"]: u["vyrizeno"] for u in oc.stav_uzlu()}
        t0 = time.perf_counter()
        with ThreadPoolExecutor(n) as ex:
            casy = list(ex.map(funkce, dotazy))
        celkem = time.perf_counter() - t0
        po = {u["nazev"]: u["vyrizeno"] - pred[u["nazev"]] for u in oc.stav_uzlu()}
        rozdeleni = ", ".join(f"{k} {v}" for k, v in po.items() if v)
        print(f"{n:>9} {celkem:7.1f}s {statistics.median(casy):7.1f}s {max(casy):8.1f}s "
              f"{n / celkem:9.2f}   [{rozdeleni}]")


# --------------------------------------------------------------------------
# Simulace: dva falesne stroje, aby slo otestovat logiku bez druheho stroje
# --------------------------------------------------------------------------
class _Falesna(BaseHTTPRequestHandler):
    doba = 0.5                      # jak dlouho "generuje"
    zamek = threading.Lock()        # jeden pozadavek naraz, jako Spark

    def log_message(self, *a):      # ticho
        pass

    def _json(self, kod: int, data: dict) -> None:
        telo = json.dumps(data).encode()
        self.send_response(kod)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(telo)))
        self.end_headers()
        self.wfile.write(telo)

    def do_GET(self):
        if self.path == "/api/version":
            self._json(200, {"version": "simulace"})
        elif self.path == "/api/ps":
            self._json(200, {"models": [{"name": "router:test", "size": 1}]})
        else:
            self._json(404, {})

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        with type(self).zamek:
            time.sleep(type(self).doba)
        self._json(200, {"message": {"content": "{}"}, "embeddings": [[0.0]]})


def _stroj(port: int):
    trida = type(f"Stroj{port}", (_Falesna,), {"zamek": threading.Lock()})
    srv = ThreadingHTTPServer(("127.0.0.1", port), trida)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def simulace() -> int:
    os.environ["OLLAMA_UZLY"] = "prvni=http://127.0.0.1:18801,druhy=http://127.0.0.1:18802"
    os.environ["OLLAMA_SOUBEZNE"] = "1"
    import common.ollama_client as oc
    oc.INTERVAL_KONTROLY = 1.0
    chyby = 0

    def krok(nazev: str, podminka: bool, detail: str = "") -> None:
        nonlocal chyby
        chyby += not podminka
        print(f"  {'OK  ' if podminka else 'CHYBA'} {nazev}" + (f"  ({detail})" if detail else ""))

    def davka(n: int) -> dict:
        pred = {u["nazev"]: u["vyrizeno"] for u in oc.stav_uzlu()}
        with ThreadPoolExecutor(n) as ex:
            list(ex.map(lambda _: oc.chat("x", model="router:test", timeout=10), range(n)))
        return {u["nazev"]: u["vyrizeno"] - pred[u["nazev"]] for u in oc.stav_uzlu()}

    print("1) běží jen PRVNÍ stroj")
    s1 = _stroj(18801)
    r = davka(1)
    krok("jeden dotaz jde na první", r == {"prvni": 1, "druhy": 0}, str(r))
    t0 = time.perf_counter()
    r = davka(4)
    krok("čtyři souběžné jdou všechny na první (druhý neběží)", r["prvni"] == 4, str(r))
    krok("a čekají ve frontě (~2 s)", time.perf_counter() - t0 > 1.8, f"{time.perf_counter() - t0:.1f} s")
    krok("druhý je veden jako nedostupný", not oc.stav_uzlu()[1]["dostupny"])

    print("2) naběhne DRUHÝ stroj – zapojí se sám")
    s2 = _stroj(18802)
    time.sleep(2.5)
    krok("hlídač ho označil jako dostupný", oc.stav_uzlu()[1]["dostupny"])
    r = davka(1)
    krok("jeden dotaz jde dál na první (priorita)", r == {"prvni": 1, "druhy": 0}, str(r))
    t0 = time.perf_counter()
    r = davka(4)
    krok("čtyři souběžné se rozdělí 2 + 2", r == {"prvni": 2, "druhy": 2}, str(r))
    krok("a jsou hotové za polovinu (~1 s)", time.perf_counter() - t0 < 1.6, f"{time.perf_counter() - t0:.1f} s")

    print("3) PRVNÍ stroj spadne")
    s1.shutdown()
    s1.server_close()
    r = davka(3)
    krok("dotazy se bez chyby vyřídí na druhém", r["druhy"] == 3, str(r))
    krok("první je veden jako nedostupný", not oc.stav_uzlu()[0]["dostupny"])

    print("4) PRVNÍ stroj se vrátí")
    s1 = _stroj(18801)
    time.sleep(2.5)
    r = davka(1)
    krok("dotaz jde zase na první (priorita)", r == {"prvni": 1, "druhy": 0}, str(r))

    print("5) spadnou OBA")
    s1.shutdown(); s1.server_close(); s2.shutdown(); s2.server_close()
    try:
        oc.chat("x", model="router:test", timeout=5)
        krok("chyba místo zaseknutí", False, "žádná výjimka")
    except Exception as e:
        krok("chyba místo zaseknutí", True, type(e).__name__)

    print("\nSIMULACE", "PROŠLA" if not chyby else f"SELHALA ({chyby} chyb)")
    return 1 if chyby else 0


def main() -> int:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--simulace", action="store_true", help="test logiky na falešných strojích")
    ap.add_argument("--hledani", action="store_true",
                    help="celé hledání (router + vektor + DB), ne jen router")
    ap.add_argument("--soubezne", type=int, nargs="+", default=[1, 2, 4, 8])
    a = ap.parse_args()
    if a.simulace:
        return simulace()

    import common.ollama_client as oc
    from common.config import MODEL_ROUTER, MODEL_EMBED
    from common.router import rozhodni
    from common.hledani import hledej

    print("Stroje:")
    oc.priprav_modely((MODEL_ROUTER, MODEL_EMBED), hlas=print)
    time.sleep(1)
    vypis_uzly(oc)

    def router(q: str) -> float:
        t0 = time.perf_counter()
        rozhodni(q)
        return time.perf_counter() - t0

    def cele(q: str) -> float:
        t0 = time.perf_counter()
        filtr, _, syrove = rozhodni(q)
        hledej(syrove.get("dotaz_text") or q, filtr=filtr, puvodni_dotaz=q, limit=60, prah=0.6)
        return time.perf_counter() - t0

    print(f"\n{'CELÉ HLEDÁNÍ' if a.hledani else 'ROUTER'} – N uživatelů naráz:")
    zmer(cele if a.hledani else router, a.soubezne, oc)
    print("\nStroje po měření:")
    vypis_uzly(oc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
