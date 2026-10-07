# Jak funguje hledání

Stav k 7. 10. 2026, korpus 5 880 SPC / 472 844 hledacích řádků. Kód:
`common/router.py`, `common/dotazy.py`, `common/hledani.py`.

Část čísel v příkladech je z doby, kdy korpus měl 32 léků (srpen–září
2026). Jsou označená „(32 léků)" – vysvětlují, PROČ je něco udělané tak,
jak je; absolutní hodnoty na celém trhu vycházejí jinak. Původní měření
jsou v `poznatky.md`.

Krok za krokem na skutečném dotazu ukáže `hledani_log.py "…"`.

---

## Řetězec od dotazu k výsledku

```
dotaz uživatele
   │
   ├─► ROUTER (gemma4:26b)    ── z věty udělá FILTR, vybere SEKCI
   │        │                    a oddělí dotaz_text pro sémantiku
   │        ├─ věk pacienta a vzor názvu se poznají PRAVIDLY, ne modelem
   │        ▼
   ├─► ROZŠÍŘENÍ DOTAZU       ── dotaz_text + formulace z hledacího slovníku
   │        │                    + PŮVODNÍ věta uživatele
   │        ▼
   ├─► FILTR (SQL WHERE)      ── omezí kandidáty PŘED hledáním
   │        │
   │        ▼
   ├─► DVA ŽEBŘÍČKY           ── cosine (bge-m3; text i klíč řádku,
   │        │                    MAXIMUM přes varianty) + český fulltext
   │        ▼
   ├─► POŘADÍ                 ── RRF, nebo „čtení sekce" v pořadí dokumentu
   │        │
   │        ▼
   ├─► PRÁH                   ── odřízne málo podobné (ne u přesných filtrů)
   │        │
   │        ▼
   └─► SESKUPENÍ PO LÉČIVECH  ── jeden lék jednou, s nejlepší pasáží
```

---

## 1. Router

Lokální model `gemma4:26b` (`config.MODEL_ROUTER`). Z věty v přirozené
řeči udělá tři věci.

### Vybere sekci

Nejdůležitější pravidlo: **když uživatel neřekne výslovně, že jde
o nežádoucí účinek, je příznak VŽDY INDIKACE.** Bez toho by dotaz
„lék na bolest" vrátil léky, které bolest *způsobují*.

```
"po vepřovém mě bolí břicho"   ->  indikace          (jídlo není lék)
"po tom léku mě bolí břicho"   ->  nezadouci_ucinky
"kdy se nesmí užívat"          ->  kontraindikace
"Paralen 500mg"                ->  atributy
"paralen bolest hlavy"         ->  indikace + nezadouci_ucinky (rozhodnou data)
```

### Vytáhne filtry

Co v dotazu není, zůstane `null` — router si **nedomýšlí**.

```
"volně prodejný"  ->  na_predpis = false
"hrazený"         ->  hrazeno = true
"se silou 500mg"  ->  sila = "500MG"      (bez mezery, jak to vrací API)
"se srdcem"       ->  organovy_system = "Srdeční poruchy"
"s paracetamolem" ->  ucinna_latka = "paracetamol"
"velmi časté"     ->  frekvence = "velmi časté"   (přesná hodnota číselníku)
"0218102"         ->  kod_sukl
```

**`hrazeno` a `na_predpis` jsou DVĚ RŮZNÉ VĚCI** a snadno se pletou —
v korpusu je 1 823 kódů na předpis, které hrazené nejsou. Hrazenost není
atribut v detailu léčiva: SÚKL ji vyjadřuje tím, že kód je v seznamu
`typSeznamu=scau` (cache `data/hrazene_scau.json`; v korpusu 6 115
hrazených kódů z 8 778).

Název léku a účinnou látku router po modelu **opraví proti registru**
(`oprav_nazev_a_latku`): překlep se dotáhne na nejbližší skutečný název.

### Oddělí `dotaz_text`

**Jen ten zbytek, co se má hledat sémanticky.** Ne celá věta.

```
"volně prodejný lék na bolest se silou 500mg"  ->  "bolest"
"co dělá Paralen se srdcem"                    ->  "srdce"
"Bolest břicha nežádoucí účinek"               ->  "bolest břicha"
```

Není to kosmetika: **PARALEN měl na dotaz „bolest" podobnost 0,618,
ale na celou větu jen 0,53** (32 léků). Slova „volně prodejný" a „najdi
mi" vektor ředí. Opačný extrém taky škodí: když router z „Bolest břicha"
udělal jen „břicho", podobnost spadla na 0,49.

Když router zahodí diakritiku („kasel" místo „kašel"), vrátí se mu
z původní věty (`obnov_diakritiku`) – bge-m3 je na ni citlivý.

### Co se pozná pravidly, ne modelem

Router není deterministický, proto se dvě věci s dopadem na bezpečnost
a přesnost berou z původní věty pravidly a model je nemůže ztratit:

- **věk pacienta** (`common/vek.py`): „pro děti", „dítě 6 let",
  „tříletý", „miminko", „pro dospělé" → filtr; popis v `docs/hledani_vek.md`;
- **vzor názvu** (`common/nazev_vzor.py`): „lék začíná oxy", „obsahuje
  pox", „končí na prazol", „přibližně zirtek" (min. 3 znaky) → filtr jen
  na název léku.

Zmínka o věku se z textu pro vektor odstraní („reflux pro děti" → „reflux").

### Když si router není jistý nebo selže

Vrátí `jistota: nizka` a hledá se ve **všech sekcích**; u každého
výsledku je vidět, odkud pochází. Selhání routeru hledání neshodí —
vrátí prázdný filtr (věk a vzor názvu se doplní i tak).

---

## 2. Rozšíření dotazu — do vektoru jde víc formulací naráz

Router má **jeden** textový výstup (`dotaz_text`). Vyhledávání ale
porovnává **víc variant** a bere nejlepší shodu:

```
uživatel: "mám nafouklé břicho"
     │
     ▼
  ROUTER  ──► filtry  (sekce, Rx/OTC, hrazení, látka, síla, frekvence…)
     └─────► dotaz_text = 'nafouklé břicho'   ← JEDEN textový výstup
                  │
                  ▼
        ┌─ 'nafouklé břicho'                  ← router
        ├─ 'nadýmání'                         ← hledací slovník (výraz „nafoukl")
        └─ 'mám nafouklé břicho'              ← původní věta uživatele
                  │
                  ▼
        SQL:  GREATEST( podobnost s v1, podobnost s v2, … )   ← MAXIMUM, ne průměr
```

**Bere se maximum, ne průměr.** Horší varianta nemůže uškodit — může jen
zachránit případ, kdy ta lepší chybí.

| zdroj | kolik | k čemu je |
|---|---|---|
| router `dotaz_text` | 1 | dotaz očištěný od vaty a od toho, co šlo do filtrů |
| hledací slovník | 0–4 | formulace, jak to stojí v datech |
| **původní věta uživatele** | 1 | pojistka proti tomu, že router ořeže příliš |

### Hledací slovník (tabulka `slovnik_dotazu`)

Mapuje **výraz laika → formulaci, která je v datech**. Používá se jen
při hledání; do dat se nic nepřidává, takže uživatel dál vidí větu
z dokumentu s odkazem na stranu.

**Proč formulace z dat a ne synonymum** (32 léků, MAALOX má reflux
popsaný opisem):

| co jde do vektoru | pořadí ze 155 indikací |
|---|---|
| `mám reflux` | #19 (0,474) |
| `regurgitace` — odborné synonymum | #10 (0,488) |
| **`vracení kyselého obsahu ze žaludku do úst`** | **#1 (0,647)** |

**Nejlepší „synonymum" není odborný termín, ale věta z dokumentu.**

**Kde je a jak se mění:**

- Úložiště je tabulka `slovnik_dotazu` v Postgresu, čte se **při každém
  hledání** – změna platí hned a ve všech instancích API, bez restartu.
- Mění se **z GUI** (blok „Hledací slovník") nebo přes `/api/slovnik`.
  Formulace se ověřuje proti zjednodušeným indikacím v DB: co není
  v indikaci žádného léku, uložit nejde. K jednomu výrazu jde vybrat víc
  formulací, nejvýš 4 (`rozsir(limit=4)`).
- `common/data/slovnik_dotazu.json` je jen **výchozí náplň** (22 výrazů):
  nahraje se jednou, když tabulka ještě neexistuje. Plnění korpusu
  (`extrakce_4_db.py`) tabulku nemaže.

**Jak se výraz páruje s dotazem** (`dotazy._sedi`): po slovech, bez
diakritiky, jako **začátek slova**. Výraz `kocovin` chytí „kocovina",
„kocovinu" i „kocovinou"; celé `kocovina` by na „kocovinu" nesedělo.
Proto se píše **kmen**:

| uživatel napíše | sedí `kasl` | sedí `kasel` |
|---|---|---|
| pořád ka**šlu** | ano | ne |
| mám ka**šel** | ne | ano |

Čeština při skloňování vyhazuje `-e-`, proto jsou ve slovníku oba kmeny.
Víceslovný výraz („nemůžu usnout") sedí, když jeho slova jdou v dotazu
po sobě. Delší výrazy mají přednost.

**Vyplatí se formulace vybrat měřením.** U antihistaminik reagoval každý
lék na jinou (32 léků):

| formulace | DITHIADEN | ZYRTEC | AERIUS |
|---|---|---|---|
| alergická reakce | **0,701** | 0,543 | 0,521 |
| úleva od příznaků alergie | 0,522 | **0,699** | 0,583 |
| příznaky alergie | 0,587 | 0,606 | **0,602** |

**Pozor na příliš obecný výraz nebo formulaci.** `ekzem → zánět kůže`
začalo trefovat AMOKSIKLAV (celulitida je bakteriální infekce, ne ekzém).
Výchozí výraz `bolest` přidává ke každému dotazu s bolestí obecné
„bolest", „bolesti", „tlumení bolesti" – a tím zvýhodňuje léky s holou
položkou „bolest" (viz `docs/prezentace_scenare.md` kap. 6).

**Výchozí záznamy vznikly nad 32 léky** a část jejich formulací v novém
korpusu už není (`reflux → vracení kyselého obsahu ze žaludku do úst`
má 0 léků). Projít – je v `todo.md`.

### Původní věta uživatele

Router není deterministický. Třikrát po sobě týž dotaz:

| dotaz | běh 1 | běh 2 | běh 3 |
|---|---|---|---|
| „bolí mě zuby" | `bolest zubů` | `bolí mě zuby` | **`zuby`** |
| „pálí mě žáha" | `pálí mě žáha` | `pálí mě` | `žáha` |

Samotné `zuby` mělo 0,396, tedy pod prahem. Proto se původní věta přidává
jako další varianta:

| ořezané routerem | původní věta | použije se |
|---|---|---|
| `zuby` 0,396 | `bolí mě zuby` **0,845** | původní |
| `průjem` **0,623** | `mám průjem` 0,604 | router |

**Původní věta se vybírá GLOBÁLNĚ, ne po řádcích.** Slovníkové varianty
se berou maximem po řádcích (různé léky legitimně odpovídají různým
formulacím). Původní věta je ale pojistka – kdyby dostala totéž
zacházení, mohl by si každý řádek vybrat variantu, která mu lichotí
(„mám průjem" posunulo „bolestivou menstruaci" přes práh, protože slovo
„mám" táhne vektor ke stížnostem). Porovnají se proto nejlepší výsledky
obou stran a použije se jen ta lepší. Stojí to jeden agregační dotaz.

**Poučení: nedeterministický článek se nemá opravovat jen promptem.**
Levnější je udělat systém odolný proti tomu, že se splete.

---

## 3. Filtr se aplikuje PŘED hledáním

Kdyby se filtrovalo až z výsledků, dotaz „volně prodejný lék na bolest
hlavy" by nejdřív našel desítky léků na bolest hlavy a pak z nich nechal
volně prodejné — možná žádný. Takhle se hledá **mezi všemi volně
prodejnými**:

```
bez filtru                       472 844 řádků
+ sekce indikace                  25 097
+ volně prodejné                   3 551
```

Co se filtruje (`hledani.Filtr`, `_podminky`): sekce, výdej, hrazení,
síla, ATC, orgánový systém, frekvence, skupina pacientů, název, kód
SÚKL, účinná látka, vzor názvu, věk (`pro_deti`, `vek`, `pro_dospele`).

**Identitu léku přiřazuje FILTR, ne hledací sloupce.** Název a látka se
hledají v registru (`nazev ILIKE`, shoda v seznamu látek), vektor o nich
u řádků sekcí neví.

### Přesný filtr vypíná práh

Když dotaz jmenuje lék, kód, látku, sílu, ATC, frekvenci nebo vzor názvu
(`Filtr.je_presny()`), **výběr už proběhl** podle řízené hodnoty a práh
podobnosti se neuplatní. „Paracetamol" vs. řádek identity PARALENU má
cosine kolem 0,65 a ACIFEIN 0,55 – práh by vyhodil lék, který
paracetamol obsahuje.

U dotazů **jen z atributů** („paracetamol", „helicid", „paralen 500mg")
API vrací `vyber_filtrem: true` a GUI shodu vůbec neukazuje – určuje jen
pořadí uvnitř výběru a o kvalitě nálezu nic neříká.

---

## 4. Co přesně se prohledává

Jeden řádek tabulky `leciva_search` = jedna položka (jedna indikace,
jeden nežádoucí účinek, jedna dávka) + jeden řádek `atributy` na SPC.

| sekce | řádků |
|---|---|
| nežádoucí účinky | 350 067 |
| dávkování | 46 540 |
| kontraindikace | 45 260 |
| indikace | 25 097 |
| atributy (identita léku) | 5 880 |

| sloupec | typ | plní se z | jak |
|---|---|---|---|
| `embedding` | `vector(1024)` | `obsah_text` | `extrakce_5_embeddingy.py` |
| `embedding_klic` | `vector(1024)` | `klic` (když je) | `extrakce_5_embeddingy.py` |
| `search_fts` | `tsvector` | `klic` + `obsah_text`, s diakritikou i bez | `GENERATED ALWAYS … STORED` |

- **`obsah_text`** je to, co vidí uživatel: laický tvar a v závorce
  odborný, když je kratší než 60 znaků (`ucpaný nos (kongesce nosní
  sliznice)`). U dávkování `pacient dávka frekvence`.
- **`klic`** je krátké heslo (1–4 slova) od modelu; u dávkování skupina
  pacientů. Má **vlastní vektor**, protože dlouhá věta význam ředí:
  indikace o 27 slovech měla na „průjem" 0,515, její klíč „akutní průjem"
  0,781. Při hledání se bere **lepší z obou vektorů**.
- **Fulltext se nikdy neplní ručně**, Postgres ho přepočítá při zápisu;
  vektory se po změně dat dopočítají skriptem (jen řádky bez vektoru).

### Co v hledacích sloupcích NENÍ

Filtrační sloupce (`sekce`, `frekvence`, `organovy_system`,
`sekce_atributy`, `strana_pdf`) a `kontext_text` (identita léku u řádků
sekcí). Kdyby byly v textu, opakovaly by se přes stovky řádků:
`kontext_text` ve fulltextu způsobil, že dotaz „paracetamol" trefil 97
řádků z 994 a správný řádek identity skončil poslední (32 léků).

---

## 5. Dva žebříčky

| | co to je | čím |
|---|---|---|
| sémantika | podobnost významu | bge-m3, 1024 dim, HNSW index; text i klíč |
| fulltext | shoda slov | konfigurace `czech_unaccent`, `ts_rank_cd` |

### Sémantika

Pro každý řádek: maximum přes všechny varianty dotazu a přes oba vektory
řádku (text, klíč). Do žebříčku jde 100 nejlepších (`KANDIDATU`).

**Z databáze se vracejí jen kandidáti obou žebříčků** (top 100 podle
podobnosti + až 1 000 podle fulltextu), ne všechny řádky po filtru.
Podobnost se spočítá pro všechny (úzká tabulka `id, cosine, fts`), široké
sloupce se dotáhnou až k vybraným. Do 7. 10. se vracelo všechno a ořezávalo
v Pythonu: dotaz přes všechny sekce (472 844 řádků) trval 13 s, přitom
výpočet podobnosti v DB jen 1,3 s – zbytek byl přenos a řazení.

Při shodné podobnosti rozhoduje fyzické pořadí řádků v tabulce, aby výběr
i pořadí byly při každém běhu stejné.

### Fulltext

**Konfigurace `czech_unaccent` = hunspell → unaccent → simple se stop
slovy** (`init-db.sql`, vlastní image `Dockerfile.postgres` s balíčkem
`hunspell-cs` a `tsearch/czech.stop`):

- **hunspell lematizuje**: „žáhy" → „žáha", „nervů" → „nerv", „pálí" →
  „pálit". Postgres stemmer pro češtinu nemá; bez toho se 2. pád v datech
  s 1. pádem v dotazu nepotkal.
- co hunspell nezná (názvy látek, latina, překlepy), spadne na unaccent;
- text se indexuje **s diakritikou i bez**, takže „prujem" najde „průjem".

**Dotaz: AND uvnitř pojmu, OR mezi pojmy.**

- text od routeru (a původní věta) se převádí na **OR** – věta obsahuje
  i slovesa a přísný AND by nenašel nic;
- formulace ze slovníku zůstávají na **AND** – jsou očištěné a plošný OR
  zahazoval konkrétnost: z „rýma, ucpaný nos, zánět sliznice nosu" stačilo
  jediné slovo „zánět" a řádek se počítal jako shoda (43 řádků místo 5,
  mezi nimi osm různých zánětů AMOKSIKLAVU; 32 léků).

Převod na OR se dělá nad už zpracovaným `tsquery`, ne nad textem od
uživatele, takže nehrozí injektáž.

Do žebříčku jde až 1 000 řádků s nenulovou shodou (`KANDIDATU_FTS`):
na celém trhu má „zápal plic" přes 100 shod a se stropem 100 se část
plných shod do žebříčku vůbec nedostala (KLACID, 2. 10.).

---

## 6. Pořadí

### RRF (výchozí)

```
skóre = 0,8 / (60 + pořadí_sem) + 0,2 / (60 + pořadí_fts)
```

**Váhou se násobí převrácené pořadí, ne podobnost.** Cosine do vzorce
nevstupuje. Důsledek (32 léků): MAALOX s podobností 0,481 skončil nad
ACIFEINEM s 0,524, protože měl lepší místo ve fulltextu; nepomohla váha
0,95 ani `k = 5`.

Známá vada na celém trhu: desítky řádků mají cosine přesně 1,000 (stejný
text u různých léků) a RRF mezi nimi řadí podle náhodného pořadí z DB
(`todo.md`: shodné hodnoty = stejné pořadí).

### Cosine (`--zpusob cosine`)

Pořadí určuje **výhradně podobnost**, fulltext slouží jen k tomu, aby se
kandidát dostal do výběru. Porovnání obou: `hledani_evaluace.py --vahy`.

### Čtení sekce místo hledání

Když dotaz jmenuje **konkrétní lék a jednu obsahovou sekci** („dávkování
vibrocil", „nežádoucí účinky paralen"), podobnost nemá co měřit: do
vektoru jde jen název léku, který v textu sekce není (u ZYRTECu měly
všechny řádky dávkování 0,30–0,32, tedy šum). Vrací se proto **celá
sekce v pořadí dokumentu** (`cely_usek: true`).

Když sekci zúží ještě další filtr (frekvence, orgánový systém, skupina
pacientů), řadí se dál podle dokumentu, ale odpověď přizná, že to není
celá sekce (`usek_orezan`).

---

## 7. Práh

Výchozí `0,60`. Aplikuje se na **cosine**, ne na RRF — RRF je jen pořadí
a jeho hodnota nic neříká o tom, jak moc je výsledek podobný. Neuplatní
se u přesných filtrů a u čtení sekce.

**Hodnota je naměřená na 32 lécích a na celém trhu je moc nízko:**
„něco na kocovinu" má 0,635 s „covid-19", „jak vyměnit pneumatiku" 0,652
s „výměnou dýchací trubičky". Přeměřit: `hledani_evaluace.py --prahy`
(parafráze podle ATC a negativní dotazy pro řadu prahů).

Když nic neprojde, odpověď rozliší dva případy: filtr nepustil nic,
nebo něco prošlo filtrem, ale nic nebylo dost podobné.

---

## 8. Když se nenajde nic — ATC záchranná síť

Když žádný řádek nedosáhne prahu (nebo filtr nepustí nic), nabídnou se
léčiva z odpovídající **terapeutické skupiny ATC**
(`common/data/atc_mapa.json`, 5 skupin; v API pole `atc_navrh`).

1. **Ukazuje se ODDĚLENĚ a označeně.** Není to nález v dokumentu, ale
   odvození ze skupiny, kterou léčivu přiřadil SÚKL.
2. **Je to znalost na úrovni TŘÍDY**, ne léčiva – zvedá recall, ne
   precision; uvnitř skupiny se řadit nedá.

---

## 9. Seskupení po léčivech

Tabulka má jeden řádek na **položku**, takže lék má vlastní řádek pro
každou indikaci. Bez seskupení by první desítka mohla být osm řádků
jednoho léku.

Hledá se proto **s rezervou** a teprve pak se seskupuje po `kod_sukl`.
U každého léku se ukáže **nejlépe skórující pasáž jako důkaz**, proč se
trefil; další shody jsou v rozbalení (CLI `--pasaze`).

Extrakty jsou v DB jednou za SPC, u **zástupce** (nejmenší kód SÚKL).
Víc balení téhož léku se tedy ve výsledcích neopakuje; řádek identity
nese názvy a síly všech balení.

---

## 10. Výstup CLI

```
 1. HELICID 20 20MG (CPS ETD)
    kod SUKL   0025366 · OTC (volně prodejný) · hrazený · ATC A02BC01
    látky      OMEPRAZOL
    poradi     100.0 / 100   (odstup od nejlepsiho)
    sémantika  0.812 cosine     pořadí #1
    fulltext   6.0000 ts_rank     pořadí #2
    sekce      Terapeutické indikace
    nalezeno   pálení žáhy (pyróza)
    zdroj      data/spc/cz_74607/spc.md § 4.1 Terapeutické indikace
```

| řádek | odkud |
|---|---|
| `kod SUKL`, výdej, hrazení, ATC, `látky` | **registr SÚKL** — řízené hodnoty, žádný model |
| `sekce`, `nalezeno` | **SPC** přes extrakci modelem |
| `poradi`, `sémantika`, `fulltext` | spočítané při hledání |
| `zdroj` | složka SPC v korpusu a číslo sekce |

```bash
uv run python hledani_cli.py "volně prodejný lék na bolest hlavy"
uv run python hledani_cli.py "bolest břicha nežádoucí účinek" --prah 0.6 --pasaze
uv run python hledani_cli.py "bolest" --zpusob cosine      # jiný způsob řazení
uv run python hledani_cli.py "bolest hlavy" --bez-routeru  # celou větou, bez filtrů
uv run python hledani_cli.py "Paralen 500mg" --json        # strojový výstup
uv run python hledani_log.py "mám reflux"                  # každý krok zvlášť
```

---

## 11. Kolik to trvá

| krok | kde | čas |
|---|---|---|
| router (gemma4:26b) | DGX | medián **1,5 s** |
| embedding variant dotazu (bge-m3) | DGX | desetiny sekundy |
| hledání v Postgresu | lokálně | ~1 s v jedné sekci s filtrem; 4–5 s přes nežádoucí účinky celého trhu nebo přes všechny sekce |
| **celkem** | | **2–3 s** |

**Router je většina času** (na 32 lécích 92 %). Volba modelu:
`benchmarky/router/bench_router.py` – gemma4:26b je 3× rychlejší než
qwen3.5:122b a o něco správnější.

První dotaz po nečinnosti trvá ~10 s navíc: Ollama model po 5 minutách
odloží a router (19 GB) se musí načíst. Proto `keep_alive: 2h` a
předehřátí při startu API.

**Prodlevu u dotazů mimo medicínu („počasí dnes") nedělá router** – ten
odpoví za 1,5 s jako vždy. Když si není jistý sekcí, hledá se ve všech
472 844 řádcích a čas je v databázi (teď ~5 s, do 7. 10. 13–27 s).
Časový limit na router by tedy nepomohl.

Router není zbytný: bez něj nejsou filtry ani výběr sekce a práh přestane
oddělovat dotazy mimo medicínu.

**Víc lidí naráz** (jeden stroj, celé hledání, 7. 10.): 1 uživatel 3,4 s,
4 naráz – poslední 7,3 s, 8 naráz – poslední 13,8 s. Propustnost ~0,6
hledání za sekundu. Na router i na vektor dotazu je limit 30 s
(`HLEDANI_TIMEOUT_S`); když ho stroj nestihne, zkusí se další, a když
selže i ten, hledá se bez routeru ve všech sekcích.

---

## 12. Známé mezery

- **Práh 0,60 pouští falešné shody** na celém trhu (kap. 7).
- **Dotaz přes všechny řádky trvá ~5 s**, protože se podobnost počítá
  přesně pro každý řádek. Rychlejší by bylo brát kandidáty z HNSW indexu
  (desítky ms), ale index neumí filtr ani maximum přes varianty –
  muselo by se změřit, co to udělá s výsledky.
- **Shodné cosine = náhodné pořadí** mezi řádky se stejným textem (kap. 6).
- **Neupřednostňuje běžné léky.** Dotaz o miminku vrátí nemocniční
  antibiotika v injekcích; chybí zvýhodnění volně prodejných léků
  a běžných forem podání.
- **Router není deterministický** – tentýž dotaz může dopadnout mírně
  jinak, občas ztratí název léku. Pojistky: původní věta, oprava názvu
  proti registru, věk a vzor názvu pravidly.
- **Chyby v datech se propisují do hledání.** Holá indikace „bolest"
  (vytržená z věty) dá vysokou shodu na každý dotaz s bolestí; nad
  korpusem data nic nekontroluje (`docs/prezentace_scenare.md` kap. 6).
- **Laický tvar nemusí používat slovo, které laik hledá.** Pomáhá
  hledací slovník, ale jen pro výrazy, které do něj někdo zapsal.
- **Víc uživatelů najednou:** router je úzké hrdlo a jeden stroj vyřizuje
  dotazy po jednom (8 lidí naráz = poslední čeká ~14 s). Dotazy se proto
  rozdělují mezi stroje s Ollamou podle dostupnosti a vytížení
  (`docs/provoz_pristupy.md`, oddíl Ollama); druhý stroj 7. 10. ještě
  není dostupný, takže zatím běží vše na jednom.
