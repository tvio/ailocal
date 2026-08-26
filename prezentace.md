# Sémantické vyhledávání v lécích — jak to funguje

Podklad pro vedení IT. Popisuje celý řetězec od výběru léků po vyhledávání,
bez potřeby znát detaily implementace.

**Co to je:** aplikace, které položíte otázku běžnou češtinou („mám reflux",
„volně prodejný lék na bolest hlavy") a ona najde odpověď v oficiálních
dokumentech SÚKL — včetně odkazu na konkrétní stranu původního PDF.

**Proč to není jen fulltext:** uživatel napíše „pálí mě žáha", v dokumentu
stojí „pyróza". Fulltext nenajde nic. Tenhle systém najde MAALOX.

**Všechno běží lokálně.** Žádná data neopouštějí síť.

---

## 1. Výběr léků do korpusu

Korpus má **32 léčiv** a je záměrně malý a vybraný tak, aby na něm šlo
demo předvést.

**Požadavek:** léky, které laik zná a má doma. Ne onkologika a infuze.
Výběr se dělá podle **ATC skupiny** — mezinárodní klasifikace, kterou
každému léku přiděluje SÚKL. Je to řízená hodnota, nic se neodhaduje.

| ATC | co to je |
|---|---|
| N02BE, N02BA | paracetamol, kyselina acetylsalicylová |
| M01A, M02A | ibuprofen a masti na bolest |
| A02A, A02B | antacida, vředová choroba a **IPP** |
| A07 | **léky na průjem** |
| R05, R06A, R01A | kašel, alergie, **ucpaný nos** |
| J01 | **antibiotika** |
| C09, C10A, A10B | tlak, cholesterol, cukrovka |

**Limit na skupinu je nutný.** Léky na tlak a cukrovku jsou v registru tak
časté, že by bez stropu zabraly většinu vzorku a demo by bylo o hypertenzi
místo o bolesti a alergii.

**EU vs. CZ registrace** se liší formátem dokumentu (viz krok 3), takže
korpus schválně obsahuje obojí — jinak by se na rozdíl nepřišlo.

Korpus se pak ještě doplňoval cíleně, aby v každé skupině byl
**volně prodejný, na předpis hrazený i na předpis nehrazený** lék.
Bez toho by filtrování vracelo jeden nebo žádný výsledek.

---

## 2. Dva druhy vstupních dat

Tohle je klíčové rozlišení, na kterém stojí důvěryhodnost celého systému.

| | odkud | jak vzniká | spolehlivost |
|---|---|---|---|
| **Strukturovaná data** | API SÚKL (Přehled léčiv) | přímo, žádný model | **100 %** |
| **Text ze SPC** | PDF dokument | parsování + jazykový model | ověřuje se |

**Strukturovaná data z API** — název, síla, léková forma, účinné látky,
ATC, způsob výdeje (Rx/OTC), hrazení z pojištění, kód SÚKL. U těchto
údajů **nemůže vzniknout chyba překladu**, protože je nikdo nepřekládá.

Hrazení je zvláštní případ: **není to atribut léku**, ale příslušnost do
seznamu. SÚKL vydává seznam kódů hrazených přípravků (8 604 položek)
a lék je hrazený, pokud v něm je. Není to totéž co „na předpis" —
v korpusu je několik léků na předpis, které hrazené nejsou.

**Text ze SPC** — indikace (na co lék je), kontraindikace (kdy se nesmí),
nežádoucí účinky a dávkování. Tohle je volný text v PDF a musí se
vyparsovat. Tady vzniká riziko a proto na to navazují dvě kontroly.

---

## 3. Převod PDF do textu

Používají se **dva nástroje** a vybírá se podle sekce:

| nástroj | k čemu | proč |
|---|---|---|
| **Docling** (backend `pypdfium2`) | indikace, kontraindikace | rozumí struktuře, dělá nadpisy a tabulky |
| **PyMuPDF** (surový text) | nežádoucí účinky, dávkování | zachová řádky tabulek tak, jak jsou |

**Proč dva:** Docling je lepší na strukturu, ale u tabulek nežádoucích
účinků slévá řádky dohromady a ztrácí vazbu „účinek → frekvence". To je
nebezpečné — účinek by dostal špatnou frekvenci. Surový text tuhle vazbu
zachová.

Výchozí backend Doclingu navíc rozbíjel mezery mezi znaky („zp u sob")
na 1 232 místech; po přepnutí na `pypdfium2` jich zbylo 109.

### Ořez EU dokumentů

U **CZ registrace** je SPC samostatný dokument. U **EU registrace** je
SPC a příbalový leták slepený do jednoho PDF a druhá půlka začíná
nadpisem přes celou stránku **„Příloha II"**. Všechno od něj dál se
zahazuje — jinak by se v datech objevily texty určené pacientovi
promíchané s odborným textem.

### Další pravidla ořezu

Sekce se ještě zkracují na jádro, aby model nedostával balast:

- **dávkování** — jen základní dávkování, bez zvláštních populací
- **nežádoucí účinky** — jen tabulka nebo seznam, bez úvodní prózy
  a bez popisu vybraných účinků
- **indikace a kontraindikace** — beze změny, jsou krátké

Ořez má pojistky: nikdy nesmí zahodit tabulku a nikdy nesmí zkrátit sekci
pod rozumnou délku.

---

## 4. Vytažení jednotlivých sekcí

Sekce se hledají podle **čísla v nadpisu** podle jednotné struktury SPC:

    4.1  Terapeutické indikace
    4.2  Dávkování a způsob podání
    4.3  Kontraindikace
    4.8  Nežádoucí účinky

Zní to triviálně, ale právě tady vznikaly nejtišší chyby — sekce se
prostě nenašla a vypadalo to, že v dokumentu není:

| co se stalo | důsledek | řešení |
|---|---|---|
| OCR zaměnilo číslici: `4.l` místo `4.1` | zmizela celá sekce indikací | číslice se hledají i ve svých záměnách (`1`↔`l`,`I`; `0`↔`O`) |
| slepené nadpisy: `## 4. KLINICKÉ ÚDAJE4.1 TERAPEUTICKÉ INDIKACE` | totéž | záložní vzor povolí číslo kdekoliv v nadpisu |

**Poučení pro management:** u dokumentů z OCR se nedá spoléhat na přesnou
shodu znaku. Selhání je navíc tiché — vypadá jako chybějící data ve zdroji,
ne jako chyba programu. Proto na to existuje kontrolní výpis, který hlásí,
kolik sekcí se našlo a kolik ne.

---

## 5. Převod sekcí do strukturovaného JSON

Text sekce dostane jazykový model se šablonou a vrátí **strukturovaná
data**. Každá sekce má vlastní tvar.

### Indikace a kontraindikace

```json
{ "doslovne": "akutní bronchitida",
  "laicky":   "náhlý zánět průdušek",
  "skupina":  "děti od 2 let" }
```

**Dvojice doslovný + laický tvar je zásadní.** Doslovný je kotva ke zdroji
(dá se ověřit, že v dokumentu opravdu je), laický je to, co uvidí uživatel.

**Skupina pacientů** je samostatné pole, protože jeden lék má často jinou
indikaci pro dospělé a jinou pro děti. ACC má každou indikaci třikrát —
pro dospělé, dospívající a děti od 2 let.

### Nežádoucí účinky

```json
{ "ucinek":          "trombocytopenie",
  "ucinek_laicky":   "nízký počet krevních destiček",
  "frekvence":       "vzácné",
  "organovy_system": "Poruchy krve a lymfatického systému" }
```

**Frekvence** se normalizuje na šest hodnot podle evropské normy pro SPC:
velmi časté, časté, méně časté, vzácné, velmi vzácné, není známo. Díky
tomu se dá filtrovat („vzácné nežádoucí účinky").

**Orgánový systém** je třída z mezinárodního číselníku MedDRA — umožňuje
dotaz „nežádoucí účinky na srdce".

### Dávkování

```json
{ "pacient":   "děti 6–12 let (váha 20–25 kg)",
  "davka":     "250 mg",
  "frekvence": "3–4× denně",
  "poznamka":  null }
```

Jeden lék má typicky několik řádků — pro dospělé, pro děti, pro pacienty
s poškozením ledvin. ZYRTEC jich má šest.

### Jedna položka = jeden řádek

Původně model vracel celou indikaci jako jednu větu. Změřilo se, že to
škodí: MAALOX měl čtyři příznaky slepené dohromady („pálení žáhy, časté
říhání, vracení kyselého obsahu, bolest v břiše na lačno") a vyhledávání
pak netrefilo ani jeden pořádně.

| dotaz | slepená věta | vlastní řádek |
|---|---|---|
| pálí mě žáha | 0,63 | **0,90** |
| pořád říhám | 0,43 | **0,66** |

Rozdělení dělá **model**, ne mechanické dělení podle čárek — to by
uškodilo ve 3 z 5 případů („alergie na cefalosporiny, karbapenemy"
rozdělením ztratí „alergie na").

---

## 6. Převod odborných výrazů na laické

Tohle je **nejdražší část celé pipeline** a zároveň ta, která rozhoduje
o použitelnosti pro laika.

### Proč nestačí nechat to na modelu

Model požádaný o překlad téhož termínu vrátí pokaždé trochu jinou větu.
Změřeno: **každý pátý termín měl víc různých laických tvarů**, a
„pancytopenie" jich měla šest. Důsledek: uživatel hledá „nízký počet
krvinek", najde jeden lék a druhý mu unikne, protože ten má „pokles všech
krevních buněk".

### Řešení: číselník pojmů

    odborný termín  →  JEDEN kanonický laický tvar

Číselník **vzniká z dat**, ale zároveň je **řídí**. Když je termín
v číselníku, použije se tvar z něj a to, co model vygeneroval, se zahodí.

Tři vrstvy, poslední přebíjí:

| vrstva | kdo ji dělá | poznámka |
|---|---|---|
| generovaný číselník | model + kontrola | 593 dvojic |
| **ruční číselník** | **člověk** | 70 dvojic, přežije přeextrahování |
| pravidla bez modelu | kód | normalizace klíčů |

**Ruční opravy jsou v odděleném souboru schválně.** Kdyby byly ve stejném,
příští přegenerování by práci člověka přepsalo.

**Přínos:** oprava jednoho špatného překladu se udělá **jednou** a projeví
se u všech léků naráz.

---

## 7. Jak se ověřuje, že data sedí

Dvě nezávislé kontroly, obě běží automaticky.

### 7a. Deterministická kontrola — bez modelu, zadarmo

Ověřuje to, co jde ověřit strojově:

| sekce | co se kontroluje |
|---|---|
| nežádoucí účinky | je účinek **doslova** ve zdrojovém textu? sedí frekvence? sedí orgánový systém? |
| dávkování | je dávka doslova ve zdroji? porovnávají se **čísla**, ne text |
| indikace, kontraindikace | je pole `doslovne` ve zdroji? |

Porovnává se po normalizaci (malá písmena, bez diakritiky a mezer),
protože zdrojová PDF mají rozbité mezerování.

**Tahle kontrola je spolehlivá a nic nestojí.** Co projde, je označeno
jako ověřené a dál se neřeší.

### 7b. Kontrola jiným modelem

Co deterministická kontrola neumí posoudit, jde na **jiný model, než který
data vyrobil** (`gemma4:31b` proti `qwen3.5:122b`). Dostane zdrojový text
a vytažené položky a u každé rozhodne, jestli má ve zdroji oporu.

**Jiný model je záměr.** Model, který si něco vymyslel, si to při kontrole
sám neodhalí.

Vyřazuje se **jednotlivá položka, ne celá sekce** — dřív kvůli jedné vadné
položce padlo i 45 dobrých.

### Známá mezera — přiznaná

Laický tvar **se proti odbornému nikde neověřuje**. Ukázalo se to na
ERCEFURYLU: odborný text „Akutní průjem bakteriálního původu" je správně,
ale model z toho laicky udělal **„náhlý záškrt"**, tedy difterii. Prošlo to
oběma kontrolami, protože obě kontrolují odborný text.

Je to zapsané jako úkol. Číselník pojmů tenhle případ částečně řeší, ale
jen u termínů, které se opakují.

---

## 8. Jak funguje hledání

```
uživatel: "hrazené léky na reflux"
     │
     ▼
  ROUTER (jazykový model)
     ├──► FILTRY:  sekce = indikace, hrazený = ano
     └──► TEXT pro vektor: 'reflux'
                  │
                  ▼
     ROZŠÍŘENÍ DOTAZU (číselník dotazů + původní věta)
        'reflux' | 'vracení kyselého obsahu ze žaludku do úst'
                 | 'regurgitace' | 'hrazené léky na reflux'
                  │
                  ▼
     SQL: WHERE hrazeny = true AND sekce = 'indikace'   ← FILTR nejdřív
          ORDER BY nejlepší z:
             • kosinová podobnost (vektory)      váha 80 %
             • český fulltext                    váha 20 %
                  │
                  ▼
     RRF (spojení dvou žebříčků) → práh → seskupení po lécích
```

### Router

Z běžné věty udělá **filtry** a **text pro sémantiku**. Rozumí tomu, že
„volně prodejný" je filtr na způsob výdeje, ne slovo k hledání.

Vrací mimo jiné: sekci, Rx/OTC, hrazení, účinnou látku, sílu, ATC,
frekvenci nežádoucího účinku, orgánový systém, název konkrétního léku.

**V aplikaci je vidět, co router vrátil** — je to součást výstupu, ne
skrytá magie. Uživatel tak pozná, proč dostal právě tyhle výsledky.

### Filtr se aplikuje PŘED hledáním

To je podstatné pro důvěryhodnost: když se ptáte na hrazené léky,
nehrazené se do výsledku **nemůžou dostat**. Není to otázka skóre.

### Dva žebříčky a jejich spojení

| | umí | neumí |
|---|---|---|
| **filtr** | vybrat správnou množinu | seřadit ji |
| **fulltext** | najít přesné slovo | poradit si s parafrází |
| **sémantika** | poradit si s parafrází | rozlišit řízené hodnoty |

Spojují se metodou **RRF** — pracuje s **pořadím**, ne s hodnotami skóre,
takže se nemusí řešit, že cosine a fulltextový rank mají jinou stupnici.

### Číselník dotazů

Mapuje **výraz laika → formulaci, která je v dokumentu**.

Změřeno na MAALOXu, který má reflux popsaný opisem a slovo „reflux"
v něm nepadne ani jednou:

| co se hledá | pořadí ze 155 indikací |
|---|---|
| „mám reflux" | #19 |
| „regurgitace" (odborné synonymum) | #10 |
| **„vracení kyselého obsahu ze žaludku do úst"** | **#1** |

**Nejlepší synonymum není odborný termín, ale věta z dokumentu.**

Rozšiřuje se **dotaz, ne data** — do textů léků se nikdy nic nepřidává,
takže u každého výsledku dál sedí odkaz na stranu SPC.

### Práh

Výsledky pod naměřenou hranicí podobnosti se zahodí. **Systém raději
neodpoví, než aby si vymyslel.** Hranice je 0,55 a je naměřená, ne
odhadnutá — v aplikaci jde posunout a je vidět, co to udělá.

---

## 9. Co všechno umí najít — scénáře k předvedení

| # | dotaz | co se ukazuje |
|---|---|---|
| 1 | `volně prodejný lék na bolest hlavy` | indikace + filtr výdeje |
| 2 | `lék na bolest na předpis` | indikace + Rx |
| 3 | `hrazený lék na bolest` | indikace + hrazení z pojištění |
| 4 | `nežádoucí účinky amoksiklav` | **celý seznam** — 44 položek |
| 5 | `vzácné nežádoucí účinky ablymico` | filtr na frekvenci |
| 6 | `dávkování zyrtec` | celá sekce dávkování, 6 řádků |
| 7 | `kdy se nesmí brát paralen` | kontraindikace |
| 8 | `lék s paracetamolem` | **řízená hodnota** — víc léků, tatáž látka, různý výdej a hrazení |
| 9 | `co může způsobit průjem` | nežádoucí účinek napříč léky (4 léky, shoda 1,00) |
| 9b | `volně prodejný lék na průjem` | **táž skupina, opačná role** — průjem jako indikace |
| 10 | `po paralenu mě bolí břicho` | rozliší **lék způsobil** od **lék léčí** |
| 11 | `pálí mě žáha` | parafráze — v dokumentu je „pyróza" |
| 12 | `lék na schizofrenii` | **nenajde nic, a je to správně** |

**Body 8 a 12 jsou nejsilnější.** Osmý ukazuje, že tatáž účinná látka
existuje ve třech kombinacích výdeje a hrazení — na to se fulltext ani
sémantika samy nezmůžou, musí spolupracovat s filtrem. Dvanáctý ukazuje,
že systém přizná, když odpověď nezná.

**Dvojice 9 a 9b stojí za vypíchnutí:** táž věc jednou jako nežádoucí
účinek, podruhé jako indikace. Router to rozliší z formulace, aniž by
uživatel cokoli nastavoval.

Kompletní a odzkoušený seznam scénářů je v `scenare.md`.

---

## 10. Další informace

### 10a. Rozsah a omezení

**Všechno je vyladěné na tomhle malém korpusu.** Prahy, váhy i číselníky
jsou naměřené na několika desítkách léků. Na tisících léků se budou muset
přeměřit — postup i testy na to jsou připravené.

Kvalita hledání se měří automaticky, ne dojmem:

```
Invarianty filtru    212/212  100 %   filtr nikdy nepustí, co nemá
Auto-recall @10       56/56   100 %   text z dokumentu najde svůj lék
Parafráze             10/10   100 %   laická formulace najde správný lék
Negativní dotazy        7/8    88 %   co v datech není, se nevrátí
```

### 10a2. Co by stálo zpracovat celý registr

Otázka, která přijde jako první: *„a co všechny léky?"*

| | kódů |
|---|---|
| kódů SÚKL celkem | 69 355 |
| z toho **fakticky dodávaných** | 9 639 |
| **různých registrací = různých SPC** | **6 766** |

Většina těch 69 tisíc jsou **balení téhož přípravku** — jiná velikost,
totéž SPC. Skutečná práce je tedy **6 766 dokumentů**.

| krok | hodin |
|---|---|
| převod PDF | 17 |
| extrakce modelem | 120 |
| **celkem** | **137 hodin ≈ 6 dnů** |

Jednorázově, na jednom stroji. Týdenní změny se dotknou jen toho, co se
změnilo — to jsou minuty.

**Pozor na past:** kdyby se hnalo všech 69 355 kódů, je to **59 dnů**.
Deduplikace na registrace ušetří desetinásobek času.

**Skutečný limit ale není výkon, je to kvalita extrakce.** Na 32 lécích
se našel chybný laický překlad, slepený nadpis, OCR záměna číslice
a ztracená část výčtu. Na 6 766 dokumentech takových případů budou
desítky a **ruční projití přestane být možné**. Tam je potřeba
investovat, ne do hardwaru.

### 10a3. Cloud pro extrakci, lokálně pro hledání?

Nabízí se rozdělit to podle toho, **co běží jednou a co pořád**:

| část | kdy běží | cloud znamená |
|---|---|---|
| **extrakce ze SPC** | jednou na dokument | **ohraničená částka**, pak nic |
| **hledání** (router + vektory) | u **každého dotazu** | **trvalý náklad**, roste s užíváním |

Odhad ceny za extrakci celého registru (27 064 volání):

| model | celkem |
|---|---|
| gpt-5-nano | **7,76 $** |
| gpt-4o-mini | 16,79 $ |
| gpt-4o | 279,91 $ |

Lokálně: **0 $, ale 120 hodin** obsazeného stroje. Za osm dolarů se tedy
ušetří pět dní výpočtu.

**Soukromí ukazuje stejným směrem**, a to je na tom nejsilnější:

| část | co by šlo ven | jak často |
|---|---|---|
| extrakce | text SPC — **veřejný dokument SÚKL** | jednou |
| hledání | **dotaz uživatele** („mám průjem") | pokaždé |

Dotazy uživatelů jsou zdravotní údaje o konkrétním člověku. Posílat je
ven při každém hledání je jiná věc než jednou odeslat dokument, který si
kdokoli stáhne ze SÚKL.

**Zatím to ale rozhodnout nejde — kvalita cloudové extrakce není
změřená.** Měřilo se jen embedování (a tam lokální model vyhrál).
U extrakce srovnání chybí a je zapsané jako úkol. Chyba v extrakci se
propíše do všech dat naráz, takže je to přesně případ, kdy se vyplatí
napřed měřit.

### 10b. Kam to lze posunout

| krok | K cemu to je|
|---|---|
| Zadani od registraci - pokdu to nebude vseobjimajici zadani na 100 stranek, minimalistike, lze delat inkrementy, nemam dostatek programovacich kreditu| lze udelat interni aplikaci pro par osob idalen na nejaky leky, kde je ptoreba neco rychle dohledat, lze i treba parametry nedostupnosi brat v potaz LPOD atp|
| Uprava vyhledavani pres klice - chtel bych udelat tento tyden, napriklad prujem - Hydrasec pro deti| Bude to o neco presnejsi
| nasazení na server | dostupné pro víc lidí, ne jen z meho jednoho počítače |
| **přidat léky** | pipeline je hotová, jde jen o čas výpočtu |
| **hledat léky se stejnou ATC** jako nejlepší výsledek | „ukaž mi alternativy k tomuhle léku" |
| dotáhnout extrakci | ručně projít označené sekce, doplnit ověření laického tvaru |

### 10c. Kde se tráví čas

| část | čas | poznámka |
|---|---|---|
| převod PDF → text | ~9 s / dokument | jednorázově |
| **vytažení sekcí do JSON + zjednodušení** | **~16 s / sekce** | **nejdražší část** |
| naplnění databáze | sekundy | |
| výpočet vektorů | ~20 s / celý korpus (1 346 řádků) | |
| **jeden dotaz uživatele** | **~6 s** | z toho router 5,6 s |

**Nejdražší je zjednodušení odborného textu na laický** — model musí
každou položku přeformulovat a je to generování, ne čtení. Celý korpus
tak stojí desítky minut, ale **dělá se jednou**.

Naopak **vlastní hledání trvá 0,3 s**. Zbylých 5,6 s z dotazu spotřebuje
router, tedy jazykový model, který z věty dělá filtry. Kdyby bylo potřeba
zrychlit odezvu, je to jediné místo, kde se to vyplatí řešit.

### 10d. Použité modely

| model | k čemu | proč tenhle |
|---|---|---|
| **qwen3.5:122b** | extrakce, zjednodušení, router | MoE architektura — zároveň nejlepší i nejrychlejší (29 tok/s proti 4,5 u menšího klasického modelu) |
| **gemma4:31b** | kontrola dat | **jiný** než ten, co data vyrobil |
| **bge-m3** | vektory (1024 rozměrů) | multilingvální, na češtinu měřitelně lepší než cloudové modely |

Cloudové modely byly **změřeny a zamítnuty**: `text-embedding-3-small` je
horší než bge-m3 ve 4 z 5 dotazů, `text-embedding-3-large` prohrává na
laických parafrázích. Za lokální řešení se tedy neplatí kvalitou.

Modely běží na **NVIDIA DGX Spark**. Velký model se drží v paměti a
nahrává se při startu aplikace, ne až u prvního dotazu — jinak by první
uživatel čekal dvě minuty a nevěděl proč.

### 10e. Technologie

| vrstva | co |
|---|---|
| **databáze** | PostgreSQL 17 + rozšíření **pgvector** (kosinová podobnost, index HNSW) |
| **fulltext** | vestavěný český fulltext PostgreSQL |
| **jazykové modely** | **Ollama** — lokální běh modelů |
| **PDF** | **Docling** (struktura, tabulky) + **PyMuPDF** (surový text) |
| **API** | **FastAPI**, dokumentace se generuje sama na `/docs` |
| **aplikace** | čisté JavaScript bez frameworku, žádný build |
| **Python** | `psycopg` (Postgres), `requests` (API SÚKL) |

Vektory i fulltext jsou **v jedné databázi**, takže filtr, podobnost
i fulltext běží jedním SQL dotazem. **Není potřeba samostatná vektorová
databáze** a data nejsou na dvou místech.

