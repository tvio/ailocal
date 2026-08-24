"""Klient pro SÚKL API.

Na serveru jsou DVĚ různá API:

A) /dlp/v1      – veřejné, dokumentované (OpenAPI na /dlp.api.json), stabilní.
                  Seznam kódů, detail léku, číselníky, PDF. Vyhledávat NEUMÍ.
B) /prehledy/v1 – nedokumentované, používá ho web prehled_leciv.html.
                  Umí vyhledávat podle názvu i ATC. Vhodné na discovery.

!!! KLÍČOVÉ: bez správných parametrů vrací jen ZRUŠENÉ registrace !!!

Dva parametry se musí poslat vždy, jinak jsou výsledky nepoužitelné:

    stavZruseni    'N' = jen platné registrace   <- tohle chceme
                   'Z' = jen zrušené
                   'V' nebo '' = všechno dohromady
    ochrannyPrvek  'X' = NEROZHODUJE (ne "nesmí mít ochranné prvky"!)
                   'A' = musí mít OP  (v praxi jen Rx)
                   'N' = nesmí mít OP (v praxi jen OTC)
                   ''  = nevrátí nic

Ověřeno 13.8.2026: 'X' je neutrální hodnota, kterou je nutné poslat
explicitně – vynechání parametru není totéž jako "nefiltrovat".
Kombinace stavZruseni='N' + ochrannyPrvek='X' vrací aktuální registr
(PARALEN: 27 záznamů, všechny stav 'R', všechny dohledatelné přes /dlp/v1).

Dělba práce: discovery (které kódy chci) přes B, vlastní data přes A.
Důvod: B není veřejný kontrakt a může se změnit bez ohlášení.
"""

import json
import time
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import requests

from common.config import SUKL_API, SUKL_SEARCH_API

logger = logging.getLogger(__name__)


class SuklClient:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "localsemantic/0.1"})

    # -----------------------------------------------------------------
    # Discovery – vyhledávací API
    # -----------------------------------------------------------------

    def hledej(
        self,
        *,
        filtr: str | None = None,
        atc: str | None = None,
        pocet: int = 50,
        stranka: int = 1,
        stav_zruseni: str = "N",
        ochranny_prvek: str = "X",
    ) -> dict:
        """Vyhledá léčiva podle názvu (prefix) nebo ATC (i prefix).

        Výchozí hodnoty stav_zruseni='N' a ochranny_prvek='X' vrací
        AKTUÁLNÍ registr. Nesahat na ně, pokud nechceš historii –
        podrobnosti v docstringu modulu.

        Vrací {"celkem": int, "data": [...]}. Záznamy mají už rozložené
        číselníkové hodnoty – např. zpusobVydeje obsahuje kodDlw 'OTC'/'Rx'.
        """
        body: dict = {
            "pocet": pocet,
            "stranka": stranka,
            "sort": ["nazev", "je_dodavka"],
            "smer": "asc",
            "stavZruseni": stav_zruseni,
            "ochrannyPrvek": ochranny_prvek,
        }
        if filtr:
            body["filtr"] = filtr
        if atc:
            body["atc"] = atc

        resp = self.session.post(
            f"{SUKL_SEARCH_API}/dlp",
            json=body,
            headers={"If-Modified-Since": "0"},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()

    def hledej_vse_dle_atc(self, atc: str, *, max_zaznamu: int = 500) -> list[dict]:
        """Postránkově stáhne záznamy dané ATC skupiny (jen platné registrace)."""
        vysledky: list[dict] = []
        stranka = 1
        while len(vysledky) < max_zaznamu:
            data = self.hledej(atc=atc, pocet=100, stranka=stranka)
            davka = data.get("data") or []
            if not davka:
                break
            vysledky.extend(davka)
            if len(vysledky) >= data.get("celkem", 0):
                break
            stranka += 1
        return vysledky[:max_zaznamu]

    # -----------------------------------------------------------------
    # Data – veřejné dokumentované API
    # -----------------------------------------------------------------

    def detail_leciva(self, kod_sukl: str) -> dict:
        """Detail léčivého přípravku podle kódu SÚKL."""
        resp = self.session.get(f"{SUKL_API}/lecive-pripravky/{kod_sukl}", timeout=30)
        resp.raise_for_status()
        return resp.json()

    def ciselnik(self, nazev: str) -> list[dict]:
        """Číselník podle názvu (zpusoby-vydeje, atc-skupiny, lekove-formy...)."""
        resp = self.session.get(f"{SUKL_API}/ciselniky/{nazev}", timeout=30)
        resp.raise_for_status()
        return resp.json()

    def ciselnik_latky(self) -> list[dict]:
        """Číselník léčivých látek (kód -> název)."""
        resp = self.session.get(f"{SUKL_API}/ciselnik-latky", timeout=60)
        resp.raise_for_status()
        return resp.json()

    def seznam_kodu(self, typ_seznamu: str = "dlpo") -> list[str]:
        """Seznam kódů SÚKL. 'dlpo' = otevřená databáze, 'scau' = hrazené."""
        resp = self.session.get(
            f"{SUKL_API}/lecive-pripravky",
            params={"typSeznamu": typ_seznamu, "uvedeneCeny": "false"},
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()

    def stahni_spc(self, kod_sukl: str, *, max_pokusu: int = 3) -> bytes:
        """Stáhne SPC PDF. Vrátí prázdné bytes, pokud PDF není k dispozici.

        Pozor: server občas odpoví HTML (redirect na EMA) místo PDF, proto
        se kontroluje magic číslo %PDF, ne jen HTTP status.
        """
        url = f"{SUKL_API}/dokumenty/{kod_sukl}/spc"
        for pokus in range(max_pokusu):
            try:
                resp = self.session.get(url, timeout=90)
                resp.raise_for_status()
                if not resp.content[:5].startswith(b"%PDF"):
                    logger.warning(
                        "  %s: odpověď není PDF (content-type: %s)",
                        kod_sukl,
                        resp.headers.get("content-type", "?"),
                    )
                    return b""
                return resp.content
            except requests.exceptions.HTTPError as e:
                if e.response is not None and e.response.status_code == 429:
                    cekej = (2 ** pokus) * 5
                    logger.warning("  429 Too Many Requests – čekám %ss", cekej)
                    time.sleep(cekej)
                    continue
                raise
            except requests.RequestException:
                if pokus < max_pokusu - 1:
                    time.sleep(2)
                    continue
                return b""
        return b""


def postav_pool(
    client: "SuklClient",
    *,
    cache: Path | None = None,
    vlaken: int = 10,
    limit: int | None = None,
) -> list[dict]:
    """Stáhne detaily všech léčiv ze seznamu dlpo a vrátí je jako lokální pool.

    Tohle je jediná spolehlivá cesta k discovery – seznam vrací pouze kódy
    (69 355 ks) a ATC je až v detailu, takže filtrovat podle ATC jde jen
    stažením detailů. Vyhledávací API tady nepomůže (obsahuje jen zrušené
    registrace, viz docstring modulu).

    Trvá jednotky až desítky minut, proto se výsledek cachuje na disk.
    Stáhnout jednou, vybírat opakovaně – při změně ATC whitelistu už není
    potřeba znovu chodit na API.
    """
    if cache and cache.exists():
        logger.info("Pool načten z cache: %s", cache)
        return json.loads(cache.read_text(encoding="utf-8"))

    kody = client.seznam_kodu("dlpo")
    if limit:
        kody = kody[:limit]
    logger.info("Stahuji detaily %d léčiv (%d vláken)...", len(kody), vlaken)

    def nacti(kod: str) -> dict | None:
        try:
            d = client.detail_leciva(kod)
        except Exception:
            return None
        return {
            "kod_sukl": kod,
            "nazev": d.get("nazev", ""),
            "sila": d.get("sila", ""),
            "doplnek": d.get("doplnek", ""),
            "atc": d.get("ATCkod", ""),
            "forma": d.get("lekovaFormaKod", ""),
            "baleni": d.get("baleni", ""),
            "cesta": d.get("cestaKod", ""),
            "zpusob_vydeje": d.get("zpusobVydejeKod", ""),
            "registracni_cislo": d.get("registracniCislo", ""),
            "eu_registrace": (d.get("registracniCislo") or "").startswith("EU"),
            "lecive_latky": d.get("leciveLatky", []),
            "je_dodavka": d.get("jeDodavka", False),
            "stav_registrace": d.get("stavRegistraceKod", ""),
        }

    pool: list[dict] = []
    with ThreadPoolExecutor(max_workers=vlaken) as ex:
        for i, rec in enumerate(ex.map(nacti, kody), 1):
            if rec:
                pool.append(rec)
            if i % 5000 == 0:
                logger.info("  ... %d/%d", i, len(kody))

    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(pool, ensure_ascii=False), encoding="utf-8")
        logger.info("Pool uložen do cache: %s (%d léčiv)", cache, len(pool))
    return pool


def vyber_dle_atc(
    pool: list[dict],
    whitelist: dict[str, int],
    *,
    jen_dodavane: bool = True,
) -> list[dict]:
    """Z poolu vybere léčiva podle ATC whitelistu s limitem na skupinu.

    Limit na skupinu je nutný – C09/A10B/C10A jsou v registru tak časté,
    že by bez stropu zabraly většinu vzorku a demo by bylo o tlaku
    a cukrovce místo o bolesti a alergii.

    Z jednoho názvu se bere jen jedna varianta balení, jinak by vzorek
    tvořilo deset velikostí toho samého přípravku.
    """
    vybrane: list[dict] = []
    for atc, limit in whitelist.items():
        kandidati = [r for r in pool if (r.get("atc") or "").startswith(atc)]
        if jen_dodavane:
            kandidati = [r for r in kandidati if r.get("je_dodavka")] or kandidati

        videne: set[str] = set()
        skupina: list[dict] = []
        for r in kandidati:
            nazev = (r.get("nazev") or "").strip().upper()
            if not nazev or nazev in videne:
                continue
            videne.add(nazev)
            skupina.append(r)
            if len(skupina) >= limit:
                break
        logger.info("  %-6s %2d/%-2d léčiv (kandidátů %d)", atc, len(skupina), limit, len(kandidati))
        vybrane.extend(skupina)
    return vybrane


def je_na_predpis(zpusob_vydeje_kod: str) -> bool | None:
    """Rx/OTC podle kódu způsobu výdeje.

    POZOR na 'NEUVEDENO': vypadá jako chybějící hodnota, ale znamená
    "výdej na lékařský předpis s modrým pruhem", tedy omamné a psychotropní
    látky. Musí být v Rx skupině, jinak by se opiáty označily za volně prodejné.

    Neznámý kód vrací None (ne False) – ať je vidět, že se objevilo něco nového,
    místo tiché chyby.
    """
    RX = {"R", "L", "C", "NEUVEDENO"}
    OTC = {"F", "O", "P", "V"}
    if zpusob_vydeje_kod in RX:
        return True
    if zpusob_vydeje_kod in OTC:
        return False
    logger.warning("Neznámý kód způsobu výdeje: %r", zpusob_vydeje_kod)
    return None
