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

- [ ] `[R6]` `evaluate.py`: testy 1–4 a `vzorek_eval.json` stojí na 32
      lécích a nad korpusem dávají nesmysly (test 0 hlásí samé CHYBA).
      Návrh: nechat jen test 0 (přepsaný na SPC) + testy 5–6 (`--korpus`
      jako výchozí), testy 1–4 a `vzorek_eval.json` smazat.

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

- [ ] Napsat nový seznam kroků (nahradí `pipeline.py`): `--vse`, `--od`,
      `--jen`, `--stav` přes všech 7 kroků; krok 3 je asynchronní (dávka až
      24 h) – seznam musí umět „čekám / navázat".
- [ ] `[R7]` Krok 1 dělá čtyři věci v jednom skriptu (42 kB). Pro přehled
      v seznamu stačí jeden krok; rozdělení na „seznam / stažení / převod"
      je samostatná práce – teď ne?
- [ ] Vyházet starou cestu ze živých skriptů:
      `naplni_db.py` (režim bez `--korpus`, `--kody`, `--znovu`, generovaný slovník pojmů),
      `extrahuj_sekce.py` (`--vse`, `--kody` nad `data/leciva`),
      `api.py`, `hledej.py`, `common/hledani.py` (záložní cesta k PDF v `data/leciva`),
      `common/config.py` (`LECIVA_DIR`, `adresar_leciva`, `MODEL_SEKCE`, `MODEL_EXTRAKCE`…),
      `common/sukl_api.py` (`postav_pool`).
- [ ] Zapsat do `skripty.md`, co seznam znamená pro měsíční job (služby,
      stav po dokumentu, co je asynchronní).

---

## 3. Platné benchmarky → `benchmarky/<téma>/`

| odkud | kam | poznámka |
|---|---|---|
| `bench_router.py` + `bench_router.json` | `benchmarky/router/` | volba modelu routeru; přeměří se při změně modelu |
| `benchmark/docling_serve/` (celé, dnes ignorované gitem) | `benchmarky/docling_serve/` | Docling Serve na DGX vs. notebook; skript a README do gitu, `vysledky/` ignorovat |
| `benchmarky/extrakce_cloud/`, `indikace_fragmenty/`, `pdfextrakce/` | zůstávají | – |

- [ ] Přesunout, opravit cesty/importy ve skriptech, pustit `--help` každého.
- [ ] `.gitignore`: zrušit `/benchmark/`, výstupy benchmarků řeší pravidla
      `benchmarky/**`.

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

| co | velikost | poznámka |
|---|---|---|
| `data/leciva/` | 16 MB, 32 léčiv | až po bodu 2 (živé skripty na ni dnes odkazují) a bodu 1c |
| `data/_zaloha_dlouhe_leky/` | 5,6 MB | záloha ze srpna |
| `data/bench_embed_cloud.json` | 13 MB | s bodem 1b |
| `legacy/data/pdf/` | – | s bodem 6 |
| `logs/` (srpen–září) | – | `[R9]` smazat staré, nechat od 30. 9.? |
| `benchmarky/pdfextrakce/{pdf,vystupy,report}` | ~70 MB | mimo git, skript si je vyrobí; smazat? |

V DB stará data nejsou (`naplni_db.py --korpus` udělal TRUNCATE 30. 9.).
`data/` není v gitu → **smazání nejde vrátit**, před každým mazáním potvrdit.

---

## 6. Smazat `legacy/`

- [ ] Až po bodu 0 (klíč). 42 souborů v gitu (dema 01–12, vlastní
      `common/`, compose) + `key.yaml`, `dalibor.py`, `data/` mimo git.
- [ ] Opravit odkazy: `CLAUDE.md` (odstavec o `legacy/`, „Peníze"),
      `pristupy.md`, `batchOpenAI.md`, komentář v `docker-compose.yml`,
      `.gitignore` (`dalibor.py`).
- [ ] `[R10]` Docker volumes `legacy_pgdata`, `legacy_pgadmin_data` – smazat taky?

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
