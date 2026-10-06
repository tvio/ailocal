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
