"""Tenký wrapper nad Ollama REST API.

Poznatky z legacy fáze, které jsou tu zapracované:
- num_ctx se NENASTAVUJE natvrdo. Server má vlastní OLLAMA_CONTEXT_LENGTH
  (systemd override) a klient by ho přebíjel. Nastavuje se jen tam, kde je
  potřeba se od serverového nastavení záměrně odchýlit.
- U hybridních reasoning modelů (Qwen3) je potřeba vypnout "thinking",
  jinak model generuje skryté tokeny a i triviální ANO/NE dotaz trvá
  násobně déle. API parametr je u některých variant nespolehlivý, proto
  se navíc přidává "/nothink" do system promptu.
"""

import json
import logging
from dataclasses import dataclass

import requests

from common.config import OLLAMA_TIMEOUT, MODEL_EXTRAKCE, MODEL_EMBED

# Jak dlouho ma model zustat v pameti po posledním pouziti.
#
# PROC TO RESIT: Ollama model po 5 minutach necinnosti ODLOZI. Dalsi dotaz
# ho pak musi nacist znovu - a qwen3.5:122b ma 87,4 GB. Projevi se to tak,
# ze `ollama ps` neukazuje nic a skript "strasne dlouho nic nedela",
# prestoze je v poradku. S nactenym modelem trva cely dotaz ~5 s.
#
# Hodnota se posila u KAZDEHO pozadavku, takze nevyzaduje zasah do
# konfigurace serveru (OLLAMA_KEEP_ALIVE).
KEEP_ALIVE = "2h"

logger = logging.getLogger(__name__)

# Pořadí, ve kterém se hledá běžící Ollama. První odpovídající vyhrává.
KANDIDATI = [
    "http://10.6.38.10:11434",
    "http://127.0.0.1:11434",
]

_url_cache: str | None = None


def get_ollama_url(*, znovu: bool = False) -> str:
    """Vrátí URL dostupné Ollamy. Volá se líně až při požadavku,
    aby šly moduly importovat i když Ollama neběží."""
    global _url_cache
    if _url_cache and not znovu:
        return _url_cache
    for url in KANDIDATI:
        try:
            r = requests.get(f"{url}/api/version", timeout=5)
            if r.ok:
                _url_cache = url
                return url
        except requests.RequestException:
            continue
    raise ConnectionError(
        "Žádná Ollama není dostupná. Zkoušeno: " + ", ".join(KANDIDATI)
    )


def dostupne_modely(base_url: str | None = None) -> list[dict]:
    url = base_url or get_ollama_url()
    r = requests.get(f"{url}/api/tags", timeout=15)
    r.raise_for_status()
    return r.json().get("models", [])


@dataclass
class Metriky:
    """Rozpad času z odpovědi Ollamy. Klíčové pro rozhodování o výkonu:
    prompt_eval = načtení vstupu, eval = generování výstupu. U dlouhých
    strukturovaných výstupů drtivě převažuje eval, takže zkracování vstupu
    (ani zmenšení num_ctx) s časem nic neudělá – řídí ho počet VÝSTUPNÍCH tokenů.
    """
    vstup_tokenu: int = 0
    vystup_tokenu: int = 0
    cas_vstup_s: float = 0.0
    cas_vystup_s: float = 0.0
    cas_celkem_s: float = 0.0
    cas_nacteni_s: float = 0.0   # načtení vah do paměti; u 70B+ modelů minuty

    @property
    def tok_za_s(self) -> float:
        return self.vystup_tokenu / self.cas_vystup_s if self.cas_vystup_s else 0.0

    @property
    def nacital_se(self) -> bool:
        """Musel se model nacist z disku? U 87GB modelu to je desitky sekund."""
        return self.cas_nacteni_s > 1.0

    def __str__(self) -> str:
        return (
            f"vstup {self.vstup_tokenu} tok / {self.cas_vstup_s:.1f} s, "
            f"výstup {self.vystup_tokenu} tok / {self.cas_vystup_s:.1f} s "
            f"({self.tok_za_s:.1f} tok/s), načtení {self.cas_nacteni_s:.1f} s, "
            f"celkem {self.cas_celkem_s:.1f} s"
        )


def chat_detail(
    prompt: str,
    *,
    system: str = "",
    model: str = MODEL_EXTRAKCE,
    base_url: str | None = None,
    json_mode: bool = False,
    think: bool | None = False,
    options: dict | None = None,
    timeout: int | None = None,
) -> tuple[str, Metriky]:
    """Jako chat(), ale vrací i rozpad času (viz Metriky)."""
    url = base_url or get_ollama_url()

    if think is False and system:
        system = f"/nothink {system}"

    zpravy = []
    if system:
        zpravy.append({"role": "system", "content": system})
    zpravy.append({"role": "user", "content": prompt})

    payload: dict = {"model": model, "messages": zpravy, "stream": False,
                     "keep_alive": KEEP_ALIVE}
    if options:
        payload["options"] = options
    if json_mode:
        payload["format"] = "json"
    if think is not None:
        payload["think"] = think

    r = requests.post(
        f"{url}/api/chat",
        json=payload,
        timeout=timeout or OLLAMA_TIMEOUT,
    )
    r.raise_for_status()
    data = r.json()

    ns = 1_000_000_000
    m = Metriky(
        vstup_tokenu=data.get("prompt_eval_count", 0),
        vystup_tokenu=data.get("eval_count", 0),
        cas_vstup_s=data.get("prompt_eval_duration", 0) / ns,
        cas_vystup_s=data.get("eval_duration", 0) / ns,
        cas_celkem_s=data.get("total_duration", 0) / ns,
        cas_nacteni_s=data.get("load_duration", 0) / ns,
    )
    return data["message"]["content"], m


def chat(prompt: str, **kw) -> str:
    """Pošle prompt a vrátí odpověď jako text.

    json_mode=True zapne Ollama JSON mode – model pak musí vrátit validní JSON.
    think=False vypíná reasoning tokeny (výchozí, viz docstring modulu).
    """
    return chat_detail(prompt, **kw)[0]


def chat_json(prompt: str, **kw) -> dict | list:
    """Jako chat(), ale rovnou rozparsuje JSON odpověď."""
    odpoved = chat(prompt, json_mode=True, **kw)
    return json.loads(odpoved)


def embed(texty: list[str], *, model: str = MODEL_EMBED, base_url: str | None = None) -> list[list[float]]:
    """Embedding dávky textů.

    Pozor: /api/embed funguje jen u modelů, které mají capability 'embedding'
    (v manifestu klíč pooling_type). Generativní model, byť sebevětší,
    embedding neumí a vrátí 501.
    """
    url = base_url or get_ollama_url()
    r = requests.post(
        f"{url}/api/embed",
        json={"model": model, "input": texty, "keep_alive": KEEP_ALIVE},
        timeout=OLLAMA_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()["embeddings"]


# --- Nacteni modelu do pameti ----------------------------------------------
# Ollama model po ~5 minutach necinnosti odlozi. Prvni dotaz po pauze pak
# ceka na nacteni 87 GB z disku a CLI vypada zaseknute. Tyhle funkce
# umoznuji stav ZJISTIT predem a model nahrat rizene, s hlaskou.
#
# Pro GUI plati totez, ale jinak: model se ma nahrat pri STARTU aplikace
# (nebo pri otevreni stranky), ne az pri prvnim dotazu uzivatele. Jinak
# prvni navstevnik zaplati tu minutu za vsechny.


def nactene_modely(base_url: str | None = None) -> dict[str, float]:
    """Modely prave v pameti -> velikost v GB."""
    url = base_url or get_ollama_url()
    try:
        r = requests.get(f"{url}/api/ps", timeout=10)
        r.raise_for_status()
        return {m["name"]: m.get("size", 0) / 1e9 for m in r.json().get("models", [])}
    except requests.RequestException as e:
        logger.debug("nelze zjistit nactene modely: %s", e)
        return {}


def je_nacteny(model: str, base_url: str | None = None) -> bool:
    """Je model v pameti? Porovnava i bez znacky ':latest'."""
    nactene = nactene_modely(base_url)
    if model in nactene:
        return True
    zaklad = model.split(":")[0]
    return any(n.split(":")[0] == zaklad for n in nactene)


def nahrej(model: str, base_url: str | None = None,
           timeout: int | None = None) -> float:
    """Nahraje model do pameti a vrati, jak dlouho to trvalo (v sekundach).

    Kdyz uz nacteny je, vrati 0 a nic nedela.
    """
    import time

    if je_nacteny(model, base_url):
        return 0.0

    url = base_url or get_ollama_url()
    t0 = time.perf_counter()

    # POZOR: embedovaci model NEUMI /api/generate a vrati 400 Bad Request.
    # Musi se nahrat pres /api/embed. Pozna se to podle toho, ze nema
    # capability 'completion' - jednodussi je zkusit generate a pri 400
    # spadnout na embed.
    try:
        r = requests.post(
            f"{url}/api/generate",
            json={"model": model, "keep_alive": KEEP_ALIVE},
            timeout=timeout or OLLAMA_TIMEOUT,
        )
        r.raise_for_status()
    except requests.HTTPError as e:
        if e.response is None or e.response.status_code != 400:
            raise
        r = requests.post(
            f"{url}/api/embed",
            json={"model": model, "input": "", "keep_alive": KEEP_ALIVE},
            timeout=timeout or OLLAMA_TIMEOUT,
        )
        r.raise_for_status()
    return time.perf_counter() - t0


@dataclass
class StavModelu:
    """Vysledek predehrati jednoho modelu."""
    model: str
    nacital_se: bool          # byl na disku a musel se nahrat?
    trvalo_s: float           # 0.0 kdyz uz byl v pameti
    chyba: str | None = None

    @property
    def ok(self) -> bool:
        return self.chyba is None


def priprav_modely(modely, *, hlas=None) -> list[StavModelu]:
    """Overi, ze jsou modely v pameti, a pripadne je nahraje.

    Bez tehle kontroly aplikace po delsi pauze "stoji" - Ollama model po
    ~5 minutach necinnosti odlozi a prvni dotaz ceka na nacteni 87 GB
    z disku, pricemz `ollama ps` mezitim neukazuje nic.

    `hlas` je volitelna funkce pro prubezne hlaseni (u CLI `print`).
    Pro GUI se necha prazdna a vykresli se az navracene `StavModelu` -
    volat se to ma pri STARTU aplikace, ne az u prvniho dotazu uzivatele,
    jinak prvni navstevnik ceka minutu.

    Chyba jednoho modelu nezastavi ostatni: kdyz se nepodari nahrat
    embedovaci model, generativni ma porad smysl nahrat.
    """
    vysledky: list[StavModelu] = []
    for model in modely:
        if je_nacteny(model):
            vysledky.append(StavModelu(model, False, 0.0))
            continue
        if hlas:
            hlas(f"Model {model} není v paměti, načítám z disku "
                 f"(u velkého modelu to je desítky sekund)...")
        try:
            trvalo = nahrej(model)
        except Exception as e:
            chyba = f"{type(e).__name__}: {e}"
            if hlas:
                hlas(f"  nepodařilo se načíst {model}: {chyba}")
            vysledky.append(StavModelu(model, True, 0.0, chyba))
            continue
        if hlas:
            hlas(f"  {model} načten za {trvalo:.1f} s")
        vysledky.append(StavModelu(model, True, trvalo))
    return vysledky
