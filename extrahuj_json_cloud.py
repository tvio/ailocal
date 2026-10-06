#!/usr/bin/env python3
"""Krok 3 pipeline: extrakce sekci do JSON. Dve cesty, STEJNY prompt i vystup:

  --beh     CLOUD, OpenAI Batch API (gpt-6-luna). Vychozi cesta pro korpus.
  --local   LOKALNE, Ollama, jedna sekce po druhe. Pro jeden kod SUKL nebo
            malou davku: cloud neni dostupny, rychla oprava jednoho leku,
            zkouska noveho lokalniho modelu (--model). Na cely korpus NE -
            25 M vystupnich tokenu je pri 30 tok/s ~10 dni.

Prompt, orez i zpracovani odpovedi jsou u obou PRESNE tytez
(common/extrakce.py: uzivatelsky_prompt, zpracuj_odpoved); lisi se jen
doprava pozadavku. Ktery model sekci vytezil, je v json/_stav.json.

JAK FUNGUJE BATCH API (OpenAI)
    1. JSONL soubor, jeden radek = jeden pozadavek s VLASTNIM celym promptem:
       {"custom_id": "...", "method": "POST", "url": "/v1/chat/completions",
        "body": {model, messages, response_format, reasoning_effort, ...}}
    2. soubor se nahraje (files, purpose="batch") -> input_file_id
    3. vytvori se davka (batches.create, completion_window="24h") -> batch_id
    4. OpenAI ji zpracuje do 24 h: validating -> in_progress -> finalizing
       -> completed | failed (neprosla validace) | expired (nestihlo se)
    5. vysledky: output_file_id (uspesne radky), error_file_id (chybne
       radky). PORADI NENI zarucene - paruje se podle custom_id.
       U 'expired' je v output_file hotova cast, zbytek v error_file.
    Cena je poloviční proti sync volani.

STAV - data/spc/_extrakce/stav.sqlite (prezije pad, Ctrl+C i restart PC)
    pozadavky  1 radek = 1 SPC x 1 sekce. stav:
                 cekajici   jeste neodeslano (nebo vraceno k opakovani)
                 odeslano   je v rozjete davce
                 hotovo     vysledek zapsan (json/<sekce>.json + _stav.json)
                 chyba      pozadavek neprosel - duvod ve sloupci chyba
                 bez_sekce  sekce v SPC neni -> nic se neposila
    davky      1 radek = 1 davka Batch API (batch_id, soubory, stav, cena)

    custom_id = "<slozka>|<sekce>|p<pokus>" - pokus odlisi opakovani.

VYSTUPY
    data/spc/<slozka>/json/<sekce>.json, json/_stav.json
    data/spc/_extrakce/davky/davka_NNNN.jsonl (+ .out.jsonl, .err.jsonl)
    data/spc/_extrakce/log/beh_<cas>.log      prubezny log (flush po radku)
    data/spc/_extrakce/report.md               souhrn + VSECHNY chyby podle ID

Pouziti:
  uv run python extrahuj_json_cloud.py --beh            # cely beh v popredi, naváže sam
  uv run python extrahuj_json_cloud.py --stav           # jen souhrn + report.md
  uv run python extrahuj_json_cloud.py --znovu-chybne   # chyby zpet do fronty
  uv run python extrahuj_json_cloud.py --znovu-seznam vadne.txt   # vybrane ID
  uv run python extrahuj_json_cloud.py --beh --test --limit-spc 5 --test-chyby

  # lokalne (Ollama) - maly rozsah
  uv run python extrahuj_json_cloud.py --local --kody 0260480            # jeden lek, vsechny sekce
  uv run python extrahuj_json_cloud.py --local --kody 0260480 --sekce indikace
  uv run python extrahuj_json_cloud.py --local --kody 0260480 --model gemma4:26b
  uv run python extrahuj_json_cloud.py --local --limit 20                # 20 cekajicich z fronty
  uv run python extrahuj_json_cloud.py --local --test --limit-spc 5 --model novy:model
                                # zkouska modelu - vystup do _extrakce_test, korpus beze zmeny
"""

import io
import sys
import json
import time
import sqlite3
import argparse
import logging
from pathlib import Path
from datetime import datetime

from common.config import (DATA_DIR, OPENAI_MODEL, OPENAI_CENA_VSTUP,
                           OPENAI_CENA_VYSTUP, OPENAI_BATCH_SLEVA,
                           CLOUD_STROP_USD, POMER_VYSTUP_VSTUP,
                           OPENAI_BATCH_LIMIT_FRONTY, OPENAI_BATCH_TOKENU_DAVKA)
from common.sekce import SEKCE_SPC, orizni_na_jadro
from common.extrakce import (uzivatelsky_prompt, telo_cloud, zpracuj_odpoved,
                             SYSTEM_PROMPT)

SPC_DIR = DATA_DIR / "spc"
KONCOVE = {"completed", "failed", "expired", "cancelled"}
MAX_POKUSU = 3          # pak uz jen rucne (--znovu-seznam), at se neplati donekonecna
log = logging.getLogger("extrakce_cloud")


# --------------------------------------------------------------------------
# prostredi behu
# --------------------------------------------------------------------------

class Beh:
    def __init__(self, test: bool):
        self.test = test
        self.prac = SPC_DIR / ("_extrakce_test" if test else "_extrakce")
        (self.prac / "davky").mkdir(parents=True, exist_ok=True)
        (self.prac / "log").mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.prac / "stav.sqlite", timeout=60)  # 30.9.: "database is locked" pri soubeznem cteni
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS pozadavky (
                id TEXT PRIMARY KEY, slozka TEXT, sekce TEXT, poradi INTEGER,
                stav TEXT, davka INTEGER, pokusu INTEGER DEFAULT 0,
                odhad_usd REAL, vstup_tok INTEGER, vystup_tok INTEGER,
                cena_usd REAL DEFAULT 0, polozek INTEGER, vysledek TEXT,
                chyba TEXT, zmeneno TEXT);
            CREATE TABLE IF NOT EXISTS davky (
                davka INTEGER PRIMARY KEY, batch_id TEXT, input_file_id TEXT,
                output_file_id TEXT, error_file_id TEXT, stav TEXT,
                pocet INTEGER, hotovo INTEGER, selhalo INTEGER,
                odhad_usd REAL, cena_usd REAL DEFAULT 0, chyba TEXT,
                vytvoreno TEXT, dokonceno TEXT);
        """)
        try:            # DB z doby pred merenim tokenu
            self.db.execute("ALTER TABLE davky ADD COLUMN tokenu INTEGER")
        except sqlite3.OperationalError:
            pass
        self.db.commit()
        # --test: vysledky NEJDOU do data/spc/<slozka>/json, ale vedle stavu,
        # at test nesahne na produkcni data.
        self.json_koren = self.prac / "json" if test else None
        self.odeslano_davek = 0
        self.pauza_do = 0.0      # po limitu fronty OpenAI neposilat do tohoto casu

    def json_dir(self, slozka: str) -> Path:
        return (self.json_koren / slozka if self.json_koren
                else SPC_DIR / slozka / "json")


_ZAMEK = None      # otevreny soubor zamku - drzi se po celou dobu behu


def zamkni(beh: Beh) -> bool:
    """Zamek proti soubeznemu behu. False = uz bezi jina instance.

    Zamyka operacni system (msvcrt na Windows, fcntl na Linuxu), ne existence
    souboru: kdyz proces spadne nebo ho nekdo zabije, OS zamek uvolni sam
    a dalsi spusteni (Planovac uloh / cron) naváže. Soubor s PID je jen
    informace pro cloveka.
    """
    global _ZAMEK
    f = open(beh.prac / "beh.lock", "a+")
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
        return False
    f.seek(0)
    f.truncate()
    f.write(f"pid {__import__('os').getpid()} od {ted()}\n")
    f.flush()
    _ZAMEK = f
    return True


def nastav_log(beh: Beh) -> Path:
    soubor = beh.prac / "log" / f"beh_{datetime.now():%Y%m%d_%H%M%S}.log"
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%Y-%m-%d %H:%M:%S")
    f = logging.FileHandler(soubor, encoding="utf-8")   # flush po kazdem zaznamu
    f.setFormatter(fmt)
    f.setLevel(logging.DEBUG)
    c = logging.StreamHandler(sys.stdout)
    c.setFormatter(fmt)
    c.setLevel(logging.INFO)
    log.setLevel(logging.DEBUG)
    log.handlers[:] = [f, c]
    return soubor


def ted() -> str:
    return datetime.now().isoformat(timespec="seconds")


def klient():
    from openai import OpenAI
    from common.config import nacti_openai_klic
    return OpenAI(api_key=nacti_openai_klic())


def cena(vstup: int, vystup: int) -> float:
    return (vstup * OPENAI_CENA_VSTUP + vystup * OPENAI_CENA_VYSTUP) / 1e6 * OPENAI_BATCH_SLEVA


# --------------------------------------------------------------------------
# 1) inventar pozadavku
# --------------------------------------------------------------------------

def slozky_korpusu() -> list[tuple[str, int]]:
    """(slozka, pocet kodu SUKL, ktere SPC pouzivaji). Poradi = priorita:
    nejdriv SPC pouzivana nejvic kody - pri rozpoctovem stropu se tak
    zpracuje to, co pokryje nejvic leciv."""
    import re
    c = sqlite3.connect(SPC_DIR / "_stav.sqlite")
    radky = c.execute("""SELECT identita, count(*) FROM kody
                         WHERE identita IS NOT NULL GROUP BY identita
                         ORDER BY count(*) DESC, identita""").fetchall()
    return [(re.sub(r"[^\w.-]+", "_", i)[:80], n) for i, n in radky]


def text_sekce(slozka: str, sekce: str) -> str | None:
    f = SPC_DIR / slozka / "sekce" / f"{sekce}.md"
    if not f.exists():
        return None
    t = f.read_text(encoding="utf-8")
    return t if len(t.strip()) >= 20 else None


def odhad_pozadavku(slozka: str, sekce: str) -> float | None:
    """Odhad ceny jednoho pozadavku (Batch) z aktualniho vstupu - tiktoken
    na presne to, co pujde do modelu, vystup pomerem z config."""
    t = text_sekce(slozka, sekce)
    if t is None:
        return None
    body = telo_cloud(uzivatelsky_prompt(sekce, orizni_na_jadro(t, sekce)), OPENAI_MODEL)
    vstup = tokeny(body)
    return cena(vstup, int(vstup * POMER_VYSTUP_VSTUP[sekce]))


def inventar(beh: Beh, limit_spc: int | None) -> None:
    import tiktoken
    enc = tiktoken.get_encoding("o200k_base")
    rezie = len(enc.encode(SYSTEM_PROMPT)) + 20
    slozky = slozky_korpusu()
    if limit_spc:
        slozky = slozky[:limit_spc]
    nove = 0
    if beh.db.execute("SELECT count(*) FROM pozadavky").fetchone()[0] < len(slozky):
        log.info("INVENTAR: pocitam tokeny sekci %d SPC kvuli rozpoctove pojistce "
                 "(poprve ~8 min, pak jen nove SPC)", len(slozky))
    for poradi, (slozka, _) in enumerate(slozky):
        if poradi and poradi % 1000 == 0 and nove:
            log.info("INVENTAR: %d / %d SPC", poradi, len(slozky))
        if not (SPC_DIR / slozka / "sekce").exists():
            continue
        for sekce in SEKCE_SPC:
            pid = f"{slozka}|{sekce}"
            if beh.db.execute("SELECT 1 FROM pozadavky WHERE id=?", (pid,)).fetchone():
                continue
            t = text_sekce(slozka, sekce)
            if t is None:
                beh.db.execute("INSERT INTO pozadavky (id,slozka,sekce,poradi,stav,zmeneno)"
                               " VALUES (?,?,?,?, 'bez_sekce', ?)",
                               (pid, slozka, sekce, poradi, ted()))
                zapis_stav(beh, slozka, sekce, {"stav": "chybi_v_dokumentu",
                                                "duvod": "sekce se v SPC nenašla"})
                continue
            vstup = rezie + len(enc.encode(uzivatelsky_prompt(sekce, orizni_na_jadro(t, sekce))))
            odhad = cena(vstup, int(vstup * POMER_VYSTUP_VSTUP[sekce]))
            beh.db.execute("INSERT INTO pozadavky (id,slozka,sekce,poradi,stav,odhad_usd,zmeneno)"
                           " VALUES (?,?,?,?, 'cekajici', ?, ?)",
                           (pid, slozka, sekce, poradi, odhad, ted()))
            nove += 1
    beh.db.commit()
    if nove:
        log.info("INVENTAR: %d novych pozadavku (%d SPC)", nove, len(slozky))


# --------------------------------------------------------------------------
# 2) odeslani davek
# --------------------------------------------------------------------------

def utraceno(beh: Beh) -> tuple[float, float]:
    """(skutecna utrata z usage, odhad rozjetych davek)."""
    skut = beh.db.execute("SELECT coalesce(sum(cena_usd),0) FROM pozadavky").fetchone()[0]
    rozj = beh.db.execute("SELECT coalesce(sum(odhad_usd),0) FROM pozadavky "
                          "WHERE stav='odeslano'").fetchone()[0]
    return skut, rozj


def otevrene_davky(beh: Beh) -> list[sqlite3.Row]:
    # Vcetne davek, ktere OpenAI uz dokoncil, ale runner je jeste nezpracoval
    # (pad mezi zapisem stavu 'completed' a zpracovanim vysledku) - jinak by
    # po restartu zustaly jejich pozadavky navzdy 'odeslano'.
    return beh.db.execute("SELECT * FROM davky WHERE batch_id IS NOT NULL "
                          "AND stav NOT IN ('zpracovana','chyba_odeslani')"
                          ).fetchall()


def lokalni_vada(body: dict) -> str | None:
    """Co by OpenAI odmitlo pri validaci davky - chytit DRIV, nez shodi celou davku."""
    zpravy = body.get("messages")
    if not zpravy:
        return "chybi messages (zadavaci prompt)"
    if not any(z.get("role") == "user" and (z.get("content") or "").strip() for z in zpravy):
        return "chybi uzivatelska zprava s textem sekce"
    if not body.get("model"):
        return "chybi model"
    return None


_ENC = None


def tokeny(body: dict) -> int:
    """Vstupni tokeny pozadavku (tiktoken) - pro limit fronty OpenAI."""
    global _ENC
    if _ENC is None:
        import tiktoken
        _ENC = tiktoken.get_encoding("o200k_base")
    return 20 + sum(len(_ENC.encode(z.get("content") or "")) for z in body.get("messages", []))


def tokeny_ve_fronte(beh: Beh) -> int:
    """Vstupni tokeny rozjetych davek. Davky z doby pred merenim tokenu
    (sloupec NULL) se odhadnou na 1 400 tokenu na pozadavek."""
    return sum((d["tokenu"] if d["tokenu"] is not None else d["pocet"] * 1400)
               for d in otevrene_davky(beh))


def odesli_davky(beh: Beh, api, *, velikost: int, max_otevrenych: int,
                 test_chyby: str | None, max_davek: int | None = None) -> bool:
    """Posle, kolik jde. Vraci False, kdyz se zastavilo na stropu / limitu davek.

    LIMIT FRONTY OpenAI (zmereno 29.9.2026 na ostrem behu): pro gpt-6-luna
    smi byt v rozjetych davkach organizace nejvys 2 000 000 VSTUPNICH tokenu
    ("Enqueued token limit reached ... Limit: 2,000,000"). Davka 1 000
    pozadavku ma ~1,3 M, takze z peti soubezne odeslanych prosla jedna
    a zbytek selhal pri validaci (zadarmo, ale zbytecne). Proto se davka
    plni podle TOKENU (config.OPENAI_BATCH_TOKENU_DAVKA) a posila se jen
    tehdy, kdyz se vejde do volneho mista ve fronte (OPENAI_BATCH_LIMIT_FRONTY).
    """
    while len(otevrene_davky(beh)) < max_otevrenych:
        if max_davek is not None and beh.odeslano_davek >= max_davek:
            log.info("LIMIT: odeslano %d davek (--max-davek), dalsi se v tomto behu neposilaji",
                     beh.odeslano_davek)
            return False
        if time.time() < beh.pauza_do:
            return True                # po limitu fronty chvili neposilat
        volne = OPENAI_BATCH_LIMIT_FRONTY - tokeny_ve_fronte(beh)
        max_tok = min(OPENAI_BATCH_TOKENU_DAVKA, volne)
        if max_tok < OPENAI_BATCH_TOKENU_DAVKA // 4:
            log.debug("fronta OpenAI plna (volno %d tok) - cekam na dokonceni davky", volne)
            return True
        radky = beh.db.execute("SELECT * FROM pozadavky WHERE stav='cekajici' "
                               "ORDER BY poradi, id LIMIT ?", (velikost,)).fetchall()
        if not radky:
            return True

        cislo = (beh.db.execute("SELECT coalesce(max(davka),0) FROM davky").fetchone()[0]) + 1
        soubor = beh.prac / "davky" / f"davka_{cislo:04d}.jsonl"
        chyba_souboru = test_chyby in ("obe", "soubor") and beh.odeslano_davek == 0  # TEST: davka bez souboru
        chyba_promptu = (test_chyby == "prompt" and beh.odeslano_davek == 0) or (test_chyby == "obe" and beh.odeslano_davek == 1)  # TEST: pozadavek bez promptu

        odeslane = []
        tok_celkem = 0
        with soubor.open("w", encoding="utf-8") as f:
            for i, r in enumerate(radky):
                pokus = r["pokusu"] + 1
                zdroj = text_sekce(r["slozka"], r["sekce"])
                t = orizni_na_jadro(zdroj, r["sekce"]) if zdroj else ""
                body = telo_cloud(uzivatelsky_prompt(r["sekce"], t), OPENAI_MODEL, pokus=pokus, sekce=r["sekce"])
                vada = "zdrojovy soubor sekce chybi" if not zdroj else lokalni_vada(body)
                if vada:
                    # Jeden vadny radek shodi validaci CELE davky (zmereno
                    # 29.9.: "missing_required_parameter" na radku 1 -> failed).
                    # Proto se vadny pozadavek do davky vubec nepusti.
                    beh.db.execute("UPDATE pozadavky SET stav='chyba', chyba=?, "
                                   "pokusu=pokusu+1, zmeneno=? WHERE id=?",
                                   (f"lokalni validace: {vada}", ted(), r["id"]))
                    log.error("  CHYBA %s: lokalni validace: %s", r["id"], vada)
                    continue
                tk = tokeny(body)
                if odeslane and tok_celkem + tk > max_tok:
                    break              # davka je plna podle tokenu, zbytek priste
                if chyba_promptu and i == 0:
                    body.pop("messages")       # TEST: chybi zadavaci prompt (az PO
                                               # lokalni validaci, at se overi reakce OpenAI)
                f.write(json.dumps({"custom_id": f"{r['id']}|p{pokus}", "method": "POST",
                                    "url": "/v1/chat/completions", "body": body},
                                   ensure_ascii=False) + "\n")
                odeslane.append(r)
                tok_celkem += tk
        radky = odeslane
        if not radky:
            beh.db.commit()
            continue

        odhad = sum(r["odhad_usd"] or 0 for r in radky)
        skut, rozj = utraceno(beh)
        if skut + rozj + odhad > CLOUD_STROP_USD:
            soubor.unlink(missing_ok=True)
            beh.db.commit()
            log.warning("ROZPOCET: utraceno %.3f $ + rozjete %.3f $ + davka %.3f $ "
                        "> strop %.2f $ (config.CLOUD_STROP_USD) - DALSI DAVKA SE "
                        "NEODESILA. Ceka %d pozadavku.", skut, rozj, odhad,
                        CLOUD_STROP_USD, pocet(beh, "cekajici"))
            return False

        beh.db.execute("INSERT INTO davky (davka,stav,pocet,odhad_usd,tokenu,vytvoreno) "
                       "VALUES (?, 'pripravena', ?, ?, ?, ?)",
                       (cislo, len(radky), odhad, tok_celkem, ted()))
        beh.db.commit()
        try:
            if chyba_souboru:
                input_id = "file-TEST-neexistuje"      # TEST: soubor se nenahral
                log.warning("TEST: davka %d se odesila s NEEXISTUJICIM souborem", cislo)
            else:
                with soubor.open("rb") as f:
                    input_id = api.files.create(file=f, purpose="batch").id
            b = api.batches.create(input_file_id=input_id,
                                   endpoint="/v1/chat/completions",
                                   completion_window="24h",
                                   metadata={"davka": str(cislo),
                                             "beh": "test" if beh.test else "korpus"})
        except Exception as e:
            beh.db.execute("UPDATE davky SET stav='chyba_odeslani', chyba=? WHERE davka=?",
                           (f"{type(e).__name__}: {e}"[:500], cislo))
            beh.db.commit()
            log.error("DAVKA %d NEODESLANA (%d pozadavku zustava 'cekajici'): %s: %s",
                      cislo, len(radky), type(e).__name__, str(e)[:300])
            return True                # nezkouset hned znovu - dalsi kolo smycky

        beh.db.execute("UPDATE davky SET stav=?, batch_id=?, input_file_id=? WHERE davka=?",
                       (b.status, b.id, input_id, cislo))
        beh.db.executemany("UPDATE pozadavky SET stav='odeslano', davka=?, "
                           "pokusu=pokusu+1, zmeneno=? WHERE id=?",
                           [(cislo, ted(), r["id"]) for r in radky])
        beh.db.commit()
        beh.odeslano_davek += 1
        log.info("DAVKA %d ODESLANA: %s, %d pozadavku, %d tok, odhad %.4f $ (%s); "
                 "ve fronte OpenAI ~%d / %d tok", cislo, b.id, len(radky), tok_celkem,
                 odhad, soubor.name, tokeny_ve_fronte(beh), OPENAI_BATCH_LIMIT_FRONTY)
    return True


# --------------------------------------------------------------------------
# 3) sledovani a zpracovani vysledku
# --------------------------------------------------------------------------

def zapis_stav(beh: Beh, slozka: str, sekce: str, zaznam: dict) -> None:
    d = beh.json_dir(slozka)
    d.mkdir(parents=True, exist_ok=True)
    f = d / "_stav.json"
    stav = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    stav[sekce] = zaznam
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(stav, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(f)                   # atomicky - pad nenecha rozepsany soubor


def zpracuj_radek(beh: Beh, davka: int, radek: dict) -> None:
    cid = radek.get("custom_id", "")
    pid, _, pokus = cid.rpartition("|")
    slozka, _, sekce = pid.partition("|")
    r = beh.db.execute("SELECT * FROM pozadavky WHERE id=?", (pid,)).fetchone()
    if r is None or r["davka"] != davka:
        log.warning("  %s: neznamy nebo stary pozadavek, preskakuji", cid)
        return

    resp = radek.get("response") or {}
    body = resp.get("body") or {}
    chyba = None
    if radek.get("error"):
        e = radek["error"]
        chyba = f"{e.get('code')}: {e.get('message')}"
    elif resp.get("status_code") != 200:
        e = body.get("error") or {}
        chyba = f"HTTP {resp.get('status_code')}: {e.get('message') or body}"[:500]

    u = body.get("usage") or {}
    vstup, vystup = u.get("prompt_tokens", 0), u.get("completion_tokens", 0)
    c = cena(vstup, vystup)

    if chyba:
        beh.db.execute("UPDATE pozadavky SET stav='chyba', chyba=?, cena_usd=cena_usd+?, "
                       "zmeneno=? WHERE id=?", (chyba, c, ted(), pid))
        log.error("  CHYBA %s: %s", cid, chyba[:200])
        return

    obsah = body["choices"][0]["message"]["content"] or ""
    v = zpracuj_odpoved(sekce, obsah, model=OPENAI_MODEL,
                        vstup_tok=vstup, vystup_tok=vystup)
    uloz_vysledek(beh, pid, v, model=OPENAI_MODEL, cena_usd=c, oznaceni=cid,
                  navic={"batch_id": davka_batch_id(beh, davka), "custom_id": cid})


def uloz_vysledek(beh: Beh, pid: str, v, *, model: str, cena_usd: float,
                  oznaceni: str, navic: dict | None = None) -> bool:
    """Zapise vysledek jedne sekce: json/<sekce>.json, _stav.json a stav
    pozadavku. Spolecne pro cloud i lokalni extrakci. Vraci True = hotovo."""
    slozka, _, sekce = pid.partition("|")
    d = beh.json_dir(slozka)
    d.mkdir(parents=True, exist_ok=True)
    if v.polozky:
        (d / f"{sekce}.json").write_text(
            json.dumps(v.polozky, ensure_ascii=False, indent=1), encoding="utf-8")
    zaznam = {"stav": v.stav, "duvod": v.duvod, "polozek": len(v.polozky),
              "model": model, **(navic or {}),
              "vstup_tok": v.vstup_tokenu, "vystup_tok": v.vystup_tokenu}
    if v.surova_odpoved:
        zaznam["surova_odpoved"] = v.surova_odpoved
    zapis_stav(beh, slozka, sekce, zaznam)

    # 'prazdna' JE vysledek, ne chyba: radiofarmaka pisou "Specificke
    # nezadouci ucinky nejsou znamy" a model spravne vrati [] (test 29.9.,
    # 3 z 3 prazdnych). Pri temperature 0 by opakovani dalo totez a stalo
    # penize. Chyba = jen 'selhala_extrakce' (nevalidni JSON, spatny tvar).
    ok = v.stav in ("neovereno", "castecna", "prazdna")
    beh.db.execute("UPDATE pozadavky SET stav=?, vysledek=?, polozek=?, vstup_tok=?, "
                   "vystup_tok=?, cena_usd=cena_usd+?, chyba=?, zmeneno=? WHERE id=?",
                   ("hotovo" if ok else "chyba", v.stav, len(v.polozky),
                    v.vstup_tokenu, v.vystup_tokenu, cena_usd,
                    None if ok else f"{v.stav}: {v.duvod}"[:500], ted(), pid))
    if ok:
        log.debug("  ok %s: %d polozek, %s", oznaceni, len(v.polozky), v.stav)
    else:
        log.error("  CHYBA %s: %s: %s", oznaceni, v.stav, v.duvod[:200])
    return ok


# --------------------------------------------------------------------------
# 3b) lokalni extrakce (Ollama) - maly rozsah, bez Batch API
# --------------------------------------------------------------------------

def slozky_kodu(kody: list[str]) -> dict[str, str]:
    """kod SUKL -> slozka SPC (inventar data/spc/_stav.sqlite)."""
    import re
    c = sqlite3.connect(SPC_DIR / "_stav.sqlite")
    ven = {}
    for k in kody:
        r = c.execute("SELECT identita FROM kody WHERE kod=? AND identita IS NOT NULL",
                      (k.strip(),)).fetchone()
        if r:
            ven[k.strip()] = re.sub(r"[^\w.-]+", "_", r[0])[:80]
    return ven


def beh_local(beh: Beh, *, model: str, kody: list[str] | None, sekce: list[str] | None,
              limit: int | None) -> int:
    """Lokalni extrakce pres Ollamu. Vraci navratovy kod.

    --kody: vyjmenovana SPC se extrahuji ZNOVU (i kdyz uz jsou hotova z cloudu).
    bez --kody: zpracuje, co CEKA ve fronte (typicky nova SPC, kdyz cloud
    neni dostupny) - nejvys `limit` pozadavku.
    """
    from common.extrakce import extrahuj_sekci
    from common.ollama_client import priprav_modely, get_ollama_url

    sekce = sekce or list(SEKCE_SPC)
    if kody:
        mapa = slozky_kodu(kody)
        nezname = [k for k in kody if k.strip() not in mapa]
        if nezname:
            log.error("CHYBA: kod SUKL neni v inventari (data/spc/_stav.sqlite): %s",
                      ", ".join(nezname))
            return 2
        ids = [f"{s}|{x}" for s in dict.fromkeys(mapa.values()) for x in sekce]
        znam = {r["id"]: r["stav"] for r in beh.db.execute(
            f"SELECT id, stav FROM pozadavky WHERE id IN ({','.join('?' * len(ids))})", ids)}
        chybi = [i for i in ids if i not in znam]
        if chybi:
            log.error("CHYBA: pozadavek neni v inventari extrakce (SPC nema vytazene "
                      "sekce? pust extrahuj_sekce.py): %s", ", ".join(chybi[:5]))
            return 2
        ids = [i for i in ids if znam[i] != "bez_sekce"]
    else:
        ids = [r["id"] for r in beh.db.execute(
            f"SELECT id FROM pozadavky WHERE stav='cekajici' AND sekce IN "
            f"({','.join('?' * len(sekce))}) ORDER BY poradi, id", sekce)]
        if limit:
            ids = ids[:limit]
    if not ids:
        log.info("LOCAL: neni co extrahovat (fronta je prazdna; konkretni lek: --kody KOD)")
        return 0

    # Model se overi a nahraje PREDEM a hlasite - jinak by kazda sekce
    # skoncila jako 'selhala_extrakce' a duvod by byl schovany v reportu.
    try:
        url = get_ollama_url()
        st = list(priprav_modely((model,)))[0]
    except Exception as e:
        log.error("CHYBA: Ollama neni dostupna: %s: %s", type(e).__name__, e)
        return 2
    if not st.ok:
        log.error("CHYBA: model %s na %s nejde nacist: %s", model, url, st.chyba)
        return 2
    log.info("LOCAL: model %s na %s, %d pozadavku%s", model, url, len(ids),
             " (TEST - vystup mimo korpus)" if beh.test else "")

    hotovo = chyb = 0
    t_start = time.perf_counter()
    try:
        for n, pid in enumerate(ids, 1):
            slozka, _, sek = pid.partition("|")
            text = text_sekce(slozka, sek)
            if text is None:
                log.warning("  %s: sekce na disku neni, preskakuji", pid)
                continue
            v = extrahuj_sekci(sek, text, model=model)
            ok = uloz_vysledek(beh, pid, v, model=model, cena_usd=0.0, oznaceni=pid,
                               navic={"zpusob": "local", "cas_s": round(v.cas_s, 1)})
            beh.db.commit()
            hotovo += ok
            chyb += not ok
            log.info("  %d/%d %s: %s, %d polozek, %.0f s", n, len(ids), pid, v.stav,
                     len(v.polozky), v.cas_s)
    except KeyboardInterrupt:
        log.warning("PRERUSENO (Ctrl+C). Hotove sekce jsou zapsane, zbytek zustal jak byl.")
    log.info("LOCAL hotovo %d, chyb %d, %.1f min", hotovo, chyb,
             (time.perf_counter() - t_start) / 60)
    return 1 if chyb else 0


def davka_batch_id(beh: Beh, davka: int) -> str:
    return beh.db.execute("SELECT batch_id FROM davky WHERE davka=?", (davka,)).fetchone()[0]


def stahni(api, file_id: str | None, cil: Path) -> list[dict]:
    if not file_id:
        return []
    text = api.files.content(file_id).text
    cil.write_text(text, encoding="utf-8")       # auditni kopie
    return [json.loads(x) for x in text.splitlines() if x.strip()]


def srovnej_s_openai(beh: Beh, api) -> None:
    """Davky, ktere u OpenAI EXISTUJI, ale v DB nemaji batch_id.

    Vznikne to padem presne mezi batches.create a zapisem do DB (stalo se
    29.9. pri testu). Bez srovnani by se pozadavky poslaly znovu a zaplatily
    dvakrat. Davka se pozna podle metadata.davka + beh, jeji pozadavky
    podle lokalniho davka_NNNN.jsonl (zapisuje se PRED odeslanim).
    """
    druh = "test" if beh.test else "korpus"
    for b in api.batches.list(limit=100):
        m = b.metadata or {}
        if m.get("beh") != druh or not str(m.get("davka", "")).isdigit():
            continue
        cislo = int(m["davka"])
        d = beh.db.execute("SELECT * FROM davky WHERE davka=?", (cislo,)).fetchone()
        if d is None or d["batch_id"]:
            continue
        if b.status in ("failed", "cancelled", "cancelling", "expired"):
            log.warning("SROVNANI: davka %d (%s) je u OpenAI %s a v DB bez zaznamu - "
                        "ignoruji", cislo, b.id, b.status)
            continue
        soubor = beh.prac / "davky" / f"davka_{cislo:04d}.jsonl"
        ids = [json.loads(x)["custom_id"].rpartition("|")[0]
               for x in soubor.read_text(encoding="utf-8").splitlines() if x.strip()]
        beh.db.execute("UPDATE davky SET batch_id=?, input_file_id=?, stav=? WHERE davka=?",
                       (b.id, b.input_file_id, b.status, cislo))
        beh.db.executemany("UPDATE pozadavky SET stav='odeslano', davka=?, pokusu=pokusu+1, "
                           "zmeneno=? WHERE id=? AND stav='cekajici'",
                           [(cislo, ted(), i) for i in ids])
        beh.db.commit()
        log.warning("SROVNANI: davka %d (%s, %s) prevzata z OpenAI - %d pozadavku "
                    "se NEPOSILA znovu", cislo, b.id, b.status, len(ids))


def sleduj(beh: Beh, api) -> None:
    for d in otevrene_davky(beh):
        try:
            b = api.batches.retrieve(d["batch_id"])
        except Exception as e:
            log.warning("DAVKA %d: stav nejde zjistit (%s), zkusim priste", d["davka"], e)
            continue
        rc = b.request_counts
        hotovo, selhalo = (rc.completed, rc.failed) if rc else (0, 0)
        if b.status != d["stav"] or hotovo != d["hotovo"] or selhalo != d["selhalo"]:
            log.info("DAVKA %d %s: %s, hotovo %d / selhalo %d / celkem %d",
                     d["davka"], b.id, b.status, hotovo, selhalo, d["pocet"])
        beh.db.execute("UPDATE davky SET stav=?, hotovo=?, selhalo=?, output_file_id=?, "
                       "error_file_id=? WHERE davka=?",
                       (b.status, hotovo, selhalo, b.output_file_id, b.error_file_id,
                        d["davka"]))
        beh.db.commit()
        if b.status in KONCOVE:
            dokonci_davku(beh, api, d["davka"], b)


def dokonci_davku(beh: Beh, api, cislo: int, b) -> None:
    zaklad = beh.prac / "davky" / f"davka_{cislo:04d}"
    radky = (stahni(api, b.output_file_id, zaklad.with_suffix(".out.jsonl"))
             + stahni(api, b.error_file_id, zaklad.with_suffix(".err.jsonl")))
    for r in radky:
        zpracuj_radek(beh, cislo, r)

    # Pozadavky, ktere v zadnem souboru nejsou (davka 'failed' pri validaci,
    # 'cancelled'). U prekroceneho limitu fronty se vraci do fronty BEZ
    # pripocteni pokusu - neni to chyba pozadavku.
    duvod = ""
    if b.status == "failed" and b.errors and b.errors.data:
        duvod = "; ".join(f"{e.code}: {e.message}" for e in b.errors.data[:5])
        # Validace hlasi CISLO RADKU vadneho pozadavku (od 1). Chyba patri jen
        # jemu - zdrave pozadavky te davky se vrati do fronty BEZ pripocteni
        # pokusu (zmereno 29.9.: jeden radek bez 'messages' shodil celou davku).
        cids = [json.loads(x)["custom_id"] for x in
                zaklad.with_suffix(".jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
        radkove = [e for e in b.errors.data if getattr(e, "line", None)]
        if radkove:
            for e in radkove:
                pid = cids[e.line - 1].rpartition("|")[0]
                beh.db.execute("UPDATE pozadavky SET stav='chyba', chyba=?, zmeneno=? "
                               "WHERE id=? AND davka=?",
                               (f"validace davky {cislo}, radek {e.line}: {e.code}: "
                                f"{e.message}"[:500], ted(), pid, cislo))
                log.error("  CHYBA %s: validace radek %d: %s: %s",
                          pid, e.line, e.code, e.message)
            n = beh.db.execute("UPDATE pozadavky SET stav='cekajici', pokusu=pokusu-1, "
                               "zmeneno=? WHERE davka=? AND stav='odeslano'",
                               (ted(), cislo)).rowcount
            log.warning("DAVKA %d: validace odmitla %d radku, %d zdravych pozadavku "
                        "zpet do fronty", cislo, len(radkove), n)
    zbyle = beh.db.execute("SELECT id FROM pozadavky WHERE davka=? AND stav='odeslano'",
                           (cislo,)).fetchall()
    limit = "limit" in duvod.lower()
    if zbyle:
        if limit:
            beh.db.execute("UPDATE pozadavky SET stav='cekajici', pokusu=pokusu-1, "
                           "zmeneno=? WHERE davka=? AND stav='odeslano'", (ted(), cislo))
            log.warning("DAVKA %d: limit fronty OpenAI (%s) - %d pozadavku zpet do fronty",
                        cislo, duvod[:200], len(zbyle))
            beh.pauza_do = time.time() + 300    # 5 min nic neposilat
            log.warning("LIMIT FRONTY: dalsi davky nejdriv za 5 min")
        else:
            beh.db.execute("UPDATE pozadavky SET stav='chyba', chyba=?, zmeneno=? "
                           "WHERE davka=? AND stav='odeslano'",
                           (f"davka {b.status}: {duvod or 'bez vysledku'}"[:500], ted(), cislo))
            log.error("DAVKA %d %s: %d pozadavku bez vysledku (%s)",
                      cislo, b.status, len(zbyle), duvod[:200] or "bez vysledku")

    c = beh.db.execute("SELECT coalesce(sum(cena_usd),0) FROM pozadavky WHERE davka=?",
                       (cislo,)).fetchone()[0]
    beh.db.execute("UPDATE davky SET stav='zpracovana', cena_usd=?, chyba=?, dokonceno=? "
                   "WHERE davka=?", (c, duvod or None, ted(), cislo))
    beh.db.commit()
    s = dict(beh.db.execute("SELECT stav, count(*) FROM pozadavky WHERE davka=? GROUP BY stav",
                            (cislo,)).fetchall())
    log.info("DAVKA %d ZPRACOVANA (%s): %s, cena %.4f $", cislo, b.status, s, c)


# --------------------------------------------------------------------------
# souhrn, report, opakovani
# --------------------------------------------------------------------------

def pocet(beh: Beh, stav: str) -> int:
    return beh.db.execute("SELECT count(*) FROM pozadavky WHERE stav=?", (stav,)).fetchone()[0]


def souhrn(beh: Beh) -> str:
    st = dict(beh.db.execute("SELECT stav, count(*) FROM pozadavky GROUP BY stav").fetchall())
    skut, rozj = utraceno(beh)
    zbyva = beh.db.execute("SELECT coalesce(sum(odhad_usd),0) FROM pozadavky "
                           "WHERE stav IN ('cekajici','chyba')").fetchone()[0]
    return (f"pozadavky: {st} | utraceno {skut:.4f} $, rozjete ~{rozj:.4f} $, "
            f"zbyva ~{zbyva:.3f} $, strop {CLOUD_STROP_USD:.2f} $")


def report(beh: Beh) -> Path:
    r = [f"# Extrakce v cloudu – stav k {ted()}\n",
         f"{'TESTOVACÍ BĚH' if beh.test else 'Korpus'}, model {OPENAI_MODEL}, Batch API.\n",
         f"**{souhrn(beh)}**\n", "## Dávky\n",
         "| # | batch_id | stav | počet | hotovo | selhalo | odhad $ | cena $ | chyba |",
         "|---|---|---|---|---|---|---|---|---|"]
    for d in beh.db.execute("SELECT * FROM davky ORDER BY davka"):
        r.append(f"| {d['davka']} | {d['batch_id'] or '–'} | {d['stav']} | {d['pocet']} "
                 f"| {d['hotovo'] or 0} | {d['selhalo'] or 0} | {d['odhad_usd'] or 0:.4f} "
                 f"| {d['cena_usd'] or 0:.4f} | {(d['chyba'] or '')[:120]} |")
    chyby = beh.db.execute("SELECT * FROM pozadavky WHERE stav='chyba' ORDER BY id").fetchall()
    r += ["", f"## Chybné požadavky ({len(chyby)})\n",
          "Znovu do fronty: `--znovu-chybne` (všechny) nebo `--znovu-seznam soubor`"
          " (ID po řádcích, sloupec `id`).\n",
          "| id | pokusů | dávka | chyba |", "|---|---|---|---|"]
    for c in chyby:
        r.append(f"| {c['id']} | {c['pokusu']} | {c['davka']} | {(c['chyba'] or '')[:160]} |")
    vys = beh.db.execute("SELECT vysledek, count(*) FROM pozadavky WHERE stav='hotovo' "
                         "GROUP BY vysledek").fetchall()
    r += ["", "## Výsledky hotových\n"] + [f"- `{v}`: {n}" for v, n in vys]
    f = beh.prac / "report.md"
    f.write_text("\n".join(r) + "\n", encoding="utf-8")
    return f


def do_fronty(beh: Beh, ids: list[str] | None) -> int:
    """Vrati pozadavky do fronty. ids=None -> vsechny chybne (do MAX_POKUSU)."""
    if ids is None:
        n = beh.db.execute("UPDATE pozadavky SET stav='cekajici', zmeneno=? "
                           "WHERE stav='chyba' AND pokusu < ?", (ted(), MAX_POKUSU)).rowcount
        vic = pocet(beh, "chyba")
        if vic:
            log.warning("%d chybnych uz ma %d pokusu - jen rucne pres --znovu-seznam",
                        vic, MAX_POKUSU)
    else:
        # Chybny = dalsi POKUS (vyssi teplota, pak schema). Hotovy vraceny
        # rucne = NOVA extrakce (zmena promptu/orezu, vadny po kontrole) ->
        # pokusy od nuly, tj. zase teplota 0 a seed. Odhad ceny se prepocita,
        # protoze vstup se mohl zmenit (30.9.: orez 4.2 vypnut).
        n = 0
        for i in ids:
            r = beh.db.execute("SELECT * FROM pozadavky WHERE id=?", (i,)).fetchone()
            if r is None or r["stav"] not in ("chyba", "hotovo"):
                continue
            nove = r["stav"] == "hotovo"
            beh.db.execute("UPDATE pozadavky SET stav='cekajici', zmeneno=?, "
                           "pokusu=CASE WHEN ? THEN 0 ELSE pokusu END, "
                           "odhad_usd=coalesce(?, odhad_usd) WHERE id=?",
                           (ted(), nove, odhad_pozadavku(r["slozka"], r["sekce"]), i))
            n += 1
    beh.db.commit()
    log.info("DO FRONTY vraceno %d pozadavku", n)
    return n


# --------------------------------------------------------------------------

def main() -> int:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--beh", action="store_true", help="inventar -> odeslani -> sledovani, v popredi")
    ap.add_argument("--local", action="store_true",
                    help="LOKALNE pres Ollamu misto Batch API - jeden lek / mala davka")
    ap.add_argument("--model", help="s --local: model v Ollame (vychozi config.MODEL_HLAVNI)")
    ap.add_argument("--kody", nargs="+", metavar="KOD",
                    help="s --local: kody SUKL, jejichz SPC se extrahuji ZNOVU")
    ap.add_argument("--sekce", nargs="+", choices=sorted(SEKCE_SPC),
                    help="s --local: jen tyto sekce (vychozi vsechny)")
    ap.add_argument("--limit", type=int,
                    help="s --local bez --kody: nejvys N cekajicich pozadavku z fronty")
    ap.add_argument("--stav", action="store_true", help="souhrn + report.md")
    ap.add_argument("--znovu-chybne", action="store_true")
    ap.add_argument("--znovu-seznam", type=Path, help="soubor s ID pozadavku po radcich")
    ap.add_argument("--velikost-davky", type=int, default=1000)
    ap.add_argument("--max-otevrenych", type=int, default=5)
    ap.add_argument("--interval", type=int, default=60, help="s mezi dotazy na stav")
    ap.add_argument("--test", action="store_true",
                    help="oddeleny stav i vystupy v data/spc/_extrakce_test")
    ap.add_argument("--limit-spc", type=int, help="jen prvnich N SPC podle priority")
    ap.add_argument("--max-davek", type=int,
                    help="v tomto behu odeslat nejvys N davek (pilot); rozjete se dosleduji")
    ap.add_argument("--test-chyby", choices=["soubor", "prompt", "obe"],
                    help="TEST: soubor = 1. davka bez souboru; prompt = v 1. davce pozadavek bez promptu; obe = obojí")
    a = ap.parse_args()
    if a.test_chyby and not a.test:
        ap.error("--test-chyby jen spolu s --test")
    if a.local and a.beh:
        ap.error("--local a --beh nejdou dohromady (lokalne NEBO cloud)")
    if (a.model or a.kody or a.sekce or a.limit) and not a.local:
        ap.error("--model, --kody, --sekce a --limit plati jen s --local")
    if a.test and (a.beh or a.local) and not a.limit_spc:
        # 29.9.: test bez limitu naplnil testovaci DB celym korpusem a zacal
        # posilat davky po 1000 pozadavcich.
        ap.error("--test s --beh / --local vyzaduje --limit-spc N")

    beh = Beh(a.test)
    if (a.beh or a.local or a.znovu_chybne or a.znovu_seznam) and not zamkni(beh):
        # Uz bezi jina instance (typicky z Planovace uloh kazdych 15 min).
        # Bez logu - jinak by kazde tiche ukonceni zalozilo novy soubor.
        print(f"{ted()} uz bezi jiny beh ({beh.prac / 'beh.lock'}), koncim")
        return 0
    soubor_logu = nastav_log(beh)
    log.info("START %s | log %s", " ".join(sys.argv[1:]), soubor_logu)

    if a.znovu_chybne:
        do_fronty(beh, None)
    if a.znovu_seznam:
        ids = [x.strip() for x in a.znovu_seznam.read_text(encoding="utf-8").splitlines()
               if x.strip() and not x.startswith("#")]
        do_fronty(beh, ids)

    kod_local = 0
    if a.local:
        from common.config import MODEL_HLAVNI
        inventar(beh, a.limit_spc)
        log.info("SOUHRN %s", souhrn(beh))
        kod_local = beh_local(beh, model=a.model or MODEL_HLAVNI, kody=a.kody,
                              sekce=a.sekce, limit=a.limit)

    if a.beh:
        # Klic se overuje HNED a hlasite: bez nej nebo s nefunkcnim klicem
        # nema beh smysl a nesmi skoncit, jako by se nic nestalo.
        from common.config import ChybaKlice, over_openai_klic
        try:
            api = klient()
            over_openai_klic(api)
        except ChybaKlice as e:
            log.error("CHYBA KLICE OPENAI: %s", e)
            log.error("Beh se NEspustil, nic se neodeslalo.")
            return 2
        srovnej_s_openai(beh, api)
        inventar(beh, a.limit_spc)
        log.info("SOUHRN %s", souhrn(beh))
        pod_stropem = True
        try:
            while True:
                if pod_stropem:
                    pod_stropem = odesli_davky(beh, api, velikost=a.velikost_davky,
                                               max_otevrenych=a.max_otevrenych,
                                               test_chyby=a.test_chyby,
                                               max_davek=a.max_davek)
                sleduj(beh, api)
                otevrene = otevrene_davky(beh)
                ceka = pocet(beh, "cekajici")
                if not otevrene and (ceka == 0 or not pod_stropem):
                    break
                log.debug("cekam %d s (otevrenych davek %d, ve fronte %d)",
                          a.interval, len(otevrene), ceka)
                time.sleep(a.interval)
        except KeyboardInterrupt:
            log.warning("PRERUSENO (Ctrl+C). Rozjete davky bezi u OpenAI dal - "
                        "stejny prikaz (--beh) na ne navaze.")
        a.test_chyby = False

    f = report(beh)
    log.info("SOUHRN %s", souhrn(beh))
    log.info("REPORT %s", f)
    if pocet(beh, "chyba"):
        log.warning("%d chybnych pozadavku - seznam v reportu, znovu: --znovu-chybne",
                    pocet(beh, "chyba"))
    return kod_local or (1 if pocet(beh, "chyba") else 0)


if __name__ == "__main__":
    raise SystemExit(main())
