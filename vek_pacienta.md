# Věk pacienta – jak funguje filtr „pro děti" (stav k 1. 10. 2026)

Cíl: dotaz laika „lék na reflux pro děti" nebo „něco na horečku pro
tříleté dítě" má vrátit **jen léky, které SPC pro daný věk výslovně
připouští** – i když to neříká indikace.

Celé je to **bez modelu**: deterministická pravidla nad už vyextrahovanými
daty (`common/vek.py`). Model ani router o věku nerozhoduje.

```
 SPC 4.1 / 4.2 / 4.3 (json)          dotaz uživatele
          │                                  │
   vek_spc()  (naplni_db.py)          vek_z_dotazu()  (router.py)
          │                                  │
 leciva.vek_od / pro_deti            Filtr.pro_deti / Filtr.vek
          └──────────────┬───────────────────┘
                 hledani.py: WHERE l.pro_deti IS TRUE
                                   AND l.vek_od <= věk
```

---

## 1. Strana DAT – od kolika let lze lék použít

### Odkud se věk bere

| sekce SPC | co z ní | příklad |
|---|---|---|
| **4.2 dávkování** (hlavní zdroj) | `pacient` + `davka` každé položky; povinná podsekce „Pediatrická populace" | „děti ve věku 1–6 let: 1–2 kapky" → ANO od 1 |
| **4.1 indikace** | pole `skupina` | „děti od 1 roku" → ANO od 1 |
| **4.3 kontraindikace** | zákaz s výslovným věkem | „děti mladší než 6 let" → NE do 6 |
| 4.4 upozornění | **neextrahujeme** | (Reyeův syndrom u aspirinu) |

### Výsledek pro každé SPC (`vek_spc()`)

| pole v DB (`leciva`) | význam | hodnoty |
|---|---|---|
| `vek_od` | od kolika let (jen z URČITÉHO údaje) | číslo v letech (0,25 = 3 měsíce), `NULL` = nejde určit |
| `pro_deti` | SPC uvádí kladné dávkování pro nějakou dětskou skupinu | `true` / `false` / `NULL` = nevím |
| `vek_duvody` | ze kterých řádků SPC to plyne (audit) | seznam textů „4.2 ANO od 1: …", „4.3 NE do 6: …" |

Uloženo u **všech kódů** SPC (ne jen u zástupce). Počítá se při každém
plnění DB (`naplni_db.py --korpus`, `--obnov-sekci`), samostatně
`naplni_db.py --jen-vek`.

### Pravidla (pořadí odpovídá kódu)

1. Každá položka dávkování se zařadí:
   - **NE** – dávka říká „nestanovena / nedoporučuje se / nesmí /
     kontraindikováno…", **nebo** poznámka „jen na lékařský předpis /
     po poradě s lékařem" (pro laika ne – ASPIRIN 500 u dětí),
   - **ANO** – dávka obsahuje číslo („1–2 kapky", „60 mg/kg"),
   - **nic** – dávka bez čísla („neuvedeno") a bez zákazu.
2. Položka **jiné lékové formy** se nepočítá (jedno SPC pro kapky
   i sprej, tablety i injekce): kód formy SÚKL (GTT, SPR, TBL, INJ, SUP…)
   proti slovům v textu (kapky, sprej, tablety, injekce, čípky…).
3. Zákaz s výslovným věkem v **poznámce** se počítá taky („Tablety se
   nedoporučují dětem mladším 15 let").
4. `vek_od` = **nejnižší spodní hranice z kladných položek**, ale jen
   z určitého údaje:
   - číslo s „od / nad / starší / X–Y" („od 12 let", „6–12 let"),
   - slova s jasnou hranicí: novorozenci 0, kojenci 0, batolata 1,
     dospívající 12, dospělí 18, starší 65.
   - **Neurčuje:** samotné „děti" („děti s glaukomem") a jen horní
     hranice („děti do 6 let: 13–16 kg"). Ty nastaví jen `pro_deti`.
5. Zákazy hranici **posunou nahoru**, opakovaně: kladné od 0, zákaz
   „do 2 let", další zákaz „2–6 let nestanoveno" → od 6.
6. Kontraindikace (4.3) se berou jen s **výslovným věkem v číslech**.
   „Děti s hmotností pod 20 kg" věk neurčuje (PARALEN by jinak vyšel 18).
7. `pro_deti` = `vek_od < 18`, nebo kladná dětská položka bez věku;
   `false`, když je zákaz pro všechny děti (0–18).

**Zásada: v pochybnostech omezit.** Lék, u kterého věk nejde určit, se
při dětském dotazu **nezobrazí**. Horší je doporučit dítěti nevhodný lék
než lék neukázat.

### Čísla (korpus, zástupci SPC)

| `vek_od` | SPC |
|---|---|
| < 1 rok (od narození / měsíců) | 404 |
| 1–11 let | 1 136 |
| 12–17 let | 651 |
| 18+ (jen dospělí) | 2 917 |
| nejde určit | 772 |

Kontrolní léky: VIBROCIL kapky 1 / sprej 6, GAVISCON 12, PARALEN 500 6 /
125 mg 3, NOVALGIN tbl 15 / inj 0,25, IBALGIN BABY 0,25, ASPIRIN 500 12,
XARELTO 18.

---

## 2. Strana DOTAZU – jak se pozná věk v otázce

`vek_z_dotazu()` v `common/vek.py`, volá ho **router** na konci
rozhodování (`common/router.py: _pridej_vek`) – **i když router selže**.

Proč ne model: router (gemma) je nedeterministický a občas ztratí název
léčiva. Tady jde o bezpečnost, filtr se nesmí ztratit.

### Kdo dělá co v jednom dotazu

Model (router) o věku NEROZHODUJE. Překlad „tříletého dítěte" → 3 dělá
regulární výraz se slovníkem číslovek, a to nad **původní větou
uživatele** (ne nad tím, co vrátil model – kdyby model věk zahodil,
filtr se stejně nastaví).

| krok | kdo | „kašel u tříletého dítěte" |
|---|---|---|
| 1. router | **model** gemma4:26b | sekce = indikace, text pro vektor |
| 2. `_pridej_vek` → `vek_z_dotazu` | **regulární výraz** | `pro_deti = True`, `vek = 3`; z textu pro vektor zmizí „u tříletého dítěte" |
| 3. hledání | SQL + vektory | `AND l.pro_deti IS TRUE AND l.vek_od <= 3` |

### Jak parser převádí slova na věk

1. **Číslovka ve slově:** slovník kmenů `_CISLOVKY` (jedno 1, dvou 2,
   **tří 3**, čtyř 4 … patnácti 15) + vzor `kmen + let…/měsíčn…`:
   „**tří**|**letého**" → 3 roky, „šesti|měsíčn…" → 0,5 roku.
2. **Číslo s jednotkou:** „3 roky", „3leté", „5 let", „2 měsíce" (→ 0,17).
   **Číslovka slovem + jednotka** (`_ZAKLADNI`, od 1. 10.): „šest let",
   „tři roky", „pět měsíců", „půl roku" – dřív chyběla a „horečka dítě
   šest let" dalo jen „pro děti" → na 1. místě BRUFEN od 12 let.
3. **Slova bez čísla:** kojenec / miminko / novorozenec → 0,5;
   batole → 2. „Kojení" (kojící matka) se NEBERE.
4. **Dětský kontext:** dítě / děti / dětský / pediatr… Číslo bez zmínky
   o dítěti („bolesti 3 roky") se jako věk nebere. Věk ≥ 18 se ignoruje.

Omezení parseru: číslovky slovy do 17; bez diakritiky („triletého") nepozná – `obnov_diakritiku` z routeru
se zatím nevolá; „dítě ve třetím roce" nepozná; „předškolák / školák"
nastaví jen `pro_deti` bez věku.

### Co pozná (skutečné výstupy)

| dotaz | `pro_deti` | `vek` | filtr v SQL |
|---|---|---|---|
| lék na kašel pro děti | ano | – | `pro_deti IS TRUE` |
| lék na kašel pro kojence | ano | 0,5 | `+ vek_od <= 0,5` |
| rýma miminko | ano | 0,5 | `+ vek_od <= 0,5` |
| horečka dítě 2 měsíce | ano | 0,17 | `+ vek_od <= 0,17` |
| kašel u tříletého dítěte | ano | 3 | `+ vek_od <= 3` |
| horečka dítě 5 let | ano | 5 | `+ vek_od <= 5` |
| horečka dítě šest let | ano | 6 | `+ vek_od <= 6` (od 1. 10.) |
| rýma dítě pět měsíců / půl roku | ano | 0,42 / 0,5 | `+ vek_od <= …` |
| lék pro batole | ano | 2 | `+ vek_od <= 2` |
| kojení a bolest hlavy | – | – | **žádný** („kojení" ≠ kojenec) |
| mám bolesti 3 roky | – | – | **žádný** (číslo bez dítěte) |
| bolest kloubů pro seniory | – | – | **žádný** (viz mezery) |
| lék pro babičku 80 let | – | – | **žádný** (věk ≥ 18 se ignoruje) |
| lék pro dospělého | – | – | **žádný** |

### Co dál router udělá

1. Do filtru nastaví `pro_deti = True` a případně `vek`.
2. Z textu pro vektor **odstraní zmínku o věku** („lék na reflux pro
   děti" → „lék na reflux"). Věk řeší filtr; ve vektoru by jen ředil
   význam (CLAUDE.md: každé slovo navíc stojí 0,03–0,05).
3. Popis filtru, který vidí uživatel: „pro děti (jen léky, jejichž SPC
   uvádí dávkování pro děti)" / „pro dítě 3 let (jen léky, jejichž SPC
   tento věk výslovně připouští)".

### Filtr v hledání (`common/hledani.py`)

```sql
AND l.pro_deti IS TRUE          -- vždy, když dotaz zmiňuje dítě
AND l.vek_od <= %(vek)s         -- jen když je známý věk
```

Lék s `pro_deti = NULL` nebo `vek_od = NULL` (nejde určit) se při
dětském dotazu **nezobrazí**.

---

## 2b. „Pro dospělé" – léky od 12 let výš nebo bez údaje o věku (6. 10. 2026)

Dotaz s „pro dospělé / u dospělých / dospělý" (i bez diakritiky,
`vek.dospeli_z_dotazu()`) nastaví `Filtr.pro_dospele` → podmínka

    l.jen_deti IS NOT TRUE
    AND (l.vek_od >= 12 OR (l.vek_od IS NULL AND l.pro_deti IS NOT TRUE))

Hranice je `vek.DOSPELI_VEK_OD = 12`. Zmínka se z textu pro vektor
odstraní. Když dotaz jmenuje i dítě („pro děti i dospělé"), platí jen
dětský filtr.

**Proč 12 a ne 18.** `vek_od` je SPODNÍ hranice („od kolika let se smí"),
ne „pro koho lék je". IBALGIN je lék pro dospělé a má `vek_od = 12`.
Zkoušeno týž den, v tomto pořadí:

| podmínka | projde SPC | co se stalo |
|---|---|---|
| jen bez dětských přípravků (`jen_deti`) | 5 805 | zůstaly léky se štítkem „od 6 let", vypadalo to jako nefunkční |
| `vek_od >= 18` nebo neznámý | 3 601 | „horečka pro dospělé" → nemocniční infuze, IBALGIN i NOVALGIN pryč |
| `vek_od >= 15` nebo neznámý | 3 714 | vypadne IBALGIN a BRUFEN (od 12 let) |
| **`vek_od >= 12` nebo neznámý** | **4 256** | běžné OTC zůstanou, dětské sirupy pryč |

**Co pořád vypadne, i když je to lék i pro dospělé:** tablety, které SPC
připouští už dětem – PARALEN 500 (od 6), NUROFEN 200 (od 6), PANADOL
NOVUM (od 6). Filtr zná jen spodní hranici; údaj „má dávku pro dospělé"
v DB není.

`leciva.jen_deti` počítá `vek.je_detsky_pripravek()` (v `vek_spc()`,
do DB `naplni_db.aktualizuj_vek` – tedy i `--jen-vek` a každé plnění):

1. **název**: PRO DĚTI, JUNIOR, BABY, DĚTSK-, PRO KOJENCE, PRO INFANTIBUS,
   KIDS, PAED, PEDIATRIC → 31 SPC, přesné;
2. **dávkování 4.2**: aspoň jedna dávka pro děti (skupina začíná pod 12 let,
   končí do 18) a žádná dávka pro dospělé ani dávka bez věku → 44 SPC.

Celkem **75 SPC / 89 kódů**. Ve filtru hraje `jen_deti` roli hlavně
u léků s neznámým věkem a u názvů typu „JUNIOR" od 12 let.
Pravidlo 2 ručně prošlé: ~36 ze 44 správně
(KLACID a FROMILID sirup, MONTELUKAST 4/5 mg, SANORIN 0,5, PARALEN 100
čípky, dětské infuze). **Chybně jen pro děti (~8):** FLUTIFORM, VIREAD
245 MG, BEXSERO, GENOTROPIN, NORDITROPIN, JODID DRASELNÝ, CHLORID SODNÝ
10%, GLUKÓZA 40% – model u nich dospělou dávku neoznačil věkem.

Schválně se nepočítá samotné „dospívající" (ELLAONE, ACTAIR) ani skupina
z indikací 4.1 (ADVANTAN) – zkoušeno, přidávalo to falešné.

## 3. GUI

Detail léku má řádek **„Věk použití"** (`static/app.js: popisVeku`):
„od 3 měsíců", „od 6 let", „jen dospělí (od 18 let)", „pro děti ano,
věk v SPC neuveden", „z SPC nejde určit". Důvody (`vek_duvody`) zatím
v GUI nejsou (todo).

---

## 4. Známé mezery

| mezera | dopad | příklad |
|---|---|---|
| **„pro děti" bez věku = jakýkoli věk pod 18** | vrátí i léky od 12 nebo 15 let | „lék na horečku pro děti" může vrátit NOVALGIN tablety (od 15) – v běžné řeči „děti" ≈ do 12 let |
| **kojenec = pevně 0,5 roku** | lék od 3 měsíců projde, od 7 měsíců ne – i když „kojenec" je 0–12 měsíců | hrubé |
| **senioři / starší nejsou vůbec** | „pro seniory", „babičce 80 let" nic nefiltruje ani nepřidá | dávkování přitom má „starší pacienti" u 3 511 položek (úprava dávky / bez úpravy) |
| **jen spodní hranice** | „od 6 let" nic neříká o horní hranici (lék jen pro děti) | pediatrické přípravky pro dospělého |
| **hmotnost se nepočítá** | „děti 20–25 kg" se bere jen podle věku | |
| **4.4 neextrahujeme** | pediatrická upozornění mimo 4.1–4.3 chybí | Reyeův syndrom (aspirin) |
| **věk z textu, ne z modelu** | neobvyklé formulace parser nepozná → „nejde určit" (13 % SPC) | |

Návrhy na rozšíření jsou v `todo.md` (bod 4b) a v `poznatky.md` (30. 9. večer).
