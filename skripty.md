# Přehled skriptů a A→Z spouštění

Účel: mapa všech `.py` souborů v kořeni projektu — co dělá, jestli je
součástí `pipeline.py`, a jestli se má pouštět sólo. Napsáno proto, že
`todo.md` bod 3 už dlouho visí jako nedodělek ("V jakém stavu je
kompletní spouštění extrakce a nahrání databáze").

**Zkratka:** `pipeline.py` NEPOKRÝVÁ celý běh od stažení dat po hotovou
databázi. Pokrývá jen prostřední část (konverze → slovník). Detaily
níže v sekci 2.

---

## 1. Co který soubor dělá

### A) Stažení dat ze SÚKL — PŘED pipeline.py

| skript | co dělá |
|---|---|
| `stahni_data.py` | Stáhne `api.json` + `spc.pdf` pro zvolená léčiva do `data/leciva/<kód>_<NÁZEV>/`. Čtyři režimy výběru: `--pilot` (3 léčiva na ověření), `--kody KOD...` (konkrétní SÚKL kódy), `--whitelist` (podle `ATC_WHITELIST` v souboru), `--vzorek-formatu` (1 lék z 20 ATC skupin, na průzkum formátů SPC). |
| `postav_pool.py` | Stáhne detail VŠECH léčiv v registru SÚKL do cache `data/pool_leciv.json` (desítky minut). Používá se jako podklad pro `--whitelist` výběr — bez cache by se ATC musel zjišťovat po jednom. Pouští se jen když cache chybí nebo je stará. |

### B) Extrakce — TOHLE dělá `pipeline.py --vse`

| pořadí | krok | skript | co dělá |
|---|---|---|---|
| 1 | Krok 1 | `konvertuj_spc.py` | PDF → Markdown přes Docling, ořez EU dokumentů na Přílohu I. |
| 2 | Krok 2 | `extrahuj_sekce.py` | Vytáhne sekce 4.1/4.2/4.3/4.8 z markdownu, vytvoří ořezanou verzi (`_orez.md`) pro model. |
| 3 | Krok 3 | `extrahuj_json.py` | Sekce → strukturovaný JSON přes `qwen3.5:122b`, včetně laického zjednodušení. Zapisuje `_stav.json`. |
| 3b | — | `ocisti_json.py` | Deterministické čištění (BEZ modelu): frekvence na číselník, `organovy_system` na kanonický MedDRA SOC, laický tvar podle `slovnik_pojmu.json`. |
| 4a | Krok 4a | `zkontroluj_json.py` | Deterministická kontrola extrakce proti zdrojovému textu (doslovná shoda po normalizaci). |
| 4b | Krok 4b | `zkontroluj_modelem.py` | Kontrola JINÝM modelem (`gemma4:31b`) tam, kde deterministická kontrola nestačí (indikace/kontraindikace, sporné případy). |
| 5 | Krok 5 | `postav_slovnik.py` | Posbírá číselník odborný→laický termín ze všech extrakcí, volitelně ověří modelem. Zapisuje `slovnik_pojmu.json` (generovaný, přepisuje se) a čte `slovnik_rucni.json` (ruční opravy, autoritativní). |

### C) Krok, který `pipeline.py` NEVOLÁ, ale je součástí extrakce

| skript | co dělá |
|---|---|
| `rozdel_vycty.py` | Rozdělí položky indikací/kontraindikací s víc slepenými příznaky do samostatných řádků (modelem, ne regexem — regex měřitelně škodí ve 3 z 5 případů). Podle `zadani.md`/`todo.md` se pouští PO `postav_slovnik.py`, před `naplni_db.py`. |

### D) Databáze a embeddingy — MIMO pipeline.py, spouští se sólo

| pořadí | skript | co dělá |
|---|---|---|
| — | `priprav_infrastrukturu.py` | Založí soubory, které `docker compose` potřebuje jako bind-mount, ale nejsou v gitu (`pgpass` aj.). Idempotentní, pustit po `git clone` před prvním `docker compose up`. |
| Krok 11 | `naplni_db.py` | Naplní Postgres z `data/leciva/*` a `slovnik_pojmu.json`: tabulky `leciva`, `extrakty`, `extrakce_stav`, `leciva_search`, `slovnik_pojmu`. Bez `--znovu` jen doplňuje chybějící; **`--znovu` po jakékoli změně dat POVINNĚ**, jinak hrozí tiché zdvojení řádků. |
| Krok 12 | `vytvor_embeddingy.py` | Spočítá embeddingy (`bge-m3`, 1024 dim) pro `leciva_search.obsah_text`. Bez `--znovu` jen chybějící řádky. |

### E) Hledání a aplikace

| skript | co dělá |
|---|---|
| `hledej.py` | CLI: router → hybridní hledání → výpis seskupený po lécích. |
| `log_hledani.py` | Jako `hledej.py`, ale vypíše KAŽDÝ krok (rozhodnutí routeru, rozšíření dotazu, skóre před prahem) — na ladění a na vysvětlení při předvádění. |
| `api.py` | FastAPI REST API + servíruje `static/` (vanilla JS GUI). Swagger na `/docs`. Na startu na pozadí předehřívá modely. |
| `evaluate.py` | Krok 15 — reprodukovatelná evaluace (testy 0–4: kvalita dat, auto-recall, negativní dotazy, parafráze, práh/váhy). **Pustit po každé změně promptu, modelu, chunkování, vah nebo prahu.** |

### F) Pomocné a diagnostické skripty — nikdy se nespouští automaticky

| skript | co dělá |
|---|---|
| `analyza_formatu.py` | Klasifikuje, kolik různých formátů má sekce 4.8 napříč staženými dokumenty (podklad pro psaní extrakčního promptu). |
| `zkontroluj_orez.py` | Ukáže, co ořez sekce ZAHODIL (ne co zůstalo) — kontrola, že ořez neuřízl něco podstatného. |
| `bench_extrakce.py` | Benchmark rychlosti extrakce: modely, `num_ctx`, tvar výstupního JSON, OpenAI. |
| `bench_embed_cloud.py` | Srovnání lokálního `bge-m3` s cloudovými embeddingy OpenAI (jen embedding, ne chat — viz CLAUDE.md peníze). |
| `bench_rerank_nano.py` | Test, jestli `gpt-5-nano` jako reranker zlepší pořadí kandidátů z `bge-m3`. |
| `test_klice.py` | Pokus: pomohl by krátký "klíč" (2–4 slova) pro hledání u dlouhých indikací? Nic nezapisuje. |

### G) `common/` — sdílené moduly (importují se, nespouští se samostatně)

| modul | co dělá |
|---|---|
| `config.py` | Jediný zdroj pravdy: cesty, názvy modelů, DB DSN, `adresar_leciva()`. |
| `sukl_api.py` | Klient pro obě SÚKL API (dokumentované `/dlp/v1` + nedokumentované vyhledávací `/prehledy/v1`). |
| `konverze.py` | Docling PDF→Markdown + ořez EU dokumentů. |
| `sekce.py` | Vytažení sekcí 4.1–4.8 z markdownu/PDF, ořez na jádro. |
| `extrakce.py` | Prompty a volání modelu pro převod sekce → JSON. |
| `slovnik.py` | Číselník odborný→laický termín, aplikace na data. |
| `meddra.py` | Normalizace názvů orgánových systémů (MedDRA SOC) na kanonický tvar. |
| `router.py` | Dotaz v přirozené řeči → filtr + výběr sekce. |
| `dotazy.py` | Rozšíření DOTAZU (ne dat) o formulace z dokumentů — číselník `slovnik_dotazu.json`. |
| `hledani.py` | Hybridní hledání: cosine (bge-m3) + český fulltext přes RRF, aplikace filtrů. |
| `ollama_client.py` | Tenký wrapper nad Ollama REST API (`chat`, `embed`, `priprav_modely`). |
| `log_behu.py` | Detailní log běhu (soubor s průběžným flushem + dávkový zápis do DB). |

---

## 2. Obsahuje `pipeline.py` opravdu všechny kroky? **NE**

`pipeline.py` řetězí přesně těch 7 kroků, co má v `KROKY` (řádek 47–55):
konverze → sekce → extrakce → očištění → kontrola1 → kontrola2 → slovník.
Tři reálné kroky pipeline chybí:

1. **Stažení dat (`stahni_data.py`) běží PŘED pipeline.py a pipeline o něm neví.**
   `pipeline.py --vse` čte `data/leciva/*`, ale nic tam nestáhne. Když
   adresář neexistuje nebo je prázdný, `pipeline.py --vse` proběhne
   "úspěšně" nad nulou léčiv.

2. **`rozdel_vycty.py` chybí v `KROKY` úplně.** Podle `zadani.md` (řádek 34,
   krok "8b") i `todo.md` se má pouštět PO `postav_slovnik.py`. Dnes se
   musí spustit ručně — `pipeline.py --vse` ho přeskočí beze slova.

3. **Naplnění databáze a embeddingy jsou úplně mimo `pipeline.py`.**
   `naplni_db.py` (krok 11) a `vytvor_embeddingy.py` (krok 12) nejsou
   v `KROKY` vůbec — bez nich nová/změněná data v hledání vůbec
   nenaskočí, ale `pipeline.py --vse` se přesto tváří jako "CELÁ PIPELINE
   HOTOVA".

K tomu jedna provozní past navíc: `pipeline.py` nemá `--kody` — vždycky
volá jednotlivé skripty s `--vse` (viz `ARGY`, řádek 58–66). Když
přidáš 2 nová léčiva a spustíš `pipeline.py --vse`, **znovu se
zkonvertují a znovu se vytáhnou sekce úplně VŠECHNA léčiva** (kroky 1–2
nemají žádnou kontrolu "už hotovo"), i těch 30 starých. Zbytečné, ale
ne drahé — kroky 1–2 model nevolají. Teprve krok 3 (`extrahuj_json.py`)
už existující JSON přeskočí, pokud nedáš `--znovu`.

## 3. Můžu pustit `pipeline.py` a pak zvlášť `naplni_db.py`?

Ano, přesně takhle to dnes funguje — ale chybí ti mezi tím `rozdel_vycty.py`
a za tím `vytvor_embeddingy.py`. Správné pořadí od nuly:

```bash
# A) stažení — MIMO pipeline.py
uv run python stahni_data.py --kody 0207818 0028820      # nebo --pilot / --whitelist

# B) extrakce — TOHLE dělá pipeline.py
uv run python pipeline.py --vse

# C) chybí v pipeline.py, pustit ručně
uv run python rozdel_vycty.py --zapis

# D) databáze a embeddingy — MIMO pipeline.py
uv run python naplni_db.py --znovu
uv run python vytvor_embeddingy.py

# E) ověření
uv run python evaluate.py
```

Pozor na `--znovu` u `naplni_db.py` — bez něj skript jen DOPLNÍ nové
řádky, staré nepřepíše (viz CLAUDE.md: "bez `--znovu` data TIŠE ZDVOJÍ"
platilo dřív, dnes to skript odmítne, ale bezpečnější je `--znovu` dávat
vždycky po změně dat).

Zkrácená verze z CLAUDE.md (`ocisti_json.py --zapis` → `naplni_db.py
--znovu` → `vytvor_embeddingy.py` → `evaluate.py`) je pro situaci, kdy
extrakce (kroky A–C) už proběhla a mění se jen řízené slovníky nebo
ruční opravy — NE pro běh od nuly.

## 4. Chci vybrat jiná léčiva z API — co musím udělat?

Dvě cesty podle toho, jestli znáš konkrétní kódy SÚKL:

**a) Konkrétní léky (znáš kód SÚKL):**
```bash
uv run python stahni_data.py --kody 0207818 0028820
```

**b) Podle skupiny léčiv (ATC kód), ne konkrétního léku:**
Uprav `ATC_WHITELIST` na začátku `stahni_data.py` (řádek 48–62) —
je to `{atc_kod: pocet}`. Přidej/uprav položku a spusť:
```bash
uv run python stahni_data.py --whitelist --limit-skupiny 5   # přebije počty z dictu
```
`postav_pool.py` je potřeba pustit jen jednou (cache trvá desítky minut
stáhnout), `--whitelist` ji pak používá k dohledání ATC kódů. Pokud
`data/pool_leciv.json` chybí, `SuklClient`/`stahni_data.py` si ji
dotáhne sám při prvním volání s `--whitelist`.

**Pak vždycky celá extrakce znovu** — nová léčiva projdou stejnou
sekvencí jako v sekci 3 (B–E). Kroky A–C jsou pro nová léčiva
nutné (žádný JSON/sekce pro ně ještě neexistuje), `naplni_db.py` bez
`--znovu` by je jen přidal ke stávajícím — to stačí, pokud jsi
neměnil nic u starých léčiv.

**Pozor na cenu:** krok 3 (`extrahuj_json.py`) a krok 4b
(`zkontroluj_modelem.py`) volají model. Lokálně (`qwen3.5:122b`,
`gemma4:31b`) to nic nestojí. Volby `--openai`/`--model gpt-5-nano`
u některých skriptů posílají text ven — drž se `gpt-5-nano`, nikdy
`gpt-4o` (viz CLAUDE.md).
