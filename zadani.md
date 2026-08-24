# Zadani
Vytvori aplikaci, ktera bude hledat v lecivech formou TSV i Embedu pres jeden vstupni dotaz. V prvni fazi staci CMD aplikace v Python.
V druhe fazi bude nadstavba API a GUI vyhledavaci report. 

# KROKY - prehled celeho postupu

Tady je jen mapa, detaily kazdeho kroku jsou nize v dokumentu.
Tabulka je v poradi, ve kterem se to DELA. Sloupec "Krok" je nazev
pouzity dal v dokumentu a v docstringech skriptu - ten NEMENIT.

**Cela pipeline je jeden spustitelny celek: `pipeline.py`.**
Kazdy krok jde spustit i zvlast, ale pipeline hlida poradi a kdyz krok
selze, dalsi uz nepousti - cetly by nekompletni data.

    uv run python pipeline.py --stav        # jak na tom jsme
    uv run python pipeline.py --vse         # cely bezh
    uv run python pipeline.py --od extrakce # jen od nejakeho kroku dal

## FAZE A - priprava dat (HOTOVO)

Korpus **26 leciv** (IFIRMASTA 0500896 vyrazena 19.8.2026 na prani uzivatele;
24.8. doplnena 4 leciva, aby sla predvadet matice filtru - viz `scenare.md`).

| poradi | Krok | Skript | Stav |
|---|---|---|---|
| 1. | Stazeni dat ze SUKL (API + SPC PDF) | `stahni_data.py` | HOTOVO - 26 leciv |
| 2. | **Krok 1** - konverze PDF -> Markdown | `konvertuj_spc.py` | HOTOVO - ~30 s/dok |
| 3. | **Krok 2** - vytazeni sekci + orez na jadro | `extrahuj_sekce.py` | HOTOVO - 104/104 |
| 4. | **Krok 3** - prevedeni sekci do JSON + zjednoduseni | `extrahuj_json.py` | HOTOVO - 104/104 |
| 5. | **Krok 3b** - vynuceni rizenych slovniku (BEZ modelu) | `ocisti_json.py` | HOTOVO |
| 6. | **Krok 4a** - kontrola proti zdroji (BEZ modelu) | `zkontroluj_json.py` | HOTOVO - 52 neshod z 959 |
| 7. | **Krok 4b** - kontrola JINYM modelem (gemma4:31b) | `zkontroluj_modelem.py` | HOTOVO - 18 z 268 |
| 8. | **Krok 5** - ciselnik pojmu + kontrola prekladu | `postav_slovnik.py` | HOTOVO - 539 dvojic, 67 rucne |
| 8b. | Rozdeleni vicepojmovych polozek (modelem) | `rozdel_vycty.py` | HOTOVO - 3 polozky -> 15 |

Stavy: `ok` 96, `zamitnuto_kontrolou` 6, `castecna` 1, `neovereno` 1.
Popis v `stavy.md`. Zamitnuto je 6 jednotlivych POLOZEK, zadna cela sekce.

## FAZE B - databaze a hledani

| poradi | Krok | Skript | Stav |
|---|---|---|---|
| 9. | Infrastruktura - docker compose + init-db | `docker-compose.yml` | HOTOVO |
| 10. | DDL - 6 tabulek | `init-db.sql` | HOTOVO |
| 11. | Plneni DB z `json/` + relacnich atributu | `naplni_db.py` | HOTOVO - 1173 radku |
| 12. | Embedding (bge-m3, 1024 dim, HNSW) | `vytvor_embeddingy.py` | HOTOVO - 1173 za ~20 s |
| 13. | Router - dotaz -> filtry + sekce | `common/router.py` | HOTOVO |
| 14. | Hybrid search - RRF nad cosine + ceskym FTS | `common/hledani.py` | HOTOVO |
| 15. | Evaluace - testy 0-4 | `evaluate.py` | HOTOVO - prah 0,55 zmeren, reprodukovatelna |
| 16. | Detailni logovani behu do souboru a do DB | `common/log_behu.py` | castecne - ma ho jen embedding |
| 17. | CLI + seskupeni po lecivech | `hledej.py` | HOTOVO |
| 18. | Doladeni podle nalezu z evaluace | | HOTOVO - viz nize |
| 19. | Rozsireni dotazu + ATC zachranna sit | `common/dotazy.py` | HOTOVO |
| 20. | Doplneni korpusu na 26 leciv pro demo | `postav_pool.py` | HOTOVO - viz `scenare.md` |
| 21. | REST API (FastAPI) se Swaggerem na /docs | `api.py` | HOTOVO |
| 22. | GUI (vanilla JS) | `static/` | HOTOVO - viz `gui.md` |
| 23. | **TADY JSME** - rucni projiti dat + nedodelky | | zbyva |

Krok 18 uzavren 24.8.: opraven router (zapor, lek+priznak), predehrati
modelu pro GUI, a **dotazen slovnik** (pokryti indikaci 3 % -> 39 %,
rucni ciselnik 1 -> 67 dvojic). Uklid TSV domeren a ODLOZEN - zmereno,
ze fulltext dotazy slucuje pres AND, takze u vet skoro nikdy nechytne
a dopad uklidu by byl maly. Podrobne v `poznatky.md`.

**Prace na CLI casti je tim uzavrena. Dalsi faze je GUI** - navod, jak
z nej volat predehrati modelu a hledani, je v `aktualnistav.md`.

### Co jeste zbyva mimo cislovane kroky

- ~~seskupeni vysledku po lecivech~~ HOTOVO
- ~~CLI `hledej.py`~~ HOTOVO
- rucne projit 28 sekci a 24 dvojic slovniku - seznam v `todo.md`
- ~~doplnit slovnik o indikace a kontraindikace~~ HOTOVO 24.8. (39 % / 26 %)
- ~~probrat obsah TSV~~ HOTOVO 24.8. (identita pryc z FTS, OR misto AND)

### Zmeny navrhu z 19.8.2026 (podrobne v poznatky.md)

1. **Indikace a kontraindikace maji stejny tvar jako nezadouci ucinky** -
   dvojice `doslovne` + `laicky` misto holeho laickeho retezce. Leciv
   s pouzitelnymi indikacemi: 9 -> **22 z 22** (po zmene zdroje textu 20.8.). Zaroven tim vznikla kotva
   ke zdroji, takze deterministicka kontrola pokryva 88 sekci misto 46.
2. **Rozpad vyctu na stredniku** pred extrakci - DITHIADEN 4 -> 9 polozek.
3. **Skupina pacientu jako ciselnik** (`skupina` + `skupina_kod`),
   hodnota `neuvedeno` je EXPLICITNI.
4. **Detailni logovani** - do souboru prubezne, do DB davkove.

### Zmeny navrhu z 21.8.2026 (podrobne v poznatky.md)

1. **Zapor je soucast priznaku.** Router z "nemuzu po prascich spat"
   udelal `dotaz_text: 'spat'` a hole sloveso pritahlo zavrate na 0,590.
   Do promptu pridano pravidlo, ze `dotaz_text` musi davat smysl sam o sobe.
2. **"Lek + priznak" jde do OBOU sekci.** "paralen bolest hlavy" je
   indikace, "acc bolest bricha" nezadouci ucinek - z formulace to poznat
   nejde, rozhodnout musi data. Bez jmenovaneho leku plati dal indikace.
3. **Prompt vs. kod:** prompt zadal pri nejistote vycet moznych sekci,
   kod ho pak zahodil (`if jistota == "nizka": sekce = None`). Vycet dvou
   a vic sekci se nove respektuje.
4. **`nahrej()` neumela embedovaci model** - `/api/generate` vraci u bge-m3
   HTTP 400. Pri 400 se nove spadne na `/api/embed`.
5. **NALEZ neopraveny:** slovnik sbira jen z nezadoucich ucinku, indikace
   a kontraindikace jsou bez dozoru (3 % / 1 % pokryti). Odhalilo to
   "neuralgie" -> "bolest podel nervu". Rozepsano v `todo.md`.
6. **NALEZ neopraveny:** laicky opis REDI podobnost - spravna odpoved
   CONTROLOCu na "bolest bricha" ma 0,531, kdezto "bolest hlavy" 0,609.

### Zmeny navrhu z 24.8.2026 (podrobne v poznatky.md)

**Data a extrakce**

1. **Slovnik plati pro vsechny sekce s laickym tvarem**, ne jen pro
   nezadouci ucinky. Klice se normalizuji (`slovnik.klic()`) - male
   pismena, bez koncove interpunkce, bez predpony "lecba/pri".
   Do ciselniku jdou jen terminy do 3 slov; dlouhe vety se neopakuji.
2. **Ciselnik se aplikuje i na hotova data BEZ modelu** (`ocisti_json.py`).
3. **Vicepojmove polozky rozdeleny na samostatne radky** (`rozdel_vycty.py`)
   - MODELEM, ne regexem: zmereno, ze regex by uskodil ve 3 z 5 pripadu.
4. **OCR zameny cislic v nadpisech sekci** (`sekce._cislo_na_vzor()`).
   "## 4.l Terapeuticke indikace" (male L) schovalo celou sekci.

**Hledani**

5. **Do fulltextu jde uz JEN `obsah_text`**, ne `kontext_text` - ten se
   opakuje na kazdem radku a razeni tim slo NAOPAK.
6. **Fulltextovy dotaz se prevadi na OR**, protoze AND kazdym dalsim
   slovem mnozinu zuzoval.
7. **Rozsirovani DOTAZU** (`slovnik_dotazu.json`) o formulace ze SPC.
   Rozsiruje se dotaz, do dat se NIC nepridava - dohledatelnost zustava.
8. **Diakritika se deterministicky obnovuje** (`router.obnov_diakritiku()`);
   jeji ztrata stoji ~0,2 podobnosti.
9. **Zapor je soucast priznaku**, "lek + priznak" jde do OBOU sekci.
10. **Filtr `hrazeny` DOPLNEN** (byl v zadani, nebyl implementovan).
    NENI totez co `na_predpis`.
11. **Frekvence nezadoucich ucinku jako PRESNY filtr** - "vzacne"
    znamena vzacne, ne "vzacne a vse castejsi". `frekvence_rank_max`
    jen u vyslovneho "a castejsi".
12. **Rezim CTENI SEKCE** - kdyz dotaz jmenuje konkretni lek a sekci,
    vraci se cela v poradi dokumentu. Razeni podle podobnosti tam nema
    co merit.
13. **ATC zachranna sit** - kdyz se nenajde nic, nabidne terapeutickou
    skupinu ODDELENE a oznacene jako odvozene.
14. **Prah zvednut 0,50 -> 0,55** po rozdeleni radku. Vychozi i v CLI.

**Evaluace**

15. **Reprodukovatelna** - `test2` mel nefunkcni seed (`ORDER BY random()`
    v Postgresu), takze kazdy beh meril jiny vzorek.
16. **Vzorky, jejichz text sdili vic leciv nez hranice, se vynechavaji** -
    u 12 shodnych radku "kopřivka" neni co radit.

**Aplikace**

17. **Predehrati modelu je v `ollama_client.priprav_modely()`**, aby ho
    mohlo pouzit GUI pri startu.
18. **`naplni_db.py` bez `--znovu` odmitne bezet**, kdyz uz data existuji -
    jinak je TISE zdvoji.
19. **REST API + GUI** - `/api/leciva` a `/api/hledat` vraceji TYZ tvar,
    aby frontend kreslil jednu komponentu.

## Krok 5 (slovnik) UZ JE HOTOVY - zmena oproti puvodnimu planu

Puvodne byl slovnik zarazeny az za evaluaci s oduvodnenim, ze se nejdriv
ma zmerit, jestli ho vyhledavani vubec potrebuje (mozna to bge-m3 zvladne
sam). To oduvodneni **platilo jen pro jednu z jeho roli**. Ukazalo se, ze
ma role dve a ta druha nepocka:

**Role 1 - pomoc vyhledavani** (aby laik nasel "nizky pocet krevnich
destick", kdyz je v datech "trombocytopenie"). Tohle je porad OTEVRENE
a rozhodne se az z evaluace, viz test 2.

**Role 2 - konzistence a kontrola.** Tahle rozhodla o tom, ze slovnik
vznikl hned:

  - Zmereno: 419 unikatnich odbornych terminu, z toho 84 (20 %) melo VIC
    ruznych laickych tvaru - "pancytopenie" mela sest podob, mezi nimi
    rozsypanou cestinu.
  - Laicky tvar NEOVERUJE ani jedna kontrola sekci. Doslovne porovnani
    nemuze (preklad ve zdroji doslova neni) a kontrolnimu modelu je
    v promptu vyslovne receno, ze zjednoduseni se za chybu nepovazuje.
  - Ciselnik je JEDINY auditovatelny artefakt. Projit 419 dvojic v jednom
    souboru jde; totez rozhazene v 738 polozkach napric 23 leky nejde.

Kontrola prekladu nasla **25 vecne spatnych dvojic ze 419**, napriklad
"vyrazka v miste aplikace" -> "Vyprazdneni na miste aplikace" nebo
"parestezie" -> "Ztrata citlivosti" (parestezie je brneni). Bez ciselniku
by to neodhalila zadna jina kontrola.

### Slovnik je obousmerny

    extrakce  --(nove terminy)-->  postav_slovnik.py  -->  slovnik_pojmu.json
    slovnik_pojmu.json  --(kanonicky tvar)-->  extrakce

Extrakce slovnik POUZIVA i PLNI. Kdyz slovnik termin zna, to co vygeneroval
model se zahodi. Nove terminy pribudou pri dalsim behu kroku 5.

**Rucni opravy patri do `slovnik_rucni.json`** - ten se NIKDY negeneruje
automaticky a ma prednost. Bez toho oddeleni by prestavba slovniku
prepsala praci cloveka tim, co vygeneroval model.

## Stavy - viz `stavy.md`

Kazda sekce ma vzdy explicitni stav, nikdy NULL. Uplny popis vcetne
prechodu mezi stavy je ve **`stavy.md`**. Seznam sekci, ktere ceka rucni
projiti, je v **`todo.md`**.

## Pomocne skripty (nejsou soucasti pipeline)

| Skript | K cemu |
|---|---|
| `analyza_formatu.py` | klasifikace sekce 4.8 do peti formatu |
| `zkontroluj_orez.py` | co ORez zahodil, oznaci podezrele pripady |
| `bench_extrakce.py` | rychlost extrakce: modely, num_ctx, tvary JSON, OpenAI |

## Pravidla, ktera plati pruresove

- **Model:** vsechno generativni bezi na `qwen3.5:122b` (`config.MODEL_HLAVNI`).
  Je to MoE - zaroven nejlepsi i nejrychlejsi. Embedding `bge-m3`; generativni
  model embedding NEUMI (vraci 501).
- **OpenAI:** jen `gpt-5-nano` (`config.OPENAI_MODEL`). Na uctu jsou jednotky
  dolaru, gpt-4o nepoustet.
- **Nejdriv pilot**, pak rozsah - viz sekce "NEJDRIV PILOT NA 2-3 LECIVECH".
- **Mezistavy zustavaji na disku** jako soubory, aby se nemuselo pri ladeni
  promptu znovu konvertovat PDF.
- **Stav extrakce se zapisuje VZDY explicitne**, nikdy NULLem - musi se poznat
  "lek nema nezadouci ucinky" od "extrakce selhala". Viz TABULKA 4.


# Vstupni kod
Podivej se vzdy do adresare legacy, kde je spousta kodu, ktery se da znovupozuit nebo upravit pro potreby noveho zdani

# JAK TO MA FUNGOVAT - souhrne a polopate

## Co je v databazi

TABULKA 1 "leciva" - sucha data z API SUKL.
Jeden radek = jeden lek. Nazev, sila, forma, baleni, ATC, ucinna latka,
na predpis ano/ne, hrazeny ano/ne.

TABULKA 2 "extrakty" - co se vytahlo z PDF.
Jeden radek = jedna extrakce jednoho leku. Uvnitr JSONB seznamy: indikace,
kontraindikace, nezadouci ucinky, davkovani. Leku muze byt vic verzi extrakce
(lokalni model, cloud) - proto vic radku na jeden lek.

TABULKA 3 "leciva_search" - vyhledavaci tabulka.
JEDEN RADEK = JEDNA VYHLEDATELNA DROBNOST. Seznamy z tabulky 2 se tu rozpadnou
na jednotlive polozky:

    Paralen, indikace,          "lecba bolesti hlavy"
    Paralen, indikace,          "horecka"
    Paralen, nezadouci_ucinky,  "nevolnost"        (caste)
    Paralen, nezadouci_ucinky,  "bolest bricha"    (vzacne)
    Paralen, davkovani,         "dospeli 500 mg 3-4x denne"
    Paralen, atributy,          "PARALEN 500MG TBL NOB, paracetamol, 0254048"

Radek 'atributy' je jediny, ktery NEPOCHAZI z PDF - je slozeny z tabulky 1
a slouzi k tomu, aby sel lek najit podle jmena/sily/kodu.
Ke kazdemu radku patri vektor (z obsah_text) a fulltextovy index.

## Co se stane pri dotazu

Priklad: "volne prodejne leky na bolest"

KROK 1 - ROUTER (maly model) rozebere vetu na:
    filtr:  na predpis = ne
    sekce:  indikace
    zbytek pro semantiku: "bolest"

KROK 2 - TVRDY FILTR. Z tabulky 1 jen volne prodejne leky, z tabulky 3 jen
radky sekce 'indikace'. Mnozina se zmensi na par desitek radku.
Tohle je deterministicke - bud je lek volne prodejny, nebo neni. Zadne "asi".

KROK 3 - HLEDANI UVNITR te mnoziny. "bolest" -> vektor -> nejblizsi vyznam.
Zaroven bezi fulltext. Vysledky se slouci pres RRF.

KROK 4 - SESKUPENI PODLE LEKU. Hledani vrati radky, ale uzivatel chce leky.
Vezme se cca 50 nejlepsich radku, seskupi se podle kod_sukl a vybere se
N ruznych leku. U kazdeho se pamatuje, KTERY RADEK ho tam dostal = dukaz.

KROK 5 - ZOBRAZENI. Teprve tady se dotahne plny profil kazdeho nalezeneho leku.

## Co se zobrazi - DVE UROVNE, nemichat je

A) PROC SE TO NASLO - ta jedna polozka, ktera vyhrala:

    PARALEN  ->  naslo se v: indikace - "lecba bolesti hlavy"

B) CO TEN LEK JE - plny profil:

    PARALEN 500MG TBL NOB (kod 0254048)
    volne prodejny, nehrazeny, paracetamol
    Indikace:          lecba bolesti hlavy, zubu, horecka
    Kontraindikace:    alergie na paracetamol, tezke jaterni poskozeni
    Nezadouci ucinky:  nevolnost (caste), bolest bricha (vzacne)
    Davkovani:         dospeli 500 mg 3-4x denne, max 4 g/den
    Zdroj:             data/leciva/0254048/spc.md § 4.1

## Co se NEUKLADA a sklada se az pri zobrazeni

- text "bolest bricha (vzacne)" -> slozi se z obsah_text + frekvence
- plny profil leku             -> slozi se dotazem podle kod_sukl

Proto v tabulce 3 NENI zadny sloupec "zobrazovany_text". Byla by to jen
slepenina sloupcu, ktere uz tam jsou.

## Odkud brat plny profil pro zobrazeni

Skladat ho z radku tabulky 3 (leciva_search) podle kod_sukl - jsou tam uz
vsechny polozky rozlozene a je to jeden dotaz. Hlavicka (nazev, sila, vydej,
hrazeni) se bere z tabulky 1.

POZOR - dva detaily, bez kterych to bude spatne:
1. Filtrovat i podle extrakt_id, jinak se u leku se dvema variantami extrakce
   (lokal + cloud) zobrazi kazda indikace DVAKRAT. Musi byt jasne, ktera
   varianta je ta "aktivni" - bud se do tabulky 3 pousti jen jedna, nebo
   se aktivni oznaci priznakem.
2. Radek sekce='atributy' do profilu NEPATRI - je to pomucka pro vyhledavani,
   ne obsah k zobrazeni. Hlavickova data vzit z tabulky 1.

## Souhrn - co je kde

| co                                | kde je ulozene                    |
|-----------------------------------|-----------------------------------|
| fakta o leku (nazev, sila, vydej) | tabulka 1, natvrdo                |
| obsah z PDF (seznamy)             | tabulka 2, JSONB                  |
| jednotlive vyhledatelne drobnosti | tabulka 3, radek na polozku       |
| plny profil pro zobrazeni         | NIKDE - slozi se dotazem          |
| text "bolest bricha (vzacne)"     | NIKDE - slozi se pri vypisu       |

# Vstupni data - rozsah a odkaz
Pridal bych vice leciv. 5 leciv z puvodniho skriptu je hodne malo, aspon 50 lepe treba 500, aby byly lepsi vysledky. Ale vse podle casi extrakce sekci a jejich zjednoduseni. 
Udelal bych test rychlosti a pak se rozhodlo pro finalnie mnozstvi leciv. A tim i menil limit pro dane ATC.
V legaci adresari uz je skript na stazeni uvodnich dat create_sample_data.py.
Nech z puvodniho skriptu roznorodost leciv podle ATC, eu registrace atp.
Uplne nas nezajimaji leky po operaci a centrove leky. Tady ty ATC skupiny bych vyhodil. Zameril bych se hodne na koncoveho pacienta co bere doma. Bude to aplikace pro zacatek pro laiky. 

## ATC whitelist - konkretni seznam

Zamer: jen leky, ktere laik zna a bere doma. Zadne nemocnicni/centrove skupiny.
Delame WHITELIST (ne blacklist) - u whitelistu presne vime, co v demu bude.
Cetnosti overeny na nahodnem vzorku 1300 leciv z dlpo (11.8.2026).

| ATC   | co to je                      | Rx/OTC | cetnost/1300 | limit | zname priklady          |
|-------|-------------------------------|--------|--------------|-------|-------------------------|
| N02BE | paracetamol                   | OTC    | 8            | 5     | PANADOL, PARALEN        |
| N02BA | kyselina acetylsalicylova     | OTC    | 1            | 2     | ANOPYRIN, ACYLPYRIN     |
| M01A  | ibuprofen a dalsi NSAID       | mix    | 23           | 6     | IBALGIN, IBUPROFEN      |
| M02A  | masti/gely na bolest          | OTC    | 2            | 3     | VOLTAREN EMULGEL        |
| A02A  | antacida (palenie zahy)       | OTC    | 2            | 3     | RENNIE                  |
| A02B  | vredova choroba + IPP         | mix    | 26           | 5     | HELICID, LANZUL         |
| R05   | kasel a nachlazeni            | OTC    | 11           | 5     | SINUPRET, HEDELIX       |
| R06A  | antihistaminika (alergie)     | mix    | 18           | 5     | NEOCLARITYN, ZYRTEC     |
| R01A  | nosni spreje (dekongestanty)  | OTC    | 2            | 3     | XYLOMAX NEO             |
| J01   | antibiotika systemova         | Rx     | 23           | 6     | AZITROMYCIN, AUGMENTIN  |
| C10A  | statiny (cholesterol)         | Rx     | 50           | 3     | SORTIS, TORVACARD       |
| A10B  | cukrovka - tablety            | Rx     | 90           | 3     | GLUCOPHAGE (metformin)  |
| C09   | vysoky tlak (ACE/sartany)     | Rx     | 95           | 3     | LOZAP, PRESTARIUM       |

Soucet limitu = 47-50 leciv. Limit na skupinu je dulezity: C09/A10B/C10A jsou
v registru tak caste, ze bez stropu by zabraly vetsinu vzorku a demo by bylo
o tlaku a cukrovce misto o bolesti a alergii.

## POZOR na N02B
Nebrat celou skupinu N02B! Obsahuje i podskupinu N02BF (gabapentinoidy - LYRICA,
PREGABALIN, GABAPENTIN), coz jsou Rx leky na neuropatickou bolest, ne nic pro laika.
Proto whitelist uvadi az uroven N02BE (anilidy = paracetamol) a N02BA (salicylaty).
Puvodni create_sample_data.py ma v INTERESTING_ATC_PREFIXES jen "N02" - opravit.

## Seed seznam znamych znacek (overeno, kody plati)

Aby v demu byly znacky, ktere laik pozna, nespolehat jen na nahodny vyber.
Tyhle kody jsou overene stazenim z API (11.8.2026) - dat je do skriptu natvrdo
jako seed a nahodnym vyberem podle ATC uz jen doplnit do 50.

| kodSukl | nazev                    | ATC     | vydej | pozn                     |
|---------|--------------------------|---------|-------|--------------------------|
| 0025364 | HELICID                  | A02BC01 | F     | OTC varianta - "ten zakladni IPP" |
| 0237394 | HELICID                  | A02BC01 | R     | Rx varianta stejne znacky |
| 0237391 | HELICID                  | A02BC01 | R     | Rx varianta stejne znacky |
| 0226664 | PANADOL NOVUM            | N02BE01 | F     | paracetamol              |
| 0226669 | PANADOL NOVUM            | N02BE01 | F     | paracetamol              |
| 0258169 | PARALEN GRIP horky napoj | N02BE51 | F     | kombinace                |
| 0087680 | ANOPYRIN                 | N02BA01 | F     | kyselina acetylsalicylova|
| 0237336 | NUROFEN                  | M01AE01 | V     | ibuprofen                |
| 0241112 | NUROFEN PRO DETI         | M01AE01 | F     | detska varianta          |
| 0239752 | NUROFEN JUNIOR POMERANC  | M01AE01 | V     | detska varianta          |
| 0173218 | VOLTAREN EMULGEL         | M02AA15 | V     | gel na bolest            |
| 0246012 | VOLTAREN FORTE           | M02AA15 | V     | gel na bolest            |
| 0058119 | RENNIE                   | A02AD01 | V     | antacidum na palenie zahy|
| 0047924 | RENNIE SPEARMINT BEZ CUKRU | A02AD01 | V   | antacidum                |
| 0221185 | ZYRTEC                   | R06AE07 | F     | alergie                  |
| 0201927 | ANALERGIN NEO            | R06AE09 | R     | alergie, Rx varianta     |
| 0246174 | ACC NEO                  | R05CB01 | F     | kasel                    |
| 0239484 | AUGMENTIN 1 G            | J01CR02 | R     | antibiotikum (Rx)        |

HELICID je pro demo obzvlast dobry: stejna znacka ma OTC (F) i Rx (R) varianty,
takze se na nem da ukazat, ze filtr na_predpis opravdu funguje.

PARALEN (0254048) uz je pouzivany v legacy demech - pridat taky.
OLYNTH se v dosud stazenem vzorku neobjevil (R01A je v registru vzacne,
cca 0,15 %) - dohledat pri velkem scanu, viz nize.

Poznamka k vydeji "V" = vyhrazena leciva, prodavaji se i mimo lekarnu
(Rennie, Voltaren, Nurofen). Do na_predpis patri jako FALSE.

## !!! DOPLNENO 13.8.2026 - DVA POVINNE PARAMETRY !!!
##
## Vyhledavaci API funguje a je to spravna cesta pro discovery,
## ALE musi se poslat dva parametry, jinak vraci jen ZRUSENE registrace:
##
##     "stavZruseni":   "N"   = jen platne registrace
##     "ochrannyPrvek": "X"   = NEROZHODUJE (ne "nesmi mit OP"!)
##
## Vynechani parametru NENI totez jako "nefiltrovat" - neutralni hodnotu
## je nutne poslat explicitne. Prazdny retezec "" nevrati nic.
## Podrobnosti a namerene hodnoty: poznatky.md, zapis 2026-08-13.
## Implementovano jako vychozi v SuklClient.hledej().

## Jak vybrat - vyhledavaci API

Verejne dokumentovane API (/dlp/v1, popsane v dlp.api.json) vyhledavat NEUMI -
seznam vraci jen pole 69 355 kodu a ATC je az v detailu.

ALE: webova aplikace https://prehledy.sukl.gov.cz/prehled_leciv.html pouziva
jine, nedokumentovane API, ktere vyhledavani umi. Nalezeno rozbalenim jejiho
JS bundlu (js/prehled_leciv.min.js) a overeno volanim (11.8.2026):

    POST https://prehledy.sukl.gov.cz/prehledy/v1/dlp
    Content-Type: application/json
    body: {"filtr": "PARALEN", "atc": "N02BE", "pocet": 50, "stranka": 1,
           "stavZruseni": "N", "ochrannyPrvek": "X",
           "sort": ["nazev","je_dodavka"], "smer": "asc"}

    Posledni dva radky jsou POVINNE - bez nich prijdou jen zrusene registrace.
    Kdyz se API zachova necekane: GUI umi zkopirovat nastaveni filtru do
    schranky jako URL, kde jsou videt vsechny parametry, ktere posila
    oficialni klient. Rychlejsi nez rozbalovat JS bundle.

Vsechny parametry jsou volitelne. Prazdne telo {} vrati celkem 137 483 zaznamu
(vic nez dlpo seznam - obsahuje zjevne i neplatne/zrusene registrace).

### Co umi
- filtr  = hledani podle nazvu, PREFIXOVE a case-insensitive.
           "PARAL" najde PARALEN (98 vysledku), ale "ARALEN" nenajde nic.
- atc    = filtr podle ATC, funguje i na PREFIX: "N02BE" -> 1107, "N02BE01" -> 653
- pocet / stranka = strankovani
- dalsi parametry videt v URL webove aplikace (zpusobVydeje, cestaPodani,
  stavRegistrace, leciveLatky, uhrada, jeDodavka...)

### Vraci bohatsi data nez dokumentovane API
Klice zaznamu: kodSUKL, nazevLP, doplnekNazvu, ATCskupina, ATCnazev, velikostBaleni,
baleni, zpusobVydeje, uhrada, stavRegistrace, dostupnost, registracniCislo,
datumRegistrace, rokZavedeni, dokumenty, jeDodavka, dovoz, ochrannyPrvek

Ciselnikove hodnoty jsou uz ROZLOZENE, ne jen kody. Napr. zpusobVydeje vraci:
    {"kod":"F", "nazev":{"cs":"volne prodejne lecive pripravky"},
     "kodDlw":"OTC", "nazevDlw":{"cs":"bez lekarskeho predpisu (OTC)"}}
Pole kodDlw uz obsahuje hotovou klasifikaci OTC/Rx - neni nutne mapovat
osm kodu rucne (ale whitelist z predchozi sekce si necháme jako kontrolu).

### DOPORUCENY POSTUP (nahrazuje hromadne stahovani)
1. DISCOVERY pres vyhledavaci API: POST /prehledy/v1/dlp s parametrem atc
   pro kazdou skupinu z whitelistu -> dostanu presne ty kodySUKL, ktere chci.
   Zadny scan tisicu kodu, zadne nahodne vzorkovani.
2. DETAIL pres dokumentovane API: GET /dlp/v1/lecive-pripravky/{kodSukl}
   - je to stabilni verejny kontrakt s OpenAPI specifikaci.
3. PDF pres GET /dlp/v1/dokumenty/{kodSukl}/spc (skript uz je v legacy).

Duvod delby: vyhledavaci API je interni vec webu, muze se kdykoli zmenit bez
ohlaseni. Pouzit ho na discovery je v poradku (kdyz se rozbije, prepise se
jeden krok), ale stavet na nem celou aplikaci by bylo krehke.

### Overene nalezy
- OLYNTH v registru JE, 13 zaznamu: OLYNTH HA 0,05%, OLYNTH HA 0,1%, OLYNTH PLUS
  (kody 0242207 R01AA07 F, 0239776 R01AA07 F, 0235783 R01AB06 F)
- DITHIADEN v registru NENI. Overeno tremi zpusoby: filtr "DITHIADEN",
  prefix "DITHIA" i "BISULEPIN" vraci 0 zaznamu, a to i v tom sirsim seznamu
  se 137 tisici polozkami. Zjevne uz zrusena registrace - do dema ho nelze vzit.
  (Latka bisulepin v ciselniku latek existuje, ale zadny registrovany pripravek.)

(Puvodni doporuceni "projit nahodny vzorek 2000-3000 kodu a filtrovat lokalne"
uz neplati - bylo napsane driv, nez se naslo vyhledavaci API. Nahodne vzorkovani
uz neni potreba, ATC filtr vraci presne to, co chceme.)

# Vstupni data - realcni cast
Vznikne jedna tabulka leciva s ID

## PREHLED VSECH POUZIVANYCH ENDPOINTU

Jsou to DVE ruzna API na stejnem serveru:

A) /dlp/v1  = verejne dokumentovane (OpenAPI spec na /dlp.api.json), STABILNI
   - GET /dlp/v1/lecive-pripravky?typSeznamu=dlpo   seznam kodu (jen kody, 69 355)
   - GET /dlp/v1/lecive-pripravky?typSeznamu=scau   seznam hrazenych
   - GET /dlp/v1/lecive-pripravky/{kodSukl}         detail leciva
   - GET /dlp/v1/ciselniky/{nazev}                  ciselniky (zpusoby-vydeje, atc-skupiny...)
   - GET /dlp/v1/ciselnik-latky                     ciselnik lecivych latek
   - GET /dlp/v1/dokumenty/{kodSukl}/spc            PDF dokumentu SPC
   - GET /dlp/v1/slozeni/{kodSukl}                  slozeni pripravku
   Vyhledavani NEUMI (zadny filtr podle nazvu ani ATC).

B) /prehledy/v1 = NEDOKUMENTOVANE, pouziva ho webova aplikace prehled_leciv.html
   - POST /prehledy/v1/dlp   VYHLEDAVANI (filtr podle nazvu, atc, strankovani)
     body napr.: {"filtr":"PARALEN","atc":"N02BE","pocet":50,"stranka":1}
   - dalsi: POST /prehledy/v1/atc, /lecivelatky, /drzitele, GET /ciselniky/{n}
   Detaily a chovani viz sekce "Jak vybrat - NASLO SE VYHLEDAVACI API" vyse.
   POZOR: neni to verejny kontrakt, muze se zmenit. Pouzivat jen na discovery.

## Relacni cast - vlastni tabulka leciva
Vstupni relacni data o lecivu se stahnou z API - kodSUKL, nazev, doplnek, sila, forma, cesta, baleni,  ATC skupina, zpusob vydeje, ucinne latky(pole) . Nove jsou uvedena i dalsi atributy do relacni casti.
Kody suklu  v davce jsou zde
https://prehledy.sukl.gov.cz/dlp/v1/lecive-pripravky?typSeznamu=dlpo
Na teto opraci je vetisna atributu podle kodu suklu
https://prehledy.sukl.gov.cz/docs/?url=/dlp.api.json#/dlp/api_dlp.vrat_lp


### Ciselnikove hodnoty
Ciselnikove hodnoty prosim preved na text
https://prehledy.sukl.gov.cz/docs/?url=/dlp.api.json#/ciselniky/api_dlp.vrat_ciselnik
Pro uciine latky / lecive latky
https://prehledy.sukl.gov.cz/docs/?url=/dlp.api.json#/ciselniky/api_dlp.vrat_cis_lecive_latky

## Je lek hrazeny
Pridal bych atribut hrazeny true/false. Pokud je lek v tomto seznamu, resp. kodSUKL, tak je hrazeny.
https://prehledy.sukl.gov.cz/dlp/v1/lecive-pripravky?typSeznamu=scau

## Je lek na predpis nebo OTC
vychazi z vyse uvedeneho atributu zpusob vydeje, v API jako zpusobVydejeKod.

OVERENO stazenim ciselniku (11.8.2026):
GET https://prehledy.sukl.gov.cz/dlp/v1/ciselniky/zpusoby-vydeje
Neni to 3+3, ale 4+4 hodnoty:

| kod       | nazev                                              | na_predpis |
|-----------|----------------------------------------------------|------------|
| R         | na lekarsky predpis                                | TRUE       |
| L         | na lekarsky predpis s omezenim (§39/4/a ZoL)       | TRUE       |
| C         | na lekarsky predpis s omezenim (§39/4/c ZoL)       | TRUE       |
| NEUVEDENO | na lekarsky predpis s MODRYM PRUHEM                | TRUE       |
| F         | volne prodejne lecive pripravky                    | FALSE      |
| O         | bez lekarskeho predpisu s omezenim                 | FALSE      |
| P         | bez lekarskeho predpisu s omezenim (RLPO)          | FALSE      |
| V         | vyhrazena leciva                                   | FALSE      |

POZOR NA "NEUVEDENO": kod vypada jako chybejici/neznama hodnota, ale ve skutecnosti
znamena "vydej na lekarsky predpis s modrym pruhem", tedy omamne a psychotropni latky.
Kdyby to spadlo do vetve "neznamo -> beru jako volne prodejne", oznacili bychom
opiaty jako volne prodejne. Musi byt explicitne v Rx skupine.

Doporuceni: mapovat pres explicitni whitelist obou skupin a kazdy kod, ktery
nesedi ani na jeden seznam, ulozit jako na_predpis = NULL (ne FALSE) a vypsat
do logu - at je videt, ze se objevil novy kod, misto tiche chyby.

Kontrolni priklad: PARALEN (0254048) ma zpusobVydejeKod = "F" -> volne prodejny.

# Vstupni data - nerelacni cast
Vznikne jedna tabulka extrakty. Pracujeme primarne s jsonb sloupeckama.
Soubory se stahuji ze stejneho API. Musi sedet lek z tabulky leciva na lek z tabulky extrkaty - musi mit stejne ID. Pro stazeni PDF k SPC se da pouzit stejny skript z adresare legaci. Skript umi stahovat PDF.
Konverze a extrakce bude mit pipeline.
## EU registrace
PDF u EU registraci je jeden dokument pro vsechno. U CZ registraci je jeden dokument SPC a jeden PIL. U EU je to spojene do jednoho a PIL zacina nadpisem pres celou stranku Priloha II. Na teto strance bych udelal orez a vyhodil zbytek vcetne teto stranky.
Pred fixnim nastavenim orezu do kodu si udelat test jednoho SPC CZ leku a EU registrace, ze dostatavem vsechny potrebne kapitoly. Porovnat CZ extakt s EU extraktem , ze mam vsechny kapitily vytazene.
EU prilohu pro prozkoumani lze najit naprikald u tohoto leku
https://www.ema.europa.eu/cs/documents/product-information/tuzulby-epar-product-information_cs.pdf
## Sekce extrakce
z PDF se budu snazit extrahovat sekce a finalne kovertovat do pole indikace, kontraindikace, nezadouci ucinky, davkovani.
## Metadata a 1:N model
Pridal bych k danemu ID leciva i klidne i moznost vic radku a filtroval. Protoze muzu treba udelat extrakci pomoci nejakeho modelu a pak pomoci openapi cloud.
Cele to lze udelat asi jako jsonb sloupec metadata - model, konverze, cas extrakce, cas prevedeni na pole.
## !!! NEJDRIV PILOT NA 2-3 LECIVECH !!!

Kroky 1-3 (Docling -> regex -> JSONB) NEPOUSTET rovnou na vsechna leciva.
Nejdriv je projet na 2-3 lecivech a rucne zkontrolovat vysledek.

Duvod: konverze Doclingem a dodrzeni JSON schematu lokalnim modelem jsou
jedine dve veci v celem zadani, ktere zatim NIKDO NEVIDEL FUNGOVAT.
Vsechno ostatni (API, modely, DDL, dimenze vektoru) je overene.
Kdyby Docling rozsypal tabulku nezadoucich ucinku nebo model nedodrzel schema,
meni to navrh - a je lepsi to zjistit na trech lecivech nez po nocnim behu
nad petiset.

Vzorek na pilot: 1 CZ registrace (napr. PARALEN 0254048), 1 EU registrace
(kvuli orezu na Priloha II) a 1 lek s bohatou tabulkou nezadoucich ucinku.

### Co zkontrolovat po Doclingu (krok 1)
- [ ] Nadpisy jsou opravdu markdown nadpisy (## 4.8 Nezadouci ucinky),
      ne jen radek textu
- [ ] MedDRA tabulka nezadoucich ucinku zustala TABULKOU (| oddelovace),
      neni zplostena do proudu textu
- [ ] U EU registrace orez na "Priloha II" sedi a nic potrebneho neuriznul
- [ ] Porovnat CZ vs EU extrakt: ma EU vsechny stejne kapitoly jako CZ?
- [ ] Cisla stranek jsou k dispozici (potreba pro odkaz do PDF)

### Co zkontrolovat po extrakci do JSONB (krok 3)
- [ ] Model vratil validni JSON
- [ ] Sedi klice podle schematu (ucinek+frekvence, pacient+davka, ...)
- [ ] Nezadouci ucinky jsou rozlozene na JEDNOTLIVE POLOZKY,
      ne jeden blok textu v jedne polozce
- [ ] Pocet polozek dava smysl (u nezadoucich ucinku desitky, ne 2)
- [ ] Hodnoty frekvence jdou namapovat na ciselnik (caste/vzacne/...)
- [ ] Zadna polozka nema obsah_text delsi nez ~400 znaku

### Zaroven zmerit cas
Pilot je i test rychlosti, podle ktereho se rozhodne finalni pocet leciv
(50 vs 500, viz sekce "Vstupni data - rozsah"). Zmerit zvlast:
konverze Doclingem, extrakce lokalnim modelem, embedding.
Extrakce lokalnim modelem bude nejpomalejsi - podle ni se to pocita.

Teprve kdyz tenhle pilot projde, pustit pipeline na cely vzorek.

## Krok 1 -  Konverze do Mardown
Pouzil bych Docling pro konverzci dokumentu do Markdown a oznacil napdpisy.
U EU registraci bych vyhodil orezeme druhou cast dokumentu, to dela podle me bordel. Je tam spousta stranek navic, protoze to jsou spojene dva dokumenty do jednoho.
## Krok 2 -  Extrakce pasazi
Pouzit regex na extrahovani sekci. Lze upravit puvodni kod v adresari legacy, PDF tools
## Krok 3 - Prevedeni do JSONB
Pouzit LLM pro konverzi sekci do polí nebo objektu polí. Lze pouzit puvodni kod z legacy adresare.
Pouzij katergorizace z puvodni prevodu do sekci objektu v legacy adresari. Ujisti se ze nezadouci ucinky jsou rozdelene podle frekvence a frekvenci pouzivej take jako filtr.
{"ucinek": "bolest břicha", "frekvence": "časté", "organovy_system": "Gastrointestinální poruchy"}

## Krok 4 -  Review konverze (NENI volitelne - viz tabulka stavu nize)
Overit jinym modelem, ze extrahovana data opravdu jsou dane sekce a ze maji stejne hodnoty, napr. paralelni konverze a porovnani vysledku nebo review vysledku formou porovnani s vstupnim textem?

### AKTUALIZOVANO 18.8.2026 - delba modelu odpadla

Puvodne: extrakce na mensim modelu (32b), kontrola na vetsim (72b).
Zmereno, ze to nedava smysl - qwen3.5:122b (MoE, 8 z 256 expertu aktivnich)
je zaroven NEJLEPSI i NEJRYCHLEJSI: ~29 tok/s proti 10,5 u 32b a 4,5 u 72b.
Vsechno generativni bezi na nem, viz poznatky.md 18.8.2026.

Princip "kontrola JINYM modelem" ale plati dal - model si neodsouhlasi
vlastni chybu. Protoze uz neni kam jit nahoru, kontrola se deli na dve casti:

1. DETERMINISTICKA kontrola bez modelu (dela se vzdy, je zadarmo):
   - je hodnota `ucinek` doslova ve zdrojovem textu sekce?
   - je `organovy_system` ve zdrojovem textu?
   - sedi `frekvence` na tu, pod kterou je ucinek ve zdroji uvedeny?
   Chyta prave ten typ chyby, ktery je u zdravotnickych dat nejnebezpecnejsi.

2. MODELOVA kontrola jen na to, co bodem 1 neprojde. Jako nezavisly model
   pouzit `gpt-5-nano` (POZOR NA ROZPOCET - je to reasoning model, ~5000
   tokenu na dotaz) nebo `gemma4:31b`, u ktereho je ale potreba pocitat
   s falesnymi poplachy, protoze je slabsi.

## Krok 5 - Slovnik pojmu (laicky tvar odbornych terminu)

### Proc to nejde udelat pri extrakci

Overeno 18.8.2026: model pri extrakci OPISUJE termin ze zdroje, i kdyz se
mu v promptu rekne "bez odbornych terminu". "Neuralgie" zustala v indikacich
u qwen2.5:32b, u qwen2.5:72b, u qwen3.5:122b I u gpt-4o. Neni to otazka
velikosti modelu - je to otazka toho, ze zjednoduseni musi byt SAMOSTATNA
uloha, ne vedlejsi pozadavek v extrakcnim promptu.

### Slovnik je DATOVA TABULKA, ne prompt

NEpodklada se modelu s instrukci "rid se timhle". Postup:

1. Posbirat unikatni terminy pres cely korpus z `data/leciva/*/json/*.json`
   (hodnoty `ucinek`, polozky `indikace` a `kontraindikace`).
   Termin, ktery je u peti leku, jde do slovniku JEDNOU.
2. Model prelozi jen ten seznam, jednorazove -> `slovnik.json`
3. Pri plneni DB se `ucinek_laicky` DOHLEDA ve slovniku. Model u toho neni.

Tri duvody, proc takhle a ne pres prompt:
- DETERMINISTICKE: termin ma jeden tvar napric celou aplikaci. U zdravotnickych
  udaju je to pozadavek, ne pohodli.
- AUDITOVATELNE: jeden soubor o par stech radcich se da precist a rucne
  opravit. Totez rozhazene v tisicich polozek zkontrolovat nejde.
- ZADARMO ZA BEHU: laicky tvar zmizi z vystupu extrakce, takze se generuje
  vyrazne min tokenu.

Prirustkove: u novych leciv se prelozi jen terminy, ktere ve slovniku jeste
nejsou.

### Znama slabina - preklad BEZ KONTEXTU je horsi

Zmereno na 10 terminech. Tentyz model, ktery v kontextu SPC prelozil
"trombocytopenie" spravne, nad HOLYM SEZNAMEM terminu plodi nesmysly:

| termin | qwen2.5:32b | qwen2.5:72b | qwen3.5:122b | gpt-5-nano |
|---|---|---|---|---|
| trombocytopenie | "mene cervene krvinky" | "nachylnost k krvaceni" | nizky pocet krevnich destick OK | malo krevnich destick OK |
| cytolyticka hepatitida | "narust plicniho jatra" | "pochod zaludku" | poskozeni jaternich bunek OK | poskozeni jater OK |
| pyroza | "zaludecni palivost" | "horcka" | paleni zahy OK | paleni zahy OK |

Slovnik proto stavet na `qwen3.5:122b` (mel vsech 10 spravne) a VZDY ho
rucne projit. Je to zdravotnicky udaj pro laiky, ne kosmetika.

### KDY to delat - UZ HOTOVO, ale jen jedna z roli

AKTUALIZOVANO 19.8.2026: slovnik UZ EXISTUJE (`slovnik_pojmu.json`,
419 dvojic). Puvodni oduvodneni "az po evaluaci" platilo jen pro jeho
roli v HLEDANI - viz sekce "Krok 5 (slovnik) UZ JE HOTOVY" na zacatku
dokumentu.

Co je porad OTEVRENE: jestli ma laicky tvar jit do EMBEDDINGU. To se
rozhodne az z mereni - "bez slovniku najde laicky dotaz spravny lek
v X pripadech z 20, se slovnikem v Y" (test 2 v EVALUACI). Naklad odkladu
je maly: znamena to doplnit sloupec a prepocitat embeddingy u ~600 ucinku.

# TABULKA 4 - stav extrakce (explicitni evidence, co se povedlo a co ne)

> **Uplny popis stavu vcetne prechodu je v `stavy.md`.** Tady zustava
> jen DDL a zduvodneni, proc to nejde resit NULLem.

## Proc to nestaci resit NULLem

NULL v datech znamena dve uplne ruzne veci a nejde je rozlisit:
  a) lek OPRAVDU nema uvedene nezadouci ucinky (nektera SPC sekci nemaji)
  b) extrakce SELHALA a data chybi

Pro aplikaci pro laiky je ten rozdil zasadni. Nikdy nesmi vzniknout dojem
"tenhle lek nema zadne nezadouci ucinky", kdyz jsme je jen nedokazali
vytahnout. To je horsi nez priznat mezeru.

Zaroven vyhledavac potrebuje vedet, ze v dane sekci daneho leku nema co
hledat - aby nehlasil "nenasli jsme nic" tam, kde ve skutecnosti nic nemame.

## DDL

CREATE TABLE extrakce_stav (
    id              BIGSERIAL PRIMARY KEY,
    kod_sukl        TEXT NOT NULL REFERENCES leciva(kod_sukl) ON DELETE CASCADE,
    extrakt_id      BIGINT REFERENCES extrakty(id) ON DELETE CASCADE,
    sekce           TEXT NOT NULL,     -- indikace|kontraindikace|nezadouci_ucinky|davkovani

    stav            TEXT NOT NULL,
        -- 'ok'                 vytazeno a overeno, da se hledat
        -- 'neovereno'          vytazeno, kontrola jeste nebezela
        -- 'chybi_v_dokumentu'  sekce v SPC NENI (legitimni stav, ne chyba)
        -- 'selhala_extrakce'   model nevratil validni JSON / nedodrzel schema
        -- 'zamitnuto_kontrolou' kontrolni model data odmitl
        -- 'prazdna'            sekce v dokumentu je, ale nema zadne polozky

    pocet_polozek   INTEGER,           -- kolik polozek se vytahlo
    format_sekce    TEXT,              -- A/B/C/D/E dle analyza_formatu.py
    zdroj_textu     TEXT,              -- 'docling_md' | 'pymupdf_raw'
    model_extrakce  TEXT,              -- qwen2.5:32b / gpt-5.4-nano / ...
    model_kontroly  TEXT,              -- qwen2.5:72b / NULL
    duvod           TEXT,              -- proc to selhalo, slovy - pro ladeni
    cas_extrakce_s  NUMERIC,
    vytvoreno       TIMESTAMPTZ DEFAULT now(),
    UNIQUE(kod_sukl, sekce, extrakt_id)
);

CREATE INDEX ON extrakce_stav (kod_sukl);
CREATE INDEX ON extrakce_stav (stav);
CREATE INDEX ON extrakce_stav (format_sekce);

## K cemu to slouzi - tri veci najednou

1. VYHLEDAVANI: pred hledanim v sekci se zkontroluje stav. Kdyz neni 'ok',
   uzivateli se to rekne narovinu:
     "U leku X nemame zpracovane nezadouci ucinky (extrakce selhala)."
   misto tichého "nenalezeno".

2. EVALUACE: Test 0 (pokryti extrakce) tuhle tabulku primo cte -
   neni potreba pocitat pokryti dodatecne SQL dotazy nad leciva_search.

3. OPTIMALIZACE PROCESU: sloupce format_sekce + zdroj_textu + model_extrakce
   dohromady rikaji, KTERA kombinace selhava. Napr. "formát C + docling_md
   ma 40 % selhani, formát C + pymupdf_raw 5 %" je primy podklad pro to,
   co zmenit. Bez teto evidence by se ladilo poslepu.

## Pravidlo pro zobrazeni uzivateli

    stav = 'ok'                 -> normalne zobrazit
    stav = 'chybi_v_dokumentu'  -> "SPC tuto sekci neobsahuje"
    cokoli jineho               -> "sekci se nepodarilo zpracovat"

NIKDY nezobrazovat prazdny seznam jako by to znamenalo "zadne nezadouci
ucinky nejsou".

# Mezistavy jako souvbory
Klidne davat do adresare leciva pro kazde lecivo vlastni podadresar podle kodu suklu.
Tohle mi prijde zbytecne cpat do databaze
1. JSON z API
2. Extrahovany markdown
3. Extrahovane sekce jako markdown

## Alternativa pomoci cloudu
Pokud konverze nepujdou dobre, tak pouzit openai platform nano model. Skript je v legacy adresari.

# Vstupni data vektory
Porad mi prijde nejlepsi treti tabulku, abych treba ohledne velikosti dimienzi nemusel menit vsehcna data. Odkaz na ID leciva a ID z druhe tabulky (ID extrakt), protoze tam muze mit jedno lecivo vice radku.
Sloupec typu  Vector, ktery bude obsahovat vektorovane value jedne sekce jednoho leku - pouze sloupec obsah_text.
Sloupec typu TSV, ktery bude obsahovat relevatni jednoslovne sloupce, typu nazev, sila. Bude regovat treba jen na Paralen nebo Paralen 500mg. 

# Hyrid search
Bude hledat pomoci RRF. Ale o 500% je dulezitejsi aby to naslo nejake semanticke veci. Ten fulltext je jen doplnek.
# Priklady hledani
Najdi mi nejake volne prodejne leky na bolest
Volne prodejny lek na bolest se silou 500mg
Paralen 500mg - zabere ciste TSV
Bolest bricha nezadouci ucinek
# Vystupy hledani
Bude vracet seznam radku z obou tabulek s obsahem.
Kod SUKL, nazev, doplnek, indikace, nezadouci ucinky, kontraindikace ,davkovani
Tady to bude asi masa veci ty pole na vraceni do radku...?
Zobraz je relevatni z objektu dane sekce.
Zobraz odkaz na dokument aby byl rozklikavaci a dopad do dane sekce.
Je potreba si tedy ukladat i cisla stranek z pdf. Soucasti kazdeho vyhledane radku v reportu bude odkaz do pdf na konrketni stranku.
Fáze 1 (CMD): vypsat cestu k souboru + název sekce, tedy něco jako data/leciva/0254048/spc.md § 4.8 Nežádoucí účinky. Klikat se v terminálu nedá, ale je to dohledatelné a hlavně to slouží jako doklad původu.
Fáze 2 (GUI): u PDF funguje kotva #page=7 (prohlížeč skočí na stránku), u markdownu je to ještě jednodušší — vyrenderuješ jen tu sekci.

# Routovani, filtrace a prioritizace hledeni
Pokud jasne neni zaqdefinovana sekce jako treb po prasicich co jsem si vzal me boli bricho , tak je samotna bolest bricha vzdy indikace
Routovani - mensi model rozhodne z jake sekce jsou informace, pripadne kombinace vice skeci. Kdyz napisu volne dostupne leky na bolest zubu. Tak by mel zjistit ze ma hledat podle filtru Rx/OTC a pak v sekci idndikace. To znamena nejdriv pripravit select , ktery omezi leky a omezi sekci  pak se bude hledat ve vyslednych vektorech?
Pokud v zadani hledani neni nic o filtru, tak filtr nepozuivat.
Pokud si reuter neni jisty, tak hledat ve vsech sekcich a zobrazit u kazdeho vysledku z jake sekce pochazi.

# Co delat kdyz to nenajde nic relevantiho
Pokud fitr vrati nula vysledku je potreba to natvrdo internprovat uzivateli, vcetne zobrazeni pouziteho filtru - uzivatesky
Pokud semantika najde jen vyrazi s malou similarity, tak asi nezobrazovat. Udelat si testem nejake prahove hodnoty a pod 0.4 napriklad nezobraovat vubec.  Udelat si test a postupne menit tuto prahovdou hodnotu, dle relevatnosti vystupu z testu.
Prahova hodnota je odvozena z modelu qwen3-embedding. Je mozne ze pro bge-m3 to bude treba 0.7. Udelat testy na prah pro jiny model.

# seskupeni odpovedi
Tabulka leciva_search má jeden řádek na položku, takže Paralen má vlastní řádek pro každou indikaci a každý nežádoucí účinek. Když se zeptame „volně prodejné léky na bolest" a vezmeme top-10 řádků odpovedi, může se snadno stát, že to bude osm řádků Paralenu a dva Panadolu — místo deseti různých léků.

Uživatel přitom čeká seznam léků, ne seznam pasáží. Řešení je vyhledat s rezervou (třeba top-50 řádků), pak seskupit podle kod_sukl a vrátit N různých léků — u každého ta nejlépe skórující pasáž jako důkaz, proč se trefil. Jinak řečeno, deduplikace není jen věc zobrazení, ale musí ovlivnit i to, kolik řádků se z databáze tahá.


Vystup routeru priklad
{
  "sekce": ["indikace"],
  "dotaz_text": "bolest",
  "na_predpis": false,
  "sila": "500MG",
  "atc": null,
  "ucinna_latka": null,
  "hrazene": null,
  "nazev": null,
  "kodSUKL": null,
  "organovy_system": null,
  "frekvence_max_rank": null
}

Poslední dva jsou filtry k nežádoucím účinkům:
  organovy_system     "Srdeční poruchy" – když se uživatel ptá na orgán/oblast
                      ("dělá to něco se srdcem?", "žaludeční potíže")
  frekvence_max_rank  2 = jen běžné NÚ (velmi časté + časté)

Poznamka: "dotaz_text" je JEN zbytek pro semantiku, ne cela veta.
Vsechny filtry, ktere v dotazu nebyly, musi byt null - ne vymyslena hodnota.
Klíčové je, aby uměl vrátit null u filtru, který v dotazu nebyl ,a aby dotaz_text byl jen ten zbytek pro sémantiku, ne celá původní věta.
Kod SUKL bych pridal do fulltext vyhledavani, nemam nidke jinde specificky vypsane.

# Pouzite modely a promty
pro extrakce local - qwen2.5:72b pro extrakci a prevedeni pasazi, 
Pokud to bude trvat dlouho tak jen 32b
alternativa pro extrakce cloud openai, kdyby to neslo dobre, zaloha - gpt-5.6-luna
embed - bge-m3
overovaci model  - treba gemma4:31b
Promty -  legaci adresari jsou podle me dobre udelany prompty pro prevedeni sekce na pole. V cloudu to fungovalo vyborne. Hodne se da pouzit asi pdf tools prace s regexem, akorat misto toho se pracuje s markdown.
Routovani - qwen2.5 - 14b nebo lepe 32b?

## Stav dostupnosti modelu (overeno 11.8.2026)

CLOUD OpenAI (overeno pres /v1/models s klicem z legacy/key.yaml):
- gpt-5.6-luna   ANO, existuje
- gpt-5.4-nano   ANO, existuje - tento pouziva legacy demo03d/demo04 a fungoval dobre,
                 takze cloudova zaloha jde pouzit beze zmeny kodu
- cela rada gpt-5.6 ma varianty: luna, sol, terra

OLLAMA na DGX Spark - v dobe psani zadani bylo stazeno:
  qwen3:32b, gemma3:27b, qwen3-embedding:8b, qwen2.5:72b, qwen3.5:122b, llama3:latest
Chybelo (uzivatel dostahuje): bge-m3, qwen2.5:32b, gemma4:31b, router model
POZOR: Qwen2.5 se nevyrabi ve velikosti 17B (existuji 7/14/32/72B) - pro router
zvolit realnou velikost.

## DOPAD NA DIMENZI VEKTORU
vector(1024) v DDL predpoklada bge-m3 (nativne 1024 dim).
Kdyby bge-m3 nakonec nebyl, jsou varianty:
 a) qwen3-embedding:8b v plnych 4096 dim -> lepsi kvalita (MTEB 70,58 vs 63,0),
    ale nad limitem 2000 pro HNSW index -> sekvencni sken.
    Pri objemu stovky az tisice radku je to naprosto v poradku.
 b) qwen3-embedding:8b orezany na 1024 -> NEDELAT. Overeno vcera na document_chunks:
    orez otocil poradi relevance naruby (viz legacy/demo01_pdf_to_vectors.md).
Pri zmene modelu je nutne zmenit i vector(N) v DDL a preindexovat.
# DDL
Pouzil bych skripy z puvodniho proejktu a jen upravil

# Infrastruktura - docker compose a init-db

Vzit soubory z legacy adresare a upravit:
    legacy/docker-compose.yml
    legacy/init-db.sql
    legacy/pgadmin-servers.json
    legacy/pgpass          (je v .gitignore, musi se vytvorit rucne)

ALE POUZIT NOVE NAZVY, nesmi se to prekryvat se starym projektem.
Napriklad "localsemantic" (nebo cokoli jineho, hlavne ne "ailocal"):

    container_name:  localsemantic-postgres, localsemantic-pgadmin
    volumes:         localsemantic_pgdata, localsemantic_pgadmin_data
    databaze/user:   localsemantic

Duvod - na stroji zustaly po starem projektu volumes ailocal_pgdata,
ailocal_pgadmin_data, legacy_pgdata, legacy_pgadmin_data a kontejner
ailocal-pgadmin. Kdyby novy projekt pouzil stejna jmena:
 - kontejner se nespusti kvuli konfliktu jmena
 - a hlavne: Docker recykluje EXISTUJICI volume se STAROU databazi.
   init-db.sql se na neprazdnem volume NESPOUSTI, takze by se nove tabulky
   vubec nevytvorily a vypadalo by to jako chyba ve skriptu.

Pri prvnim spusteni (a po kazde zmene DDL) proto:
    docker compose down -v && docker compose up -d
Prepinac -v smaze i volume, jinak se schema neaktualizuje.

## Co v init-db.sql upravit oproti legacy
- nove tabulky (leciva, extrakty, leciva_search) misto document_chunks/extrakty_json/simplify
- vector(1024) pro bge-m3
- konfigurace czech_unaccent zustava beze zmeny, ta funguje
- pgvector extension zustava

# Poznamka k adresari
Root adresar je prazdny az na legacy/, .git, CLAUDE.md a zadani soubory.
Vsechny puvodni soubory jsou v legacy/ i v git historii.
Novy projekt si tedy infrastrukturni soubory musi vytvorit (viz sekce vyse) -
v rootu neni z ceho spustit docker compose.

# DDL pro tabulku vektory
CREATE TABLE leciva_search (
    id               BIGSERIAL PRIMARY KEY,
    kod_sukl         TEXT   NOT NULL REFERENCES leciva(kod_sukl) ON DELETE CASCADE,
    extrakt_id       BIGINT REFERENCES extrakty(id) ON DELETE CASCADE,
                     -- NULL u radku sekce='atributy' (nepochazi z PDF, ale z tabulky leciva)

    -- ---- FILTRACNI SLOUPCE (nikdy nesmi byt v hledanem textu) ----
    sekce            TEXT NOT NULL,
                     -- 'atributy'          identita leku, 1 radek na lek, zdroj = tabulka leciva
                     -- 'indikace'          }
                     -- 'kontraindikace'    }  zdroj = SPC, 1 radek na polozku
                     -- 'nezadouci_ucinky'  }
                     -- 'davkovani'         }
    frekvence        TEXT,      -- POUZE pro nezadouci_ucinky: 'caste', 'vzacne'...
    frekvence_rank   SMALLINT,  -- POUZE pro nezadouci_ucinky: 1=velmi caste ... 9=neni znamo
                                -- davkovaci frekvence ("3-4x denne") sem NEPATRI, ta je v polozka_json
    organovy_system  TEXT,      -- POUZE pro nezadouci_ucinky: MedDRA System Organ Class
                                -- "Srdecni poruchy", "Gastrointestinalni poruchy", ...
                                -- Standardizovany ciselnik (~27 trid), overeno 14.8.2026:
                                -- nazvy jsou napric dokumenty DOSLOVA shodne, takze se
                                -- da filtrovat presne, ne pres podobnost.
                                -- Smysl: uzivatel nevi, co je "tachykardie", ale umi rict
                                -- "srdce" -> router to prelozi na filtr organovy_system.
                                -- NEPATRI do obsah_text (stejna past jako sekce a frekvence -
                                -- opakuje se pres stovky radku a znehodnotilo by fulltext).
    sekce_atributy     JSONB,     -- doplnkova pole polozky z poli extrakce jedntolivch sekci pdf  (pacient, davka, latka, efekt...)
                                -- prejmenovano z "atributy", aby se to nepletlo se sekci 'atributy'

    -- ---- TEXTY ----
    kontext_text     TEXT,      -- identita leku: "PARALEN 500MG TBL NOB, paracetamol"
                                -- u radku sekce='atributy' nechat NULL (bylo by to 2x)
                                -- silu psat BEZ mezery, presne jak ji vraci API
    obsah_text       TEXT NOT NULL,
                                -- 'atributy'         -> "PARALEN 500MG TBL NOB, paracetamol, 0254048"
                                -- 'indikace'         -> "lecba bolesti hlavy, zubu a horecky"
                                -- 'nezadouci_ucinky' -> "bolest bricha"
    -- POZN: zobrazovany_text tu ZAMERNE NENI.
    -- Text pro uzivatele se sklada az pri vypisu z obsah_text + frekvence
    -- + sekce_atributy. Nema smysl ho ukladat, byla by to jen slepenina
    -- sloupcu, ktere uz v tabulce jsou.

    -- ---- HLEDACI SLOUPCE ----
    embedding        vector(1024),  -- bge-m3, do vektoru jde POUZE obsah_text
    search_fts       tsvector GENERATED ALWAYS AS (
                         setweight(to_tsvector('czech_unaccent', coalesce(kontext_text,'')), 'A') ||
                         setweight(to_tsvector('czech_unaccent', coalesce(obsah_text,'')),  'B')
                     ) STORED,

    -- ---- PROVENIENCE ----
    strana_pdf       INTEGER,   -- NULL u radku sekce='atributy'
    vytvoreno        TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX ON leciva_search USING hnsw (embedding vector_cosine_ops);
CREATE INDEX ON leciva_search USING gin  (search_fts);
CREATE INDEX ON leciva_search (kod_sukl);
CREATE INDEX ON leciva_search (sekce);
CREATE INDEX ON leciva_search USING gin  (atributy);

# Ukazaka dat pro tabulku vektory

sekce	frekvence	obsah_text	sekce_atributy	(vypis pro uzivatele - SKLADA SE, neuklada)
atributy	–	PARALEN 500MG TBL NOB, paracetamol, 0254048	NULL	PARALEN 500MG TBL NOB
indikace	–	léčba bolesti hlavy, zubů a horečky	NULL	Léčba bolesti hlavy, zubů a horečky
nezadouci_ucinky	časté	nevolnost	NULL	nevolnost (časté)
nezadouci_ucinky	vzácné	bolest břicha	{"organovy_system":"Gastrointestinální poruchy"}	bolest břicha (vzácné)
davkovani	–	dospělí 500 mg 3–4× denně	{"pacient":"dospělí","davka":"500 mg","frekvence":"3–4× denně","poznamka":"max 4 g/den"}	Dospělí: 500 mg, 3–4× denně (max. 4 g/den)

Posledni sloupec NENI v tabulce - je to ukazka toho, co se z radku slozi az pri vypisu.

# Priklad kombinace routeru , selectu a hledani v embedu
-- „Bolest břicha nežádoucí účinek"
WHERE s.sekce = 'nezadouci_ucinky'          -- router z dotazu
ORDER BY s.embedding <=> embed('bolest břicha')

-- „Volně prodejný lék na bolest se sílou 500mg"
JOIN leciva l USING (kod_sukl)
WHERE l.na_predpis = false                  -- tvrdý filtr
  AND upper(l.sila) = upper('500mg')        -- tvrdý filtr (prosté porovnání textu)
  AND s.sekce = 'indikace'                  -- router
ORDER BY s.embedding <=> embed('bolest')

-- „Paralen 500mg"
WHERE s.sekce = 'atributy'
  AND s.search_fts @@ websearch_to_tsquery('czech_unaccent','Paralen 500mg')

# Sila - maximalne zjednoduseno pro demo

ZADNE parsovani, zadny prepocet na mg, zadna normalizace mezer.
Sila se bere z API tak, jak prijde, a porovnava se jako text.

Duvod, proc to staci (overeno na 16 300 lecivech):
API uz vraci silu v jednotnem tvaru BEZ mezery a velkymi pismeny - "500MG",
"1G", "25MCG". Neni tedy co normalizovat na strane dat.

## Pravidlo pro vstup od uzivatele
Validni zapis sily v dotazu je BEZ MEZERY: "500mg" nebo "500MG".
Aplikace vstup jen prevede na velka pismena a porovna primo se sloupcem sila.

    WHERE upper(l.sila) = upper('500mg')     -- '500MG' = '500MG'

Zapis s mezerou ("500 mg") se zamerne neresi - neni to validni vstup.
(Technicky by to byl jeden radek regexu v Pythonu, ale pro demo to neni potreba.
 Na ukazce staci silu psat dohromady.)

## Co se NERESI
- prepocet mezi jednotkami (G/MG/MCG)
- rozsahove filtry ("do 500 mg")
- kombinace a koncentrace ("450MG/50MG", "10MG/ML", "0,5MG/ML+50MG/ML")
  Tyhle tvary v datech existuji, ale pro demo se s nimi nepracuje -
  filtr na silu je proste nenajde a to je v poradku.
- ~4 % leciv ma silu prazdnou (vakciny, nutricni pripravky) - taky se neresi

# Ciselnik frekvence nezadoucich ucinku

Standardni konvence EU SmPC (MedDRA/CIOMS). Overeno primo v textu PARALEN SPC,
ktery ji uvadi doslova pred tabulkou nezadoucich ucinku.

| rank | kanonicky text | vyskyt                          |
|------|----------------|---------------------------------|
| 1    | velmi časté    | >= 1/10                         |
| 2    | časté          | >= 1/100 az < 1/10              |
| 3    | méně časté     | >= 1/1 000 az < 1/100           |
| 4    | vzácné         | >= 1/10 000 az < 1/1 000        |
| 5    | velmi vzácné   | < 1/10 000                      |
| 9    | není známo     | z dostupnych udaju nelze urcit  |

## Normalizace vstupu
LLM extrakce muze vratit varianty ("Velmi caste", "velmi casté", "caste (>=1/100)").
Pred ulozenim proto: lowercase, odstranit diakritiku, sloucit vicenasobne mezery,
oriznout zavorky s cetnosti - a teprve pak mapovat na kanonicky text + rank.
Neznama/neprirazena hodnota -> rank 9, ne NULL (aby razeni fungovalo konzistentne).

Rank 9 (ne 6) je zamerne - nechava misto pro pripadne dalsi urovne a pri
ORDER BY frekvence_rank spolehlive konci "neni znamo" az na konci.

## Pouziti
- Filtr pro laika: WHERE frekvence_rank <= 2  (jen bezne nezadouci ucinky)
- Razeni vysledku: ORDER BY frekvence_rank  (nejcastejsi nahore)
- Frekvence NEPATRI do obsah_text ani kontext_text - je to nizkokardinalni hodnota
  opakujici se pres stovky radku, tedy stejna past jako nazev sekce.
  Do vypisu pro uzivatele patri ("bolest břicha (vzácné)") - ten se ale sklada
  az pri zobrazeni z obsah_text + frekvence, neuklada se.

# EVALUACE - jak poznat, ze to funguje (skript evaluate.py)

Cil: neoverovat vysledky rucne po jednom. Protoze jsou data STRUKTUROVANA,
da se vetsina pravdy odvodit primo z databaze a rucni prace zbyde na minimum.

Klicova myslenka: DOSLOVNA SHODA JE SPODNI HRANICE.
Kdyz semanticke hledani nenajde lek, ktery hledane slovo obsahuje doslova,
je to jednoznacna chyba - bez lidskeho posuzovani. Semantika smi najit VIC
(synonyma, parafraze), ale nesmi ztratit to, co je v datech napsane.

## Test 0 - Kvalita a pokryti extrakce (predpoklad vseho ostatniho)

Tohle se musi pustit JAKO PRVNI. Kdyz se u leku nepovede extrakce sekce,
ten lek proste zmizi z vysledku prislusnych dotazu a NIKDO SI TOHO NEVSIMNE -
vyhledavani bude vypadat, ze funguje, jen ten lek "neexistuje".
Vsechny nasledujici testy meri kvalitu hledani nad daty, o kterych predpokladaji,
ze jsou kompletni. Test 0 to overi.

Plne automaticke, zadna rucni prace - vse se pocita SQL dotazy nad DB.

### 0a) Pokryti sekci
Kolik leciv ma vsechny ocekavane sekce vyextrahovane.

  SELECT l.kod_sukl, l.nazev,
         count(DISTINCT s.sekce) FILTER (WHERE s.sekce <> 'atributy') AS sekci
  FROM leciva l LEFT JOIN leciva_search s USING (kod_sukl)
  GROUP BY 1,2 HAVING count(DISTINCT s.sekce) FILTER (WHERE s.sekce <> 'atributy') < 4;

Vypsat konkretne, KTEREMU leku KTERA sekce chybi - ne jen souhrnne cislo.
Cil: 100 %. Kdyz ne, je potreba vedet, jestli sekce v PDF opravdu neni
(nektere SPC nemaji interakce) nebo selhala extrakce.

### 0b) Prazdne a podezrele sekce
Sekce existuje, ale nema zadnou polozku, nebo ma podezrele malo/moc.

  - pocet polozek = 0            -> extrakce vratila prazdne pole
  - indikace > 30 polozek        -> pravdepodobne se natahla cela sekce jako jedna vec
  - nezadouci_ucinky < 3 polozky  -> u SPC skoro jiste chyba, tech byva desitky
  - obsah_text delsi nez ~400 znaku -> nerozlozilo se to na polozky,
    zustal tam blok textu (presne to, co delalo problem v legacy demech)

### 0c) Struktura JSONB
Overit, ze polozky maji povinne klice podle schematu z legacy/demo04:
  nezadouci_ucinky -> "ucinek" + "frekvence"
  davkovani       -> "pacient" + "davka"
  interakce       -> "latka" + "efekt"
Chybejici klic = LLM nedodrzel schema, coz se pri lokalnim modelu stava.

### 0d) Frekvence, ktere se nenamapovaly
  SELECT count(*) FROM leciva_search
  WHERE sekce = 'nezadouci_ucinky' AND frekvence_rank = 9;

Rank 9 znamena "neni znamo" NEBO "nepodarilo se namapovat". Kdyz je jich
hodne, rozbila se normalizace frekvence a filtr frekvence_rank <= 2
prestane davat smysl.

### 0e) Cisla stranek
  SELECT count(*) FROM leciva_search WHERE strana_pdf IS NULL;

Bez cisla stranky nefunguje odkaz do PDF, coz je jedna z veci, kterou
chceme na demu ukazovat jako doklad puvodu.

### 0f) Porovnani variant extrakce (kdyz bezi lokal i cloud)
Model 1:N (vic radku extrakty na jeden lek) tohle umoznuje zadarmo:
porovnat pocet polozek na sekci mezi lokalnim modelem a cloudem.
Vyrazny rozdil (napr. lokal 4 nezadouci ucinky, cloud 22) = lokalni extrakce
neco vypustila. Neni potreba vedet, ktera je spravne - staci ze se lisi
a stoji za pohled.

### Vystup 0
    Pokryti sekci            48/50   96 %   CHYBI: 0239484 (davkovani), 0058119 (interakce)
    Prazdne sekce             3      CHYBA: 0246012/indikace, ...
    Struktura JSONB          198/201  98 %  CHYBA: chybi klic "frekvence" ve 3 polozkach
    Frekvence nenamapovana    12/430   3 %  OK
    Chybi cislo stranky       0        OK
    Rozdil lokal vs cloud     2 leky   POHLED: 0025364 (4 vs 22 polozek)

## Test 1 - Invarianty filtru (plne automaticke, 0 rucni prace)

Neni potreba vedet, co je spravna odpoved. Staci overit, ze KAZDY vraceny
radek splnuje podminku, kterou router vytahl z dotazu:

  dotaz obsahoval "volne prodejny"  -> kazdy vysledek MUSI mit na_predpis = false
  dotaz obsahoval "500mg"           -> kazdy vysledek MUSI mit upper(sila) = '500MG'
  router urcil sekci indikace       -> kazdy vysledek MUSI mit sekce = 'indikace'
  dotaz obsahoval "hrazeny"         -> kazdy vysledek MUSI mit hrazeny = true

Ocekavana uspesnost 100 %. Jakykoli propad = unik filtru, tvrda chyba.

## Test 2 - Automaticky generovane dotazy z dat (plne automaticke)

Generator: vezmi nahodnou ulozenou polozku a udelej z ni dotaz.

  polozka:   lek OLANZAPIN, sekce nezadouci_ucinky, obsah_text "sucho v ustech"
  dotaz:     "sucho v ustech jako nezadouci ucinek"
  ocekavam:  OLANZAPIN je v top-5 vysledku

Takhle vznikne 200+ dotazu bez jedine minuty rucniho znackovani.
Netestuje synonyma, ale spolehlive odhali katastroficke chyby: spatna sekce,
zredene vektory, rozbity filtr, chybejici radky, spatne chunkovani.

Ground truth se da spocitat i SQL dotazem:
  SELECT DISTINCT kod_sukl FROM leciva_search
  WHERE sekce = 'nezadouci_ucinky' AND obsah_text ILIKE '%bolest břicha%';

Metriky: Recall@5, Recall@10.

## Test 3 - Negativni dotazy (rucne, staci 5)

Dotazy, na ktere v datech odpoved NENI. Spravna odpoved = "nenasli jsme nic".

  "lek na zlomeninu nohy"
  "neco na HIV"
  "pripravek na hubnuti"
  "vitamin C"          (pokud neni ve whitelistu ATC)
  "ockovani proti chripce"

Tohle je na demu NEJSILNEJSI test. Kdyz systém na neexistujici tema rekne
"nemam", je to pro vedeni presvedcivejsi dukaz, ze nefabuluje, nez deset
spravnych odpovedi. Zaroven je to jediny test, ktery overi prah podobnosti.

### Kalibrace prahu podobnosti
Testy 2 a 3 dohromady urci prah: najdi hodnotu, pri ktere negativni dotazy
uz neprojdou, ale automaticky generovane (test 2) porad prochazi.
Prah NEHADAT od stolu - musi vyjit z techto dvou mnozin.

## Test 4 - Parafraze (rucne, staci 10)

Jedina kategorie, kterou automat nevyrobi - dotazy bez doslovneho prekryvu.
Tady se rucne napise ocekavany vysledek. Je to ta nejzajimavejsi cast,
protoze ukazuje, ze semantika umi neco, co fulltext ne.

| dotaz                    | ocekavane leky   | proc to automat nevyrobi          |
|--------------------------|------------------|-----------------------------------|
| "pali me zaha"           | HELICID, RENNIE  | v datech "refluxni choroba jicnu" |
| "nemuzu dychat nosem"    | OLYNTH           | v datech "nosni kongesce"         |
| "boli me v krku"         | (doplnit)        | jina formulace v indikacich       |
| "mam rymu"               | OLYNTH           | v datech "rinitida"               |
| "boli me hlava"          | PARALEN, PANADOL | primy prekryv, kontrolni priklad  |

## Vystup skriptu

    $ uv run python evaluate.py

    --- TEST 0: kvalita dat (nez se vubec merí hledani) ---
    Pokryti sekci             48/50    96 %   CHYBI: 0239484 (davkovani)
    Prazdne sekce              3       CHYBA: 0246012/indikace, ...
    Struktura JSONB          198/201   98 %   CHYBA: chybi klic "frekvence" (3x)
    Frekvence nenamapovana    12/430    3 %   OK
    Chybi cislo stranky        0        OK

    --- TEST 1-4: kvalita hledani ---
    Invarianty filtru         48/48   100 %   OK
    Auto-recall @5           192/200   96 %
    Auto-recall @10          198/200   99 %
    Parafraze (rucne)          8/10    80 %   CHYBA: "boli me v krku", "na otok"
    Negativni dotazy           5/5    100 %   OK (spravne nic nevratil)

POZOR na poradi: kdyz TEST 0 hlasi diry v datech, cisla z testu 1-4 nemaji
smysl interpretovat jako kvalitu hledani. Lek, ktery neni v datech, nemuze
byt nalezen - a vypadalo by to jako chyba vyhledavani, i kdyz je chyba
v extrakci. Nejdriv opravit data, pak ladit hledani.

Skript pustit po KAZDE zmene chunkovani, promptu, modelu nebo vah RRF.
Hned je videt, jestli zmena pomohla nebo uskodila - misto dojmu z peti
rucne vyzkousenych dotazu.

## vedlejsi uzitek
Eval vyresi i otevrene dohady, ktere nejde rozhodnout od stolu:
- davat nazev leku do dense vektoru, nebo jen do fulltextu? -> pustit obojim
  zpusobem a porovnat cisla
- vaha RRF mezi semantikou a fulltextem
- bge-m3 vs qwen3-embedding:8b
- velikost limitu na ATC skupinu (50 vs 500 leciv)
Rozhodne mereni, ne nazor.