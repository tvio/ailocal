# Úklid projektu – seznam úkolů (6. 10. 2026)

Pracovní seznam, prochází se odshora. Po dokončení úklidu se tenhle soubor
smaže. Inventura: 31 skriptů `.py` v kořeni, 19 modulů v `common/`, 25 `.md`,
14 výstupů benchmarků `.json` v kořeni, `legacy/` (42 souborů v gitu).

**Zatím se nic nemazalo ani nepřesouvalo.** `[R]` = čeká na rozhodnutí.

---

## 0. Než se začne

- [ ] **Commit rozdělané práce** – 19 změněných souborů od 4. 10. (slovník
      v DB, filtr pro dospělé, GUI). Úklid dělat v samostatných commitech,
      ať jde každý krok vrátit.
- [x] **Klíč k OpenAI ven z `legacy/`** (R1, hotovo 6. 10.) – `key.yaml`
      v kořeni (v `.gitignore`). Chybí / špatný tvar / OpenAI ho odmítne →
      `extrahuj_json_cloud.py --beh` skončí hned chybou `CHYBA KLICE OPENAI`
      a návratovým kódem 2 (`config.over_openai_klic`, volání zdarma).
- [x] **Jména a umístění skriptů** (R2) – návrh z bodu 4 schválen.

---

## 1. Neaktuální věci – ke smazání

### 1a. Stará pipeline (32 léčiv, `data/leciva/`, lokální qwen)

**HOTOVO 6. 10.** – smazáno vše z tabulky včetně obou souborů `.old` (R3).

| soubor | proč pryč |
|---|---|
| `pipeline.py` | řetězí jen starou cestu (7 kroků nad `data/leciva`); **po přesunu kontrol už nefunguje**; nahradí ho nový seznam kroků (bod 2) |
| `stahni_data.py` | stahování po kódech do `data/leciva`; nahrazeno `konvertuj_serve.py` + `common/seznam_leciv.py` |
| `postav_pool.py` | nahrazeno `common/seznam_leciv.py` (píše tentýž `pool_leciv.json`) |
| `konvertuj_spc.py` | lokální Docling; nahrazeno `konvertuj_serve.py` |
| `extrahuj_json.py` | extrakce lokálním qwenem; nahrazeno `extrahuj_json_cloud.py` (prompty zůstávají v `common/extrakce.py`) |
| `rozdel_vycty.py` | dělení výčtů modelem nad starým korpusem; dnes to dělá prompt indikací |
| `doplni_klice.py` | dopočet klíčů do starých dat; klíč je teď přímo v extrakci |
| `analyza_formatu.py` | průzkum formátů 4.8 před psaním promptu (srpen) |
| `zkontroluj_orez.py` | kontrola ořezu sekce; ořez 4.2 je od 30. 9. vypnutý |
| `test_klice.py` | jednorázový pokus (září), nic nezapisuje |
| `konverze.log`, `konverze_vzorek.log` | logy ze srpna, omylem v gitu |
| `daliborTech.old`, `zadaniVitek.old` | mimo git, osobní podklady `[R3]` smazat, nebo si je necháš jinde? |

**Kontroly a slovník pojmů (R4, hotovo 6. 10.)** – nesmazáno, přesunuto do
`nerealizovane_kontroly/` (README říká, co který skript dělá):
`zkontroluj_json.py`, `zkontroluj_modelem.py`, `postav_slovnik.py`,
`ocisti_json.py`. **V pipeline zůstávají živé** `common/slovnik.py`
a `slovnik_rucni.json` (ruční číselník se při extrakci uplatňuje pořád).

### 1b. Zastaralé benchmarky a jejich výstupy v kořeni

**HOTOVO 6. 10.** – smazáno vše včetně auditu hledání (R5); zbývá jen
`data/bench_embed_cloud.json` (data mimo git, bod 5).

| soubor | proč pryč |
|---|---|
| `bench_extrakce.py` | rychlost lokální extrakce (qwen, `num_ctx`); extrakce je v cloudu |
| `bench_zjednoduseni.py` + `bench_zjednoduseni*.json`, `bench_gemma_zjednoduseni*.json` | qwen vs. cloud ve zjednodušení; rozhodnuto (luna), závěr v `poznatky.md` |
| `bench_effort_luna*.json`, `bench_effort_nano*.json` | `reasoning_effort` luna/nano; rozhodnuto, závěr v `CLAUDE.md` |
| `bench_rerank_nano.py` | rerank přes gpt-5-nano; model se už nepoužívá |
| `bench_embed_cloud.py` + `data/bench_embed_cloud.json` (13 MB) | cloudové embeddingy; zamítnuto, závěr v `CLAUDE.md` |
| `bench_konverze.py` + `bench_konverze.json` | varianty lokálního Doclingu; produkce jede přes Docling Serve |
| `audit_hledani.py` + `.json` (3,4 MB) + `.md` | audit hledání z 22. 9. nad 32 léky; závěry jsou v `todo.md` `[R5]` smazat, nebo `.md` nechat v archivu? |

### 1c. Stará evaluace

**HOTOVO 6. 10. (R6).** `evaluate.py` má jen test 0 (pokrytí počítané po
SPC: 96 %, dřív zavádějících 64 % po kódech), parafráze podle ATC
a negativní dotazy; `--prahy` a `--vahy` měří nad korpusem. Testy 1–4
a `vzorek_eval.json` smazány. Po úklidu: 18/20, přesnost 69 %, negativní
5/6 – stejné jako před ním.

---

## 2. Nová pipeline – jeden seznam všech kroků

Cíl: jediný vstupní skript se seznamem `KROKY` (CLAUDE.md mu říká
`extrakce_all.py`), od API SÚKL po hotovou DB. Dnešní skutečné pořadí:

| # | krok | dnes | služba |
|---|---|---|---|
| 0 | příprava prostředí (jednou) | `priprav_infrastrukturu.py`, `docker compose up -d` | – |
| 1 | seznam léčiv z API SÚKL, inventář SPC, stažení (SÚKL + EMA), převod, kontroly převodu, report | `konvertuj_serve.py --obchodovana` (+ `common/seznam_leciv.py`, `kontrola_konverze.py`, `report_konverze.py`) | Docling Serve, MS Word |
| 2 | sekce 4.1/4.2/4.3/4.8 | `extrahuj_sekce.py --korpus` | – |
| 3 | extrakce do JSON | `extrahuj_json_cloud.py --beh` (+ `--znovu-chybne`) | OpenAI Batch |
| 4 | naplnění DB + věk (`vek_od`, `pro_deti`, `jen_deti`) | `naplni_db.py --korpus` | Postgres |
| 5 | embeddingy | `vytvor_embeddingy.py` | Ollama (bge-m3) |
| 6 | rejstřík pro člověka | `postav_rejstrik.py` | – |
| 7 | evaluace | `evaluate.py --korpus` | Ollama (router) |

- [x] **`extrakce_all.py`** (6. 10.): `--seznam`, `--stav`, `--vse`, `--od`,
      `--jen`; zámek, log, návratové kódy; po kroku 3 ověří, že extrakce
      doběhla. Vyzkoušeno `--seznam`, `--stav` a krok `rejstrik`; celé
      `--vse` puštěné nebylo (stálo by peníze a hodiny).
- [ ] `[R7]` Krok 1 dělá čtyři věci v jednom skriptu (42 kB). Pro přehled
      v seznamu stačí jeden krok; rozdělení na „seznam / stažení / převod"
      je samostatná práce – teď ne?
- [x] Vyházet starou cestu ze živých skriptů (6. 10.):
      `naplni_db.py` (režim bez `--korpus`, `--kody`, `--znovu`, generovaný slovník pojmů),
      `extrahuj_sekce.py` (`--vse`, `--kody` nad `data/leciva`),
      `api.py`, `hledej.py`, `common/hledani.py` (záložní cesta k PDF v `data/leciva`),
      `common/config.py` (`LECIVA_DIR`, `adresar_leciva`, `MODEL_SEKCE`, `MODEL_EXTRAKCE`…),
      `common/sukl_api.py` (`postav_pool`).
- [x] `skripty.md`: co seznam znamená pro měsíční job (služby, návratové
      kódy, asynchronní krok 3).
- [x] Lokální extrakce zůstává a je zapojená jako volba kroku 3
      (`--local`, `--model`, `--kody`, `--sekce`, `--limit`) v runneru
      i v `extrakce_all.py`. Vyzkoušeno na 1 sekci v testovací složce
      (gemma4:26b, 10 s, 12 položek) a chybové stavy (neznámý kód, model).

---

## 3. Platné benchmarky → `benchmarky/<téma>/`

**HOTOVO 6. 10.** Pravidlo od uživatele: co neměří dnešní pipeline, smazat.

- `bench_router.py` → `benchmarky/router/` (cesty opraveny, výstup `.json`
  už není v gitu).
- Smazáno: `benchmark/docling_serve/` (Codex, nebyl v gitu),
  `benchmarky/pdfextrakce/` (lokální Docling vs. pymupdf4llm, ~70 MB výstupů),
  audit hledání.
- Zůstává: `router/`, `extrakce_cloud/`, `indikace_fragmenty/`.
- Seznam s popisem: `benchmarky/README.md` + oddíl „Benchmarky" v `CLAUDE.md`
  (načítá se s projektem).
- [x] `bench_router.py` část B přepsána na parafráze podle ATC (nepuštěno).

---

## 4. Názvy a kořen projektu `[R2]`

Omezení: skript spouštěný `uv run python X.py` najde `common/` jen když leží
v kořeni. Podsložka pro skripty znamená spouštění `python -m …` a úpravu
všech návodů. Proto návrh **předpony v kořeni**, zbytek do složek:

| dnes | návrh |
|---|---|
| (nový seznam kroků) | `extrakce_all.py` |
| `konvertuj_serve.py` | `extrakce_1_konverze.py` |
| `extrahuj_sekce.py` | `extrakce_2_sekce.py` |
| `extrahuj_json_cloud.py` | `extrakce_3_json.py` |
| `naplni_db.py` | `extrakce_4_db.py` |
| `vytvor_embeddingy.py` | `extrakce_5_embeddingy.py` |
| `postav_rejstrik.py` | `extrakce_6_rejstrik.py` |
| `hledej.py` | `hledani_cli.py` |
| `log_hledani.py` | `hledani_log.py` |
| `evaluate.py` | `hledani_evaluace.py` |
| `api.py` | zůstává (`uvicorn api:app`) |
| `priprav_infrastrukturu.py` | `provoz_priprava.py` |

V kořeni pak zůstane: 11 skriptů, `CLAUDE.md`, `pyproject.toml`, `uv.lock`,
`docker-compose.yml`, `init-db.sql`, `.gitignore` + složky `common/`,
`static/`, `benchmarky/`, `docs/`, `data/`.

- [ ] `[R8]` Soubory pro Docker (`Dockerfile.postgres`, `tsearch/`,
      `pgadmin-servers.json`, `pgpass`) do `docker/`? Znamená úpravu cest
      v `docker-compose.yml` a `priprav_infrastrukturu.py`.
- [ ] `slovnik_dotazu.json`, `atc_mapa.json` → `common/data/` (čte je jen
      `common/dotazy.py`).
- [ ] Po přejmenování: `CLAUDE.md` (Příkazy), `skripty.md`, `scenare.md`,
      `gui.md`, `sledovaniBatchOpenAI.md`, docstringy „Použití:".

---

## 5. Stará data pryč

**HOTOVO 6. 10.** Smazáno (mimo git, nevratně, s potvrzením): `data/leciva/`
(32 léčiv), `data/_zaloha_dlouhe_leky/`, `data/bench_embed_cloud.json`.
V DB stará data nebyla (TRUNCATE 30. 9.).

- [ ] `[R9]` `logs/` (3,8 MB, 40 souborů od srpna) – smazat staré?

---

## 6. Smazat `legacy/`

**HOTOVO 6. 10.** Smazáno celé: 42 souborů z gitu + `dalibor.py`, `pgpass`,
`data/pdf/` mimo git. Klíč k OpenAI je v kořeni. Odkazy v `CLAUDE.md`
a `.gitignore` opraveny; zmínky „z legacy fáze" v komentářích `common/`
jsou historie a zůstávají.

- [ ] `[R10]` Docker volumes z dřívějška ještě existují: `legacy_pgdata`,
      `legacy_pgadmin_data`, `ailocal_pgdata`, `ailocal_pgadmin_data`.
      Aplikace používá jen `localsemantic_*`. Smazat?

---

## 7. Dokumenty – aktualizovat nebo smazat

| soubor | návrh |
|---|---|
| `CLAUDE.md` | **aktualizovat**: korpus 5 880 SPC (ne 32), modely (qwen už ne), příkazy, „Po změně dat", `legacy/`, tabulka dokumentace |
| `skripty.md` | **přepsat** podle bodu 2 (dnes z půlky popisuje starou pipeline) |
| `aktualnistav.md` | zkrátit na aktuální stav; historie je v `poznatky.md` |
| `todo.md` (107 kB, 2 100 řádků) | **proškrtat**: nechat „TODO ME" + TOP od 2. 10. + cílový stav; plány z 22.–29. 9. nad 32 léky smazat `[R11]` |
| `poznatky.md` (282 kB, 107 zápisů) | nechat celé – je to deník měření, jen přesun |
| `extrakce.md` | aktualizovat: stav k 29. 9., popisuje i kroky 3b–5 staré cesty |
| `extrakce_kontroly.md` | aktualizovat podle `[R4]` |
| `stavy.md` | aktualizovat: odkazuje na `data/leciva` a `pipeline.py --stav` |
| `hledej.md`, `gui.md`, `vek_pacienta.md`, `scenare.md` | aktuální (měněno 6. 10.), jen projít odkazy na staré skripty |
| `batchOpenAI.md` + `sledovaniBatchOpenAI.md` | sloučit do jednoho, opravit cestu ke klíči |
| `pristupy.md` | aktualizovat (klíč, Ollama) |
| `prezentace.md` | **zastaralá** (25. 8., 32 léků, qwen) `[R12]` přepsat na korpus, nebo smazat a vystačit si se `scenare.md`? |
| `zadani.md` (67 kB, 4. 9.) | původní zadání + výběr 32 léků; `[R13]` smazat, nebo nechat jako archiv? |
| `tentoTyden.md` | **smazat** – plán od 2. 10., zbytek přenést do `todo.md` |
| `codex_pripominky.md` | **smazat** – jednorázová odpověď Codexu ke konverzi |
| `audit_hledani.md` | viz `[R5]` |
| `agents.md` | pokyny pro Codex `[R14]` používáš ho ještě? Když ano, musí zůstat v kořeni |

---

## 8. Dokumenty do `docs/` s předponami

| dnes | návrh |
|---|---|
| `CLAUDE.md` | zůstává v kořeni (jinak se nenačte) |
| `poznatky.md` | `docs/denik_poznatky.md` |
| `aktualnistav.md` | `docs/denik_stav.md` |
| `todo.md` | `docs/denik_todo.md` |
| `skripty.md` | `docs/pipeline_prehled.md` |
| `extrakce.md` | `docs/pipeline_extrakce.md` |
| `extrakce_kontroly.md` | `docs/pipeline_kontroly.md` |
| `stavy.md` | `docs/pipeline_stavy.md` |
| `batchOpenAI.md` + `sledovaniBatchOpenAI.md` | `docs/pipeline_batch_openai.md` |
| `hledej.md` | `docs/hledani_jak_funguje.md` |
| `vek_pacienta.md` | `docs/hledani_vek.md` |
| `gui.md` | `docs/hledani_gui_api.md` |
| `scenare.md` | `docs/prezentace_scenare.md` |
| `prezentace.md` | `docs/prezentace_vyklad.md` (podle `[R12]`) |
| `pristupy.md` | `docs/provoz_pristupy.md` |

- [ ] Přesun přes `git mv` (zachová historii), pak hromadně opravit odkazy
      mezi dokumenty a v komentářích kódu (`poznatky.md` je zmíněné v desítkách
      docstringů).
- [ ] `CLAUDE.md`: tabulka „Dokumentace" a oddíl „Zápisky" na nové cesty.

---

## Pořadí provedení

0 → 1 (mazání skriptů a benchmarků) → 3 → 2 (nový seznam kroků, vyházet
starou cestu z kódu) → 1c → 5 → 6 → 4 (přejmenování) → 7 → 8.
Po krocích 2 a 4 pustit `evaluate.py --korpus` a jedno hledání přes API.
