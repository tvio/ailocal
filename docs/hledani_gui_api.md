# GUI a API

Webová nadstavba nad hledáním. Backend **FastAPI** (`api.py`), frontend
**vanilla JS** bez frameworku a bez build kroku (`static/`). Stav k 7. 10. 2026.

    uv run uvicorn api:app --port 8000

Jak hledání funguje uvnitř: `docs/hledani_jak_funguje.md`.

| adresa | co tam je |
|---|---|
| http://localhost:8000/ | aplikace |
| http://localhost:8000/docs | **Swagger** – dokumentace a zkoušení API |

**Na serveru** je aplikace na `https://t-api-dlp01.sukl.cz:8090/` – HTTPS
dělá kontejner nginx před uvicornem (`docs/provoz_prenos_na_server.md` kap. 5).
Frontend volá API relativními adresami (`/api/…`), takže o portu ani
o HTTPS neví a nic se v něm nenastavuje.

---

## Nahrávání modelu při startu

Pro hledání jsou potřeba dva modely: router `gemma4:26b` (19 GB)
a `bge-m3`. Ollama je po ~5 minutách nečinnosti odloží a načtení routeru
trvá kolem 10 sekund. Kdyby se načítal až u prvního dotazu, první
návštěvník čeká a neví proč.

Proto se nahrává **na pozadí hned při startu** (`@app.on_event("startup")`
pustí vlákno). Než je hotovo:

- `/api/hledat` vrací **503** s hláškou, co se děje
- frontend přes `/api/stav` cyklí co 1,5 s a drží přes celou stránku
  přesýpací hodiny s textem *„aplikace startuje (model se načítá do paměti)"*

Výpis léčiv (`/api/leciva`) model nepotřebuje a jede hned.

---

## Endpointy

| metoda | cesta | k čemu |
|---|---|---|
| GET | `/api/stav` | jsou modely v paměti? + `uzly`: stav strojů s Ollamou (dostupnost, rozpracované dotazy, odezva, modely v paměti) |
| GET | `/api/lecivo/{kod}/sekce/{sekce}` | všechny položky jedné sekce léku v pořadí dokumentu (GUI: „Ostatní indikace léku" v rozbalení, načítá se až při rozbalení) |
| GET | `/api/leciva` | výpis korpusu (jen zástupci SPC), stránkovaný (`strana`, `na_strance` 5–200, GUI nabízí 10/25/50/100) a řaditelný |
| GET | `/api/hledat` | sémantické hledání |
| GET | `/api/pdf/{kod_sukl}` | původní SPC v PDF |
| GET | `/api/slovnik` | hledací slovník: výraz uživatele → formulace z indikací (tabulka `slovnik_dotazu`), naposledy upravený výraz první |
| GET | `/api/slovnik/formulace?q=` | které zjednodušené indikace v datech obsahují text (nabídka v GUI), s počtem léků |
| POST | `/api/slovnik` | přidat k výrazu jednu nebo víc formulací (`formulace` = text nebo pole; uloží se všechny, nebo žádná); každá MUSÍ být v indikacích některého léku (jinak 422), max 4 na výraz. Platí hned, bez restartu |
| DELETE | `/api/slovnik?vyraz=&formulace=` | odebrat jednu formulaci |

**Hledací slovník v GUI** (6. 10.): zabalený blok pod vyhledáváním s návodem
a dvěma příklady. Uživatel napíše svůj výraz (kmen slova), do druhého pole
část indikace; pod polem se nabídnou formulace, které v datech opravdu
jsou, s počtem léků. Klikáním jich jde vybrat víc (nejvýš 4), tlačítko
Přidat uloží celý výběr a seznam se znovu načte – nový výraz je první.
Křížkem jde jednotlivou formulaci odebrat.

Zápis jde do tabulky `slovnik_dotazu` v Postgresu – společná všem
instancím API, čte se při každém hledání (žádná cache, žádný restart).
`common/data/slovnik_dotazu.json` je jen výchozí náplň při založení tabulky.
**Bez přihlášení může slovník měnit každý, kdo GUI vidí** (`todo.md`).

### Jeden tvar odpovědi pro obojí

`/api/leciva` i `/api/hledat` vracejí **tentýž objekt**, takže frontend
kreslí jednu komponentu. U výpisu bez hledání jsou pole z hledání prostě
`null` a v rozbaleném detailu se ukážou jako **NA**.

    { "dotaz": null, "router": null, "celkem": 5880, "strana": 1,
      "stran": 588, "radky": [ { "lecivo": {...}, "skore": null,
      "nejlepsi": null, "dalsi": [] } ],
      "cely_usek": false, "usek_orezan": false, "vyber_filtrem": false,
      "atc_navrh": [] }

`lecivo` nese i věk použití (`vek_od`, `pro_deti`). Výpis i hledání
vracejí jen **zástupce SPC** (víc balení téhož léku se neopakuje).

### Řazení

`?razeni=` bere jen hodnoty z whitelistu (`nazev`, `kod_sukl`, `sila`,
`atc`, `na_predpis`, `hrazeno`, `ucinne_latky`) – jde to přímo do
`ORDER BY`, takže volný vstup tam nesmí. `?smer=asc|desc`.

Ve **výsledcích hledání se neřadí podle sloupců** – tam řadí relevance.

### Vynucení sekce

`?sekce=indikace|davkovani|kontraindikace|nezadouci_ucinky` **přebije
router**. Omezení platí jen na sekční výstupy:

- filtry z dotazu (volně prodejný, hrazený, účinná látka, síla) **platí dál**
- základní údaje o léčivu se vracejí vždycky

Ověřeno: `?q=paralen&sekce=nezadouci_ucinky` vrátí
`filtr = sekce: nezadouci_ucinky; název obsahuje „Paralen"`.

### Odkaz do PDF na konkrétní stranu

Každá nalezená pasáž nese `strana_pdf`. Frontend otevírá
`/api/pdf/{kod}#page=N` – fragment `#page=` umí vestavěný prohlížeč PDF,
takže se dokument otevře **rovnou u nalezeného místa**. Ikona je 📝.

### Práh podobnosti jde nastavit z obrazovky

Posuvník **Práh podobnosti** (0 – 0,9, krok 0,05) se posílá jako
`?prah=`. Výchozí je **0,60**, tlačítko vedle ho vrátí. Hodnota je
naměřená na 32 lécích a na celém trhu pouští falešné shody – přeměření
je v `todo.md`.

Posun posuvníku jen překresluje číslo; **hledá se až při puštění**
(`change`, ne `input`) — jinak by každý krok posílal dotaz na model.

**U přesných filtrů se práh neuplatňuje** (název, látka, síla, ATC,
frekvence) — výběr už udělal filtr. API v tom případě vrátí `prah: 0.0`
a blok routeru napíše *„práh neuplatněn (filtr je přesný)"*, aby to
nevypadalo, že posuvník nefunguje.

### Čtení sekce místo hledání v ní

Když dotaz jmenuje **konkrétní lék a jednu konkrétní sekci**
(„dávkování zyrtec"), vrátí se **celá sekce v pořadí dokumentu**
a odpověď má `cely_usek: true`.

**Shoda se neukazuje, kde nic neříká (6. 10.).** Sloupec Shoda je prázdný
a skóre (RRF, cosine, fulltext) v detailu schované ve dvou případech:

- `cely_usek` – čtení sekce („dávkování helicid"): řádky vybral filtr lék + sekce;
- `vyber_filtrem` – dotaz jen z atributů („paracetamol", „helicid", „paralen 500mg",
  kód SÚKL): léky vybral SQL filtr nad registrem (`nazev ILIKE`, účinná látka,
  síla, kód, ATC). Cosine a fulltext se počítají nad řádkem identity léku,
  určují jen POŘADÍ uvnitř výběru a „paracetamol" → PARALEN 0,65 vypadalo
  jako slabá shoda. Záhlaví sloupce: „Nalezeno (podle názvu, látky nebo kódu)".

Jakmile dotaz nese i příznak („paralen bolest hlavy"), shoda se ukazuje – tam
měří podobnost příznaku s textem SPC.

Důvod: výběr už udělal filtr a do vektoru jde jen název léku, který
v textu sekce vůbec není. Podobnosti pak vyjdou 0,320 / 0,307 / 0,303 —
šum. Řadit podle toho by znamenalo ukázat náhodnou pasáž místo té první.

V tomhle režimu se pasáže **neořezávají**. Když sekci zúžil ještě další
filtr (frekvence, skupina pacientů, orgánový systém), vrací odpověď
`usek_orezan: true` a popisek se změní — tvrdit „celá sekce" u 6 položek
ze 44 by byla nepravda:

| stav | popisek v GUI |
|---|---|
| nic dalšího nezúžilo | *celá sekce, 44 položek — rozbalte ▼* |
| zúženo filtrem | *odpovídá filtru: 6 položek — rozbalte ▼* |

### Filtr na frekvenci nežádoucích účinků

Dotaz „vzácné nežádoucí účinky ablymico" nastaví **přesnou** frekvenci
(`frekvence: vzácné`), ne „rank ≤ 4". Rozdíl je zásadní — s rankem by
přišlo i 19 častých a 5 velmi častých, tedy opak toho, co člověk chtěl.

`frekvence_rank_max` se použije jen u výslovného „a častější".

Frekvence se počítá mezi **řízené hodnoty**, takže se u ní neuplatňuje
práh podobnosti — výběr už udělal filtr.

### Záchranná síť podle ATC

Když hledání nevrátí nic, přidá se `atc_navrh` – léčiva z odpovídající
terapeutické skupiny. Frontend to kreslí **odděleně, čárkovaným rámečkem
a s upozorněním, že to není údaj ze SPC**. Filtr uživatele platí i tady
(na „hrazené antibiotikum" nevyskočí nehrazený AMOKSIKLAV).

---

## Frontend

Jeden soubor `static/app.js`, žádné závislosti.

| prvek | chování |
|---|---|
| pole dotazu | placeholder `hrazené léky na reflux`, **Enter hledá** |
| „Nastavení hledání" | zabalený blok (výchozí stav): omezení na sekci, posuvník prahu (0 – 0,9; hledá se až při puštění; tlačítko vrátí 0,60) a „Zvýraznit od" |
| „Zvýraznit od" | jen obarví řádky podle shody (spolehlivé / hraniční), nic nefiltruje a neposílá dotaz |
| „Hledací slovník" | zabalený blok: návod, přidání výrazu s formulacemi z nabídky, seznam a odebrání |
| stránkování | okénkem, výběr 10 / 25 / 50 / 100 na stránku |
| Hledat / Reset | Reset vrátí úvodní výpis a zruší filtr sekce |
| šipka ▼ vlevo / klik na řádek | rozbalí detail: další shody nebo celá sekce, údaje o léku; skóre (RRF, cosine, ts_rank) jen tam, kde něco říká |
| 📝 vpravo | otevře SPC v PDF na příslušné straně |
| hodiny v řádku | *model pracuje…* během dotazu |
| hodiny přes stránku | *aplikace startuje* dokud není model v paměti |
| sloupec Shoda | podobnost nejlepší pasáže; **prázdný** u čtení sekce a u dotazů jen z atributů |

**Metadata jsou schválně zabalená.** Díky tomu se úvodní výpis a výsledek
hledání skoro neliší – u výpisu jsou skóre `NA`, ale nejsou vidět, dokud
si je někdo nerozbalí.

---

## Co ještě chybí

- řazení ve výsledcích hledání (teď jen relevance)
- filtr Rx/OTC a hrazení klikáním (jde jen dotazem nebo přes API)
- stránkování hledání načítá celý výsledek a stránkuje až v paměti
- přihlášení pro úpravy hledacího slovníku
- upozornění, když je v zabaleném „Nastavení hledání" něco jinak než
  výchozí (vybraná sekce, posunutý práh)
- stav strojů s Ollamou je jen v `/api/stav`, v GUI vidět není
- víc procesů API (uvicorn workers): každý proces si počítá vytížení
  strojů sám, o dotazech ostatních procesů neví

## Provoz

`--reload` po čase přestal zabírat a server běžel na starém kódu.
**Po změně kódu API radši restartovat**, po změně `static/` stačí
v prohlížeči Ctrl+F5.

### Jak na Windows najít a zabít proces (obdoba `ps -ef | grep`)

Vypsat python procesy i s příkazovou řádkou — `Get-Process` sám
`CommandLine` neukáže, proto `Get-CimInstance`:

    Get-CimInstance Win32_Process -Filter "Name like '%python%'" |
      Select-Object ProcessId, CommandLine | Format-Table -AutoSize

Zabít všechny uvicorny najednou:

    Get-CimInstance Win32_Process -Filter "Name like '%python%'" |
      Where-Object { $_.CommandLine -like '*uvicorn*' } |
      ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

Kdo drží port (obdoba `lsof -i :8000`):

    Get-NetTCPConnection -LocalPort 8000 -State Listen |
      Select-Object LocalPort, OwningProcess

**Pozor:** `Get-NetTCPConnection` občas vrátí PID, který už neexistuje —
socket je ve stavu, kdy proces skončil, ale port se ještě neuvolnil.
Když `Stop-Process` hlásí „proces nenalezen" a port pořád odpovídá, jdi
přes `Win32_Process` výš. Uvicorn navíc drží **dva** procesy (rodič
a worker), takže je potřeba zabít oba.

Zabití podle PID jde i klasicky:

    taskkill /F /PID 12345

## Dva režimy výsledku (od 1. 10. 2026)

| režim | kdy | řádek | rozbalení |
|---|---|---|---|
| **hledání** | „pálí mě žáha" | záhlaví „Nalezeno (nejlepší shoda)", v buňce [sekce] + pasáž, pod ní drobně „pro: … · věk · +N shod ▼" | další shody podle podobnosti, metadata |
| **čtení sekce** (`cely_usek`) | „nežádoucí účinky paralen", „dávkování vibrocil" | **souhrn sekce**: NÚ počty podle frekvence, dávkování skupiny pacientů, indikace počet + začátek | celá sekce uspořádaná podle smyslu: **NÚ seskupené podle frekvence** (nejčastější nahoře), **dávkování jako tabulka** (pro koho / dávka / jak často / poznámka), indikace seznam; metadata sbalená v „Údaje o léku" (bez skóre) |

Čtení sekce s 1–2 léky se **rozbalí samo**. Sekce zúžená filtrem
(„vzácné NÚ paralen") má v souhrnu „(odpovídá filtru)".

Proč: dřív se i u čtení sekce ukazovala v řádku PRVNÍ položka – NÚ
s první položkou „vzácné" vypadaly, jako by lék měl jen vzácné účinky.

Štítky u nálezu: **„indikace pro: …"** = skupina pacientů dané indikace
(z 4.1, jen když je známá); **„věk: od X let"** = věk použití léku
(`docs/hledani_vek.md`), podle něj filtruje „pro dítě X let".

**Buňka Nalezeno** (1. 10. 2026): vlevo **barevná značka sekce** s pevnou
šířkou (Indikace / Kontraindikace / Dávkování / Nežád. účinky / Identita,
plný název v bublině), vpravo dva zarovnané řádky – text nálezu
(u NÚ s frekvencí) a pod ním šedé doplňky „pro: skupina indikace (zkrácená
na 40 zn.) · věk použití · +N shod ▼". Co znamená sloupec, říká záhlaví
(„nejlepší shoda" / „souhrn sekce"), ne štítek v každém řádku.
