# CLAUDE.md

Pokyny pro Claude Code. **Cílem je nemuset znovu odvozovat, co už je
změřené** — detaily jsou v `poznatky.md`, tady je jen mapa a miny.

---

## Co to je

**localsemantic** — sémantické vyhledávání v souhrnech údajů o přípravku
(SPC) ze SÚKL. Uživatel se ptá běžnou češtinou („mám reflux"), aplikace
najde odpověď v oficiálních dokumentech a ukáže odkaz na stranu PDF.

Cílová skupina jsou **laici**. Všechno běží lokálně.

Korpus **32 léčiv / 1 346 řádků**. CLI, REST API i webové GUI jsou hotové.

**Rozšiřuje se na všechna obchodovaná léčiva: 8 803 kódů SÚKL = 5 613
unikátních SPC** (deduplikace podle identity dokumentu). Konverze běží
přes `konvertuj_serve.py` (Docling Serve na DGX Sparku).

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

- **Seznam kroků = `pipeline.py` (`KROKY`)**, později `extrakce_all.py`.
  Mapa všech skriptů s popisem = **`skripty.md`**.
- **Nový produkční krok** se ve STEJNÉ změně zapíše do obou. Když
  nahrazuje starý krok, starý se tam označí jako nahrazený (nebo smaže).
- **Benchmarky a jednorázové analýzy patří do `benchmarky/<téma>/`**,
  ne do kořene projektu. Nové `bench_*.py` do kořene nezakládat.
- Diagnostické pomocníky zapsat do `skripty.md` (sekce F) s tím, kdy
  se pouštějí.

### Vždy mít přehled o CELÉ pipeline — hlavně při její optimalizaci

Než začneš měnit nebo zrychlovat kterýkoli krok, **ujasni si celou
řadu kroků od stažení po hotovou DB** (`skripty.md`, `pipeline.py`)
a to, co tvoje změna znamená pro kroky před a za ní (formát výstupu,
úložiště, stav po dokumentu, závislost na službě).

Proč: z téhle práce vznikne **zadání pro produkční aplikaci**, která
bude data nahrávat jako **měsíční job na serveru**. Tam už se změny
nepůjdou dělat tak rychle jako na notebooku (nasazení, provozní
schvalování, jiné prostředí). Každá změna pipeline, kterou teď
uděláš bez přehledu o celku, se pak do zadání propíše jako nejasnost
nebo díra. Když něco optimalizuješ, zapiš do `skripty.md`/`todo.md`
i to, **co to znamená pro budoucí job** (nová závislost, nový stav,
změna pořadí, co musí být v konfiguraci).

---

## Dokumentace — čti podle toho, co řešíš

| soubor | k čemu |
|---|---|
| **`poznatky.md`** | **nejnovější nahoře.** Co se ukázalo jinak, než čekalo zadání. Vždycky s naměřenými čísly. |
| `aktualnistav.md` | stav teď + další kroky |
| `todo.md` | úkoly, nahoře prioritní |
| **`extrakce.md`** | **jak funguje extrakce do JSON a navazující kroky** (prompty, dopočty, kontroly, kdo ověřuje laický tvar a klíč, nálezy N1–N12) |
| `extrakce_kontroly.md` | všechny kontroly extrakce s odkazy na soubory; **od 29. 9. VYPNUTÉ** (`config.KONTROLY_ZAPNUTE`), co dodělat nad novým korpusem |
| `batchOpenAI.md`, `sledovaniBatchOpenAI.md` | OpenAI Batch API (routy, zprávy, stavy, příklady) a jak běh `extrahuj_json_cloud.py` spustit a sledovat |
| `vek_pacienta.md` | filtr „pro děti / pro dítě X let": odvození věku z SPC 4.1–4.3 bez modelu, rozpoznání v dotazu, známé mezery |
| `hledej.md` | jak funguje hledání (router, rozšíření dotazu, RRF, práh) |
| `gui.md` | API a webová aplikace |
| `scenare.md` | **odzkoušené dotazy pro předvádění** |
| `prezentace.md` | výklad pro vedení IT, laicky |
| `stavy.md`, `pristupy.md` | stavy extrakce; hesla a řešení potíží |
| `zadani.md` | původní zadání + stav kroků |

**Než začneš něco měnit v hledání nebo extrakci, projdi `poznatky.md`.**
Většina „dobrých nápadů" už tam je změřená — někdy jako zamítnutá.

**`legacy/` je mrtvá složka** — záloha demo fáze do srpna 2026. Kód,
modely, tabulky ani skripty odtud **neplatí**; první verze aplikace je
hotová a nahradila je. Jediné, co se z `legacy/` používá, je
`key.yaml`. Nečerpej odtud, pokud tě tam někdo výslovně nepošle.

---

## Peníze a bezpečnost

**POZOR NA PENÍZE:** na účtu OpenAI jsou **jednotky dolarů**. Pro cloud
používej **výhradně `gpt-6-luna`** (`config.OPENAI_MODEL`) a **vždy
s `reasoning_effort="none"`** (`config.OPENAI_REASONING_EFFORT`).
Reasoning se účtuje jako výstup a bez vypnutí je účet ~4× vyšší.
Pozor, luna bere `none`, na `minimal` vrací 400 (u nano je to naopak).
`gpt-4o`, `gpt-4o-mini` ani řadu `sol` nepouštět. Klíč je
v `legacy/key.yaml`, načítá se přes `config.nacti_openai_klic()`
(soubor **není validní YAML**, chybí mezera za dvojtečkou).

Embeddingy jsou jiný produkt a jsou o dva řády levnější — zákaz míří na
chat. I tak měř jen na vzorku.

Hesla k Postgresu, pgAdminu a Ollamě jsou v **`pristupy.md`**.

---

## Modely

| model | k čemu |
|---|---|
| `qwen3.5:122b` (`MODEL_HLAVNI`) | extrakce a zjednodušení lokálně |
| `gemma4:26b` (`MODEL_ROUTER`, `MODEL_KONTROLY`) | router + kontrola. MoE, 128 expertů / 8 aktivních. Kontrola je **záměrně JINÝ** model než ten, co data vyrobil |
| `gpt-6-luna` (`OPENAI_MODEL`) | **jediná cloudová volba pro extrakci** — nejlevnější, nejlepší a jediná překládá latinu do laické češtiny |
| `bge-m3` (`MODEL_EMBED`) | embedding, 1024 dim |

Router na gemma4:26b: medián **1,51 s** proti 4,56 s u qwenu, správně
24/26 proti 21/26 (`bench_router.py`, poznatky 24. 9.). Router je 92 %
času dotazu. Za provozu (API) jsou potřeba jen router a bge-m3.

**Generativní model embedding neumí** — vrátí 501 lokálně, 403 na OpenAI.

**U MoE se rychlost z velikosti neodhaduje.** gemma4:31b (dense) je
2,6× pomalejší než qwen3.5:122b (MoE), protože DGX Spark brzdí
propustnost paměti a rozhodují aktivní parametry.

Modely běží na DGX Sparku. Ollama je odloží po ~5 min nečinnosti, proto
`keep_alive: 2h` a předehřátí při startu (`ollama_client.priprav_modely()`).

---

## Příkazy

```bash
docker compose up -d
uv run uvicorn api:app --port 8000     # GUI + Swagger na /docs
uv run python hledej.py "mám reflux"   # CLI
uv run python log_hledani.py "..."     # podrobný log jednoho hledání
uv run python pipeline.py --stav
uv run python evaluate.py

# konverze celého korpusu (Docling Serve přes tunel na localhost:5001)
uv run python konvertuj_serve.py --obchodovana      # navazuje sám
uv run python konvertuj_serve.py --stav             # souhrn, podezřelé, kde se stálo
```

**EMA (EU EPARy) omezuje stahování (429).** Stahovat z ní jedno po
druhém s rozestupem (`--ema-rozestup`), limity nikdy neobcházet.

### Po ZMĚNĚ DAT vždy v tomhle pořadí

```bash
uv run python ocisti_json.py --zapis
uv run python naplni_db.py --znovu          # --znovu POVINNĚ
uv run python vytvor_embeddingy.py
uv run python evaluate.py
```

---

## Pravidla, která stála nejvíc času

### Měření

- **Pusť `evaluate.py` po KAŽDÉ změně** promptu, modelu, chunkování,
  vah nebo prahu. Je reprodukovatelný, dva běhy dají totéž.
- **Testovací případy ověřuj proti datům, nevymýšlej je.** Stalo se
  třikrát, že „negativní" dotaz v datech byl.
- **Opravit vybrané případy není totéž co zlepšit systém.** Případy si
  člověk vybírá podle toho, že ho zaujaly — zkreslený vzorek.
  Rozhoduje měření na celé sadě. (Takhle padla oprava hubness.)
- **„Je to vlastnost modelu" je pohodlný závěr.** Než ho napíšeš, změř,
  jestli je ten jev rovnoměrný.

### Data

- **`naplni_db.py` bez `--znovu` data TIŠE ZDVOJÍ.** Skript to nově
  odmítne, ale pořadí výš je bezpečnější.
- **Přeextrahování chyby neopraví**, jen je přesune jinam.
- **Ruční opravy patří do `slovnik_rucni.json`**, ne do generovaného
  slovníku — jinak je příští běh přepíše.
- **Poměr zdrojů sekcí je regresní test.** `extrahuj_sekce.py` vypisuje
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
  procesů na Windows je v `gui.md`.
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

- **Laický tvar se neověřuje** proti odbornému. Model přeložil „akutní
  průjem" jako „náhlý záškrt" a prošlo to oběma kontrolami.
- **Router není deterministický** — občas ztratí název léčiva nebo ořeže
  dotaz na jedno slovo. Částečně řešeno pojistkou s původní větou.
- **Prahy a číselníky jsou naměřené na 32 lécích.** Na tisících se budou
  muset přeměřit.

---

## Zápisky

- **`poznatky.md`** — každý poznatek s datem, **nejnovější nahoře**,
  vždy s naměřenými čísly. Když něco vyjde jinak, než zadání čekalo,
  patří to sem.
- **`aktualnistav.md`** — při ukončení práce zapiš přesný stav: co je
  rozpracované a jaký je další krok. Práce se často přerušuje.
- **`todo.md`** — úkoly; prioritní nahoře.
