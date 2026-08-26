# GUI a API

Webová nadstavba nad hledáním. Backend **FastAPI**, frontend **vanilla JS**
bez frameworku a bez build kroku.

    uv run uvicorn api:app --port 8000 --reload

| adresa | co tam je |
|---|---|
| http://localhost:8000/ | aplikace |
| http://localhost:8000/docs | **Swagger** – dokumentace a zkoušení API |

---

## Nahrávání modelu při startu

Generativní model má **87 GB** a Ollama ho po ~5 minutách nečinnosti
odloží. Kdyby se načítal až u prvního dotazu, první návštěvník čeká
minutu a neví proč.

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
| GET | `/api/stav` | jsou modely v paměti? |
| GET | `/api/leciva` | výpis korpusu, stránkovaný a řaditelný |
| GET | `/api/hledat` | sémantické hledání |
| GET | `/api/pdf/{kod_sukl}` | původní SPC v PDF |

### Jeden tvar odpovědi pro obojí

`/api/leciva` i `/api/hledat` vracejí **tentýž objekt**, takže frontend
kreslí jednu komponentu. U výpisu bez hledání jsou pole z hledání prostě
`null` a v rozbaleném detailu se ukážou jako **NA**.

    { "dotaz": null, "router": null, "celkem": 26, "strana": 1,
      "stran": 3, "radky": [ { "lecivo": {...}, "skore": null,
      "nejlepsi": null, "dalsi": [] } ] }

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
`?prah=`. Výchozí **0,55** je naměřená hodnota, tlačítko vedle ho vrátí.

| práh | „mám reflux" vrátí |
|---|---|
| 0,30 | 10 léčiv (i zjevný šum) |
| **0,55** | **4 léčiva** |
| 0,75 | 1 léčivo (jen MAALOX 0,86) |

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
| posuvník prahu | 0 – 0,9; hledá se až při puštění; tlačítko vrátí 0,55 |
| Hledat / Reset | Reset vrátí úvodní výpis a zruší filtr sekce |
| šipka ▼ vlevo | rozbalí metadata řádku (skóre, cosine, ts_rank, pořadí, strana) |
| 📝 vpravo | otevře SPC v PDF na příslušné straně |
| hodiny v řádku | *model pracuje…* během dotazu |
| hodiny přes stránku | *aplikace startuje* dokud není model v paměti |

**Metadata jsou schválně zabalená.** Díky tomu se úvodní výpis a výsledek
hledání skoro neliší – u výpisu jsou skóre `NA`, ale nejsou vidět, dokud
si je někdo nerozbalí.

---

## Co ještě chybí

- řazení ve výsledcích hledání (teď jen relevance)
- filtr Rx/OTC a hrazení klikáním (jde jen dotazem nebo přes API)
- stránkování hledání načítá celý výsledek a stránkuje až v paměti

## Provoz

`--reload` po čase přestal zabírat a server běžel na starém kódu.
**Po změně schématu odpovědi radši restartovat.**

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
