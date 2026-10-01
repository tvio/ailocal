"""Aktuální seznam léčiv z VEŘEJNÉHO API SÚKL (/dlp/v1) – první krok pipeline.

Proč samostatně: seznam z 24. 8. zastaral o jedno vydání a 5 kódů mezitím
zaniklo (poznatky.md 25. 9.). Každý běh pipeline proto začíná tady.

Postup:
  1. /aktualni-davky            -> vydání DLPO (datumVydani, platnostOd, verze)
  2. stejné vydání jako minule  -> nic nestahovat
  3. /lecive-pripravky?typSeznamu=dlpo  -> VŠECHNY kódy (~69 800)
     /lecive-pripravky?typSeznamu=scau  -> hrazené kódy (~8 600)
  4. /lecive-pripravky/{kod}     -> detail každého kódu (stav registrace,
     obchodovanost, ATC, registrační číslo…); 16 souběžně ≈ 5 min

POZOR – dvě API se NESMÍ míchat:
  /dlp/v1        veřejné, pro integraci, MĚSÍČNÍ vydání (dlpo/scau) – TOHLE
  /prehledy/v1   API webu (GUI), TÝDENNÍ přírůstky – na seznam léčiv ne
Data z jednoho vydání a týdenního stavu webu by si odporovala.

`uvedeneCeny` seznam NEZUŽUJE (true i false = 69 759 kódů, 25. 9.) –
obchodovanost je jen v detailu (`jeDodavka`), proto se stahují všechny.

Výstup (formát jako dřívější postav_pool, navíc `hrazeno`):
  data/pool_leciv.json        seznam léčiv (výběr polí + hrazeno)
  data/pool_leciv.meta.json   vydání, ze kterého seznam je
  data/detaily_leciv/<kod>.json  PLNÝ detail kódů v rozsahu (obchodované +
                              platný stav) – pro naplni_db (api_json, obal…)
  data/hrazene_scau.json      kódy hrazených (scau) – pro naplni_db
  data/ciselnik_latky.json    číselník léčivých látek – pro naplni_db

Atributy pro aplikaci: výdej Rx/OTC = zpusobVydejeKod (detail),
hrazeno = kód v seznamu scau, stav registrace, obchodovanost = jeDodavka.
"""

import json
import time
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import requests

from common.config import SUKL_API, DATA_DIR

logger = logging.getLogger(__name__)

# Stavy registrace, se kterými pracujeme (číselník /ciselniky/stavy-registrace).
# NE jen R – první verze brala jen R a vypadlo ~370 obchodovaných kódů (B, F, I).
#   R registrovaný, B po změně (6 měs. na trhu), C zrušená – stahuje se z oběhu,
#   F specifický léčebný program, I mimořádné opatření MZ, K/M pozastavení,
#   Y pozbyla platnost – stahuje se z oběhu.
# Mimo: G J N U Z ZI ZS (ukončené/zrušené) a P = potravina pro zvláštní
# lékařské účely (není léčivo; 460 obchodovaných kódů v září 2026).
PLATNE_STAVY = {"R", "B", "C", "F", "I", "K", "M", "Y"}

POOL = DATA_DIR / "pool_leciv.json"
META = DATA_DIR / "pool_leciv.meta.json"
# Plný JSON detailu kódů v rozsahu (obchodované + platný stav) – naplni_db.py
# z něj bere obalKod, indikacniSkupinaKod a celý api_json. Pool drží jen výběr.
DETAILY = DATA_DIR / "detaily_leciv"
# Cache hrazených pro naplni_db.nacti_hrazene() – obnovuje se se seznamem,
# jinak zůstala z 24. 8. (hrazenost = kód je v seznamu scau, ne atribut detailu).
HRAZENE = DATA_DIR / "hrazene_scau.json"
# Číselník léčivých látek (kód -> název) pro naplni_db.nacti_latky() – bez
# obnovy by nová látka byla v DB jen jako číslo (cache byla z 20. 8.).
LATKY = DATA_DIR / "ciselnik_latky.json"
VLAKEN = 16


def aktualni_vydani(s: requests.Session | None = None) -> dict:
    """Vydání DLPO z /aktualni-davky: {"typ","datumVydani","platnostOd","verze"}."""
    s = s or requests.Session()
    r = s.get(f"{SUKL_API}/aktualni-davky", timeout=60)
    r.raise_for_status()
    return next(d for d in r.json() if d.get("typ") == "DLPO")


def _klic(v: dict) -> str:
    return f"{v.get('platnostOd')} v{v.get('verze')}"


def _seznam(s: requests.Session, typ: str) -> list[str]:
    r = s.get(f"{SUKL_API}/lecive-pripravky",
              params={"typSeznamu": typ, "uvedeneCeny": "true"}, timeout=180)
    r.raise_for_status()
    return r.json()


def _detail(s: requests.Session, kod: str) -> dict | None:
    for pokus in range(4):
        try:
            r = s.get(f"{SUKL_API}/lecive-pripravky/{kod}", timeout=30)
        except requests.RequestException:
            time.sleep(2 * (pokus + 1))
            continue
        if r.status_code == 404:
            return None                      # kód v seznamu, detail už ne
        if r.status_code in (429, 502, 503, 504):
            time.sleep(5 * (pokus + 1))
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f"detail {kod} se nepodařilo stáhnout")


def obnov_seznam(*, vynutit: bool = False) -> tuple[list[dict], dict, bool]:
    """Vrátí (seznam léčiv, vydání, bylo_obnoveno).

    Když je uložený seznam ze stejného vydání, vrátí ho bez stahování.
    Zapisuje atomicky – přerušené stahování nepřepíše platný seznam.
    """
    s = requests.Session()
    s.mount("https://", requests.adapters.HTTPAdapter(pool_maxsize=VLAKEN * 2))
    vydani = aktualni_vydani(s)
    ulozene = json.loads(META.read_text(encoding="utf-8")) if META.exists() else {}
    if not vynutit and POOL.exists() and _klic(ulozene.get("vydani", {})) == _klic(vydani):
        logger.info("SEZNAM LÉČIV: aktuální (vydání DLPO platné od %s, verze %s)",
                    vydani.get("platnostOd"), vydani.get("verze"))
        return json.loads(POOL.read_text(encoding="utf-8")), vydani, False

    logger.info("SEZNAM LÉČIV: nové vydání DLPO %s (uloženo: %s) – stahuji",
                _klic(vydani), _klic(ulozene.get("vydani", {})) or "nic")
    t0 = time.time()
    kody = _seznam(s, "dlpo")
    hrazene = set(_seznam(s, "scau"))
    logger.info("  kódů %d, z toho hrazených %d; stahuji detaily (%d souběžně)…",
                len(kody), len(hrazene), VLAKEN)

    DETAILY.mkdir(parents=True, exist_ok=True)
    seznam, chybi, ulozeno = [], 0, 0
    with ThreadPoolExecutor(VLAKEN) as ex:
        for i, (kod, d) in enumerate(zip(kody, ex.map(lambda k: _detail(s, k), kody)), 1):
            if d is None:
                chybi += 1
            else:
                reg = d.get("registracniCislo") or ""
                seznam.append({
                    "kod_sukl": kod,
                    "nazev": d.get("nazev", ""),
                    "sila": d.get("sila", ""),
                    "doplnek": d.get("doplnek", ""),
                    "atc": d.get("ATCkod", ""),
                    "forma": d.get("lekovaFormaKod", ""),
                    "baleni": d.get("baleni", ""),
                    "cesta": d.get("cestaKod", ""),
                    "zpusob_vydeje": d.get("zpusobVydejeKod", ""),
                    "registracni_cislo": reg,
                    "eu_registrace": reg.startswith("EU"),
                    "lecive_latky": d.get("leciveLatky", []),
                    "je_dodavka": d.get("jeDodavka", False),
                    "stav_registrace": d.get("stavRegistraceKod", ""),
                    "soubezny_dovoz": d.get("registracniCisloSoubDov") or "",
                    "hrazeno": kod in hrazene,
                })
                if d.get("jeDodavka") and d.get("stavRegistraceKod") in PLATNE_STAVY:
                    (DETAILY / f"{kod}.json").write_text(
                        json.dumps(d, ensure_ascii=False), encoding="utf-8")
                    ulozeno += 1
            if i % 10000 == 0:
                logger.info("  detaily %d/%d (%.0f s)", i, len(kody), time.time() - t0)

    HRAZENE.write_text(json.dumps(sorted(hrazene), ensure_ascii=False), encoding="utf-8")
    r = s.get(f"{SUKL_API}/ciselnik-latky", timeout=180)
    r.raise_for_status()
    LATKY.write_text(json.dumps({str(x["kod"]): str(x.get("nazev") or x["kod"])
                                 for x in r.json()}, ensure_ascii=False, indent=1),
                     encoding="utf-8")
    tmp = POOL.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(seznam, ensure_ascii=False), encoding="utf-8")
    tmp.replace(POOL)
    META.write_text(json.dumps({
        "vydani": vydani, "stazeno": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "kodu_v_seznamu": len(kody), "detailu": len(seznam), "bez_detailu": chybi,
        "plnych_detailu_ulozeno": ulozeno,
        "hrazenych": len(hrazene)}, ensure_ascii=False, indent=1), encoding="utf-8")
    obch = sum(1 for r in seznam if r["je_dodavka"] and r["stav_registrace"] in PLATNE_STAVY)
    logger.info("SEZNAM LÉČIV HOTOV za %.0f s: %d léčiv (bez detailu %d), "
                "platných a obchodovaných %d", time.time() - t0, len(seznam), chybi, obch)
    return seznam, vydani, True
