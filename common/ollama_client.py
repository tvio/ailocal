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
import threading
import time
from dataclasses import dataclass, field

import requests

from common.config import (OLLAMA_TIMEOUT, OLLAMA_UZLY, OLLAMA_SOUBEZNE,
                           MODEL_EXTRAKCE, MODEL_EMBED)

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

# ---------------------------------------------------------------------------
# Vic stroju s Ollamou: dostupnost a rozdelovani zateze (7. 10. 2026)
# ---------------------------------------------------------------------------
# Hledani pousti vic lidi najednou a router je uzke hrdlo. Zmereno na DGX
# Sparku: Ollama vyrizuje dotazy na router PO JEDNOM (2 soubezne = 3,0 s,
# 4 = 6,1 s, 8 = 11,6 s; propustnost porad ~0,66 dotazu/s). Osmy uzivatel
# tedy ceka 12 s, prestoze jeho dotaz trva 1,5 s. Druhy stroj frontu puli.
#
# JAK SE VYBIRA STROJ (vyber_uzel):
#   1. jen stroje, ktere jsou DOSTUPNE a model na nich nechybi;
#   2. prednost ma stroj, ktery ma VOLNO (rozpracovano < soubezne) - a mezi
#      volnymi ten s modelem v pameti, pak ten drive v seznamu (PRIORITA:
#      prvni je Spark, druhy stroj se pouzije, az kdyz ma Spark praci);
#   3. kdyz maji praci vsechny, bere se ten s nejkratsi frontou.
#
# VYTIZENI: Ollama zadny udaj o fronte ani zatizeni nevraci (/api/ps rika
# jen, ktere modely jsou v pameti). Pocitame si proto sami, kolik pozadavku
# na kterem stroji prave bezi. Je to vytizeni OD TETO APLIKACE - o praci,
# kterou na stroj posila nekdo jiny (extrakce, jiny proces API), nevime;
# pozna se jen podle delsi odezvy (stav_uzlu() -> odezva_s).
#
# DOSTUPNOST hlida vlakno na pozadi (kazdych INTERVAL_KONTROLY sekund,
# /api/version + /api/ps). Pozadavek tak nikdy neceka na nedostupny stroj
# a stroj, ktery nabehne pozdeji, se zapoji sam. Kdyz pozadavek selze na
# spojeni, stroj se hned oznaci jako nedostupny a pozadavek se zopakuje na
# dalsim. Hlidac taky udrzuje registrovane modely v pameti na VSECH
# dostupnych strojich - Ollama je jinak po keep_alive odlozi.
INTERVAL_KONTROLY = 15.0     # s mezi kontrolami dostupnosti
CAS_KONTROLY = 2.0           # s timeout jedne kontroly
CAS_SPOJENI = 3.0            # s na navazani spojeni u pozadavku (ne na odpoved)
MODEL_CHYBI_S = 300.0        # po 404 "model nenalezen" stroj pro ten model vynechat


@dataclass
class Uzel:
    """Jeden stroj s Ollamou a to, co o nem aplikace vi."""
    nazev: str
    url: str
    soubezne: int = 1                 # kolik pozadavku naraz, nez se sahne jinam
    dostupny: bool | None = None      # None = jeste nezkouseno
    chyba: str | None = None
    bezi: int = 0                     # rozpracovane pozadavky z teto aplikace
    vyrizeno: int = 0
    selhalo: int = 0
    odezva_s: float | None = None     # klouzavy prumer doby odpovedi
    teple: set = field(default_factory=set)       # modely v pameti (/api/ps)
    chybi: dict = field(default_factory=dict)     # model -> do kdy ho nezkouset
    nahrava: bool = False             # hlidac prave nahrava model

    def ma_v_pameti(self, model: str) -> bool:
        zaklad = model.split(":")[0]
        return model in self.teple or any(m.split(":")[0] == zaklad for m in self.teple)


_UZLY: list[Uzel] = [Uzel(n, u.rstrip("/"), OLLAMA_SOUBEZNE) for n, u in OLLAMA_UZLY]
# Zpetna kompatibilita: seznam adres v poradi priority.
KANDIDATI = [u.url for u in _UZLY]

_zamek = threading.Lock()
_hlidac: threading.Thread | None = None
_registrovane: list[str] = []       # modely, ktere ma hlidac drzet v pameti


def _zkontroluj(u: Uzel) -> None:
    """Dostupnost stroje a modely v pameti. Meni stav uzlu, nic nevraci."""
    try:
        r = requests.get(f"{u.url}/api/version", timeout=CAS_KONTROLY)
        r.raise_for_status()
        ps = requests.get(f"{u.url}/api/ps", timeout=CAS_KONTROLY)
        teple = ({m["name"] for m in ps.json().get("models", [])} if ps.ok else set())
        dostupny, chyba = True, None
    except requests.RequestException as e:
        dostupny, chyba, teple = False, type(e).__name__, set()
    with _zamek:
        if u.dostupny is not dostupny:
            logger.info("Ollama %s (%s): %s", u.nazev, u.url,
                        "DOSTUPNA" if dostupny else f"nedostupna ({chyba})")
        u.dostupny, u.chyba, u.teple = dostupny, chyba, teple


def _zkontroluj_vse() -> None:
    """Vsechny stroje soubezne - nedostupny nesmi zdrzet kontrolu ostatnich."""
    vlakna = [threading.Thread(target=_zkontroluj, args=(u,), daemon=True) for u in _UZLY]
    for v in vlakna:
        v.start()
    for v in vlakna:
        v.join(CAS_KONTROLY * 2 + 1)


def _zahrej(u: Uzel) -> None:
    """Nahraje registrovane modely na jeden stroj (ve vlastnim vlakne)."""
    try:
        for model in list(_registrovane):
            if u.ma_v_pameti(model) or time.time() < u.chybi.get(model, 0):
                continue
            try:
                trvalo = nahrej(model, u.url)
                logger.info("Ollama %s: model %s nahran za %.1f s", u.nazev, model, trvalo)
                with _zamek:
                    u.teple.add(model)
            except requests.HTTPError as e:
                if e.response is not None and e.response.status_code == 404:
                    u.chybi[model] = time.time() + MODEL_CHYBI_S
                    logger.warning("Ollama %s: model %s na stroji NENI (ollama pull)",
                                   u.nazev, model)
            except requests.RequestException as e:
                logger.debug("Ollama %s: nahrani %s selhalo: %s", u.nazev, model, e)
    finally:
        u.nahrava = False


def _dohrej_modely() -> None:
    """Na kazdem dostupnem stroji spusti nahrani registrovanych modelu, ktere chybi."""
    for u in _UZLY:
        if u.dostupny and not u.nahrava and any(not u.ma_v_pameti(m) for m in _registrovane):
            u.nahrava = True
            threading.Thread(target=_zahrej, args=(u,), daemon=True).start()


def _smycka_hlidace() -> None:
    while True:
        time.sleep(INTERVAL_KONTROLY)
        try:
            _zkontroluj_vse()
            _dohrej_modely()
        except Exception:                       # hlidac nesmi umrit
            logger.exception("hlidac Ollamy selhal, pokracuje")


_start_zamek = threading.Lock()      # jen pro prvni kontrolu (ne _zamek - ten bere _zkontroluj)
_zkontrolovano = threading.Event()   # prvni kontrola stroju dobehla


def _zajisti_hlidace() -> None:
    """Prvni volani zkontroluje stroje hned (nejvys par sekund), dal uz
    stav udrzuje vlakno na pozadi. Soubezna volani pri startu POCKAJI, az
    prvni kontrola dobehne - jinak by videla stroje jako "nezkouseno"
    a hlasila, ze zadna Ollama neni dostupna."""
    global _hlidac
    if _zkontrolovano.is_set():
        return
    with _start_zamek:
        if _zkontrolovano.is_set():
            return
        _zkontroluj_vse()
        _hlidac = threading.Thread(target=_smycka_hlidace, daemon=True, name="ollama-hlidac")
        _hlidac.start()
        _zkontrolovano.set()


def vyber_uzel(model: str | None = None, vynechat: set | None = None) -> Uzel:
    """Stroj pro dalsi pozadavek - viz pravidla nahore. ConnectionError,
    kdyz neni dostupny zadny."""
    _zajisti_hlidace()
    ted = time.time()
    with _zamek:
        kand = [u for u in _UZLY if u.dostupny and u.nazev not in (vynechat or ())
                and not (model and ted < u.chybi.get(model, 0))]
        if not kand:
            raise ConnectionError(
                "Žádná Ollama není dostupná"
                + (f" s modelem {model}" if model else "") + ". Stroje: "
                + ", ".join(f"{u.nazev} {u.url} "
                            f"({u.chyba or ('model chybí' if u.dostupny else 'nezkoušeno')})"
                            for u in _UZLY))
        volne = [u for u in kand if u.bezi < u.soubezne]
        if volne:
            # mezi volnymi: model v pameti ma prednost, pak poradi v seznamu
            return min(volne, key=lambda u: (bool(model) and not u.ma_v_pameti(model),
                                             _UZLY.index(u)))
        return min(kand, key=lambda u: (u.bezi / max(u.soubezne, 1), _UZLY.index(u)))


def _posli(cesta: str, payload: dict, *, model: str, timeout: float,
           base_url: str | None = None) -> dict:
    """POST na Ollamu. Bez base_url vybere stroj a pri selhani zkusi dalsi."""
    if base_url:
        r = requests.post(f"{base_url}{cesta}", json=payload, timeout=(CAS_SPOJENI, timeout))
        r.raise_for_status()
        return r.json()

    vynechat: set[str] = set()
    posledni: Exception | None = None
    for _ in range(len(_UZLY)):
        try:
            u = vyber_uzel(model, vynechat)
        except ConnectionError:
            if posledni is not None:
                raise posledni
            raise
        with _zamek:
            u.bezi += 1
        t0 = time.perf_counter()
        try:
            r = requests.post(f"{u.url}{cesta}", json=payload, timeout=(CAS_SPOJENI, timeout))
            r.raise_for_status()
            trvalo = time.perf_counter() - t0
            with _zamek:
                u.vyrizeno += 1
                u.odezva_s = trvalo if u.odezva_s is None else 0.8 * u.odezva_s + 0.2 * trvalo
            return r.json()
        except requests.ReadTimeout as e:
            # Stroj zije, jen to nestihl v limitu: pro tenhle pozadavek zkusit jiny.
            logger.warning("Ollama %s neodpovedela do %s s, zkousim dalsi stroj",
                           u.nazev, timeout)
            posledni = e
        except (requests.ConnectionError, requests.ConnectTimeout) as e:
            # Stroj neodpovida - oznacit hned; hlidac ho zase zapoji, az nabehne.
            with _zamek:
                u.dostupny, u.chyba = False, type(e).__name__
            logger.warning("Ollama %s neodpovida (%s), zkousim dalsi stroj",
                           u.nazev, type(e).__name__)
            posledni = e
        except requests.HTTPError as e:
            kod = e.response.status_code if e.response is not None else 0
            if kod == 404:
                # Ollama bezi, ale model na stroji neni - chvili ho tam nezkouset.
                u.chybi[model] = time.time() + MODEL_CHYBI_S
                logger.warning("Ollama %s: model %s nenalezen (404), zkousim dalsi stroj",
                               u.nazev, model)
            elif kod >= 500:
                logger.warning("Ollama %s: HTTP %s, zkousim dalsi stroj", u.nazev, kod)
            else:
                with _zamek:
                    u.selhalo += 1
                raise                           # chyba pozadavku, jinde by dopadla stejne
            posledni = e
        finally:
            with _zamek:
                u.bezi -= 1
        with _zamek:
            u.selhalo += 1
        vynechat.add(u.nazev)
    assert posledni is not None
    raise posledni


def stav_uzlu() -> list[dict]:
    """Stav vsech stroju pro /api/stav a ladeni."""
    _zajisti_hlidace()
    with _zamek:
        return [{"nazev": u.nazev, "url": u.url, "dostupny": bool(u.dostupny),
                 "chyba": u.chyba, "bezi": u.bezi, "soubezne": u.soubezne,
                 "vyrizeno": u.vyrizeno, "selhalo": u.selhalo,
                 "odezva_s": None if u.odezva_s is None else round(u.odezva_s, 2),
                 "modely_v_pameti": sorted(u.teple)} for u in _UZLY]


def get_ollama_url(*, znovu: bool = False) -> str:
    """URL dostupne Ollamy s nejvyssi prioritou (pro kod, ktery chce jednu
    adresu: predehrati, vypis). Pozadavky chat/embed si stroj vybiraji samy."""
    _zajisti_hlidace()
    if znovu:
        _zkontroluj_vse()
    for u in _UZLY:
        if u.dostupny:
            return u.url
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
    """Jako chat(), ale vrací i rozpad času (viz Metriky).

    Bez `base_url` si stroj vybere rozdelovani zateze (vyber_uzel) a pri
    vypadku zkusi dalsi; s `base_url` jde pozadavek presne tam."""
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

    data = _posli("/api/chat", payload, model=model,
                  timeout=timeout or OLLAMA_TIMEOUT, base_url=base_url)

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


def embed(texty: list[str], *, model: str = MODEL_EMBED, base_url: str | None = None,
          timeout: float | None = None) -> list[list[float]]:
    """Embedding dávky textů.

    Pozor: /api/embed funguje jen u modelů, které mají capability 'embedding'
    (v manifestu klíč pooling_type). Generativní model, byť sebevětší,
    embedding neumí a vrátí 501.
    """
    data = _posli("/api/embed", {"model": model, "input": texty, "keep_alive": KEEP_ALIVE},
                  model=model, timeout=timeout or OLLAMA_TIMEOUT, base_url=base_url)
    return data["embeddings"]


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

    Vice stroju: tady se ceka jen na stroj s nejvyssi prioritou. Modely se
    zaroven ZAREGISTRUJI a hlidac na pozadi je nahraje a drzi v pameti i na
    ostatnich dostupnych strojich (a na tech, ktere nabehnou pozdeji).
    """
    _zajisti_hlidace()
    for m in modely:
        if m not in _registrovane:
            _registrovane.append(m)
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
    _zkontroluj_vse()          # at je hned videt, co je kde v pameti
    _dohrej_modely()           # ostatni stroje na pozadi
    return vysledky
