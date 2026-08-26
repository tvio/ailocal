# TODO 
1. 
1. Upravit hledání dle zjednoduseni
1. V jakem stavu je kompletni spousteni extrakce a naloadovani databaze. Udelat jeden file
1. Udelat logovani komple konverze
2. Udelat logovani komplet od A..Z
2. Vylepsit vyhledavani, kdyz najde nejaky vysoky rank - tak pridat vsehcno z dane ATC skupiny a lecive latky. 
4. Proc lek na kasel vraci ACIFEIN

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
