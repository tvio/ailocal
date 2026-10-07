# CLAUDE.md

Pokyny pro Claude Code. **Cílem je nemuset znovu odvozovat, co už je
změřené** — detaily jsou v `poznatky.md`, tady je jen mapa a miny.

---

## Co to je

**localsemantic** — sémantické vyhledávání v souhrnech údajů o přípravku
(SPC) ze SÚKL. Uživatel se ptá běžnou češtinou („mám reflux"), aplikace
najde odpověď v oficiálních dokumentech a ukáže odkaz na stranu PDF.

Cílová skupina jsou **laici**. Všechno běží lokálně.

Korpus = **všechna obchodovaná léčiva ČR (zářijové vydání SÚKL): 8 778 kódů
SÚKL = 5 880 unikátních SPC**, 472 844 hledacích řádků v `data/spc/`
a v Postgresu. CLI, REST API i webové GUI jsou hotové. Hledání běží
lokálně (router + embedding na DGX Sparku), **extrakce do JSON jde do
cloudu** (OpenAI Batch); lokální extrakce je jen volba pro jeden lék.

**Kde co je:** spustitelné skripty v kořeni (`extrakce_N_…` = kroky
pipeline, `hledani_…` = CLI, log, evaluace, `api.py`), sdílený kód
v `common/`, dokumentace v `docs/`, benchmarky v `benchmarky/`,
nedodělané kontroly v `nerealizovane_kontroly/`, GUI ve `static/`.

**CÍLOVÝ STAV:** celá pipeline jako jeden skript `extrakce_all.py`
spouštěný **cronem jednou měsíčně na serveru** – přírůstkově (nová /
změněná / zaniklá SPC), s navazováním po pádu, zámkem proti souběžnému
běhu, logem, monitoringem a rozpočtovou pojistkou pro cloud. Požadavky
jsou v `todo.md` nahoře. **Každý nový krok pipeline piš tak, aby do toho
zapadl:** opakovatelně spustitelný, se stavem po dokumentu a bez
natvrdo zadaných adres.

### Pipeline má JEDEN seznam kroků — žádné skripty „bokem"

Z kódu musí být vždy jasné, co se v pipeline dělá a v jakém pořadí,
**bez zpětného dohledávání.**

- **Seznam kroků = `extrakce_all.py` (`KROKY`)** – 7 kroků od API SÚKL
  po evaluaci (`--seznam`, `--stav`, `--vse`, `--od`, `--jen`).
  Mapa všech skriptů s popisem = **`docs/pipeline_prehled.md`**.
  Skripty se 6. 10. přejmenovaly (`extrakce_N_…`, `hledani_…`); v `poznatky.md`
  jsou pod původními jmény – převodní tabulka je ve `docs/pipeline_prehled.md` oddíl 6.
- **Nový produkční krok** se ve STEJNÉ změně zapíše do obou. Když
  nahrazuje starý krok, starý se tam označí jako nahrazený (nebo smaže).
- **Benchmarky a jednorázové analýzy patří do `benchmarky/<téma>/`**,
  ne do kořene projektu. Nové `bench_*.py` do kořene nezakládat.
  Nový benchmark zapiš do `benchmarky/README.md` i do oddílu
  „Benchmarky" níž; zastaralý smaž (závěr s čísly zůstává v `poznatky.md`).
- Diagnostické pomocníky zapsat do `docs/pipeline_prehled.md` (sekce F) s tím, kdy
  se pouštějí.

### Vždy mít přehled o CELÉ pipeline — hlavně při její optimalizaci

Než začneš měnit nebo zrychlovat kterýkoli krok, **ujasni si celou
řadu kroků od stažení po hotovou DB** (`docs/pipeline_prehled.md`)
a to, co tvoje změna znamená pro kroky před a za ní (formát výstupu,
úložiště, stav po dokumentu, závislost na službě).

Proč: z téhle práce vznikne **zadání pro produkční aplikaci**, která
bude data nahrávat jako **měsíční job na serveru**. Tam už se změny
nepůjdou dělat tak rychle jako na notebooku (nasazení, provozní
schvalování, jiné prostředí). Každá změna pipeline, kterou teď
uděláš bez přehledu o celku, se pak do zadání propíše jako nejasnost
nebo díra. Když něco optimalizuješ, zapiš do `docs/pipeline_prehled.md`/`todo.md`
i to, **co to znamená pro budoucí job** (nová závislost, nový stav,
změna pořadí, co musí být v konfiguraci).

---

## Dokumentace — kam se ZAPISUJE a kde se ČTE

### V kořeni: soubory, do kterých se zapisuje (nezapomínat)

| soubor | k čemu | kdy do něj psát |
|---|---|---|
| **`poznatky.md`** | deník měření, **nejnovější nahoře**. Co se ukázalo jinak, než se čekalo – vždy s naměřenými čísly. | po každém měření, nálezu nebo slepé uličce |
| **`aktualnistav.md`** | stav teď + další krok | **na konci každé práce** – práce se často přerušuje |
| **`todo.md`** | úkoly, nahoře prioritní | když vznikne úkol nebo se nějaký dokončí |
| `CLAUDE.md` | tenhle soubor: mapa a miny | když se změní pravidlo, struktura projektu nebo seznam benchmarků |
| `README.md` | vstup pro člověka: co to je, jak to pustit, kde co hledat | když se změní spuštění nebo struktura |
| `agents.md` | pokyny pro Codex jako druhého recenzenta | neměnit bez pokynu |

### V `docs/`: popisy, které se čtou podle toho, co řešíš

| soubor | k čemu |
|---|---|
| **`docs/pipeline_prehled.md`** | **mapa všech skriptů a pořadí kroků pipeline**, co znamenají pro měsíční job, dřívější názvy skriptů |
| `docs/pipeline_extrakce.md` | jak funguje extrakce do JSON (prompty, ořez, dopočty, stavy, nálezy N1–N12) |
| `docs/pipeline_batch_openai.md` | OpenAI Batch API (routy, zprávy, stavy) a jak běh spustit a sledovat |
| `docs/pipeline_stavy.md` | stavy extrakce – co který znamená |
| `docs/hledani_jak_funguje.md` | hledání: router, rozšíření dotazu, RRF, práh, hledací slovník |
| `docs/hledani_vek.md` | filtry „pro děti / dítě X let / pro dospělé": odvození věku z SPC bez modelu |
| `docs/hledani_gui_api.md` | API a webová aplikace |
| `docs/prezentace_scenare.md` | **odzkoušené dotazy pro předvádění** + ukázka chyb v datech |
| `docs/prezentace_vyklad.md` | výklad pro vedení IT, laicky |
| `docs/provoz_pristupy.md` | hesla, adresy, řešení potíží |
| `benchmarky/README.md` | co který benchmark měří a kolik stojí |
| `nerealizovane_kontroly/kontroly_popis.md` | kontroly extrakce: co dělaly, proč neběží, co chybí |

Když měníš skript nebo chování, **oprav ve stejné změně i jeho popis
v `docs/`** – jinak dokument zastará (stalo se: půlka návodů popisovala
smazanou pipeline). Nový dokument patří do `docs/` s předponou podle
oblasti (`pipeline_`, `hledani_`, `provoz_`, `prezentace_`), ne do kořene.

V `poznatky.md` jsou skripty i dokumenty pod **původními názvy**
(`naplni_db.py`, `hledej.md`…); převod je v `docs/pipeline_prehled.md` oddíl 6.

**Než začneš něco měnit v hledání nebo extrakci, projdi `poznatky.md`.**
Většina „dobrých nápadů" už tam je změřená — někdy jako zamítnutá.

**Složka `legacy/` (demo fáze do srpna 2026) i původní korpus 32 léčiv
(`data/leciva/`) jsou od 6. 10. 2026 smazané.** Kód je v gitu do commitu
`71c761c`; data se nedají vrátit. Platí jen korpus `data/spc/`.

---

## Peníze a bezpečnost

**POZOR NA PENÍZE:** na účtu OpenAI jsou **jednotky dolarů**. Pro cloud
používej **výhradně `gpt-6-luna`** (`config.OPENAI_MODEL`) a **vždy
s `reasoning_effort="none"`** (`config.OPENAI_REASONING_EFFORT`).
Reasoning se účtuje jako výstup a bez vypnutí je účet ~4× vyšší.
Pozor, luna bere `none`, na `minimal` vrací 400 (u nano je to naopak).
`gpt-4o`, `gpt-4o-mini` ani řadu `sol` nepouštět. Klíč je
v `key.yaml` v kořeni (v `.gitignore`), načítá se přes `config.nacti_openai_klic()`
(soubor **není validní YAML**, chybí mezera za dvojtečkou).

Embeddingy jsou jiný produkt a jsou o dva řády levnější — zákaz míří na
chat. I tak měř jen na vzorku.

Hesla k Postgresu, pgAdminu a Ollamě jsou v **`docs/provoz_pristupy.md`**.

---

## Modely

| model | k čemu |
|---|---|
| `qwen3.5:122b` (`MODEL_HLAVNI`) | lokální extrakce – jen volba `--local` pro jeden lék / malou dávku (výchozí cesta je cloud) |
| `gemma4:26b` (`MODEL_ROUTER`, `MODEL_KONTROLY`) | router + kontrola. MoE, 128 expertů / 8 aktivních. Kontrola je **záměrně JINÝ** model než ten, co data vyrobil |
| `gpt-6-luna` (`OPENAI_MODEL`) | **jediná cloudová volba pro extrakci** — nejlevnější, nejlepší a jediná překládá latinu do laické češtiny |
| `bge-m3` (`MODEL_EMBED`) | embedding, 1024 dim |

Router na gemma4:26b: medián **1,51 s** proti 4,56 s u qwenu, správně
24/26 proti 21/26 (`benchmarky/router/bench_router.py`, poznatky 24. 9.). Router je 92 %
času dotazu. Za provozu (API) jsou potřeba jen router a bge-m3.

**Generativní model embedding neumí** — vrátí 501 lokálně, 403 na OpenAI.

**U MoE se rychlost z velikosti neodhaduje.** gemma4:31b (dense) je
2,6× pomalejší než qwen3.5:122b (MoE), protože DGX Spark brzdí
propustnost paměti a rozhodují aktivní parametry.

Modely běží na DGX Sparku (`10.6.38.10`); druhý stroj Dell (`10.6.38.9`)
je v konfiguraci, ale 7. 10. ještě nemá otevřený port. Ollama modely odloží
po ~5 min nečinnosti, proto `keep_alive: 2h`, předehřátí při startu
(`ollama_client.priprav_modely()`) a hlídač, který je drží v paměti.

**Víc strojů s Ollamou** (`config.OLLAMA_UZLY`, pořadí = priorita):
`ollama_client` hlídá dostupnost, dotazy na router a embedding rozděluje
podle vytížení a při výpadku zkusí další stroj. **Jeden stroj vyřizuje
router po jednom** (8 uživatelů naráz = poslední čeká ~14 s). Nikdy
nevolej Ollamu přes `requests` napřímo – vždy `chat()` / `embed()`,
jinak dotaz obejde rozdělování. Popis: `docs/provoz_pristupy.md`.

---

## Benchmarky — co je k dispozici

Než začneš měřit něco „od nuly", podívej se sem. Podrobnosti (co
potřebují, kolik stojí) jsou v **`benchmarky/README.md`**. Pouští se
z kořene projektu.

| benchmark | odpovídá na | kdy pustit |
|---|---|---|
| `benchmarky/router/bench_router.py` | který lokální model má dělat router (rychlost, správnost, stabilita) | změna modelu nebo promptu routeru |
| `benchmarky/soubeh/bench_soubeh.py` | kolik čeká N uživatelů naráz, rozdělení mezi stroje s Ollamou; `--simulace` testuje výběr stroje a výpadky | po zapojení dalšího stroje; `--simulace` po zásahu do `ollama_client.py` |
| `benchmarky/extrakce_cloud/bench_extrakce_luna.py` | kolik stojí extrakce korpusu v cloudu, ukázka na 3 SPC | před každým hromadným cloudovým během, po změně promptu |
| `benchmarky/indikace_fragmenty/detektory.py` | kolik položek indikací je podezřelých (bez modelu) | po přeextrahování indikací |
| `benchmarky/indikace_fragmenty/soudce.py` | kolik z podezřelých je opravdu chyba (soudí gemma) | když je potřeba skutečný podíl chyb |
| `benchmarky/indikace_fragmenty/test_promptu.py` | starý vs. nový prompt indikací | před změnou promptu indikací |

Regresní test hledání je `hledani_evaluace.py` (není to benchmark, pouští
se po každé změně). Starší benchmarky (qwen, nano, cloudové embeddingy,
lokální Docling, pymupdf4llm) jsou smazané; závěry jsou v tabulce slepých
uliček níž a v `poznatky.md`.

---

## Příkazy

```bash
docker compose up -d
uv run uvicorn api:app --port 8000     # GUI + Swagger na /docs
uv run python hledani_cli.py "mám reflux"   # CLI
uv run python hledani_log.py "..."     # podrobný log jednoho hledání
uv run python hledani_evaluace.py              # test dat + parafráze ATC + negativní
uv run python extrakce_all.py --stav   # kde který krok pipeline je

# konverze celého korpusu (Docling Serve přes tunel na localhost:5001)
uv run python extrakce_1_konverze.py --obchodovana      # navazuje sám
uv run python extrakce_1_konverze.py --stav             # souhrn, podezřelé, kde se stálo
```

**EMA (EU EPARy) omezuje stahování (429).** Stahovat z ní jedno po
druhém s rozestupem (`--ema-rozestup`), limity nikdy neobcházet.

### Po ZMĚNĚ DAT vždy v tomhle pořadí

```bash
uv run python extrakce_4_db.py --korpus               # vše od nuly (~40 min)
# nebo jen jedna sekce:  extrakce_4_db.py --obnov-sekci indikace
uv run python extrakce_5_embeddingy.py                # jen řádky bez vektoru
uv run python hledani_evaluace.py
# + restart API
```

---

## Pravidla, která stála nejvíc času

### Měření

- **Pusť `hledani_evaluace.py` po KAŽDÉ změně** promptu, modelu, chunkování,
  vah nebo prahu. Je reprodukovatelný, dva běhy dají totéž.
- **Testovací případy ověřuj proti datům, nevymýšlej je.** Stalo se
  třikrát, že „negativní" dotaz v datech byl.
- **Opravit vybrané případy není totéž co zlepšit systém.** Případy si
  člověk vybírá podle toho, že ho zaujaly — zkreslený vzorek.
  Rozhoduje měření na celé sadě. (Takhle padla oprava hubness.)
- **„Je to vlastnost modelu" je pohodlný závěr.** Než ho napíšeš, změř,
  jestli je ten jev rovnoměrný.

### Data

- **`extrakce_4_db.py --korpus` plní vždy od nuly** (TRUNCATE; hledací
  slovník `slovnik_dotazu` nechá). Přírůstek po SPC zatím neexistuje –
  po opravě jedné sekce stačí `--obnov-sekci`.
- **Přeextrahování chyby neopraví**, jen je přesune jinam.
- **Ruční opravy laického tvaru patří do `common/data/slovnik_rucni.json`**
  – uplatní se při každé extrakci. (Generovaný slovník už neexistuje.)
- **Poměr zdrojů sekcí je regresní test.** `extrakce_2_sekce.py` vypisuje
  `docling_md=… pymupdf_raw=…`; skoková změna = něco se rozbilo.

### Čeština a texty

- **Diakritika je drahá.** Její ztráta stojí ~0,2 podobnosti a u „kašel"
  vrátí jiný lék. Router ji obcas zahodí, proto
  `router.obnov_diakritiku()`.
- **Klíče slovníku dotazů jsou KMENY** („kasl" i „kasel"), protože
  čeština při skloňování vyhazuje `-e-`. Nejsou to překlepy.
- **Do dotazu pro vektor nesmí slovo, které je v datech skoro všude**
  („léčba" je v 33 ze 155 indikací).
- **Dlouhá věta ředí význam.** Každé slovo navíc stojí 0,03–0,05.
  Tohle je nejčastější příčina špatných výsledků — projevilo se pětkrát.

### Provoz

- **Po změně schématu odpovědi restartuj API.** `--reload` po čase
  přestane zabírat a server běží na starém kódu. Postup na zabití
  procesů na Windows je v `docs/hledani_gui_api.md`.
- **Nepouštěj dlouhé běhy přes `tail`** — buffer schová průběh i chyby.
- **`num_ctx` nejít pod 16384** — Ollama delší prompt tiše usekne.

### Komunikace

- **Popisek je součást odpovědi, ne dekorace.** Když text tvrdí něco
  jiného než data, hledá se chyba tam, kde není. Stalo se třikrát
  za den.
- **Když operace trvá dlouho, musí být vidět proč.** Mlčící aplikace
  vypadá jako rozbitá.

---

## Změřené slepé uličky — NEZKOUŠET ZNOVU

| co | proč ne |
|---|---|
| **oprava hubness** (odečíst „rozbočivost") | spraví jednotlivé případy, ale na celé sadě je horší: 8/10 parafrází místo 9/10 při stejných negativních |
| **vybrat jednu variantu dotazu globálně** | ze tří antihistaminik by zbylo jedno; různé léky odpovídají různým formulacím |
| **cloudové embeddingy** | `3-small` horší než bge-m3 ve 4 z 5 dotazů, `3-large` prohrává na laických parafrázích |
| **pymupdf4llm** místo Doclingu | 3× rychlejší, ale slévá frekvence do odstavců |
| **`frekvence_rank_max` na vzácný konec** | „vzácné" pak vrátí i velmi časté — přesný opak |
| **mechanické dělení výčtů podle čárek** | uškodí ve 3 z 5 případů; dělí to model |
| **gemma4:31b (dense)** na cokoli | v každé úloze nejpomalejší (10 tok/s, router 11,8 s) a laický tvar v 37 % jen opíše |
| **cloud s výchozím `reasoning_effort`** | 4–16× pomalejší a 4–21× dražší, kvalita skoro stejná |

---

## Nedodělky, o kterých se ví

- **Extrakci nic nekontroluje.** Kontroly (doslovná shoda, jiný model,
  číselník pojmů) uměly jen 32 léků a nad korpusem neběží
  (`nerealizovane_kontroly/`); všechny sekce jsou `neovereno`. Laický
  tvar se neověřoval ani dřív: „akutní průjem" → „náhlý záškrt" prošlo.
  Příklad tří chyb na jednom léku: `docs/prezentace_scenare.md` kap. 6.
- **Router není deterministický** — občas ztratí název léčiva nebo ořeže
  dotaz na jedno slovo. Částečně řešeno pojistkou s původní větou.
- **Práh 0,60 a číselníky jsou naměřené na 32 lécích.** Na celém trhu
  práh pouští falešné shody („kocovina" → covid). Přeměřit:
  `hledani_evaluace.py --prahy`.
- **Věk použití** se odvozuje pravidly a občas chybuje (COLDREX 18 místo
  15); filtr „pro dospělé" zná jen spodní hranici věku.
- **Přírůstkové plnění DB** a kontejner pro server – `todo.md`.

---

## Zápisky — povinné, v kořeni projektu

- **`poznatky.md`** — každý poznatek s datem, **nejnovější nahoře**,
  vždy s naměřenými čísly. Když něco vyjde jinak, než se čekalo,
  patří to sem.
- **`aktualnistav.md`** — při ukončení práce zapiš přesný stav: co je
  rozpracované a jaký je další krok. Práce se často přerušuje.
- **`todo.md`** — úkoly; prioritní nahoře.
