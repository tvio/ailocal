# STAV K 30.9.2026 večer — VĚK POUŽITÍ + DÁVKOVÁNÍ BEZ OŘEZU

- **Ořez 4.2 vypnut** (zahazoval dávky u 56 % SPC, např. VIBROCIL).
  Přeextrahováno 5 451 dávkování (schéma u dávkování vždy). Běží
  `--znovu-chybne --beh` (69 + 8 z dávky 85). **Pak:**

      uv run python extrahuj_json_cloud.py --znovu-chybne --beh   # zbylé chyby
      uv run python naplni_db.py --obnov-sekci davkovani           # + přepočet věku
      uv run python vytvor_embeddingy.py                           # jen nové řádky
      # restart API

- **Věk použití** (`common/vek.py`): `leciva.vek_od/pro_deti`, filtr
  „pro děti / pro dítě X let" v routeru (deterministicky), GUI detail
  „Věk použití". Věk určen u 87 % SPC. Poznatky 30. 9. večer.
- **Rejstřík:** `data/leky/<NÁZEV SÍLA>_<kód>` → složka SPC,
  `postav_rejstrik.py --najdi vibrocil`.
- **Evaluace trhu:** `evaluate.py --korpus` (parafráze ATC 20/20, 67 %).
- **GUI stránkování** okénkem + výběr 10/25/50/100.
- Utraceno celkem ~10,1 $ (strop 10,5 $).

---

# STAV K 30.9.2026 ráno — CLOUDOVÁ EXTRAKCE KORPUSU DOKONČENA

- `extrahuj_json_cloud.py --beh` doběhl: **23 479 sekcí hotovo, 16 chyb**
  (nevalidní JSON, nejspíš useknutý výstup), 25 bez sekce. Výstupy jsou v
  `data/spc/<slozka>/json/`, report v `data/spc/_extrakce/report.md`.
- **Utraceno 7,94 $** (odhad 5,5 $, výstup byl o 62 % větší). Na účtu
  zbývá ~2 $.
- 16 chyb = zacyklení modelu → opraveno (strop 40 k, teplota 0,4,
  Structured Outputs na 3. pokus), **všech 23 495 hotovo, 0 chyb**.
- **DB: `naplni_db.py --korpus`** (nové) – všech 8 778 kódů v `leciva`
  (sloupce `spc`, `zastupce`), extrakty a hledací řádky JEN JEDNOU ZA SPC
  u zástupce (nejmenší kód). Řádek `atributy` nese názvy a síly všech
  balení SPC. API: PDF přes mapu kód → SPC, výpis léků jen zástupci.
  Staré DB 32 léčiv se tím smaže (TRUNCATE).
- **HOTOVO (30. 9.):** `naplni_db.py --korpus` (37 min) + `vytvor_embeddingy.py`
  (~2 h): **451 186 hledacích řádků, všechny s vektorem, 93 507 s klíčem**.
  `hledej.py "mám reflux"` funguje nad korpusem (MAALOX, RELUMO/omeprazol…).
  `hledej.py` ukazuje zdroj z `data/spc/` (opraveno).
- **Po nahrání:** `evaluate.py` je postavený na 32 léčivech –
  `vzorek_eval.json` má texty staré qwen extrakce a kódy, které nemusí
  být zástupci. Čísla nebudou porovnatelná → evaluaci postavit znovu
  nad korpusem (`todo.md`). Restartovat API (nové sloupce, PDF z `data/spc`).

---

# STAV K 29.9.2026 — EXTRAKCE ZMAPOVANÁ (`extrakce.md`)

- Úkol 1 z `todo.md` hotový: celá extrakce a navazující kroky popsané
  v **`extrakce.md`**, nálezy N1–N12 v kap. 7. Kód se neměnil.
- **KONTROLY EXTRAKCE DOČASNĚ VYPNUTÉ** (`config.KONTROLY_ZAPNUTE =
  False`): `klic_ma_oporu`, kroky 4a/4b v `pipeline.py`, kontrola
  slovníku modelem. Jednorázově zapnout: `pipeline.py --vse --s-kontrolami`.
  Popis všech kontrol a toho, co chybí (N1–N5, N8, regresní sada):
  **`extrakce_kontroly.md`**. Zapracovat až nad novým korpusem.
  Důvod: zbývá tento týden, Batch API (okno 24 h) zabere ~2 dny.
- Sekce nového korpusu budou ve stavu `neovereno`. `naplni_db.py`
  (bez `--jen-ok`) je nahraje.
- **N11 rozhodnuto: extrakce do cloudu CELÁ** (luna, reasoning `none`,
  `temperature=0`, `seed=42`). Cloudová cesta je v `common/extrakce.py`.
- **Cena: ~5,5 $ přes Batch** (vstup 31,5 M tok, výstup ~15,7 M;
  pesimisticky 6,4 $). Reálná ukázka na 3 SPC bez chyby. Detaily jsou v
  `poznatky.md` 29. 9., nástroj `benchmarky/extrakce_cloud/`.
- **Otevřené před během:** generovaný slovník přepisuje lunu (42 %
  laických tvarů, i s překlepy). Návrh je brát jen ruční slovník. Dál
  ověřit zůstatek na OpenAI.
- **Generovaný slovník qwenu SMAZÁN** (`slovnik_pojmu.json/.md`, jsou v gitu).
  Platí jen ruční `slovnik_rucni.json`; generovaný se postaví z výstupu luny.
- **`extrahuj_json_cloud.py` hotový a otestovaný** (Batch API, stav v
  SQLite, log, `report.md`, opakování chybných, rozpočtový strop,
  srovnání se sirotčími dávkami). Test na 5 SPC s úmyslnými chybami
  prošel – `poznatky.md` 29. 9. večer.
- **ROZPOČET:** na účtu 10 $, korpus ~5,5 $ (pesimisticky 6,4 $) →
  `config.CLOUD_STROP_USD = 8.0`, stačí na celý korpus s rezervou.
- **Další krok – ostrý běh (v popředí):**

      uv run python extrahuj_json_cloud.py --beh --max-davek 1   # pilot 1000 požadavků
      uv run python extrahuj_json_cloud.py --beh                 # zbytek, naváže
      uv run python extrahuj_json_cloud.py --stav                # kdykoli: souhrn + report.md

  Log: `data/spc/_extrakce/log/`, report: `data/spc/_extrakce/report.md`.

---

# STAV K 25.9.2026 večer — KONVERZE A SEKCE CELÉHO KORPUSU HOTOVÉ

**Nic neběží na pozadí.** Po restartu počítače lze navázat. Další krok:
**extrakce do JSON modelem** – plán a pod-úkoly v `todo.md` úplně nahoře
(úterý 29. 9.).

## Kde jsou data

| co | kde |
|---|---|
| seznam léčiv (zářijové vydání SÚKL) | `data/pool_leciv.json` + `.meta.json` (vydání) |
| plné detaily kódů v rozsahu | `data/detaily_leciv/<kód>.json` (9 196) |
| hrazené, číselník látek | `data/hrazene_scau.json`, `data/ciselnik_latky.json` |
| SPC (PDF, md, strany, kontrola, sekce) | `data/spc/<identita>/` |
| stav inventáře a konverze | `data/spc/_stav.sqlite` (tabulky `kody`, `spc`) |
| **reporty k prohlédnutí** | `data/spc/_report/podezrele.html` (395 podezřelých), `sekce.html` + `sekce.csv` (zdroj každé sekce, nenalezené) |
| původních 32 léčiv (GUI, DB) | `data/leciva/` – beze změny |

## Čísla

    kódy v rozsahu (obchodované, PLATNE_STAVY R B C F I K M Y)  8 863
      z toho se SPC                                              8 778
      bez SPC (F/I neregistrované, SPC nemají)                      85
      homeopatika bez SPC (V12) – vynechána                        333
    unikátní SPC používaná kódy                                  5 880
    převedeno (Docling Serve + 4 z Wordu)                  všechna, 0 chyb
    podezřelých po kontrole konverze                               395
    sekcí 4.1/4.2/4.3/4.8                                       23 520
      zdroj Docling (md) / surový text PDF             17 856 / 5 641
      nenalezeno (indikace 13, dávkování 5, kontraindikace 3, NÚ 2)  23

## Jak znovu spustit (měsíční běh = týž příkaz)

    uv run python konvertuj_serve.py --obchodovana   # seznam -> inventář -> konverze -> kontroly -> report
    uv run python konvertuj_serve.py --stav          # souhrn, podezřelé, kde se stálo
    uv run python extrahuj_sekce.py --korpus         # sekce + přehled sekcí
Docling Serve přes SSH tunel na `localhost:5001` (musí běžet).

## Co se dnes (25. 9.) změnilo – podrobně v `poznatky.md`

- `konvertuj_serve.py`: seznam léčiv z VEŘEJNÉHO API na začátku běhu
  (`common/seznam_leciv.py`, jen při novém měsíčním vydání), inventář s
  deduplikací (EU podle registračního čísla), prokládání 1 EU / 10 CZ,
  EMA ≥ 10 s + Retry-After, opakování při 502/503/504, Word (.doc) přes
  MS Word -> DOCX + PDF, kontroly po každém dokumentu, report na konci.
- `common/kontrola_konverze.py`: frekvence proti značkám PDF (jinak
  geometrie), hledání sekcí SDÍLENÉ s `common/sekce.py`, pokrytí jen
  u sekcí, které extrakce opravdu bere z Doclingu (`zdroj_48`).
- `common/sekce.py`: nadpis „4. 8." s mezerou (MENOPUR).
- `extrahuj_sekce.py --korpus` + `common/report_sekce.py`.

## Pozor / otevřené

- **Reporty podezřelých ještě nikdo neprošel** – projít podle typu důvodu.
- `pipeline.py` o nových krocích neví; `naplni_db.py` čte zatím
  `data/leciva/…/api.json` (32 léčiv) – viz `todo.md` „Krok 0 – úklid".
- Kontrola konverze nemá regresní sadu (todo) – po každé její změně
  ověřit aspoň ERMM-1, PARALEN, CAVINTON (ok) a MENOPUR, AUBAGIO,
  CASARO (podezřelé).
- Homeopatika a F/I bez SPC: do přehledu patří jen s atributy – todo.

---

# STAV K 22.9.2026 — provedeny kroky 0, 0,5, 1 a 2 z plánu v `todo.md`

Podklad: audit Codexu (`audit_hledani.md`) + vlastní měření.
Plán i s vysvětlením a příklady je v **`todo.md`** nahoře.

## Naměřený stav (práh 0,60, zmrazený vzorek)

    Invarianty filtru           212/212   100%
    Auto-recall @5               46/47     98%
    Auto-recall @10              51/51    100%
    Negativní dotazy              7/8      88%
    Parafráze (ručně)            10/10    100%   <- s prahem, viz níže

    TEST 0:
    Pokrytí sekcí                30/32     94%   ALGESAL, ENDITRIL
    Frekvence namapovaná        594/889    67%   295 položek rank 9
    Bez duplicitních řádků     1308/1308  100%   nové
    Jednotný klíč u téhož textu 1279/1279 100%   nové

Korpus **32 léčiv / 1 340 řádků** (bylo 1 346, minus 6 duplicit).

## Co se změnilo

**Slovník dotazů** (`common/dotazy.py`, `slovnik_dotazu.json`)
- hledání klíče z PODŘETĚZCE na porovnání PO SLOVECH (prefixy)
- klíč `tlak` odstraněn — měl shodné hodnoty s `vysoký tlak`, ale
  přidával `hypertenze` i k „nízký tlak" a „tlak v uchu"
- `rýma` → kmen `rým` (byl to jediný klíč jako plný 1. pád)
- `kasel`/`kasl` sjednoceny, další pády na kmeny; 24 → 22 klíčů

**Fulltext** (`common/hledani.py`)
- varianty ze slovníku jdou POPRVÉ do fulltextu (dosud jen do vektorů)
- AND uvnitř řízeného pojmu, OR mezi pojmy
- původní věta zůstává na OR — přísný AND by u „mám rýmu" vyžadoval
  i „mít" a nenašel NIC
- změřeno: `rýma` 43 → 5 řádků, `mám reflux` 23 → 6

**Evaluace** (`evaluate.py`)
- vzorek ZMRAZEN do `vzorek_eval.json`, losování se nepouští
- práh se předává do `test2` i `test4` (dřív jen do `test3`)
- `test4` vypisuje obě čísla, s prahem i bez
- dvě nové kontroly v TEST 0: duplicitní řádky, jednotný klíč

**Data** (`ocisti_json.py`)
- 6 úplných duplicit odstraněno, 4 klíče sjednoceny

## Co to přineslo

**Parafráze na produkčním prahu 9/10 → 10/10.** Dotaz „mám rýmu"
vracel ENDITRIL, HIDRASEC a IMODIUM — tři léky na průjem. Příčina:
klíč slovníku byl `rýma` a hledal se jako podřetězec, takže se
v „rýmu" netrefil a rozšíření se VŮBEC nespustilo.

**Měření je poprvé porovnatelné napříč změnou dat.** Po
`naplni_db.py --znovu` vyšla všechna čísla kvality hledání identicky.
Dřív by se vzorek přelosoval (shoda 5 řádků z 60).

## Co zbývá

- **KROK 0,7** — nesmyslná laická zjednodušení („kyselé řinčení do
  krku", „zamezování léčbě", „při alenzii"). Šest nálezů je v `todo.md`.
- **KROK 3** — omezit, kdy smí klíč sám prosadit výsledek. Měření
  ukázalo, že přísnou pojistku nasadit NELZE, dokud se neopraví
  porovnávání slov (viz `poznatky.md` 22. 9.).
- **KROK 4** — přeměřit prahy a váhy. Až po KROKU 3.
- `zánět kůže` jako přímý dotaz pořád zasahuje 43 řádků, protože
  původní dotaz zůstává na OR. Zvážit AND s návratem k OR, když
  AND nenajde nic — ZMĚŘIT.

## Pozor při spouštění

`vzorek_eval.json` **nemazat** — smazáním se vzorek přelosuje
a čísla přestanou být porovnatelná s minulými běhy.

---

# STAV K 4.9.2026 — HOTOVO, PŘIPRAVENO K PŘEDVEDENÍ

**CLI, API i GUI jsou hotové a odzkoušené. Nic neběží na pozadí.**

    docker compose up -d
    uv run uvicorn api:app --port 8000
       aplikace  http://localhost:8000/
       Swagger   http://localhost:8000/docs

Dokumentace: **`scenare.md`** (co zadávat při předvádění), **`gui.md`**
(jak funguje aplikace a API), `hledej.md` (jak funguje hledání),
`poznatky.md` (nejnovější nahoře), `pristupy.md`, `stavy.md`, `todo.md`.

---

## Co je hotové

### Data — 32 léčiv

| krok | skript | výsledek |
|---|---|---|
| stažení ze SÚKL | `stahni_data.py` | 26 léčiv vč. SPC PDF |
| konverze | `konvertuj_spc.py` | Docling, backend `pypdfium2` |
| sekce + ořez | `extrahuj_sekce.py` | **128/128** |
| JSON | `extrahuj_json.py` | 128/128 |
| řízené slovníky | `ocisti_json.py` | bez modelu |
| rozdělení výčtů | `rozdel_vycty.py` | 3 položky → 15 |
| kontrola proti zdroji | `zkontroluj_json.py` | deterministická |
| kontrola jiným modelem | `zkontroluj_modelem.py` | gemma4:31b |
| číselník pojmů | `postav_slovnik.py` | **593 dvojic, 70 ručně** |

Stavy: `ok` 118, `zamitnuto_kontrolou` 9, `castecna` 1.

### Databáze — 1 346 hledatelných řádků

| sekce | řádků |
|---|---|
| nezadouci_ucinky | 895 |
| indikace | 166 |
| kontraindikace | 150 |
| davkovani | 103 |
| atributy | 32 |

### Hledání

Router → filtry + sekce, hybridně cosine (bge-m3) + český FTS přes RRF.
Nad tím tři režimy, které vznikly z měření:

- **běžné hledání** — parafráze laika, práh 0,55
- **čtení sekce** — dotaz jmenuje lék a sekci → celá sekce v pořadí
  dokumentu (řadit podle podobnosti tam nemá co měřit)
- **řízené hodnoty** — název, látka, síla, ATC, frekvence → práh se
  neuplatňuje, výběr už udělal filtr

**Pojistka proti nedeterminismu routeru:** do hledání jde vždycky i
**původní věta uživatele** jako další varianta. Router totiž z „bolí mě
zuby" udělá jednou `bolest zubů`, jindy jen `zuby` — a to má 0,396, tedy
pod prahem. Bere se maximum přes varianty, takže horší nemůže uškodit.

### Evaluace (reprodukovatelná, dva běhy dají totéž)

```
Invarianty filtru           212/212   100%
Auto-recall @5               47/47    100%
Auto-recall @10              56/56    100%
Negativní dotazy (práh 0,60)  7/8      88%
Parafráze (ručně)            10/10    100%
```

Z 60 vzorků je měřitelných 50 (@5) a 54 (@10) — zbytek má text shodný
u víc léčiv, než je hranice, takže tam není co řadit.

Jediný neúspěch: `léčba roztroušené sklerózy` → AMOKSIKLAV 0,564
(„rozlitého zánětu kůže"), tedy nový řádek z rozdělení výčtu.

### Aplikace

`api.py` (FastAPI, Swagger na `/docs`) + `static/` (vanilla JS).
Výpis 26 léčiv A–Z se stránkováním a řazením, hledání s výpisem toho,
co vrátil router, vynucení sekce, rozbalovací metadata, odkaz do PDF
na nalezenou stranu, ATC záchranná síť, **posuvník prahu podobnosti**,
předehřátí modelu při startu.

---

## ZMĚNY 4.9. — klíč pro hledání a český lematizátor

1. **Klíč pro hledání** (`klic`) u indikací a kontraindikací — 1–4 slova
   v 1. pádě. **Uživatel dál vidí původní text**, klíč je rejstříkové
   heslo. HIDRASEC PRO DĚTI na dotaz „průjem" z 0,515 na **0,807**.
   219 klíčů, ověřeno napřed na 10 položkách (`test_klice.py`).
2. **Dva vektory na řádek** (text i klíč), bere se lepší — kdyby jen
   klíč, tři z deseti položek by se zhoršily.
3. **Deterministická pojistka** `klic_ma_oporu()` — klíč bez opory
   v původním textu se zahodí. Model překládal „nahoru".
4. **Český lematizátor ve fulltextu** (hunspell-cs, 261 tis. slov)
   přes `Dockerfile.postgres`. Postgres češtinu mezi svými 29 stemmery
   nemá. **Dotazů bez fulltextové shody z 5 na 1 ze 17.**
5. **Práh 0,55 → 0,60**, přeměřeno.

**Pozor při spouštění:** Postgres se teď **staví z vlastního image**.
První `docker compose up -d` bude chvíli buildovat.

---

## ZMĚNY 25.8.

1. **Korpus 26 → 32 léčiv.** Doplněna celá skupina **A07 (průjem)**, aby
   šla předvést matice filtrů: IMODIUM/ENDITRIL/HIDRASEC (OTC),
   HIDRASEC PRO DĚTI a ERCEFURYL (Rx), CEDEPOS (Rx **hrazený**).
   HIDRASEC je zajímavý — tatáž látka je ve 100 mg volně prodejná
   a ve 30 mg pro děti na předpis.
2. **Slepený nadpis** `## 4. KLINICKÉ ÚDAJE4.1 TERAPEUTICKÉ INDIKACE`
   schoval CEDEPOSu celou sekci indikací. Doplněn záložní vzor, který
   povolí číslo kdekoliv v nadpisu — pouští se až když selže přísný.
3. **Model přeložil „akutní průjem" jako „náhlý ZÁŠKRT"** (difterii)
   u ERCEFURYLU. Opraveno v datech i v ručním číselníku. **Prošlo to
   oběma kontrolami**, protože obě ověřují odborný text proti zdroji —
   laický tvar se dnes neověřuje nikde. Úkol v `todo.md`.
4. **`prezentace.md`** — nový dokument pro vedení IT, celý řetězec
   od A do Z laicky.
5. **Práh v GUI** — posuvník 0–0,9, výchozí naměřených 0,55.
6. **Pojistka proti ořezání routerem** — do hledání jde i původní věta
   uživatele.

**Rozhodnuto nechat tak:** `hrazený lék na průjem` nevrátí nic. CEDEPOS
má indikaci „infekce Clostridioides difficile", tedy nemocniční infekci,
ne běžný průjem — laik by ho dostat neměl.

---

## DALŠÍ KROKY

### 0. DVĚ VĚCI NAHOŘE V `todo.md` — objeveny 4.9.

- **Klíč zvedá i nesouvisející věci.** „Mám rýmu" → přes slovník
  „zánět sliznice nosu" → **AMOKSIKLAV „zánět kosti" 0,692**. Potřetí
  týž vzor: obecné slovo v hodnotě číselníku přitáhne celou svou třídu.
- **Rozšíření dotazu nejde do fulltextu.** `rýma` → OLYNTH fts 0,0,
  ale `zánět sliznice nosu` → **12,0**, přestože je to hodnota ze
  slovníku pro tutéž rýmu. Číselník byl postavený přesně pro tohle
  a fulltext to nikdy nedostane.

Řešit v tomhle pořadí — druhé bez prvního nafoukne šum i do fulltextu.

### 1. Ruční projití dat — jediné, co brání „čistému" demu

| co | kde |
|---|---|
| 7 sekcí označených kontrolou | `todo.md` |
| TALVOSILEN — model ztratil část výčtu (bolest hlavy, zubů, nervů) | `todo.md` |
| ZYRTEC — „obecní skupina" místo „obecná" | `todo.md` |
| 1 položka s frekvencí „nejčastějším" (nenormalizovaná) | `todo.md` |

### 2. Nestabilita routeru — vědět o ní při předvádění

`časté nežádoucí účinky amoksiklav` občas ztratí název léčiva a místo
6 položek vrátí 2. **Když se to při ukázce stane, stačí dotaz zopakovat.**
Návrh deterministické pojistky (dohledat název v DB) je v `todo.md`.
Dnes to nechytí žádný test.

### 3. Nedodělky

- **Logování** (krok 16) má zatím jen embedding, zapojit do kroků 1–5
- **Řazení ve výsledcích hledání** — teď jen relevance
- **Filtry Rx/OTC klikáním** v GUI — jde jen dotazem nebo přes API
- **Stránkování hledání** se dělá až v paměti
- Česká **stop-slovníková konfigurace** pro FTS — doměřeno, dopad malý
- **Váha fulltextu podle typu dotazu** (router typ zná přes `je_presny()`)

### 4. Rozhodnutí, která jsou na tobě

- **Generovat nové dvojice slovníku přes `gpt-5-nano`?** Levné a lepší
  čeština, ale naráží to na premisu „všechno lokálně". SPC jsou veřejné
  dokumenty SÚKL, takže riziko je malé — pokud se to tvrzení vedení
  říká, musí se upřesnit.
- **Embedovat odborný a laický tvar zvlášť?** Měřeno: laický opis ředí
  podobnost. Znamená přegenerovat embeddingy (~20 s běhu).

---

## Jak spustit

    uv run python priprav_infrastrukturu.py     # pgpass a bind-mounty
    docker compose up -d
    uv run python pipeline.py --stav            # kde jsme
    uv run uvicorn api:app --port 8000          # GUI + API
    uv run python hledej.py --nahrej            # CLI: předehřát PŘED ukázkou
    uv run python evaluate.py

**Po změně dat vždy v tomhle pořadí:**

    uv run python ocisti_json.py --zapis
    uv run python naplni_db.py --znovu          # --znovu POVINNĚ
    uv run python vytvor_embeddingy.py
    uv run python evaluate.py

## Co pohlídat

- **`naplni_db.py` bez `--znovu` data ZDVOJÍ.** Skript to nově odmítne,
  ale pořadí výš je bezpečnější.
- **Po změně schématu odpovědi restartovat API.** `--reload` po čase
  přestal zabírat a server běžel na starém kódu.
- **Poměr zdrojů sekcí je regresní test** (`extrahuj_sekce.py`).
- **Testovací případy OVĚŘOVAT proti datům, ne vymýšlet.**
- **Nepouštět běhy přes `tail`** — buffer schová průběh i chyby.
- **Přeextrahování chyby neopraví**, jen je přesune jinam.
- **Diakritika v konstantách** — předpony psané v ASCII tiše nefungují.
- **Popisek je součást odpovědi.** Třikrát dnes vypadala chyba tam, kde
  nebyla, protože text tvrdil něco jiného než data.
- **`num_ctx` nejít pod 16384** — Ollama delší prompt tiše usekne.

---

# ROZPRACOVÁNO 23.9.2026 — rozvaha nad rozšířením korpusu do cloudu

Zadání: předvedení pro management má obsahovat mnohem víc léčiv,
ideálně všechna obchodovaná. Protože je to jednorázový extrakt,
zvažuje se, že zjednodušení a klíče udělá cloud, protože lokálně
to trvá. Embedding a router zůstávají lokálně tak jako tak.

**Závěry i s čísly jsou v `poznatky.md` nahoře.** Tady jen stav a
další krok.

## Co je hotové

- **`bench_zjednoduseni.py`** (nový soubor) — izoluje krok „laický
  tvar + klíč". Vstupem je hotové `doslovne` z korpusu, takže modely
  dostanou bajt po bajtu totéž a liší se jen výstupem. Metriky jsou
  deterministické (`klic_ma_oporu`, délka klíče, podíl slov laického
  tvaru bez opory ve zdroji). Umí `--effort` pro `reasoning_effort`
  a průběžně ukládá do `bench_zjednoduseni.syrove.json`.
- **Cílený regresní test** na 8 známých nesmyslech z `poznatky.md`
  — proběhl na všech třech modelech, výsledky zapsané.
- **Cenový model** pro 6 618 SPC, ceník ověřen 23.9.2026.
- **Časová bilance** celé pipeline pro 6 618 SPC.

## Co běží / co zbývá dokončit

**HOTOVO.** Velký benchmark na 106 položkách z 8 léčiv doběhl pro
všech 5 konfigurací (qwen3.5, nano výchozí, nano `minimal`, luna
výchozí, luna `none`). Tabulka je v `poznatky.md`.

Historie, ať se chyba neopakuje — běh byl spuštěn dvakrát:

- první běh shodilo zavření IDE ve 3/4; výsledky se zapisovaly až na
  konci, takže se ztratily. **Opraveno na průběžný zápis.**
- druhý běh spuštěn; jestli nedoběhl, **stačí ho pustit znovu se
  stejnými parametry a naváže tam, kde skončil**:

      uv run python bench_zjednoduseni.py --leciv 8 \
          --cloud gpt-5-nano,gpt-6-luna

  Trvá ~35 min (qwen ~12, nano ~18, luna ~6). Jestli
  `bench_zjednoduseni.syrove.json` existuje, nic se neplatí znovu.

Utraceno na OpenAI celkem ~0,08 $ za všechna měření.

**Hlavní výsledek:** vypnutí reasoningu (`minimal` u nana, `none`
u luny; každý bere jen to své, druhé vrací 400) stojí nejvýš setinu
opory klíče, ale je 16× rychlejší a 21× levnější. Cena pro 6 618 SPC
klesla ze 46,56 $ na 4,77 $, resp. 2,38 $ přes Batch. Tím **cena
přestala být kritériem** a rozhoduje jen to, že luna jako jediná ze
tří skutečně překládá latinu do laické češtiny.

## Další krok — a je jiný, než zadání čekalo

Měření otočilo pořadí priorit:

1. **Kontrola laického tvaru proti zdroji.** Dnes obě kontroly ověřují
   `doslovne`, ne `laicky`, takže zkomoleniny projdou. Nesmysly jsou
   nedeterminismus, ne neschopnost modelu — na 6 618 SPC je vyrobí
   kterýkoli model. **Tohle musí být hotové PŘED hromadným během.**
2. **Zmrazit vzorek pro `evaluate.py` test 2**, jinak po rozšíření
   korpusu nebude vidět, jestli si člověk pohoršil.
3. **Deduplikace na registrační číslo** — 8 803 kódů SÚKL je jen
   6 618 SPC, tedy o 25 % méně práce.
4. **Paralelizovat Docling.** 61 h z celkových 347 h a cloud na to
   nemá vliv; OCR podle logu jede na CPU.
5. Teprve pak rozhodnout o cloudu. Pokud ano, pak **gpt-6-luna, ne
   gpt-5-nano** (jako jediná ze tří skutečně překládá do laické
   češtiny; nano je zároveň nejpomalejší i nejdražší) a **vždy
   s nastaveným `reasoning_effort`**, protože ten rozhoduje mezi
   účtem 2 $ a 47 $.

## Peníze

Na OpenAI je vyhrazeno 10 $. Zatím utraceno řádově pár centů
(regresní test + dva částečné benchmarky). Pozor: `config.OPENAI_MODEL`
je pořád `gpt-5-nano`.

---

# KDE JSME A KAM SE POSOUVÁME (23. 9. 2026)

## Kde jsme

**Aplikace je hotová a předvedená** na 32 léčivech / 1 340 řádcích.
CLI, REST API i webové GUI fungují, hledání je naměřené (viz nahoře).

Dnešek byl celý o otázce **„jak z 32 léčiv udělat celý trh"** a o tom,
proč model vyrábí nesmysly. Odpovědi změnily zadání na třech místech:

| co se čekalo | co se změřilo |
|---|---|
| korpus má ~8 000 léčiv | **6 618 SPC** (SPC je na registrační číslo, ne na kód SÚKL) |
| nesmysly = slabý model, pomůže cloud | **nedeterminismus** — 8 z 8 zmizelo při druhém běhu qwenu |
| Docling je pomalý | **Docling vůbec nejede** (`InvalidCxxCompiler`) |
| pymupdf4llm slévá frekvence | na 8 léčivech **drží vazbu shodně** s Doclingem |
| cloud je drahý | **~2,7 $** za korpus, když se vypne reasoning |

## Kam se chceme posunout

Cíl: **předvedení pro management nad celým trhem, ne nad 32 léky.**

Rozpočet práce pro 6 618 SPC dnes vychází na **347 h sériově**, tedy
14,5 dne non-stop na i5 notebooku. Cesta tam vede přes čtyři věci
v tomhle pořadí — a **pořadí je záměrné**, protože každá další je
levnější, když se udělá ta předchozí:

1. **Zprovoznit a zrychlit konverzi** (61 h). Nejdřív
   `TORCHDYNAMO_DISABLE=1`, bez ní nejede nic. Pak `do_ocr=False`
   (−15 % zadarmo) a doměřit pymupdf4llm (~3,9×). Cíl: **z 61 h na
   jednotky hodin, bez serveru.**
2. **Kontrola laického tvaru proti zdroji.** Dnes ji nedělá nikdo.
   Bez ní se nesmysly rozmnoží na 278 000 řádků, kde už je nikdo
   očima nenajde. **Tohle blokuje hromadný běh.**
3. **Zjednodušení + klíče přes cloud** — gpt-6-luna, reasoning
   vypnutý, Batch API, ~2,7 $. Nahradí 197 h lokální extrakce.
4. **Evaluace zjednodušení a klíčů** v `evaluate.py`, aby bylo vidět,
   jestli si člověk polepšil. Dnes se měří jen hledání.

Až tohle bude, zbývá přeměřit prahy a váhy — jsou naměřené na 32 lécích
a na 278 000 řádcích neplatí. K tomu je potřeba **zmrazený vzorek**,
jinak nejsou běhy porovnatelné.

## Co zůstává lokálně za všech okolností

Embedding (bge-m3), router, hledání, kontroly. Do cloudu jde **jen
zjednodušení a klíče**, protože jen tam se ukázal rozdíl v kvalitě.

## Peníze

Rozpočet 10 $ na OpenAI. Utraceno dnes ~0,10 $ za všechna měření.
Odhad hromadného běhu ~2,7 $. **`config.OPENAI_MODEL` je pořád
`gpt-5-nano` a je potřeba ho změnit** na `gpt-6-luna`.
