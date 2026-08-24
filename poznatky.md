# Poznatky z realizace

Zápisy toho, co se během stavby ukázalo jinak, než zadání předpokládalo.
Nejnovější nahoře.

---

## 2026-08-24 — „Celá sekce" lhala, když ji zúžil další filtr

Hlášení: `časté nežádoucí účinky amoksiklav` vypíše celou sekci, přestože
router filtr našel správně — prý to přebije logika čtení sekce a měl by
zabrat další WHERE.

**WHERE zabíral celou dobu.** Ověřeno napřímo, bez routeru:

| filtr | položek | z celkových 44 |
|---|---|---|
| jen sekce + název | 44 | celá sekce |
| + `frekvence: časté` | **6** | zúženo |
| + `organovy_system` | **11** | zúženo |

Chyba byla v **popisku**. GUI psalo *„celá sekce, 6 položek"*, což je
nepravda — je to 6 ze 44. Kdo to čte, oprávněně usoudí, že filtr
nezabral.

**Oprava:** přibyl příznak `Odpoved.usek_orezan` — je `true`, když
sekci zúžil ještě nějaký další filtr (frekvence, skupina pacientů,
orgánový systém). Řazení podle dokumentu zůstává, protože je pořád
správné; mění se jen text:

| stav | popisek |
|---|---|
| `cely_usek`, nic dalšího | „celá sekce, 44 položek" |
| `cely_usek` + zúženo | **„odpovídá filtru: 6 položek"** |

**Poučení: popisek je součást odpovědi, ne dekorace.** Když text tvrdí
něco jiného, než co data dělají, vypadá to jako chyba ve funkci — a
hledá se pak tam, kde není. Je to potřetí dnes (po hlášce „nedosáhl
prahu podobnosti" u prázdného filtru a po točícím se kolečku).

### Vedlejší pozorování: router občas ztratí název léčiva

Při ověřování vyšlo, že `časté nežádoucí účinky amoksiklav` jednou
vytáhne `nazev='Amoksiklav'` a podruhé `nazev=None`. Bez názvu se režim
čtení nespustí, jede běžné hledání a práh výsledek ořeže na 2 položky
místo 6. Totéž se dřív stalo u `vzácné nežádoucí účinky paralen`.

**Je to nedeterminismus routeru, ne chyba filtru.** Do `todo.md`.

---

## 2026-08-24 — Frekvence jako filtr: „vzácné" nesmí znamenat „vzácné a všechno častější"

Podnět: frekvenci nežádoucích účinků máme v datech, tak ji použít.
`velmi časté nežádoucí účinky paralen` vracelo nula záznamů.

Nález byl trojí — první je **nedorozumění, ne chyba**:

### 1. Ta nula byla správně

PARALEN **žádné velmi časté nežádoucí účinky nemá**:

| rank | frekvence | položek |
|---|---|---|
| 4 | vzácné | 3 |
| 5 | velmi vzácné | 10 |
| 9 | není známo | 2 |

Nula je tedy věcná odpověď. **Špatná byla hláška**, která tvrdila, že
nic nedosáhlo prahu podobnosti — přitom filtr nepustil dál ani jeden
záznam. Dvě různé příčiny slité do jedné věty. GUI teď rozlišuje:

    Filtr nepustil dál ani jeden záznam (sekce: nezadouci_ucinky;
    frekvence: velmi časté; název obsahuje „Paralen“). Taková
    kombinace v datech není — zkuste dotaz bez některého omezení.

### 2. `frekvence_rank_max` je pro vzácný konec ŠPATNÁ sémantika

Filtr uměl jen „rank ≤ N", tedy „aspoň tak časté". U častého konce to
dává smysl, u vzácného je to **přesný opak** toho, co člověk chce.
Změřeno na ABLYMICU, dotaz na **vzácné**:

    vraci: {'vzácné': 1, 'časté': 19, 'méně časté': 7, 'velmi časté': 5}

Kdo se ptá na vzácné účinky, nechce vidět těch 5 velmi častých.

**Oprava:** přibyl `Filtr.frekvence` — **přesná** hodnota z číselníku.
`frekvence_rank_max` zůstává, ale router ho použije jen u výslovného
„a častější". Normalizuje se přes `normalizuj_frekvenci()`, tedy touž
funkcí jako data, aby filtr a obsah mluvily stejným jazykem.

| dotaz | filtr | vrací |
|---|---|---|
| vzácné nežádoucí účinky ablymico | `frekvence: vzácné` | jen vzácné (1) |
| časté a častější účinky ablymico | `rank_max: 2` | časté 19 + velmi časté 5 |

### 3. Práh odřízl i to, co filtr správně vybral

`velmi časté nežádoucí účinky` (bez léku) našlo filtrem správných **12
řádků a všechny je odřízl práh 0,55**. Dotaz totiž nenese žádný příznak,
na kterém by se dala podobnost měřit — „velmi časté nežádoucí účinky"
není nic, co by v textu účinku stálo.

Je to táž věc jako u atributů („vektor nerozliší paracetamol od
pefloxacinu") a u čtení sekce („dávkování zyrtec"). **Frekvence přidána
do `Filtr.je_presny()`**, takže se práh neuplatní — výběr už proběhl
podle řízené hodnoty.

Výsledek: `velmi časté nežádoucí účinky` vrátí 3 léčiva, samé velmi časté.

### Poučení, potřetí v jiné podobě

**Když dotaz nenese nic než specifikaci filtru, práh ani řazení podle
podobnosti nemají co měřit.** Pokaždé se to projeví jinak — jednou
náhodným pořadím, jednou prázdným výsledkem — ale příčina je stejná.
Stojí za zvážení, jestli by `organovy_system` (taky řízená hodnota
z MedDRA) neměl do `je_presny()` taky.

### Vedlejší nález: jedna nenormalizovaná frekvence

V korpusu je `rank=9  "nejčastějším"  1x` — hodnota, kterou
`normalizuj_frekvenci()` nerozpoznala a spadla do „není známo".
Do `todo.md`.

---

## 2026-08-24 — „Dávkování zyrtec" je ČTENÍ sekce, ne hledání v ní

Hlášení: `dávkování zyrtec` vrátí jen dávkování pro dospělé s poškozením
ledvin. Data přitom mají všech 6 řádků včetně obecného.

Router odvedl práci správně:

    sekce = davkovani; název obsahuje „Zyrtec"

Jenže do vektoru pak šlo jen slovo **`zyrtec`**, které v textu dávkování
**vůbec není**. Podobnosti proto vyšly

    0,320  dospělí s těžkým poškozením ledvin bez dialýzy
    0,307  obecní skupina 10 mg (1 tableta) jednou denně
    0,303  dospělí se středním poškozením ledvin
    …

**Rozdíl 0,017 mezi prvním a druhým je šum**, ne informace. Nahoru se
dostalo, co zrovna padlo — a seskupení pak ukázalo jen tu jednu pasáž.

### Dva různé úmysly, které vypadají stejně

| dotaz | co člověk chce |
|---|---|
| „pálí mě žáha" | **najdi** mi lék |
| „dávkování zyrtec" | **ukaž** mi tuhle sekci |

U druhého výběr **už udělal filtr** a řadit podle podobnosti nemá co
měřit. Je to táž věc jako dřív u atributů („vektor nerozliší paracetamol
od pefloxacinu"), jen se to projevilo uvnitř jednoho léčiva.

### Oprava: režim čtení sekce

Když filtr obsahuje **konkrétní lék** (`nazev` nebo `kod_sukl`) **a jednu
konkrétní sekci**, vrátí se **celá sekce v pořadí dokumentu**, ne seřazený
výběr. `Odpoved.cely_usek` to hlásí dál, API v tom režimu neořezává
pasáže a GUI napíše „celá sekce, 6 položek — rozbalte".

    obecní skupina 10 mg (1 tableta) jednou denně          <- ted prvni
    starší lidé s normální funkcí ledvin 10 mg jednou denně
    dospělí se slabým poškozením ledvin 10 mg jednou denně
    …

Běžné hledání se nezměnilo (ověřeno: „pálí mě žáha" dál MAALOX 0,860,
`cely_usek=false`), evaluace beze změny.

**Poučení: pořadí podle podobnosti dává smysl jen tam, kde je podobnost
čím měřit.** Když dotaz nenese nic než identitu, je jakékoli řazení
náhoda a poctivější je vrátit pořadí z dokumentu.

### Vedlejší nález: „obecní skupina" místo „obecná"

V datech ZYRTECu je `obecní skupina 10 mg` — překlep z extrakce
(„obecní" místo „obecná"). Do `todo.md`.

---

## 2026-08-24 — `hidden` neskryje prvek, který má vlastní `display`

Kolečko „model pracuje…" se točilo pořád, ne jen během dotazu. Logika
v JS byla přitom správná — zapnout před `fetch`, vypnout ve `finally`.

Chyba byla v CSS:

    .pracuje { display: flex; ... }

Atribut **`hidden` skrývá jen přes `display: none` z výchozího stylu
prohlížeče**, takže ho přebije jakýkoli vlastní `display`. U překryvu
při startu jsem na to pamatoval (`.prekryv[hidden]`), u `.pracuje` ne.

Opraveno **globálně**, ne u jedné třídy:

    [hidden] { display: none !important; }

Předtím jsem si udělal audit — prvků skrývaných přes `hidden` je pět
(`start`, `pracuje`, `router`, `hlaska`, `atc-navrh`) a rozbité bylo
jen `pracuje`. Globální pravidlo ale znamená, že na to nemusím myslet
u žádné další třídy.

**Poučení: když se prvek skrývá atributem `hidden`, nesmí mít v CSS
vlastní `display` bez doprovodného pravidla.** Projeví se to jako
„funkce nefunguje", přestože kód je v pořádku.

### Vedlejší poznatek k provozu: uvicorn `--reload` po čase přestal

Watcher zachytil první změnu a pak už žádnou, takže server běžel na
starém kódu a vypadalo to, že úprava nezabrala. Restart pomohl.

Zabít ho nešlo přes port — `Get-NetTCPConnection` hlásila PID, který už
neexistoval. Skutečné procesy byly workeři:

    Get-CimInstance Win32_Process -Filter "Name like '%python%'"
    -> "python.exe -c from multiprocessing.spawn import spawn_main..."

**Po změně schématu odpovědi je jistější server restartovat**, ne se
spoléhat na `--reload`.

---

## 2026-08-24 — GUI: FastAPI + vanilla JS, jeden tvar odpovědi pro výpis i hledání

Postaveno `api.py` + `static/`. Podrobně v **`gui.md`**.

### Rozhodnutí, které ušetřilo nejvíc práce

`/api/leciva` (úvodní výpis) a `/api/hledat` vracejí **tentýž objekt**.
U výpisu jsou pole z hledání prostě `null`. Frontend tak kreslí **jednu
komponentu** místo dvou a metadata jsou v obou případech schovaná
v rozbalovacím řádku — u výpisu se ukážou jako `NA`.

Vyplynulo to ze zadání („nemusí se zas tak lišit iniciační report od
vyhledaného"), ale platí to i technicky: dvě různé tabulky by znamenaly
dvakrát psát řazení, stránkování i rozbalování.

### Nahrávání modelu je součást UX, ne detail

87 GB se nahrává **na pozadí při startu aplikace**, ne u prvního dotazu.
Než je hotovo, `/api/hledat` vrací **503 s hláškou** a frontend drží přes
celou stránku přesýpací hodiny s textem, **co se děje a proč to trvá**.

Je to totéž poučení jako u CLI: mlčící aplikace vypadá jako rozbitá.
Rozdíl je, že u webu to musí vydržet i to, že uživatel přijde dřív než
model — proto `/api/stav` a cyklení co 1,5 s.

### Řazení jde do ORDER BY, takže whitelist

`?razeni=` se mapuje přes slovník `RAZENI`, ne skládá do SQL. Volný
vstup v `ORDER BY` je injektáž.

Ve **výsledcích hledání se podle sloupců neřadí** — tam řadí relevance
a míchat to s abecedou by dávalo nesmysly.

### Odkaz do PDF na konkrétní stranu

Každá pasáž nese `strana_pdf`, frontend otevírá `/api/pdf/{kod}#page=N`.
Fragment `#page=` umí vestavěný prohlížeč PDF, takže není potřeba nic
renderovat na serveru — dokument se otevře rovnou u nalezeného místa.

### Drobnost, kterou stálo za to změřit

Ikonu „obdélník s tužkou" jsem nejdřív napsal jako `&#128441;`, což je
U+1F5B9 🖹 (dokument s textem). Správně je `&#128221;` = U+1F4DD 📝.
**U číselných entit se vyplatí si ten znak vypsat**, ne odhadovat
z paměti.

### Stav

Ověřeno: výpis 26 léčiv na 3 stránky, řazení podle všech sloupců,
hledání s routerem, vynucení sekce (`?q=paralen&sekce=nezadouci_ucinky`
→ `filtr = sekce: nezadouci_ucinky; název obsahuje „Paralen"`), ATC
záchranná síť respektující filtr, PDF 200 / neexistující 404, Swagger
na `/docs`.

---

## 2026-08-24 — OCR záměna `4.l` místo `4.1` schovala celou sekci

Při doplňování korpusu na 26 léčiv nahlásila pipeline u **TALVOSILEN
FORTE** stav `chybi_v_dokumentu` u indikací. V dokumentu ale jsou —
nadpis zní

    ## 4.l Terapeutické indikace

s malým písmenem **`l`** místo číslice **`1`**. Klasická záměna z OCR.
Regex hledal `4\.1`, takže **celá sekce zmizela** a nikdo se to nedozvěděl
jinak než tím, že u léčiva chyběla data.

**Oprava:** `sekce._cislo_na_vzor()` — každá číslice se hledá i ve svých
záměnách:

    "4.1"  ->  4\.[1lI|!]

| číslice | záměny |
|---|---|
| 0 | O o Q |
| 1 | l I \| ! |
| 2 | Z |
| 5 | S |
| 6 | G |
| 8 | B |
| 9 | g |

Po opravě: *„Všechny sledované sekce nalezeny u všech léčiv."*

**Poučení: u textu z OCR se nesmí hledat přesná číslice.** Zvlášť když je
to jediný klíč, podle kterého se sekce pozná — selhání je pak tiché
a vypadá jako chybějící data ve zdroji, ne jako chyba parseru.

### Vedlejší nález, který zůstal: model při extrakci ztratil část výčtu

Zdroj TALVOSILENu říká

    …bolesti různého původu, např. při bolesti hlavy a zubů, při bolesti
    nervového původu, bolesti při zraněních a operacích, bolesti při
    degenerativních revmatických onemocněních…

Model z toho udělal 3 položky a **bolest hlavy, zubů, nervového původu
ani po zraněních mezi nimi nejsou**. Deterministická kontrola to
neodhalila, protože kotvu na zdroj má, ale nepočítá položky výčtu.
Zapsáno do `todo.md`.

---

## 2026-08-24 — Obecné slovo v dotazu proti konkrétní formulaci: znovu a jinde

Po doplnění korpusu nefungovaly nové demo dotazy — a byl to **potřetí
tentýž jev**, jen z jiné strany:

| dotaz | text v SPC | cosine |
|---|---|---|
| `bolest` | „středně silné až silné bolesti" (ULTRACOD) | **0,469** |
| `alergie` | „na úlevu od příznaků v nose a očích způsobených pylovou i celoroční alergií" (ZYRTEC) | **0,547** |

Obojí **pod prahem 0,55**, takže se nová léčiva vůbec nenašla. Dřív to
byl dlouhý text proti krátkému dotazu (MAALOX/reflux), teď obecné slovo
proti konkrétní formulaci — **stejná příčina, embedding průměruje.**

Řešeno stejným nástrojem, `slovnik_dotazu.json`. A je vidět, že to
**rozlišuje**, ne jen plošně zvedá skóre:

| varianta dotazu | ULTRACOD | ZYRTEC |
|---|---|---|
| `bolest` | 0,469 | 0,421 |
| **`středně silné až silné bolesti`** | **0,804** | 0,413 |
| `alergie` | 0,386 | 0,547 |
| **`úleva od příznaků alergie`** | 0,318 | **0,699** |

Správný lék jde nahoru, nesprávný zůstává dole nebo klesne.

### Výsledek na demo dotazech

| dotaz | před | po |
|---|---|---|
| hrazený lék na bolest | ALGIFEN 0,62 | **ULTRACOD 0,80** |
| nehrazený lék na předpis proti bolesti | (nic) | **TALVOSILEN 0,74** |
| volně prodejný lék na alergii | PARALEN 0,56 | **ZYRTEC 0,70** |
| volně prodejný lék na bolest hlavy | ACIFEIN 1,00 | ACIFEIN 1,00 (nezměněno) |

Poslední řádek je důležitý — obecný klíč „bolest" **nepřebil** konkrétní
dotaz na bolest hlavy.

Evaluace po rozšíření korpusu na 26 léčiv (1173 řádků): invarianty
210/210, recall @5 50/50 a @10 54/54, parafráze 10/10, negativní 7/8 —
**beze změny.**

---

## 2026-08-24 — Ztráta diakritiky stojí pětinu podobnosti a vrátí JINÝ lék

Našlo se při stavbě demo scénářů: „mám ucpaný nos" nevracelo **nic**,
přestože AFRIN i OLYNTH jsou přesně na to. Router vrátil
`dotaz_text: 'ucpany nos'` — **bez diakritiky**.

Změřeno na indikacích (bge-m3):

| s diakritikou | bez diakritiky |
|---|---|
| `ucpaný nos` → **0,682** AFRIN | `ucpany nos` → **0,464** AFRIN |
| `zácpa` → **0,657** BISACODYL | `zacpa` → **0,486** BISACODYL |
| `kašel` → **0,591 ACC** | `kasel` → **0,361 ABAKTAL** ← jiný lék! |

Ztráta je zhruba **0,2**, tedy dost na propadnutí pod práh. U „kašel" to
navíc přehodí pořadí a první je antibiotikum místo léku na kašel.

Souvisí to s tím, proč je fulltext nastavený na `unaccent` — jenže to
platí jen pro fulltext. **Vektor diakritiku vidí** a bez ní je to pro
něj jiné slovo.

### Tři vrstvy opravy, protoby jedna nestačí

**1. Pokyn v promptu routeru** — „piš česky s diakritikou, nikdy
nepřepisuj do ASCII". Nutné, ale samo o sobě nespolehlivé.

**2. Deterministická záchrana `router.obnov_diakritiku()`** — když se
slovo z `dotaz_textu` po odstranění diakritiky shoduje se slovem
z původního dotazu, vezme se **tvar uživatele**. Spolehnout se na prompt
nestačí; tohle je levné a nemůže to selhat.

    'ucpany nos' + 'mám ucpaný nos'  ->  'ucpaný nos'
    'kasel'      + 'pořád kašel'     ->  'kašel'

Nezachrání to jiný pád („zácpu" → „zácpa"), na to je vrstva 1.

**3. Rozšíření dotazu porovnává BEZ diakritiky** (`dotazy.rozsir()`).
Řeší případ, kdy **uživatel sám** píše bez diakritiky — pak vrstva 2
nemá odkud brát. Klíče jsou proto **kmeny** („kasl", ne „kašel"), aby
prošly skloňováním, a hodnoty diakritiku **mají** — právě ony ji do
hledání vrátí.

    'porad kaslu'  ->  + 'kašel', 'vykašlávání hlenu', 'zánět průdušek'

### Výsledek

| dotaz | před | po |
|---|---|---|
| porad kaslu | nic | **ACC 0,75** |
| mam ucpany nos | nic | **AFRIN 0,68**, OLYNTH 0,67 |
| mam zacpu | nic | **BISACODYL 0,66** |
| mam alergii | nic | **DITHIADEN 0,70**, AERIUS 0,58 |

**Poučení: co model vrátí jako text, se nesmí brát jako hotové.**
Router je generativní a tiše mění tvar slov — a u vektorového hledání
je tvar slova to jediné, na čem záleží.

### Vedlejší poučení: příliš obecný záznam ve slovníku škodí

Přidal jsem `"ekzem": ["ekzém", "zánět kůže"]` a „zánět kůže" začalo
trefovat AMOKSIKLAV („rozlitého zánětu kůže" = celulitida, bakteriální
infekce). Zúženo na `["ekzém", "atopický ekzém"]`. **Do rozšíření
dotazu patří jen formulace, které v datech opravdu znamenají totéž.**

---

## 2026-08-24 — Do CLI vráceny základní údaje o léčivu (a chyba v ATC síti)

Ve výpisu chyběly údaje o léku samotném — člověk viděl nalezenou pasáž,
ale ne jestli je lék na předpis, hrazený a co v něm je. Doplněno natěsno
na dva řádky, ať to nezabírá místo:

    kod SUKL   0254048 · OTC (volně prodejný) · nehrazený · ATC N02BE01
    látky      PARACETAMOL

Do `Vysledek` k tomu přibyly `ucinne_latky` a `atc` (spolu s dřívějšími
`na_predpis` a `hrazeno`), takže je má k dispozici i GUI — nemusí si pro
ně chodit zvlášť do DB.

### Přitom se našla chyba v ATC záchranné síti

Na dotaz **„hrazené antibiotikum"** síť nabízela **AMOKSIKLAV, který
hrazený NENÍ** — tedy přesný opak toho, co člověk chtěl. Síť se ptala
jen na ATC prefix a filtr uživatele ignorovala.

Opraveno: `vypis_atc_zachranu()` bere `Filtr` a uplatňuje `na_predpis`
i `hrazeno`. Po opravě zůstane jen ABAKTAL.

**Poučení: záchranná větev je pořád odpověď na TÝŽ dotaz.** Když se
píše fallback, snadno se zapomene, že omezení z dotazu platí i pro něj —
a nabídnout v nouzi něco, co uživatel výslovně vyloučil, je horší než
nenabídnout nic.

---

## 2026-08-24 — Realizováno: rozdělení pojmů, rozšíření dotazu, ATC záchranná síť

Všechny tři kroky provedeny a změřeny. Výsledek na původní stížnosti —
dotaz „mám reflux", jak to vidí uživatel v CLI:

| | před | po |
|---|---|---|
| 1. | CONTROLOC 0,578 | **MAALOX 0,858** |
| 2. | OMEPRAZOL 0,566 | **OMEPRAZOL 0,674** |
| 3. | **AFRIN 0,512** (ucpaný nos) | **CONTROLOC 0,616** |
| 4. | **PARALEN 0,510** (menstruace) | — |
| 9. | MAALOX | — |

### 1. Rozdělení vícepojmových položek — MODELEM, ne regexem

`rozdel_vycty.py`. Regex se **zamítl na základě měření**: naivní dělení
na čárkách by uškodilo ve **3 z 5** případů —

| lék | text | proč nedělit |
|---|---|---|
| OLYNTH | „zánětem, jako je alergickým, jiným než alergickým…" | přídavná jména k témuž zánětu |
| AMOKSIKLAV | „alergie na cefalosporiny, karbapenemy…" | ztratilo by se „alergie na" |
| ACIFEIN | „bolesti hlavy, zubů" | ze „zubů" samotného nic nezbude |

Model češtinu chápe a tyhle tři **správně nerozdělil**, u ostatních
doplnil chybějící tvar („zubů" → „bolest zubů"). Položek bylo 7, takže
šlo projít očima.

Do promptu bylo nutné přidat, že díl musí být **v 1. pádě a bez spojek** —
první běh vracel „zejména bolesti hlavy" a „a bolestí kloubů".

Výsledek: 3 položky → 15, korpus 994 → **1006 řádků**.

| dotaz | před | po |
|---|---|---|
| pořád říhám | 0,431 (**pod prahem**, nenašlo) | **0,507** |
| pálí mě žáha | 0,633 | **0,783** |
| bolí mě zuby | — | **0,845** (ACIFEIN) |

### 2. Rozšíření dotazu (`common/dotazy.py`, `slovnik_dotazu.json`)

Rozšiřuje se **DOTAZ, ne data**. V SQL se bere `GREATEST` přes varianty —
nejlepší shoda vyhrává, ne průměr.

    "mám reflux" -> + "vracení kyselého obsahu ze žaludku do úst"
                    + "návrat obsahu žaludku do jícnu" + "regurgitace"

MAALOX na „mám reflux": **0,510 → 0,858**.

Proč se nepřidávají řádky do dat: CLI u každého výsledku tiskne
`zdroj … spc.md § 4.1`. Vygenerovaný řádek by zdroj neměl a přišli
bychom o dohledatelnost, což je hlavní přednost celé ukázky.

### 3. ATC záchranná síť (`atc_mapa.json`)

Ukáže se **jen když hledání nevrátí nic**, odděleně a označeně:

    PODLE TERAPEUTICKE SKUPINY (odvozeno z ATC, NENI to udaj ze SPC)
      A02 - léčiva na poruchy žaludeční kyselosti
          CONTROLOC 20MG, MAALOX 400MG/400MG, OMEPRAZOL FARMAX 20MG

Výrazy musí být **kmeny, ne celé tvary** — „alergie" neodpovídá „alergii".

### Práh musel nahoru: 0,50 → 0,55

**Rozdělení posunulo celé rozdělení podobností.** Krátký řádek je
podobnější všemu než dlouhý specifický, takže vzrostly i falešné shody:
negativní dotaz „lék na schizofrenii" trefil nově vzniklý řádek
„bolest hlavy" na 0,537.

Ověřeno, že to **není vinou rozšiřování dotazu** — u těch tří
negativních dotazů se rozšíření vůbec nespustilo.

| práh | parafráze | negativní |
|---|---|---|
| 0,50 | 10/10 | 5/8 |
| **0,55** | **10/10** | **7/8** |
| 0,60 | 7/10 | 8/8 |

Změněno i výchozí `--prah` v CLI z **0.0 na 0.55** — proto se dřív
u refluxu ukazoval AFRIN.

### Konečný stav

```
Invarianty filtru           210/210   100%
Auto-recall @5               48/48    100%
Auto-recall @10              56/56    100%
Negativní dotazy (práh 0,55)  7/8      88%
Parafráze (ručně)            10/10    100%
```

Negativní 7/8 je **stejně jako před celou prací**, ale správné odpovědi
mají teď mnohem větší odstup (0,858 proti 0,674) místo dřívějšího
těsného shluku, kde se mezi správné vešel sprej na nos.

Jediný neúspěch: „léčba roztroušené sklerózy" → AMOKSIKLAV 0,564
(„rozlitého zánětu kůže") — nový řádek z rozdělení výčtu.

---

## 2026-08-24 — Nejlepší rozšíření dotazu není synonymum, ale FORMULACE DOKUMENTU

Návrh: když výraz v textu chybí, dogenerovat synonyma — typicky podle ATC
nebo účinné látky (omeprazol → reflux, antibiotika → infekce) a případně
z toho udělat další řádky indikací.

Změřeno, co která varianta udělá s MAALOXem (ze 136 indikací):

| co jde do vektoru | MAALOX |
|---|---|
| `mám reflux` (dnešní stav) | #19, 0,474 |
| `regurgitace` — odborné synonymum | #10, 0,488 |
| **`vracení kyselého obsahu ze žaludku do úst`** | **#1, 0,647** |

**Odborné synonymum pomůže málo, formulace z dokumentu trefí napoprvé.**
Je to logické — vektor porovnává s tím, co v dokumentu opravdu stojí,
takže nejlepší „synonymum" je ta věta sama. Číselník pojmů tedy nemá
mapovat jen `odborný → laický`, ale i `laický dotaz → formulace v textu`.

### Dvě věci v návrhu se míchají a je potřeba je oddělit

| | příklad | co to je |
|---|---|---|
| **synonymum** | regurgitace = reflux | totéž jinými slovy — bezpečné, symetrické |
| **odvození** | omeprazol → reflux | tvrzení, CO lék léčí — to je nová informace |

To druhé **není synonymum**, je to lékařská znalost, kterou tam přidáme
my. A tady je riziko: kdyby se z toho udělaly **další řádky indikací**,
psali bychom do dat něco, **co v SPC není**. Přitom celá přednost téhle
ukázky je dohledatelnost — CLI u každého výsledku tiskne
`zdroj  data/leciva/…/spc.md § 4.1`. Vygenerovaný řádek by žádný zdroj
neměl.

**Doporučení: odvozená slova smí sloužit jen k VYHLEDÁNÍ, nikdy
k ZOBRAZENÍ.** Uživatel ať pořád vidí větu ze SPC; synonymum jen pomůže
tu větu najít. Pak se nic nevymýšlí a dohledatelnost zůstává.

### ATC jako podklad je dobrý nápad — je to řízená hodnota

Není to odhad, ATC přiřazuje SÚKL a v korpusu ho mají **všechna léčiva**:

| ATC | léčiv | co to je |
|---|---|---|
| A02 | 3 | CONTROLOC, MAALOX, OMEPRAZOL — porucha acidity |
| N02 | 3 | ACIFEIN, ACYLCOFFIN, PARALEN — analgetika |
| J01 | 2 | ABAKTAL, AMOKSIKLAV — antibiotika |
| R01 | 2 | AFRIN, OLYNTH — nosní dekongestiva |
| R06 | 2 | AERIUS, DITHIADEN — antihistaminika |

Pět skupin pokryje 12 z 22 léčiv, takže mapovací tabulka je **malá
a ručně zkontrolovatelná** — ne generování na každý lék zvlášť.

**Ale je to znalost NA ÚROVNI TŘÍDY**, takže zvedá jen recall, ne
precision: kdyby se A02 označilo jako „reflux", dostanou všechna tři
léčiva stejné skóre a uvnitř skupiny se rozlišovat nedá. Jako záchranná
síť „aspoň se ta trojice najde" to funguje, jako řazení ne.

### Doporučené pořadí kroků

1. **Rozdělit vícepojmové řádky** — nejlevnější, nic se nevymýšlí,
   pomůže všem příznakům naráz (+0,23 až +0,29)
2. **Číselník `dotaz → formulace v textu`** — změřeno #1, žádná změna
   schématu, stačí rozšířit dotaz před embedováním
3. **ATC mapa jen jako záchranná síť** pro dotazy, kde první dvě selžou,
   a **výhradně pro vyhledání**, ne do zobrazených indikací

---

## 2026-08-24 — „Rozdělit" znamená rozdělit POJMY do řádků, ne rozsekat pojem

Upřesnění, protože předchozí zápis sváděl ke špatnému čtení. Dotaz zněl:
„vracení kyselého obsahu ze žaludku do úst je přece jeden pojem, to už
nemůžu rozsekat, ne?" **Správně — a taky se to dělat nemá.**

### Myšlenkový model: embedding je JEDEN BOD

Vektor je jeden bod v prostoru významů. Když do řádku dáš **jeden**
pojem, bod padne na něj. Když tam dáš **čtyři**, padne někam doprostřed
mezi ně — a tedy blízko k žádnému.

MAALOX má dnes v jednom řádku čtyři samostatné příznaky:

    léčba potíží spojených s přílišnou kyselinou v žaludku, jako jsou
      ├─ pálení žáhy,
      ├─ časté říhání,
      ├─ vracení kyselého obsahu ze žaludku do úst
      └─ a bolest v břiše na lačno

Návrh je udělat z toho **čtyři řádky**, každý s jedním pojmem
**vcelku**. „Vracení kyselého obsahu ze žaludku do úst" zůstane přesně
takhle — jen dostane vlastní bod místo toho, aby se dělilo o jeden se
třemi dalšími.

### Netýká se to jen refluxu — trpí VŠECHNY čtyři

| dotaz uživatele | dnes (celá věta) | vlastní řádek | zisk |
|---|---|---|---|
| mám reflux | 0,474 | 0,555 | +0,081 |
| pálí mě žáha | 0,633 | **0,900** | +0,266 |
| pořád říhám | **0,431** | **0,663** | +0,232 |
| bolí mě břicho na lačno | 0,619 | **0,904** | +0,285 |

„Pořád říhám" má dnes **0,431, tedy pod prahem 0,50** — na říhání se
MAALOX nenajde vůbec, přestože to má v indikaci napsané.

### Zkracovat pojem NEPOMÁHÁ

Ověřeno, ať je jasné, že řešení není „psát to kratší":

| cosine | text |
|---|---|
| 0,555 | vracení kyselého obsahu ze žaludku do úst (celý pojem) |
| 0,549 | vracení kyseliny (zkráceno) |
| 0,554 | … (regurgitace) — odborný termín v závorce |
| **0,853** | **reflux** |

### Zbytek rozdílu NENÍ chunkování, ale SLOVNÍK

Rozdělení dostane MAALOX z #19 na #4, ale ne na #1. Důvod je jiného
druhu: **slovo „reflux" není v MAALOXu nikde** — ani laicky, ani
odborně. SPC říká „regurgitace kyselého žaludečního obsahu do úst"
a to má proti dotazu „mám reflux" jen **0,559**, prakticky totéž co
laický opis. Model prostě neví, že regurgitace = reflux.

Tady chunkování nepomůže z principu. Pomůže **číselník pojmů** —
rozšířit dotaz nebo text o synonymum. To je přesně ten dávno plánovaný
„test C" a je to další argument pro `slovnik_pojmu.json`.

### Vedlejší nález: odborný termín delší než 60 znaků se ZAHAZUJE

`naplni_db._spoj()` má `MAX_DELKA_ODBORNEHO = 60` a delší odborný text
do `obsah_text` nepřipojí. Proto je slovo „regurgitace" **v celém
indexu jen jednou** a u MAALOXu vůbec. Pravidlo dává smysl (nemá se
zdvojovat dlouhá věta), ale znamená to, že u dlouhých indikací se
odborná verze do hledání nedostane vůbec. Souvisí s návrhem embedovat
odborný a laický tvar jako dva samostatné vektory.

### Shrnutí: tři různé mechanismy, tři různé opravy

| problém | projev | oprava |
|---|---|---|
| víc pojmů v jednom řádku | bod padne doprostřed | **rozdělit na řádky** |
| dlouhý opis jednoho pojmu | mírné naředění | nechat vcelku, nezkracovat |
| slovo v textu vůbec není | model nespojí synonyma | **číselník pojmů** |

---

## 2026-08-24 — gpt-5-nano embeddingy NEUMÍ (403). Jako přeřazovač pomůže, ale nespolehlivě

Doplnění předchozího testu. Primární cíl byl vyzkoušet `gpt-5-nano`,
jenže **chat model vektory nevydá**:

    embeddings.create(model="gpt-5-nano")
    -> 403 "You are not allowed to generate embeddings from this model"

Je to táž věc, kterou máme lokálně u qwenu (501). Cloudový embedovací
test tedy proběhl přes `text-embedding-3-large` — to JE plnohodnotný
cloud, největší embedovací model OpenAI, a problém nevyřešil.

### Nano jako přeřazovač (retrieve-then-rerank)

`bench_rerank_nano.py`: bge-m3 zúží 136 na 20, nano jich 20 seřadí.

| dotaz | bge-m3 | po přeřazení |
|---|---|---|
| mám reflux | #19 | **#8** |
| lék na reflux | #8 | #7 |
| vrací se mi jídlo do krku | #2 | **#1** |

Pomůže, **ale nedá se na něj spolehnout**:

1. **Saturuje.** Skóre 10 dalo skoro všem kandidátům, takže uvnitř
   skupiny nerozlišuje a pořadí zůstává z velké části od bge-m3.
2. **Je nekonzistentní.** Témuž MAALOXovu textu dalo u „mám reflux"
   **10**, u „lék na reflux" **4**.
3. **Je nejdražší z celého testu.** $0,0031 — čtyřnásobek obou
   embedovacích modelů dohromady, protože nano je reasoning model
   a spotřebovalo 7 338 výstupních tokenů na krátký JSON.
4. **Nemůže zachránit, co vektor nevytáhl.** Pracuje jen s top-20.

### Po SESKUPENÍ je to horší, než syrové pořadí ukazovalo

Uživatel v CLI vidí léčiva, ne řádky. Dotaz „mám reflux":

| # | cosine | lék | indikace |
|---|---|---|---|
| 1 | 0,578 | CONTROLOC | léčba příznaků refluxu ✓ |
| 2 | 0,566 | OMEPRAZOL | pálení žáhy ✓ |
| **3** | **0,512** | **AFRIN** | **ucpaný nos** |
| **4** | **0,510** | **PARALEN** | **bolestivá menstruace** |
| **5** | **0,501** | **BISACODYL** | **vyprazdňování** |
| 9 | — | MAALOX | |

**MAALOX je až za čtyřmi naprosto nesouvisejícími léky** — a ty tři
prostřední jsou **nad prahem 0,50**, takže by se v ukázce vedení
opravdu zobrazily.

Navíc: u „lék na reflux" vyhrává uvnitř MAALOXu **špatná indikace** —
„jako součást léčby vředů na žaludku" (0,497), ne ta o refluxu. Věta
o refluxu je tak naředěná, že prohraje i s vlastním sourozencem.

### Závěr celého testu

**Ani cloudový embedding, ani cloudový rerank tenhle případ nespraví.**
Spraví ho rozdělení té jedné věty:

| varianta | cosine na „mám reflux" | pořadí |
|---|---|---|
| celá věta (dnes) | 0,474 | #19 |
| `text-embedding-3-large` | — | #7 |
| nano rerank | — | #8 |
| **fragment „vracení kyselého obsahu…"** | **0,555** | **#4** |

Nejlepší výsledek dá **nejlevnější varianta**: zadarmo, lokálně, bez
cloudu a bez závislosti na externí službě. Úkol je v `todo.md`.

---

## 2026-08-24 — Cloudový embedding MAALOX/reflux NEVYŘEŠÍ. Vinen je text, ne model

Otázka: MAALOX nemá v indikaci slovo „reflux" a bge-m3 ho umístí hluboko.
Zvládne to silnější cloudový model? **Nezvládne.** Skript
`bench_embed_cloud.py` (cache, opakovaný běh nestojí nic).

Pořadí MAALOXu ze **136 indikací** — jen pořadí je srovnatelné, absolutní
cosine mezi modely NE, každý má jinou škálu:

| dotaz | bge-m3 | 3-small | 3-large |
|---|---|---|---|
| mám reflux | #19 | #15 | **#7** |
| lék na reflux | #8 | #8 | **#6** |
| reflux | #14 | **#46** | #10 |
| pálení žáhy | **#1** | #6 | **#1** |
| vrací se mi jídlo do krku | **#2** | #19 | #6 |

### Tři závěry

**1. `text-embedding-3-small` je HORŠÍ než bge-m3** ve 4 z 5 dotazů —
u „reflux" propadne až na #46. Levný cloudový model není upgrade.

**2. `3-large` pomůže jen na odborné slovo.** Na „reflux" zvedne MAALOX
z #19 na #7, ale na **laických parafrázích prohraje**: „vrací se mi
jídlo do krku" #6 proti bge-m3 #2. A ani tak není MAALOX nahoře.

**3. bge-m3 vyhrává na laické češtině** — „pálení žáhy" #1, „vrací se mi
jídlo do krku" #2, v obou lepší nebo stejný jako 3-large. Je
multilingvální, kdežto OpenAI modely jsou anglocentrické. **Pro naši
úlohu (laik píše česky) je volba bge-m3 správná** a měřením potvrzená.

### Skutečná příčina: čtyři příznaky slepené v jedné větě

MAALOX má v indikaci

    léčba potíží spojených s přílišnou kyselinou v žaludku, jako jsou
    pálení žáhy, časté říhání, vracení kyselého obsahu ze žaludku do úst
    a bolest v břiše na lačno

Reflux tam **je** („vracení kyselého obsahu ze žaludku do úst"), jen
utopený mezi třemi dalšími příznaky. Změřeno na bge-m3, dotaz „mám
reflux":

| cosine | text |
|---|---|
| 0,474 | celá věta, jak je dnes v DB |
| 0,462 | pálení žáhy |
| 0,497 | časté říhání |
| **0,555** | **vracení kyselého obsahu ze žaludku do úst** |
| 0,447 | bolest v břiše na lačno |

**Samotný fragment má 0,555 a MAALOX by s ním byl #4 ze 136** — místo
dnešního #19. Tedy **lepší výsledek než `3-large` (#7), zadarmo,
lokálně a beze změny modelu.**

### Co z toho plyne

Je to potřetí tentýž nález (po „laický opis ředí podobnost" a „holé
sloveso nemá ostrý význam"): **embedding průměruje přes celý text, takže
co je slepené dohromady, to se navzájem naředí.**

Oprava nepatří k modelu, ale k extrakci — **rozdělit vícepříznakové
indikace na samostatné položky**, přesně jak se to už dělá u nežádoucích
účinků. `sekce.rozpad_vyctu()` dnes dělí na středníku; tady je oddělovač
„jako jsou … , … a …". Zapsáno do `todo.md`.

**Cena testu:** 4 896 tokenů na model, dohromady **$0,00073**. Embeddingy
jsou jiný produkt než chat a jsou o dva řády levnější — zákaz z
`CLAUDE.md` míří na gpt-4o, ne sem.

---

## 2026-08-24 — Filtr „hrazený" byl v zadání, ale nikdy se neimplementoval

Hlášení: „hrazené antibiotikum" filtr vůbec nezaregistruje a místo toho
se chytí `na předpis". Ověřeno — **filtr `hrazeno` v kódu neexistoval**.

Zadání ho přitom má rozepsaný na třech místech:

- ř. 201 „na predpis ano/ne, **hrazeny ano/ne**"
- ř. 486 návod, jak ho zjistit (`/dlp/v1/lecive-pripravky?typSeznamu=scau`)
- ř. 795 ukázka výstupu routeru obsahuje `"hrazene": null`
- ř. 1116 invariant „dotaz obsahoval *hrazeny* → každý výsledek MUSÍ mít
  hrazeny = true"

V kódu z toho nebylo **nic** — jediná stopa byl docstring
`seznam_kodu()` v `sukl_api.py`, který 'scau' zmiňuje.

**Model si pak poradil, jak uměl:** „hrazené" je nejblíž tomu, co znal,
tedy způsobu výdeje, a namapoval to na `na_predpis`. Není to halucinace
routeru, je to důsledek chybějícího pole ve schématu odpovědi.

### Proč je ta záměna věcně špatně

Hrazenost a způsob výdeje jsou **nezávislé**. V korpusu 22 léčiv:

| na předpis | hrazeno | léčiv |
|---|---|---|
| ne | ne | 10 |
| **ano** | **ne** | **5** |
| ano | ano | 7 |

Pět léčiv je na předpis a hrazených není (ABLYMICO, AMOKSIKLAV,
ACIDUM ASCORBICUM, ADVANTAN, AMEDO). Na dotazu „hrazené antibiotikum"
to je vidět přímo: ABAKTAL hrazený je, AMOKSIKLAV ne.

### Hrazenost není atribut, je to PŘÍSLUŠNOST DO SEZNAMU

Tohle je důvod, proč se na to dá snadno zapomenout. Detail léčiva
z API žádné pole o hrazení nemá. SÚKL ji vyjadřuje tak, že kód je
v seznamu `typSeznamu=scau` — 8 604 kódů, stahuje se zvlášť
a cachuje do `data/hrazene_scau.json`.

    hrazeno = kod_sukl in nacti_hrazene()

### Doplněno napříč celým řetězcem

| místo | co přibylo |
|---|---|
| `init-db.sql` | sloupec `leciva.hrazeno BOOLEAN` + index |
| `naplni_db.py` | `nacti_hrazene()` s cache, plnění při INSERTu |
| `hledani.py` | `Filtr.hrazeno`, podmínka `l.hrazeno = %s`, pole ve `Vysledek` |
| `router.py` | pole v odpovědi, pravidla, **výslovné varování**, že to není `na_predpis` |
| `evaluate.py` | 3 nové invarianty (hrazený / nehrazený / hrazený na předpis) |
| `hledej.py` | řádek `z API SÚKL  na předpis, hrazený pojišťovnou` |

Invarianty filtru **120/120 → 210/210**, ostatní testy beze změny.

### Poučení

**Když filtr ve schématu chybí, model ho nenahlásí — namapuje ho na
nejbližší, který existuje.** Je to tichá chyba: výsledky vypadají
rozumně (nějaká podmnožina se vrátí), jen odpovídají na jinou otázku.
Stojí za to projít zadání proti `Filtr` a ověřit, že tam je všechno.

Zbývající drobnost: u dotazu složeného **jen z filtrů** („hrazený lék na
předpis") nechá router celou větu v `dotaz_text`, místo aby ho nechal
prázdný. Semanticky se pak hledá text bez obsahu. Zapsáno do `todo.md`.

---

## 2026-08-24 — Provedeno: TSV bez identity, dotaz přes OR. A evaluace, která dosud měřila náhodu

Implementace obou závěrů z předchozího zápisu. Plus dvě chyby v samotné
evaluaci, které při tom vypadly.

### 1. `kontext_text` pryč z `search_fts`

`search_fts` je `GENERATED ALWAYS`, takže se nedá změnit ALTERem —
sloupec musí pryč a znovu (GIN index spadne s ním):

    ALTER TABLE leciva_search DROP COLUMN search_fts;
    ALTER TABLE leciva_search ADD COLUMN search_fts tsvector
      GENERATED ALWAYS AS (
        setweight(to_tsvector('czech_unaccent', coalesce(obsah_text,'')), 'A')
      ) STORED;
    CREATE INDEX ON leciva_search USING gin (search_fts);

Změněno i v `init-db.sql`, aby čistá instalace dostala totéž.

| dotaz | před | po |
|---|---|---|
| `paracetamol` | 97 řádků, správný **nakonec** | **2 řádky, oba `atributy`** |
| `paralen` | 32 řádků | **1 řádek** |
| `bolest hlavy` | 17 | 17 (beze změny) |

### 2. Dotaz se převádí na OR

    replace(websearch_to_tsquery('czech_unaccent', %s)::text, '&', '|')

Nad **už zpracovaným** tsquery, ne nad textem uživatele — fráze zůstanou
jako `<->` a nehrozí injektáž.

Výsledek u `paralen 500mg paracetamol`: PARALEN **3,0**, ACIFEIN **1,0**,
ALGIFEN 0,0. Dřív binárně 0,4/0,0.

Nečekaný vedlejší přínos: **u příznakových dotazů se fulltext nově SHODUJE
se sémantikou**, místo aby jí odporoval. „Bolest hlavy" → PARALEN má
fts 3,0 i cosine 0,784, oboje první.

### 3. Evaluace měla nefunkční seed

`test2` volal `random.seed(42)`, ale vzorkuje se přes `ORDER BY random()`
**na straně Postgresu**, kam Python seed nedosáhne. **Každý běh tedy měřil
jiný vzorek** — a to je celé vysvětlení „rozptylu evaluace" zapsaného
dřív dnes. Nebyl to nedeterminismus routeru.

Opraveno přes `setseed()` ve stejném spojení jako výběr. Dva běhy po sobě
teď dají **identická čísla**.

**Poučení: regresní test, který si sám mění vzorek, neměří regrese.**
Rozdíl 57/60 vs 60/60 jsem předtím připsal modelu — bylo to vzorkování.

### 4. Recall test žádal nemožné

Vzorek „kopřivka" má v datech **12 naprosto shodných řádků** — všechny
cosine 1,000 a ts_rank 1,0000. Požadavek „ABLYMICO musí být v top 10"
tedy neměřil řazení, ale to, jak padly shody.

Takové vzorky se teď z metriky **vynechávají** (a je vidět kolik), ne
tiše počítají jako úspěch — to by bylo stejně zavádějící opačným směrem.
Hranice: @5 vynechá text sdílený víc než 5 léčivy, @10 víc než 10.

### Výsledek

```
Invarianty filtru        120/120   100%
Auto-recall @5            47/47    100%
Auto-recall @10           56/56    100%
Negativní (práh 0,50)      7/8      88%
Parafráze                 10/10    100%
```

Z 60 vzorků je měřitelných 47 (@5) a 56 (@10). Práh přeměřen, **zůstává
0,50** — tabulka se nezměnila.

Jediný neúspěch je pořád `něco na popáleniny` → kopřivka 0,535.

---

## 2026-08-24 — Fulltext řadí identitu NAOPAK. Viník není text sekcí, ale `kontext_text`

Podnět: „v TSV by měly být jen základní údaje o léku z API, a to formou
OR; nejsem si jistý, jestli slova ze sekcí fulltext neředí."

Ředí — a je to horší, než to vypadalo. Dotaz **`paracetamol`** dnes:

| ts_rank | sekce | řádek |
|---|---|---|
| **1,0000** | nezadouci_ucinky | ACIFEIN — nevolnost (nauzea) |
| 1,0000 | indikace | PARALEN — zvýšená tělesná teplota |
| 1,0000 | nezadouci_ucinky | ACIFEIN — únava |
| … | | (celkem 97 řádků z 994) |
| **0,4000** | atributy | PARALEN, 500MG, PARACETAMOL ← **správná odpověď** |

**Fulltext dá správné odpovědi NEJHORŠÍ rank ze všech.** V RRF tedy
aktivně tlačí správný výsledek dolů.

### Příčina

`search_fts` = `kontext_text`(A=1,0) + `obsah_text`(B=0,4), přičemž

- `kontext_text` = „PARALEN, 500MG, PARACETAMOL" je na **každém ze 32
  řádků** PARALENU → identita se rozstříkne po celém léku ve váze A
- řádek `atributy` má `kontext_text` **prázdný** (schválně, aby se
  identita neopakovala dvakrát) → jeho shoda spadne do váhy B

Takže vážení funguje přesně obráceně, než mělo. Dřívější zápis
„váha A se u atributů neuplatňuje" byl jen půlka pravdy — druhá půlka
je, že se uplatňuje **všude jinde**, kde nemá.

### Oprava je chirurgická: vyhodit `kontext_text` z FTS

Změřeno na celém korpusu:

| dotaz | dnes | bez `kontext_text` |
|---|---|---|
| `paracetamol` | 97 řádků | **2 řádky, oba `atributy`** |
| `paralen` | 32 řádků | **1 řádek, `atributy`** |
| `bolest hlavy` | 17 | **17 (beze změny)** |
| `kopřivka` | 16 | **16 (beze změny)** |

**Identitní dotazy se spraví úplně, příznakové se nezmění vůbec.**
Text sekcí tedy z fulltextu vyhazovat NENÍ potřeba — problém nikdy
nebyl v něm.

### OR místo AND dává odstupňovaný rank

Druhá půlka podnětu, nezávislá na první. Dnes `websearch_to_tsquery`
slova **slučuje přes AND**, takže u atributů vyjde rank binárně 0,4/0,0
a řadit se podle něj nedá. S OR nad identitou:

    to_tsquery('czech_unaccent', 'paralen | 500mg | paracetamol')

| rank | lék |
|---|---|
| **3,0000** | PARALEN (trefil všechna tři slova) |
| **1,0000** | ACIFEIN (trefil jen paracetamol) |

Pořadí je věcně správné — PARALEN je čistý paracetamol 500 mg, ACIFEIN
kombinace tří látek. **S AND by ACIFEIN vypadl úplně**, přestože
paracetamol obsahuje.

### K vyšší váze fulltextu v RRF

Platí, ale ne plošně. Váha v RRF je **globální**, kdežto spolehlivost
fulltextu je **různá podle typu dotazu**:

| typ dotazu | co má rozhodovat |
|---|---|
| `paralen`, `paracetamol`, ATC, kód SÚKL | fulltext / filtr — řízená hodnota |
| `bolest břicha`, `nemůžu spát` | sémantika — laik použije jiná slova |

Router přitom typ dotazu **už zná** — `Filtr.je_presny()` vrací True,
když je ve filtru název, kód, látka, síla nebo ATC. Nabízí se tedy
**váhu volit podle toho příznaku**, ne ji zvedat natvrdo. Je to stejná
logika, podle které se u přesných filtrů už dnes vypíná práh.

---

## 2026-08-24 — Fulltext dotazy SLUČUJE (AND), takže u vět skoro nikdy nechytí

Měřeno kvůli úkolu „v TSV je toho moc". Ukázalo se něco jinýho, než se
čekalo. `websearch_to_tsquery` spojuje slova operátorem **AND**, takže
každé další slovo výsledek **zužuje**:

| dotaz | řádků z 994 |
|---|---|
| `bolest` | 112 |
| `bolest hlavy` | 33 |
| `zánět jater` | 16 |
| `náhlý zánět jater` | **1** |
| `lék na bolest` | **2** |

Z toho plyne, že **u víceslovných laických dotazů fulltext prakticky
nepřispívá** – množina je prázdná nebo jednoprvková a celou práci
odvede sémantika. Fulltext je užitečný na **jednoslovné přesné dotazy**
(název léku, účinná látka, kód SÚKL), přesně jak se ukázalo u atributů.

### Stop slova nakonec NEJSOU hlavní problém

Samostatně chytnou hodně řádků (`'v'` 331, `'a'` 319, `'nebo'` 258,
`'na'` 232 z 994), takže to vypadá zle. Jenže kvůli AND se to projeví
jen tehdy, když je stop slovo **v dotazu** – a tam ho router už dávno
odřezává jako vatu. Kdyby se tam dostalo, způsobilo by to
**falešně NEGATIVNÍ** výsledek (zúžení), ne falešně pozitivní.

**Závěr: úklid TSV má menší dopad, než se zdálo, a nese riziko.** Česká
stop-slovníková konfigurace by znamenala nasadit `czech.stop` do
`$SHAREDIR/tsearch_data/` v kontejneru a přepočítat `GENERATED` sloupec
u všech 994 řádků. Před ukázkou vedení se to nevyplatí. Úkol zůstává
v `todo.md` i s tímhle měřením, ale **priorita klesla**.

---

## 2026-08-24 — Práh zůstává 0,50, ale je to teď kompromis (dřív nebyl)

Po zpřesnění slovníku se laické tvary **zkrátily**, a tím vzrostly
podobnosti napříč korpusem – přesně podle dřívějšího zjištění, že delší
opis význam ředí. Vedlejší efekt: jeden negativní dotaz prolezl.

    'něco na popáleniny' -> DITHIADEN (0,535) 'kopřivka'

Popáleniny v datech nejsou (ověřeno `overit_negativni()`), ale kopřivka
je taky kožní potíž a po zkrácení na holý tvar má dost vysokou podobnost.

Přeměřený práh:

|  práh | parafráze | negativní |
|---|---|---|
| 0,45 | 10/10 | 2/8 |
| **0,50** | **10/10** | **7/8** |
| 0,55 | 9/10 | 8/8 |
| 0,60 | 6/10 | 8/8 |

**Zůstává 0,50.** Rozhodl konkrétní případ: při 0,55 vypadne
**„pálí mě žáha" (0,542)** – tedy přesně ten dotaz, kvůli kterému se
řešil CONTROLOC a reflux. Vyměnit reálnou laickou otázku za jeden
hraniční falešný poplach se nevyplatí.

Dřív bylo 0,50 „zadarmo" (8/8 i 10/10). **Teď je to vědomý kompromis
a je potřeba ho takhle prezentovat**, ne jako bezchybné číslo.

### Vedlejší zjištění: evaluace sama má rozptyl

Dva běhy `evaluate.py` nad **týmiž daty** daly Auto-recall @5 jednou
**60/60**, podruhé **57/60**. Testy 1–3 jdou přes router, a ten je
generativní model, takže není deterministický.

**Poučení: jednotlivý běh evaluace nestačí na posouzení změny o pár
procent.** Rozdíl 57 vs. 60 je v šumu. Rozhodovat se dá až podle
opakovaného běhu nebo podle testů, které model neobsahují
(invarianty filtru, TEST 0).

---

## 2026-08-24 — Slovník dotažen: ruční číselník, hygiena klíčů, aplikace bez modelu

Dodělání toho, co 21.8. vyšlo najevo. Čtyři změny, všechny deterministické
(žádný model se nepouštěl).

### 1. Hygiena klíčů (`slovnik.klic()`)

Data měla klíče, na které se číselník **už nikdy netrefí**:

| vadný klíč | proč |
|---|---|
| `akutní hepatitida.` | koncová tečka |
| `léčba žaludečních vředů` | předpona „léčba" |
| `Při vředech na kůži.` | zbytek větného rámce |

`klic()` sjednotí malá písmena, zahodí koncovou interpunkci a odřízne
předpony „léčba / léčení / terapie / při". Používá se při **stavbě
i vyhledání**, jinak by se klíče minuly. Sloučením se 67 nových termínů
smrsklo na **+50** – zbytek splynul s tím, co už ve slovníku bylo
(např. `kopřivka` tam byla 12× z nežádoucích účinků).

**POZOR:** předpony musí být v promptu i v kódu **s diakritikou**. Napsal
jsem je nejdřív v ASCII (`"lecba "`) a `léčba žaludečních vředů` se
neodřízlo – tiše, bez chyby.

### 2. Slovník umí oba tvary položek (`slovnik.TVARY`)

    nezadouci_ucinky        {"ucinek": ..., "ucinek_laicky": ...}
    indikace/kontraindikace {"doslovne": ..., "laicky": ...}

Do 24.8. uměl `uplatni()` jen první tvar, proto indikace nikdo nehlídal.
V `extrakce.py` se navíc volal jen uvnitř `if nazev_sekce ==
"nezadouci_ucinky"` – přesunuto na `SEKCE_S_LAICKYM_TVAREM`.

### 3. Ruční číselník: 67 dvojic projitých člověkem

`slovnik_rucni.json` měl **1 položku**, teď má **67**. Opravovaly se dvě
třídy vad:

**Věcné chyby modelu** – nejhorší byla `akutní pankarditidy` →
„čerstvé záněty srdeční stěny a **kloubů kolem srdce**". Pankarditida je
zánět všech vrstev srdce, žádné klouby v tom nejsou. Dál `neuralgie` →
„bolest podél nervu" (a při jiném běhu „nervové bolesti"), `zánětů
sliznice jícnu` → „zánětu **stěny** jícnů" (sliznice ≠ stěna).

**Zbytky větného rámce** – „Při obyčejných akné (trvalé pupínky).",
„Při nemoci známé jako růžovka.". Do číselníku patří **holý tvar
v 1. pádě**, protože se skládá do vět až při výpisu. Řeší to
`ocisti_laicky()`.

### 4. Aplikace na hotová data BEZ modelu

Rozšířen `ocisti_json.py` (ten je právě na deterministické čištění).
Přeextrahování modelem by trvalo hodiny a podle dřívějšího měření by
chyby stejně neopravilo, jen přesunulo.

    uv run python ocisti_json.py --zapis     # 77 položek opraveno

### Výsledek

| sekce | pokrytí 21.8. | pokrytí 24.8. |
|---|---|---|
| nezadouci_ucinky | 410 (100 %) | 410 (100 %) |
| indikace | 4 (3 %) | **45 (39 %)** |
| kontraindikace | 1 (1 %) | **26 (26 %)** |

Zbytek jsou dlouhé věty, které do číselníku **nepatří** – neopakují se,
klíč by se na ně už netrefil. Slovník má 476 dvojic, z toho 67 ručně
ověřených.

Na dotaz „bolest nervů" vrací PARALEN „bolest nervů (neuralgie)"
s podobností **0,838**.

---

## 2026-08-24 — `naplni_db.py` bez `--znovu` TIŠE ZDVOJÍ data

Past, do které jsem spadl. Po opravě slovníku jsem pustil:

    uv run python naplni_db.py        # BEZ --znovu

Skript vypsal správně vypadající `radku ze sekci 972` a skončil bez
chyby. Jenže `leciva_search` **nemá unikátní klíč přes obsah**, takže
se 972 řádků **přisypalo** k těm, co tam už byly.

Poznalo se to až na evaluaci, a ne hned – čísla vypadala jako vada dat:

    Frekvence namapovaná    884/1308      (mělo být 442/654)
    Čísla stránek          1944/1944      (mělo být 972/972)
    Invarianty filtru       134/134       (mělo být 120/120)

Všechno přesně **dvojnásobek**. Varovný signál byl už dřív ve výpisu
embeddingů (`kontrola | 1988/1988`), ale prošel bez povšimnutí.

**Oprava:** `naplni_db.py` bez `--znovu` teď skončí s chybou, když
`leciva_search` už řádky má:

    CHYBA: leciva_search uz ma 994 radku. Bez --znovu by se data
           ZDVOJILA. Pouzij:  uv run python naplni_db.py --znovu

**Poučení: skript, který se pouští opakovaně, musí být idempotentní,
nebo to musí odmítnout.** Tichý přírůstek je horší než pád – data
vypadají v pořádku a chyba se projeví až o dva kroky dál, kde už ji
nikdo nespojí s příčinou.

Správné pořadí po změně dat:

    uv run python ocisti_json.py --zapis
    uv run python naplni_db.py --znovu
    uv run python vytvor_embeddingy.py
    uv run python evaluate.py

---

## 2026-08-21 — Slovník sbírá JEN z nežádoucích účinků; indikace jsou bez dozoru

Postřeh: „bolest podél nervu" jako laický tvar **neuralgie** je špatně
a ve slovníku ten termín není. Ověřeno — a příčina je systémová.

`postav_slovnik.py::posbirej()` prochází **jen** `nezadouci_ucinky.json`
a čte jen `ucinek` / `ucinek_laicky`:

    for f in sorted(LECIVA_DIR.glob("*/json/nezadouci_ucinky.json")):

Když se **20.8. sjednotil tvar indikací a kontraindikací** na
`{doslovne, laicky}`, sběrač slovníku se s tím nerozšířil. Vzniklo
241 řádků (136 indikací + 105 kontraindikací), jejichž laický tvar
**nikdo nekontroluje a při každém běhu se generuje znovu jinak**.

| sekce | unikátních termínů | ve slovníku |
|---|---|---|
| nezadouci_ucinky | 410 | **410 (100 %)** |
| indikace | 113 | **4 (3 %)** |
| kontraindikace | 99 | **1 (1 %)** |

Slovník tedy funguje bezvadně — jen na třetině dat.

### Slovník se ale nevyplatí na všechno

Číselník má smysl u termínu, který se OPAKUJE. Změřeno:

| sekce | do 3 slov | prům. délka | opakuje se u víc léčiv |
|---|---|---|---|
| nezadouci_ucinky | 74 % | 3,0 slova | **24 %** |
| indikace | 38 % | 8,9 slova | 11 % |
| kontraindikace | 24 % | 9,5 slova | **1 %** |

Nežádoucí účinky jsou krátké termíny („trombocytopenie", „kopřivka") –
ideální pro číselník. Indikace jsou často celé věty:

    „Přípravek Ablymico je indikován jako doplňková léčba k dietě
     se sníženým obsahem kalorií a zvýšené fyzické aktivitě…"

Klíč slovníku na takovou větu se **už nikdy netrefí** (opakování 1–11 %).
Zato mezi indikacemi jsou i pravé krátké termíny, přesně ty problémové:
`neuralgie`, `kopřivka`, `bronchiektázie`, `mukoviscidóza`, `laryngitida`.

**Závěr: rozhodovat podle TVARU termínu, ne podle sekce.** Do slovníku
patří termíny do ~3 slov ze všech sekcí – to je 43 (indikace) + 24
(kontraindikace) = **67 nových položek**, ne 207. Dlouhé věty ať si
model překládá pokaždé, číselník by je stejně nezachytil.

### Poznámka k přesunu generování do cloudu

Zvažuje se generovat nové dvojice přes `gpt-5-nano` (lepší čeština,
krátké úlohy, levné). Věcně to sedí, ale **naráží to na premisu projektu**
– „všechno běží lokálně, data neopouštějí síť". SPC jsou veřejné
dokumenty SÚKL, takže riziko je malé, ale pro ukázku vedení by se tvrzení
o plné lokálnosti muselo upřesnit. Je to rozhodnutí, ne detail.

Pokud se to udělá, musí zůstat zachované, že **kontroluje JINÝ model než
generuje** (dnes generuje qwen3.5:122b, kontroluje gemma4:31b).

---

## 2026-08-21 — Co přesně jde do vektoru a co do fulltextu (ověřeno na datech)

Oba hledací sloupce jsou v `leciva_search` a **každý se plní z něčeho
jiného**. Ověřeno dotazem do živé databáze, ne z DDL.

| sloupec | typ | zdroj | čím se plní |
|---|---|---|---|
| `embedding` | `vector(1024)` | **jen `obsah_text`** | `vytvor_embeddingy.py` (bge-m3) |
| `search_fts` | `tsvector` | `kontext_text` **+** `obsah_text` | `GENERATED ALWAYS ... STORED` |

Fulltext se tedy **nikdy neplní ručně** – Postgres ho přepočítá sám při
každém zápisu. Embedding se naopak musí přegenerovat skriptem.

    search_fts tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('czech_unaccent', coalesce(kontext_text,'')), 'A') ||
        setweight(to_tsvector('czech_unaccent', coalesce(obsah_text,'')),  'B')
    ) STORED

### Skutečné řádky ze všech pěti sekcí

**atributy** (PARALEN)

    kontext_text  NULL
    obsah_text    'PARALEN, 500MG, TBL NOB, PARACETAMOL, 0254048'
    -> vektor     z obsah_text
    -> fts        '0254048':6B '500mg':2B 'nob':4B 'paracetamol':5B
                  'paralen':1B 'tbl':3B

**indikace** (PARALEN)

    kontext_text  'PARALEN, 500MG, PARACETAMOL'
    obsah_text    'bolest podél nervu (neuralgie)'
    -> vektor     z 'bolest podél nervu (neuralgie)'   <- BEZ názvu léku
    -> fts        '500mg':2A 'paracetamol':3A 'paralen':1A
                  'bolest':4B 'nervu':6B 'neuralgie':7B 'podel':5B

**nezadouci_ucinky** (PARALEN)

    kontext_text  'PARALEN, 500MG, PARACETAMOL'
    obsah_text    'nízký počet krevních destiček (trombocytopenie)'
    -> fts        '500mg':2A 'paracetamol':3A 'paralen':1A
                  'desticek':7B 'krevnich':6B 'nizky':4B 'pocet':5B
                  'trombocytopenie':8B

**kontraindikace** (PARALEN)

    obsah_text    'Alergie na hlavní účinnou složku nebo jakoukoli další látku v léku.'
    -> fts        '500mg':2A 'paracetamol':3A 'paralen':1A 'alergie':4B
                  'dalsi':11B 'hlavni':6B 'jakoukoli':10B 'latku':12B
                  'leku':14B 'na':5B 'nebo':9B 'slozku':8B 'ucinnou':7B 'v':13B

**davkovani** (PARALEN)

    obsah_text    'děti 6–12 let (váha 20–25 kg) 250 mg neuváděno'
    -> fts        '500mg':2A 'paracetamol':3A 'paralen':1A '12':6B '20':9B
                  '25':10B '250':12B '6':5B 'deti':4B 'kg':11B 'let':7B
                  'mg':13B 'neuvadeno':14B 'vaha':8B

### Tři věci, které z toho koukají

**1. Vektor NEVÍ, ke kterému léku patří.** Řádek indikace se embeduje jako
holé „bolest podél nervu (neuralgie)" – slovo PARALEN v něm není. Je to
schválně: identita léku je v každém ze 136 indikačních řádků stejná, takže
by fungovala jako konstanta přičtená ke všem podobnostem a rozdíly by
stlačila (tentýž důvod jako u slova „léčba"). **Lék přiřazuje FILTR,
ne vektor.** Fulltext to naopak ví, protože má `kontext_text` ve váze A.

**2. `czech_unaccent` je `simple` + unaccent, tedy BEZ stemmingu
a BEZ stop slov.** Vidět na kontraindikaci: indexuje se i `'na'`, `'nebo'`,
`'v'`. Důsledky:
- „nervu" se **nespojí** s „nerv" ani „nervy" – fulltext hledá tvar, ne
  základ slova. Na skloňovanou češtinu je to slabé, proto nese jen 20 %.
- diakritika se srovná („podél" → `podel`), takže „kuze" najde „kůže"

**3. U `atributy` je `kontext_text` prázdný u VŠECH 22 řádků**, takže
váha A se tam neuplatní a všechny shody mají ts_rank 0,4. Doplňuje to
dřívější zápis o řazení atributů konkrétním číslem.

| sekce | řádků | z toho s `kontext_text` | s embeddingem |
|---|---|---|---|
| atributy | 22 | **0** | 22 |
| davkovani | 77 | 77 | 77 |
| indikace | 136 | 136 | 136 |
| kontraindikace | 105 | 105 | 105 |
| nezadouci_ucinky | 654 | 654 | 654 |

Filtrační sloupce (`sekce`, `frekvence`, `organovy_system`,
`sekce_atributy`, `strana_pdf`) **nejsou ani v jednom** z hledacích
sloupců – jsou to hodnoty do `WHERE`, ne text k hledání.

---

## 2026-08-21 — „Lék + příznak": směr se z dotazu poznat NEDÁ, rozhodnout musí data

Návrh zněl: když uživatel napíše lék a k němu potíž („paralen bolesti
břicha"), nemá to router poslat na nežádoucí účinky? Natvrdo **ne** –
rozbilo by to opačný případ. Změřeno hledáním v obou sekcích naráz:

| dotaz | vítěz | sekce |
|---|---|---|
| ACC + bolest břicha | 0,789 „bolest břicha" | **nezadouci_ucinky** |
| Paralen + bolest hlavy | 0,784 „bolest hlavy" | **indikace** |
| Paralen + bolest břicha | 0,520 „bolestivé měsíčky" | nic správného |

**Stejný tvar věty, opačná sekce.** Rozhoduje, co je o tom léku
v datech, ne jak je dotaz napsaný. Paralen bolest hlavy léčí, ACC
bolest břicha způsobuje – z formulace to nepozná ani člověk.

### Řešení: obě sekce a ať rozhodne podobnost

Do promptu routeru přidána výjimka z pravidla „příznak je vždy
indikace": **když je jmenován KONKRÉTNÍ lék a směr není řečený**, jdou
do sekce obě a jistota je „nizka". Filtr na název zúží výběr na jeden
lék, takže obě sekce jsou pár desítek položek a správnou vybere
podobnost sama.

Bez léku („bolí mě břicho") platí původní pravidlo dál – je to indikace,
člověk hledá, co si vzít. Ověřeno, že se nezměnilo.

### Přitom se našla nekonzistence prompt vs. kód

Prompt říká: *„Když si nejsi jistý sekcí, dej jistota 'nizka' a do sekce
dej VŠECHNY, které přicházejí v úvahu."* Kód ale hned nato dělal:

    if jistota == "nizka":
        sekce = None          # a výčet je pryč

Model tedy poslušně vyjmenoval kandidáty a **kód je zahodil** a hledal
ve všech pěti sekcích včetně dávkování. Opraveno: výčet **dvou a víc**
sekcí se respektuje, na `None` se padá jen u jediné sekce s nízkou
jistotou (to si protiřečí samo o sobě).

**Poučení: když se prompt na něco ptá, kód to nesmí zahodit.** Jinak se
platí za tokeny navíc a ještě se hledá šíř, než je potřeba.

---

## 2026-08-21 — Laický opis ŘEDÍ podobnost: správná odpověď skončí pod špatnou

Vypadlo to z předchozího měření. Dotaz **„bolest břicha"**, čisté cosine
na bge-m3:

| cosine | text |
|---|---|
| **0,789** | bolest břicha |
| **0,666** | břicho |
| 0,609 | bolest hlavy ← **jiná část těla** |
| 0,562 | nadýmání v břiše |
| **0,531** | bolest nebo nepohodlí v břiše (Bolest břicha a břišní diskomfort) |

Poslední řádek je **věcně správná odpověď** CONTROLOCu – a skončí
**pod „bolestí hlavy"**. Přitom holé „bolest břicha" má 0,789.

**Příčina je délka.** Embedding průměruje přes celý text, takže „nepohodlí",
„břišní" a „diskomfort" jádro významu naředí. Krátká „bolest hlavy"
mezitím těží ze sdíleného slova „bolest".

Je to **daň za laicizaci**: text se dělal čitelný pro laika, a tím
zdelšil a rozmělnil. Čím delší laický opis, tím hůř dohledatelný.
Souvisí s tím, proč se CONTROLOC nenajde na „pálení žáhy" – jeho laický
text říká „návrat kyseliny".

Neopraveno, jen změřeno. Možnosti k prověření (vstup pro test C):

1. embedovat **odborný termín zvlášť** od laického opisu (dva řádky,
   ne jeden dlouhý)
2. embedovat **zkrácený kanonický tvar** a laický text jen zobrazovat
3. rozšířit dotaz přes **slovník pojmů** (už postaven, 426 dvojic)

Varianta 1 vypadá nejlevněji – data pro ni jsou, JSON má `ucinek`
i `ucinek_laicky` odděleně.

---

## 2026-08-21 — Router zahodil zápor a „spát" pak přitáhlo závratě

Dotaz **„nemůžu po prášcích spát"** vrátil na 2. a 3. místě **závratě**
s podobností 0,590. Vypadalo to na chybu embedovacího modelu. Nebyla.

Router z dotazu udělal `dotaz_text: 'spát'` – **zahodil zápor**, který
nesl celý význam. Změřeno nad sekcí `nezadouci_ucinky`:

| co šlo do vektoru | 1. výsledek | 2. výsledek |
|---|---|---|
| `spát` ← co router poslal | nespavost 0,649 | **závratě 0,590** |
| `nemůžu spát` | nespavost 0,710 | noční můry 0,647 |
| `nespavost` | nespavost **1,000** | nespavost (insomnie) 0,820 |
| `poruchy spánku` | poruchy spánku 0,744 | nespavost 0,713 |

**Holé sloveso nemá ostrý význam.** „Spát" je podobné spoustě
neurologických a psychiatrických příznaků naráz, takže se všechno slije
do pásma 0,55–0,65 a rozdíl mezi správnou a špatnou odpovědí zmizí.
Se zachovaným záporem je odstup 0,710 vs 0,647, s odborným termínem
dokonce 1,000 vs 0,820.

Správná odpověď byla po celou dobu **první** – hledání nebylo špatně.
Špatně byl **odstup**: šum seděl 0,06 pod ní, takže to na výpisu vypadalo
jako nerozhodnuté.

### Oprava v promptu routeru

Přibylo výslovné pravidlo, že zápor je součást příznaku:

    "nemůžu po prášcích spát"  -> dotaz_text: "nemůžu spát"   (NE "spát")
    "nemůžu dýchat nosem"      -> dotaz_text: "nemůžu dýchat nosem"

a kontrola pro model: **dotaz_text musí dávat smysl sám o sobě.** Když
se na něj podíváš bez původní věty a nepoznáš, co člověk hledá, ořezal
jsi moc.

### Ořezávání dotazu je nůž na obě strany

Je to **druhá půlka** problému se slovem „léčba" o den dřív. Tam se
ořezalo **málo** a slovo z 33 ze 136 indikací navléklo podobnost na
všechno. Tady se ořezalo **moc**.

| chyba | projev | příklad |
|---|---|---|
| ořezáno málo | všechno si je podobné | „léčba roztroušené sklerózy" → 0,586 na štítnou žlázu |
| ořezáno moc | význam zmizí, šum vyplave | „spát" → závratě 0,590 |

Dřív naměřeno totéž u „Bolest břicha" → „břicho" (0,678 → 0,492).
**Vyhazovat se smí jen slovo, které je v datech skoro všude
(„léčba", „přípravek"). Nikdy slovo, které nese význam – a zápor
význam nese.**

### Vedle toho opravena chyba: bge-m3 nešel předehřát

Kontrola modelů při startu hlásila:

    nepodařilo se načíst bge-m3: 400 Client Error: Bad Request
    for url: http://10.6.38.10:11434/api/generate

`nahrej()` mířila na `/api/generate`, což **embedovací model neumí**
a vrací 400. `bge-m3` se tak nikdy nepředehřál a platil se za něj první
dotaz. Opraveno: při 400 se spadne na `/api/embed`.

---

## 2026-08-20 — Fulltext u atributů neumí ŘADIT, umí jen ano/ne

Otázka zněla: nešlo by u dotazu na účinnou látku („paracetamol") vyhodit
sémantiku a nechat rozhodnout fulltext? Vypadá to logicky – je to řízená
hodnota, fulltext ji najde přesně.

**Změřeno, že by to nepomohlo.** `ts_rank_cd` vrací u atributů jen dvě
hodnoty:

| lék | rank „paracetamol" | rank „kofein" |
|---|---|---|
| ACIFEIN | 0,40000 | 0,40000 |
| PARALEN | 0,40000 | 0,00000 |
| ACYLCOFFIN | 0,00000 | 0,40000 |

Buď **0,4 nebo 0,0**, nic mezi tím. `ts_rank_cd` u jednoho slova s jedním
výskytem vrátí prostě váhu třídy, a `obsah_text` má váhu **B = 0,4**.

Řazení podle fulltextu by tedy dalo **náhodné pořadí** – to „#1 vs #2"
ve výpisu je jen pořadí řádků v databázi mezi shodnými hodnotami.

### Každá ze tří vrstev umí něco jiného

| | umí | neumí |
|---|---|---|
| **filtr** | vybrat správnou množinu | seřadit ji |
| **fulltext** | potvrdit shodu (0,4 / 0,0) | seřadit ji |
| **sémantika** | seřadit uvnitř množiny | oddělit správné od špatných |

U dotazu „paracetamol" dá sémantika PARALEN (0,611) před ACIFEIN (0,548),
což je věcně lepší – PARALEN je čistý paracetamol, ACIFEIN je kombinace
tří látek. Sémantika tam tedy **k něčemu je**, jen k něčemu jinému, než
se čekalo.

Proto se u přesných filtrů vypíná **práh**, ne sémantika. Práh byl to
jediné, co tam škodilo (viz zápis o `Filtr.je_presny()`).

### Nedodělek: váha A se u atributů neuplatňuje

`search_fts` má dvě váhy:

    setweight(kontext_text, 'A')   -- identita léku, váha 1,0
    setweight(obsah_text,  'B')   -- obsah, váha 0,4

Jenže **řádky `atributy` mají `kontext_text` prázdný** (schválně, aby se
identita neopakovala dvakrát v témže řádku). Váha A se tak nikde
neuplatní a všechny shody mají 0,4.

Návrh A/B váhy má, ale u atributů nic nedělají. Stojí za prověření,
jestli to nechat, nebo identitu do `kontext_text` doplnit – dotaz na
název léku by pak měl 2,5× vyšší rank než shoda v textu jiné sekce.

### Do CLI přibyla surová hodnota ts_rank

Bez ní nešlo posoudit, co vlastně rozhodlo:

    sémantika  0.611 cosine     pořadí #1
    fulltext   0.4000 ts_rank    pořadí #2

Právě z toho výpisu byl ten problém vidět na první pohled.

---

## 2026-08-20 — U atributů z API sémantika nerozlišuje nic (a práh škodí)

Postřeh uživatele: když router u dotazu „volně prodejný lék
s paracetamolem" vytáhne filtr `účinná látka = paracetamol`, je **výběr
už hotový**. Účinná látka, název, síla, ATC a kód SÚKL jsou řízené
hodnoty z API – buď sedí, nebo ne. Sémantika k tomu nemá co přidat.

**Změřeno** na dotazu „paracetamol" nad sekcí `atributy`, bez filtru
na látku:

| cosine | řádek | správně? |
|---|---|---|
| 0,611 | PARALEN … **PARACETAMOL** | ano |
| 0,548 | ACIFEIN … **PARACETAMOL** | ano |
| 0,517 | ABAKTAL … DIHYDRÁT PEFLOXACIN-MESILÁTU | **ne** |
| 0,489 | OMEPRAZOL … OMEPRAZOL | **ne** |
| 0,483 | ACC … ACETYLCYSTEIN | **ne** |

Mezi poslední správnou (0,548) a první špatnou (0,517) je rozdíl **0,031**
a všechny špatné sedí v hustém pásmu těsně pod. **Vektor nerozliší
paracetamol od pefloxacinu** – obojí je pro něj „název léčiva".

### Práh tam aktivně škodí

Při prahu 0,55 by vypadl **ACIFEIN, přestože paracetamol obsahuje**.
Práh měří podobnost u něčeho, kde podobnost nemá význam.

**Oprava:** `Filtr.je_presny()` – když filtr obsahuje řízenou hodnotu
(název, kód SÚKL, účinná látka, síla, ATC), **práh se neuplatní**.
Výběr už proběhl podle přesné hodnoty a cosine by ho jen kazil.

Ověřeno: s přesným filtrem projdou obě správné odpovědi i při prahu 0,65.
U filtru jen na sekci se práh dál uplatňuje normálně.

### Obecněji

Rozděluje to data na dva druhy a každý chce jiný nástroj:

| druh | příklad | čím hledat |
|---|---|---|
| **řízené hodnoty z API** | název, látka, síla, ATC, kód | filtr / fulltext – přesně |
| **volný text ze SPC** | indikace, nežádoucí účinky | sémantika – na parafráze |

Sémantika je nutná tam, kde uživatel použije jiná slova než dokument.
U atributů se ale žádná parafráze nekoná – „paracetamol" je paracetamol.

---

## 2026-08-20 — Slovo „léčba" v dotazu navléká podobnost na všechno

Negativní dotaz „léčba roztroušené sklerózy" vrátil ALTHYXIN s podobností
**0,586** – tedy nad prahem – s textem „Léčba nezhoubného zvětšení štítné
žlázy".

Příčina: router tentokrát nechal v `dotaz_text` **celou větu** včetně
slova „léčba". A „léčba" je v **33 ze 136 indikací**, takže vektor pak
měří podobnost hlavně na něm, ne na nemoci.

**Oprava:** do promptu routeru přidán výslovný pokyn vynechat i „léčba",
„léčení", „terapie", „přípravek", „prostředek".

| dotaz | dotaz_text | top cosine |
|---|---|---|
| „léčba roztroušené sklerózy" | před: celá věta | 0,586 |
| | po: „roztroušená skleróza" | **0,475** |
| „léčba bolesti hlavy" | „bolesti hlavy" | 0,774 |

**Poučení: do dotazu pro vektor nesmí jít slovo, které je v datech skoro
všude.** Chová se jako konstanta přičtená ke všem podobnostem a rozdíly
mezi nimi stlačí. Je to stejný problém jako u filtračních sloupců, které
proto do `obsah_text` nedáváme.

---

## 2026-08-20 — „Skript nic nedělá": Ollama odloží 87GB model po 5 minutách

Projev: `hledej.py` se zdánlivě zasekne a `ollama ps` neukazuje **žádný**
model. Po dlouhé době doběhne správně.

**Není to chyba skriptu.** Ollama model po ~5 minutách nečinnosti odloží
z paměti (výchozí `keep_alive`). Další dotaz ho musí načíst znovu –
a qwen3.5:122b má **87,4 GB**.

| stav | doba dotazu |
|---|---|
| model načtený | **5–6 s** |
| model odložený | desítky sekund až minuty (načtení 87 GB z disku) |

### Dvě opravy

**1. `keep_alive: "2h"` u každého požadavku** (`ollama_client.KEEP_ALIVE`).
Posílá se v těle požadavku, takže to nevyžaduje zásah do konfigurace
serveru (`OLLAMA_KEEP_ALIVE`) – což je podstatné, protože na DGX nemusíme
mít práva na systemd.

**2. Načítání se ZOBRAZUJE.** Tohle byla hlavně chyba v komunikaci se
uživatelem: skript mlčel a vypadal jako zaseknutý. Ollama přitom vrací
`load_duration` v každé odpovědi – jen se nikde neukazoval:

    POZN: model se musel načíst z disku (43.2 s). Další dotaz už bude rychlý.

Přidán příznak `Metriky.nacital_se` (práh 1 s) a výpis v CLI.

**Poučení: když operace trvá dlouho, musí být vidět PROČ.** Mlčící skript
vypadá jako rozbitý skript a vede k hledání chyby tam, kde není.

### Co za to platíme

`keep_alive: 2h` drží **87 GB paměti obsazených**. DGX má 128 GB
sjednocené paměti, takže na jiné modely zbývá málo. Když se souběžně pustí
extrakce s jiným modelem nebo DGX používá někdo další, může to vadit –
pak dává smysl kratší doba (30 min).

### Nedodělek: předehřátí před demem

První dotaz po delší pauze bude vždycky pomalý. Před ukázkou vedení se
model má nahrát dopředu prázdným požadavkem, aby první ostrý dotaz nebyl
ten, který trvá minutu. Zatím neimplementováno (návrh: `hledej.py --nahrej`).

---

## 2026-08-20 — Účinné látky se ukládaly jako KÓDY, ne názvy

Dotaz „volně prodejný lék s paracetamolem" nevrátil nic, přestože router
sestavil filtr **správně** (`sekce=atributy; volně prodejné; účinná látka
„paracetamol"`).

**Příčina byla v datech.** API SÚKL vrací u léčiva jen kódy látek:

    "leciveLatky": [1064]

a ukládaly se tak, jak přišly:

    PARALEN | ucinne_latky = 1064
    atributy | "PARALEN, 500MG, TBL NOB, 1064, 0254048"

Filtr `ucinna_latka ILIKE '%paracetamol%'` tedy hledal v poli, kde bylo
`1064`. **Rozbíjelo to i vyhledávání** – kdo napsal „paracetamol", nemohl
PARALEN najít ani sémanticky, protože ta látka v textu vůbec nebyla.

**Oprava:** SÚKL má číselník `/dlp/v1/ciselnik-latky` (6 951 látek).
Překlad se dělá při plnění DB a cachuje na disk
(`data/ciselnik_latky.json`), aby se nestahoval pokaždé.

    PARALEN   [1064]           -> ['PARACETAMOL']
    ACIFEIN   [12, 1064, 223]  -> ['KYSELINA ACETYLSALICYLOVÁ', 'PARACETAMOL', 'KOFEIN']
    ABLYMICO  [16742]          -> ['LIRAGLUTID']

### Co to odhalilo navíc

Dotaz na účinnou látku teď funguje, ale ukázal dvě věci k doladění:

1. **Router si nebyl jistý sekcí** (`jistota: nizka`), takže hledal ve
   všech. Jako nejlepší pasáž pak ukázal DÁVKOVÁNÍ, ne identitu léku.
   U dotazu na účinnou látku by měl mířit na `atributy`.
2. **Podobnosti jsou nízké** (0,435–0,460), takže při naměřeném prahu 0,50
   by dotaz nevrátil nic. Vektor totiž porovnává „paracetamol" s textem
   o dávkování, kde to slovo není.

Je to případ, kdy **rozhoduje FILTR, ne sémantika** – a práh na cosine
proti tomu pracuje. Stojí za úvahu, jestli u dotazů, kde filtr sám vybral
malý počet léčiv, práh vůbec uplatňovat.

---

## 2026-08-20 — Kolik trvá jeden dotaz a proč na DGX „není vidět aktivita"

Rozpad jednoho dotazu (`hledej.py "volně prodejný lék na bolest hlavy"`):

| krok | kde běží | čas |
|---|---|---|
| router (qwen3.5:122b) | DGX | **5,62 s** |
| embedding dotazu (bge-m3) | DGX | 0,16 s |
| hledání v Postgresu | lokálně | 0,31 s |
| seskupení po léčivech | lokálně | 0,0001 s |
| **celkem** | | **6,08 s** |

**Router je 92 % celkového času.** Vlastní hledání – vektorová podobnost
nad 994 řádky, český fulltext, RRF a seskupení – trvá **0,31 s**.

### Proč na DGX není vidět vytížení

Dvě věci dohromady:

1. **Trvá to jen ~6 s** a je to jeden krátký dotaz. Při obnovování
   `nvidia-smi` po sekundách se to snadno mine.
2. **qwen3.5:122b je MoE** – aktivuje se 8 expertů z 256, tedy ~3 %
   parametrů. Je to mělký záběr, ne dlouhé vytížení jako u hustého modelu.

Modely přitom v paměti zůstávají (`/api/ps`):

    qwen3.5:122b     87,4 GB
    bge-m3:latest     0,7 GB

### Co z toho plyne pro optimalizaci

Kdyby bylo potřeba hledání zrychlit, **nemá smysl sahat na vektorové
hledání ani na RRF** – ty dohromady dělají 5 % času. Jediná páka je router:

- menší model jen na routování (byl původně `qwen2.5:14b`)
- nebo router úplně vynechat u dotazů, kde je sekce zřejmá
- nebo cache na opakované dotazy

Ale pozor: **router není zbytný**. Změřeno, že bez něj přestane fungovat
práh podobnosti (negativní dotazy 0/8 místo 8/8) a dotaz „lék na bolest"
vrací léky, které bolest způsobují. Zrychlení by se muselo měřit proti
té ztrátě, ne jen proti času.

---

## 2026-08-20 — Evaluace: práh 0,50 a proč ho dělá funkčním ROUTER

Krok 15 hotový (`evaluate.py`). Výsledky:

```
Invarianty filtru           120/120   100%
Auto-recall @5               56/60     93%
Auto-recall @10              59/60     98%
Negativní dotazy (práh 0.50)   8/8    100%
Parafráze (ručně)            10/10    100%
```

### Práh je 0,50, ne 0,70

Zadání odhadovalo pro bge-m3 ~0,7. **Naměřeno, že to neplatí** – práh 0,7
by vrátil jen 1 parafrázi z 10.

| práh | parafráze | negativní |
|---|---|---|
| 0,45 | 9/10 | 3/8 |
| **0,50** | **9/10** | **8/8** |
| 0,55 | 6/10 | 8/8 |
| 0,70 | 1/10 | 8/8 |

### NEJDŮLEŽITĚJŠÍ ZJIŠTĚNÍ: práh funguje jen S ROUTEREM

Nejdřív jsem naměřil, že **žádný práh obojí neoddělí** – rozdělení se
překrývala (parafráze 0,486–0,709, negativní 0,502–0,652). Ten závěr byl
špatný, protože jsem negativní dotazy pouštěl **bez routeru**, tedy přes
všech 994 řádků včetně nežádoucích účinků. Tam se vždy něco vágně
podobného najde.

Skutečný dotaz ale projde routerem. Ten ho omezí na `indikace` (136 řádků)
a mezi indikacemi nic podobného malárii není:

| dotaz | top cosine bez routeru | s routerem |
|---|---|---|
| „něco na HIV" | 0,502 | **0,435** |
| „lék na malárii" | – | **0,449** |
| „lék na dnu" | – | **0,389** |

**Výsledek při prahu 0,50: bez routeru 0/8, s routerem 8/8.**

Router tedy není pohodlí, ale **podmínka toho, aby práh vůbec dával smysl**.
Bez něj se filtruje šum, který vznikl tím, že se hledalo ve špatné sekci.

### Čtyři z pěti negativních dotazů byly ve skutečnosti V DATECH

Vážnější chyba testu. Původní sada:

| dotaz | co v datech opravdu je |
|---|---|
| „zlomenina nohy" | CONTROLOC má **zlomeniny kyčelní kosti** jako NÚ |
| „očkování proti chřipce" | ADVANTAN má „reakce kůže po očkování" |
| „přípravek na hubnutí" | **ABLYMICO (liraglutid) na hubnutí PŘÍMO JE** |
| „vypadávání vlasů" | ADVANTAN má „zánět vlasového váčku" |

Systém odpovídal **správně** a test to počítal jako selhání – tím se
znehodnotilo celé měření prahu.

**Poučení: negativní testovací případ se musí OVĚŘIT proti datům, ne
odhadnout.** V korpusu se stovkami nežádoucích účinků se skoro každé
lékařské téma někde vyskytne. Přidána funkce `overit_negativni()`, která
sadu automaticky prověří – tuhle chybu už nikdo tiše neudělá.

Ověřeně nepřítomná témata v tomhle korpusu: HIV, malárie, Parkinson,
roztroušená skleróza, schizofrenie, osteoporóza, dna, popáleniny.

### Test 0 našel v datech tohle

```
Pokrytí sekcí         21/22    ALGESAL: chybí nezadouci_ucinky
Podezřelé sekce       83/87    4 sekce mají položku delší než 400 znaků
Struktura JSONB     979/979    100 %
Frekvence namapovaná 442/654   212 položek má rank 9
Čísla stránek           0/994  NIKDY SE NEPLNILA
```

Pořadí testů má smysl: kdyby se tyhle díry neznaly, čísla z testů 1–4 by
se daly číst jako kvalita hledání, přestože jde o chybu v datech.

---

## 2026-08-20 — Volba extraktoru podle SEKCE, ne podle tabulky

Původní pravidlo znělo „sekce má markdown tabulku → Docling, nemá →
surový PyMuPDF text". Vzniklo kvůli **záměně frekvencí v sekci 4.8**.
Aplikoval jsem ho ale plošně na všechny sekce, a to bylo špatně:
**indikace a kontraindikace žádné frekvence nemají**, takže se jich ten
důvod nikdy netýkal.

### Co to stálo

| | Docling | plain text |
|---|---|---|
| nadpisy v indikacích a kontraindikacích | **15** | **0** |
| odrážky | 122 | 82 |

Nulové nadpisy znamenají, že se ztratilo rozdělení na skupiny pacientů
(`## Dospělí`, `## Pediatrické použití`). Model pak musel hádat —
u OMEPRAZOLU označil jako „dospělí" jen **1 položku z 12**.

Po přepnutí indikací a kontraindikací na Docling: poměr zdrojů
**63 docling_md / 25 pymupdf_raw** (dřív 20 / 72).

### Změřeno: pymupdf4llm NENÍ náhrada, přestože je 3× rychlejší

Otázka zněla, jestli místo plain textu nepoužít pymupdf4llm — dělá
podobné věci jako Docling a je výrazně rychlejší.

**Rychlost a obecná struktura mu svědčí:**

| léčivo | nástroj | nadpisy | tabulky | rozbitá slova | čas |
|---|---|---|---|---|---|
| OMEPRAZOL | pymupdf4llm | 82 | 57 | 1 | **9,6 s** |
| | docling | 96 | 59 | 1 | ~30 s |
| CONTROLOC | pymupdf4llm | 64 | 17 | **1** | **9,4 s** |
| | docling | 81 | 17 | **10** | ~30 s |

**Ale na sekci 4.8 selhává přesně tam, kde to nejvíc vadí:**

| AMOKSIKLAV 4.8 | samostatné frekvence | SLEPENÉ |
|---|---|---|
| pymupdf_raw | **16** | **0** |
| docling | 16 | 1 |
| pymupdf4llm | **0** | **5** |

Slévá frekvence i účinky do jednoho odstavce:

    Infekce a infestace</u> Časté kandidóza sliznic a kůže Není známo
    přerůstání necitlivých organismů <u>Poruchy krve...</u> Vzácné
    reverzibilní leukopenie ... Není známo hemolytická anémie

Na jednom řádku jsou **dvě různé frekvence a k nim účinky bez oddělení**.
To je přesně stav, kvůli kterému model u DITHIADENU zapsal „velmi vzácné"
místo „vzácné" – desetinásobné podhodnocení rizika.

U ACC navíc sekci 4.8 vůbec nenašel, protože píše nadpis jako
`# **4.8 Nežádoucí účinky**` (tučné uvnitř nadpisu) a náš regex to nečeká.
To by se opravit dalo, ale slévání ne.

### Závěr

**Žádný extraktor není nejlepší na všechno.** Dělení podle sekce je
správné, jen se má řídit RIZIKEM, ne přítomností tabulky:

| sekce | zdroj | proč |
|---|---|---|
| indikace, kontraindikace | **Docling** | nemají frekvence, potřebují nadpisy skupin |
| nežádoucí účinky, dávkování | tabulka → Docling, jinak plain text | riziko záměny frekvencí je reálné |

Trojnásobná rychlost pymupdf4llm se u sekce, kde se rozhoduje
o zdravotním údaji, nevyplatí.

## Propsání nadpisu skupiny do položek

Samotná struktura z Doclingu **nestačila**. I s `## Dospělí` a odrážkami
pod ním model u OMEPRAZOLU označil jako „dospělí" jen tu jednu položku,
kde je „u dospělých" přímo ve větě, a zbylým deseti dal „neuvedeno".

Řešení: skupina se **deterministicky propíše ke každé položce** ještě
před vstupem do modelu (`sekce.oznac_skupiny`):

    ## Dospělí
    [Dospělí] - Léčba duodenálních vředů
    [Dospělí] - Prevence relapsu duodenálních vředů

Nadpis, který skupinou pacientů NENÍ (`## Léčba bez porady s lékařem`),
skupinu naopak **ruší** – jinak by se propsal omylem.

Výsledek u OMEPRAZOLU:

    před:  dospeli 2,  neuvedeno 10,  deti 3
    po:    dospeli 12,                deti 3

**Poučení: strukturu textu nestačí modelu ukázat, musí se mu předžvýkat.**
Nadpis platný pro deset položek pod ním model spolehlivě nepropojí.

## ts_rank_cd dává u jednoslovných dotazů skoro stejné hodnoty

Fulltextový rank počítá `ts_rank_cd` nad `tsvector` s vahami:

    setweight(to_tsvector('czech_unaccent', kontext_text), 'A')  -- identita léku
    setweight(to_tsvector('czech_unaccent', obsah_text),   'B')  -- obsah

Postgres váhy: A=1,0 B=0,4 C=0,2 D=0,1. Shoda v názvu léku tedy váží
2,5× víc než v textu.

**Změřeno pro dotaz „bolest": všechny čtyři shody měly rank přesně
0,40000.** Jedno slovo, jeden výskyt, váha B – rank je pak konstanta
a pořadí mezi nimi je jen pořadím řádků v databázi, tedy náhoda.

A právě tenhle bezcenný rozdíl přebil přes RRF sémantiku u MAALOXU.
Je to další argument pro režim `--zpusob cosine`.

---

## 2026-08-20 — Jak funguje RRF a proč váha 0,8 nestačí

### Rámcově

Hybridní hledání má dva zdroje: **sémantiku** (cosine nad embeddingy) a
**český fulltext** (`ts_rank_cd` nad `tsvector`). Ty dvě čísla se nedají
sečíst — cosine je 0–1, `ts_rank` má úplně jiný rozsah a jinou distribuci.

**RRF (Reciprocal Rank Fusion) to obchází tím, že zahodí skóre a pracuje
jen s POŘADÍM:**

    skore = vaha_sem / (k + poradi_sem) + vaha_fts / (k + poradi_fts)

Výchozí nastavení (`common/hledani.py`):

| parametr | hodnota | kde se mění |
|---|---|---|
| `VAHA_SEMANTIKA` | 0,8 | `--vaha-semantika` |
| váha fulltextu | dopočítává se jako 1 − váha | – |
| `RRF_K` | 60 | parametr `rrf_k` funkce `hledej()` |

### Co se váhou násobí

**NE podobnost, ale převrácené pořadí.** Cosine do vzorce nevstupuje vůbec —
použije se jen k určení pořadí a pak se zahodí. Skutečná čísla pro dotaz
„bolest" (sekce indikace, volně prodejné):

| lék | cosine | #sem | #fts | příspěvek sem | příspěvek fts | RRF |
|---|---|---|---|---|---|---|
| PARALEN | 0,618 | 1 | 3 | 0,013115 | 0,003175 | 0,016289 |
| MAALOX | 0,481 | 9 | 4 | 0,011594 | 0,003125 | 0,014719 |
| ACIFEIN | 0,524 | 6 | – | 0,012121 | 0 | 0,012121 |

**MAALOX s podobností 0,481 skončil nad ACIFEINEM s 0,524.**

### Proč se to děje

Hodnota `1/(k+pořadí)` má při k=60 extrémně úzký rozsah:

| pořadí | 1/(60+pořadí) |
|---|---|
| 1 | 0,01639 |
| 9 | 0,01449 |
| 50 | 0,00909 |
| 100 | 0,00625 |

Mezi **1. a 9. místem je rozdíl jen 13 %**, zatímco v cosine je mezi 0,618
a 0,481 rozdíl 28 %. Sémantický handicap MAALOXU tedy činil 0,00053,
kdežto fulltextový bonus mu dal 0,00313 — **šestkrát víc, přestože má
fulltext čtyřikrát nižší váhu**.

### Změřeno: váha ani k to nespraví

| váha sémantiky | pořadí monotónní podle cosine? |
|---|---|
| 0,80 | ne |
| 0,90 | ne |
| 0,95 | ne |
| 1,00 | ano (ale to už je čistá sémantika) |

| k | váha 0,8 | váha 0,9 |
|---|---|---|
| 5 | ne | částečně |
| 10 | ne | částečně |
| 20 | ne | ne |
| 60 | ne | ne |

**Není to vada implementace, je to podstata metody.** RRF slučuje dvě
pořadí a je navržené tak, aby slabší žebříček mohl výsledek ovlivnit.

### Řešení: druhý režim řazení

Přidán přepínač `--zpusob`:

- **`rrf`** (výchozí) — klasická fúze, fulltext může změnit pořadí
- **`cosine`** — pořadí určuje VÝHRADNĚ podobnost, fulltext slouží jen
  k tomu, aby se kandidát dostal do výběru (recall). Odpovídá zadání
  „fulltext je jen doplněk" doslovněji. Váha se v něm neuplatní.

Který je lepší, má rozhodnout **evaluace na víc dotazech**, ne dojem
z jednoho. Proto jsou v kódu oba a výchozí zůstává `rrf`.

### Ve výpisu se RRF normalizuje na 0–100

Surové hodnoty (0,016289 vs 0,014719) se nedají číst — rozdíly jsou
v pátém desetinném místě. CLI proto přepočítává na **odstup od nejlepšího
výsledku**. Absolutní hodnota RRF stejně nic neznamená: není to
podobnost ani pravděpodobnost, jen pomocné číslo pro seřazení.

---

## 2026-08-20 — „Pálení žáhy" nenajde CONTROLOC ani OMEPRAZOL (dvě příčiny)

Reálný dotaz, který selhal. Oba léky přitom na reflux jsou a mají to
v indikacích. Rozbor ukázal **dvě nezávislé příčiny**:

### 1. OMEPRAZOL vůbec není v indexu

Jeho sekce `indikace` má stav `zamitnuto_kontrolou`, takže se do
`leciva_search` nepouští. Našel se jen jeho řádek z **dávkování**
(„Dospělí (léčba pálení žáhy bez lékaře) 20 mg 1x denně", cosine 0,645),
protože tam ten termín doslova je.

Je to správné chování stavového modelu, ale má cenu: **lék je pro
vyhledávání neviditelný, dokud sekci někdo neprojde ručně.**

### 2. CONTROLOC je v indexu, ale laický text nepoužívá běžný termín

Uložený text:

    „Léčba příznaků návratu kyseliny ze žaludku do jícnu.
     (Symptomatická léčba refluxní choroby jícnu)"

Slovo **„pálení žáhy" tam není**. Model přeložil odborný termín popisně
místo běžným lidovým výrazem, a bge-m3 to spojení nedá — CONTROLOC se
nedostal ani do prvních osmi, kde jsou výsledky kolem 0,45 typu
„zápal plic" nebo „horečka".

### Co z toho plyne

Tohle je **konkrétní důkaz pro test C z evaluace** (má slovník pojmů vliv
na hledání?). Ukazuje, že problém není v embedovacím modelu, ale v tom,
**jakými slovy je psaný laický tvar**. Kdyby v něm bylo „pálení žáhy",
dotaz by uspěl.

Možná řešení k vyzkoušení v evaluaci:
1. do laického tvaru vynutit **běžný lidový termín**, ne opis
   (prompt: „řekni to slovem, které použije laik při hledání")
2. ukládat do `obsah_text` **oba tvary** i u indikací (u nežádoucích
   účinků se to už dělá: „nízký počet krevních destiček (trombocytopenie)")
3. rozšířit dotaz o synonyma ze slovníku pojmů před embedováním

---

## 2026-08-19 — Sjednocení tvaru indikací a kontraindikací (návrh uživatele)

**Změna návrhu.** Indikace a kontraindikace byly do teď jen laický řetězec.
Nežádoucí účinky měly dvojici `ucinek` (doslova ze zdroje) + `ucinek_laicky`.
Uživatel navrhl sjednotit to a mělo to čtyři důsledky, z nichž jeden jsem
nečekal:

1. **Vznikla kotva ke zdroji.** Bez doslovného tvaru nebylo co porovnat,
   takže deterministická kontrola tyhle sekce **vůbec nemohla ověřit**.
   Po změně pokrývá 88 sekcí místo 46.
2. **Zmizel limit „2–5 slov"**, který nutil model slučovat a zahazovat.
3. **Menší chybovost** – stejný tvar u všech sekcí, stejná pravidla.
4. **Hned se to projevilo v datech**, viz níž.

### Číselné dopady

| | před | po |
|---|---|---|
| léčiv s použitelnými indikacemi | **9 z 22** | **19 z 22** |
| řádků indikací | 46 | 91 |
| léčiv s kontraindikacemi | 18 | **22 z 22** |
| zamítnutých sekcí | 22 | **8** |
| sekcí `ok` | 70 | **79 z 88** |

Počet léčiv, která jde najít podle indikace, se **víc než zdvojnásobil**.

## Středníky ve výčtech ničí extrakci

SPC píše výčty indikací jako jednu větu oddělenou **středníky**. Model to
čte jako souvislý text a polovinu položek sloučí nebo zahodí. Změřeno na
DITHIADENU, sekce 4.1:

| vstup | položek |
|---|---|
| původní (se středníky) | **4** |
| středníky → nové řádky | **9** |
| středníky i čárky → řádky | 8 |

A zlepšila se i kvalita: `Quinckeho edém` dal se středníky nesmysl
„tvarohový otok obličeje", po rozpadu správně „náhlé otoky kůže a sliznic".

**Čárky se NEDĚLÍ** – uvnitř jedné indikace jsou běžné („alergická rýma,
zvláště sezónní") a rozpad by je roztrhal.

Opraveno u ZDROJE (`sekce.rozpad_vyctu`), ne v promptu – stejný princip
jako u rozbitých slov.

### Fragmenty z české elipsy jsou přijatelné

PARALEN má ve zdroji „bolesti zubů, hlavy, neuralgie". Model to správně
rozdělí, ale v `doslovne` zůstane holé „hlavy". Necháno schválně: kdyby
model doplnil „bolesti hlavy", **přestalo by to být doslovné a kontrola
by to označila za chybu**, přestože by to bylo správně. Laický tvar
význam nese správně a to je pole, které vidí uživatel.

## Skupina pacientů jako číselník, ne chybějící klíč

U indikací se do položek dostávaly nadpisy skupin pacientů:

    "Dospělí • Léčba duodenálních vředů"
    "Pediatrické použití Děti od 1 roku a s hmotností ≥ 10 kg"   <- není indikace

OMEPRAZOL má **jiné indikace pro dospělé a pro děti**, takže tu informaci
nešlo jen zahodit. Řešeno dvěma vrstvami, stejně jako u frekvence:

| pole | hodnota | role |
|---|---|---|
| `skupina` | doslova ze zdroje – „děti od 1 roku a s hmotností ≥ 10 kg" | zobrazení |
| `skupina_kod` | `deti` | filtr |

Kdyby byl jen doslovný text, filtr by nefungoval (každý lék to píše jinak).
Kdyby byl jen kód, ztratila by se hmotnostní podmínka.

**Hodnota `neuvedeno` je EXPLICITNÍ**, ne chybějící klíč – stejný princip
jako u stavů extrakce: z prázdna nejde poznat „zdroj skupinu nerozlišuje"
od „model to přehlédl". V korpusu: 65× neuvedeno, 12× děti,
9× dospívající, 5× dospělí.

---

## 2026-08-19 — Docker compose bere jméno projektu z názvu ADRESÁŘE

Zadání varovalo před kolizí jmen volumes a kontejnerů se starým projektem.
Ošetřil jsem obojí (`localsemantic-*`), a compose přesto **rozebral starý
projekt** – zmizel kontejner `ailocal-pgadmin`.

**Příčina:** jméno projektu si compose odvozuje z názvu adresáře, a ten se
jmenuje `ailocal`. Nové kontejnery se tím zařadily do starého projektu.
Data ztracená nebyla (volumes zůstaly), ale je to past, kterou zadání
nepředvídalo.

**Oprava:** explicitní `name: localsemantic` v `docker-compose.yml`.

### Bind-mounty jako prázdné adresáře – podruhé

`pgpass` **i** `pgadmin-servers.json` byly na disku jako **prázdné
adresáře**, které tam vyrobil Docker při starém běhu. Je to přesně ten
problém, kterým celá tahle práce před časem začala.
`priprav_infrastrukturu.py` teď hlídá všechny tři bind-mounty.

### CHECK omezení v DDL se vyplatila hned

Do `init-db.sql` jsem přidal `CHECK` na povolené hodnoty stavů a sekcí.
Otestováno a odmítá:

    'chibi_v_dokumentu'   -> ODMÍTNUTO (překlep opravovaný týž den)
    sekce 'vymyslena'     -> ODMÍTNUTO
    frekvence u indikace  -> ODMÍTNUTO (filtry NÚ nesmí být jinde)

To poslední je podstatné: kdyby se `frekvence` omylem vyplnila u indikace,
filtr by se choval nepředvídatelně a nikdo by to nepoznal.

---

## 2026-08-19 — Router: „po vepřovém mě bolí břicho" je INDIKACE

Bez routeru vrátí dotaz „volně prodejný lék na bolest" položky ze sekce
`nezadouci_ucinky` – tedy léky, které bolest **způsobují**, ne které ji
léčí. U aplikace pro laiky je to nebezpečná záměna, ne jen nepřesnost.

Router (`common/router.py`) z dotazu určí sekci a filtry. Na první pokus
uspěl u 6 ze 7 testů, ale **selhal přesně na případu, který zadání jmenuje**:

    "po prasicich co jsem si vzal me boli bricho"  ->  nezadouci_ucinky

**Příčina byla v mém promptu:** mezi spouštěči nežádoucích účinků jsem měl
formulaci „po čem mi je". Jenže po vepřovém ani po houbách není lék.
Opraveno na podmínku, že potíže musel způsobit **LÉK**, a oba případy
přidány jako protipříklady. Po opravě 6/6:

    po prasicich ... me boli bricho    -> indikace
    po tom leku me boli bricho        -> nezadouci_ucinky
    vcera jsem jedl houby, je mi zle  -> indikace
    muze paralen zpusobit vyrazku     -> nezadouci_ucinky

## RRF umí přebít sémantiku, i když má nižší váhu

Zadání: „o 500 % je důležitější, aby to našlo sémantické věci, fulltext je
jen doplněk." Nastaveno 0,8 / 0,2. Přesto u dotazu „Paralen 500mg":

    0.498  S3/F8   PARALEN  davkovani  starší 15 let ... 500 mg
    0.759  S1/F33  PARALEN  atributy   PARALEN, 500MG, TBL NOB

Řádek s **nižší** podobností skončil výš. RRF pracuje s POŘADÍM, ne se
skóre, takže 3. místo v sémantice + 8. ve fulltextu přebilo 1. místo
v sémantice + 33. ve fulltextu.

    0.8/(60+3) + 0.2/(60+8)  = 0.0156
    0.8/(60+1) + 0.2/(60+33) = 0.0153

**Váha 0,8 na to nestačí** – rozhoduje rozdíl v pořadí, ne váha.
K doladění v evaluaci; možnosti: vyšší váha, jiná fúze, nebo práh na
cosine ještě před fúzí.

## Práh podobnosti pro bge-m3 se MUSÍ naměřit

Zadání odhaduje, že pro bge-m3 může být kolem 0,7 (0,4 platilo pro
qwen3-embedding). Naměřeno na reálných dotazech:

| dotaz | nejlepší cosine |
|---|---|
| „Paralen 500mg" (přesný název) | 0,76 |
| „volně prodejné léky na bolest" | 0,53 |
| „bolest břicha nežádoucí účinek" | 0,68 |

**Práh 0,7 by u dotazu na bolest nevrátil vůbec nic.** Odhad ze zadání
tedy neplatí a hodnota se musí naměřit testem, ne převzít.

---

## 2026-08-19 — Nestabilní je EXTRAKCE, ne kontrola (a spletl jsem si to)

Dva běhy celé pipeline nad stejným korpusem daly různý výsledek:
`ok` 75 → 70, zamítnutých 17 → 22. Ze sjednocení 28 sekcí se shodlo
jen **11 (39 %)**.

**Unáhlil jsem se se závěrem**, že je nespolehlivá kontrola, a napsal
to i do `todo.md`. Změřeno to nebylo. Když jsem pustil kontrolu
**dvakrát nad TÝMIŽ daty**, vyšlo:

| | sekcí |
|---|---|
| běh 1 | 20 |
| běh 2 | 20 |
| v obou | **19** |
| shoda (Jaccard) | **90 %** |

**Kontrola je stabilní.** Rozptyl dělá **extrakce** – přeextrahováním
vznikne jiná sada formulací, a tím i jiná sada chyb.

### Co z toho plyne prakticky

1. **Pouštět kontrolu opakovaně se nevyplatí.** Při 90 % shodě je druhý
   průchod skoro zbytečný.
2. **Přeextrahovat data „aby to bylo lepší" je iluze.** Chyby se
   nezmenší, jen se přesunou jinam. Potvrzuje to dřívější zjištění,
   že `mediální` místo `mediastinální` se při opakování zopakovalo,
   zatímco cyrilice se přestěhovala do jiného pole.
3. **Sjednocení napříč běhy má smysl** – ne kvůli nespolehlivé kontrole,
   ale protože každý běh extrakce vyrobí trochu jinou sadu chyb.
   Sekce označená v OBOU bězích je nejjistější kandidát: chyba se
   reprodukovala.
4. **Ruční opravy musí být mimo generovaná data.** Proto
   `slovnik_rucni.json` – kdyby se opravovalo přímo v extrahovaném
   JSONu, příští běh by to smazal.

### Poučení k postupu

Rozdíl mezi dvěma běhy měl dvě možné příčiny (nestabilní kontrola,
nestabilní extrakce) a já z nich vybral jednu bez měření. Přitom to
měření stálo 9 minut a dalo jednoznačnou odpověď. **Když má jev dvě
možné příčiny, oddělit je experimentem, ne úvahou.**

---

## 2026-08-19 — Kontrola JINÝM modelem funguje: gemma4:31b našla obrácený význam

Krok 4, část 2 (`zkontroluj_modelem.py`). Kontroluje `gemma4:31b`, tedy JINÝ
model než ten, který extrahoval (`qwen3.5:122b`). Větší už není kam jít –
122b je z lokálních nejlepší – takže se volí **jiný, ne větší**.

**Výsledek: 57 sekcí, 547 položek, 24 označeno (4,4 %), 4,3 min, 4,6 s
na sekci, žádné selhání volání.**

### Nejzávažnější nález celé kontroly

OLYNTH, kontraindikace. Zdroj:

    OLYNTH 0,5 mg/ml: děti do 2 let.
    OLYNTH 1 mg/ml:   děti do 7 let.

Extrakce z toho udělala:

    "Nad 2 let pro přípravku s koncentrací 0,5 mg/ml"
    "Nad 7 let pro přípravky s koncentrací 1 mg/ml"

**Obrácený význam.** U nosního spreje, který se volně prodává a používá
u dětí, by to rodiči řeklo pravý opak toho, co je v dokumentu.

Tohle **nemohla najít deterministická kontrola** – slova „2", „let" i „děti"
ve zdroji jsou, mění se jen vztah mezi nimi. A nemohl to najít ani model,
který to vyrobil. Přesně proto musí kontrolovat JINÝ model.

### Další potvrzené nálezy

| lék | extrakce | zdroj |
|---|---|---|
| DITHIADEN | „**těžké** alergické reakce" | „**akutní** alergické stavy" |
| AMOKSIKLAV | průjem, nauzea, zvracení = „není známo" | „**Nejčastěji** hlášenými…" |
| AMOKSIKLAV | „kůže a **svaly**" | „kůže a **měkké tkáně**" |
| ACIDUM ASCORBICUM | „obecný nedostatek kyslíku v krvi" | „methemoglobinemie" |

### Proč zrovna gemma4:31b

Ověřeno na vzorku před ostrým během: rychlá, vrací validní JSON, najde
skutečnou chybu **a přitom neoznačkuje všechno** (1 nález z 65 položek).
Obava, že slabší model bude dělat falešné poplachy, se nepotvrdila – při
4,4 % označených jsou nálezy, které jsem ručně ověřil, oprávněné.

**Úloha je zúžená schválně:** jen „má tahle položka oporu ve zdroji?",
žádné přepisování ani návrhy oprav. Model vrací jen indexy položek
a krátký důvod. Krátký výstup = rychlý výstup, a slabší model unese
úzkou úlohu líp než širokou.

**Pojistka proti halucinaci:** index musí ukazovat na existující položku,
jinak se nález zahodí a počítá zvlášť. Kdyby model začal vymýšlet indexy,
je to signál, že kontrole nelze věřit.

### Konečný stav kroku 4

| stav | sekcí |
|---|---|
| `ok` | **75** |
| `zamitnuto_kontrolou` | **17** |

Deterministická kontrola potvrdila 35 sekcí, modelová dalších 40.
Zbylých 17 sekcí je označeno k ručnímu posouzení – to je práce pro člověka,
ne pro další model.

---

## 2026-08-19 — Rozbitá slova NEDĚLÁ PDF, dělá je textový backend Doclingu

Celý den jsem rozbité mezerování („P acienti", „V zácné", „srd eční")
popisoval jako **vadu zdrojových PDF** a stavěl na to opravy: `sprav_mezerovani()`,
`sceluj_frekvence()`, `slep_rozdelena_slova()`. Byl to špatný předpoklad
a měl jsem ho ověřit dřív, než jsem začal stavět záplaty.

**Změřeno na 22 dokumentech korpusu, tytéž soubory oběma extraktory:**

| extraktor | rozbitých míst |
|---|---|
| PyMuPDF (`page.get_text("text")`) | **64** |
| Docling, výchozí backend | **1 232** |

Devatenáctinásobek nad TOTOŽNÝMI PDF. Nejhorší případy:

| léčivo | PyMuPDF | Docling |
|---|---|---|
| ALTHYXIN | 3 | **363** |
| OLYNTH | 0 | **240** |
| CONTROLOC | 1 | **237** |
| ACECOR | 0 | **157** |

### Řeší to volba backendu, ne následné slepování

Docling má vyměnitelný textový backend. Výchozí `docling_parse_v4` slova
rozbíjí, `pypdfium2` ne:

| léčivo | docling_parse_v4 | pypdfium2 |
|---|---|---|
| ALTHYXIN | 363 | **4** |
| CONTROLOC | 237 | **10** |
| PARALEN | 9 | **3** |
| IFIRMASTA | 3 | 7 |

**TABULKY ZŮSTÁVAJÍ SHODNÉ** – 17/17 a 39/39 řádků. Extrakci tabulek dělá
layout model (RT-DETR + TableFormer), ne textový backend, takže se přepnutím
nic neztratí. Navíc je pypdfium2 o něco rychlejší (26,7 s vs 34,1 s).

Nastavuje se v `konverze.konvertuj_pdf()`:

    from docling.datamodel.base_models import InputFormat
    from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
    from docling.document_converter import DocumentConverter, PdfFormatOption

    DocumentConverter(format_options={
        InputFormat.PDF: PdfFormatOption(backend=PyPdfiumDocumentBackend)})

### Proč na tom záleželo víc, než to vypadá

Rozbité `V zácné` vedlo k tomu, že model zapsal `velmi vzácné` – tedy
desetinásobné podhodnocení rizika u léku. Defekt „jen v mezerách" se
neprojevil jako nečitelný text, ale jako **věcně chybný zdravotnický údaj**.

### Poučení

1. **Než začnu opravovat vadu, ověřit KDE vzniká.** Dva extraktory nad
   týmž souborem daly odpověď za pár minut. Postavil jsem místo toho tři
   opravné funkce na předpokladu, který byl špatně.
2. **Oprava u zdroje > záplata potom.** Slepování zpětně nemůže být nikdy
   úplné a nese riziko, že slepí něco špatně: `„že na jejich vzniku"` →
   `„žena jejich vzniku"`. Musel jsem kvůli tomu zavést práh výskytu
   samostatného slova, což je složitost, která teď z velké části odpadá.
3. **Výchozí nastavení knihovny není nutně to nejlepší.** Docling používáme
   kvůli tabulkám a nadpisům; že si k tomu bere i horší textový backend,
   nebylo nikde vidět, dokud se to nezměřilo.

`slep_rozdelena_slova()` zůstává jako pojistka na zbylých pár desítek míst,
ale přestává být hlavním řešením.

---

## 2026-08-19 — Nejzávažnější nález: model si domyslel „velmi" u frekvence

DITHIADEN měl ve zdroji **5× `V zácné`** (rozbité mezerování z PDF).
Model z toho udělal **5× `velmi vzácné`**. To je desetinásobné podhodnocení
rizika – *vzácné* je 1/10 000 až 1/1 000, *velmi vzácné* pod 1/10 000.
U aplikace, která to má ukazovat laikovi, je to nejhorší možná chyba
a **žádná kontrola uvnitř modelu by ji nenašla** – model si byl jistý.

`sprav_mezerovani()` to nechytlo, protože řeší osamocené písmeno
S DIAKRITIKOU obklopené mezerami, kdežto tady bylo rozdělené obyčejné
„V" + „zácné".

**Oprava: scelit označení frekvence JEŠTĚ PŘED tím, než text uvidí model**
(`sekce.sceluj_frekvence()`). Frekvence je řídicí údaj, takže se nesmí
spoléhat na to, že si model poradí. Postiženo bylo 5 z 23 léčiv.
Po opravě má DITHIADEN 6× `časté` a 5× `vzácné` – přesně jako zdroj.

**Obecné poučení: vada zdroje se projeví jako sebejistá chyba modelu.**
Rozbité mezerování nezpůsobilo, že by model selhal viditelně – způsobilo,
že doplnil chybějící kus podle toho, co dávalo smysl. Proto se defekty PDF
musí opravovat před vstupem do modelu, ne po něm.

## Řízený slovník se dá vynutit deterministicky (`ocisti_json.py`)

`organovy_system` má být FILTR, jenže v korpusu bylo **31 různých hodnot**
místo ~20 skutečných kategorií. Rozdíl dělaly:

| druh znečištění | příklad |
|---|---|
| rozbité mezerování | `Psychiatrické p oruchy`, `C évní poruchy` |
| značky poznámek | `Poruchy nervového systému*` |
| závorky navíc | `Poruchy imunitního systému (viz bod 4.3 a 4.4)` |
| překlep modelu | `v místo aplikace` (8×), `mediální` místo `mediastinální` |

Většinu spraví normalizace (bez mezer a diakritiky), zbytek přibližná shoda
proti kanonickému seznamu MedDRA SOC (`common/meddra.py`, práh 0,85).
Totéž u frekvence – `neste známo` (9×) a `neznámá frekvence` (6×).

**Výsledek: frekvence přesně 6 hodnot, orgánový systém přesně 20.**
Obojí je teď použitelné jako filtr.

**Přeextrahování tyhle chyby NEOPRAVÍ.** Ověřeno: `mediální` se při
opakovaném běhu zopakovalo a zároveň vznikly chyby nové (cyrilice se
přesunula do jiného pole). Očištění je oproti tomu deterministické,
zadarmo a opakovatelné.

## Cyrilice se objevila i v generovaném poli

Dřívější závěr „cyrilice byla jen v opisovaném poli" platil pro tehdejší
data, ne obecně. Po přeextrahování se objevila v `ucinek_laicky`
u CONTROLOCU (`těžké kožní реакции`). **Jazykový úlet postihuje obě
role – opis i tvorbu textu.** Kontrolovat se musí všechna textová pole.

## Kde jsme skončili

| | neshod | % |
|---|---|---|
| první běh | 47 | 6,2 % |
| po opravě kontroly (čísla u dávky, řečtina ven) | 27 | 3,6 % |
| po očištění na řízený slovník | 19 | 2,7 % |
| po scelení frekvencí ve zdroji | **11** | **1,5 %** |

39 ze 46 kontrolovatelných sekcí je `ok`. Zbylých 11 neshod jsou
kandidáti na modelovou kontrolu – mezi nimi `P řjem` místo `Průjem`.

---

## 2026-08-19 — Deterministická kontrola extrakce chytá to, co model nepřizná

Krok 4 se dělí na dvě části. První je **kontrola proti zdrojovému textu
bez modelu** (`zkontroluj_json.py`) – je zadarmo, spolehlivá a chytá právě
ten typ chyby, který je u zdravotnických dat nejnebezpečnější.

**Výsledek na 758 položkách (23 léčiv):** 27 neshod (3,6 %),
36 ze 46 sekcí zcela čistých.

### Co našla a co by jinak prošlo

| nález | proč je to vážné |
|---|---|
| `Respirační, hrudní a **mediální** poruchy` | má být *mediastinální* – poškozený název MedDRA kategorie, tedy klíč, podle kterého se filtruje |
| `Celkové poruchy a reakce v **месте** aplikace` | CYRILICE uprostřed slova, 7 výskytů u ADVANTANU |
| `Hyonatremie` | má být *Hyponatremie* |
| `Cellulitida` | má být *Celulitida* |

Cyrilice byla omezená na jediný soubor (5 z 36 položek), takže to není
systémový problém, ale **bez téhle kontroly by se to nikdy neukázalo** –
extrakce sama hlásila `neovereno`, tedy „proběhlo v pořádku".

### Cyrilice vznikla při OPISU, ne při zjednodušování

Objevila se **výhradně v poli `organovy_system`** – tedy v tom jediném,
kde má model opisovat ze zdroje doslova. V poli `ucinek_laicky`, kde model
tvoří vlastní text, nebyla ani jednou.

    zdroj:  Celkové poruchy a reakce v místě aplikace
    model:  Celkové poruchy a reakce v месте aplikace

A není to záměna vizuálně podobných znaků – `месте` je opravdové ruské
slovo (*в месте* = „v místě"). Model jedno slovo uprostřed české věty
**přeložil do ruštiny** místo aby ho opsal.

**Poučení: selhala ta jednodušší úloha, ne ta těžší.** Kreativní překlad
pro laiky proběhl čistě, mechanický opis se rozsypal. Přirozený předpoklad
by byl opačný – hlídat hlavně generovaná pole – a byl by špatně.
U vícejazyčného modelu se musí kontrolovat i doslovný opis, právě proto,
že může nepozorovaně ujet do jiného jazyka.

### Porovnávat se musí PO NORMALIZACI

Malá písmena, bez diakritiky, bez mezer a interpunkce. Zdrojová PDF mají
rozbité mezerování znaků („zp ů sob"), takže doslovná shoda by padala
na vadě zdroje, ne na chybě extrakce.

### U dávkování se NESMÍ porovnávat text, jen ČÍSLA

Doslovná kontrola `davka` hlásila **27 z 27 položek jako chybu, přestože
byla data správná**. Model dávku legitimně skládá a přepisuje jednotky:
ze zdrojové tabulky `25-50 | 100-200` a hlavičky „mikrogramů/den" udělá
`úvodní dávka: 25–50 mcg; udržovací dávka: 100–200 mcg`.

Po přepnutí na porovnání čísel: **0 neshod** – a je to zároveň silnější
tvrzení, protože překlep v čísle je u dávkování to nebezpečné, ne
přepsaná jednotka.

### Do kontroly cizího písma NEPATŘÍ řecká abeceda

Přidal jsem do hlídání i rozsah řecké abecedy a okamžitě to udělalo falešný poplach na
`Zvýšené jaterní enzymy (transaminázy, γ-GT)`. Řecká písmena jsou
v lékařském textu legitimní (γ-GT, β-blokátory). Hlídá se jen cyrilice
a CJK.

### Poučení

Falešné poplachy nejsou neškodné – **kontrola, která hlásí 27 z 27, se
přestane číst**. Dvě úpravy (čísla místo textu u dávky, řečtina ven
z hlídání) snížily šum ze 47 na 27 nálezů, a ty zbylé jsou skoro všechny
skutečné.

---

## 2026-08-18 — Tři způsoby, jak qwen3.5:122b rozbil parsování JSONu

Při prvním ostrém běhu kroku 3 spadlo **50 % sekcí 4.8**. Ani jedna
příčina nebyla v datech ani v modelu jako takovém – všechno šlo o to,
jak se odpověď zpracovává:

**1. Markdownová ohrádka i při zapnutém JSON módu.** Model vrátil
```` ```json {...} ``` ````, přestože je v požadavku `format: json`.
Data byla v pořádku, ale `json.loads()` spadl na „Expecting value:
line 1 column 1". Postihlo DITHIADEN i ACIFEIN.
→ `_ocisti_odpoved()` ohrádku sundá.

**2. Překlep v názvu klíče.** U AERIA přišlo `"ucinker"` místo `"ucinek"`.
Kontrola povinných klíčů kvůli tomu zahodila 6 z 18 položek a s nimi
celou sekci. → `_oprav_klice()` mapuje klíč na nejbližší očekávaný.

**Práh podobnosti je 0,7, a to není odhad.** Změřeno na skutečných
i vymyšlených případech:

| klíč | nejbližší | 2. nejbližší |
|---|---|---|
| ucinker | ucinek **0,769** | pacient 0,429 |
| pacent | pacient 0,923 | ucinek 0,333 |
| organovy_systm | organovy_system 0,966 | pacient 0,286 |
| ucinnost | ucinek **0,571** | pacient 0,533 |
| nesmysl | organovy_system 0,364 | ucinek 0,308 |

Reálné překlepy 0,77–0,97, nesouvisející slova nejvýš 0,57, druhý
kandidát vždy pod 0,54. **Práh 0,8 by „ucinker" (0,769) nechytil.**

**3. Nahodilý výpadek.** AERIUS vrátil na indikace prázdné pole nad
textem, kde jsou dvě jasné indikace (alergická rýma, kopřivka).
Napodruhé prošlo. → `extrahuj_sekci(pokusy=2)`.

**Nový stav `castecna`.** Dřív se při chybějících klíčích u části položek
zahodila celá sekce. To je špatně oběma směry: použitelná data se
zachránit dají, ale stav to musí přiznat. Teď se dobré položky ponechají
a stav řekne, kolik se zahodilo a proč.

**Výsledek po opravách: 92/92 sekcí, žádné selhání**, 24,4 min celkem,
15,9 s na sekci (23 léčiv × 4 sekce, qwen3.5:122b).

### Dávkování o jedné položce NENÍ chyba

11 z 23 léčiv má v `davkovani.json` jedinou položku. Je to **důsledek
ořezu na jádro**, ne selhání extrakce – ořez odstraní zvláštní populace
a zbyde základní dávkování, které je často jedna skupina pacientů:

    ACC 4.2:  1 442 -> 151 zn -> [{"pacient": "Dospělí a dospívající od 14 let",
              "davka": "10 ml sirupu", "frekvence": "2-3krát denně"}]

Ověřeno na AMOKSIKLAVU, ACYLCOFFINU a ACC – ve všech případech jádro
odpovídá tomu, co v ořezaném textu opravdu je. **Nízký počet položek
u dávkování je proto očekávaný a nemá se „opravovat".**

---

## 2026-08-18 — qwen3.5:122b je zároveň nejlepší i nejrychlejší (MoE)

Vzniklo to při hledání modelu na laický překlad. **Ani qwen2.5:32b, ani
qwen2.5:72b to nad holým seznamem termínů neumí** – domýšlejí si:

| termín | 32B | 72B | qwen3.5:122b | gpt-4o |
|---|---|---|---|---|
| trombocytopenie | „méně červené krvinky" | „náchylnost k krvácení" | **nízký počet krevních destiček** ✓ | málo krevních destiček ✓ |
| bronchospazmus | sevření dýchacích cest ✓ | „úzkostné údy" | **křeč dýchacích cest** ✓ | zúžení průdušek ✓ |
| cytolytická hepatitida | „nárůst plicního játra" | „pochod žaludku" | **poškození jaterních buněk** ✓ | zánět jater ✓ |
| pyróza | žaludeční pálivost | „horčka" | **pálení žáhy** ✓ | pálení žáhy ✓ |
| nauzea | „zvracení" | „znechucení" | **nevolnost** ✓ | nevolnost ✓ |

qwen3.5:122b mělo **všech 10 termínů správně**, na úrovni gpt-4o.

**A je přitom nejrychlejší ze všech**, protože je to MoE – aktivuje se jen
část parametrů, takže velikost modelu neurčuje množství čtené paměti:

| model | tok/s | PARALEN 4.8 | PARALEN 4.1 |
|---|---|---|---|
| qwen2.5:32b | 10,5 | 78,5 s | 24,0 s |
| qwen2.5:72b | 4,5 | 443,4 s | 134,0 s |
| **qwen3.5:122b** | **~29** | **28,8 s** | **3,3 s** |

Struktura z 122b je shodná s 32B i 72B (15 položek, tytéž frekvence
a orgánové systémy). Na indikacích je **41× rychlejší než 72B**.

**Důsledek:** dělení modelů podle úlohy (32B na opis, 72B na laický text)
je zbytečné – 122b vyhrává na obou stranách. `MODEL_SEKCE` má smysl si
nechat jako mechanismus, ale všechny sekce míří na 122b.

### Proč je větší model rychlejší – jak funguje MoE

**Generování tokenů je limitované PROPUSTNOSTÍ PAMĚTI, ne výpočtem.**
Aby model vyprodukoval jeden token, musí přečíst váhy z paměti. Výpočet
sám je proti tomu zanedbatelný, takže platí:

    strop tok/s ≈ propustnost paměti / velikost přečtených vah

DGX Spark má sjednocenou paměť s propustností **273 GB/s**. Pro hustý
(dense) model se čtou VŠECHNY váhy na každý token:

| model | v paměti | teoretický strop | naměřeno |
|---|---|---|---|
| qwen2.5:32b (Q4_K_M) | 28,5 GB | 273/28,5 = 9,6 tok/s | 10,5 |
| qwen2.5:72b (Q4_K_M) | 58,0 GB | 273/58,0 = 4,7 tok/s | 4,5 |

Naměřené hodnoty sedí na teoretický strop na jednotky procent – potvrzuje
to, že opravdu jde o propustnost a ne o nic jiného. (Ověřeno i tím, že
oba modely byly 100 % v paměti, žádný offload – `/api/ps`, `size` vs.
`size_vram`.)

**MoE (Mixture of Experts) tenhle vztah rozbíjí.** Vrstvy jsou rozdělené
na desítky „expertů" a malá routovací síť před každou vrstvou vybere,
kteří **2–4 experti** daný token zpracují. Ostatní se vůbec nečtou. Takže:

- **celkových parametrů**: 122 mld. → musí být v paměti
- **aktivních na token**: řádově jednotky miliard → jen ty se čtou

Čte se tedy zlomek vah, a protože čtení je to úzké hrdlo, model je
rychlejší, i když je „větší". Kvalitu si drží proto, že se experti během
tréninku specializují a dohromady pojmou víc znalostí, než by se vešlo
do hustého modelu téže rychlosti.

**Ověřeno z manifestu modelu** (`POST /api/show`), ne odhadem:

    family                  qwen35moe
    parameter_size          125.1B          (Q4_K_M)
    expert_count            256
    expert_used_count       8               <- aktivní na token
    block_count             48
    embedding_length        3072
    context_length          262144

**8 expertů z 256** = aktivuje se ~3 % expertních parametrů na token.
Zpětný dopočet z naměřených ~29 tok/s to potvrzuje: 273 / 29 ≈ **9,4 GB
čtených na token**, proti 58 GB u hustého 72B – tedy zhruba šestina.

**Dvě věci navíc, které z manifestu vypadly a počítáme s nimi jinde:**

- **`context_length` je 262 144 tokenů** nativně. Celý náš korpus sekcí
  má dohromady ~100 tis. znaků, takže délka dokumentu přestává být téma.
  (Serverové `num_ctx` je ale pořád to, co rozhoduje – a prompt delší než
  `num_ctx` Ollama tiše usekne, viz zápis o num_ctx níž.)
- **Model má vision část** (`qwen35moe.vision.*`, 27 bloků). Je tedy
  multimodální – použitelný na obrázky/scany bez nasazování dalšího modelu.
  Zatím nepotřebujeme, ale je dobré o tom vědět.

**Proč je to důležité zrovna pro DGX Spark:** má hodně paměti (128 GB),
ale na svou velikost málo propustnosti (273 GB/s – pro srovnání, H100 má
přes 3 TB/s). To je přesně profil, kde **hustý 70B model je odsouzený ke
4 tok/s, zatímco 122B MoE jede 29**. MoE potřebuje hodně paměti a málo
propustnosti; Spark má hodně paměti a málo propustnosti. Sedí to na sebe.

**Poučení: počet parametrů neříká nic o rychlosti, dokud nevíš, jestli je
model hustý nebo MoE.** Náš dřívější odhad „72B je 2× větší než 32B, tak
bude 2× pomalejší" byl postavený na předpokladu, který u MoE neplatí ani
v jednom směru. Při volbě modelu se ptát na **aktivní** parametry, ne na
celkové – a stejně to změřit.

**Srovnání s cloudem (gpt-5-nano)** na téže slovníkové úloze: kvalitativně
remíza, všech 10 termínů správně u obou. Ale:

| | tokenů výstupu | čas |
|---|---|---|
| qwen3.5:122b | 199 | 6,8 s |
| gpt-5-nano | **4 930** | 50,3 s |

gpt-5-nano je reasoning model, takže drtivá většina z těch 4 930 tokenů
jsou skryté uvažovací tokeny – **které se účtují**. Na slovník o pár
stech termínech by to byl násobek očekávané ceny. Lokální 122b je tu
7× rychlejší, spotřebuje 25× míň tokenů, stojí nula a data neopustí síť.
Cloud tedy jen jako kontrolní vzorek, ne jako nástroj.

## POZOR NA PENÍZE (OpenAI)

Na účtu jsou jen jednotky dolarů. Používat **výhradně `gpt-5-nano`**
(`config.OPENAI_MODEL`). **Nepouštět `gpt-4o` ani `gpt-4o-mini`** –
gpt-4o stojí násobně víc. Klíč `legacy/key.yaml` se načítá přes
`config.nacti_openai_klic()`; soubor NENÍ validní YAML mapa (chybí mezera
za dvojtečkou), takže `yaml.safe_load()[...]` na něm spadne.

**Pořád platí:** „neuralgie" zůstává v indikacích i u 122b a u gpt-4o.
Model při extrakci opisuje termín ze zdroje, i když se mu řekne „bez
odborných termínů". Laický tvar musí vzniknout jako SAMOSTATNÁ úloha
(slovník), ne jako vedlejší požadavek v extrakčním promptu.

---

## 2026-08-18 — 32B vs 72B: strukturu zvládnou stejně, liší se ČEŠTINA

Měřeno na PARALEN 4.8 (2 604 zn → 1 479 po ořezu), stejný prompt.

| | čas | položek | frekvence | orgánové systémy |
|---|---|---|---|---|
| qwen2.5:32b | 128,7 s | 15 | shodné | shodné |
| qwen2.5:72b | 443,4 s | 15 | shodné | shodné |

**Strukturní výsledek je totožný** – stejné účinky, stejné frekvence,
stejné orgánové systémy. 72B je 3,4× pomalejší a na struktuře nepřidá nic.

**Rozdíl je výhradně v laickém překladu**, a je zásadní:

| odborný termín | 32B | 72B |
|---|---|---|
| anafylaktický šok | „severe alergická reakce" | „těžká alergická reakce" |
| neutropenie | „nízký počet neutrofilů (typ **bílkovej krvinek**)" | „nízký počet neutrofilů" |
| agranulocytóza | „úplný nedostatek **bílkovej krvinek** bez granul" | „nízký počet granulocytů" |
| bronchospazmus | „**zadrhnutí v plicích, těžký dýchání**" | „zúžení dýchacích cest" |
| žloutenka | „**žloutnou kůže a běla očí**" | „žlutá barva kůže a očí" |
| cytolytická hepatitida | „nadměrné ztráta buněk **v jatech**" | „zánět jater s poškozením buněk" |

32B míchá angličtinu („severe"), obecnou češtinu („bílkovej", „těžký
dýchání") a tvoří nesmysly. Pro aplikaci určenou laikům je takový výstup
nepoužitelný – a je to přesně to pole, které uživatel uvidí.

**Důsledek pro návrh:** dělit úlohu podle toho, co který model umí.
Struktura (účinek, frekvence, orgánový systém) na 32B, laický překlad
na 72B. A protože se odborné termíny napříč léčivy **opakují**
(trombocytopenie, angioedém, nauzea…), laický tvar nemusí vznikat
znovu u každého léku – stačí **sdílený slovník pojmů**, vyrobený jednou
velkým modelem. To je zároveň varianta „D" z měření tvarů výstupu
(12 % tokenů oproti dnešnímu plochému poli).

---

## 2026-08-18 — Ořez sekce na jádro: co se smí uříznout a čím se to pojistí

**Zadání:** do modelu má jít nezbytné minimum. U dávkování jen základní
odstavec (zvláštní populace pryč), u nežádoucích účinků jen jádro
tabulky/seznamu, ne popisy a definice okolo.

**Výsledek:** sekce 4.8 + 4.2 přes 23 léčiv **173 614 → 102 815 znaků (59 %)**.
Ořez se dělá až v `extrahuj_sekci()`, NE při ukládání sekcí – na disku
zůstává úplný text, protože slouží ke kontrole proti PDF. Je to záměrná
ztráta informace a nikdy se nesmí použít na text ukazovaný uživateli.

**Mřížky `##` musí být v ořezových regexech volitelné.** Tři čtvrtiny
sekcí jdou ze surového PyMuPDF textu, kde nadpisy markdownové značky
nemají. S `^#{1,6}` ořez u 20 ze 46 sekcí neudělal vůbec nic.

**Dvě pojistky proti přeříznutí (obě vznikly z reálného selhání):**

1. BISACODYL má hned na začátku 4.2 varování „Děti ve věku 10 let nebo
   mladší…". Řez na první shodě nechal ze sekce jen nadpis (1 891 → 38 zn).
   Proto se hledá první podnadpis, po kterém ve zbytku **pořád zůstane
   konkrétní dávka**.
2. Samotný test na dávku nestačí: ALTHYXIN má v jádru „mikrogr amů"
   s rozbitým mezerováním, takže regex na jednotku neuspěje a ořez se
   vzdal (7 707 → 7 707). Přidána alternativa **minimální délky** 250 znaků.

Konečný stav: BISACODYL 1 891 → 502, ALTHYXIN 7 707 → 795, žádná sekce
neuříznutá na nadpis.

**Dvě krátké hodnoty jsou správně, ne chyba:** ALGESAL 4.8 → 78 znaků
(lék má jediný účinek, zbytek byl regulatorní boilerplate) a AFRIN 4.2 →
99 znaků (po odříznutí „Pediatrická populace" zbylo dávkování pro dospělé).
Ztráta dětského dávkování je vědomý důsledek zadání „jen základní odstavec".

---

## 2026-08-18 — Regrese: oprava regexu nadpisů rozhodila volbu zdroje textu

Při opravě jiné chyby (regex ukusoval první písmeno názvu sekce –
„erapeutické indikace") jsem oddělovač zúžil z `[\s.]+` na `[ \t.]+`.
Tím přestal odpovídat konci řádku – a v surovém PyMuPDF textu bývá číslo
sekce na vlastním řádku a název až na dalším („4.8\nNežádoucí účinky").

**Projev:** poměr zdrojů se převrátil z **21 md / 71 raw** na **78 md /
14 raw**. Sekce se pořád „našly u všech léčiv", takže kontrolní hláška
nic nehlásila – jen tiše spadly na markdownový fallback. Tím se vrátila
přesně ta vada, kvůli které pravidlo volby zdroje vzniklo: Docling
u formátu s frekvencí na vlastním řádku přiřadí účinek špatné frekvenci.

**Oprava:** `[\s.]+(?=\S)` – `\S` v lookaheadu (neukousne první písmeno)
a `\s` v oddělovači (umí konec řádku). Po opravě **72 raw / 20 md**.

**Poučení:** u téhle pipeline nestačí kontrolovat „našlo se to". Souhrn
na konci `extrahuj_sekce.py` vypisuje poměr `docling_md` / `pymupdf_raw`
a **ten poměr je regresní test** – když se skokově změní, něco se rozbilo.

---

## 2026-08-18 — Čas extrakce řídí VÝSTUPNÍ tokeny, ne vstup ani num_ctx

Měřeno skriptem `bench_extrakce.py` na IFIRMASTA (0500896), sekce 4.8,
4 951 znaků. Ollama vrací v odpovědi rozpad času (`prompt_eval_duration`,
`eval_duration`, `load_duration`) – zapracováno do `ollama_client.Metriky`.

**Rozpad času na jednom volání (qwen2.5:32b):**

| fáze | tokenů | čas | rychlost |
|---|---|---|---|
| načtení vstupu | 2 537 | 3,1 s | 818 tok/s |
| generování výstupu | 400 | 38,2 s | **10,5 tok/s** |

Načtení vstupu je **8 % času**. Zkrácení vstupu tedy ušetří sekundy,
zatímco výstup stojí minuty.

**num_ctx nemá na rychlost vliv** (stejný prompt, jen jiná alokace):

| num_ctx | 4096 | 8192 | 16384 | 32768 |
|---|---|---|---|---|
| tok/s | 10,5 | 10,5 | 10,4 | 10,4 |

Attention se počítá přes tokeny, které v cache **reálně jsou**, ne přes
alokovanou velikost. Snížení `num_ctx` ušetří **paměť** (KV cache je
~320 kB/token u 72B, tj. ~10,2 GB při 32768), ale ne čas.

**POZOR – tichý ořez:** prompt delší než `num_ctx` Ollama bez chyby
usekne. Nejdelší sekce 4.8 v korpusu je ABOXOMA: 34 754 znaků, což je ale
jen **5 845 tokenů** (změřeno přes `prompt_eval_count`, ne odhadnuto –
odhad z počtu znaků dával 10 900 a byl špatně, protože ta sekce je ze
dvou třetin výplňové mezery v tabulce). I tak **nejít pod 16384**: musí
se vejít vstup + prompt + celý výstup, a tiché zmizení nežádoucích účinků
je u aplikace pro laiky nejhorší možné selhání.

**Zhuštění markdown tabulky se nevyplatí kvůli rychlosti.** Docling
zarovnává buňky na šířku sloupce, takže u ABOXOMA je **67 % sekce mezery**.
Odstranění výplně vypadá jako obrovská úspora, ale v tokenech skoro není –
tokenizér běhy mezer komprimuje sám:

| | znaky | tokeny |
|---|---|---|
| ABOXOMA | 34 754 → 9 632 (−72 %) | 5 845 → 4 579 (**−22 %**) |
| OLANZAPIN | 26 241 → 12 970 (−51 %) | 6 563 → 6 053 (**−8 %**) |

A protože vstup je 8 % času, celkový dopad na rychlost je pod 2 %.
Zhuštění má smysl leda kvůli kvalitě (míň šumu pro model), ne kvůli času.
**Poučení: délku vstupu měřit v tokenech přes `prompt_eval_count`,
nikdy neodhadovat z počtu znaků.**

**Skutečná páka je tvar výstupního JSON.** Dnešní ploché pole opisuje
název orgánového systému a frekvenci u každé z 33 položek. Spočítáno na
reálném výsledku:

| tvar výstupu | tokenů | podíl | 32B @10,5 tok/s |
|---|---|---|---|
| ploché pole, SOC+frekvence u každé položky | 1 498 | 100 % | 143 s |
| seskupené podle SOC a frekvence | 769 | 51 % | 73 s |
| SOC+frekvence čtené deterministicky ze zdroje | 504 | 34 % | 48 s |
| + laický tvar ze sdíleného slovníku pojmů | 181 | **12 %** | 17 s |

**Důsledek pro návrh:** frekvence i orgánový systém jsou ve zdroji napsané
doslova – změřeno, že **22 z 23 dokumentů** je má buď jako buňku tabulky
(65 %), nebo jako explicitní řádek (39 %); jediná výjimka je ALGESAL
(čistá próza). Nechat je číst regexem místo modelu tedy zároveň
**zpřesní** (frekvence je zdravotní údaj, odhadovat ho nelze) a
**zrychlí** (ubere dvě třetiny výstupu).

---

## 2026-08-18 — Rozložení práce v korpusu je extrémní (Pareto)

Delší sekce = víc účinků = delší výstup = víc času. Rozložení délek
sekce 4.8 přes 23 léčiv:

| práh délky 4.8 | zbyde léčiv | ušetří práce | vyřadí |
|---|---|---|---|
| < 20 000 zn | 20/23 | 40 % | ACTELSAR, ABOXOMA, OLANZAPIN |
| < 15 000 zn | 19/23 | 54 % | + ACLEXA |
| < 10 000 zn | 17/23 | 64 % | + ABLYMICO, ACYLCOFFIN |

**Čtyři léčiva (17 %) dělají přes polovinu veškeré práce.**

**Proč práh podle délky přesto NEPOUŽÍT jako první volbu:** vyřadil by
OLANZAPIN_VIATRIS – antipsychotikum, tedy přesně ten typ léku, na kterém
v legacy fázi selhal dotaz na schizofrenii. Délka sekce 4.8 koreluje se
závažností léku, takže práh systematicky odstraní psychiatrika a
onkologika. Demo by pak umělo hledat jen triviální léky.

**Dělení sekce po orgánových systémech to nespraví:** u ABOXOMA našel
Docling jen 4 nadpisy SOC, takže nejdelší jednotlivý blok má pořád
31 221 znaků.

**Hlavní argument:** extrakce je **jednorázový ingest**, ne dotaz. Celý
korpus (23 léčiv × 4 sekce, ~352 600 znaků) vyjde na ~87 000 výstupních
tokenů ≈ 2,3 h v dnešním tvaru, ~45 min v kompaktním. Pustí se jednou
přes noc. Rychlost dema závisí na vyhledávání, ne na extrakci.
Práh délky si nechat jako pojistku, ne jako výchozí řešení.

---

## 2026-08-14 — Orgánový systém (MedDRA SOC) je použitelný jako filtr

**Nápad:** u nežádoucích účinků nefiltrovat jen podle frekvence, ale i podle
orgánového systému. Uživatel neví, co je „tachykardie", ale umí říct „srdce".

**Ověření konzistence** (na třech dokumentech, sekce 4.8):

| systém | PARALEN | OLANZAPIN | IFIRMASTA |
|---|---|---|---|
| Poruchy krve a lymfatického systému | ✓ | ✓ | ✓ |
| Poruchy imunitního systému | ✓ | ✓ | ✓ |
| Respirační, hrudní a mediastinální poruchy | ✓ | ✓ | ✓ |
| Poruchy jater a žlučových cest | ✓ | ✓ | ✓ |
| Poruchy kůže a podkožní tkáně | ✓ | ✓ | ✓ |

Názvy jsou **doslova shodné**, ne jen podobné. Je to MedDRA System Organ
Class se standardizovanými českými překlady – asi 27 tříd celkem, jeden
dokument použije 6–15. Nízká kardinalita + řízený slovník = ideální filtr.

**Implementace:** sloupec `organovy_system` v `leciva_search`, vyplněný
jen u řádků `sekce='nezadouci_ucinky'`. Platí pro něj stejné pravidlo
jako pro `sekce` a `frekvence`: **do hledaného textu NEPATŘÍ**, jinak by
se „Srdeční poruchy" opakovalo přes stovky řádků a znehodnotilo fulltext.

**Výhoda oproti sémantice:** dotaz „dělá to něco se srdcem" nemusí doufat,
že vektor spojí „tachykardii" se „srdcem" – router přeloží dotaz na
`WHERE organovy_system = 'Srdeční poruchy'` a je to deterministické.

**Opatrnost k použití pro vyloučení:** filtr je obousměrný, ale u aplikace
pro laiky by se neměly kategorie nežádoucích účinků tiše skrývat. Filtrovat
až tehdy, když se uživatel sám zeptá úžeji – ne jako výchozí zúžení výpisu.

---

## 2026-08-14 — EudraVigilance nenahradí extrakci z SPC (jiná data, ne jen jiný formát)

Zvažovalo se, jestli místo vytěžování PDF nevzít nežádoucí účinky
z mezinárodní databáze EudraVigilance (adrreports.eu).

**Závěr: nejde, a není to otázka formátu ani API.** Jsou to jiná data,
která odpovídají na jinou otázku.

| | SPC, sekce 4.8 | EudraVigilance |
|---|---|---|
| co to je | schválený seznam v registrační dokumentaci | spontánní hlášení podezření |
| frekvence | kategorie „velmi časté ≥1/10", „vzácné"… | žádné – jen počty hlášení |
| jmenovatel | z klinických studií | neznámý (neví se, kolik lidí lék bralo) |
| zkreslení | – | výrazné (co se nahlásí, ne co se stane) |
| aktualizace | při změně registrace | týdně |

Naše aplikace má ukazovat, **co o léku říká jeho oficiální dokumentace**,
včetně kategorie frekvence, na kterou chceme filtrovat. To v EudraVigilance
prostě není – jsou tam běžící součty hlášení, ne schválené kategorie.

**K API:** veřejné API ani hromadné stažení EMA nenabízí. Přístup je přes
webové reporty, line listings a formuláře jednotlivých případů na portálu.

Ponecháno jako možné budoucí obohacení („tento účinek byl X-krát hlášen"),
ale ne jako náhrada extrakce z SPC.

Zdroje: adrreports.eu/en/data_source.html, EMA user manual k portálu.

---

## 2026-08-14 — !!! Docling ZAMĚŇUJE frekvence u SPC bez tabulky !!!

Nejzávažnější nález zatím. Není to ztráta dat, ale **záměna** – vzniknou
data, která vypadají správně, ale jsou nepravdivá.

**Postižený formát:** SPC, kde nežádoucí účinky nejsou v tabulce, ale jako
posloupnost odstavců typu klíč–hodnota (IFIRMASTA). PyMuPDF tam taky
nenajde ani jednu tabulku – opravdu žádná není.

**Co se stane:** Docling slepí hodnotový řádek s hodnotou následujícího
klíče a tím posune celé přiřazení.

Poruchy nervového systému:

| zdroj | Časté | Není známo |
|---|---|---|
| PDF (správně) | závratě, ortostatické závratě* | vertigo, bolesti hlavy |
| Docling (CHYBNĚ) | závratě, ortostatické závratě* **vertigo, bolesti hlavy** | (prázdné) |

Cévní poruchy:

| zdroj | Časté | Méně časté |
|---|---|---|
| PDF (správně) | ortostatická hypotenze* | návaly horka |
| Docling (CHYBNĚ) | ortostatická hypotenze* **návaly horka** | (prázdné) |

Z „návalů horka“ se tak stane častý nežádoucí účinek, přestože jsou méně časté.
Pro aplikaci, kde je frekvence hlavní filtr pro laika, je to vážné.

**Surový text z PyMuPDF je u tohoto formátu SPRÁVNÝ** – zachovává řádkování:

    Poruchy nervového systému:
    Časté:
    závratě, ortostatické závratě*
    Není známo:
    vertigo, bolesti hlavy

**Návrh řešení:** když Docling v sekci 4.8 nevyrobí tabulku, brát obsah
té sekce ze surového textu PyMuPDF, ne z markdownu. Docling se použije
jen na nalezení hranic sekcí (nadpisy zvládá dobře).

**U pravých tabulek Docling funguje správně** – ověřeno na PARALENU,
frekvence přiřazené přesně, včetně rozdělení jednoho orgánového systému
do dvou řádků podle frekvence.

---

## 2026-08-14 — Rozbité mezerování znaků v PDF (vada zdroje, ne extraktoru)

**Projev:** `Dávkování a zp ů sob podání`, `pot ř eb lé č by ka ž dého` –
osamocená písmena obklopená mezerami.

**Není to vada PyMuPDF ani Doclingu** – ověřeno, oba extraktory vracejí
totéž. Je to vlastnost zdrojového PDF (špatné šířky mezer ve fontu).
Proto se normalizace musí aplikovat na OBA zdroje textu, ne jen na jeden;
poprvé jsem to opravil jen v `surovy_text()` a u dokumentu, který bral
sekci z Doclingu, se to vůbec neprojevilo.

**Rozsah:** 1 z 23 dokumentů (ALTHYXIN), 61 výskytů, 7 % slov. Výjimka,
ne systémový problém – nemá smysl kolem toho stavět velké řešení.

**Řešení:** `common/konverze.py::sprav_mezerovani()` opravuje jednoznačný
případ – osamocené písmeno S DIAKRITIKOU mezi dvěma písmeny.

Bezpečnost pravidla: písmena `ě š č ř ž ý á í é ú ů ď ť ň` nejsou v češtině
samostatná slova, na rozdíl od `a i k o s u v z`. Kdyby se pravidlo
rozšířilo na všechna písmena, slepilo by legitimní předložky se sousedy.

Po opravě zbývá 0 výskytů. Zbytkové poškození bez diakritiky
(`individuálníc h`, `mikrogr amů`) se neřeší – regexem to nejde odlišit
od legitimního dělení a modely si s takovým textem poradí.

---

## 2026-08-14 — Stav extrakce musí být explicitní, NULL nestačí

**Problém:** `NULL` v datech znamená dvě neslučitelné věci a nejdou rozlišit:
lék buď opravdu nemá uvedené nežádoucí účinky, nebo se je nepodařilo vytáhnout.

Pro aplikaci pro laiky je to zásadní. Nesmí vzniknout dojem „tenhle lék nemá
žádné nežádoucí účinky", když jsme je jen nedokázali zpracovat. Přiznaná
mezera je mnohem lepší než tiché zamlčení.

**Řešení:** čtvrtá tabulka `extrakce_stav`, řádek na (lék × sekce), se stavy:

    ok, neovereno, chybi_v_dokumentu, selhala_extrakce,
    zamitnuto_kontrolou, prazdna

Pravidlo pro zobrazení: `ok` → normálně; `chybi_v_dokumentu` → „SPC tuto
sekci neobsahuje"; cokoli jiného → „sekci se nepodařilo zpracovat".
Prázdný seznam se NIKDY nezobrazuje jako nepřítomnost účinků.

**Slouží třem věcem najednou:**
1. vyhledávání ví, kde nemá co hledat (místo tichého „nenalezeno")
2. Test 0 v evaluaci čte pokrytí přímo odsud
3. sloupce `format_sekce` + `zdroj_textu` + `model_extrakce` dají dohromady
   evidenci, KTERÁ kombinace selhává – přímý podklad pro optimalizaci
   místo ladění poslepu

**Dělba modelů:** extrakce na menším (qwen2.5:32b), kontrola na větším
(qwen2.5:72b). Kontrola je levnější úloha (krátký výstup, menšina případů)
a jiný model si méně pravděpodobně odsouhlasí vlastní chybu.

---

## 2026-08-14 — Změřeno na 23 léčivech: PĚT formátů sekce 4.8

Vzorek: 20 léčiv z 20 různých ATC skupin + 3 pilotní. Klasifikace
skriptem `analyza_formatu.py`.

| formát | podíl | zdroj pro extrakci |
|---|---|---|
| B) tabulka, řádek na účinek | 8/23 (35 %) | Docling markdown |
| A) matice, sloupce = frekvence | 7/23 (30 %) | Docling markdown |
| D) klíč–hodnota inline (`Časté: nevolnost`) | 5/23 (22 %) | surový text |
| C) klíč–hodnota, hodnota na dalším řádku | 2/23 (9 %) | **surový text (nutně)** |
| E) krátká próza (pár vět) | 1/23 (4 %) | surový text |

**Rozhodnutí o zdroji – jednoduché pravidlo:**

    sekce 4.8 obsahuje markdown tabulku  ->  Docling markdown
    neobsahuje                           ->  surový text z PyMuPDF

Pokrývá 100 % rizika bez spoléhání na detekci poškození. U formátů bez
tabulky markdown stejně nic nepřidává (není co strukturovat), zatímco
surový text zachovává řádkování věrně.

**Proč nespoléhat jen na detektor záměn:** detektor (frekvence bez obsahu)
zafungoval správně – označil IFIRMASTU a správně NEoznačil ACC, kde
Docling převedl formát C bezchybně. Ale poškození ve formátu C není
univerzální, je závislé na dokumentu, takže „detekuj a pak oprav" by
znamenalo spoléhat, že detektor chytí každý případ. U dat, kde záměna
frekvence znamená „vzácný účinek vydávaný za častý", je levnější
nespoléhat vůbec.

**Zajímavost:** zdrojové PDF u ACC míchá oba styly v jedné sekci
(`Méně časté:` s hodnotou na dalším řádku i `Velmi vzácné: Krvácení`
inline). Formát tedy není vlastnost dokumentu jako celku – prompt pro
extrakci musí počítat s tím, že se styly střídají i uvnitř jedné sekce.

**Čas konverze na větším vzorku:** 41,9 s na dokument (23 dokumentů,
963 s celkem) – víc než u pilotu, protože vzorek obsahuje větší SPC.
Odhad 35 min pro 50 léčiv, ~5,8 h pro 500.

---

## 2026-08-14 — SPC mají nejméně TŘI různé formáty sekce 4.8 (překonáno – viz výše)

Formát NEZÁVISÍ na tom, jestli je registrace CZ nebo EU – ověřeno,
OLANZAPIN i IFIRMASTA jsou obě EU a mají formát jiný.

**1. Tabulka „řádek na účinek“** (PARALEN, CZ)

    | Orgánový systém | Frekvence | Nežádoucí účinek |
    | Poruchy kůže... | vzácné    | vyrážka, dermatitida |
    | Poruchy kůže... | velmi vzácné | závažné kožní reakce |

Docling zvládá správně.

**2. Matice, sloupce = frekvence** (OLANZAPIN, EU)

    | Velmi časté | Časté | Méně časté | Vzácné | Není známo |
    | Poruchy krve a lymfatického systému (řádek přes všechny sloupce) |
    |             | Eozinofilie, Leukopenie | ... |

Orgánový systém je slučovaný řádek přes celou šířku, účinky jsou pak
v příslušném frekvenčním sloupci. Docling to převede, ale výsledek
má opakovaný název systému ve všech sloupcích – jde zpracovat, ale
prompt pro extrakci s tím musí počítat.

**3. Odstavce klíč–hodnota, bez tabulky** (IFIRMASTA, EU)

    Poruchy nervového systému:
    Časté:
    závratě, ortostatické závratě*

Docling zde ZAMĚŇUJE frekvence – viz zápis výše.

**Důsledek:** prompt pro převod do JSONB musí umět všechny tři, nebo
se musí formát detekovat a volit podle něj zdroj i prompt.
**Nevíme, kolik dalších formátů existuje** – tři jsme našli na třech
dokumentech, což naznačuje, že jich bude víc. Před během na celém
vzorku je potřeba projet víc léčiv a formáty spočítat.

---

## 2026-08-13 — Docling na Windows padá bez MSVC: nutné vypnout torch.compile

**Projev:** Konverze skončila chybou, ne varováním:

    ConversionError: Conversion failed for: spc.pdf with status: failure.
    Errors: InvalidCxxCompiler: Compiler: cl is not found.

**Příčina:** Docling si tahá torch a ten se pokouší JIT kompilovat
(`torch._inductor` kontroluje podporované vektorové instrukce). Hledá
MSVC `cl.exe`, nenajde ho a **shodí celou konverzi**. Ve výstupu to
přitom vypadá jako neškodné varování – opakovalo se to jedenáctkrát
jako `TORCHDYNAMO` hláška, takže jsem to nejdřív odepsal jako šum.

**Řešení:** Vypnout torch.compile přes proměnné prostředí, nastavené
DŘÍV než se torch naimportuje. V `common/konverze.py` na začátku modulu:

    os.environ.setdefault("TORCHDYNAMO_DISABLE", "1")
    os.environ.setdefault("TORCH_COMPILE_DISABLE", "1")

Pro naše použití (inference layout modelu) torch.compile potřeba není.
Alternativa by byla doinstalovat Visual C++ Build Tools – zbytečně těžké.

**Ověření:** PARALEN (8 stran) se pak zkonvertoval za 26,6 s,
20 429 znaků, 61 nadpisů.

**Ponaučení pro čtení logů:** Když v logu opakovaně bliká varování
a zároveň nevzniká výstup, nestačí varování odfiltrovat jako šum –
je potřeba najít poslední řádek, kde se rozhodlo o výsledku. Připravil
jsem se o čas tím, že jsem výstup pouštěl přes `tail`, takže se skutečná
chybová hláška ani nedostala do logu.

---

## 2026-08-13 — Ořez EU dokumentů patří PŘED konverzi, ne za ni

**Zjištění:** EU registrace jsou slepenec – Příloha I je SPC (chceme),
Příloha II a dál jsou podmínky registrace, obal a příbalová informace
(nechceme). Původní návrh ořezával až vygenerovaný markdown, takže
Docling zbytečně zpracovával celý dokument.

**Naměřené úspory na pilotu:**

| dokument | stran celkem | Příloha II na str. | ke konverzi | úspora |
|---|---|---|---|---|
| PARALEN (CZ) | 8 | — | 8 | 0 % |
| IFIRMASTA (EU) | 46 | 15 | 14 | −70 % |
| OLANZAPIN (EU) | 96 | 20 | 19 | −80 % |
| **celkem** | **150** | | **41** | **−73 %** |

**Implementace:** `common/konverze.py::orizni_pdf_pred_konverzi()` –
PyMuPDF najde stránku s Přílohou II (řádově milisekundy), vyrobí ořezané
PDF a Doclingu se předloží jen to. Čísla stránek zůstávají shodná
s originálem, takže odkazy do PDF dál platí.

Detekce hlídá, aby "PŘÍLOHA II" nechytila "PŘÍLOHA III" – negativní
lookahead `P[ŘR]ÍLOHA\s+II(?!I)`.

Ponechána i pojistka: kdyby stránkový ořez nezabral (jiné formátování),
zkusí se ještě ořez na úrovni markdownu jako dřív.

---

## 2026-08-13 — Vyhledávací API: dva povinné parametry, jinak vrací jen zrušené registrace

**Podstata:** `POST /prehledy/v1/dlp` obsahuje celý registr včetně platných
registrací. Ale **bez dvou konkrétních parametrů vrací jen zrušené**, což
vypadá, jako by aktuální léčiva neobsahovalo vůbec.

**Správné volání:**

    {"filtr": "PARALEN", "atc": "N02BE",
     "stavZruseni": "N",      # jen platné registrace
     "ochrannyPrvek": "X",    # NEROZHODUJE (ne "nesmí mít OP"!)
     "pocet": 50, "stranka": 1,
     "sort": ["nazev","je_dodavka"], "smer": "asc"}

**Význam hodnot (ověřeno měřením, ne dokumentací):**

| parametr | hodnota | význam | PARALEN | IFIRMASTA (Rx) |
|---|---|---|---|---|
| stavZruseni | `N` | jen platné | 27 (vše stav R) | 24 |
| stavZruseni | `Z` | jen zrušené | 84 | – |
| stavZruseni | `V` / `""` | vše dohromady | 111 | – |
| ochrannyPrvek | `X` | nerozhoduje | 27 | 24 |
| ochrannyPrvek | `A` | musí mít OP | 0 | 24 |
| ochrannyPrvek | `N` | nesmí mít OP | 27 | 0 |
| ochrannyPrvek | `""` | nevrátí nic | 0 | 0 |

Past je v tom, že **vynechání parametru není totéž jako "nefiltrovat"**.
Neutrální hodnotu `X` je nutné poslat explicitně. A `""` (prázdný řetězec),
což by člověk čekal jako "bez filtru", nevrací nic.

**Jak si správné parametry ověřit bez rozbalování JS:** GUI umí zkopírovat
aktuální nastavení filtru do schránky jako URL. V ní jsou vidět všechny
parametry včetně `stavZruseni="N"` a `ochrannyPrvek="X"`. Když se příště
API zachová nečekaně, tohle je nejrychlejší cesta ke zjištění, co posílá
oficiální klient. (Testovací instance: testprehledy.sukl.cz, produkční
prehledy.sukl.gov.cz – parametry stejné.)

Zdroj správných hodnot: výchozí objekt `To` v JS bundlu webové aplikace
(`js/prehled_leciv.min.js`) – `stavZruseni:"N", ochrannyPrvek:"X"`.
Podle nápovědy v UI to vypadá, že `X` znamená "LP nesmí být opatřen OP",
ale měření ukázalo opak: `X` = nerozhoduje, pro "nesmí" je `N`.

**Moje chyba, kterou to způsobilo:** Nejdřív jsem z toho uzavřel, že API
je archiv zrušených registrací a discovery se musí dělat stažením detailů
všech 69 355 kódů. Testoval jsem přitom jen jednotlivé parametry samostatně
(`stavRegistrace:"R"`, `stavZruseni:"N"`, `jeDodavka:true`) — každý zvlášť
vracel nulu, takže jsem to prohlásil za slepou uličku. Až poslání celé sady
naráz ukázalo, že se ty parametry ovlivňují: `stavZruseni:"N"` samotné dá
0 výsledků, ale spolu s `ochrannyPrvek:"X"` dá 27 platných.

**Ponaučení:** U API, které nemá dokumentaci, nestačí zkoušet parametry
po jednom — je potřeba zreplikovat celou sadu, kterou posílá jeho vlastní
klient. Negativní výsledek jednotlivého parametru neznamená, že cesta
nevede k cíli.

**Stav implementace:** `SuklClient.hledej()` posílá oba parametry jako
výchozí, takže volající se o to nemusí starat. Ověřeno: N02BE=470,
R06A=813, A02B=1203, J01=1400, R01A=150 platných registrací, všechny
dohledatelné přes `/dlp/v1`.

Funkce `postav_pool()` (stažení detailů všech léčiv + lokální filtrování)
zůstává v modulu jako záložní cesta, kdyby se nedokumentované API rozbilo.
Pro běžný provoz se nepoužívá.

---

## 2026-08-13 — Pilotní léčiva (ověřené kódy)

Kódy, které fungují na dokumentovaném API a mají SPC PDF:

| kód | název | typ | proč v pilotu |
|---|---|---|---|
| 0254048 | PARALEN 500MG | CZ, OTC | jednoduchý CZ dokument, 60 kB |
| 0500896 | IFIRMASTA 300MG | EU, Rx | EU registrace → test ořezu na Příloha II, 258 kB |
| 0500778 | OLANZAPIN VIATRIS 20MG | EU, Rx | bohatá MedDRA tabulka NÚ (~10 tis. znaků), 766 kB |
