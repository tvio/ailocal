# Přehled skriptů a pořadí spouštění

Mapa všech spustitelných skriptů a modulů `common/`. **Stav k 6. 10. 2026**
(`uklid.md`): stará pipeline nad 32 léky (`data/leciva/`, lokální qwen) je
smazaná, platí jen cesta celého korpusu (`data/spc/`, 5 880 SPC).

**Seznam kroků = `extrakce_all.py` (`KROKY`).** Je to jediné místo, kde je
pořadí pipeline; tabulka níž ho jen opakuje pro čtení.

```bash
uv run python extrakce_all.py --seznam        # vypsat kroky
uv run python extrakce_all.py --stav          # kde který krok je (nic nespouští)
uv run python extrakce_all.py --vse           # všechno po řadě
uv run python extrakce_all.py --od db         # od kroku dál (po pádu, po opravě)
uv run python extrakce_all.py --jen sekce extrakce
```

Hlídá návratové kódy, má zámek proti souběžnému běhu
(`data/extrakce_all.lock`) a log `logs/extrakce_all_<čas>.log`. Po kroku 3
ověří, že extrakce opravdu doběhla (nic ve frontě ani u OpenAI) – jinak
skončí kódem 3 a DB neplní.

**Krok 3 lokálně** (`--local`, od 6. 10.): místo OpenAI jede přes Ollamu –
pro jeden kód SÚKL nebo malou dávku, když cloud není dostupný, na rychlou
opravu léku nebo zkoušku nového lokálního modelu. Stejný prompt, stejné
zpracování odpovědi, stejný výstup; v `_stav.json` je u sekce model
a `zpusob: local`. Celý korpus lokálně ne (~10 dní).

```bash
uv run python extrakce_all.py --jen extrakce --local --kody 0260480              # jeden lék, qwen
uv run python extrakce_all.py --jen extrakce --local --kody 0260480 --sekce indikace --model gemma4:26b
uv run python extrakce_all.py --od extrakce --local --limit 40                   # co čeká ve frontě, pak DB…
uv run python extrahuj_json_cloud.py --local --test --limit-spc 5 --model novy:model   # zkouška modelu mimo korpus
```

Po lokální extrakci jednoho léku se DB doplní `naplni_db.py --obnov-sekci
<sekce>` (znovu nahraje celou sekci korpusu, přírůstek po SPC zatím není)
a `vytvor_embeddingy.py`. Přejmenování skriptů (`extrakce_N_…`,
`hledani_…`) je bod 4 v `uklid.md`.

---

## 1. Pipeline korpusu – pořadí od API SÚKL po hotovou DB

| # | krok | příkaz | služba | stav / navazování |
|---|---|---|---|---|
| 0 | prostředí (jednou) | `priprav_infrastrukturu.py`, `docker compose up -d` | Docker | – |
| 1 | seznam léčiv, inventář SPC, stažení, převod, kontroly převodu, report | `konvertuj_serve.py --obchodovana` | API SÚKL, EMA, Docling Serve, MS Word | `data/spc/_stav.sqlite`, navazuje sám |
| 2 | sekce 4.1/4.2/4.3/4.8 | `extrahuj_sekce.py` | – | přepočítá vše, ~10 min |
| 3 | extrakce do JSON | `extrahuj_json_cloud.py --beh` (cloud) nebo `--local` (Ollama, malý rozsah) | OpenAI Batch (klíč `key.yaml`) / Ollama | `data/spc/_extrakce/stav.sqlite`, navazuje; dávka až 24 h |
| 4 | DB + věk (`vek_od`, `pro_deti`, `jen_deti`) | `naplni_db.py --korpus` (jedna sekce: `--obnov-sekci X`, jen věk: `--jen-vek`) | Postgres | `--korpus` vždy od nuly (TRUNCATE), hledací slovník nechá |
| 5 | embeddingy | `vytvor_embeddingy.py` | Ollama (bge-m3) | jen řádky bez vektoru |
| 6 | rejstřík pro člověka | `postav_rejstrik.py` | – | – |
| 7 | evaluace | `evaluate.py` | Ollama (router), Postgres | – |

**Pro budoucí měsíční job:** cron pouští `extrakce_all.py --vse`. Kroky 1
a 3 závisí na vnějších službách (Docling Serve, OpenAI) a krok 3 čeká na
dávky až 24 h; při souběhu s jinou instancí extrakce skončí pipeline kódem
3 a další spuštění naváže `--od extrakce`. Krok 4 zatím neumí přírůstek
(todo); kontroly extrakce neběží (`nerealizovane_kontroly/`). Návratové
kódy: 0 hotovo, 2 klíč OpenAI, 3 extrakce nedoběhla, jinak kód kroku.

## 2. Skripty pipeline

| skript | co dělá |
|---|---|
| `extrakce_all.py` | **Seznam kroků.** Pouští kroky 1–7 jako samostatné procesy, viz úvod. |
| `konvertuj_serve.py` | **Nahrazuje kroky „stažení" + „Krok 1" pro celý korpus.** Inventář (API SÚKL → identita SPC, deduplikace), stažení (SÚKL, EU z EMA s rozestupem), ořez Přílohy II, převod přes **Docling Serve** (DGX Spark), SPC ve Wordu přes MS Word (DOCX = obsah, PDF = stránky), kontroly kvality proti PDF. Navazuje po pádu, dávky, hlídač zatuhnutí. `--stav` = souhrn. |
| `common/seznam_leciv.py` | **Krok 0:** aktuální měsíční vydání SÚKL (`/aktualni-davky`), seznam kódů (`dlpo`), hrazené (`scau`), detail každého kódu, číselník látek – jen VEŘEJNÉ API. Filtr `PLATNE_STAVY` (R B C F I K M Y) + `jeDodavka`. Voláno z `konvertuj_serve.py`. |
| `common/kontrola_konverze.py` | Kontroly převodu (voláno z `konvertuj_serve.py` po každém dokumentu): pokrytí textu 4.8, frekvence proti značkám PDF (jinak geometrie tabulky), falešné nadpisy. Sekce hledá **stejně jako extrakce** (`common/sekce.py`). |
| `common/report_konverze.py` | Report podezřelých `data/spc/_report/podezrele.html` – na konci KAŽDÉHO běhu `konvertuj_serve.py`. |
| `extrahuj_sekce.py` | **Krok 2:** sekce 4.1/4.2/4.3/4.8 z `data/spc/<identita>/` (jen SPC používaná kódy z inventáře); do `sekce/_prehled.json` přidá `_konverze` = verdikt kontroly převodu. Bez modelu, ~10 min. |
| `extrahuj_json_cloud.py --beh` | **Krok 3 pro celý korpus (od 29. 9.):** extrakce sekcí do JSON přes **OpenAI Batch API** (gpt-6-luna, reasoning none, temperature 0, seed). Prompt a zpracování odpovědi sdílí s `extrahuj_json.py` (`common/extrakce.py`). Stav po požadavku (SPC × sekce) v `data/spc/_extrakce/stav.sqlite`, log `…/_extrakce/log/`, `report.md` se všemi chybami podle ID; navazuje po pádu; `--znovu-chybne`, `--znovu-seznam`; rozpočtový strop `config.CLOUD_STROP_USD`. **Pro budoucí job:** nová závislost OpenAI (klíč, rozpočet), dávka dobíhá až 24 h, výstup `data/spc/<slozka>/json/`. Kontroly jsou zatím vypnuté (`extrakce_kontroly.md`). |
| `common/doc_na_pdf.ps1` | MS Word: `.doc` → DOCX + PDF se značkami (voláno z `konvertuj_serve.py`). |
| `naplni_db.py --korpus` | **Krok 4.** Celý korpus z `data/spc/` + `data/detaily_leciv/`. Vždy od nuly (TRUNCATE přes `vyprazdni_korpus()`, tabulku `slovnik_dotazu` nechá). Všechny kódy do `leciva` (sloupce `spc`, `zastupce`), extrakty a hledací řádky jen jednou za SPC u **zástupce** (nejmenší kód). ~40 min. Na konci přepočte věk (`aktualizuj_vek`). Další režimy: `--obnov-sekci X` (jen jedna sekce), `--jen-vek`. Bez režimu skončí chybou. |
| `vytvor_embeddingy.py` | **Krok 5.** Embeddingy (`bge-m3`, 1024 dim) pro `leciva_search.obsah_text` a klíč. Bez `--znovu` jen chybějící řádky. |
| `postav_rejstrik.py` | **Krok 6.** Rejstřík korpusu pro člověka: `data/leky/<NÁZEV SÍLA>_<kód>` = odkaz (junction) na `data/spc/<id>` + `data/spc/_rejstrik.csv`. `--najdi vibrocil` / `--najdi 0218102`. Pustit po každé změně inventáře (měsíčně). |
| `priprav_infrastrukturu.py` | **Krok 0.** Založí soubory, které `docker compose` potřebuje jako bind-mount, ale nejsou v gitu (`pgpass` aj.). Idempotentní, pustit po `git clone` před prvním `docker compose up`. |

## 3. Hledání a aplikace

| skript | co dělá |
|---|---|
| `hledej.py` | CLI: router → hybridní hledání → výpis seskupený po lécích. |
| `log_hledani.py` | Jako `hledej.py`, ale vypíše KAŽDÝ krok (rozhodnutí routeru, rozšíření dotazu, skóre před prahem) — na ladění a na vysvětlení při předvádění. |
| `api.py` | FastAPI REST API + servíruje `static/` (vanilla JS GUI). Swagger na `/docs`. Na startu na pozadí předehřívá modely. |
| `evaluate.py` | **Krok 7.** Test 0 (kvalita dat, bez modelu; `--jen-data`) + parafráze podle ATC + negativní dotazy mimo medicínu. `--prahy`, `--vahy` měří práh a způsob řazení. Testy nad 32 léky jsou smazané. |

## 4. Benchmarky a diagnostika — nikdy se nespouští automaticky

Úplný seznam s tím, co potřebují a kolik stojí: **`benchmarky/README.md`**.

| skript | co dělá |
|---|---|
| `benchmarky/router/bench_router.py` | Router na různých lokálních modelech, rychlost i správnost. Pustit při změně modelu routeru. |
| `benchmarky/extrakce_cloud/bench_extrakce_luna.py` | Cena CELÉ extrakce v cloudu (luna): `--tokeny` spočítá vstup korpusu tiktokenem, `--beh` pustí reálnou extrakci na malém/středním/velkém SPC a odhadne výstup i cenu. Pustit před každým hromadným cloudovým během (změna promptu = jiná cena). |
| `benchmarky/indikace_fragmenty/` | Detektory a soudce chybných položek indikací (2. 10.), `test_promptu.py` starý vs. nový prompt. Pustit při změně promptu indikací. |
| `nerealizovane_kontroly/` | Kontroly extrakce a číselník pojmů nad starým korpusem – předloha, nespustitelné bez úprav (README uvnitř). |

## 5. `common/` — sdílené moduly (importují se, nespouští se samostatně)

| modul | co dělá |
|---|---|
| `config.py` | Jediný zdroj pravdy: cesty, názvy modelů, DB DSN, `adresar_leciva()`. |
| `sukl_api.py` | Klient pro obě SÚKL API (dokumentované `/dlp/v1` + nedokumentované vyhledávací `/prehledy/v1`). |
| `konverze.py` | Docling PDF→Markdown + ořez EU dokumentů. |
| `sekce.py` | Vytažení sekcí 4.1–4.8 z markdownu/PDF, ořez na jádro. |
| `extrakce.py` | Prompty a volání modelu pro převod sekce → JSON. |
| `slovnik.py` | Číselník odborný→laický termín, aplikace na data. |
| `meddra.py` | Normalizace názvů orgánových systémů (MedDRA SOC) na kanonický tvar. |
| `vek.py` | Věk použití léku z SPC 4.1–4.3 BEZ modelu (`vek_spc`: `vek_od`, `pro_deti`, důvody) a věk v dotazu laika (`vek_z_dotazu`, `bez_veku`). Plní ho `naplni_db.py` (`aktualizuj_vek`, i `--jen-vek`), filtr v `hledani.py`, volá `router.py`. |
| `nazev_vzor.py` | Hledání podle části názvu: pevné formulace „lék začíná [na] XXX / obsahuje XXX / končí [na] XXX / přibližně XXX" (min. 3 znaky; přibližně = překlepy a fonetika) → filtr JEN na název léku (bez diakritiky). Volá `router.py` deterministicky, filtr v `hledani.py`. |
| `router.py` | Dotaz v přirozené řeči → filtr + výběr sekce. |
| `dotazy.py` | Rozšíření DOTAZU (ne dat) o formulace z dokumentů — číselník `slovnik_dotazu.json`. Od 6. 10. je úložištěm tabulka `slovnik_dotazu` v DB (mění se z GUI přes `/api/slovnik`, čte se při každém dotazu); JSON je jen výchozí náplň při založení tabulky. `naplni_db.py` ji mazat NESMÍ. |
| `hledani.py` | Hybridní hledání: cosine (bge-m3) + český fulltext přes RRF, aplikace filtrů. |
| `ollama_client.py` | Tenký wrapper nad Ollama REST API (`chat`, `embed`, `priprav_modely`). |
| `log_behu.py` | Detailní log běhu (soubor s průběžným flushem + dávkový zápis do DB). |
| `seznam_leciv.py`, `kontrola_konverze.py`, `report_konverze.py`, `report_sekce.py`, `doc_na_pdf.ps1` | části kroků 1 a 2, popis v oddílu 2. |

## 6. Smazáno 6. 10. 2026 (v gitu do commitu `71c761c`)

Stará pipeline: `pipeline.py`, `stahni_data.py`, `postav_pool.py`,
`konvertuj_spc.py`, `extrahuj_json.py`, `rozdel_vycty.py`, `doplni_klice.py`,
`analyza_formatu.py`, `zkontroluj_orez.py`, `test_klice.py`.
Benchmarky s výstupy: `bench_extrakce.py`, `bench_zjednoduseni.py`,
`bench_rerank_nano.py`, `bench_embed_cloud.py`, `bench_konverze.py`,
`bench_effort_*.json`, `bench_gemma_zjednoduseni*.json`,
`bench_zjednoduseni*.json`, `bench_konverze.json`, `benchmarky/pdfextrakce/`
(Docling vs. pymupdf4llm), `audit_hledani.py` + `.md`, `benchmark/docling_serve/`
(nebyl v gitu). Závěry z nich jsou
v `poznatky.md` a v tabulce slepých uliček v `CLAUDE.md`.
