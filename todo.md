



# TODO — přepsáno 14. 10. 2026 proti kódu

Hotové a zastaralé úkoly (úklid, přenos na server, cloudová extrakce,
rozhodnutí před během) jsou smazané – předchozí verze je v gitu
(`git log -p todo.md`), starší úkoly do 25. 9. v `docs/archiv_todo_2026-09.md`.
U každého bodu je v závorce, **o co se opírá v kódu**.

## 0. Upravy a opravy vzesle s jednani s mgmt IT
2. Udelat si stats do konce roku na openai tokeny
3. Nejde hledani dle konrketniho veku.
---

## 1. Kvalita hledání – nejasnosti, kde nevím, jestli to funguje dobře

Evaluace teď: parafráze **18/20** (30. 9. bylo 20/20), přesnost 69 %,
negativní 5/6 (`logs/evaluace_po_prenosu.log`, 9. 10.).

- [ ] **Je 18/20 regrese, nebo šum routeru?** Pustit
      `hledani_evaluace.py --korpus` ještě 2×. Router není deterministický
      (±4 b.), jeden běh nestačí k závěru.
- [ ] **Dva propadlé dotazy:** „kašlu a nejde mi vykašlat hlen" (R05)
      a „pálí mě při močení" (J01/G04) – `hledani_log.py "…"`: vypadla
      po promptu indikací v2 položka, která dotaz dřív chytala?
- [ ] **Sada `PARAFRAZE_KORPUS` je malá a ATC seznamy úzké**
      (`hledani_evaluace.py:205`): V11 bylinné čaje u „pálí mě při
      močení" chybí → přesnost je podhodnocená. Rozšířit o legitimní
      skupiny, homeopatika V12 rozhodnout (bod 5). Případy ověřovat
      proti datům.
- [ ] **Jeden negativní dotaz propadá** (5/6) – zjistit který (dřív
      „jak vyměnit pneumatiku" → LIDOCAINE 0,652) a proč ho router pustil.
- [ ] **Práh 0,60 přeměřit na celém trhu** (`hledani_evaluace.py --prahy`).
      Naměřený na 32 lécích; pouští falešné shody („kocovina" → covid,
      „plešatost" → čaje na plynatost). Pak přeměřit i váhy (`--vahy`).
- [ ] **Hledací slovník přidává ke každému dotazu s „bolest" obecné
      varianty** `bolest`, `bolesti`, `tlumení bolesti` (`rozsir("bolest
      hlavy")`). Řádky s klíčem „bolesti" pak mají 1,000 a A–Z je dá
      nahoru: „volně prodejný lék na bolest hlavy" → AESCIN TEVA „bolest
      (i rozšířená po těle)", „lék začíná ibal na bolest zubů" → gel
      „místní léčba bolesti". Projít heslo `bolest` ve slovníku
      (`/api/slovnik`) – obecné slovo do variant nepatří (CLAUDE.md).
- [ ] **A–Z u shod 1,000 dává nahoru nemocniční léky:** „mám horečku" →
      radiofarmakum 2-[18F]-FDG první, „horečka dítě šest let" →
      CEFTAZIDIME (injekce). Uvnitř shod 1,000 řadit OTC / běžné formy
      dřív (navazuje na „Laik dostává nemocniční léky").
- [ ] **Holá indikace „léčba"** (HUMULIN N u „cukrovky", 1,000) – vada
      extrakce; změřit, kolik indikací je jen „léčba" / „bolest".
- [ ] Příklady v GUI (`PRIKLADY` v `static/app.js`) po každé změně
      hledání nebo dat projít znovu – ověřené 14. 10. na 1. stránce.
- [ ] **Věk nemá evaluaci.** V `hledani_evaluace.py` žádný test na
      „pro děti / dítě X let" není. Sada s ověřeným očekáváním: žádný lék
      s `vek_od > X`, ASPIRIN nesmí u horečky dítěte.
- [ ] **Test 0 „Podezřelé sekce" hlásí 99 %** (`hledani_evaluace.py:84`,
      heuristika > 30 indikací / < 3 NÚ / > 400 znaků je z 32 léků) –
      přeměřit na korpusu, jinak test nic neříká.
- [ ] **Laik dostává nemocniční léky:** kojenci → injekční antibiotika
      (MEDOCLAV, TAXIMED), „kašel pro děti" → DALACIN, PARACETAMOL infuze.
      Hledání formu podání ani OTC neupřednostňuje (`lekova_forma` se jen
      vypisuje, `common/hledani.py:473`). Návrh: OTC dopředu,
      injekce/infuze dozadu.
- [ ] **Shody 1,000 jsou abecedně (14. 10.), ale A–Z o kvalitě nic
      neříká:** „mám rýmu" má 22 léků s 1,000 a nahoru jdou i ALYOSTAL
      PRICK (alergenový test) nebo ERDOMED; v evaluaci 4/5 → 2/5. Uvnitř
      skupiny 1,000 by šlo řadit podle dalšího znaku (OTC, forma podání,
      fulltext) – navazuje na bod „Laik dostává nemocniční léky".
- [ ] Je-li shod 1,000 víc než kandidátů (`KANDIDATU` = 100 řádků),
      o tom, které se do výběru vejdou, rozhoduje pořadí v DB (ctid).
- [ ] **GUI „Fulltext: nenašel" je zavádějící** (`static/app.js:257`) –
      řádek fulltext našel, jen se nevešel do `KANDIDATU_FTS`. Psát
      „mimo prvních N".
- [ ] (až bude vidět, že trpí odborné dotazy) samostatné vektory laický /
      odborný místo „laický (odborný)" (`extrakce_4_db.py:152 _spoj`);
      přepočet všech vektorů ~2 h.

## 2. Kvalita extrakce – nic ji nekontroluje

Všechny sekce jsou `neovereno`, `config.KONTROLY_ZAPNUTE = False`.
Skripty v `nerealizovane_kontroly/` čtou smazané `data/leciva/` – nad
korpusem nejdou pustit.

- [ ] **Kontroly přepsat na `data/spc` a zařadit jako krok za extrakci**
      (`extrakce_all.py` `KROKY` + `docs/pipeline_prehled.md`). Co chybí:
      `nerealizovane_kontroly/kontroly_popis.md` kap. 3 – N1 laický tvar
      proti zdroji (neověřuje se vůbec), N2 opora klíče proti `doslovne`,
      N3 klíč 1–4 slova / ne obecný (22 % klíčů > 4 slova), N4 vazba
      účinek→frekvence. Dodělat **před prvním měsíčním během**.
- [ ] **Regresní sada známých zmetků**, kterou kontroly MUSÍ chytit:
      ULTRACOD „alenzie", OMEPRAZOL „řinčení", BISACODYL „ve třasu",
      „akutní průjem" → „náhlý záškrt", HIDRASEC klíč „onemocnění".
- [ ] **`ocisti_json.py` pro korpus** (dnes čte `data/leciva/`): duplicitní
      řádky a 274 textů s víc různými klíči.
- [ ] **Soudce nad novou DB** (`benchmarky/indikace_fragmenty/soudce.py`) –
      skutečný podíl chybných položek indikací po promptu v2 (před: ~4 %;
      detektory: podezřelých 6 427 → 5 944).
- [ ] **COLDREX HORKÝ NÁPOJ 0260480 – tři chyby** (poznatky 6. 10.):
      (1) holá „bolest" z „a s ním spojená bolest" – pravidlo o odkazech
      na předchozí část věty do promptu indikací (37 léků má holou
      „bolest"); (2) skupina v samostatném odstavci nepřiřazena (12 282
      z 25 097 indikací bez skupiny – změřit, kolik ji v textu má);
      (3) věk 18 místo 15 (`common/vek.py`) – zákaz podmíněný hmotností;
      úzká oprava rozbije 6× VORICONAZOLE.
- [ ] **Dávkování: `pacient` je volný text** (18 230 různých popisů,
      45 % nejde zařadit podle věku). Bez modelu: při plnění DB odvodit
      štítky (věk, ledviny, játra, hmotnost…). Pro měsíční job: schéma
      `pacient` → `vek` / `stav` / `podminky`, přeextrahovat 4.2 (~2 $),
      nejdřív na vzorku.
- [ ] **Dávkování z Markdownu místo surového textu?** (`common/sekce.py`:
      4.2 bez tabulky → `pymupdf_raw`). Změřit na vzorku, jestli Markdown
      zachová nadpisy „Pediatrická populace".
- [ ] **Nadpis jako odrážka** („- 4.8 Nežádoucí účinky", 13 z 5 880 SPC) –
      `common/sekce.py` ho nepozná; opravit až s regresní sadou konverze
      (bod 3), pozor na „- 4.8 mg".
- [ ] 4.4 (zvláštní upozornění, např. Reyeův syndrom u aspirinu) se
      neextrahuje (`SEKCE_SPC` jen 4.1/4.2/4.3/4.8) – zvážit pediatrická
      upozornění.

## 3. Měsíční job (`extrakce_all.py` cronem)

Hotovo: 7 kroků v `KROKY`, zámek, log, návratové kódy, ověření doběhnutí
extrakce, rozpočtový strop s odhadem před odesláním (`extrakce_3_json.py`),
navazování po pádu v krocích 1 a 3.

- [ ] **`extrakce_all.py --vse` jednou celé naostro** (po úklidu neběželo;
      peníze, hodiny, TRUNCATE DB).
- [ ] **DB přírůstkově:** `extrakce_4_db.py --korpus` dělá `TRUNCATE
      leciva CASCADE` (`:453`). Upsert po SPC, zaniklá SPC označit jako
      neaktivní, nemazat. Tabulku `slovnik_dotazu` při přepisu nesmazat
      (dnes ji TRUNCATE nezasáhne – nemá cizí klíč).
- [ ] **Embeddingy jen pro nová / změněná SPC** (celý přepočet ~2 h).
- [ ] **Změněné SPC → jen ta do extrakce.** Nová verze CZ SPC = nová
      identita (`extrakce_1_konverze.py:175`); chybí otisk obsahu PDF
      a propagace „zaniklé" přes kroky 2–5.
- [ ] **Souhrn běhu jako JSON** (nová / změněná / zaniklá, chyby,
      podezřelé, čas, cena, čísla evaluace) + prahy pro upozornění.
      Kam upozornění posílat – rozhodnout.
- [ ] `--dry-run`: jen ukázat, co by se zpracovalo.
- [ ] Konfigurace z prostředí ještě chybí pro OpenAI (model, strop
      `CLOUD_STROP_USD`) a prahy – Ollama, Postgres, Docling Serve už ano
      (`common/config.py`).
- [ ] Kontrola volného místa před během (`/opt` 18 GB volných; kolik
      navíc potřebuje plnění od nuly – WAL, mrtvé řádky).
- [ ] **`.doc` SPC na Linuxu** – převod přes Word/PowerShell
      (`extrakce_1_konverze.py:525`) na serveru nepoběží; náhrada
      LibreOffice (4 dokumenty z 5 880).
- [ ] **Regresní sada kontroly konverze** (`common/kontrola_konverze.py`):
      ok – PARALEN cz_82842, ERMM-1 cz_87529, CAVINTON cz_10145, ACECOR;
      podezření – MENOPUR cz_95795, AUBAGIO, CASARO; nadpisy „4. 8.",
      „4.8.Nežádoucí", „4.8)." není nadpis, „4.81" není 4.8.
- [ ] Nastavit cron `extrakce_all.py --vse` (zatím žádný není).

## 4. Provoz na serveru – co zbývá

- [ ] Povolení portu 8090 v síti → ověřit
      `https://t-api-dlp01.sukl.cz:8090/` z počítače uživatele.
- [ ] Ze serveru ověřit dosah na Docling Serve, OpenAI, SÚKL a EMA.
- [ ] Smoke test zbývá: `bench_soubeh.py --simulace`,
      `extrakce_6_rejstrik.py` (symlinky), GUI; služba `localsemantic-api`
      po skutečném restartu serveru.
- [ ] Záloha DB (`pg_dump` do souboru); `data/pgdata` nebalit tarem s `data/`.
- [ ] `data/localsemantic.dump` (2,9 GB) po ověření provozu smazat.
- [ ] **Zápis do hledacího slovníku je bez přihlášení**
      (`api.py:509` POST/DELETE `/api/slovnik`) – před zveřejněním
      rozhodnout, kdo smí.
- [ ] Certifikát platí do 17. 3. 2027; po výměně `nginx -s reload`.
- [ ] Soubory pro Docker (`Dockerfile.postgres`, `tsearch/`,
      `pgadmin-servers.json`, `pgpass`) jsou v kořeni – do `docker/`?
      (úprava `docker-compose.yml`, `provoz_priprava.py`, znovusestavení)

## 5. GUI a data pro laika

- [ ] **Filtry Rx / hrazeno berou jen zástupce SPC** (`common/hledani.py:216`,
      `l.hrazeno`). Liší se u 151 SPC (hrazení) a 37 (Rx/OTC) → filtr
      „aspoň jedno balení splňuje" (EXISTS přes `leciva.spc`).
- [ ] **Seznam balení u léku** – GUI ukazuje jen zástupce, ostatní kódy
      SPC (síla, balení, hrazení) nevidí (`api.py:269`).
- [ ] **`vek_duvody` ukázat v GUI** (proč „od 3 let") – API vrací jen
      `vek_od` / `pro_deti` (`api.py:129`).
- [ ] **Hledací slovník projít proti korpusu** (`/api/slovnik/formulace`) –
      např. formulace u `reflux` už v datech není (0 léků).
- [ ] **Homeopatika a přípravky bez SPC:** 333 homeopatik bez SPC
      a 85 neregistrovaných F/I se nevedou (`extrakce_1_konverze.py:279`).
      Návrh: příznak `ma_spc`, nahrát jen sekci `atributy`, popisek „bez
      SPC – údaje jen z registru"; test, že dotaz na příznak nevrátí
      přípravek bez SPC. **ROZHODNOUT obsahově: 25 homeopatik SE SPC**
      (Oscillococcinum, Traumeel…) – nechat / označit / vyřadit z hledání
      podle příznaků.
- [ ] (pro produkci) hledací řádky navázat na SPC, ne na kód – zástupce
      je zkratka.

## 6. Víc uživatelů najednou

Rozdělování mezi stroje s Ollamou je hotové (`common/ollama_client.py`).

- [ ] **Dell 10.6.38.9 zapojit:** otevřít port 11434, stáhnout
      `gemma4:26b` a `bge-m3` ve stejných tazích jako Spark, pak
      `bench_soubeh.py` (čekání 8 uživatelů ~14 s má klesnout na půl).
- [ ] **`OLLAMA_NUM_PARALLEL`** – globální pro stroj, násobí paměť na
      kontext i u qwen3.5:122b. Změřit, pak zvednout `OLLAMA_SOUBEZNE`.
- [ ] Výběr stroje i podle odezvy – `odezva_s` se měří, ale
      `vyber_uzel` ji nepoužívá (`common/ollama_client.py:205`);
      vytížení od jiných procesů aplikace nevidí.
- [ ] Víc procesů API (uvicorn workers) – každý počítá vytížení sám.
- [ ] Počítadlo v GUI: kolik lidí má aplikaci otevřenou, kolik hledání
      běží, stav strojů (je v `/api/stav`).
