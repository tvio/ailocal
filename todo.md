# TODO ME
0. Leky cely korpus
Pridat debug log do GUI pro hledani
1. Sestaveni flow aplikace dle skritpy.md
1. Udelat logovani komple konverze
2. Udelat logovani komplet od A..Z
2. Vylepsit vyhledavani, kdyz najde nejaky vysoky rank - tak pridat vsehcno z dane ATC skupiny a lecive latky. 
4. Proc lek na kasel vraci ACIFEIN

---

# TOP – OD 2. 10. 2026: PIPELINE, ÚKLID, KONTEJNER, SERVER

Plán s vysvětlením je v `tentoTyden.md`. Pořadí:

### 1. Pipeline pro opakované spouštění
- [ ] Jeden příkaz přes celý řetěz (konverze → sekce → extrakce cloud →
      DB → věk → embeddingy → rejstřík → evaluate), JEDEN seznam kroků
- [ ] `naplni_db.py`: přírůstek po SPC místo TRUNCATE, zaniklá SPC označit
- [ ] Změněná SPC poznat (identita + otisk PDF) → jen ta do extrakce
- [ ] Konfigurace z prostředí: Ollama, Docling Serve, Postgres, OpenAI, rozpočet
- [ ] Zámek, log běhu, souhrn JSON, návratový kód pro cron

### 2. Úklid projektu
- [ ] Benchmarky z kořene do `benchmarky/<téma>/`
- [ ] `.gitignore`: neignorovat celé `benchmarky/`, jen výstupy (skripty dnes nejsou v gitu)
- [ ] `data/leciva/` (32 léčiv) a kód, který ho čte → korpus, nebo legacy
- [ ] `pipeline.py` KROKY + `skripty.md` A→Z podle skutečnosti
- [ ] Zastaralé dokumenty projít (`agents.md`, `codex_pripominky.md`, `aktualnistav.md`)

### 3. Kontejner
- [x] Velikost (1. 10.): `data/spc` 4,5 GB, `data/detaily_leciv` 41 MB, DB 5,7 GB → přenos ~10 GB
- [ ] Dockerfile aplikace + docker-compose (Postgres image už je)
- [ ] `data/` jako volume, přenos tar/rsync (ne git)
- [ ] DB přenášet `pg_dump`/`pg_restore` (embeddingy ~2 h znovu nepočítat)
- [ ] Tajnosti mimo image (env/secret), Ollama + Docling Serve z konfigurace

### 4. Nasazení na server
- [ ] Přenést image + data + dump, konfigurace, spuštění
- [ ] Smoke test: `hledej.py`, `evaluate.py --korpus`, GUI
- [ ] Měsíční cron + upozornění (viz CÍLOVÝ STAV níže)

### 4b. Před prezentací
- [x] (1. 10.) **Výpis VŠECH hledacích vzorů s odzkoušenými příklady** → `scenare.md` přepsán pro korpus – aby se
      při prezentaci nic nevymýšlelo na koleni. Staré (hrazený lék na
      reflux, volně prodejný lék s paracetamolem, nežádoucí účinky X,
      dávkování X, čtení sekce, frekvence NÚ, ATC záchranná síť…) i nové:
      věk („horečka dítě šest let", „rýma miminko"), „lék začíná / obsahuje /
      končí / přibližně" (zirtek, oftalmoframikoin, kalideko), kombinace
      vzor + sémantika („lék začíná na oxy na rýmu"). Každý příklad
      OVĚŘIT na korpusu (pravidlo CLAUDE.md) a zapsat do `scenare.md`.
- [ ] **Posuvníky „práh" a „barva" v GUI – zamyslet se, jestli dávají smysl.**
      Práh 0,60 je naměřený na 32 lécích; na korpusu a u přesných filtrů
      (věk, vzor názvu, čtení sekce) se neuplatňuje. Rozhodnout: skrýt
      do „pro pokročilé", přeměřit, nebo odstranit.

### 4c. ROZEBRAT ZÍTRA (2. 10.) – slabá místa z `scenare.md`
- [ ] **Práh podobnosti 0,60 přeměřit na celém trhu.** Je naměřený na 32
      lécích; na 5 880 SPC pouští falešné shody: „něco na kocovinu" →
      léky na covid, „lék na plešatost" → čaje na plynatost. Souvisí
      s úkolem na posuvník prahu v GUI (bod 4b).
- [ ] **Upřednostnit pro laika volně prodejné léky a vhodnou formu podání.**
      Dotazy na kojence/miminka vracejí nemocniční antibiotika v injekcích
      (MEDOCLAV, TAXIMED), „lék na kašel pro děti" má nahoře antibiotikum
      DALACIN. Možnosti: OTC dopředu, injekce/infuze dozadu nebo skrýt,
      pokud dotaz výslovně nechce nemocniční léčbu.

### 4d. Víc uživatelů najednou
- [ ] **Paralelismus na Ollamě pro víc uživatelů.** Router (gemma4:26b)
      je 92 % času dotazu a Ollama dnes zpracuje dotazy postupně – druhý
      uživatel čeká na prvního. `OLLAMA_NUM_PARALLEL` je ale GLOBÁLNÍ pro
      celý server (násobí paměť na kontext i u qwen3.5:122b) – změřit
      dopad, případně router na samostatné instanci. Viz bod o embeddinzích.
- [ ] **Počítadlo v GUI:** kolik lidí má aplikaci otevřenou v prohlížeči
      a kolik hledání právě běží (API: počet aktivních požadavků +
      „živé" spojení / heartbeat z GUI).

### 5. Když zbude čas
- [ ] Slovník dotazů: editace v GUI + doplnit podle korpusu (bod 5 níže)
- [ ] Evaluace: věk, ATC seznamy, test 0 pro korpus (bod 4b níže)

---

# TOP – ÚTERÝ 29. 9. 2026: EXTRAKCE DO JSON MODELEM (další etapa pipeline)

Konverze i rozparsování sekcí celého korpusu jsou hotové (viz
`aktualnistav.md` nahoře). Teď převod sekcí do strukturovaného JSON
modelem (indikace, kontraindikace, dávkování, NÚ + laický tvar + klíč).
**Pořadí pod-úkolů je závazné.**

### 1. HOTOVO 29. 9.: jak extrakce funguje TEĎ → `extrakce.md`

**Nejdřív rozhodnout N11** (`extrakce.md` kap. 7): luna byla změřena jen na
zjednodušení z hotového `doslovne`, produkce dělá vše jedním voláním →
buď rozdělit extrakci na 2 kroky (lokálně doslovné, cloud laický+klíč),
nebo celou extrakci do cloudu (nutné změřit 4.8). Určuje tvar úkolů 2–4.

Nic neměnit, dokud není jasný celý řetěz. Projít a sepsat (do
`skripty.md` / krátký výklad):
- [x] `extrahuj_json.py` – vstup `sekce/<sekce>.md` (PLNÁ sekce), ořez na
      jádro až uvnitř `extrahuj_sekci()` (`orezat=True`); výstup
      `json/<sekce>.json` + `_stav.json`. **Dnes čte jen `data/leciva/`
      (32 léčiv) a běží na lokálním qwen3.5:122b** (`config.MODEL_SEKCE`).
- [x] `common/extrakce.py` – `SYSTEM_PROMPT`, `PROMPTY` (per sekce),
      `POPIS_FORMATU` (5 formátů NÚ), `extrahuj_sekci()` / `_jeden_pokus()`,
      opakování při prázdné odpovědi, `klic_ma_oporu()` (klíč bez opory se
      zahazuje), `normalizuj_frekvenci()`, `normalizuj_skupinu()`.
- [x] `common/sekce.py` – `orizni_na_jadro()` (4.2 jen základní dávkování,
      4.8 bez prózy/hlášení, 4.1/4.3 rozpad výčtů + skupiny).
- [x] Navazující kroky: `ocisti_json.py` (číselníky, bez modelu) →
      `zkontroluj_json.py` (doslovná shoda se zdrojem) → `zkontroluj_modelem.py`
      (gemma4:26b) → `postav_slovnik.py` → `rozdel_vycty.py` → `naplni_db.py`
      (**čte `data/leciva/<kód>_<NÁZEV>/api.json` – pro korpus přepnout na
      `data/detaily_leciv/`**) → `vytvor_embeddingy.py` → `evaluate.py`.
- [x] Kde se liší laický tvar a klíč, kdo je vyrábí (jeden prompt s extrakcí?)
      a co přesně ověřují dnešní kontroly (jen `doslovne`, NE `laicky`).

### 2. Kontroly na KLÍČ a LAICKÝ tvar (musí být PŘED hromadným během)

Důvod: `poznatky.md` 23. 9. – nesmysly v laickém tvaru („kyselé řinčení
do krku", „náhlý záškrt" za akutní průjem) NEJSOU vlastnost modelu, ale
nedeterminismus → cloud je neřeší, jediná obrana je kontrola.

> **VŠECHNY KONTROLY EXTRAKCE ODLOŽENY 29. 9. – zapracovat až nad
> novým korpusem z cloudu.** Vypnuto přepínačem `config.KONTROLY_ZAPNUTE`
> (klic_ma_oporu, kroky 4a/4b, kontrola slovníku). Seznam toho, co
> dodělat, je v **`extrakce_kontroly.md` kap. 3**:
> - [ ] N1 laický tvar proti zdroji, N2 opora klíče proti `doslovne`,
>       N3 `zkontroluj_klic()` (naměřeno: 22 % klíčů > 4 slova),
>       N4 vazba účinek→frekvence proti značkám PDF, N5 stabilní ID místo
>       indexů, N8 uložený ořez, změřit 4b na gemma4:26b, regresní sada
> - [ ] Po zapracování: `KONTROLY_ZAPNUTE = True`, pustit 4a/4b nad
>       korpusem, přeměřit `evaluate.py`
>
> **ODLOŽENO 29. 9.: N1 (laický tvar dlouhých indikací/kontraindikací
> neověřuje nic) a N2 (opora klíče se ověřuje proti `laicky`, ne proti
> `doslovne`)** – viz `extrakce.md` kap. 4 a 7. Důvod: zbývá jen tento
> týden a Batch API OpenAI má okno až 24 h, takže cloudový běh zabere
> ~2 dny. Přednost má dostat korpus přes extrakci. Obě díry zůstávají
> OTEVŘENÉ – data z hromadného běhu budou mít laický tvar a klíč
> neověřené a musí se to o nich vědět (popisek / stav), dokud se
> kontroly nedodělají. Dodělat PŘED dalším měsíčním během.

- [ ] **Laický tvar proti zdroji:** dnes se neověřuje vůbec. Návrh: slova
      laického tvaru bez opory ve zdroji ani ve slovníku odborný→laický
      (`slovnik_pojmu.json`, `slovnik_rucni.json`) = podezření;
      nesmyslná/neexistující slova (slovník češtiny?); kontrola modelem
      (gemma4:26b, jiný model než ten, co tvar vyrobil).
- [ ] **Klíč:** 1–4 slova (dnes nevynucuje nikdo), 1. pád, diakritika,
      opora ve zdroji (`klic_ma_oporu`), nesmí být obecný („onemocnění"),
      nemá nechávat odborný termín, který laický tvar už přeložil
      (26b to dělal v 31 %, qwen 15 % – `poznatky.md` 24. 9.).
- [ ] Regresní sada známých zmetků z `poznatky.md` (ULTRACOD „alenzie",
      OMEPRAZOL „řinčení", BISACODYL „ve třasu", HIDRASEC klíč
      „onemocnění"…) – kontrola je MUSÍ chytit.

### 3. HOTOVO 29. 9.: cena v cloudu – ~5,5 $ přes Batch (poznatky 29. 9.)

- [x] Rozhodnuto 29. 9.: extrakce do cloudu CELÁ, luna, `reasoning_effort
      ="none"`, `temperature=0`, `seed=42`. Cloudová cesta je v
      `common/extrakce.py` (`_zavolej_cloud`).
- [x] Tokeny korpusu: vstup 31,5 M (polovina je prompt), výstup ~15,7 M
      → sync 11 $, **Batch ~5,5 $** (pesimisticky ~6,4 $).
- [x] Reálná extrakce na malém/středním/velkém SPC – bez chyby, 0,0065 $.
- [ ] **ROZHODNOUT PŘED BĚHEM: generovaný slovník přebíjí lunu.** 42 %
      laických tvarů ve vzorku přepsal `slovnik_pojmu.json` (qwen, 32 léčiv),
      i s překlepy („Pomalý tep srce"). Návrh: pro cloudový běh brát jen
      `slovnik_rucni.json` (68 ručních), generovaný slovník postavit
      znovu až z výstupu luny.
- [ ] Ověřit zůstatek na účtu OpenAI (odhad 5,5–6,4 $ + rezerva na opakování).
- [ ] (odloženo s kontrolami) vazba účinek → frekvence u luny proti značkám PDF.

### 4. Spustit v nové podobě – `extrahuj_json_cloud.py` (Batch API)

- [x] `extrahuj_json_cloud.py` (29. 9.): inventář SPC × sekce, dávky Batch
      API, stav po požadavku v `data/spc/_extrakce/stav.sqlite`, navazování
      po pádu / Ctrl+C, log `data/spc/_extrakce/log/`, `report.md` se všemi
      chybami podle ID, `--znovu-chybne` / `--znovu-seznam`, rozpočtový
      strop `config.CLOUD_STROP_USD`, priorita = SPC s nejvíc kódy.
- [ ] Test na 5 SPC s úmyslnými chybami (dávka bez souboru, požadavek bez
      promptu) – výsledek v `poznatky.md`.
- [x] **ROZPOČET: na účtu 10 $, korpus ~5,5 $ (pesimisticky 6,4 $).**
      `CLOUD_STROP_USD = 8.0` – pokryje celý korpus s rezervou.
- [ ] Ostrý běh: `uv run python extrahuj_json_cloud.py --beh` (v popředí).
- [ ] Po běhu: `postav_slovnik.py --zapis` z výstupu luny (generovaný
      slovník qwenu smazán 29. 9.), pak `ocisti_json.py` pro korpus.
- [ ] Zapsat do `pipeline.py` (dnes zná jen `data/leciva/`) – s úklidem
      „Krok 0" (dvě úložiště).
- [x] (29. 9.) Zámek proti souběžnému běhu (`beh.lock`, drží OS) + hlídač z Plánovače úloh – `sledovaniBatchOpenAI.md`.
- [x] Známá mezera (vyřešena `srovnej_s_openai`): pád PŘESNĚ mezi `batches.create` a zápisem do DB
      nechá dávku u OpenAI bez záznamu → požadavky se pošlou znovu
      (dvojí platba za ~1 dávku). Řešení: při startu srovnat
      `batches.list()` podle `metadata.davka`.

### 4b. DB a hledání nad korpusem (30. 9.)

- [x] `naplni_db.py --korpus`: zástupce SPC (nejmenší kód), `leciva.spc`,
      `leciva.zastupce`; API PDF přes mapu kód → SPC, výpis jen zástupci.
- [x] `evaluate.py --korpus` (30. 9.): parafráze podle ATC 20/20 (přesnost
      67 %), negativní mimo medicínu 5/6 – `poznatky.md` 30. 9.
- [ ] Test 0 pro korpus: pokrytí sekcí jen u ZÁSTUPCŮ SPC, heuristiku
      „podezřelé sekce" přeměřit (dnes hlásí 99 %).
- [ ] `ocisti_json.py` pro korpus: 10 145 duplicitních řádků, 342 textů
      s nejednotným klíčem.
- [ ] ATC seznamy v `PARAFRAZE_KORPUS` rozšířit o legitimní skupiny (V11
      bylinné čaje…), jinak přesnost podhodnocuje. Homeopatika V12 → rozhodnutí.
- [ ] Slabé dotazy: „mám alergii", „pálí mě při močení"; router pustil
      „jak vyměnit pneumatiku" (LIDOCAINE 0,652).
- [x] **Věk použití + filtr „pro děti"** (30. 9.): `common/vek.py`,
      `leciva.vek_od/pro_deti/vek_duvody`, `naplni_db.py --jen-vek`, router
      deterministicky, API + GUI detail „Věk použití". Poznatky 30. 9. večer.
- [ ] Věk: evaluace – sada dotazů „pro děti / pro dítě X let" s ověřeným
      očekáváním (žádný lék s vek_od > X, ASPIRIN nesmí u horečky dítěte).
- [ ] Věk: `vek_duvody` ukázat v GUI (proč „od 3 let") – popisek je součást odpovědi.
- [ ] Laické dotazy vracejí nemocniční injekce (FORTUM, PARACETAMOL B. BRAUN
      infuze) → filtr/upřednostnění formy podání a OTC pro laika.
- [ ] 4.4 (zvláštní upozornění) neextrahujeme – obsahuje např. Reyeův
      syndrom u aspirinu. Zvážit extrakci pediatrických upozornění.
- [ ] **Dávkování ze surového textu PDF místo Markdownu** (`common/sekce.py`:
      sekce bez tabulky → `pymupdf_raw`). Pravidlo vzniklo kvůli slepování
      FREKVENCÍ v 4.8 a na 4.2 se použilo plošně (stejně jako dřív na 4.1,
      kde se to opravovalo). Změřit na vzorku, jestli Markdown u 4.2 dá
      úplnější dávkování (nadpisy „Pediatrická populace" se zachovají).
      Smazáno 5 451 starých `davkovani_orez.md` (1. 10., ořez vypnut).
- [ ] **Dávkování: `pacient` je volný text, 18 230 různých popisů
      ze 45 197 položek, 45 % nejde zařadit podle věku** („Dospělí od 18 let
      s bipolární poruchou při přidání induktorů … bez valproátu"). Schéma
      hlídá jen strukturu, ne obsah.
      (1) HNED, bez modelu: při plnění DB odvodit štítky – věk
      (`normalizuj_skupinu`) + podmínky (ledviny, játra, dialýza, hmotnost,
      interakce/CYP, těhotenství) → filtr „dávkování pro děti".
      (2) Pro měsíční job: schéma `pacient` → `vek`, `stav`, `podminky`
      (výčet) – nutné přeextrahovat 4.2 (~2 $), nejdřív změřit na vzorku.
- [ ] **Evaluace znovu nad korpusem:** nový zmrazený `vzorek_eval.json`
      (starý = texty qwenu, kódy 32 léčiv), ověřit negativní dotazy
      a parafráze proti novým datům (pravidlo: případy ověřovat proti datům).
      Pak přeměřit PRAHY a VÁHY (naměřené na 32 lécích).
- [ ] **GUI: seznam balení u léku** – u zástupce ukázat i ostatní kódy SPC
      (sílu, balení, hrazení). Dnes vidí uživatel jen zástupce.
- [ ] **Filtry Rx/hrazeno berou jen zástupce.** Změřeno 30. 9.: hrazení se
      mezi balením liší u **151 z 5 880 SPC (2,6 %)**, Rx/OTC u **37 (0,6 %)**.
      U nich filtr podle zástupce může lék chybně vyřadit/zařadit →
      filtr „aspoň jedno balení splňuje" (EXISTS přes `leciva.spc`).
- [ ] Pro produkci zvážit pořádné řešení: hledací řádky navázat na SPC,
      ne na kód (schéma, hledání, GUI) – dnešní zástupce je zkratka.
- [ ] `ocisti_json.py`, `postav_slovnik.py` pro korpus (čtou `data/leciva/`).
- [ ] **Embeddingy celého korpusu ~2 h** (451 186 řádků, 30. 9.). Brzdí model,
      ne DB: bge-m3 přes Ollamu ~120 textů/s i při dávce 64–256, zápis do DB
      s HNSW 421 řádků/s. Pro měsíční job stačí přírůstek (nová/změněná SPC).
      Kdyby byl potřeba celý přepočet rychleji: `OLLAMA_NUM_PARALLEL` +
      paralelní požadavky, nebo samostatný embedding server (TEI) – změřit.
      POZOR: `OLLAMA_NUM_PARALLEL` je globální pro celý server – násobí
      paměť na kontext i u qwen3.5:122b a gemma4:26b, hrozí jejich
      odkládání a znovunačítání (87 GB). Váhy se nenačítají vícekrát.
      Čistší je samostatný embedding server mimo Ollamu.

### 5. Slovník DOTAZŮ podle nového korpusu + editace v GUI

`slovnik_dotazu.json` (rozšíření dotazu laika o formulace z dokumentů,
`common/dotazy.py`) je postavený na 32 léčivech.
- [ ] Doplnit podle nového korpusu (formulace z laických tvarů a klíčů
      luny) – klíče jsou KMENY (CLAUDE.md), obecná slova nesmí do hodnot.
- [ ] **Editace v GUI:** přidat / upravit / smazat heslo (klíč → varianty)
      – API endpoint + stránka ve `static/`. Změnu hned promítnout do
      hledání (cache `common/dotazy.py`), zápis do JSON se zálohou.
- [ ] Po každé změně `evaluate.py` (slovník mění hledání).

---

# CÍLOVÝ STAV: `extrakce_all.py` – celá pipeline jedním příkazem, spouštěná cronem

**Až budou obchodovaná léčiva dotažená do konce** (konverze → JSON →
zjednodušení → DB → embeddingy → evaluace), sjednotit to do jednoho
nadstavbového skriptu, který půjde nasadit na server a pouštět
**cronem např. jednou měsíčně**. Léčiva přibývají a končí, SPC se mění.

### Rozsah dat – co je zatím VYŘAZENÉ (25. 9.)

- [ ] **Homeopatika (ATC V12) bez SPC – vyřazena, ale do seznamu nejspíš
      patří.** 357 obchodovaných, 332 z nich SPC nemá (zjednodušená
      registrace, metadata 404). Vyřazena, aby nerozbíjela vyhledávání.
      Později rozhodnout, jak je ukazovat (bez SPC = bez indikací, jen
      atributy). 25 homeopatik S SPC (registrace s indikací: Oscillococcinum,
      Traumeel, Engystol…) zatím v korpusu – ROZHODNOUT.
- [x] **Platné stavy registrace: R, B, C, F, I, K, M, Y** (`PLATNE_STAVY`
      v `common/seznam_leciv.py`). Původně jen R – vypadlo ~370 obchodovaných
      (B 286, F 80, I 5). Mimo: G J N U Z ZI ZS a **P = potraviny pro zvláštní
      lékařské účely** (460 obchodovaných, nejsou léčiva).
- [x] Seznam léčiv se obnovuje z veřejného API na začátku běhu (měsíční
      vydání); 5 kódů z 24. 8. zaniklo mezi vydáními.

### Kontrola konverze potřebuje REGRESNÍ SADU známých případů (25. 9.)

Oprava jedné falešné chyby rozbila jiný dokument (PARALEN 93 % → 14 %),
chyceno jen proto, že se ručně zkoušely i dokumenty, které byly v pořádku.

- [ ] Skript/test se sadou případů s OČEKÁVANÝM výsledkem, pouštět po
      každé změně `common/kontrola_konverze.py` (jako `evaluate.py`):
      - ok: PARALEN cz_82842, ERMM-1 cz_87529 („4.8.Nežádoucí" bez mezery),
        CAVINTON cz_10145 (Word), ACECOR (falešný nadpis Doclingu – info)
      - podezření: MENOPUR cz_95795 (chybí poznámky a–e, ~66 %),
        AUBAGIO (posun sloupce frekvencí, benchmark), CASARO (přeskládání)
      - nadpisy: „4. 8.", „4.8.Nežádoucí", „4.8" samotné na řádku,
        zalomený odkaz „4.8)." NENÍ nadpis, „4.81" není 4.8.
- [ ] `common/sekce.py`: Docling občas udělá z nadpisu bodu ODRÁŽKU
      („- 4.8 Nežádoucí účinky" místo „## 4.8…") – 13 z 5 880 SPC (0,2 %),
      4.8 jen STOPTUSSIN. Sekce se pak vezme ze surového textu (text je, ale
      bez tabulky Doclingu). Povolit „- 4.x Velké písmeno" jako nadpis –
      až s regresní sadou (pozor na odrážky typu „- 4.8 mg").

### Přípravky BEZ SPC v aplikaci – zařadit jen s atributy z registru

Týká se: **homeopatika bez SPC** (ATC V12: obchodovaných 358 v září 2026 – web ukazuje ~360 kvůli týdenním přírůstkům; 333 bez SPC, 25 se SPC) a
**neregistrované F/I** (léčebný program / mimořádné opatření, 85 kódů –
SPC nemají, odkaz vede na web SÚKL o povolení). Do přehledu patří, ale
nesmí rozbít hledání podle příznaků. Až po extrakci a plnění DB.

- [ ] DB: příznak `ma_spc` + typ (`bezne` / `homeopatikum` / `neregistrovane_FI`).
- [ ] Přípravky bez SPC nahrát **jen jako sekci `atributy`** (název, síla,
      látky, ATC, kód, výdej, hrazení) – žádné indikace/NÚ. Dotaz na příznak
      jde routerem do indikací → neobjeví se; dotaz na název („arnika",
      „Legalon") je najde přes atributy (fakticky fulltext).
- [ ] **Riziko: dotazy s nízkou jistotou routeru** hledají ve všech sekcích
      vč. atributů → přípravek bez SPC se může chytit na slovo z názvu/látky.
      **Změřit PŘED nasazením:** test v `evaluate.py` – dotazy na příznaky
      nesmí vrátit přípravek s `ma_spc = false`.
- [ ] **GUI popisek:** „bez SPC – údaje jen z registru SÚKL" / „homeopatikum",
      bez odkazu na PDF (popisek je součást odpovědi – CLAUDE.md).
- [ ] **ROZHODNOUT: 25 homeopatik SE SPC** (Oscillococcinum, Traumeel,
      Engystol, Coryzalia, Stotux…). Mají v SPC indikace („chřipka") → na
      „lék na chřipku" by se ukázala vedle běžných léků. Otázka obsahu pro
      laiky, ne techniky: nechat / označit „homeopatikum" / vyřadit z hledání
      podle příznaků.

### Krok 0 – úklid, ať je pipeline čitelná bez zpětného dohledávání

Pravidlo je v CLAUDE.md („Pipeline má JEDEN seznam kroků"). Dnešní stav
ho porušuje:

- [ ] **`konvertuj_serve.py` není v `pipeline.py` `KROKY`** – krok 1 tam
      pořád je `konvertuj_spc.py` (lokální Docling). Zapsat, starý označit.
- [ ] **Dvě úložiště:** `data/leciva/<kód>_<NÁZEV>/` (32 léčiv) a
      `data/spc/<identita>/` (celý korpus). Kroky 2+ čtou jen první.
      Sjednotit na jedno (identita SPC + mapa kód → SPC).
- [ ] **`rozdel_vycty.py` chybí v `KROKY`**, stažení a DB/embeddingy jsou
      mimo `pipeline.py` (viz `skripty.md` sekce 2).
- [ ] **Benchmarky v kořeni** (`bench_embed_cloud`, `bench_extrakce`,
      `bench_konverze`, `bench_rerank_nano`, `bench_router`,
      `bench_zjednoduseni` + jejich `*.json`) a Codexův `benchmark/` přesunout
      do `benchmarky/<téma>/`. Pozor na odkazy v `poznatky.md`.
- [ ] `skripty.md` po úklidu přepsat tak, aby A→Z pořadí bylo na jednom místě.

### Musí umět

- [ ] **Přírůstkově, ne celé znovu.** Inventář z API SÚKL (`dokumenty-metadata`)
      porovnat s minulým během:
      - **nová SPC** → zpracovat celá,
      - **změněná SPC** → poznat podle identity dokumentu (CZ `id` se mění
        s verzí) + otisku obsahu PDF (SHA-256); zpracovat znovu,
      - **zaniklá** (kód už není obchodovaný / registrovaný) → v DB označit
        jako neaktivní, NEMAZAT (historie, odkazy),
      - beze změny → přeskočit.
- [ ] **Navazování po pádu** jako `konvertuj_serve.py`: stav po každém
      dokumentu, stejný příkaz pokračuje; dávky se stabilními čísly.
- [ ] **Zámek proti souběžnému běhu** (cron nesmí pustit druhý běh, když
      první ještě jede).
- [x] **Report podezřelých na konci každého běhu** (`common/report_konverze.py`,
      volá `konvertuj_serve.py`) – do `extrakce_all.py` převzít + počet
      podezřelých do souhrnu běhu jako práh pro upozornění.
- [ ] **Logování:** jeden log na běh + souhrn běhu jako JSON
      (kolik nových / změněných / zaniklých, chyb, podezřelých, čas, cena).
- [ ] **Monitoring:** návratový kód pro cron (0 ok, ≠0 problém) + upozornění,
      když se překročí práh (chyb > N %, podezřelých > N %, běh trval
      nezvykle dlouho, EMA/SÚKL vrací 429, cloud nad rozpočet). Kam
      upozornění posílat – rozhodnout (e-mail / Teams / soubor pro dashboard).
- [ ] **Rozpočtová pojistka pro cloud** (luna Batch API): odhad ceny PŘED
      odesláním, strop na běh; nad stropem neodeslat a upozornit.
- [ ] **Ohled na externí služby:** EMA a SÚKL s rozestupem a respektem
      k 429 (viz EU dokumenty 25. 9.), nikdy obcházet limity.
- [ ] **Závislosti jako konfigurace:** URL Docling Serve, Ollamy, Postgresu,
      rozpočet, prahy – ne natvrdo v kódu (server ≠ notebook).
- [ ] **DB přírůstkově:** `naplni_db.py` dnes umí jen `--znovu` (celé znovu).
      Pro měsíční běh upsert po léčivech + deaktivace zaniklých.
- [ ] Na konci **evaluate.py** a jeho čísla do souhrnu běhu – regrese se
      musí projevit hned, ne až u uživatele.
- [ ] `--dry-run`: jen ukázat, co by se zpracovalo (nové/změněné/zaniklé), nic nedělat.

Stavební kameny už existují: `konvertuj_serve.py` (inventář, dedup,
navazování, dávky, hlídač zatuhnutí, kontroly), `common/kontrola_konverze.py`,
`pipeline.py` (pořadí kroků).

---

# ZÍTRA (25. 9. 2026): konverze VŠECH obchodovaných SPC do Markdownu přes Docling Serve

**STAV 25. 9. 23:05 – po opravě kontroly: 395 podezřelých, sekce přeparsované,
přehled `data/spc/_report/sekce.html` + `sekce.csv`. Detail v `aktualnistav.md`.**

**STAV 25. 9. 21:40 – SEKCE ROZPARSOVANÉ (bez modelu):** `extrahuj_sekce.py
--korpus` na 5 880 SPC: 23 520 sekcí, zdroj docling_md 17 856 (76 %) /
pymupdf_raw 5 641 (24 %), **nenalezeno 23 (0,1 %)**: indikace 13, dávkování 5,
kontraindikace 3, NÚ 2. Verdikt kontroly konverze v `sekce/_prehled.json`
(`_konverze`): 415 podezřelých. DALŠÍ KROK: extrakce do JSON modelem – až
po kontrolách laického tvaru a klíče a přepočtu rozpočtu luny.

**STAV 25. 9. 20:05 – KONVERZE HOTOVÁ NA ZÁŘIJOVÉM VYDÁNÍ SÚKL:**
8 825 obchodovaných R kódů, 8 492 se SPC → **5 648 používaných SPC,
vše převedeno**, 419 podezřelých (`data/spc/_report/podezrele.html`).
Seznam léčiv se obnovuje sám z veřejného API na začátku běhu
(`common/seznam_leciv.py`). 23 SPC už nepoužívá žádný kód (staré verze).

**STAV 25. 9. 18:25 – KONVERZE HOTOVÁ: 5 613 / 5 613 SPC** (0 chyb),
**456 podezřelých (8,1 %)** k projití: `uv run python konvertuj_serve.py --stav`.
EU 839/839 (EMA: ≥10 s mezi staženími + Retry-After, opakování při
502/503/504). DALŠÍ KROK: projít podezřelé podle typu důvodu, pak
extrakce do JSON (luna Batch API – nejdřív kontroly laického tvaru a klíče).

**STAV 25. 9. 13:00:** převedeno **4 800 z 5 613 SPC** (vč. 4 z Wordu),
375 podezřelých po nové kontrole. **Zbývá 813 EU dokumentů** — EMA
vrací 429 (nejspíš dočasný trest za ranní 4 souběžná stahování; včera
68 EU dokumentů po 0,3 s prošlo bez problému). Běh zastaven, nechat
EMA vychladnout (večer / přes noc) a pak:
`uv run python konvertuj_serve.py --obchodovana --od-davky 48 --znovu-chyby`  (tempo řídí Retry-After, ~2 h)
Když bude 429 dál, NEOBCHÁZET (User-Agent apod.) – zvýšit rozestup.

**STAV 25. 9. ráno:** skript `konvertuj_serve.py` + kontroly
`common/kontrola_konverze.py` HOTOVÉ. Inventář hotový: **5 613 unikátních
SPC** (data/spc/_stav.sqlite). Konverze čeká na Docling Serve (tunel na
localhost:5001 nebyl dostupný). Spustit:
`uv run python konvertuj_serve.py --kod 0254048` (zkouška), pak
`uv run python konvertuj_serve.py --obchodovana`. Souhrn: `--stav`.

Proč Docling Serve a ne pymupdf4llm: `poznatky.md` 24. 9. — na Sparku
13× rychlejší (~2,8 s/PDF), výstup totožný s lokálním Doclingem,
pipeline je na Docling naladěná.

### 1. Seznam dokumentů a DEDUPLIKACE (před stažením)

- [ ] Z `data/pool_leciv.json`: obchodované + registrované (`je_dodavka`,
      `stav_registrace == "R"`) → 8 803 kódů SÚKL.
- [ ] U každého kódu `GET /dlp/v1/dokumenty-metadata/{kod}` → identita SPC:
      - **CZ:** `id` dokumentu (např. 82842) — stahuje se ale přes
        `/dokumenty/{kod}/spc`, `/dokumenty/{id}` vrací 400!
      - **EU:** `link` na EPAR na EMA — **jeden dokument pro celý přípravek**
        (všechny síly i balení).
- [ ] **Deduplikovat podle té identity** (id / link), ne podle kódu ani
      registračního čísla. Odpověď na otázku „hledat duplicity u EU":
      ANO, a udělá se to samo — všechna balení EU přípravku mají TENTÝŽ
      odkaz. Odhad ~5 500 různých SPC (± 570), z toho EU ~840.
      Uložit mapu `kod SÚKL → identita SPC`, ať se výsledek dá rozdat
      zpátky na všechny kódy.
- [ ] Kódy bez SPC v API (~6 %) zapsat do logu jako `bez_spc`, ne tiše vynechat.
- [ ] EU PDF z EMA mají i 100+ stran → ořez před Přílohou II
      (`konverze.orizni_pdf_pred_konverzi`) PŘED odesláním na server.

### 2. Konverzní skript — požadavky

- [ ] **Paralelně:** víc požadavků na Docling Serve najednou (server byl
      při sekvenčním běhu vytížený jen z poloviny; čas serveru 1,4 s vs
      HTTP 2,8 s). Začít na 4 souběžných, změřit, případně zvýšit.
      Pozor: Spark sdílí paměť s Ollamou — hlídat, že se modely nevytlačují.
- [ ] **Stav po KAŽDÉM dokumentu** do souboru (JSONL / SQLite):
      `identita, kod, stav (ok|chyba|timeout|bez_spc), cas_s, stran, znaku,
      tabulek, chyba`. Při novém spuštění se hotové přeskočí →
      **navázání přesně tam, kde to skončilo**.
- [ ] **Jasný log průběhu:** `[1234/5500] 0254048_PARALEN 8 str. 2,1 s OK`
      + každých N dokumentů souhrn (hotovo, chyb, zbývá, odhad dokončení).
      Běh přes `tail` ne — viz CLAUDE.md.
- [ ] **Timeout na požadavek** (např. 10 min na PDF, EPAR má i 100 stran)
      → stav `timeout`, pokračuje se dalším. Zatuhnutí se pak pozná
      v logu: poslední řádek `ZAČÍNÁ <dokument>` bez `HOTOVO`.
- [ ] Zápis výstupu atomicky (do `.tmp`, pak přejmenovat) — přerušený
      zápis nesmí vypadat jako hotový dokument.
- [ ] Na konci souhrn: kolik ok / chyb / timeout / bez SPC, celkový čas.

### 3. Kontroly kvality po konverzi (zatím NEVÍM PŘESNĚ JAK — rozmyslet)

Docling na Sparku má stejné vady jako lokálně (`poznatky.md` 24. 9.).
Kontroly se mají pouštět nad hotovým Markdownem, bez dalšího Doclingu:

- [ ] **Pokrytí textu proti PDF** — nejjednodušší a nejdůležitější.
      Slova sekce 4.8 ze surového textu PyMuPDF (`surovy_text`) vs slova
      téže sekce v Markdownu. Pod ~90 % = podezření na ztracený nebo
      přeskládaný text (na 100 SPC by to označilo 4 dokumenty, např.
      CASARO 35 %). Hotová implementace: `benchmarky/pdfextrakce/
      bench_pdfextrakce.py` → `slova_pdf_48()` + `pokryti()`.
- [ ] **Sloupec frekvence podle polohy v PDF** (tabulky formátu 2, sloupce
      = frekvence). Docling u AUBAGIO posunul účinky o sloupec („časté" →
      „velmi časté"). Kontrola: najít slovo z buňky v PDF, zjistit, pod
      kterým záhlavím frekvence leží, porovnat s Markdownem. Základ je
      v `benchmarky/pdfextrakce/arbitr_pdf.py`; zatím porovná jen buňky
      se shodným textem → rozšířit.
- [ ] **Falešné nadpisy** — Docling dělá `##` i z obyčejných vět
      (ACECOR „Přípravek je indikován:"). Skutečný podnadpis je v PDF
      tučně / kurzívou / PODTRŽENÝ (`tucne_radky()` v benchmarku).
      Méně kritické — vadí jen tam, kde nadpis určuje skupinu pacientů.
- [ ] Výsledek kontrol zapsat do stavu dokumentu (`kontrola: ok | podezreni`)
      a podezřelé vypsat na konci — ať se dají projít ručně.

---

# GUI: pracovat s orgánovým systémem (24. 9. 2026)

Data ho mají (`leciva_search.organovy_system`, MedDRA třídy u NÚ), filtr
v `Filtr.organovy_system` i v routeru existuje, ale **v GUI se nevyužívá**
— ukazuje se jen v rozbaleném detailu nejlepší položky.

- [ ] Ukázat orgánový systém u každé položky NÚ v seznamu (jako frekvenci).
- [ ] Zúžení seznamu podle orgánového systému v prohlížeči — stejně jako
      tlačítka frekvence (`frekTlacitka` v `static/app.js`).
- [ ] Možnost seskupit NÚ podle orgánového systému (tak je to i v SPC 4.8).
- Data jsou připravená: `organovy_system` má **878 z 889 NÚ (99 %)**.
- [ ] Data: 1 NÚ má frekvenci „nejčastějším" (není v číselníku) —
      opravit v `slovnik_rucni.json` / normalizaci, GUI ji zatím ukáže šedě.
- [ ] Router: „co dělá Paralen se srdcem" — spor pravidel v promptu, viz
      níž; souvisí s tím, kdy se filtr na orgánový systém použije.

---

# Router na gemma4:26b (24. 9. 2026) — 3× rychlejší, stejně správný

Čísla v `poznatky.md` 24. 9. Medián 1,51 s proti 4,56 s u qwenu.

- [x] `MODEL_ROUTER` a `MODEL_KONTROLY` = `gemma4:26b` (24. 9.)
- [ ] Projít scénáře ze `scenare.md` v GUI s novým routerem.
- [ ] Změřit KONTROLU na 26b (`zkontroluj_modelem.py`) — přepnuto bez
      měření. Zkusit, jestli najde známou chybu „akutní alergické stavy"
      vs „těžké alergické reakce", kterou našla 31b.
      Zkouška na 3 sekcích (24. 9.): 5,0 s/sekci, JSON OK, 6 nálezů
      ze 144 položek — **2 z nich si samy odporují** („ve zdroji je
      vzácná, v položce je vzácná"). Plané poplachy hlídat.
- [ ] Ověřit paměť: vejde se 26b vedle qwen3.5:122b, nebo ho Ollama odloží?
- [ ] Rozhodnout v promptu routeru spor „co dělá Paralen se srdcem" —
      příklad (NÚ) proti výjimce (lék + příznak → obě sekce).
- [ ] `bench_zjednoduseni.py` má prompt BEZ diakritiky, produkce s ní.
      Opravit a přeměřit i cloudové srovnání z 23. 9.

---

# TOP ÚKOL (23. 9. 2026): zrychlit konverzi — Docling / pymupdf4llm

Konverze je po extrakci druhá největší brzda: **61 h z 347 h** pro
6 618 SPC, a cloud na ni nemá vliv. Běží na i5 notebooku. Čísla jsou
v `poznatky.md` nahoře.

- [x] `TORCHDYNAMO_DISABLE=1` — produkce ho měla celou dobu
      (`common/konverze.py` při importu), padal jen benchmark. Opraveno. (24. 9.)
- [x] **`do_ocr=False`** v produkci. Na 32 léčivech 31/32 shodně, úspora
      jen **8 %** (ne 15 %). (24. 9.)
- [x] **pymupdf4llm na všech 32:** 3,2×, buňky NÚ ve sloupci 93 %,
      formát 2 **97 %**. Vada: ~40 slepených slov v 4.8. (24. 9.)
- [x] Benchmark na 100 SPC: `benchmarky/pdfextrakce/` (24. 9.)
- [ ] **PROHLÉDNOUT** `benchmarky/pdfextrakce/report/index.html` — hlavně
      léky s červenými čísly; rozhodovat proti PDF, ne proti Doclingu.
- [ ] **ROZHODNOUT: pymupdf4llm (starý režim) + pojistka pokrytím,
      nebo selektivní Docling?** Čísla v `poznatky.md` 24. 9.
- [ ] Rozhodčí `arbitr_pdf.py` rozšířit i na buňky s rozdílným textem
      (dnes najde jen 5 sporů) — teprve pak jde říct, kdo má frekvence
      správně častěji.
- [ ] Marker: potřebuje `llama-server` (llama.cpp) — rozhodnout, zda
      instalovat.
- [ ] Pokud pymupdf4llm projde, doplnit do `extrahuj_sekce.py` čištění
      jeho artefaktů: `<br>` v buňkách, `<sup>1</sup>`, `**tučné**`
      v hlavičce a **rozpad tabulky na dvě přes zlom stránky**.
- [ ] **Selektivní Docling** — tabulku má jen 31 ze 128 sekcí a 34 sekcí
      už dnes jede z PyMuPDF. Pouštět Docling jen na stránky s tabulkou;
      `_prehled.json` a `strany.json` už vědí kde.
- [ ] Teprve pak řešit paralelizaci a server. Když kroky výš srazí 61 h
      na jednotky hodin, deployment nemusí být potřeba vůbec.

---

# ÚKOL: zjednodušení + klíče celého korpusu přes cloud

Rozhodnuto 23. 9. na základě měření (`poznatky.md`). Ostatní kroky —
embedding, router, hledání — zůstávají lokálně.

**Konfigurace: `gpt-6-luna`, `reasoning_effort="none"`, Batch API.**

- [x] `config.OPENAI_MODEL` = `gpt-6-luna`, `OPENAI_REASONING_EFFORT = "none"`
      (24. 9.; zapojeno v `bench_extrakce`, `bench_rerank_nano`, `zkontroluj_modelem`).
- [ ] `reasoning_effort="none"` POVINNĚ. Luna bere `none`, nano bere
      `minimal`, každý model jen to své (druhé vrací 400). Bez vypnutí
      je účet 46 $ místo 5 $. `low` NEPOMÁHÁ — reasoning zůstane na 90 %.
- [ ] Batch API: JSONL, 24h okno, −50 %. 19 854 požadavků se vejde do
      jednoho batche (limit 50 000), JSONL ~52 MB (limit 200 MB).
- [ ] Očekávaná cena **~2,7 $** za 6 618 SPC. Vstup je jen 17 % účtu,
      takže cachování ani zkracování promptu neřešit.
- [ ] Ošetřit: pořadí výsledků NEODPOVÍDÁ pořadí vstupu (párovat přes
      `custom_id`), chybové položky jdou do zvláštního souboru.
- [ ] Deduplikovat na registrační číslo: 8 803 kódů SÚKL = jen 6 618 SPC.

---

# ÚKOL: pořádná pipeline extrakce — lokálně i cloudem, ručně spustitelná

**Extrakce nesmí být „pustit model na pozadí".** Musí to být sada
skriptů s jasnými vstupy a výstupy, kterou jde spustit ručně,
zopakovat a zkontrolovat. Dnes to tak není.

## Co je dnes špatně

**1. Část produkčních kroků je MIMO `pipeline.py`.** V `KROKY` je jen
sedm skriptů (konverze → sekce → extrakce → očištění → kontrola1 →
kontrola2 → slovník). Mimo ně, ale k výsledku nutné, zůstávají:

| skript | co dělá | proč to vadí |
|---|---|---|
| `stahni_data.py` | stažení SPC z SÚKL | krok 0, bez něj není co extrahovat |
| `doplni_klice.py` | dopočet klíčů | **klíč JE součást extrakce**, ne doplněk |
| `rozdel_vycty.py` | dělení výčtů modelem | mění počet položek |
| `zkontroluj_orez.py` | kontrola ořezu sekcí | ověření mimo řadu ověření |
| `naplni_db.py` | naplnění DB | bez `--znovu` TIŠE ZDVOJÍ |
| `vytvor_embeddingy.py` | embeddingy | bez nich hledání nefunguje |

Důsledek: „pustím pipeline" **neznamená** „mám hotová data". Správné
pořadí je dnes ústní tradice v `CLAUDE.md`, ne kód.

**2. Nejde spustit jedno léčivo.** `ARGY` má natvrdo `--vse` u konverze,
sekcí i extrakce. Přepínače `--od` a `--jen` vybírají KROK, ne LÉČIVO.
Jednotlivé skripty `--kody` umí, pipeline je nepředá.

**3. Není přepínač lokálně / cloud.** Volba modelu je v `config.py`
a mění se editací souboru.

## Co má vzniknout

- [ ] **`--kody` a `--vse` na úrovni pipeline**, propsané do všech
      kroků. Musí jít říct „extrahuj jen 0500896" i „extrahuj všechna
      obchodovaná".
- [ ] **Výběr korpusu jako vstup**, ne jako implicitní „co leží
      v `data/leciva`". Aspoň: jedno léčivo / seznam kódů / všechna
      obchodovaná (`je_dodavka` + `stav_registrace=R`, deduplikovaná
      na registrační číslo — 6 618, ne 8 803).
- [ ] **`--kde local|cloud`** na úrovni pipeline, ne editací `config.py`.
      Cloud znamená gpt-6-luna + `reasoning_effort="none"` + Batch API;
      lokál qwen3.5. **Embedding, router a hledání zůstávají lokálně
      v obou případech.**
- [ ] **Doplnit do `KROKY` všechny chybějící kroky** z tabulky výš,
      včetně naplnění DB a embeddingů, ve správném pořadí. Pravidlo
      „po změně dat vždy `ocisti` → `naplni --znovu` → `embeddingy` →
      `evaluate`" musí vynucovat kód, ne dokumentace.
- [ ] **Ověření jsou součást pipeline, ne příloha.** Kontrola proti
      zdroji, kontrola jiným modelem, kontrola ořezu a nově kontrola
      laického tvaru (viz blokující krok níž) musí běžet v řadě
      a jejich výsledek musí být vidět v `_stav.json`.
- [ ] **Každý krok hlásí, co načetl a co zapsal**, a `--stav` musí
      říct pravdu o celé řadě, ne jen o její části.
- [ ] **Idempotence a navazování.** Běh na 6 618 SPC se přeruší —
      musí jít pustit znovu a dopočítat jen chybějící, ne začínat od
      nuly. (Táž chyba jako u `bench_zjednoduseni.py`, kde pád IDE
      shodil výsledky dvou modelů; opraveno průběžným zápisem.)
- [ ] **Suchý běh** (`--nanecisto`), který vypíše, co by se dělalo,
      s kolika léčivy a odhadem času a ceny. U cloudu MUSÍ ukázat
      odhad ceny dřív, než se něco pošle.

## Proč to je teď

Na 32 lécích se dá ručně dohlédnout, co kde chybí. **Na 6 618 SPC
a ~278 000 řádcích ne.** Krok, který zůstane mimo pipeline, se
na velkém korpusu prostě zapomene — a přijde se na to až podle
divných výsledků hledání.

---

# ÚKOL: evaluace zjednodušení a klíčů (dnes se NEDĚLÁ)

`evaluate.py` měří hledání, ale **kvalitu `laicky` a `klic` neměří
nikdo**. Proto se na nesmysly přišlo až náhodou při ladění prahů.

- [ ] Přidat do `evaluate.py` sadu nad `laicky` a `klic`. Metriky už
      existují v `bench_zjednoduseni.py` a jsou deterministické:
      pokrytí klíčem, opora klíče, podíl klíčů delších než 4 slova.
- [ ] **Doplnit kontrolu laického tvaru proti zdroji** — viz blokující
      krok níž. Bez ní evaluace nechytí `řinčení` ani `ve třasu`.
- [ ] POZOR: `laik_bez_op` (podíl slov bez opory) **nepoužívat jako
      metriku kvality**. Změřeno: nejvyšší hodnotu má nejlepší model,
      protože skutečný překlad latiny slova ze zdroje nemá.
- [ ] Zmrazit vzorek, ať jdou běhy porovnávat (týž problém jako test 2).

---

# NÁPAD (nerozpracováno): opravovat nesmysly druhým během qwenu

Změřeno, že **8 z 8 známých nesmyslů zmizelo při pouhém druhém
spuštění** téhož modelu s týmž promptem. Chyba je nedeterministická,
takže druhý pokus ji s vysokou pravděpodobností neudělá.

Myšlenka: nespoléhat na jeden běh, ale **podezřelé položky přegenerovat**.

Co není vyřešené:
- **Podle čeho vybrat, co přegenerovat?** Přegenerovat všechno je
  dvojnásobná cena. Potřebuje to detektor — tedy nejdřív kontrolu
  laického tvaru (blokující krok níž).
- **Kdy přestat?** Druhý běh může vyrobit jiný nesmysl. Nabízí se
  generovat dvakrát a porovnat mezi sebou; kde se shodnou, je to
  nejspíš dobře. Neměřeno.
- Pozor na zápis „přeextrahování chyby neopraví, jen je přesune jinam" —
  platí pro slepé přeextrahování celé sekce, ne pro cílené
  přegenerování detekované položky. **Rozdíl je v tom, že se ví, co
  se opravuje.**

---

# BLOKUJÍCÍ KROK (23. 9. 2026): kontrola LAICKÉHO TVARU proti zdroji

**Tohle musí být hotové dřív, než se korpus rozšíří** — lokálně
i v cloudu. Podklad a čísla jsou v `poznatky.md` nahoře.

## Proč to je priorita

Dnes **obě kontroly ověřují `doslovne` proti zdroji, `laicky` neověřuje
nikdo.** Proto prošly:

    OMEPRAZOL  "kyselé řinčení do krku"     (má být kyselá regurgitace)
    ULTRACOD   "při ALENZII na paracetamol" (má být alergii)
    BISACODYL  "bolestí VE TŘASU"           (má být v řiti)
    ACIDUM AS. "ZAMEZOVÁNÍ LÉČBĚ stavů..."  (má být prevence a léčba)
    ZYRTEC     "ledviny přestaly fungovat"  (rozbitá věta)

Změřeno 23. 9.: **8 z 8 těchto případů zmizelo při pouhém druhém
spuštění qwenu** se stejným promptem a stejným vstupem. Není to tedy
neschopnost modelu, ale **nedeterminismus** — na 6 618 SPC ho vyrobí
kterýkoli model, lokální i cloudový. Přeextrahování nepomůže, jen to
přesune jinam. **Jediná obrana je detekce.**

Pozor: chyby výš jsou v korpusu **pořád**. Testovací běh je neopravil,
jen ukázal, že model by je podruhé neudělal.

## Proč nestačí to, co se nabízí první

- **Poměr slov bez opory ve zdroji NEFUNGUJE jako detektor
  vymýšlení.** Změřeno na 106 položkách: qwen 0,221, nano 0,240,
  luna 0,285–0,321. **Nejvyšší hodnotu má model, který je nejlepší** —
  protože skutečný překlad latiny do češtiny slova ze zdroje
  z definice nemá („kyselá regurgitace" → „návrat kyselého obsahu").
  Práh na tuhle metriku by zahazoval právě ty dobré překlady.
- **Slovníková kontrola sama nestačí.** Hunspell chytí `alenzie`
  (není to slovo), ale **`řinčení` i `třas` jsou platná česká slova** —
  projdou. Chyba je ve významu, ne v pravopisu.

## Návrh: dvě vrstvy, obě se musí změřit

- [ ] **vrstva 1 — slovník (hunspell).** Je v Postgresu, už se používá
      pro lematizaci ve fulltextu. Chytí nesmyslná slova typu
      `alenzie`. Levné, deterministické.
- [ ] **vrstva 2 — významová vzdálenost `laicky` vs `doslovne`.**
      Embedding bge-m3 běží lokálně a je zadarmo. „kyselé řinčení
      do krku" proti „kyselá regurgitace" by mělo sedět výrazně níž
      než správný překlad. **Tohle je ta vrstva, která chytí `řinčení`
      a `ve třasu`.**
- [ ] **prahovat až po změření**, ne od stolu. Sada: těch 8 známých
      případů jako pozitivní, celý zbytek korpusu jako negativní.
      Zajímá nás **falešně pozitivních** — kolik dobrých překladů by
      práh zahodil.
- [ ] rozhodnout, co s nálezem: zahodit `laicky` a nechat `doslovne`,
      nebo položku poslat na přeextrahování (pozor, viz výš — samo to
      nespraví, ale u nedeterministické chyby druhý pokus většinou
      projde)

## Co z toho padá jako vedlejší produkt

Kontrola opory klíče už dnes funguje jako **detektor zkomolené
češtiny ve zdrojovém textu** — na to nebyla stavěná (viz `poznatky.md`
22. 9., BISACODYL a ULTRACOD). Až bude vrstva 2 hotová, stojí za to
ji na tohle použít schválně.

---

# PLÁN K PROVEDENÍ TEĎ  (22. 9. 2026)

Vzniklo z auditu Codexu + vlastních měření. **Pořadí je záměrné** —
každý krok stojí na předchozím. Všechno níže je změřené, ne odhadnuté.
Čísla v závorkách jsou naměřená 22. 9. na živé databázi.

---

## KROK 0: Řádky se shodným textem  << ZAČÍT TADY

**OPRAVENO 22. 9.** Původní znění tohoto kroku tvrdilo, že indikace
mají 19 duplicitních řádků. **Byla to chyba měření** — počítalo se
`count(*) - count(DISTINCT (kod_sukl, obsah_text))`, což **ignoruje
rozměr „skupina pacientů"**. Po ověření v datech to vypadá jinak.

### Co v datech doopravdy je

    sekce             radku se     z toho lisi se    OPRAVDU
                    shodnym textem   skupinou      nadbytecnych
    indikace              29             29              0
    nezadouci_ucinky      32              0             32

**Indikace duplicitní NEJSOU.** ACC má 27 řádků indikací = 9 indikací
× 3 věkové skupiny (dospělí, dospívající, děti od 2 let). Skupina je
uložená v `sekce_atributy->>'skupina_kod'`. Je to legitimní údaj.

**Nežádoucí účinky duplicitní JSOU** — 32 řádků v 16 dvojicích, které
se neliší ničím.

### Problém A: skupina pacientů není v hledaném textu

`obsah_text` je u všech tří řádků ACC stejný, skupina v něm není.
Pro hledání jsou ty tři řádky **nerozlišitelné** — mají stejný
vektor i stejné TSV, takže obsadí tři místa z pěti týmž textem
a ostatní léky se nevejdou.

Zároveň se tím zahazuje užitečná informace: na dotaz **„průjem
u dětí"** by šlo trefit právě ten dětský řádek, ale dnes to nejde.

- [ ] rozhodnout: dostat skupinu do hledaného textu (pak jsou řádky
      rozlišitelné a dotaz „u dětí" má co trefit), NEBO je pro
      hledání sloučit a skupinu nechat jen jako metadata
- [ ] ZMĚŘIT obě varianty, nevybírat od stolu — přidání slov do
      textu stojí podobnost (0,03–0,05 za slovo)

### Problém B: skutečné duplicity v nežádoucích účincích

16 dvojic, které se neliší ani skupinou. Tyhle pryč.

- [ ] zjistit, jak vznikly
- [ ] deduplikovat v `ocisti_json.py` — deterministické, bez modelu
- [ ] kontrola do `evaluate.py` TEST 0

### Problém C: tentýž text dostal RŮZNÉ klíče

Nejnázornější důkaz, že generování klíče je loterie. Stejná indikace,
stejný zdrojový text, jeden běh extrakce — a tři různé klíče:

    ACC "dědičná nemoc s hustým hlenem v plicích"
        deti         -> "dědičná nemoc s hustým hlenem v plicích"
        dospeli      -> "hustý hlen v plicích"
        dospivajici  -> "dědičná nemoc s hustým hlenem"

    ACC "nemoc dýchacích cest způsobená hlenem..."
        deti         -> "nemoci dýchacích cest se ztíženým vykašláváním"
        dospeli      -> "HNIL dýchacích cest se špatným vykašláním"   <- nesmysl
        dospivajici  -> "nemoci dýchacích cest"

Tři řádky téže indikace tak dostanou **tři různé vektory klíče**
a na tentýž dotaz se seřadí různě.

- [ ] klíč počítat **jednou na každý RŮZNÝ zdrojový text**, ne na
      každý řádek. Je to deterministické, zadarmo to sníží loterii
      a odstraní tenhle rozpor.

### Jak ověřit

    -- POZOR na to, co vsechno radek ROZLISUJE. Krome skupiny pacientu
    -- jeste FREKVENCE a ORGANOVY SYSTEM: ACIFEIN ma "nevolnost" jako
    -- 'caste' u traveni a 'velmi vzacne' u imunity, ADVANTAN ma tyz
    -- ucinek ve dvou frekvencich. To duplicity NEJSOU.
    SELECT count(*) - count(DISTINCT (kod_sukl, sekce, obsah_text,
           coalesce(sekce_atributy->>'skupina_kod','-'),
           coalesce(frekvence,'-'), coalesce(organovy_system,'-')))
    FROM leciva_search WHERE sekce<>'atributy';

    -- tentyz text musi mit VSUDE tentyz klic
    SELECT count(*) FROM (
      SELECT kod_sukl, sekce, obsah_text FROM leciva_search
      GROUP BY 1,2,3 HAVING count(DISTINCT coalesce(klic,'')) > 1) q;

Obojí má vyjít 0. Pozor: `naplni_db.py --znovu` to NEOPRAVÍ,
duplicita i rozpor v klíčích jsou už ve zdrojovém JSON.

### Poučení k zapsání

Měřit „duplicitu" přes shodu jednoho sloupce je past, když tabulka
nese víc rozměrů. Řádek může mít shodný text a přesto nést jinou
informaci.

---

## KROK 0,5: Opravit, JAK se hledá ve slovníku dotazů

### Co je špatně

`rozsir()` v `common/dotazy.py` hledá klíč slovníku jako **podřetězec**:

    if _bez_diakritiky(klic) in d:

„Podřetězec" znamená „posloupnost znaků kdekoliv uvnitř", ne „celé
slovo". Slovo `tlak` je obsažené v `nízký tlak`, v `tlak v uchu`
i v `vysoký tlak` — pro počítač je to ve všech třech případech tatáž
shoda.

### Příklad 1 — OPAČNÝ VÝZNAM

    "nízký tlak"    -> ['nízký tlak', 'vysoký krevní tlak', 'hypertenze']
    "tlak v uchu"   -> ['tlak v uchu', 'vysoký krevní tlak', 'hypertenze']

Uživatel se ptá na NÍZKÝ tlak a hledání mu k dotazu přičte VYSOKÝ.
„Tlak v uchu" není krevní tlak vůbec. ACECOR (lék na vysoký tlak)
pak dostane skóre 1,000, protože se porovnává s textem, který mu
sedí doslova.

### Příklad 2 — ROZŠÍŘENÍ SE NESPUSTÍ, KDYŽ JE SLOVO SKLOŇOVANÉ

    "rýma"      -> ['rýma', 'ucpaný nos', 'zánět sliznice nosu']
    "rýmu"      -> ['rýmu']                      <- NIC
    "mám rýmu"  -> ['mám rýmu']                  <- NIC

Klíč ve slovníku je `rýma`. Řetězec „rýma" ale **není obsažen**
v „rýmu" (poslední písmeno se liší), takže se rozšíření vůbec
nespustí. Proto „mám rýmu" vrací ENDITRIL, HIDRASEC a IMODIUM —
tři léky na PRŮJEM.

### Příklad 3 — SLOVNÍK JE V KMENECH NEKONZISTENTNÍ

    "kašel"  -> ['kašel', 'vykašlávání hlenu']
    "kašlu"  -> ['kašlu', 'kašel', 'vykašlávání hlenu', 'zánět průdušek']

Tytéž potíže, jiné výsledky. `CLAUDE.md` říká, že klíče slovníku jsou
KMENY (`kasl`), aby prošly skloňováním. U `kasl` to platí, u `rýma`
ne — `rýma` je plný 1. pád. Nekonzistence se projevuje jako
„někdy to funguje, někdy ne".

### Co udělat

- [ ] hledat klíč na HRANICI SLOVA, ne jako podřetězec
      (`\mtlak\M` v regulárním výrazu, nebo porovnávat po slovech)
- [ ] NEBO ještě lépe: použít lemmatizaci, kterou už máme —
      hunspell v Postgresu umí `rýmu` -> `rýma` (viz poznatky 4.9.)
- [ ] projít `slovnik_dotazu.json` a sjednotit: buď všude kmeny,
      nebo všude 1. pád + lemmatizace
- [ ] opravit záznamy, kde varianta MĚNÍ VÝZNAM (`nízký tlak`
      nesmí dát `hypertenze`)

### Jak ověřit

Po opravě musí platit:

    "nízký tlak"  -> NEobsahuje 'hypertenze'
    "mám rýmu"    -> obsahuje 'ucpaný nos'
    "kašel"       -> tytéž varianty jako "kašlu"

---

## KROK 0,7: Nesmyslná laická zjednodušení  << NOVÉ, 22. 9.

### Co je špatně

Model při převodu do laické podoby vyrábí slova, která **v češtině
neexistují nebo znamenají něco jiného**. Nejde o kostrbatý sloh —
jde o to, že výsledek je v indexu a **uživatel ho vidí**.

Obě kontroly to pustí, protože obě ověřují `doslovne` proti zdroji.
**Laický tvar se dnes neověřuje nikde** (známý nedodělek).

### Příklady — všechny jsou TEĎ v živém indexu

**a) Vymyšlené slovo**

    OMEPRAZOL  "léčba pálení žáhy a kyselé ŘINČENÍ do krku"
               -> má být „kyselé říhání" / „návrat kyselého obsahu"
               -> řinčení je zvuk kovu

    ACC        klíč „HNIL dýchacích cest se špatným vykašláním"
               -> ve zdroji je HLEN

    OLYNTH     "ROZDĚLÁNÍ operace k odstraňování hypofýzy"
               -> má být „prodělaná operace hypofýzy"

    DITHIADEN  "Quinckeho edém není TVAROHOVÝ otok"
               -> zachyceno kontrolou, ale ukazuje týž vzor

**b) OBRÁCENÝ VÝZNAM — nejhorší případ**

    ACIDUM ASCORBICUM
        zdroj:  „prevence a léčba stavů nedostatku vitaminu C"
        laicky: „ZAMEZOVÁNÍ LÉČBĚ stavů, kdy tělu chybí vitamín C"

    Z „prevence a léčba" se stalo „zamezování léčbě". Lék, který
    nedostatek vitaminu C LÉČÍ, má v indexu napsáno, že léčbě BRÁNÍ.

    ERCEFURYL  „akutní průjem" -> „náhlý ZÁŠKRT" (difterie)
               už opraveno, ale prošlo to OBĚMA kontrolami

**c) Překlep, který mění význam**

    ZYRTEC     "OBECNÍ skupina 10 mg" -> má být „obecná skupina"

**d) Zkomolená čeština — nalezeno 22. 9., taky v živém indexu**

    ULTRACOD   "při ALENZII na paracetamol"   -> má být „alergii"
    BISACODYL  "zácpa spojená s bolestí VE TŘASU, prasklinami nebo
                krvácenými žilkami"           -> má být „v řiti"
                (SPC: zácpa spojená s bolestí v řiti, fisurami, hemoroidy)
    AFRIN      klíč „zanícená KŮŽA a sliznice" -> má být „kůže"
    ERCEFURYL  klíč „...způsobený BACTERIAMI"  -> má být „bakteriemi"

Tyhle čtyři našla mimochodem **kontrola opory klíče** — klíč obsahoval
slovo, které ve zdroji není, protože zkomolený je ZDROJ, ne klíč.
U ULTRACODU a BISACODYLU je klíč správnější než text, ze kterého vznikl.

### Proč to vadí

1. **Uživatel to čte.** Je to text zobrazený ve výsledku, ne interní
   mezikrok. U léků je nesrozumitelný nebo obrácený popis riziko.
2. **Kazí to hledání.** „Kyselé řinčení" nikdo nehledá, takže se
   pasáž nenajde na to, na co by měla.
3. **Nechytí to žádný test.** TEST 0 kontroluje strukturu, ne smysl.

### Co udělat

- [ ] **Deterministická kontrola napřed**: laický tvar projít proti
      slovníku češtiny, který UŽ MÁME — hunspell v Postgresu
      (261 tis. slov). Slovo, které hunspell nezná a není to název
      látky, je podezřelé. Chytlo by „řinčení"? NE, to je české
      slovo. Chytlo by „hnil"? Taky ne. **Tohle najde jen překlepy,
      ne záměny — a to je potřeba vědět dopředu, ne až po nasazení.**
- [ ] **Kontrola jiným modelem, ale na SPRÁVNOU otázku.** Dnešní
      `zkontroluj_modelem.py` se ptá „sedí `doslovne` na zdroj?".
      Chybí otázka **„znamená `laicky` totéž co `doslovne`?"**
      Zpětný překlad: nech model z laického tvaru uhodnout odborný
      a porovnej. „Zamezování léčbě" -> „prevence léčby" != zdroj.
- [ ] **Vyjmenovat zakázané obraty.** „Zamezování" u indikace je
      skoro vždy chyba — indikace je to, NA CO lék je.
- [ ] přidat do `evaluate.py` TEST 0 kontrolu na známé nesmysly
      (seznam v `slovnik_rucni.json`), ať se nevrátí
- [ ] opravit těch 6 nálezů výše ručně v `slovnik_rucni.json`

### Jak ověřit

    SELECT nazev, obsah_text FROM leciva_search s JOIN leciva l USING (kod_sukl)
    WHERE obsah_text ~* '(řinčení|hnil |obecní skupina|zamezování|rozdělání)';

Má vrátit prázdno.

### Pozor

`CLAUDE.md` varuje: **přeextrahování chyby neopraví, jen je přesune
jinam.** Tyhle opravy patří do `slovnik_rucni.json`, ne do dat —
jinak je příští běh extrakce přepíše.

---

## KROK 0,8: Vyzkoušet qwen3.8-flash-next na generování  << AŽ BUDE STAŽENÝ

### Proč

Všechno v KROKU 0,7 i většina potíží s klíči (KROK 3) jsou vady
**generování**, ne vyhledávání. Ladit nad nimi prahy a váhy je ladění
nad šumem. Dnešní `MODEL_HLAVNI` = `qwen3.5:122b` vyrábí mimo jiné
„kyselé řinčení do krku", „zamezování léčbě" a klíč „onemocnění".

Model je potřeba **stáhnout** (zatím není v Ollamě).

### Jak to změřit, ať to není dojem

Nepouštět celou pipeline a nekoukat, jestli „to vypadá líp". Existuje
hotová sada případů, u kterých se ví, jak má výsledek vypadat.

- [ ] stáhnout model, přidat do `common/config.py` vedle `MODEL_HLAVNI`
      (nepřepisovat ho — musí jít porovnat oba)
- [ ] **A) známé nesmysly**: pustit oba modely na TYCHŽ zdrojových
      textech a porovnat, jestli se chyba zopakuje:

        OMEPRAZOL   "kyselé řinčení do krku"      má být říhání
        ACIDUM AS.  "zamezování léčbě stavů"      má být prevence a léčba
        ULTRACOD    "při alenzii na paracetamol"  má být alergii
        BISACODYL   "bolestí ve třasu"            má být v řiti
        ACC         klíč "hnil dýchacích cest"    ve zdroji je hlen
        ZYRTEC      "obecní skupina 10 mg"        má být obecná
        ERCEFURYL   "náhlý záškrt"                má být akutní průjem
        DITHIADEN   "tvarohový otok"              Quinckeho edém
        AFRIN       klíč "zanícená kůža"          má být kůže
        ERCEFURYL   klíč "...bacteriami"          má být bakteriemi

- [ ] **B) klíče**: pustit `doplni_klice.py` oběma modely na týchž
      položkách a porovnat
      - kolik klíčů je delších než 4 slova (dnes **24,4 %**)
      - kolik klíčů je jen obecná kategorie (dnes např. `onemocnění`,
        `náhlá bolest`, `křeče a bolest`)
      - **jak moc je model sám se sebou ve shodě** — pustit DVAKRÁT na
        tomtéž a porovnat. Dnešní model dává na týchž datech 67 % null
        a tatáž indikace ve třech věkových skupinách dostala tři různé
        klíče.
- [ ] **C) `test_klice.py`** — ten už na porovnávání na vzorku je
- [ ] **D) až pak** `evaluate.py` na celé sadě; zmrazený vzorek to teď
      umožňuje porovnat poctivě

### Pozor

- **Přeextrahování chyby neopraví, jen je přesune jinam.** Měřit se
  musí na TYCHŽ vstupech, ne „pustit znovu a uvidíme".
- Ruční opravy patří do `slovnik_rucni.json`, ne do dat.
- Kontrolní model (`MODEL_KONTROLY` = `gemma4:31b`) musí zůstat **JINÝ**
  než ten, co data vyrobil. Kdyby se nový model nasadil na generování,
  nesmí zároveň kontrolovat.
- Všechno lokálně, **žádný cloud** — na účtu OpenAI jsou jednotky dolarů.

---

## KROK 1: Regresní sada se ZMRAZENÝM vzorkem

### Co je špatně dnes

`evaluate.py` `test2` (auto-recall) losuje 60 řádků takhle:

    SELECT setseed(...); ... ORDER BY random() LIMIT 60

Vypadá to jako pevně daný vzorek, protože seed je pevný. **Není.**
`random()` přiřazuje čísla řádkům v tom pořadí, v jakém je databáze
čte z disku. Když se tabulka přepíše, pořadí se změní — a vypadne
jiný vzorek, PŘESTOŽE je seed týž.

### Příklad

Změřeno na dočasných tabulkách: tatáž data, tentýž seed, jen jiné
fyzické pořadí řádků:

    vzorek_a | vzorek_b | shodnych
          60 |       60 |        5

**Z 60 řádků se shoduje PĚT.**

A protože postup „po změně dat" končí `naplni_db.py --znovu`
(= přepis tabulky) a pak `evaluate.py`, **každá změna dat vzorek
přelosuje**. Číslo před změnou a po ní měří jiné položky.

Přesně tak vzniklo „zhoršení" 47/47 -> 46/47, které žádné zhoršení
nebylo.

### Druhá vada: testy neaplikují PRÁH

`test4` (parafráze) volá `hledej(...)` **bez `prah`**, a výchozí
hodnota v `hledej()` je `0.0`. Měří se tedy stav, který uživatel
nikdy nevidí:

    prah 0,00 (jak měří test4):  10/10
    prah 0,60 (co vidí uživatel): 9/10
        'mám rýmu' čekal OLYNTH, dostal ENDITRIL, HIDRASEC, IMODIUM

Zelená tabulka tím schovává, že dotaz na rýmu vrací léky na průjem.

### Co udělat

- [ ] vzorek NELOSOVAT z tabulky — zmrazit seznam do souboru
      (`vzorek_eval.json` se seznamem `id` nebo rovnou textů)
- [ ] do výpisu přidat, na jakém vzorku se měřilo
- [ ] předávat `prah` do `test2` i `test4`, nebo aspoň vypisovat
      obě čísla (bez prahu / s prahem)
- [ ] přidat sadu ZÁMĚN: ke každému dotazu nejen „co se má najít",
      ale i „co se najít NESMÍ"

### Příklad takové dvojice

    dotaz:      "mám rýmu"
    MÁ vrátit:  OLYNTH / AFRIN (nosní pasáže)
    NESMÍ:      AMOKSIKLAV "zánět kosti"
                OMEPRAZOL "zánět jícnu"
                ENDITRIL / HIDRASEC / IMODIUM (průjem)

POZOR: zakázat se má **PASÁŽ, ne celý lék**. AMOKSIKLAV má v datech
taky legitimní nosní indikaci („akutní bakteriální zánět vedlejších
nosních dutin"), takže zakázat celý AMOKSIKLAV by bylo špatně.

---

## KROK 2: Fulltext na AND uvnitř pojmu, OR mezi pojmy

### Co je špatně

Dnes se z dotazu i ze všech jeho variant udělá jeden pytel slov
a zeptá se „obsahuje řádek NĚKTERÉ z nich?".

Pro dotaz `rýma` vzniknou varianty `rýma`, `ucpaný nos`,
`zánět sliznice nosu`, takže se fakticky hledá:

    rýma NEBO ucpaný NEBO nos NEBO zánět NEBO sliznice NEBO nosu

Stačí tedy, aby řádek obsahoval **jediné slovo „zánět"**, a už se
počítá jako shoda.

### Příklad — co to natáhne

Dotaz na rýmu takhle trefí OSM řádků AMOKSIKLAVU:

    zánět kosti          zánět zubu
    zánět kůže           zánět středního ucha
    zánět nosních dutin  zánět močového měchýře
    zánět průdušek       zánět ledvinné pánvičky

Doslova každý zánět v korpusu.

### Jak to má být

Uvnitř JEDNOHO pojmu vyžadovat VŠECHNA slova, mezi pojmy stačit
kterýkoliv:

    rýma NEBO (ucpaný A ZÁROVEŇ nos) NEBO (zánět A ZÁROVEŇ sliznice A ZÁROVEŇ nos)

Zápis pro Postgres: `rýma | (ucpaný & nos) | (zánět & sliznice & nos)`

### Změřeno

    sestaveni fulltextoveho dotazu          zasazenych radku
    dnes: jen puvodni "ryma"                       3
    rozsireni, OR mezi vsemi slovy                43
    rozsireni, AND uvnitr, OR mezi pojmy           5

U samostatného `zánět kůže` je to ještě víc vidět: **43 -> 1**.

Po opravě: AFRIN a OLYNTH shodu **mají**, AMOKSIKLAV „zánět kosti"
a OMEPRAZOL „zánět jícnu" **nemají** (ověřeno řádek po řádku).

### POZOR — na co si dát majzl

**AND se NESMÍ pustit na původní větu uživatele.** Věta „mám rýmu"
obsahuje i sloveso, takže přísný AND by vyžadoval i „mít" a nenašel
by NIC. Proto dvoukolejně:

- řízený pojem (varianta ze slovníku, klíč) -> AND uvnitř
- původní věta uživatele                    -> OR, nebo do FTS vůbec

### Co udělat

- [ ] v `common/hledani.py` přestat stavět `fts_dotaz` jen z `dotaz`
      a zapojit varianty (dnes jdou POUZE do vektorů — viz TODO 2)
- [ ] složit tsquery jako OR mezi pojmy, AND uvnitř pojmu
- [ ] původní větu držet odděleně
- [ ] AŽ POTOM znovu měřit váhu fulltextu (dnes 20 %) — ta hodnota
      se nastavovala v době, kdy fulltext skoro vždycky vracel nulu,
      takže dnes nic neznamená

---

## KROK 3: Omezit, kdy smí KLÍČ sám prosadit výsledek

### Co je špatně

Každý řádek má **dva vektory** — jeden za celý text, druhý za klíč.
Při hledání se bere LEPŠÍ z nich. Komentář v kódu říká „maximum může
jen pomoci". Pro **číslo u jednoho řádku** to platí. Pro **pořadí
výsledků** neplatí — nesouvisející řádek se tím taky zvedne.

### Příklad CELÝ, včetně zdrojového textu (doměřeno 22. 9.)

Dotaz **„rýma"** se rozšíří na `ucpaný nos` a `zánět sliznice nosu`.

**a) AMOKSIKLAV — antibiotikum, skončí na dotaz o rýmě DRUHÉ**

    ZDROJ (SPC)  "infekce kostí a kloubů, zejména osteomyelitida"
    LAICKY       "infekce kostí a kloubů, zejména zánět kosti
                  (infekce kostí a kloubů, zejména zánět kosti)"
    KLIC         "zánět kosti"

    proti laickemu textu   0,513   <- POD prahem 0,60, neviditelne
    proti KLICI            0,692   <- NAD prahem, druhe misto
    rozdil                 0,179

    Klic se trefil na variantu "zánět sliznice nosu".

**b) OMEPRAZOL FARMAX — lék na žaludek, čtvrtý**

    ZDROJ (SPC)  "Dlouhodobá léčba pacientů se zhojenou refluxní ezofagitidou"
    LAICKY       "dlouhodobá léčba u pacientů, kteří měli zánět jícnu
                  a ten již zahojil"
    KLIC         "zánět jícnu"

    proti laickemu textu   0,450
    proti KLICI            0,675
    rozdil                 0,225

**c) ACC — lék na kašel, páté místo**

    ZDROJ (SPC)  "astmoidní bronchitida"
    LAICKY       "zánět průdušek s dušností jako u astmatu (astmoidní bronchitida)"
    KLIC         "zánět průdušek s dušností"

    proti laickemu textu   0,569
    proti KLICI            0,657

### Škoda změřená na celém pořadí

    DNES (text i klic)            BEZ KLICU (jen text)
    0,726  OLYNTH                 0,682  AFRIN
    0,692  AMOKSIKLAV  nesouvisi  0,674  OLYNTH
    0,688  AFRIN                  0,609  MAALOX
    0,675  OMEPRAZOL   nesouvisi
    0,657  ACC         nesouvisi
    0,623  ABAKTAL

    nad prahem: 8                 nad prahem: 3

**Klíče zvedly počet výsledků nad prahem z 3 na 8** a tři z nich
s rýmou nesouvisí vůbec.

### Proč to dělá — a proč to není náhoda

Klíč je KRÁTKÝ. To je jeho přednost (krátká fráze neředí význam,
HIDRASEC šel z 0,515 na 0,807) a zároveň přesně ta vada: **krátká
fráze se páruje s jinou krátkou frází podobného tvaru.** „Zánět
sliznice nosu" a „zánět kosti" jsou obě jmenné fráze tvaru
„zánět + orgán". Dlouhý původní text tu shodu ředil — a právě to
ředění klíč odstranil.

Komentář v kódu říká „maximum může jen pomoci". Pro ČÍSLO u jednoho
řádku to platí. Pro POŘADÍ ne — zvedne se i řádek, který se zvednout
neměl.

### Druhá věc: pojistka u klíče je POMĚROVÁ

`klic_ma_oporu()` vyžaduje, aby aspoň POLOVINA významových slov klíče
byla ve zdrojovém textu. Jedno vymyšlené slovo se tedy sveze na
ostatních.

**Příklad 1** — ověřeno, projde:

    klic  "zánět kosti"
    zdroj "zánět sliznice nosu"
    -> "zánět" sedí, "kosti" nesedí -> 1 ze 2 = 50 % -> PROŠLO

**Příklad 2** — skutečný klíč v datech u ACC:

    klic  "hnil dýchacích cest se špatným vykašláním"
    zdroj "nemoc dýchacích cest způsobená HLENEM, který se špatně vykašlává"

    cest       -> sedí
    dychacich  -> sedí
    spatnym    -> sedí
    vykaslanim -> sedí
    hnil       -> BEZ OPORY        4 z 5 = 80 % -> PROŠLO

„Hnil" je zkomolenina, ve zdroji je „hlen". Je to týž vzor jako známý
nedodělek „akutní průjem -> náhlý záškrt".

### Co udělat

- [ ] zvážit pravidlo „ŽÁDNÉ významové slovo bez opory" místo poměru
- [ ] ZMĚŘIT, kolik klíčů by takové pravidlo zahodilo, NEŽ se nasadí
      (poměr 0,5 tam někdo dal z nějakého důvodu)
- [ ] omezit, aby rozšíření × krátký klíč samo prosadilo výsledek —
      např. vyžadovat potvrzení celým pojmem
- [ ] POZOR: klíč nesmí potvrzovat sám sebe. Index je dnes
      `klic || ' ' || obsah_text`, takže AND přes variantu se může
      splnit napůl z klíče a napůl z textu. Pro kontrolu opory je
      silnější důkaz PŮVODNÍ text.

### Čím to NENÍ

Pozor na zkratku „zakázat obecná slova jako zánět a bolest".
Pravidlo „aspoň dvě slova, z toho jedno konkrétní" NESTAČÍ —
`zánět sliznice nosu` i `zánět kosti` ho oba splňují. Rozhoduje
soulad významu, ne počet slov. A u obecného dotazu může být „bolest"
přesně to, co člověk hledá.

---

## KROK 4: Teprve teď prahy a váhy

Až když kroky 0–3 sedí, má smysl znovu měřit práh a váhu fulltextu.
Dřív ne — dnes se váha ladí nad OR, který prokazatelně přitahuje šum,
takže by se optimalizovalo na špatných datech.

- [ ] `evaluate.py --prahy` a `--vahy` na NOVÉ, zmrazené sadě
- [ ] rozlišit pravidla pro IDENTITU léku (název, látka, síla — ty
      řeší relační filtr) a pro OBSAHOVÉ hledání (příznaky)

---

## TODO: KLIC - DELKA SE NEVYNUCUJE A GENEROVANI JE LOTERIE

Zmereno 22.9. Podrobne v `poznatky.md`.

Pojistka `klic_ma_oporu()` NENI viník chybejicich klicu - zahodila
0 z 55. Klic se dela z `laicky` (uz zjednoduseny text), takze je to
ZKRACENI, ne dalsi preklad. Skutecne priciny jsou dve jine:

### a) delka klice se nekontroluje

Pojistka overuje jen oporu ve zdroji, pravidlo "1-4 slova" z promptu
nevynucuje NIKDO:

    24,4 % klicu (40 ze 164) je delsich nez 4 slova
     8 slov  TALVOSILEN  "středně silná až silná bolest s různou příčinou"
     7 slov  OMEPRAZOL   "pálení žáhy a kyselé řinčení do krku"

Jde to proti duvodu, proc klic existuje (dlouha veta redi vyznam).

- [ ] pridat do `klic_ma_oporu()` (nebo vedle nej) tvrdy limit na pocet
      slov - je to deterministicke, model to nemuze obejit
- [ ] rozhodnout, co s klicem pres limit: zahodit, nebo orezat?
      ZMERIT obe varianty, nevybirat od stolu
- [ ] zahodit klic, ktery NENI kratsi nez zdroj (dnes 5 klicu) - takovy
      klic neusetri nic

### b) generovani klice je nedeterministicke

Z 55 dlouhych polozek bez klice model 67,3 % vratil jako null, ale pri
novem behu by 32,7 % klic DOSTALO. Tytez polozky, tentyz prompt, jiny
vysledek. Tyz vzor jako u routeru.

- [ ] POZOR: doplnit tech 55 chybejicich klicu by SKODILO. Je to skoro
      samá kontraindikace "alergie na účinnou látku", a `alergie` uz je
      klicem 6x - presne vzor z TODO 1. Az PO vyreseni obecnych slov.

## TODO 1: KLIC ZVEDA I NESOUVISEJICI VECI  << TOP

Zmereno 4.9. Dotaz "mám rýmu" se pres `slovnik_dotazu.json` rozsiri
o "zánět sliznice nosu" - a to pritahne VSECHNO se slovem zanet:

    0,726  OLYNTH      přetížení nosu způsobené zánětem sliznice   spravne
    0,692  AMOKSIKLAV  infekce kostí a kloubů, zejména ZÁNĚT KOSTI  SPATNE
    0,675  OMEPRAZOL   zánět jícnu                                  spatne
    0,657  ACC         zánět průdušek                               spatne

Je to POTRETI tyz vzor - po "zánět kůže" (trefovalo AMOKSIKLAV)
a po klici "bolest" (trefovalo vsechno bolestive).

**Obecne slovo v hodnote ciselniku pritahne celou svou tridu.**

- [ ] projit `slovnik_dotazu.json` a najit prilis obecne hodnoty
      (zanet, bolest, infekce, porucha)
- [ ] zvazit pravidlo: hodnota musi mit aspon DVE vyznamova slova,
      z nichz jedno je konkretni (organ, cast tela)
- [ ] zvazit totez u KLICU z extrakce - OLYNTH ma klic "zánět dutin",
      AMOKSIKLAV ma zanet v devíti indikacich
- [ ] pridat do `evaluate.py` test, ktery to chyti automaticky

## TODO 2: ROZSIRENI DOTAZU NEJDE DO FULLTEXTU  << TOP

Zmereno 4.9. `hledani.py` stavi `fts_dotaz` JEN z `dotaz`, varianty ze
slovniku se pouziji **pouze pro vektory**:

    dotaz 'rýma'                 -> OLYNTH fts =  0,0
    dotaz 'zánět sliznice nosu'  -> OLYNTH fts = 12,0

Pritom "zánět sliznice nosu" JE hodnota ze slovniku pro "rýmu" a JE
v indikaci OLYNTHU doslova. Fulltext ji nikdy nedostane.

Promarnena prilezitost: ciselnik byl postaveny tak, aby mapoval laicky
vyraz na FORMULACI Z DOKUMENTU - a presne na to je fulltext nejlepsi,
protoze skoruje binarne (0 nebo trefa).

- [ ] poslat do `websearch_to_tsquery` VSECHNY varianty, ne jen `dotaz`
      (spojit pres OR, stejne jako se dnes spojuji slova)
- [ ] POZOR: souvisi s TODO 1 - kdyz se do fulltextu dostane obecna
      hodnota jako "zánět", nafoukne to i tam. Resit v tomto poradi.
- [ ] premerit prah a vahu fulltextu; dnesnich 20 % bylo nastaveno
      v dobe, kdy fulltext skoro vzdycky mlcel

## RUCNE PROJIT – sekce oznacene kontrolou

**28 sekci** = SJEDNOCENI dvou behu CELE PIPELINE.

Nestaci vzit posledni bezh, ale duvod je jiny, nez to vypadalo na prvni
pohled. Zmereno:

  - KONTROLA nad TYMIZ daty je stabilni: dva behy daly 20 a 20 sekci,
    shoda 19, tedy 90 %. Poustet kontrolu opakovane se NEVYPLATI.
  - Rozptyl delá EXTRAKCE. Mezi dvema behy cele pipeline se shodlo jen
    11 sekci z 28 (39 %), protoze preextrahovanim vznikla jina data -
    jine formulace, jine chyby.

Sjednoceni je tu tedy proto, ze kazdy bezh extrakce vyrobi trochu jinou
sadu chyb, ne proto, ze by kontrola byla nespolehliva.

Legenda: `oba` = oznaceno v obou bezich pipeline (nejjistejsi
kandidat - chyba se reprodukovala), `jen 1.` / `jen 2.` = jen v jednom.

Zdroj pravdy je `data/leciva/<kod>/sekce/<sekce>.md` proti
`data/leciva/<kod>/json/<sekce>.json`. Duvody v `json/_stav.json`.

| # | lecivo | sekce | behy | oznaceno | poznamka |
|---|---|---|---|---|---|
| 1 | `0000009_ACYLCOFFIN` | nezadouci_ucinky | jen 2. | 1/46 |  |
| 2 | `0002479_DITHIADEN` | indikace | oba | 3/6 |  |
| 3 | `0021727_ACIFEIN` | kontraindikace | oba | 1/9 |  |
| 4 | `0021727_ACIFEIN` | nezadouci_ucinky | jen 2. | 1/54 |  |
| 5 | `0028839_AERIUS` | indikace | jen 1. | - |  |
| 6 | `0094156_ABAKTAL` | indikace | oba | 2/9 | VYMYSLENA INDIKACE – 'nadory plic' u ANTIBIOTIKA. VAZNE. |
| 7 | `0094156_ABAKTAL` | nezadouci_ucinky | oba | 2/44 |  |
| 8 | `0151435_ALGESAL` | indikace | jen 1. | - |  |
| 9 | `0151435_ALGESAL` | nezadouci_ucinky | oba | 1/1 |  |
| 10 | `0214435_CONTROLOC` | indikace | oba | 2/3 |  |
| 11 | `0216273_AFRIN` | indikace | oba | 1/4 |  |
| 12 | `0216273_AFRIN` | kontraindikace | jen 2. | 1/8 |  |
| 13 | `0216273_AFRIN` | nezadouci_ucinky | jen 1. | - |  |
| 14 | `0226195_ACC` | indikace | jen 2. | 1/5 |  |
| 15 | `0226195_ACC` | nezadouci_ucinky | jen 2. | 1/24 |  |
| 16 | `0232958_OMEPRAZOL_FARMAX` | indikace | oba | 3/12 |  |
| 17 | `0239773_OLYNTH` | indikace | jen 2. | 1/5 |  |
| 18 | `0239773_OLYNTH` | kontraindikace | oba | 1/5 | OBRACENY VYZNAM – zdroj 'deti DO 2 let'. VAZNE. |
| 19 | `0243462_ACIDUM_ASCORBICUM_BBP` | indikace | oba | 1/3 |  |
| 20 | `0247147_ADVANTAN` | indikace | jen 2. | 2/3 |  |
| 21 | `0247147_ADVANTAN` | nezadouci_ucinky | jen 1. | - |  |
| 22 | `0249287_ALTHYXIN` | kontraindikace | jen 2. | 1/8 |  |
| 23 | `0254048_PARALEN` | indikace | jen 2. | 2/10 |  |
| 24 | `0254542_AMOKSIKLAV` | indikace | oba | 1/8 |  |
| 25 | `0254542_AMOKSIKLAV` | nezadouci_ucinky | jen 1. | - |  |
| 26 | `0260415_BISACODYL_KRKA` | indikace | jen 2. | 1/9 |  |
| 27 | `0260415_BISACODYL_KRKA` | kontraindikace | jen 1. | - |  |
| 28 | `0285675_ALGIFEN_NEO` | indikace | jen 2. | 1/9 |  |

### Duvody z posledniho behu

**0000009_ACYLCOFFIN / nezadouci_ucinky** (1 z 46)
- V textu je 'Žaludeční hypersekrece' samostatně a 'akutní pankreatitida v důsledku hypersenzitivní reakce'. Položka chybně spojuje hypersekreci s hyper

**0002479_DITHIADEN / indikace** (3 z 6)
- v textu není zmíněna intenzita reakcí (těžké)
- text zmiňuje astma bronchiale a rýmu, nikoliv obecný záchvat na dýchání
- Quinckeho edém není tvarohový otok

**0021727_ACIFEIN / kontraindikace** (1 z 9)
- Zdroj uvádí chirurgické výkony spojené s masivnějším krvácením (obecně), nikoliv pouze ty nedávno provedené.

**0021727_ACIFEIN / nezadouci_ucinky** (1 z 54)
- ucinek_laicky 'krvácení ze dvanácti' je věcně nesprávný překlad pro 'krvácení z dásní'

**0094156_ABAKTAL / indikace** (2 z 9)
- zdroj zmiňuje exacerbaci CHOP/bronchitidy, nikoliv zánět plic
- zdroj uvádí gonokokovou uretritidu a cervicitidu, ne hnisavý zánět

**0094156_ABAKTAL / nezadouci_ucinky** (2 z 44)
- Nesprávná frekvence: ve zdroji je Trombocytopenie uvedena jako 'Vzácné', nikoliv 'Méně časté' (v tabulce je v kolonce Vzácné).
- V textu je uvedeno 'Zvýšení hladin... alkalických fosfatáz', položka uvádí pouze název enzymu 'Alkalické fosfatázy'.

**0151435_ALGESAL / nezadouci_ucinky** (1 z 1)
- Nesouhlasí frekvence: ve zdroji je 'ojediněle', v položce 'není známo'

**0214435_CONTROLOC / indikace** (2 z 3)
- ve zdroji není zmínka o pálení žáhy, pouze o refluxní chorobě jícnu
- terapéutická indikace je konkrétně prevence vředů při léčbě NSAID, nikoliv obecná ochrana žaludku

**0216273_AFRIN / indikace** (1 z 4)
- zdroj hovoří o alergické rinitidě obecně, nikoliv konkrétně o alergii na pyl

**0216273_AFRIN / kontraindikace** (1 z 8)
- Zdroj uvádí akutní onemocnění koronárních cév nebo kardiální astma, nikoliv nádor nebo selhání srdce

**0226195_ACC / indikace** (1 z 5)
- zdroj zmiňuje bronchiální astma a astmoidní bronchitidu, nikoliv astmoidní kašel

**0226195_ACC / nezadouci_ucinky** (1 z 24)
- V textu je uvedeno pouze, že byla prokázána snížená agregace trombocytů, ale není to uvedeno jako vedlejší účinek s konkrétní frekvencí v rámci systém

**0232958_OMEPRAZOL_FARMAX / indikace** (3 z 12)
- zdroj specifikuje návrat konkrétně duodenálních a žaludečních vředů, nikoliv vředů obecně
- zdroj specifikuje prevenci pouze u rizikových pacientů při užívání NSAID
- Zollinger-Ellisonův syndrom není v textu popsán jako hormonální

**0239773_OLYNTH / indikace** (1 z 5)
- text uvádí rinitidu spojenou s infekcemi, nikoliv léčbu samotných infekcí

**0239773_OLYNTH / kontraindikace** (1 z 5)
- Zdroj zmiňuje transsfenoidální hypofyzektomii, nikoliv operaci nosní přepážky

**0243462_ACIDUM_ASCORBICUM_BBP / indikace** (1 z 3)
- položka není v textu uvedena

**0247147_ADVANTAN / indikace** (2 z 3)
- v textu není zmíněno
- v textu není zmíněno

**0249287_ALTHYXIN / kontraindikace** (1 z 8)
- Zdroj uvádí kombinaci levothyroxinu a tyreostatik, nikoliv tohoto léku s jinými proti štítné žláze

**0254048_PARALEN / indikace** (2 z 10)
- text uvádí horečku PŘI infekcích, nikoliv samotné infekce jako indikaci
- zdroj výslovně uvádí NEZÁNĚTLIVÉ etiologie

**0254542_AMOKSIKLAV / indikace** (1 z 8)
- text hovoří o exacerbaci chronické bronchitidy, nikoliv obecně o kašli a dušení

**0260415_BISACODYL_KRKA / indikace** (1 z 9)
- zdroj hovoří o usnadnění defekace u pacientů léčených opioidy, nikoliv o zácpě způsobené těmito léky

**0285675_ALGIFEN_NEO / indikace** (1 z 9)
- tenesmy močového měchýře jsou křečivé bolesti při močení, nikoliv bolest způsobená častým močením

## RUCNE PROJIT – ciselnik pojmu

Soubor `slovnik_pojmu.md`, sekce **K rucnimu projiti**.
Posledni bezh: **24 oznacenych ze 426 dvojic**.

Opravy patri do **`slovnik_rucni.json`** – ten se nikdy negeneruje
automaticky a ma prednost pred vygenerovanym slovnikem, takze
rucni prace prezije preextrahovani.

Dva nalezy jsou FALESNE a nemaji se opravovat:
- `poruchy TK` – model si myslel, ze TK = tkane; v ceske medicine
  je to *tlak krevni*, extrakce byla spravne
- `kychnuti` – model si vymyslel, ze kychnuti je odchod plynu

## KROK: Vyresit "paleni zahy" - CASTECNE VYRESENO 24.8.

**Stav po dotazeni slovniku (24.8.):** dotaz "pali me zaha" uz vraci

    1. 0,633  MAALOX             ... pali zahy, caste rihani ...
    2. 0,598  OMEPRAZOL FARMAX   ... pali zahy a kysele rincení ...
    3. 0,584  OMEPRAZOL FARMAX   lecba paleni zahy ...

Tim je vyresena puvodni stiznost, ze "controloc a omeprazol to vubec
nenaslo" - **OMEPRAZOL i MAALOX se najdou**.

**CONTROLOC se porad nenajde** (ani v top 12). Jeho laicky text mluvi
o "navratu kyseliny", ne o paleni zahy. Je to ukazka toho, ze slovnik
resi ODBORNE terminy, ale ne situaci, kdy je laicky opis sice spravny,
jen pouziva jina slova nez uzivatel. Souvisi s nalezem "laicky opis redi
podobnost" (poznatky.md 21.8.).

Puvodni zadani ukolu:

Realny dotaz, ktery selhal. CONTROLOC i OMEPRAZOL jsou na reflux a maji
to v indikacich, presto je dotaz "paleni zahy" nenasel. DVE nezavisle
priciny, kazda chce jine reseni.

### 1. OMEPRAZOL neni v indexu vubec

Sekce `indikace` ma stav `zamitnuto_kontrolou` -> nepousti se do
`leciva_search`. Nasel se jen jeho radek z DAVKOVANI, kde je "paleni
zahy" doslova.

Reseni: projit tu sekci rucne (uz je v seznamu vyse).

### 2. CONTROLOC je v indexu, ale nema tam slovo "paleni zahy"

Ulozeny laicky text:
    "Lecba priznaku navratu kyseliny ze zaludku do jicnu.
     (Symptomaticka lecba refluxni choroby jicnu)"

Bezny lidovy termin tam NENI a bge-m3 to spojeni neda - CONTROLOC se
nedostal ani do prvnich osmi.

Neni to vada embedovaciho modelu, ale toho, JAKYMI SLOVY je psany
laicky tvar. Moznosti k vyzkouseni v evaluaci (test C):

  a) vynutit v promptu BEZNY LIDOVY termin misto opisu
     ("rekni to slovem, ktere pouzije laik pri hledani")
  b) ukladat do `obsah_text` OBA tvary i u indikaci - u nezadoucich
     ucinku se to uz dela: "nizky pocet krevnich desticek (trombocytopenie)"
  c) rozsirit dotaz o synonyma ze slovniku pojmu pred embedovanim

Podrobne v `poznatky.md`, zapis z 20.8.2026.

## ~~KROK: Ciselnik "laicky dotaz -> formulace v textu"~~ HOTOVO 24.8.

Zmereno 24.8.: nejlepsi rozsireni dotazu NENI synonymum, ale formulace
z dokumentu. MAALOX na dotaz o refluxu:

    "mám reflux"                                  #19  (0,474)
    "regurgitace"          odborne synonymum      #10  (0,488)
    "vracení kyselého obsahu ze žaludku do úst"   #1   (0,647)

- [x] HOTOVO jako samostatny `slovnik_dotazu.json` + `common/dotazy.py`, smer `laicky vyraz -> formulace v textu`
      (dnes umi jen `odborny -> laicky`)
- [x] rozsiruje se DOTAZ pred embedovanim, ne text v DB - nic se nevymysli
      a zustane dohledatelnost na SPC
- [x] dodrzeno: odvozena slova (omeprazol -> reflux) smi slouzit jen
      k VYHLEDANI, NIKDY k zobrazeni. CLI u kazdeho vysledku tiskne
      `zdroj ... spc.md § 4.1` - vygenerovany radek by zadny zdroj nemel
      a prisli bychom o hlavni prednost ukazky.
- [x] `atc_mapa.json` + `vypis_atc_zachranu()` - ukaze se JEN kdyz nic nenajde (A02 -> kyselost/reflux, J01 -> infekce,
      N02 -> bolest, R01 -> ucpany nos, R06 -> alergie). Pet skupin pokryje
      12 z 22 leciv, tabulka je mala a rucne zkontrolovatelna.
      ALE je to znalost NA UROVNI TRIDY - zvedne recall, ne precision.

## ~~KROK: Rozdelit vicepriznakove INDIKACE~~ HOTOVO 24.8.

Zmereno 24.8. (`bench_embed_cloud.py`, podrobne v poznatky.md).

MAALOX ma ctyri priznaky slepene v jedne vete:

    lecba potizi spojenych s prilisnou kyselinou v zaludku, jako jsou
    paleni zahy, caste rihani, vraceni kyseleho obsahu ze zaludku do ust
    a bolest v brise na lacno

Na dotaz "mam reflux" ma cela veta cosine 0,474 (#19 ze 136), ale samotny
fragment "vraceni kyseleho obsahu ze zaludku do ust" ma **0,555 -> #4**.
Rozdeleni tedy da lepsi vysledek nez cloudovy text-embedding-3-large
(#7), zadarmo a lokalne.

- [x] udelano JINAK - modelem (`rozdel_vycty.py`), ne regexem; meritelne by regex uskodil ve 3 z 5 pripadu. Puvodni navrh byl rozsirit `rozpad_vyctu()` o oddelovac typu "jako jsou A, B a C"
      (dnes deli jen na stredniku)
- [x] osetreno - model 3 z 7 polozek spravne NEROZDELIL. Puvodni varovani: nesmi se rozbit indikace, kde je vycet soucasti JEDNE
      diagnozy - rozdelovat jen tam, kde jsou to samostatne priznaky
- [x] provedeno: `naplni_db.py --znovu`, embeddingy, evaluate
- [x] zkontrolovano - kontraindikace maji 1 kandidata a ten se delit NEMA

**Naleha to vic, nez se zdalo.** Po seskupeni po lecivech je na dotaz
"mam reflux" poradi: CONTROLOC, OMEPRAZOL, **AFRIN (ucpany nos, 0,512),
PARALEN (bolestiva menstruace, 0,510), BISACODYL (vyprazdnovani, 0,501)**
a teprve #9 MAALOX. Ty tri nesmyslne jsou NAD prahem 0,50, takze by se
v ukazce vedeni zobrazily. Overeno 24.8., ze to nespravi ani cloudovy
embedding (3-large: #7), ani rerank pres gpt-5-nano (#8) - rozdeleni
vety da #4, zadarmo a lokalne.

Souvisi s "laicky opis redi podobnost" a "hole sloveso nema ostry
vyznam" - potreti tentyz nalez: **embedding prumeruje pres cely text.**

## RUCNE PROJIT: TALVOSILEN - model ztratil cast vyctu indikaci

Zdroj (0086023, sekce 4.1) uvadi:

    ...bolesti ruzneho puvodu, napr. pri bolesti hlavy a zubu, pri bolesti
    nervoveho puvodu, bolesti pri zranenich a operacich, bolesti pri
    degenerativnich revmatickych onemocnenich...

Model z toho udelal 3 polozky a **bolest hlavy, zubu, nervoveho puvodu
ani po zranenich mezi nimi NEJSOU**.

- [ ] doplnit chybejici polozky rucne, nebo preextrahovat jen tuhle sekci
- [ ] **deterministicka kontrola tohle neodhali** - kotvu na zdroj ma, ale
      nepocita polozky vyctu. Zvazit kontrolu "kolik carek/napr. je ve
      zdroji vs kolik polozek vzniklo".

## DROBNOST: preklep "obecní skupina" v davkovani ZYRTECu

Extrakce vyrobila `obecní skupina 10 mg (1 tableta) jednou denně` -
ma byt "obecná skupina", nebo lepe proste "dospeli a deti od 12 let".

- [ ] opravit rucne v json/davkovani.json u 0155683
- [ ] podivat se, jestli "obecní" nevzniklo i jinde

## DROBNOST: nenormalizovana frekvence "nejcastejsim"

V korpusu je 1 polozka s frekvenci `nejčastějším`, kterou
`normalizuj_frekvenci()` nerozpoznala a dala jí rank 9 ("neni znamo").

- [ ] najit ji a opravit ve zdrojovem JSON, nebo pridat do
      `FREKVENCE_SYNONYMA` v `common/extrakce.py`

## KROK: Router obcas ztrati nazev leciva

Zmereno 24.8.: `caste nezadouci ucinky amoksiklav` vytahne jednou
`nazev='Amoksiklav'`, podruhe `nazev=None`. Totez u `vzacne nezadouci
ucinky paralen`.

Dopad: bez nazvu se nespusti rezim cteni sekce, jede bezne hledani
a prah orizne vysledek (2 polozky misto 6).

**CASTECNE RESENO 24.8.:** do hledani jde vzdy i puvodni veta uzivatele
(`hledej(..., puvodni_dotaz=...)`), takze prilis agresivni orez uz
nezpusobi prazdny vysledek. Ztratu `nazev` to ale neresi - bez nej se
nespusti rezim cteni sekce.

- [ ] pridat do promptu vyrazny priklad "FREKVENCE + NAZEV LEKU naraz"
- [ ] zvazit deterministickou pojistku: kdyz se v dotazu vyskytuje slovo,
      ktere se shoduje s nazvem leciva v DB (bez diakritiky, case
      insensitive), doplnit `nazev` i kdyz ho model vynechal
- [ ] pridat invariant do `evaluate.py` - dnes to zadny test nechyti

## KROK: Overovat LAICKY tvar proti odbornemu

Zjisteno 25.8.: ERCEFURYL mel `doslovne` "Akutní průjem bakteriálního
původu" (SPRAVNE) a `laicky` "Náhlý ZÁŠKRT způsobený bakteriemi" -
zaskrt je difterie. **Proslo to obema kontrolami**, protoze obe
kontroluji odborny text proti zdroji.

Laicky tvar se dnes neoveruje nikde. Ciselnik pojmu to resi jen
u terminu, ktere se OPAKUJI - jednorazova veta propadne.

- [ ] pustit na dvojice `doslovne` -> `laicky` tutez kontrolu, jakou uz
      dela `postav_slovnik.py` na terminech (jiny model rozhodne, jestli
      laicky tvar vecne odpovida odbornemu)
- [ ] zacit u INDIKACI a KONTRAINDIKACI - tam jsou to cele vety, takze
      ciselnik je nepokryva
- [ ] opraveno rucne: ERCEFURYL (v datech i v `slovnik_rucni.json`)

## ~~KROK: Oprava rozbocivosti (hubness)~~ ZAMITNUTO 25.8.

**Nedelat.** Domereno na cele evaluacni sade: pri stejne uspesnosti
na negativnich dotazech (7/8) padne o jednu parafrazi VIC nez dnes.
Opravi vybrane pripady, ale zhorsi celek - potresta i legitimni
obecne odpovedi, protoze ty jsou rozbocovaci ze stejneho duvodu.
Podrobne v poznatky.md.

### Puvodni zadani (pro pripad, ze by nekdo chtel zkusit jinak)

Zmereno 25.8.: nektere radky jsou blizko VSEMU. "bolestivá menstruace"
ma prumernou podobnost 0,506 ke 12 nesouvisejicim dotazum, prumer
korpusu je 0,399 (3,5 smerodatne odchylky).

Po odecteni rozbocivosti:

    kasel + ACIFEIN "bolest hlavy"       0,567 -> 0,013
    prujem + ACIFEIN "bolest hlavy"      0,546 -> -0,008
    negativni dotazy celkove             0,50-0,62 -> 0,11-0,24
    parafraze spravne prvni              7/10 -> 8/10

- [ ] pridat sloupec `hubnost` do `leciva_search`, pocitat pri plneni DB
      proti PEVNE sade dotazu (varianta "podobnost k ostatnim RADKUM"
      je HORSI - nadhodnoti velmi specificke texty jako "kopřivka")
- [ ] **prah preměřit od nuly** - stupnice se posune z ~0,5 na ~0,15
- [ ] zvazit preskalovani zpatky na 0-1, aby cislo pro uzivatele
      zustalo nazorne
- [ ] sada dotazu pro pozadi je NOVY ladici parametr - musi odpovidat
      tomu, na co se lide ptaji

## KROK: Oddelit text pro ZOBRAZENI od textu pro HLEDANI  << PRIORITA

Nejvetsi zbyvajici zlepseni. Podrobne v poznatky.md.

HIDRASEC PRO DETI ma indikaci na 27 slov a v hledani se nechyta:

    dotaz "průjem u dětí"   dlouha veta 0,623   kratky klic 0,902

Tyka se to 39 % indikaci, 67 % kontraindikaci a 77 % davkovani
(polozky nad 10 slov).

- [ ] pridat pole `klic` do sablony extrakce (2-4 slova, nazev stavu) -
      ZADNA volani modelu navic, jen pole navic v existujici sablone
- [ ] sloupec `hledaci_klic` v `leciva_search`
- [ ] rozhodnout, CO embedovat:
      a) jen klic                            - ztrati detail
      b) klic i cely text jako DVA vektory   - symetricke s dotazem, DOPORUCENO
      c) klic do vektoru, text do fulltextu  - kompromis zadarmo
- [ ] `obsah_text` zustava beze zmeny - uzivatel dal vidi PUVODNI zneni
      a odkaz na stranu SPC. Klic je rejstrikove heslo, ne nahrada obsahu.
- [ ] u stavajicich dat staci cileny pruchod pres polozky nad ~10 slov
      (cca 250 polozek)
- [ ] po zmene preměřit prah a pustit evaluate

## KROK: Projit ZADANI proti Filtru - co dalsiho chybi?

24.8. se zjistilo, ze filtr `hrazeny` byl v zadani rozepsany na trech
mistech (vc. invariantu), ale v kodu **neexistoval vubec**. Router ho
pak tise mapoval na `na_predpis` - vysledky vypadaly rozumne, jen
odpovidaly na jinou otazku.

- [ ] **Projit zadani a overit, ze KAZDY zminovany filtr je ve `Filtr`.**
      Doplneno uz: `hrazeno`. Zkontrolovat aspon: stav registrace,
      dostupnost/`jeDodavka`, leková forma, cesta podani, obal,
      indikacni skupina, EU registrace.
- [ ] ke kazdemu doplnenemu filtru pridat **invariant do `evaluate.py`** -
      to je jedine, co takovou diru odhali automaticky

## DROBNOST: dotaz slozeny JEN z filtru nechava vatu v dotaz_text

"hrazeny lek na predpis" -> router vytahne oba filtry spravne, ale
`dotaz_text` necha jako celou vetu misto prazdneho retezce. Semanticky
se pak hleda text, ktery nenese zadny obsah.

- [ ] kdyz po vytazeni filtru nezbyde vecne slovo, vratit `dotaz_text`
      prazdny a radit jen podle filtru (nebo podle nazvu leciva)

## KROK: Detailni logovani behu (do souboru a do DB)

**Proc:** Ted se prubeh vypisuje jen na obrazovku a casto pres `tail`,
ktery drzi vystup v bufferu - pri dlouhem behu neni videt, kde to je,
a po skonceni uz se nedohleda, co se u konkretniho leciva stalo.
Kdyz krok spadne uprostred, nezustane po nem zadna stopa.

### Co ma byt v logu

Kazdy radek = jedna jednotka prace. Musi z nej byt poznat VSECHNO:

    cas | krok | lecivo | sekce | akce | stav | vysledek | trvani

Priklad:

    2026-08-19 17:42:03 | krok3 | 0254048_PARALEN | indikace | extrakce
        | ok | 7/7 polozek | 11.7s
    2026-08-19 17:42:15 | krok3 | 0239773_OLYNTH | indikace | extrakce
        | castecna | 4/6 polozek (2 bez klicu) | 14.6s
    2026-08-19 17:43:01 | krok4b | 0002479_DITHIADEN | indikace | kontrola
        | zamitnuto | 3/8 oznaceno | 5.5s

Pole `vysledek` ma byt ve tvaru **hotovo/celkem**, at je videt pokrok
i uspesnost (6/6 vs 4/6), ne jen "hotovo".

### Kam

1. **Soubor** - `logs/<datum>_<krok>.log`, zapisovat PRUBEZNE (flush po
   kazdem radku), ne az na konci. Musi jit sledovat behem behu.
2. **Databaze** - tabulka `beh_log` se stejnymi sloupci. Az po skonceni
   kroku, davkove. Slouzi k dotazum typu "u kterych leciv trvala extrakce
   nejdyl" nebo "kolikrat uz selhal krok 3 u ABAKTALU".

### Na co si dat pozor

- **NEPOUSTET pres `tail`/`head`** - buffer schova prubeh i chybove hlasky.
  Logovat do souboru a ten pripadne sledovat zvlast.
- Log musi prezit pad kroku - proto prubezny flush do souboru a zapis
  do DB az potom (kdyz spadne, soubor zustane).
- Stav pouzivat STEJNY jako v `stavy.md`, ne vymyslet novy slovnik.

## ~~KROK: Slovnik – doplnit indikace a kontraindikace~~ HOTOVO 24.8.

Zjisteno 21.8.: `postav_slovnik.py::posbirej()` sbira **jen** z
`nezadouci_ucinky.json`. Po sjednoceni tvaru indikaci/kontraindikaci
(20.8.) se s tim nerozsiril, takze 241 radku ma laicky tvar, ktery
**nikdo nekontroluje** a pri kazdem behu vznika jinak.

Projev, ktery to odhalil: **"neuralgie" -> "bolest podel nervu"** –
spatne, a ve slovniku ten termin neni.

| sekce | unikatnich | ve slovniku |
|---|---|---|
| nezadouci_ucinky | 410 | 410 (100 %) |
| indikace | 113 | **4 (3 %)** |
| kontraindikace | 99 | **1 (1 %)** |

### Ukoly

**Vsechno hotovo 24.8. krome posledni odrazky (rozhodnuti o cloudu).**
Vysledek: pokryti indikaci 3 % -> 39 %, kontraindikaci 1 % -> 26 %,
slovnik 476 dvojic, z toho 67 rucne overenych. Zbytek jsou dlouhe vety,
ktere do ciselniku NEPATRI.

- [x] **Rozsirit `posbirej()`** i na `indikace.json` a
      `kontraindikace.json` (pole `doslovne` / `laicky`), ale sbirat
      **jen terminy do ~3 slov**. Dlouhe vety se neopakuji (11 % / 1 %),
      klic slovniku se na ne uz nikdy netrefi. Ciselnik ma smysl jen
      pro to, co se vraci.
      Odhad prirustku: 43 (indikace) + 24 (kontraindikace) = **67 polozek**
- [x] **Jednorazove rucne projit kratke terminy** a spravne prelozit do
      `slovnik_rucni.json` (ma prednost pred generovanym a prezije
      preextrahovani). Dnes ma soubor **1 polozku**.
      Zacit temi, ktere uz jsou videt jako vadne: `neuralgie`,
      `bronchiektazie`, `mukoviscidoza`, `laryngitida`, `bronchiolitida`
- [ ] **ROZHODNUTI: generovat nove dvojice pres `gpt-5-nano`?** misto
      lokalniho modelu – kratke ulohy, levne, lepsi cestina.
      ALE: naráží to na premisu "vsechno lokalne, data neopousteji sit".
      SPC jsou verejne dokumenty SUKL, takze riziko je male, ale pro
      ukazku vedeni se to tvrzeni musi upresnit. **Rozhodnuti, ne detail.**
      Pokud ano, zachovat pravidlo, ze **kontroluje JINY model nez
      generuje** (dnes generuje qwen3.5:122b, kontroluje gemma4:31b).
- [x] ~~preextrahovat~~ - nebylo potreba, slovnik se aplikoval
      deterministicky pres `ocisti_json.py --zapis` (77 polozek)

---

## ~~KROK: Probrat obsah TSV~~ HLAVNI CAST HOTOVA 24.8.

Podezreni: `search_fts` obsahuje vic, nez je k uzitku. Podklady zmerene
21.8. (podrobne v poznatky.md, sekce "Co presne jde do vektoru").

Dnesni stav – `search_fts` = `kontext_text`(A) + `obsah_text`(B),
konfigurace `czech_unaccent` = `simple` + unaccent.

### Co konkretne je podezrele

**1. Stop slova se indexuji.** `simple` je neodstranuje. Videt na
kontraindikaci PARALENU:

    'na':5B 'nebo':9B 'v':13B 'jakoukoli':10B 'dalsi':11B

Ctyri ze ctrnacti tokenu nenesou zadnou informaci. Krome objemu to
**posouva `ts_rank_cd`** – cover density pocita vzdalenosti mezi
shodami a vata mezi ne vklada mezery.

**2. Cisla z davkovani.** Radek davkovani ma v TSV `'12' '20' '25'
'250' '6'`. Dotaz na "250" trefi vsechny leky s jakoukoli 250.
Zvazit, jestli davkovani do fulltextu vubec patri.

**3. Kod SUKL a lekova forma v atributech.** `'0254048'` a `'tbl'`,
`'nob'` – kod ma smysl (da se hledat), `TBL NOB` je zkratka, kterou
laik nenapise nikdy.

**4. Kontext_text se opakuje u KAZDEHO radku leciva.** PARALEN ma
'paralen':1A ve vsech 22 radcich. Pro `ts_rank` to znamena, ze dotaz
na nazev leku da stejny rank vsem jeho radkum – neni podle ceho radit
(uz zapsano jako "vaha A se u atributu neuplatnuje", tohle je druha
strana teze problemu).

### HOTOVO 24.8.

- [x] **`kontext_text` vyhozen z `search_fts`.** Byl to hlavni viník:
      identita leciva se opakuje na KAZDEM radku ve vaze A, takze dotaz
      `paracetamol` trefil 97 radku z 994 a spravnou odpoved (`atributy`)
      dal NAKONEC. Po zmene: 2 radky, oba `atributy`. Priznakove dotazy
      beze zmeny. Zmeneno v `init-db.sql` i migraci na zive DB.
- [x] **Dotaz se prevadi na OR** misto AND. `ts_rank_cd` je tim pouzitelny
      na razeni: PARALEN 3,0 / ACIFEIN 1,0 misto binarnich 0,4/0,0.

### ZBYVA – priorita NIZKA

- [ ] **Ceska stop-slovnikova konfigurace.** Znamena dostat `czech.stop`
      do `$SHAREDIR/tsearch_data/` v kontejneru a prepocitat vsech 994
      radku. Dopad by byl maly: stop slova zpusobuji falesne NEGATIVNI
      vysledek (AND zuzuje), ne falesne pozitivni - a router je z dotazu
      stejne odrezava jako vatu. Pred ukazkou se to nevyplati.
- [ ] **Vaha fulltextu podle typu dotazu.** Router uz typ zna
      (`Filtr.je_presny()`), takze u identitnich dotazu by fulltext mohl
      mit vetsi vahu nez u priznakovych, misto dnesni globalni 0,8/0,2.
      Je to stejna logika, podle ktere se u presnych filtru vypina prah.

### Puvodni mereni (proc to bylo podezrele)

`websearch_to_tsquery` slova **slucuje pres AND**, takze kazde dalsi
slovo vysledek ZUZUJE:

| dotaz | radku z 994 |
|---|---|
| `bolest` | 112 |
| `bolest hlavy` | 33 |
| `nahly zanet jater` | **1** |

U viceslovnych laickych dotazu tedy fulltext skoro nikdy nechytne a celou
praci odvede semantika. Stop slova by navic zpusobila falesne NEGATIVNI
vysledek (zuzeni), ne falesne pozitivni – a router je z dotazu stejne
odrezava jako vatu.

Ceska stop-konfigurace by znamenala dostat `czech.stop` do
`$SHAREDIR/tsearch_data/` v kontejneru a prepocitat GENERATED sloupec
u vsech 994 radku. **Pred ukazkou vedeni se to nevyplati.**

### Co s tim

- [ ] rozhodnout, jestli nasadit **ceskou stop-slovnikovou konfiguraci**
      misto holeho `simple` (pozor: zmena konfigurace = prepocet
      GENERATED sloupce u vsech 994 radku, ale je to jeden ALTER)
- [ ] rozhodnout, jestli `davkovani` vyradit z fulltextu (nechat jen
      vektor) – cisla tam delaji vic skody nez uzitku
- [ ] rozhodnout, jestli z atributu vyhodit lekovou formu (`TBL NOB`)
- [ ] **zmerit dopad na evaluaci PRED a PO** – bez cisla to nemenit

POZOR: `search_fts` je `GENERATED ALWAYS ... STORED`, takze zmena
znamena `ALTER TABLE`, ne preplneni dat. Embedding se tim NEMENI.

---

## Starsi poznamky

- Nastroj na debugging, bezi na portu 6061, umi detekovat praci
  s vektory – najit nazev a nastudovat.
- Proc u IFIRMASTY nevytahl tabulku – kouknout rucne na PDF.
