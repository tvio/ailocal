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
MODEL_HLAVNI = "qwen3.5:122b"        # extrakce, slovník, router, kontrola
MODEL_EMBED = "bge-m3"               # embedding NEDĚLÁ generativní model!
                                     # /api/embed vyžaduje capability 'embedding'
                                     # (pooling_type v manifestu), jinak vrátí 501.
                                     # 1024 dim nativně -> vejde se do HNSW indexu.

# Menší modely zůstávají pro srovnání v benchmarku, v pipeline se nepoužívají.
MODEL_EXTRAKCE = MODEL_HLAVNI
MODEL_LAIK = MODEL_HLAVNI
MODEL_ROUTER = MODEL_HLAVNI
# Kontrola MUSI byt JINY model nez ten, ktery extrahoval - model si
# neodsouhlasi vlastni chybu. Vetsi uz neni kam jit (122b je nejlepsi),
# takze se voli jiny, ne vetsi. Overeno na vzorku: gemma4:31b je rychla
# (9,7 s/sekci), vraci validni JSON a nasla skutecnou chybu, kterou
# deterministicka kontrola najit nemuze ("akutni alergicke stavy" ve zdroji
# proti "tezke alergicke reakce" v extrakci). Pritom neoznackuje vsechno -
# 1 nalez z 65 polozek.
MODEL_KONTROLY = "gemma4:31b"

# Který model dělá kterou sekci. Dělit úlohy mezi modely se ukázalo jako
# zbytečné – 122b vyhrává na struktuře i na češtině. Mechanismus tu zůstává,
# kdyby bylo potřeba se od toho někde odchýlit.
MODEL_SEKCE = {
    "indikace": MODEL_HLAVNI,
    "kontraindikace": MODEL_HLAVNI,
    "davkovani": MODEL_HLAVNI,
    "nezadouci_ucinky": MODEL_HLAVNI,
}

# --- OpenAI (jen na srovnání, ne v pipeline) ---
# POZOR NA PENÍZE: na účtu je jen pár dolarů. Používat VÝHRADNĚ gpt-5-nano,
# ten je pro tuhle úlohu ověřeně dost dobrý a stojí nejmíň. gpt-4o ani
# gpt-4o-mini nepouštět – gpt-4o stojí násobně víc a účet by to vyčerpalo.
OPENAI_MODEL = "gpt-5-nano"

EMBED_DIMENSION = 1024

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


def nacti_openai_klic(cesta: str | Path = "legacy/key.yaml") -> str:
    """Načte klíč k OpenAI z key.yaml.

    Pozor: soubor je "key:sk-proj-..." BEZ mezery za dvojtečkou, takže to
    není validní YAML mapa – yaml.safe_load() vrátí jeden řetězec, ne dict.
    Proto se to parsuje ručně a snese obojí tvar.
    """
    text = Path(cesta).read_text(encoding="utf-8").strip()
    if ":" not in text:
        raise ValueError(f"{cesta}: nečekaný tvar, chybí dvojtečka")
    klic = text.split(":", 1)[1].strip().strip("\"'")
    if not klic.startswith("sk-"):
        raise ValueError(f"{cesta}: za dvojtečkou není klíč OpenAI")
    return klic
