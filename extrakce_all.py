#!/usr/bin/env python3
"""Cela pipeline korpusu jako JEDEN seznam kroku: od API SUKL po hotovou DB.

    1 konverze -> 2 sekce -> 3 extrakce -> 4 db -> 5 embeddingy -> 6 rejstrik -> 7 evaluace

Tohle je jedine misto, kde je videt, co se v pipeline dela a v jakem
poradi (KROKY niz). Kazdy krok je samostatny skript, ktery jde pustit
i zvlast; tenhle soubor je jen poskladá, hlida navratove kody a nepusti
dalsi krok, kdyz predchozi nedobehl.

CO KTERY KROK POTREBUJE (pro mesicni job na serveru):
    1 konverze    API SUKL, EMA (limit 429!), Docling Serve, MS Word pro .doc
    3 extrakce    OpenAI Batch API - klic v key.yaml, rozpoctovy strop
                  config.CLOUD_STROP_USD; davka dobiha az 24 h
    4 db          Postgres; --korpus maze a plni od nuly (hledaci slovnik zustava)
    5 embeddingy  Ollama (bge-m3)
    7 evaluace    Ollama (router), Postgres

NAVAZOVANI: kroky 1, 3 a 5 si drzi stav po dokumentu a po padu navazou
stejnym prikazem. Kroky 2, 4, 6 jedou vzdy cele. Po padu tedy staci
`--od <krok>`.

KROK 3 MA DVE CESTY: vychozi je cloud (OpenAI Batch). S --local jede
pres Ollamu (config.MODEL_HLAVNI nebo --model) - jen pro jeden kod SUKL
(--kody) nebo malou davku z fronty (--limit): kdyz cloud neni dostupny,
na rychlou opravu leku nebo zkousku noveho lokalniho modelu. Cely korpus
lokalne by trval ~10 dni. Vystup i dalsi kroky jsou stejne.

KROK 3 JE V CLOUDU ASYNCHRONNI: skript ceka, dokud davky u OpenAI nedobehnou.
Kdyz uz bezi jina instance (zamek), skonci hned s kodem 0 - proto se
po nem OVERUJE, ze ve fronte nic nezbylo; jinak by se do DB nahrala
smes starych a novych dat.

CO V PIPELINE NENI: kontroly extrakce (nerealizovane_kontroly/) a
prirustkove plneni DB (todo.md).

Pouziti:
  uv run python extrakce_all.py --seznam              # jen vypsat kroky
  uv run python extrakce_all.py --stav                # kde ktery krok je
  uv run python extrakce_all.py --vse                 # vsechno po rade
  uv run python extrakce_all.py --od db               # od kroku dal
  uv run python extrakce_all.py --jen sekce extrakce  # jen vybrane kroky

  # krok 3 LOKALNE (Ollama) misto cloudu - jeden lek / mala davka:
  uv run python extrakce_all.py --jen extrakce --local --kody 0260480
  uv run python extrakce_all.py --jen extrakce --local --kody 0260480 --model gemma4:26b
  uv run python extrakce_all.py --od extrakce --local --limit 40   # co ceka ve fronte, pak DB...
"""

import io
import sys
import time
import sqlite3
import argparse
import subprocess
from pathlib import Path
from datetime import datetime

from common.config import DATA_DIR

# Poradi je ZAVAZNE - kazdy krok cte to, co vyrobil predchozi.
# (id, popis, skript, argumenty, vnejsi sluzby)
KROKY = [
    ("konverze",   "seznam leciv z API SUKL, inventar SPC, stazeni, prevod, kontroly prevodu",
     "extrakce_1_konverze.py", ["--obchodovana"], "API SUKL, EMA, Docling Serve"),
    ("sekce",      "sekce 4.1 / 4.2 / 4.3 / 4.8 z markdownu a PDF",
     "extrakce_2_sekce.py", [], "-"),
    ("extrakce",   "sekce -> JSON (laicky tvar, klic, frekvence) pres OpenAI Batch",
     "extrakce_3_json.py", ["--beh"], "OpenAI (key.yaml)"),
    ("db",         "naplneni Postgresu od nuly + vek pouziti",
     "extrakce_4_db.py", ["--korpus"], "Postgres"),
    ("embeddingy", "vektory pro hledaci radky a klice (jen chybejici)",
     "extrakce_5_embeddingy.py", [], "Ollama bge-m3, Postgres"),
    ("rejstrik",   "data/leky + _rejstrik.csv (hledani slozky SPC podle nazvu a kodu)",
     "extrakce_6_rejstrik.py", [], "-"),
    ("evaluace",   "kvalita dat + parafraze podle ATC + negativni dotazy",
     "hledani_evaluace.py", [], "Ollama router, Postgres"),
]
ID_KROKU = [k[0] for k in KROKY]

STAV_KONVERZE = DATA_DIR / "spc" / "_stav.sqlite"
STAV_EXTRAKCE = DATA_DIR / "spc" / "_extrakce" / "stav.sqlite"
LOG_DIR = Path("logs")


def ted() -> str:
    return datetime.now().isoformat(sep=" ", timespec="seconds")


class Log:
    """Radek na obrazovku i do logs/extrakce_all_<cas>.log. Vystup samotnych
    kroku jde rovnou na obrazovku (bez bufferu) - do souboru jen zacatky,
    konce, navratove kody a doby."""

    def __init__(self) -> None:
        LOG_DIR.mkdir(exist_ok=True)
        self.soubor = LOG_DIR / f"extrakce_all_{datetime.now():%Y%m%d_%H%M%S}.log"
        self.f = self.soubor.open("a", encoding="utf-8")

    def __call__(self, text: str) -> None:
        radek = f"{ted()} {text}"
        print(radek, flush=True)
        self.f.write(radek + "\n")
        self.f.flush()


def zamkni():
    """Zamek proti soubeznemu behu cele pipeline (cron + rucni spusteni).
    Drzi ho operacni system, takze po padu nezustane viset. None = uz bezi."""
    f = open(DATA_DIR / "extrakce_all.lock", "a+")
    try:
        if sys.platform == "win32":
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return None
    return f


def _pocty(db: Path, sql: str) -> dict[str, int]:
    if not db.exists():
        return {}
    c = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=30)
    try:
        return {str(k): n for k, n in c.execute(sql).fetchall()}
    finally:
        c.close()


def stav_extrakce() -> dict[str, int]:
    return _pocty(STAV_EXTRAKCE, "SELECT stav, count(*) FROM pozadavky GROUP BY stav")


def over_extrakci(log: Log) -> bool:
    """Po kroku 3: nesmi zustat nic ve fronte ani u OpenAI."""
    st = stav_extrakce()
    nedobehlo = st.get("cekajici", 0) + st.get("odeslano", 0)
    chyb = sum(n for k, n in st.items() if k.startswith(("chyba", "selhal")))
    if nedobehlo:
        log(f"STOP: extrakce NEDOBEHLA - ve fronte {st.get('cekajici', 0)}, "
            f"u OpenAI {st.get('odeslano', 0)} pozadavku. Nejspis bezi jina instance, "
            f"nebo zasahl rozpoctovy strop. Stav: extrakce_3_json.py --stav")
        return False
    if chyb:
        log(f"POZOR: {chyb} pozadavku skoncilo chybou (data/spc/_extrakce/report.md). "
            f"Do DB pujdou jejich STARE vystupy, pokud existuji. "
            f"Oprava: extrakce_3_json.py --znovu-chybne --beh")
    return True


def vypis_seznam() -> None:
    print(f"{'#':>2} {'krok':11} {'skript':38} {'sluzby':30} co dela")
    print("-" * 130)
    for i, (kid, popis, skript, argy, sluzby) in enumerate(KROKY, 1):
        print(f"{i:>2} {kid:11} {(skript + ' ' + ' '.join(argy)).strip():38} {sluzby:30} {popis}")


def vypis_stav() -> None:
    """Kde ktery krok je - jen cteni stavovych souboru a DB, nic nespousti."""
    print("1 konverze  ", end="")
    k = _pocty(STAV_KONVERZE, "SELECT stav, count(*) FROM spc GROUP BY stav")
    print(k or "stav nenalezen (data/spc/_stav.sqlite)")
    sekci = sum(1 for _ in (DATA_DIR / "spc").glob("*/sekce/_prehled.json")) \
        if (DATA_DIR / "spc").exists() else 0
    print(f"2 sekce      SPC s vytazenymi sekcemi: {sekci}")
    print(f"3 extrakce   {stav_extrakce() or 'stav nenalezen (data/spc/_extrakce/stav.sqlite)'}")
    try:
        import psycopg
        from common.config import PG_DSN
        with psycopg.connect(PG_DSN, connect_timeout=5) as c:
            leciv, spc = c.execute("SELECT count(*), count(*) FILTER (WHERE zastupce AND spc IS NOT NULL) "
                                   "FROM leciva").fetchone()
            radku, bez = c.execute("SELECT count(*), count(*) FILTER (WHERE embedding IS NULL) "
                                   "FROM leciva_search").fetchone()
        print(f"4 db         kodu {leciv}, SPC {spc}, hledacich radku {radku}")
        print(f"5 embeddingy radku bez vektoru: {bez}")
    except Exception as e:                      # DB nebezi - stav zbytku je i tak uzitecny
        print(f"4-5 db       nedostupna: {type(e).__name__}: {str(e)[:80]}")
    rej = DATA_DIR / "spc" / "_rejstrik.csv"
    print(f"6 rejstrik   {datetime.fromtimestamp(rej.stat().st_mtime):%Y-%m-%d %H:%M}"
          if rej.exists() else "6 rejstrik   neexistuje")
    print("7 evaluace   bez ulozeneho stavu - pustit: hledani_evaluace.py")


def main() -> int:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--vse", action="store_true", help="vsechny kroky po rade")
    g.add_argument("--od", choices=ID_KROKU, help="od tohoto kroku dal")
    g.add_argument("--jen", nargs="+", choices=ID_KROKU, help="jen tyhle kroky (v poradi pipeline)")
    g.add_argument("--stav", action="store_true", help="kde ktery krok je, nic nespousti")
    g.add_argument("--seznam", action="store_true", help="vypsat kroky a skoncit")
    ap.add_argument("--local", action="store_true",
                    help="krok extrakce LOKALNE pres Ollamu misto OpenAI (maly rozsah)")
    ap.add_argument("--model", help="s --local: model v Ollame (vychozi config.MODEL_HLAVNI)")
    ap.add_argument("--kody", nargs="+", metavar="KOD",
                    help="s --local: kody SUKL, jejichz SPC se extrahuji znovu")
    ap.add_argument("--sekce", nargs="+", metavar="SEKCE", help="s --local: jen tyto sekce")
    ap.add_argument("--limit", type=int, help="s --local bez --kody: nejvys N pozadavku z fronty")
    a = ap.parse_args()
    if (a.model or a.kody or a.sekce or a.limit) and not a.local:
        ap.error("--model, --kody, --sekce a --limit plati jen s --local")

    if a.seznam:
        vypis_seznam()
        return 0
    if a.stav:
        vypis_stav()
        return 0

    if a.jen:
        vybrane = [k for k in KROKY if k[0] in a.jen]
    else:
        vybrane = KROKY[ID_KROKU.index(a.od):] if a.od else KROKY

    zamek = zamkni()
    if zamek is None:
        print(f"{ted()} pipeline uz bezi (data/extrakce_all.lock), koncim")
        return 0
    log = Log()
    log(f"START kroky: {', '.join(k[0] for k in vybrane)} | log {log.soubor}")

    t_vse = time.perf_counter()
    for kid, popis, skript, argy, _ in vybrane:
        cislo = ID_KROKU.index(kid) + 1
        if kid == "extrakce" and a.local:
            argy = ["--local"]
            for prep, hodn in (("--model", a.model), ("--limit", a.limit)):
                if hodn:
                    argy += [prep, str(hodn)]
            for prep, hodn in (("--kody", a.kody), ("--sekce", a.sekce)):
                if hodn:
                    argy += [prep, *hodn]
        log(f"KROK {cislo} {kid}: {popis}  [{skript} {' '.join(argy)}]")
        t0 = time.perf_counter()
        try:
            kod = subprocess.run([sys.executable, skript, *argy]).returncode
        except KeyboardInterrupt:
            log(f"PRERUSENO v kroku {kid} (Ctrl+C). Navazat: extrakce_all.py --od {kid}")
            return 130
        log(f"KROK {cislo} {kid}: navratovy kod {kod}, {(time.perf_counter() - t0) / 60:.1f} min")
        if kod != 0:
            log(f"STOP: krok {kid} selhal. Po oprave navazat: extrakce_all.py --od {kid}")
            return kod
        if kid == "extrakce" and not over_extrakci(log):
            return 3

    log(f"HOTOVO: {len(vybrane)} kroku za {(time.perf_counter() - t_vse) / 60:.1f} min. "
        f"API po zmene dat restartovat.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
