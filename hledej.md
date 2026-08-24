# Jak funguje hledání

Podrobný popis s příklady. Stručné shrnutí RRF a jeho vad je
v `poznatky.md` (zápisy z 20. 8. 2026).

---

## Řetězec od dotazu k výsledku

```
dotaz uživatele
   │
   ├─► ROUTER (qwen3.5:122b)  ── z věty udělá FILTR a vybere SEKCI
   │        │                    a oddělí dotaz_text pro sémantiku
   │        ▼
   ├─► FILTR (SQL WHERE)      ── omezí kandidáty PŘED hledáním
   │        │
   │        ▼
   ├─► DVA ŽEBŘÍČKY           ── cosine (bge-m3) + český fulltext
   │        │
   │        ▼
   ├─► FÚZE (RRF nebo cosine) ── určí pořadí
   │        │
   │        ▼
   ├─► PRÁH                   ── odřízne málo podobné
   │        │
   │        ▼
   └─► SESKUPENÍ PO LÉČIVECH  ── jeden lék jednou, s nejlepší pasáží
```

---

## 1. Router

Z věty v přirozené řeči udělá tři věci.

### Vybere sekci

Nejdůležitější pravidlo: **když uživatel neřekne výslovně, že jde
o nežádoucí účinek, je příznak VŽDY INDIKACE.** Bez toho by dotaz
„lék na bolest" vrátil léky, které bolest *způsobují*.

```
"po vepřovém mě bolí břicho"   ->  indikace          (jídlo není lék)
"po tom léku mě bolí břicho"   ->  nezadouci_ucinky
"kdy se nesmí užívat"          ->  kontraindikace
"Paralen 500mg"                ->  atributy
```

### Vytáhne filtry

Co v dotazu není, zůstane `null` — router si **nedomýšlí**.

```
"volně prodejný"  ->  na_predpis = false
"hrazený"         ->  hrazeno = true
"se silou 500mg"  ->  sila = "500MG"      (bez mezery, jak to vrací API)
"se srdcem"       ->  organovy_system = "Srdeční poruchy"
"s paracetamolem" ->  ucinna_latka = "paracetamol"
```

**`hrazeno` a `na_predpis` jsou DVĚ RŮZNÉ VĚCI** a snadno se pletou —
v korpusu je 5 léčiv, která jsou na předpis a hrazená nejsou (ABLYMICO,
AMOKSIKLAV). Dokud filtr `hrazeno` neexistoval, „hrazené antibiotikum"
se chytlo na `na_predpis` a vracelo špatnou množinu.

Hrazenost není atribut v detailu léčiva — SÚKL ji vyjadřuje tím, že kód
je v seznamu `typSeznamu=scau` (8 604 kódů, cachovaný do
`data/hrazene_scau.json`).

### Oddělí `dotaz_text`

**Jen ten zbytek, co se má hledat sémanticky.** Ne celá věta.

```
"volně prodejný lék na bolest se silou 500mg"  ->  "bolest"
"co dělá Paralen se srdcem"                    ->  "srdce"
"Bolest břicha nežádoucí účinek"               ->  "bolest břicha"
```

Není to kosmetika: **PARALEN má na dotaz „bolest" podobnost 0,618,
ale na celou větu jen 0,53.** Slova „volně prodejný" a „najdi mi"
vektor ředí.

Pozor na opačný extrém — název příznaku se nesmí zkracovat. Když router
z „Bolest břicha" udělal jen „břicho", podobnost spadla na 0,49.

### Když si router není jistý

Vrátí `jistota: nizka` a hledá se ve **všech sekcích**. U každého
výsledku je pak vidět, odkud pochází. Selhání routeru hledání neshodí —
vrátí prázdný filtr.

---

## 2. Filtr se aplikuje PŘED hledáním

To je podstatné. Kdyby se filtrovalo až z výsledků, dotaz „volně prodejný
lék na bolest se silou 500mg" by nejdřív našel 20 léků na bolest a pak
z nich nechal ty s 500mg — možná žádný. Takhle se hledá **mezi všemi
volně prodejnými 500mg léky**.

```
bez filtru                        782 záznamů
+ sekce indikace                   91
+ volně prodejné                   30
+ síla 500MG                        8
```

---

## Rozšíření dotazu — hledá se víc formulací naráz

Než se dotaz pošle do vektoru, rozšíří se o formulace, které jsou
v textech SPC (`slovnik_dotazu.json`, `common/dotazy.py`):

    "mám reflux"  ->  + "vracení kyselého obsahu ze žaludku do úst"
                      + "návrat obsahu žaludku do jícnu"
                      + "regurgitace"

V SQL se pak bere `GREATEST` přes varianty — **nejlepší shoda vyhrává**,
ne průměr. Když jedna formulace trefí, je to nález, i když ostatní minou.

Změřeno: MAALOX na „mám reflux" **0,510 → 0,858**. Slovo „reflux" přitom
v celém MAALOXu není ani jednou.

**Nejlepší „synonymum" není odborný termín, ale věta z dokumentu.**
Vektor porovnává s tím, co v dokumentu opravdu stojí — samotné
„regurgitace" dá MAALOX na #10, formulace z SPC na #1.

**Rozšiřuje se DOTAZ, ne data.** Do textů léčiv se nic nepřidává, takže
se nic nevymýšlí a u každého výsledku dál sedí odkaz na stranu SPC.

## Zdroj hledání — co přesně se prohledává

Oba žebříčky níž hledají v **jiném textu**. Bez toho se výsledky nedají
vysvětlit.

| sloupec | typ | plní se z | jak |
|---|---|---|---|
| `embedding` | `vector(1024)` | `obsah_text` | `vytvor_embeddingy.py`, ručně |
| `search_fts` | `tsvector` | `obsah_text` (váha A) | `GENERATED ALWAYS ... STORED` |

Oba tedy berou **tentýž text** — liší se způsobem hledání, ne zdrojem.
Fulltext se navíc **nikdy neplní ručně**, Postgres ho přepočítá sám při
každém zápisu; embedding se po změně dat musí přegenerovat skriptem.

### Skutečný řádek

    kontext_text  'PARALEN, 500MG, PARACETAMOL'   <- do hledání NEJDE
    obsah_text    'bolest podél nervu (neuralgie)'

    -> embedding   z 'bolest podél nervu (neuralgie)'
    -> search_fts  'bolest':1A 'nervu':3A 'neuralgie':4A 'podel':2A

### Proč `kontext_text` do fulltextu NEJDE

Do 24.8.2026 tam byl ve váze A a **rozbíjel řazení**. Identita léku se
opakuje na každém jeho řádku, takže dotaz `paracetamol` trefil 97 řádků
z 994 a správnou odpověď dal **nakonec**:

| ts_rank | řádek |
|---|---|
| 1,0000 | ACIFEIN — nevolnost (nauzea) |
| 1,0000 | PARALEN — zvýšená tělesná teplota |
| **0,4000** | PARALEN, 500MG, PARACETAMOL ← správná odpověď |

Řádek `atributy` má totiž `kontext_text` prázdný, takže jeho shoda spadla
do váhy B. Po vyhození `kontext_text` z FTS trefí `paracetamol` **2 řádky,
oba `atributy`**, a příznakové dotazy (`bolest hlavy` → 17 řádků) se
nezměnily vůbec.

**Identitu léku přiřazuje FILTR, ne hledací sloupce.** Vektor o ní neví
vůbec — řádek indikace se embeduje jako holé „bolest podél nervu".

### Fulltextový dotaz se převádí na OR

`websearch_to_tsquery` slova **slučuje přes AND**, takže každé další slovo
množinu zužuje — `paralen 500mg paracetamol` trefilo jediný řádek
a ACIFEIN vypadl, přestože paracetamol obsahuje. Proto se dotaz převádí:

    replace(websearch_to_tsquery('czech_unaccent', dotaz)::text, '&', '|')

Převádí se **už zpracovaný tsquery**, ne text od uživatele — uvozovkované
fráze zůstanou jako `<->` a nehrozí injektáž.

Tím se `ts_rank_cd` stane použitelným, protože řádek, který trefí víc
slov, dostane vyšší rank:

| rank | lék | poznámka |
|---|---|---|
| **3,0000** | PARALEN | trefil paralen + 500mg + paracetamol |
| **1,0000** | ACIFEIN | trefil jen paracetamol |
| 0,0000 | ALGIFEN NEO | netrefil nic |

Dřív u atributů vycházelo binárně 0,4/0,0 a řadit se podle toho nedalo.

### `czech_unaccent` je `simple` + unaccent

Tedy **bez stemmingu a bez stop slov**. „Nervu" se nespojí s „nerv" ani
„nervy" — fulltext hledá tvar, ne základ slova. Na skloňovanou češtinu je
slabý, což je věcný důvod, proč nese jen 20 %. Diakritika se naopak
srovná, takže „kuze" najde „kůže".

### Co v hledacích sloupcích NENÍ

Filtrační sloupce (`sekce`, `frekvence`, `organovy_system`,
`sekce_atributy`, `strana_pdf`) a `kontext_text`. Jsou to hodnoty do
`WHERE` nebo na výpis, ne text k hledání.

## 3. Dva žebříčky

| | co to je | čím |
|---|---|---|
| sémantika | podobnost významu | bge-m3, 1024 dim, HNSW index |
| fulltext | shoda slov | `czech_unaccent`, `ts_rank_cd` |

Do vektoru jde **pouze `obsah_text`**. Filtrační sloupce (`sekce`,
`frekvence`, `organovy_system`) v něm nejsou — opakovaly by se přes
stovky řádků a znehodnotily by vektorový prostor. Kontext léku
(`kontext_text`) taky ne: „PARALEN 500MG" u každé položky by převážil
vlastní obsah a všechny položky jednoho léku by si byly podobné.

Fulltext má navrch u dotazů typu „Paralen 500mg", kde uživatel píše
přesný název — tam vektor selhává, protože „500MG" je jeden token
bez významu.

---

## 4. Fúze — dva režimy

### `--zpusob rrf` (výchozí)

```
skore = 0.8 / (60 + pořadí_sem) + 0.2 / (60 + pořadí_fts)
```

**Váhou se násobí převrácené pořadí, ne podobnost.** Cosine do vzorce
nevstupuje vůbec.

Důsledek, změřený na reálných datech: MAALOX s podobností **0,481**
skončil nad ACIFEINEM s **0,524**, protože měl lepší místo ve fulltextu.
Nepomohla váha 0,95 ani snížení `k` na 5. Podrobný rozbor v `poznatky.md`.

### `--zpusob cosine`

Pořadí určuje **výhradně podobnost**. Fulltext slouží jen k tomu, aby se
kandidát dostal do výběru. Váha se neuplatní.

```
rrf     PARALEN(0.62) > MAALOX(0.48) > ACIFEIN(0.52) > ACYLCOFFIN(0.51)
cosine  PARALEN(0.62) > ACIFEIN(0.52) > ACYLCOFFIN(0.51) > MAALOX(0.48)
```

Který je lepší, rozhodne evaluace. Výchozí zůstává `rrf`.

---

## 5. Práh

`--prah 0.6` odřízne výsledky s nižší podobností. Práh se aplikuje na
**cosine**, ne na RRF — RRF je jen pořadí a jeho hodnota nic neříká o tom,
jak moc je výsledek podobný.

Naměřené hodnoty:

| dotaz | nejlepší cosine |
|---|---|
| „Paralen 500mg" (přesný název) | 0,76 |
| „bolest břicha" v nežádoucích účincích | 1,00 (doslovná shoda) |
| „bolest" v indikacích | 0,62 |
| šum („zápal plic" na dotaz o pálení žáhy) | ~0,45 |

**Zadání odhadovalo práh 0,7 — to neplatí.** Při 0,7 by dotaz na bolest
nevrátil vůbec nic. Rozumné se jeví okolí 0,55–0,6, ale musí se doměřit
v evaluaci.

---

## Když se nenajde nic — ATC záchranná síť

Když žádný řádek nedosáhne prahu (nebo filtr nepustí nic), CLI ještě
nabídne léčiva z odpovídající **terapeutické skupiny ATC**
(`atc_mapa.json`):

    PODLE TERAPEUTICKE SKUPINY (odvozeno z ATC, NENI to udaj ze SPC)
      A02 - léčiva na poruchy žaludeční kyselosti
          CONTROLOC 20MG, MAALOX 400MG/400MG, OMEPRAZOL FARMAX 20MG

Dvě věci na tom záleží:

1. **Vypisuje se ODDĚLENĚ a označeně.** Není to nález v dokumentu, ale
   naše odvození ze skupiny, kterou léčivu přiřadil SÚKL. Míchat to mezi
   nálezy ze SPC by zničilo dohledatelnost.
2. **Je to znalost na úrovni TŘÍDY**, ne léčiva. Všechna léčiva ve
   skupině dostanou totéž, takže to zvedá recall, ne precision — uvnitř
   skupiny se řadit nedá.

## 6. Seskupení po léčivech

Tabulka má jeden řádek na **položku**, takže PARALEN má vlastní řádek pro
každou indikaci. Bez seskupení by top-10 mohlo být osm řádků PARALENU
a dva PANADOLU — místo deseti různých léků.

Proto se hledá **s rezervou** (60 řádků) a teprve pak se seskupuje po
`kod_sukl`. U každého léku se ukáže **nejlépe skórující pasáž jako důkaz**,
proč se trefil. Přepínač `--pasaze` ukáže i další shody.

Deduplikace tedy není jen věc zobrazení — ovlivňuje i to, kolik řádků
se tahá z databáze.

---

## Výstup CLI

U každého léčiva se nejdřív vypíšou **základní údaje z API SÚKL** —
tedy to, co o léku platí bez ohledu na dotaz. Jsou natěsno na dvou
řádcích, aby nezabíraly půl obrazovky:

    1. PARALEN 500MG
       kod SUKL   0254048 · OTC (volně prodejný) · nehrazený · ATC N02BE01
       látky      PARACETAMOL
       poradi     100.0 / 100   (odstup od nejlepsiho)
       sémantika  0.828 cosine     pořadí #1
       fulltext   3.0000 ts_rank     pořadí #1
       sekce      Terapeutické indikace
       nalezeno   bolest hlavy
       zdroj      data/leciva/0254048_PARALEN/spc.md § 4.1

**Výdej a hrazení jsou dvě různé věci** a pletou se — proto jsou vedle
sebe. Lék může být na předpis a nehrazený zároveň (ABLYMICO, AMOKSIKLAV).
Řádek `látky` se vypíše, jen když jsou látky známé; u kombinovaných
přípravků jich je víc (ACIFEIN má tři).

| řádek | odkud |
|---|---|
| `kod SUKL`, `látky` | **API SÚKL** — řízené hodnoty, žádný model u toho nebyl |
| `sekce`, `nalezeno` | **SPC** přes extrakci modelem |
| `poradi`, `sémantika`, `fulltext` | spočítané při hledání |
| `zdroj` | cesta do konvertovaného SPC vč. čísla sekce |

## Příklady

```bash
# základní
uv run python hledej.py "volně prodejný lék na bolest"

# uvozovky nejsou nutné, přepínače můžou být kdekoliv
uv run python hledej.py mám --zpusob cosine "nežádoucí účinek kopřivka"

# s prahem a víc pasážemi
uv run python hledej.py "bolest břicha nežádoucí účinek" --prah 0.6 --pasaze

# porovnání režimů řazení
uv run python hledej.py "bolest" --zpusob rrf
uv run python hledej.py "bolest" --zpusob cosine

# vypnout router (hledá celou větou, bez filtrů)
uv run python hledej.py "bolest hlavy" --bez-routeru

# strojový výstup
uv run python hledej.py "Paralen 500mg" --json
```

---

## Kolik to trvá

| krok | kde | čas |
|---|---|---|
| router (qwen3.5:122b) | DGX | **5,62 s** |
| embedding dotazu (bge-m3) | DGX | 0,16 s |
| hledání v Postgresu | lokálně | 0,31 s |
| seskupení po léčivech | lokálně | 0,0001 s |
| **celkem** | | **6,08 s** |

**Router je 92 % času.** Vlastní hledání nad 994 řádky – vektor, fulltext,
RRF i seskupení – trvá 0,31 s.

Proto na DGX „není vidět aktivita": je to jeden krátký dotaz a qwen3.5:122b
je MoE, takže se aktivuje 8 expertů z 256. Mělký a krátký záběr.

Kdyby bylo potřeba zrychlit, jediná páka je router – ale ten NENÍ zbytný,
bez něj přestane fungovat práh (negativní dotazy 0/8 místo 8/8).

## Známé mezery

### Lék může být pro hledání neviditelný

Sekce ve stavu `zamitnuto_kontrolou` se do `leciva_search` **nepouštějí**.
OMEPRAZOL má takto vyřazené indikace, takže ho dotaz „pálení žáhy"
v indikacích nenajde vůbec — přestože na reflux je.

Je to správné chování (neověřená data se laikovi neukazují), ale má cenu.
Seznam sekcí k ručnímu projití je v `todo.md`.

### Laický tvar nemusí používat slovo, které laik hledá

CONTROLOC má v indikacích „Léčba příznaků návratu kyseliny ze žaludku do
jícnu". Slovo **„pálení žáhy" tam není**, takže ho dotaz na pálení žáhy
nenajde, i když je v indexu.

Není to vada embedovacího modelu, ale toho, **jakými slovy je psaný laický
tvar**. Je to konkrétní vstup pro test C z evaluace (má slovník pojmů vliv
na hledání?). Možná řešení jsou v `poznatky.md`.
