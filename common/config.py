"""Společná konfigurace – jediný zdroj pravdy pro cesty, modely a DB."""

from pathlib import Path

# --- Datové adresáře ---
DATA_DIR = Path("data")
LECIVA_DIR = DATA_DIR / "leciva"          # per-lék podadresář: <kod>_<NAZEV>


def adresar_leciva(kod_sukl: str, nazev: str | None = None) -> Path:
    """Cesta k adresáři léčiva ve tvaru data/leciva/0254048_PARALEN.

    Název je v cestě záměrně – samotný kód SÚKL si nikdo nepamatuje
    a při procházení dat by se muselo pokaždé otevírat api.json.
    Když se adresář s daným kódem už na disku najde, vrátí se ten
    existující (ať se nevytvoří duplicita při jiném tvaru názvu).
    """
    if LECIVA_DIR.exists():
        for p in LECIVA_DIR.iterdir():
            if p.is_dir() and p.name.split("_")[0] == kod_sukl:
                return p
    if not nazev:
        return LECIVA_DIR / kod_sukl
    return LECIVA_DIR / f"{kod_sukl}_{_bezpecny_nazev(nazev)}"


def _bezpecny_nazev(nazev: str) -> str:
    """Název léku do podoby použitelné v cestě (bez diakritiky a mezer)."""
    import re
    import unicodedata

    bez_diakritiky = "".join(
        z for z in unicodedata.normalize("NFKD", nazev) if not unicodedata.combining(z)
    )
    ocisteny = re.sub(r"[^A-Za-z0-9]+", "_", bez_diakritiky).strip("_").upper()
    return ocisteny[:40] or "BEZ_NAZVU"

# --- SÚKL API ---
# A) veřejné dokumentované API – stabilní kontrakt, detail léku + PDF
SUKL_API = "https://prehledy.sukl.gov.cz/dlp/v1"
# B) nedokumentované API webové aplikace – JEDINÉ, které umí vyhledávat
#    (podle názvu i ATC). Používat pouze na discovery, viz zadani.md.
SUKL_SEARCH_API = "https://prehledy.sukl.gov.cz/prehledy/v1"

# --- Ollama ---
# Extrakce dlouhé sekce 4.8 na 72B modelu překročila 600 s a spadla na timeout,
# takže se tvářila jako selhaná extrakce. Limit je záměrně velkorysý – lepší
# počkat než dostat falešné 'selhala_extrakce'.
OLLAMA_TIMEOUT = 2400

# qwen3.5:122b je MoE – aktivuje se jen zlomek parametrů, takže je zároveň
# NEJLEPŠÍ i NEJRYCHLEJŠÍ z lokálních modelů (~29 tok/s proti 10,5 u 32B
# a 4,5 u 72B). Měření a srovnání kvality viz poznatky.md 18.8.2026.
# Počet parametrů tu neříká nic o rychlosti – u MoE se nesmí odhadovat.
MODEL_HLAVNI = "qwen3.5:122b"        # extrakce a zjednodušení (lokálně)
MODEL_EMBED = "bge-m3"               # embedding NEDĚLÁ generativní model!
                                     # /api/embed vyžaduje capability 'embedding'
                                     # (pooling_type v manifestu), jinak vrátí 501.
                                     # 1024 dim nativně -> vejde se do HNSW indexu.

# Menší modely zůstávají pro srovnání v benchmarku, v pipeline se nepoužívají.
MODEL_EXTRAKCE = MODEL_HLAVNI
MODEL_LAIK = MODEL_HLAVNI
# gemma4:26b je MoE (128 expertu, aktivnich 8). Jako router zmereno
# 24.9.2026 (bench_router.py, poznatky.md): median 1,51 s proti 4,56 s
# u qwen3.5:122b, 103 tok/s proti 30, spravne 24/26 proti 21/26,
# evaluate.py shodne. Router je 92 % casu dotazu, takze tohle je primo
# to, co uzivatel ceka.
MODEL_ROUTER = "gemma4:26b"
# Kontrola MUSI byt JINY model nez ten, ktery extrahoval - model si
# neodsouhlasi vlastni chybu. gemma4:26b je jina rodina nez qwen i nez
# cloudova luna, takze pravidlo plati dal. Nahradila gemma4:31b (dense),
# ktera byla v kazde uloze 2,6-3x pomalejsi nez qwen (10 tok/s).
# Samotna kontrola se na 26b NEMERILA - rozhodnuto 24.9.2026 podle
# routeru a zjednoduseni. Puvodni overeni na 31b: nasla skutecnou chybu
# ("akutni alergicke stavy" ve zdroji proti "tezke alergicke reakce"),
# 1 nalez z 65 polozek.
MODEL_KONTROLY = "gemma4:26b"

# Který model dělá kterou sekci. Dělit úlohy mezi modely se ukázalo jako
# zbytečné – 122b vyhrává na struktuře i na češtině. Mechanismus tu zůstává,
# kdyby bylo potřeba se od toho někde odchýlit.
MODEL_SEKCE = {
    "indikace": MODEL_HLAVNI,
    "kontraindikace": MODEL_HLAVNI,
    "davkovani": MODEL_HLAVNI,
    "nezadouci_ucinky": MODEL_HLAVNI,
}

# --- OpenAI: JEDINÁ cloudová volba pro extrakci ---
# POZOR NA PENÍZE: na účtu je jen pár dolarů. gpt-6-luna jako jediná ze
# tří změřených skutečně překládá latinu do laické češtiny (qwen
# i gpt-5-nano ji opisují), a přitom je levná: 0,10 / 0,50 $ za 1M.
# Celý korpus 6 618 SPC (zjednodušení + klíče) přes Batch API ~2,7 $.
# Viz poznatky.md 23.9.2026. gpt-4o, gpt-4o-mini ani řadu sol nepouštět.
OPENAI_MODEL = "gpt-6-luna"
# Reasoning se účtuje jako výstup a rozhoduje o ceně víc než volba modelu:
# luna s výchozím reasoningem 0,0113 $, s "none" 0,0030 $ na týž vzorek,
# kvalita skoro stejná. POVINNĚ "none" - luna na "minimal" vrací 400
# (u gpt-5-nano je to naopak, tam je vypínač "minimal").
OPENAI_REASONING_EFFORT = "none"

# Cena gpt-6-luna v $ za 1M tokenu (overeno 23.9.2026) a sleva Batch API.
OPENAI_CENA_VSTUP = 0.10
OPENAI_CENA_VYSTUP = 0.50
OPENAI_BATCH_SLEVA = 0.5
# ROZPOCTOVA POJISTKA pro extrahuj_json_cloud.py: skutecna utrata (z usage)
# + odhad rozjetych davek + odhad nove davky nesmi strop prekrocit - jinak
# se dalsi davka NEODESLE. Na uctu 10 $ (29.9.2026, platform.openai.com),
# odhad celeho korpusu 5,5 $, pesimisticky 6,4 $ (poznatky 29.9.). Strop
# nechava rezervu na opakovani a nepresnost odhadu vystupu.
CLOUD_STROP_USD = 11.5  # 2.10.: +preextrahovani indikaci promptem v2 (~0,7-0,9 $)
# LIMIT FRONTY Batch API: pro gpt-6-luna smi byt v rozjetych davkach
# organizace nejvys 2 000 000 vstupnich tokenu (zmereno 29.9.2026 na ostrem
# behu: "Enqueued token limit reached ... Limit: 2,000,000"). Nad limitem
# davka selze pri validaci. Nechava se rezerva na nepresnost tiktokenu.
OPENAI_BATCH_LIMIT_FRONTY = 1_800_000
# Max. vstupnich tokenu v jedne davce - dve davky se vejdou do fronty
# soucasne, takze zatimco jedna konci, druha uz bezi.
OPENAI_BATCH_TOKENU_DAVKA = 850_000
# Odhad pomeru vystup/vstup pro pojistku (namereno 29.9. na 3 SPC, luna).
POMER_VYSTUP_VSTUP = {"indikace": 0.31, "davkovani": 0.39,
                      "kontraindikace": 0.25, "nezadouci_ucinky": 0.96}

EMBED_DIMENSION = 1024

# --- Kontroly extrakce: DOČASNĚ VYPNUTÉ (29.9.2026) ---
# Rozhodnuto kvůli času: nový korpus jde nejdřív přes cloud (luna, Batch
# API) BEZ kontrol. Kontroly se zapracují až nad novým korpusem – popis
# všech kontrol a proč jsou vypnuté: extrakce_kontroly.md.
# Vypíná: klic_ma_oporu() v extrakci, kroky 4a/4b v pipeline.py
# a kontrolu slovníku modelem (nerealizovane_kontroly/postav_slovnik.py --zkontroluj).
# Data pak mají stav 'neovereno' – to je PRAVDA, ne chyba.
KONTROLY_ZAPNUTE = False

# --- Docling Serve na DGX Spark (CUDA) ---
# Přes SSH tunel na localhost. 13× rychlejší než lokální Docling, výstup
# totožný (poznatky.md 24.9.2026). Používá konvertuj_serve.py.
DOCLING_SERVE_URL = "http://localhost:5001"

# --- PostgreSQL ---
PG_HOST = "localhost"
PG_PORT = 5432
PG_USER = "localsemantic"
PG_PASSWORD = "localsemantic"
PG_DATABASE = "localsemantic"

PG_DSN = f"postgresql://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DATABASE}"

# --- Sekce SPC ---
# Hodnoty sloupce leciva_search.sekce. 'atributy' není z PDF – skládá se
# z relační tabulky a slouží k hledání léku podle jména/síly/kódu.
SEKCE_Z_PDF = ["indikace", "kontraindikace", "nezadouci_ucinky", "davkovani"]
SEKCE_ATRIBUTY = "atributy"

# --- Číselník frekvence nežádoucích účinků (EU SmPC / MedDRA) ---
FREKVENCE_RANK = {
    "velmi caste": 1,
    "caste": 2,
    "mene caste": 3,
    "vzacne": 4,
    "velmi vzacne": 5,
    "neni znamo": 9,
}
FREKVENCE_RANK_NEZNAMA = 9

# --- Číselník skupin pacientů (u indikací) ---
# Stejný princip jako u stavů extrakce: chybějící hodnota neřekne, jestli
# zdroj skupinu nerozlišuje, nebo jestli ji model přehlédl. Proto se
# 'neuvedeno' zapisuje EXPLICITNĚ a nikdy se nenechává prázdné.
#
# Většina indikací skupinu nerozlišuje – týká se to hlavně léků, které mají
# jiné indikace pro dospělé a pro děti (OMEPRAZOL: refluxní ezofagitida
# u dětí od 1 roku, duodenální vředy u dětí od 4 let).
SKUPINA_NEUVEDENO = "neuvedeno"
SKUPINA_TEXT_NEUVEDENO = "není uvedeno"

# Kód -> jak se to ukáže uživateli. Kód je filtr, text je popisek.
SKUPINY_PACIENTU = {
    "neuvedeno": "není uvedeno",
    "dospeli": "dospělí",
    "dospivajici": "dospívající",
    "deti": "děti",
    "kojenci": "kojenci a novorozenci",
    "starsi": "starší pacienti",
    "jine": "jiná skupina",
}


# Klic k OpenAI: soubor key.yaml v KORENI projektu (je v .gitignore, do
# gitu nesmi). Do 6. 10. 2026 lezel v legacy/key.yaml.
OPENAI_KLIC_SOUBOR = Path("key.yaml")


class ChybaKlice(RuntimeError):
    """Klic k OpenAI chybi, ma spatny tvar, nebo ho OpenAI odmitlo."""


def nacti_openai_klic(cesta: str | Path = OPENAI_KLIC_SOUBOR) -> str:
    """Načte klíč k OpenAI z key.yaml. Když to nejde, ChybaKlice s návodem.

    Pozor: soubor je "key:sk-proj-..." BEZ mezery za dvojtečkou, takže to
    není validní YAML mapa – yaml.safe_load() vrátí jeden řetězec, ne dict.
    Proto se to parsuje ručně a snese obojí tvar.

    Jestli klíč u OpenAI opravdu FUNGUJE, tady se nepozná – to ověřuje
    over_openai_klic() jedním voláním, které nic nestojí.
    """
    p = Path(cesta)
    navod = (f"Vytvoř soubor {p} v kořeni projektu s jedním řádkem "
             f"„key: sk-proj-…“ (je v .gitignore).")
    if not p.exists():
        raise ChybaKlice(f"Klíč k OpenAI nenalezen: soubor {p.resolve()} neexistuje. {navod}")
    text = p.read_text(encoding="utf-8").strip()
    if ":" not in text:
        raise ChybaKlice(f"{p}: nečekaný tvar, chybí dvojtečka. {navod}")
    klic = text.split(":", 1)[1].strip().strip("\"'")
    if not klic.startswith("sk-"):
        raise ChybaKlice(f"{p}: za dvojtečkou není klíč OpenAI (má začínat „sk-“). {navod}")
    return klic


def over_openai_klic(klient, model: str | None = None) -> None:
    """Ověří, že klíč u OpenAI FUNGUJE a že je dostupný model. ChybaKlice, když ne.

    Jedno volání GET /v1/models/<model> – neúčtuje se. Pouští se na začátku
    cloudového běhu, aby špatný klíč neselhal až po hodině přípravy dávek
    (nebo hůř: aby běh potichu „doběhl" bez jediného požadavku).
    """
    import openai

    model = model or OPENAI_MODEL
    try:
        klient.models.retrieve(model)
    except openai.AuthenticationError as e:
        raise ChybaKlice(f"OpenAI klíč odmítlo (401): neplatný nebo zrušený klíč v "
                         f"{OPENAI_KLIC_SOUBOR}. [{e}]") from e
    except openai.PermissionDeniedError as e:
        raise ChybaKlice(f"OpenAI klíč nemá oprávnění (403) – projekt nebo model "
                         f"{model} není pro klíč povolený. [{e}]") from e
    except openai.NotFoundError as e:
        raise ChybaKlice(f"Model {model} není pro tento klíč dostupný (404). [{e}]") from e
    except openai.RateLimitError as e:
        raise ChybaKlice(f"OpenAI odmítá požadavky (429) – vyčerpaný kredit nebo "
                         f"limit účtu. [{e}]") from e
    except openai.APIConnectionError as e:
        raise ChybaKlice(f"K OpenAI se nejde připojit (síť, proxy) – klíč se "
                         f"nepodařilo ověřit. [{e}]") from e
