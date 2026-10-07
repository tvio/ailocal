# Jak funguje extrakce do JSON — stav k 6. 10. 2026

Popisuje, co se **opravdu** děje. Zmapováno z kódu 29. 9., kapitoly 1, 3.1,
3.4 a 5 přepsány 6. 10. po úklidu: extrakce jede v cloudu (gpt-6-luna,
Batch API) nad celým korpusem `data/spc/`, stará cesta nad 32 léky
(`data/leciva/`, qwen) je smazaná.

> **Kontroly extrakce NEBĚŽÍ** (`config.KONTROLY_ZAPNUTE = False`,
> skripty v `nerealizovane_kontroly/`). Všechny sekce korpusu jsou ve stavu
> `neovereno`. Co kontroly dělaly a co chybí:
> **`nerealizovane_kontroly/kontroly_popis.md`**. Kapitola 5 je popisuje
> jako návrh pro případ, že se k nim někdo vrátí.

Obsah:

1. [Celý řetěz na jedné obrazovce](#1-celý-řetěz-na-jedné-obrazovce)
2. [Vstup: odkud se bere text sekce](#2-vstup-odkud-se-bere-text-sekce)
3. [Krok 3 – extrakce modelem, podrobně](#3-krok-3--extrakce-modelem-podrobně)
4. [Laický tvar a klíč – kdo je vyrábí a kdo je ověřuje](#4-laický-tvar-a-klíč--kdo-je-vyrábí-a-kdo-je-ověřuje)
5. [Navazující kroky 3b až 12](#5-navazující-kroky-3b-až-12)
6. [Jedna položka od PDF po databázi (příklad)](#6-jedna-položka-od-pdf-po-databázi-příklad)
7. [Nálezy – co z toho plyne pro korpus a cloud](#7-nálezy--co-z-toho-plyne-pro-korpus-a-cloud)

---

## 1. Celý řetěz na jedné obrazovce

Seznam kroků je `extrakce_all.py` (`KROKY`), přehled skriptů
`docs/pipeline_prehled.md`.

```
 API SÚKL, EMA
   │  extrakce_1_konverze.py   seznam léčiv, inventář SPC, stažení, Docling Serve (DGX)
   ▼                           → spc.pdf, spc.md, strany.json, kontrola.json
 data/spc/<identita>/
   │  extrakce_2_sekce.py      regexy, BEZ modelu → sekce/<sekce>.md (+ _orez.md k nahlédnutí)
   ▼
 sekce/indikace.md, davkovani.md, kontraindikace.md, nezadouci_ucinky.md
   │  extrakce_3_json.py       ořez na jádro → PROMPT → gpt-6-luna (Batch) → dopočty
   │                           JEDNÍM voláním vznikne doslovné + laické + klíč
   │                           (--local: totéž přes Ollamu, jeden lék / malá dávka)
   ▼
 json/<sekce>.json + json/_stav.json            stav „neovereno"
   │  extrakce_4_db.py --korpus   Postgres: leciva, extrakty, extrakce_stav, leciva_search
   │                              + věk použití (vek_od, pro_deti, jen_deti) bez modelu
   │  extrakce_5_embeddingy.py    bge-m3, dva vektory na řádek (text + klíč)
   │  extrakce_6_rejstrik.py      data/leky – složka SPC podle názvu a kódu
   │  hledani_evaluace.py
   ▼
 hledání
```

**Důležité pro orientaci:**

- Model se v řetězu volá na **jednom** místě: extrakce (luna). Normalizace
  na číselníky (frekvence, MedDRA, skupina pacientů, ruční číselník pojmů)
  jsou deterministické a dělají se hned při zápisu JSON.
- **Mezi extrakcí a DB není žádná kontrola.** Dřívější kroky 3b, 4a, 4b, 5
  a 8b (kap. 5) nad korpusem neexistují.
- Extrakty a hledací řádky se nahrávají jednou za SPC, u zástupce
  (nejmenší kód SÚKL).

---

## 2. Vstup: odkud se bere text sekce

Tohle už je hotové i pro celý korpus. Pro pochopení extrakce je ale
potřeba vědět, co přesně model dostane.

**Soubor:** `data/spc/<identita>/sekce/<sekce>.md` . Vyrábí ho `extrakce_2_sekce.py`
přes `common/sekce.py: vytahni_vsechny()`.

### Hledání sekce

Sekce se hledá podle čísla bodu SPC (4.1 indikace, 4.2 dávkování,
4.3 kontraindikace, 4.8 nežádoucí účinky) a končí na nadpisu dalšího
bodu (4.2, 4.3, 4.4, 4.9). Regex snese:

- záměny číslic z OCR („4.l" místo „4.1"),
- mezeru kolem tečky („4. 8."),
- slepený nadpis („## 4. KLINICKÉ ÚDAJE4.1 …"), ale jen jako záložní vzor.

Když se konec nenajde, vezme se 40 000 znaků od začátku sekce.

### Ze kterého převodu

| sekce | zdroj textu | proč |
|---|---|---|
| 4.1, 4.3 | **vždy Docling markdown** | drží nadpisy skupin pacientů („## Dospělí"); frekvence tu nejsou, takže riziko záměny nehrozí |
| 4.2, 4.8 **s tabulkou** | Docling markdown | tabulku umí jen Docling |
| 4.2, 4.8 **bez tabulky** | surový text PDF (PyMuPDF) | Docling u formátu „frekvence na vlastním řádku" slepuje hodnoty a účinek skončí u špatné frekvence |

V korpusu je to 17 856 sekcí z Doclingu a 5 641 ze surového textu.
Nenašlo se 23 sekcí. Tenhle poměr je regresní test: když se skokem
změní, něco se rozbilo.

### Opravy vad zdrojového PDF (před uložením, bez modelu)

Týkají se obou zdrojů:

1. `sprav_mezerovani` – „zp ů sob" → „způsob",
2. `slep_rozdelena_slova` – slepí rozdělená slova proti slovníku
   postavenému z **celého** dokumentu,
3. `sceluj_frekvence` – „V zácné" → „Vzácné". Kvůli DITHIADENU, kde si
   model „V zácné" doplnil na „velmi vzácné" a riziko tím podhodnotil
   desetkrát.

### Velikost vstupu v korpusu (po ořezu, znaky)

| sekce | sekcí | součet | medián | 95 % pod | max |
|---|---|---|---|---|---|
| indikace | 5 867 | 3,4 mil. | 380 | 1 507 | 40 980 |
| kontraindikace | 5 877 | 3,1 mil. | 343 | 1 608 | 16 145 |
| dávkování | 5 875 | 18,6 mil. | 1 524 | 10 834 | 124 241 |
| nežádoucí účinky | 5 878 | **42,5 mil.** | 5 063 | 21 541 | 82 723 |

Celkem ~68 mil. znaků. **Dvě třetiny vstupu tvoří sekce 4.8.** Tokeny
nejsou změřené (úkol v `todo.md` bod 3).

⚠ Čísla ořezu jsou z `_prehled.json`. Ořez sekcí 4.1 a 4.3 tam
znaky nesníží (jen přeformátuje), viz níže.

---

## 3. Krok 3 – extrakce modelem, podrobně

Dva soubory:

- `extrakce_3_json.py` – fronta požadavků (SPC × sekce), odeslání, stav, report,
- `common/extrakce.py` – prompty, tělo požadavku a všechno kolem odpovědi.

### 3.1 `extrakce_3_json.py` – runner

```
uv run python extrakce_3_json.py --beh                    # cloud, Batch API, naváže sám
uv run python extrakce_3_json.py --stav                   # souhrn + report.md
uv run python extrakce_3_json.py --znovu-chybne --beh     # chyby zpět do fronty
uv run python extrakce_3_json.py --local --kody 0260480   # lokálně přes Ollamu, jeden lék
```

Stav je v `data/spc/_extrakce/stav.sqlite`, 1 řádek = 1 SPC × 1 sekce:
`cekajici` → `odeslano` → `hotovo` | `chyba`; `bez_sekce` = sekce v SPC není.

1. **Inventář:** pro každé SPC z inventáře konverze a každou ze 4 sekcí
   založí požadavek. Když chybí `sekce/<sekce>.md` → `bez_sekce`, do
   `_stav.json` jde `chybi_v_dokumentu`, nic se neposílá.
2. **Cloud (`--beh`):** požadavky se balí do dávek JSONL (každý řádek nese
   celý vlastní prompt), plní se podle limitu tokenů ve frontě OpenAI,
   dávka dobíhá až 24 h. Před startem se ověří klíč (`key.yaml`) a hlídá
   se rozpočtový strop `config.CLOUD_STROP_USD`. Popis API:
   `docs/pipeline_batch_openai.md`.
3. **Lokálně (`--local`):** stejná fronta, jedna sekce po druhé přes
   Ollamu (`--model`, výchozí `config.MODEL_HLAVNI`); jen `--kody` nebo
   `--limit` požadavků.
4. **Zápis výsledku** je pro obě cesty jedna funkce (`uloz_vysledek`):
   když jsou položky → `json/<sekce>.json`; **prázdný výsledek soubor
   nezapíše**. Do `_stav.json` jde `{stav, duvod, polozek, model, tokeny}`,
   u lokální cesty navíc `zpusob: local`.
5. **Opakování:** chybný požadavek jde do fronty znovu (nejvýš 3 pokusy):
   2. pokus s teplotou 0,4 bez seedu, 3. pokus s vynuceným JSON schématem.
   U dávkování je schéma vždy (model se bez něj cyklil ve ~3 %).
6. `report.md` vypíše všechny chyby podle ID.

### 3.2 Předzpracování textu – `orizni_na_jadro()`

Volá se uvnitř `extrahuj_sekci()` (`orezat=True`). Soubor `_orez.md` na
disku je **jen k nahlédnutí**. Ořez se při extrakci počítá znovu
z plné sekce a stejně tak ho znovu počítají obě kontroly.

Ořez je **záměrná ztráta informace** a nesmí se použít na nic, co vidí
uživatel.

**4.2 dávkování – jen základní dávkování**

Hledají se podnadpisy, za kterými začínají zvláštní populace: „Starší",
„Pediatr…", „Děti", „Porucha funkce ledvin/jater", „Způsob podání"…
Z kandidátních řezů se vybere:

1. nejkratší řez, ve kterém **zůstala konkrétní dávka** (číslo + mg/ml/
   tablet/…) **a zároveň tabulka**, pokud v sekci nějaká je;
2. jinak nejkratší řez, který udrží tabulku; když ji neudrží žádný,
   neřeže se vůbec;
3. jinak (topické přípravky, dávka jen slovy) první řez delší než 250
   znaků;
4. jinak celá sekce.

Pozor: dětské dávkování se tím **ztrácí záměrně**. Položka dávkování
pro děti vznikne jen tehdy, když je před prvním řezným nadpisem.

**4.8 nežádoucí účinky – jen tabulka nebo seznam**

- Konec jádra je první podnadpis „Popis vybraných…", „Hlášení podezření",
  „Pediatr…", „Další informace", „Dlouhodobé užívání", „Zvláštní
  populace", „Starší".
- Začátek je první řádek, který vypadá jako struktura: tabulka (`|`),
  nadpis (`#`) nebo řádek „Časté:". Úvodní próza (definice frekvencí,
  popis studií) se zahodí.
- Když je první strukturou řádek s frekvencí, ořez se vrátí o řádek
  výš na nadpis orgánového systému. Jinak by první účinky přišly
  o orgánový systém.
- Boilerplate „Hlášení podezření na nežádoucí účinky…" se odstraní vždy.

**4.1 a 4.3 indikace a kontraindikace – nic se neubírá, jen přeformátuje**

1. `rozpad_vyctu`: **středníky → nové řádky.** DITHIADEN: se středníky
   4 položky, po rozpadu 9. Čárky se nedělí, protože uvnitř jedné
   indikace jsou běžné.
2. `oznac_skupiny`: pod nadpisem skupiny pacientů („## Dospělí",
   „## Pediatrické použití") se každému řádku předřadí `[Dospělí] `.
   Upřesnění na vlastním řádku („Děti od 1 roku a s hmotností ≥ 10 kg")
   skupinu zpřesní. Jiný nadpis skupinu zruší. OMEPRAZOL: bez toho model
   označil jako „dospělí" jen 1 indikaci z 11.

### 3.3 Prompt

Zpráva do modelu má dvě části:

- **system** (`SYSTEM_PROMPT`, společný pro všechny sekce): „strukturovaná
  extrakce z SPC … laický tvar bez latiny … nic si nevymýšlej … vrať
  POUZE validní JSON". Ollama klient před něj přidá `/nothink`.
- **user** = `PROMPTY[sekce]` + `--- TEXT SEKCE ---` + ořezaný text +
  `--- KONEC ---`.

Co se po modelu chce v jednotlivých sekcích:

| sekce | pole položky | povinná | poznámky z promptu |
|---|---|---|---|
| indikace | `doslovne`, `laicky`, `klic`, `skupina` | doslovne, laicky | doslovně i s odborným termínem; laicky bez latiny; **klíč 1–4 slova, 1. pád, drž se slov ze zdroje**, vynech „léčba, prevence…", bez stavu klíč vynech; každou indikaci zvlášť; **nepatří sem** síla pro věkovou skupinu, nadpisy skupin, „bez porady s lékařem" |
| kontraindikace | `doslovne`, `laicky`, `klic` | doslovne, laicky | totéž + „POZOR na věkové hranice – ‚děti do 2 let' = mladší než 2 roky" |
| dávkování | `pacient`, `davka`, `frekvence`, `poznamka` | pacient, davka | jedna položka na skupinu pacientů; **žádný laický tvar ani klíč** |
| nežádoucí účinky | `ucinek`, `ucinek_laicky`, `frekvence`, `organovy_system` | ucinek, ucinek_laicky, frekvence | účinek doslovně, víc účinků na řádku = víc položek, pojem ne věta, bez hvězdiček; frekvence jedna ze 6 hodnot; SOC doslovně; **popis 5 formátů tabulek** (`POPIS_FORMATU`); projdi text až do konce; **žádný klíč** |

**Laický tvar i klíč tedy vznikají v TOMTÉŽ volání jako doslovná
extrakce.** Samostatný krok „zjednodušení" v kódu není.

### 3.4 Volání modelu

**Cloud** – tělo požadavku staví `extrakce.telo_cloud()`, stejné pro sync
i Batch:

| parametr | hodnota | dopad |
|---|---|---|
| model | `gpt-6-luna` (`config.OPENAI_MODEL`), jiný funkce odmítne | peníze |
| `reasoning_effort` | `"none"` | bez toho 4–21× dražší, kvalita stejná |
| `temperature`, `seed` | 0 a 42; při opakování 0,4 bez seedu | deterministický první pokus |
| `response_format` | `json_object`; u dávkování a od 3. pokusu JSON schéma (strict) | proti vynechanému klíči a zacyklení |
| `max_completion_tokens` | 40 000 | strop proti zacyklení (nejdelší legitimní výstup měl 29 860) |

**Lokálně** (`--local`) – `ollama_client.chat()`:

| parametr | hodnota | dopad |
|---|---|---|
| endpoint | `POST /api/chat`, stroj vybere `ollama_client.vyber_uzel()` ze `config.OLLAMA_UZLY` | při výpadku zkusí další stroj |
| `format` | `"json"` | JSON vynucen, schéma ne; qwen občas vrátí ```` ```json ```` ohrádku |
| `think` | `false` + `/nothink` v system promptu | vypnuté uvažování |
| `temperature`, `seed`, `num_predict` | 0, 42, 40 000 (od 6. 10.) | jako cloud, kde to jde |
| `keep_alive` | `2h` | model se neodloží z paměti |
| `num_ctx` | nenastavuje se, platí serverové `OLLAMA_CONTEXT_LENGTH` | nejít pod 16 384, Ollama delší prompt tiše usekne |

### 3.5 Zpracování odpovědi – `_jeden_pokus()`

V tomhle pořadí:

1. **Výjimka při volání** (timeout, spojení) → `selhala_extrakce`.
2. **Sundání markdownové ohrádky** a `json.loads`. Nevalidní JSON →
   `selhala_extrakce` + surová odpověď.
3. **Najít pole položek:** `data[sekce]`; když model pole pojmenoval
   jinak a v objektu je jediný klíč, vezme se ten.
   Není to seznam → `selhala_extrakce`. Prázdný seznam → `prazdna`.
4. **Oprava překlepů v názvech klíčů** (`_oprav_klice`, difflib,
   podobnost ≥ 0,7): „ucinker" → „ucinek". Kvůli jednomu takovému
   překlepu padlo dřív 6 položek z 18.
5. **Povinné klíče:** položky bez nich se zahodí.
   Nezbyla žádná → `selhala_extrakce`. Zbyla část → `castecna` +
   důvod „N z M položek zahozeno".
6. Jinak stav **`neovereno`**, tedy „extrahováno, nikdo neověřil".

**Opakování** (`pokusy=2`): druhý pokus se pustí, jen když první skončil
prázdně nebo chybou. Výsledek `castecna` se bere hned a neopakuje se.
Když uspěje až druhý pokus, důvod dostane „(uspělo až na 2. pokus)".

### 3.6 Deterministické dopočty po odpovědi

Všechno bez modelu, v tomhle pořadí:

| # | co | sekce | detail |
|---|---|---|---|
| 1 | **skupina pacientů** | indikace | `normalizuj_skupinu()` → text doslovně + kód pro filtr (`deti`, `dospeli`, `kojenci`, …, `jine`). Chybějící skupina se zapíše jako „není uvedeno"/`neuvedeno`, nikdy NULL |
| 2 | **opora klíče** | indikace, kontraindikace | `klic_ma_oporu(klic, laicky or doslovne)`: aspoň polovina významových slov klíče (delších než 2 znaky, mimo „léčba", „prevence", předložky) musí mít shodné **první 4 písmena** se slovem zdroje. Bez opory → `klic = null`. ⚠ **Zdrojem je `laicky`**, viz kapitola 4 |
| 3 | **frekvence** | NÚ | `normalizuj_frekvenci()`: pryč závorky „(≥1/100…)" a diakritika → číselník 6 hodnot + rank 1–5/9. Synonyma („ojediněle", „zřídka" → **není známo**, záměrně, nehádá se). Překlepy přes difflib ≥ 0,75. Neznámá hodnota zůstane a dostane rank 9 |
| 4 | **orgánový systém** | NÚ | `meddra.normalizuj_soc()`: 26 kanonických SOC; ořez „*", „(viz bod 4.3)"; porovnání bez mezer a diakritiky, jinak podobnost ≥ 0,85 (pak `organovy_system_opraveno: true`) |
| 5 | **laický tvar ze slovníku** | indikace, kontraindikace, NÚ | `slovnik.uplatni()`: když je odborný termín (normalizovaný: malá písmena, bez „léčba "/„při ", bez koncové interpunkce) ve `slovnik_pojmu.json` nebo `slovnik_rucni.json`, **laický tvar od modelu se zahodí** a nahradí se tvarem ze slovníku (`laicky_ze_slovniku: true`). Ruční slovník přebíjí generovaný |

Slovník se načte jednou na běh (cache v paměti). Ve slovníku je dnes
593 dvojic, z toho 70 ručních.

### 3.7 Stavy sekce (`_stav.json` → tabulka `extrakce_stav`)

| stav | kdo ho nastaví | význam |
|---|---|---|
| `neovereno` | extrakce | model vrátil použitelná data, nikdo je neověřil |
| `castecna` | extrakce | část položek zahozena kvůli chybějícím klíčům |
| `prazdna` | extrakce | sekce je (skoro) prázdná, nebo model vrátil `[]` i napodruhé |
| `selhala_extrakce` | extrakce | výjimka / nevalidní JSON / špatný tvar |
| `chybi_v_dokumentu` | extrakce | sekce v SPC nenalezena |
| `ok` | kontrola 4a nebo 4b | všechno ověřeno |
| `zamitnuto_kontrolou` | kontrola 4b | model označil aspoň jednu položku (indexy se uloží) |

Pravidlo: stav je vždycky vyplněný, nikdy NULL. Pro laika se musí
rozlišit „lék nemá nežádoucí účinky" od „extrakce selhala".

Stav 32 léčiv dnes: `ok` 118, `zamitnuto_kontrolou` 9, `castecna` 1.

---

## 4. Laický tvar a klíč – kdo je vyrábí a kdo je ověřuje

Tohle je jádro úkolu 2 v `todo.md`, proto samostatně.

### Kdo je vyrábí

| pole | sekce | vyrábí | kdy se může přepsat |
|---|---|---|---|
| `laicky` / `ucinek_laicky` | ind., kontraind., NÚ | qwen, **v témže volání jako extrakce** | slovník (krok 3.6 #5 a znovu `ocisti_json.py`); `rozdel_vycty.py` (qwen napíše nový) |
| `klic` | ind., kontraind. | qwen, v témže volání | zahodí se bez opory (3.6 #2); `ocisti_json.py` ho sjednotí mezi položkami se stejným laickým textem |
| klíč dávkování | dávkování | není z modelu – `extrakce_4_db.py` použije `pacient` | – |
| klíč NÚ | NÚ | **nevzniká vůbec** | – |

### Co je dnes ověřuje

| kontrola | `doslovne` / `ucinek` | `laicky` | `klic` |
|---|---|---|---|
| deterministická (`zkontroluj_json.py`) | ✅ podřetězec zdroje po normalizaci | ❌ výslovně vynecháno | ❌ |
| opora klíče (`klic_ma_oporu`) | – | – | ⚠ jen proti **laickému** tvaru, jen polovina slov, jen první 4 písmena |
| modelem (`zkontroluj_modelem.py`) | ✅ jen u sekcí, které **nejsou `ok`** | ❌ prompt výslovně říká, že zjednodušení **není** chyba | ❌ |
| slovník (`postav_slovnik.py --zkontroluj`) | – | ✅ gemma, ale **jen kanonický tvar termínu**, ne každá položka; u ind./kontraind. **jen termíny do 3 slov** | ❌ |
| cizí písmo (`NELATINKA`) | ✅ | ✅ (azbuka, CJK v jakémkoli poli) | ✅ |

**Důsledky:**

1. **Dlouhé laické indikace a kontraindikace neověřuje nic.** Víceslovný
   termín se do slovníku nedostane, deterministická kontrola laický tvar
   vynechává a modelová kontrola ho toleruje. Přesně tudy prošel „náhlý
   záškrt" (za „akutní průjem").
2. **Opora klíče se opírá o výstup téhož modelu.** Zdroj pro
   `klic_ma_oporu` je `laicky`, na `doslovne` se sáhne, jen když laický
   tvar chybí. Když model napíše nesmyslný laický tvar a klíč z něj, klíč
   „má oporu". Navíc se opora ověřuje **před** přepsáním laického tvaru
   slovníkem, takže klíč může mít oporu v textu, který se vzápětí zahodí.
3. **Délka klíče 1–4 slova, 1. pád a obecná slova („onemocnění") se
   nevynucují.** Je to jen v promptu.
4. **Vazba účinek → frekvence se v sekcích se stavem `ok` neověřuje.**
   Deterministická kontrola u frekvence zjišťuje jen, jestli se slovo
   („časté") vyskytuje **někde** v sekci, a to se vyskytuje skoro vždycky.
   Sekce, kde všechny účinky doslovně sedí, dostane `ok`, a modelová
   kontrola, která by vazbu posoudila, ji pak přeskočí.

---

## 5. Navazující kroky

**Dnes za extrakcí běží jen kroky 4 a 5 pipeline** (`extrakce_4_db.py`,
`extrakce_5_embeddingy.py`) – popsané na konci kapitoly.

Podkapitoly 3b, 4a, 4b, 5 a 8b popisují kroky **staré cesty nad 32 léky**.
Nad korpusem neběží: skripty 3b–5 jsou v `nerealizovane_kontroly/`,
`rozdel_vycty.py` je smazaný (dělení výčtů dělá prompt indikací). Zůstávají
tu jako popis toho, co kontroly dělaly; přepisovaly `json/*.json`
a `_stav.json` na místě.

### 3b `ocisti_json.py` — bez modelu

```
uv run python ocisti_json.py            # jen ukáže změny
uv run python ocisti_json.py --zapis
```

1. NÚ: znovu `normalizuj_frekvenci` + `normalizuj_soc`. Vypíše SOC, které
   nesedí na žádný kanonický.
2. Všechny tři sekce s laickým tvarem: znovu `slovnik.uplatni()`. Tak se
   ruční oprava ve slovníku propíše **bez přeextrahování**.
3. **Deduplikace:** zahodí úplně shodné objekty (porovnává se celý objekt,
   protože ACC má 9 indikací × 3 skupiny a to duplicity nejsou).
4. **Sjednocení klíče:** když má tentýž laický text u víc položek různé
   klíče, všude se použije nejčastější (při shodě nejkratší).

Proč samostatný skript: přeextrahování chyby neopraví, jen je přesune.
Čištění je deterministické, zadarmo a dá se opakovat.

### 4a `zkontroluj_json.py` — bez modelu

```
uv run python zkontroluj_json.py --zapis [--detail]
```

Pro každou sekci znovu spočítá ořez z plné sekce a znormalizuje ho
(malá písmena, bez diakritiky, **bez mezer a interpunkce**). Pak ověří:

| sekce | pole | test |
|---|---|---|
| NÚ | `ucinek`, `organovy_system`, `frekvence` | normalizovaná hodnota je podřetězec normalizovaného zdroje |
| indikace, kontraindikace | `doslovne` | totéž |
| dávkování | `davka` | **jen čísla**: každé číslo z dávky musí být ve zdroji. U zdroje se bere obojí čtení „1 000" (1000 i 1 a 000), protože mezera v PDF je nejednoznačná |
| všechny | jakékoli pole | žádná azbuka ani CJK (ADVANTAN měl „mеsta" s cyrilským е) |

Hodnoty kratší než 4 znaky se nekontrolují (našly by se náhodou).

Výsledek jde do `_stav.json[sekce].kontrola`. **Když nesedí nic,
`neovereno` → `ok`.** Jinak stav zůstane `neovereno` a sekce jde do 4b.

### 4b `zkontroluj_modelem.py` — gemma4:26b

```
uv run python zkontroluj_modelem.py --vse --zapis [--model gpt-6-luna]
```

- Vezme každou sekci, která **není `ok`** (tedy i `castecna`
  a `zamitnuto_kontrolou` z minula).
- Prompt: ořezaný zdroj + očíslované položky jako JSON. Otázka: „má
  položka oporu ve zdroji?" Za chybu se počítá vymyšlená položka, jiná
  frekvence, jiný SOC nebo věcně jiný obsah. **Za chybu se nepočítá
  zjednodušení, zkrácení ani překlad termínu.**
- Odpověď: `{"chybne": [{"i": index, "proc": "…"}]}`. Neplatné indexy se
  zahodí a spočítají (signál, že kontrole nelze věřit).
- `--zapis`: `kontrola_modelem = {model, oznaceno, chybne_indexy, duvody}`.
  0 označených → `ok`, jinak → `zamitnuto_kontrolou`.
- Proč jiný model: model si neodsouhlasí vlastní chybu. **Na gemma4:26b
  se kontrola neměřila**, převzala se 24. 9. podle výsledků routeru.
- Umí i cloud (`--model gpt-…`, s `reasoning_effort` jen pro model z configu).

### 5 `postav_slovnik.py` — gemma4:26b volitelně

```
uv run python postav_slovnik.py --zkontroluj --zapis
```

1. Posbírá dvojice (odborný termín → laický tvar) ze všech NÚ a z indikací
   a kontraindikací **do 3 slov** (delší jsou věty, na které se slovník
   stejně nikdy netrefí).
2. Kanonický tvar = nejčastější, při shodě kratší. Ruční přepis vyhrává.
3. `--zkontroluj`: gemma v dávkách po 20 dvojicích („odpovídá laický tvar
   věcně termínu?"). Ruční dvojice se nekontrolují.
4. `--zapis`: `slovnik_pojmu.json` (generovaný, **přepíše se celý**)
   + `slovnik_pojmu.md` (k ručnímu projití, označené nahoře).

**Zpětná vazba:** slovník vzniká z extrakce a zároveň ji řídí. Při
**dalším** běhu extrakce (nebo `ocisti_json.py`) přebije model. Ručně
opravený termín se tak projeví všude a přežije přeextrahování.

Ruční opravy patří do `slovnik_rucni.json`, jinak je příští
`postav_slovnik.py` přepíše.

### 8b `rozdel_vycty.py` — qwen3.5:122b, mimo `pipeline.py`

```
uv run python rozdel_vycty.py [--zapis]
```

- Kandidáti: indikace/kontraindikace, jejichž **laický** tvar odpovídá
  úzkému regexu „…, jako jsou / např. / zejména / včetně …".
- qwen rozhodne, jestli jde o víc samostatných stavů. Když ano, vrátí
  díly `{doslovne, laicky}` v 1. pádě.
- `--zapis`: původní položka se nahradí díly (kopie objektu, takže zůstane
  skupina a ostatní pole; přibude `rozdeleno_z_vyctu: true`).
- **Výstup se nekontroluje.** `doslovne` v dílech napsal model, takže už
  doslovné není. Klíč zůstane z původní položky, tedy u všech dílů stejný.
- V korpusu 32 léčiv: 3 položky → 15.

### Krok 4 `extrakce_4_db.py` — bez modelu

```
uv run python extrakce_4_db.py --korpus               # vše od nuly (~40 min)
uv run python extrakce_4_db.py --obnov-sekci indikace # jen jedna sekce
uv run python extrakce_4_db.py --jen-vek              # jen přepočet věku
```

- Čte `data/detaily_leciv/<kód>.json` (relační data) a mapu kód → SPC
  z `data/spc/_stav.sqlite`.
- `--korpus` = `TRUNCATE leciva CASCADE` (`vyprazdni_korpus()`); hledací
  slovník `slovnik_dotazu` nechá a pojistka to ověří.
- Plní tabulky:
  - `leciva`: 1 řádek na kód (sloupce `spc`, `zastupce`, věk),
  - `extrakty`: celý JSON sekce + plný i ořezaný zdroj – jen u zástupce,
  - `extrakce_stav`,
  - `leciva_search`: 1 řádek na položku + 1 řádek `atributy` na SPC.
- **Co jde do hledaného textu `obsah_text`:**
  - NÚ, indikace, kontraindikace: `laicky (odborne)`. Odborný tvar se
    připojí, jen když je kratší než 60 znaků, jinak by ředil vektor.
  - Dávkování: `pacient davka frekvence`.
  - Frekvence, SOC a sekce jdou do **samostatných sloupců jako filtry**,
    ne do textu.
- **Sekce `zamitnuto_kontrolou`:** vyřadí se jen položky na
  `chybne_indexy`. Starý záznam bez indexů vyřadí celou sekci.
  `--jen-ok` pustí jen stav `ok`.
- `strana_pdf` ze `strany.json` (první nadpis, který začíná číslem bodu).

### Krok 5 `extrakce_5_embeddingy.py` — bge-m3

Dva vektory na řádek: `embedding` z `obsah_text` a `embedding_klic`
z `klic` (jen když klíč je). Hledání bere lepší z obou. Na konci zkontroluje,
že žádný řádek nezůstal bez vektoru. Loguje do souboru i DB.

### Pořadí

Jediný zdroj pořadí je `extrakce_all.py` (`KROKY`): konverze → sekce →
extrakce → db → embeddingy → rejstřík → evaluace. Dřívější rozpor tří
zdrojů (nález N5) je tím vyřešený.

---

## 6. Jedna položka od PDF po databázi (příklad)

ACYLCOFFIN, sekce 4.1, z reálných dat:

```
SPC (Docling md):  „Bolesti mírné a střední intenzity různého původu, např. bolesti
                    hlavy, kloubů a svalů provázející chřipková onemocnění; bolesti
                    zubů; neuralgie; bolesti vertebrogenního původu; horečnaté stavy …"

ořez 4.1:           středníky → řádky
                    Bolesti mírné a střední intenzity … chřipková onemocnění
                    bolesti zubů
                    neuralgie
                    …

qwen (1 volání):    {"doslovne": "neuralgie", "laicky": <co model napíše>, "klic": <…>}

dopočty:            skupina → "není uvedeno"/neuvedeno
                    klíč → ověřen proti laickému tvaru, jinak null
                    slovník zná "neuralgie" → laicky = "bolest nervů", laicky_ze_slovniku

json/indikace.json: {"doslovne": "neuralgie", "laicky": "bolest nervů",
                     "skupina": "není uvedeno", "skupina_kod": "neuvedeno",
                     "laicky_ze_slovniku": true, "klic": null}

kontrola 4a:        "neuralgie" je ve zdroji → sekce bez neshody → stav ok
                    (laický tvar nikdo neověřuje, tady ho ale drží ruční slovník)

DB leciva_search:   obsah_text = "bolest nervů (neuralgie)", klic = NULL
                    embedding z obsah_text, embedding_klic = NULL
```

První položka téže sekce („Bolesti mírné a střední intenzity…, např.
bolesti hlavy, kloubů a svalů…") je kandidát pro `rozdel_vycty.py`
(„např."). Její laický tvar má 11 slov, takže do slovníku nepatří
a **neověřuje ho žádný krok**.

---

## 7. Nálezy – co z toho plyne pro korpus a cloud

Všechny nálezy jsou ověřené v kódu. Neznamenají, že je něco rozbité
na 32 léčivech (tam se to prošlo očima). Znamenají, že na 5 880 SPC
to nikdo očima neprojde.

**Stav k 6. 10.:** N5 (pořadí kroků) a N11 (extrakce do cloudu) jsou
vyřešené; části „pro úkol 3 a 4" popisují rozhodování z 29. 9. Nálezy ke
kontrolám laického tvaru a klíče (N1–N4, N8) **platí dál** – nad korpusem
je nic neověřuje.

### Pro úkol 2 (kontroly laického tvaru a klíče)

- **N1 – Laický tvar dlouhých indikací a kontraindikací neověřuje žádný
  krok** (kap. 4). Tohle je hlavní díra.
- **N2 – `klic_ma_oporu` ověřuje klíč proti `laicky`, ne proti
  `doslovne`**, a dřív, než slovník laický tvar přepíše. Stačí změnit
  zdroj opory na `doslovne` (případně obojí), ale **nejdřív změřit**:
  po 1. pádu a laickém přeložení může opora v odborném textu vycházet
  hůř (např. „průjem" proti „diarrhoea").
- **N3 – Délka klíče, 1. pád a zákaz obecných slov jsou jen v promptu.**
  Deterministicky jde vynutit délku a černou listinu („onemocnění",
  „potíže", „stav").
- **N4 – Vazba účinek → frekvence se v sekcích `ok` neověřuje.** Pro
  cloud je to podstatné, protože luna se na 4.8 zatím neměřila (úkol 3).

### Pro úkol 4 (nová podoba kroku v pipeline)

- **N5 – Posun indexů.** `chybne_indexy` z kontroly 4b jsou pozice
  v seznamu. `ocisti_json.py` (deduplikace) a `rozdel_vycty.py`
  (vkládání dílů) po kontrole seznam mění, a `extrakce_4_db.py` pak vyřadí
  **jiné** položky, než označila kontrola. Hrozí to při postupu z
  CLAUDE.md „po změně dat" (ocisti → naplni_db bez nové kontroly)
  a vždy u `rozdel_vycty.py`. Řešení: stabilní ID položky místo indexu,
  nebo kontrolu pouštět až po všech úpravách.
- **N6 – Navazování po pádu.** Hotovost se pozná jen podle existence
  `json/<sekce>.json`. `_stav.json` se zapisuje až po všech 4 sekcích
  léčiva. Pád uprostřed = JSON bez stavu a příští běh sekci přeskočí se
  stavem „?". Prázdný výsledek soubor nezapíše, takže se pokaždé zkouší
  znovu. Pro korpus: stav po sekci v SQLite jako u `extrakce_1_konverze.py`.
- **N7 – Nedeterminismus.** Nenastavuje se `temperature` ani `seed`.
  Lokálně lze dát `options={"temperature": 0}`. U luny je potřeba ověřit,
  co model podporuje. Opakovatelnost se dá změřit dvěma běhy nad týmž
  vzorkem.
- **N8 – Ořez se počítá třikrát** (extrakce, kontrola 4a, kontrola 4b)
  vždy z plné sekce. Když se `orizni_na_jadro()` mezi extrakcí
  a kontrolou změní, kontrola porovnává s jiným textem, než viděl model.
  Pro job: uložit ořez, který šel do modelu, a kontrolovat proti němu.
- **N9 – Verdikt kontroly konverze se nepoužívá.** `_prehled.json`
  nese `_konverze` (395 podezřelých SPC), ale extrakce ani DB ho nečtou.
  Rozhodnout, jestli podezřelá SPC extrahovat, označit, nebo odložit.
- **N10 – Adresy natvrdo:** Ollama v `ollama_client.KANDIDATI`, Postgres
  v `config.py`. Pro server patří do konfigurace.

### Pro úkol 3 (cloud)

- **N11 – Luna byla změřená na jiném úkolu, než jaký dnes dělá produkce.**
  `bench_zjednoduseni.py` dával modelům **hotové `doslovne`** a chtěl jen
  `laicky` + `klic`. Měl vlastní prompt, **bez diakritiky**, a dávkoval
  celou sekci najednou. Produkce dělá všechno jedním voláním z textu
  sekce. Dvě cesty:
  - **a) Rozdělit extrakci na dva kroky:** lokálně qwen vytáhne doslovné
    + frekvence + SOC (to je ověřitelné deterministicky), cloud (luna)
    udělá jen laický tvar + klíč. Přesně tohle bylo změřeno. Výhoda:
    do cloudu jde jen krátký text (desítky znaků na položku, ne
    42 mil. znaků sekcí 4.8). Nevýhoda: lokální extrakce zůstává
    a na 5 880 SPC trvá dlouho (kvůli ní vznikl nápad s cloudem).
  - **b) Celou extrakci do cloudu:** nutné změřit lunu na 4.8 (vazba
    účinek → frekvence proti značkám PDF) a spočítat tokeny. Vstup je
    ~68 mil. znaků, dvě třetiny z toho 4.8.
  
  **Tohle rozhodnutí určuje tvar úkolů 2–4, proto patří na začátek.**
- **N12 – Slovník z 32 léčiv bude přebíjet cloud na celém korpusu.**
  Je to žádoucí kvůli jednotnosti, ale chyba ve slovníku se rozšíří
  na tisíce léčiv. Před hromadným během projít `slovnik_pojmu.md`
  (hlavně neruční dvojice označené kontrolou).
