

# TOP – OD 2. 10. 2026: PIPELINE, ÚKLID, KONTEJNER, SERVER

Pořadí (plán z 2. 10.; starší úkoly do 25. 9. jsou v `docs/archiv_todo_2026-09.md`):

### 0. Evaluace po indikacích v2 (4. 10.) – podívat se
- [ ] `hledani_evaluace.py --korpus` dal **18/20** (30. 9. 20/20), přesnost 69 %
      (67 %), negativní 5/6. Pustit ještě 2× – je to regrese, nebo šum
      routeru (±4 b.)?
- [ ] „kašlu a nejde mi vykašlat hlen" 0/5 v R05 (PREVAC, BRUFEN,
      BRONCHIPRET) a „pálí mě při močení" 0/5 v J01/G04 (čaje V11,
      IBEROGAST): `hledani_log.py "…"` – vypadla z indikací položka,
      která dotaz dřív chytala (prompt v2 ji přesunul do `skupina` nebo
      sloučil)?
- [ ] Soudce (`benchmarky/indikace_fragmenty/soudce.py`) nad NOVOU DB –
      skutečný podíl chybných položek po promptu v2 (před: ~4 %).
      Detektory: podezřelých 6 427 → 5 944. `podezrele.jsonl` už je
      stav NOVÉ DB (starý z 2. 10. se 6. 10. omylem přepsal, čísla jsou
      v poznatcích); skript teď předchozí výstup odkládá s datem.
- [ ] 274 textů s víc různými klíči → `ocisti_json.py --zapis`.
- [ ] **COLDREX HORKÝ NÁPOJ 0260480 – tři chyby, neopraveno** (poznatky
      6. 10.): (1) holá „bolest" z „a s ním spojená bolest" – do promptu
      indikací pravidlo o ODKAZECH na předchozí část věty (37 léků má
      holou „bolest/bolesti"); (2) skupina v samostatném odstavci
      nepřiřazena (12 282 z 25 097 indikací bez skupiny – změřit, kolik
      ji v textu má); (3) věk: zákaz podmíněný hmotností („15–18 let
      pod 50 kg") posune hranici na 18 – úzká oprava opraví 3 SPC
      a rozbije 6× VORICONAZOLE, potřeba přesnější pravidlo.

### 0b. Hledací slovník z GUI (6. 10.) – co znamená pro server
- [x] Úložiště v DB (tabulka `slovnik_dotazu`), ne v souboru: společné všem
      instancím, čte se při každém hledání, nasazení ho nepřepíše.
- [ ] Měsíční job / `extrakce_4_db.py`: tabulku `slovnik_dotazu` NEMAZAT (dnes
      ji `TRUNCATE leciva CASCADE` nezasáhne – nemá cizí klíč; hlídat při
      přepisu na přírůstkové plnění). Zálohuje se s databází.
- [ ] Zápis je bez přihlášení – před zveřejněním rozhodnout, kdo smí.
- [ ] `reflux` → „vracení kyselého obsahu ze žaludku do úst" už v datech
      NENÍ (0 léků po cloudové extrakci) – projít výchozí záznamy slovníku
      proti novému korpusu (`/api/slovnik/formulace`).

### 1. Pipeline pro opakované spouštění
- [x] Jeden příkaz přes celý řetěz – `extrakce_all.py` (6. 10.), zámek,
      log, návratové kódy, ověření doběhnutí extrakce
- [ ] `extrakce_all.py --vse` pustit jednou celé naostro (po úklidu neběželo)
- [ ] `extrakce_4_db.py`: přírůstek po SPC místo TRUNCATE, zaniklá SPC označit
      (dnes i oprava jednoho léku znamená `--obnov-sekci` celé sekce)
- [ ] Změněná SPC poznat (identita + otisk PDF) → jen ta do extrakce
- [ ] Konfigurace z prostředí: Ollama, Docling Serve, Postgres, OpenAI, rozpočet
      (Ollama už ano: `OLLAMA_UZLY`, `OLLAMA_SOUBEZNE`, `HLEDANI_TIMEOUT_S`)
- [ ] Souhrn běhu jako JSON pro monitoring

### 2. Úklid projektu – HOTOVO 6. 10.
Stará pipeline, `legacy/`, zastaralé benchmarky a dokumenty smazány; skripty
přejmenovány (`extrakce_N_…`, `hledani_…`); dokumentace v `docs/`. Zbývá:
- [ ] Soubory pro Docker (`Dockerfile.postgres`, `tsearch/`,
      `pgadmin-servers.json`, `pgpass`) do `docker/`? Znamená úpravu
      `docker-compose.yml`, `provoz_priprava.py` a znovusestavení kontejneru
      – vyřešit spolu s bodem 3.
- [ ] Staré logy v `logs/` (3,8 MB, od srpna) – smazat?
- [ ] Docker volumes z dřívějška: `legacy_pgdata`, `legacy_pgadmin_data`,
      `ailocal_pgdata`, `ailocal_pgadmin_data` (aplikace používá jen
      `localsemantic_*`) – smazat?
- [ ] Kontroly extrakce nad korpusem (`nerealizovane_kontroly/`) – přepsat
      na `data/spc` a zařadit jako kroky za extrakci.
- [ ] `benchmarky/router/bench_router.py` po úpravě části B (parafráze
      podle ATC) jednou pustit.
- [ ] `hledani_evaluace.py --prahy` nad korpusem – přeměřit práh 0,60.

### 3. Kontejner
- [x] Velikost (1. 10.): `data/spc` 4,5 GB, `data/detaily_leciv` 41 MB, DB 5,7 GB → přenos ~10 GB
- [ ] Dockerfile aplikace + docker-compose (Postgres image už je)
- [ ] `data/` jako volume, přenos tar/rsync (ne git)
- [ ] DB přenášet `pg_dump`/`pg_restore` (embeddingy ~2 h znovu nepočítat)
- [ ] Tajnosti mimo image (env/secret), Ollama + Docling Serve z konfigurace

### 4. Nasazení na server
Server: RHEL 9.4, x86, dosáhne na Spark. Má tam běžet všechno a dál se
tam vyvíjí přes Remote-SSH. **Postup: `docs/provoz_prenos_na_server.md`.**
- [x] Konfigurace z prostředí: Ollama, Postgres, Docling Serve (`.env.example`)
- [ ] Na serveru: Docker (nebo podman), `uv`, dosah na Docling Serve 5001,
      OpenAI, SÚKL, EMA – Docker 9. 10. běží, Ollama na Sparku dostupná;
      Docling Serve, OpenAI, SÚKL a EMA ze serveru neověřeno
- [x] Přenést: kód gitem, data tarem (4,7 GB), DB `pg_dump`/`pg_restore`
      (embeddingy se nepočítají znovu), `key.yaml` ručně – hotovo 9. 10.,
      DB 5,6 GB v `data/pgdata` na `/opt` (`PGDATA_DIR` v `.env`)
- [ ] **Místo na `/opt`: 18 GB volných.** Měsíční `extrakce_4_db.py --korpus`
      plní od nuly – ověřit, kolik místa navíc potřebuje (WAL, mrtvé řádky),
      a dát do monitoringu jobu kontrolu volného místa před během
- [ ] `data/localsemantic.dump` (2,9 GB) po ověření provozu smazat
- [ ] Záloha DB na serveru (`pg_dump` do souboru); `data/pgdata` se nesmí
      balit tarem spolu s `data/`
- [x] Ověřit vlastní image Postgresu (hunspell) – 9. 10. na serveru
      sestavený a použitý, evaluace stejná jako na notebooku
- [ ] Smoke test: 9. 10. prošlo `extrakce_all.py --stav`, `hledani_cli.py`,
      `hledani_evaluace.py` (18/20, 69 %, 5/6); zbývá `bench_soubeh.py
      --simulace`, `extrakce_6_rejstrik.py` (symlinky) a GUI
- [ ] **`.doc` SPC na Linuxu:** převod přes MS Word a PowerShell nepoběží;
      náhrada přes LibreOffice (4 dokumenty z 5 880, jen krok 1)
- [x] SELinux a připojené soubory v `docker-compose.yml` – `:z` není
      potřeba (SELinux je Enforcing, ale Docker tu běží bez jeho podpory)
- [x] HTTPS pro GUI na portu 8090 (9. 10.): kontejner `localsemantic-nginx`,
      certifikát `*.sukl.cz` z `/opt/nginx/cert`, profil `server` v compose
- [ ] Povolení portu 8090 v síti (požadavek u správců) – pak ověřit
      z počítače uživatele `https://t-api-dlp01.sukl.cz:8090/`
- [ ] Certifikát platí do 17. 3. 2027; po výměně `nginx -s reload`
- [x] API jako služba systemd `localsemantic-api` (9. 10., jednotka
      v `systemd/`) – ověřit po skutečném restartu serveru
- [ ] měsíční cron `extrakce_all.py --vse`
      + upozornění (viz CÍLOVÝ STAV níže)
- [ ] Co má Claude vědět i na serveru, psát do `CLAUDE.md` – paměť Claude
      je vázaná na počítač a k 7. 10. je prázdná

### 4b. Před prezentací
- [x] (1. 10.) **Výpis VŠECH hledacích vzorů s odzkoušenými příklady** → `docs/prezentace_scenare.md` přepsán pro korpus – aby se
      při prezentaci nic nevymýšlelo na koleni. Staré (hrazený lék na
      reflux, volně prodejný lék s paracetamolem, nežádoucí účinky X,
      dávkování X, čtení sekce, frekvence NÚ, ATC záchranná síť…) i nové:
      věk („horečka dítě šest let", „rýma miminko"), „lék začíná / obsahuje /
      končí / přibližně" (zirtek, oftalmoframikoin, kalideko), kombinace
      vzor + sémantika („lék začíná na oxy na rýmu"). Každý příklad
      OVĚŘIT na korpusu (pravidlo CLAUDE.md) a zapsat do `docs/prezentace_scenare.md`.
- [ ] **Posuvníky „práh" a „barva" v GUI – zamyslet se, jestli dávají smysl.**
      Práh 0,60 je naměřený na 32 lécích; na korpusu a u přesných filtrů
      (věk, vzor názvu, čtení sekce) se neuplatňuje. Rozhodnout: skrýt
      do „pro pokročilé", přeměřit, nebo odstranit.

### 4c. ROZEBRAT ZÍTRA (2. 10.) – slabá místa z `docs/prezentace_scenare.md`
- [ ] **Práh podobnosti 0,60 přeměřit na celém trhu.** Je naměřený na 32
      lécích; na 5 880 SPC pouští falešné shody: „něco na kocovinu" →
      léky na covid, „lék na plešatost" → čaje na plynatost. Souvisí
      s úkolem na posuvník prahu v GUI (bod 4b).
- [ ] **Upřednostnit pro laika volně prodejné léky a vhodnou formu podání.**
      Dotazy na kojence/miminka vracejí nemocniční antibiotika v injekcích
      (MEDOCLAV, TAXIMED), „lék na kašel pro děti" má nahoře antibiotikum
      DALACIN. Možnosti: OTC dopředu, injekce/infuze dozadu nebo skrýt,
      pokud dotaz výslovně nechce nemocniční léčbu.

- [ ] **Váhy a řazení – „zápal plic hrazený" (2. 10.):** KLACID se shodným
      textem „zápal plic (pneumonie)" až na 11. místě (odstup 68), CIPROFLOXACIN
      2. (92). Tři příčiny, žádná věcná:
      1. **Klíč:** CIPRO má klíč „zápal plic" → vektor klíče = vektor dotazu,
         cosine 1,000; KLACID „pneumonie" → 0,801. Ze 36 shodných řádků má
         „zápal plic" jen 2, „pneumonie" 33 (model, nedeterminismus; kontroly
         klíče vypnuté – N3). Klíč je i ve fulltextu → 6,0 proti 3,0.
         → sjednotit klíč u stejného textu (jako `ocisti_json.py`), preferovat
         laické slovo.
      2. **RRF počítá pořadí, ne hodnotu:** shodné cosine 1,000 dostanou
         100 / 92 / 90 / 88 jen podle náhodného pořadí z DB → shodné hodnoty
         hodnotit stejně (sdílené pořadí).
      3. **Fulltext jen top 100 kandidátů (`KANDIDATU`):** shod je přes 100,
         KLACID (3,0) se nevešel → z fulltextu nic. → zvýšit strop / sdílené
         pořadí pro shodné hodnoty.
      **Hotovo 2. 10.:** `KANDIDATU_FTS = 1000` (fulltext zvlášť) – KLACID
      dostal fulltext pořadí #194, odstup 68 → 73, pořád 11. místo (hlavní je
      cosine). Evaluace: parafráze 20/20, přesnost 67 → 66 %, negativní 5/6.
- [ ] **Sjednocení klíče (doporučeno jako první):** všechny řádky se stejným
      textem dostanou stejný klíč, deterministicky. Pravidlo: **klíč = laický
      tvar** (1–4 slova), jinak nejčastější. NE „nejčastější" jako
      `ocisti_json.py` u 32 léků – tady by vyhrála odborná „pneumonie" (33 z 36)
      a všechny by měly 0,80. Přepočet jen vektorů klíčů změněných řádků.
      Jak: PRAVIDLEM po řádcích, ne kopírováním „správného" řádku – laický
      tvar 1–4 slova → klíč = laický, delší → klíč od modelu zůstane.
      V `extrakce_4_db.py` (JSON netknutý), změněným řádkům smazat
      `embedding_klic` a `extrakce_5_embeddingy.py` doplnit o dopočet jen klíče.
      **Změřeno 2. 10.:** změnilo by se 7 833 klíčů indikací (z 10 226
      krátkých) a 14 122 kontraindikací. Model dává do klíče odborný termín
      („zápal plic" → pneumonie 34×, „pálení žáhy" → pyróza 3×).
      Evaluace PŘED a PO; u kontraindikací zvážit vynechat (obecné klíče, N3).
      **VYZKOUŠENO A VRÁCENO 2. 10.** – horší (laický klíč zrovnoprávnil vytržené
      kusy indikací, simvastatin → „cukrovka" 1,0). Poznatky 2. 10.
- [x] **Přeextrahovat INDIKACE s opraveným promptem** – HOTOVO 4. 10.
      (25 097 řádků, celkem utraceno 11,00 $). Zbývá vyhodnocení, viz
      TOP „0. Evaluace po indikacích v2". Původní zadání: měřeno 2. 10.:
      ~4 % položek chybných, ~1–2 % „skupina pacientů jako indikace".
      Do promptu: (1) „u pacientů s X / u nemocných s X / po výkonu X" NENÍ
      indikace, X → pole `skupina`; (2) položka = samostatný název stavu
      v 1. pádě, ne kus věty. Ověřit NEJDŘÍV na vzorku 218 položek
      (`benchmarky/indikace_fragmenty/soudce.py`, starý vs. nový prompt),
      pak celý korpus přes `extrakce_3_json.py --znovu-seznam`, DB
      `--obnov-sekci indikace`, evaluace.
- [ ] **RRF: shodné hodnoty = stejné pořadí** (KLACID mezi 40× cosine 1,0).
- [ ] **Alternativa: samostatné vektory laický / odborný** místo „laický
      (odborný)" v jednom textu (`extrakce_4_db.py: _spoj`). Závorka vzniká jen když
      se odborný liší od laického a má ≤ 60 znaků → stejný pojem má podle SPC
      jednou 1,0 („zápal plic"), jednou 0,80 („zápal plic (pneumonie)").
      Řeší i odborné dotazy, ale přepočet všech vektorů (~2 h). Až když bude
      vidět, že trpí odborné dotazy.
- [ ] **GUI popisek „Fulltext: nenašel" je zavádějící** – fulltext řádek
      našel (3,0), jen se nevešel mezi top 100. Psát „shoda 3,0, mimo
      prvních 100" (popisek je součást odpovědi).

### 4d. Víc uživatelů najednou
- [x] **Rozdělování zátěže mezi stroje s Ollamou** (7. 10.): dostupnost,
      priorita Sparku, přelití na druhý stroj, náhradní cesta při výpadku,
      limit 30 s na router a embedding, stav v `/api/stav`. Simulace na
      falešných strojích prošla. `docs/provoz_pristupy.md`.
- [ ] **Dell (10.6.38.9) zapojit:** otevřít port 11434
      (`OLLAMA_HOST=0.0.0.0`), `ollama pull gemma4:26b` a `bge-m3` ve
      STEJNÝCH tazích jako Spark. Pak `benchmarky/soubeh/bench_soubeh.py`
      – čekání 8 uživatelů má klesnout z ~14 s zhruba na polovinu.
- [ ] **`OLLAMA_NUM_PARALLEL` na strojích** – dnes router jede po jednom
      (2 souběžné = 2× delší čekání). Je to GLOBÁLNÍ nastavení serveru,
      násobí paměť na kontext i u qwen3.5:122b (gemma je načtená
      s kontextem 262 144). Změřit dopad, pak zvednout `OLLAMA_SOUBEZNE`.
- [ ] **Víc procesů API** (uvicorn workers): každý si počítá vytížení
      strojů sám. Stačí pro pár workerů; při větším počtu sdílet stav.
- [ ] **Vytížení od jiných** (extrakce na témže stroji) aplikace nevidí,
      jen delší odezvu – zvážit výběr stroje i podle průměrné odezvy.
- [ ] **Počítadlo v GUI:** kolik lidí má aplikaci otevřenou v prohlížeči
      a kolik hledání právě běží; stav strojů s Ollamou (je v `/api/stav`).

### 5. Když zbude čas
- [ ] Slovník dotazů: editace v GUI + doplnit podle korpusu (bod 5 níže)
- [ ] Evaluace: věk, ATC seznamy, test 0 pro korpus (bod 4b níže)

---

# TOP – ÚTERÝ 29. 9. 2026: EXTRAKCE DO JSON MODELEM (další etapa pipeline)

Konverze i rozparsování sekcí celého korpusu jsou hotové (viz
`aktualnistav.md` nahoře). Teď převod sekcí do strukturovaného JSON
modelem (indikace, kontraindikace, dávkování, NÚ + laický tvar + klíč).
**Pořadí pod-úkolů je závazné.**

### 1. HOTOVO 29. 9.: jak extrakce funguje TEĎ → `docs/pipeline_extrakce.md`

**Nejdřív rozhodnout N11** (`docs/pipeline_extrakce.md` kap. 7): luna byla změřena jen na
zjednodušení z hotového `doslovne`, produkce dělá vše jedním voláním →
buď rozdělit extrakci na 2 kroky (lokálně doslovné, cloud laický+klíč),
nebo celou extrakci do cloudu (nutné změřit 4.8). Určuje tvar úkolů 2–4.

Nic neměnit, dokud není jasný celý řetěz. Projít a sepsat (do
`docs/pipeline_prehled.md` / krátký výklad):
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
      (gemma4:26b) → `postav_slovnik.py` → `rozdel_vycty.py` → `extrakce_4_db.py`
      (**čte `data/leciva/<kód>_<NÁZEV>/api.json` – pro korpus přepnout na
      `data/detaily_leciv/`**) → `extrakce_5_embeddingy.py` → `hledani_evaluace.py`.
- [x] Kde se liší laický tvar a klíč, kdo je vyrábí (jeden prompt s extrakcí?)
      a co přesně ověřují dnešní kontroly (jen `doslovne`, NE `laicky`).

### 2. Kontroly na KLÍČ a LAICKÝ tvar (musí být PŘED hromadným během)

Důvod: `poznatky.md` 23. 9. – nesmysly v laickém tvaru („kyselé řinčení
do krku", „náhlý záškrt" za akutní průjem) NEJSOU vlastnost modelu, ale
nedeterminismus → cloud je neřeší, jediná obrana je kontrola.

> **VŠECHNY KONTROLY EXTRAKCE ODLOŽENY 29. 9. – zapracovat až nad
> novým korpusem z cloudu.** Vypnuto přepínačem `config.KONTROLY_ZAPNUTE`
> (klic_ma_oporu, kroky 4a/4b, kontrola slovníku). Seznam toho, co
> dodělat, je v **`nerealizovane_kontroly/kontroly_popis.md` kap. 3**:
> - [ ] N1 laický tvar proti zdroji, N2 opora klíče proti `doslovne`,
>       N3 `zkontroluj_klic()` (naměřeno: 22 % klíčů > 4 slova),
>       N4 vazba účinek→frekvence proti značkám PDF, N5 stabilní ID místo
>       indexů, N8 uložený ořez, změřit 4b na gemma4:26b, regresní sada
> - [ ] Po zapracování: `KONTROLY_ZAPNUTE = True`, pustit 4a/4b nad
>       korpusem, přeměřit `hledani_evaluace.py`
>
> **ODLOŽENO 29. 9.: N1 (laický tvar dlouhých indikací/kontraindikací
> neověřuje nic) a N2 (opora klíče se ověřuje proti `laicky`, ne proti
> `doslovne`)** – viz `docs/pipeline_extrakce.md` kap. 4 a 7. Důvod: zbývá jen tento
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

### 4. Spustit v nové podobě – `extrakce_3_json.py` (Batch API)

- [x] `extrakce_3_json.py` (29. 9.): inventář SPC × sekce, dávky Batch
      API, stav po požadavku v `data/spc/_extrakce/stav.sqlite`, navazování
      po pádu / Ctrl+C, log `data/spc/_extrakce/log/`, `report.md` se všemi
      chybami podle ID, `--znovu-chybne` / `--znovu-seznam`, rozpočtový
      strop `config.CLOUD_STROP_USD`, priorita = SPC s nejvíc kódy.
- [ ] Test na 5 SPC s úmyslnými chybami (dávka bez souboru, požadavek bez
      promptu) – výsledek v `poznatky.md`.
- [x] **ROZPOČET: na účtu 10 $, korpus ~5,5 $ (pesimisticky 6,4 $).**
      `CLOUD_STROP_USD = 8.0` – pokryje celý korpus s rezervou.
- [ ] Ostrý běh: `uv run python extrakce_3_json.py --beh` (v popředí).
- [ ] Po běhu: `postav_slovnik.py --zapis` z výstupu luny (generovaný
      slovník qwenu smazán 29. 9.), pak `ocisti_json.py` pro korpus.
- [x] Zapsat do seznamu kroků – `extrakce_all.py` (6. 10.).
- [x] (29. 9.) Zámek proti souběžnému běhu (`beh.lock`, drží OS) + hlídač z Plánovače úloh – `docs/pipeline_batch_openai.md`.
- [x] Známá mezera (vyřešena `srovnej_s_openai`): pád PŘESNĚ mezi `batches.create` a zápisem do DB
      nechá dávku u OpenAI bez záznamu → požadavky se pošlou znovu
      (dvojí platba za ~1 dávku). Řešení: při startu srovnat
      `batches.list()` podle `metadata.davka`.

### 4b. DB a hledání nad korpusem (30. 9.)

- [x] `extrakce_4_db.py --korpus`: zástupce SPC (nejmenší kód), `leciva.spc`,
      `leciva.zastupce`; API PDF přes mapu kód → SPC, výpis jen zástupci.
- [x] `hledani_evaluace.py --korpus` (30. 9.): parafráze podle ATC 20/20 (přesnost
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
      `leciva.vek_od/pro_deti/vek_duvody`, `extrakce_4_db.py --jen-vek`, router
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
- [ ] Po každé změně `hledani_evaluace.py` (slovník mění hledání).

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
      každé změně `common/kontrola_konverze.py` (jako `hledani_evaluace.py`):
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
      **Změřit PŘED nasazením:** test v `hledani_evaluace.py` – dotazy na příznaky
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

- [x] Krok konverze je v seznamu kroků `extrakce_all.py` (6. 10.).
- [x] Jedno úložiště `data/spc/<identita>/`; `data/leciva` smazáno (6. 10.).
- [x] Všech 7 kroků včetně DB a embeddingů je v `extrakce_all.py` (6. 10.).
- [ ] **Benchmarky v kořeni** (`bench_embed_cloud`, `bench_extrakce`,
      `bench_konverze`, `bench_rerank_nano`, `bench_router`,
      `bench_zjednoduseni` + jejich `*.json`) a Codexův `benchmark/` přesunout
      do `benchmarky/<téma>/`. Pozor na odkazy v `poznatky.md`.
- [ ] `docs/pipeline_prehled.md` po úklidu přepsat tak, aby A→Z pořadí bylo na jednom místě.

### Musí umět

- [ ] **Přírůstkově, ne celé znovu.** Inventář z API SÚKL (`dokumenty-metadata`)
      porovnat s minulým během:
      - **nová SPC** → zpracovat celá,
      - **změněná SPC** → poznat podle identity dokumentu (CZ `id` se mění
        s verzí) + otisku obsahu PDF (SHA-256); zpracovat znovu,
      - **zaniklá** (kód už není obchodovaný / registrovaný) → v DB označit
        jako neaktivní, NEMAZAT (historie, odkazy),
      - beze změny → přeskočit.
- [ ] **Navazování po pádu** jako `extrakce_1_konverze.py`: stav po každém
      dokumentu, stejný příkaz pokračuje; dávky se stabilními čísly.
- [ ] **Zámek proti souběžnému běhu** (cron nesmí pustit druhý běh, když
      první ještě jede).
- [x] **Report podezřelých na konci každého běhu** (`common/report_konverze.py`,
      volá `extrakce_1_konverze.py`) – do `extrakce_all.py` převzít + počet
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
- [ ] **DB přírůstkově:** `extrakce_4_db.py` dnes umí jen `--znovu` (celé znovu).
      Pro měsíční běh upsert po léčivech + deaktivace zaniklých.
- [ ] Na konci **hledani_evaluace.py** a jeho čísla do souhrnu běhu – regrese se
      musí projevit hned, ne až u uživatele.
- [ ] `--dry-run`: jen ukázat, co by se zpracovalo (nové/změněné/zaniklé), nic nedělat.

Stavební kameny už existují: `extrakce_1_konverze.py` (inventář, dedup,
navazování, dávky, hlídač zatuhnutí, kontroly), `common/kontrola_konverze.py`,
`extrakce_all.py` (pořadí kroků, zámek, log, návratové kódy).

---
