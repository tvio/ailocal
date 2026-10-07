# localsemantic

Sémantické a fulltextové vyhledávání v souhrnech údajů o přípravku (SPC)
ze SÚKL. Uživatel se ptá běžnou češtinou („pálí mě žáha"), aplikace najde
odpověď v oficiálních dokumentech a ukáže odkaz na stranu PDF.

Korpus: všechna obchodovaná léčiva ČR (zářijové vydání SÚKL) – 8 778 kódů
SÚKL, 5 880 unikátních SPC. Cílová skupina jsou laici.

## Spuštění

```bash
uv run python provoz_priprava.py          # jednou po git clone (soubory pro Docker)
docker compose up -d                      # Postgres + pgAdmin
uv run uvicorn api:app --port 8000        # GUI http://localhost:8000/, Swagger /docs
uv run python hledani_cli.py "mám reflux" # totéž z příkazové řádky
```

Potřebuje Ollamu s modely `gemma4:26b` (router) a `bge-m3` (embedding).
Stroje jsou v `common/config.py` (`OLLAMA_UZLY`, na serveru proměnná
prostředí); může jich být víc, aplikace mezi ně dotazy rozděluje. Hesla a řešení potíží:
`docs/provoz_pristupy.md`.

## Pipeline dat

Jeden seznam kroků od API SÚKL po hotovou databázi:

```bash
uv run python extrakce_all.py --seznam    # co se dělá a v jakém pořadí
uv run python extrakce_all.py --stav      # kde který krok je
uv run python extrakce_all.py --vse       # všechno po řadě
```

| # | krok | skript | potřebuje |
|---|---|---|---|
| 1 | seznam léčiv, stažení SPC, převod do Markdownu | `extrakce_1_konverze.py` | API SÚKL, EMA, Docling Serve |
| 2 | sekce 4.1 / 4.2 / 4.3 / 4.8 | `extrakce_2_sekce.py` | – |
| 3 | extrakce do JSON | `extrakce_3_json.py` | OpenAI (klíč v `key.yaml`), nebo `--local` přes Ollamu |
| 4 | naplnění databáze | `extrakce_4_db.py` | Postgres |
| 5 | embeddingy | `extrakce_5_embeddingy.py` | Ollama |
| 6 | rejstřík složek SPC podle názvu a kódu | `extrakce_6_rejstrik.py` | – |
| 7 | evaluace | `hledani_evaluace.py` | Ollama, Postgres |

Krok 3 stojí peníze (celý korpus ~11 $) a v cloudu dobíhá až 24 hodin.
Podrobnosti: `docs/pipeline_prehled.md`.

## Struktura

| kde | co |
|---|---|
| `extrakce_*.py` | kroky pipeline, `extrakce_all.py` je jejich seznam |
| `hledani_*.py`, `api.py` | hledání z příkazové řádky, podrobný log, evaluace, REST API |
| `common/` | sdílený kód (router, hledání, extrakce, věk, konfigurace) a `common/data/` (slovníky) |
| `static/` | webové GUI |
| `docs/` | dokumentace: `pipeline_*`, `hledani_*`, `provoz_*`, `prezentace_*` |
| `benchmarky/` | měření, která jde zopakovat – seznam v `benchmarky/README.md` |
| `nerealizovane_kontroly/` | kontroly extrakce nad původním malým korpusem, nad celým neběží |
| `data/` | korpus a mezivýsledky, není v gitu |

## Kam se zapisuje

| soubor | k čemu |
|---|---|
| `poznatky.md` | deník měření a nálezů, nejnovější nahoře |
| `aktualnistav.md` | stav teď a další krok |
| `todo.md` | úkoly |
| `CLAUDE.md` | pokyny pro Claude Code: pravidla, slepé uličky, mapa dokumentace |
| `agents.md` | pokyny pro Codex |

## Co je dobré vědět

- Data z automatické extrakce obsahují chyby a nic je zatím nekontroluje;
  u každého výsledku je proto odkaz na stranu původního PDF. Příklad:
  `docs/prezentace_scenare.md`, kapitola 6.
- Dotazy na předvedení: `docs/prezentace_scenare.md`.
