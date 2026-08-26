# Scénáře pro předvádění

Co korpus umí, co v něm chybí a **co konkrétně zadávat**, aby se nemuselo
pořád ukazovat jen „bolest" a „reflux".

Všechny dotazy níž jsou **odzkoušené** — čísla v závorce je podobnost
(cosine) nejlepšího výsledku. U slabých míst je to napsané.

Předvádí se v GUI (`uv run uvicorn api:app --port 8000`, pak
http://localhost:8000/) — popis obrazovky je v `gui.md`.

---

## 1. Co korpus pokrývá

**32 léčiv** (22 + 4 doplněná 24.8. + 6 na průjem 25.8.). Rozdělení podle terapeutické oblasti (ATC):

| ATC | oblast | léčiva | typické indikace v datech |
|---|---|---|---|
| A02 | žaludeční kyselost, reflux | CONTROLOC, MAALOX, OMEPRAZOL, GASTROFAIT | pálení žáhy, reflux, vředy žaludku a dvanáctníku, říhání |
| **A07** | **průjem** | IMODIUM, ENDITRIL, HIDRASEC, HIDRASEC PRO DĚTI, ERCEFURYL, CEDEPOS | akutní průjem, infekční průjem, *C. difficile* |
| A03 | křeče trávicího ústrojí | ALGIFEN NEO | žlučníkové a ledvinové koliky, bolestivá menstruace, bolest zubů |
| A06 | zácpa | BISACODYL KRKA | zácpa, příprava na vyšetření střeva |
| A10 | cukrovka / obezita | ABLYMICO | hubnutí u dospělých a dětí |
| A11 | vitaminy | ACIDUM ASCORBICUM | nedostatek vitaminu C |
| C07 | tlak, srdce | ACECOR | vysoký tlak, poruchy rytmu, stav po infarktu |
| C10 | cholesterol | AMEDO | zvýšený cholesterol, prevence příhod |
| D07 | kortikoidy na kůži | ADVANTAN | ekzémy (7 druhů) |
| H03 | štítná žláza | ALTHYXIN | zvětšení štítné žlázy, nedostatek hormonů |
| J01 | antibiotika | ABAKTAL, AMOKSIKLAV | zánět dutin, ucha, průdušek, zápal plic, močové cesty |
| M02 | lokální na svaly | ALGESAL | modřiny, revmatické bolesti |
| N02 | bolest a horečka | ACIFEIN, ACYLCOFFIN, PARALEN | bolest hlavy, zubů, zad, nervů, horečka |
| R01 | ucpaný nos | AFRIN, OLYNTH | ucpaný nos, senná rýma, záněty dutin |
| R05 | kašel, hleny | ACC | zánět průdušek, astma, mukoviscidóza |
| R06 | alergie | AERIUS, DITHIADEN | alergická rýma, kopřivka, otok, ekzém |

---

## 2. Matice filtrů — kde jsou díry

Aby šlo předvádět filtrování a nevracel se jeden nebo žádný výsledek,
je potřeba mít v každé oblasti víc kombinací **výdej × hrazení**.

Legenda: ✔ máme · ➕ doplňuje se · ✗ chybí · — v realitě neexistuje

| ATC | OTC nehrazený | Rx hrazený | Rx nehrazený |
|---|---|---|---|
| **A02** kyselost | ✔ MAALOX, OMEPRAZOL | ✔ CONTROLOC | ✔ **GASTROFAIT** |
| **N02** bolest | ✔ PARALEN, ACIFEIN, ACYLCOFFIN | ✔ **ULTRACOD** | ✔ **TALVOSILEN FORTE** |
| **R06** alergie | ✔ **ZYRTEC** | ✔ AERIUS, DITHIADEN | ✗ |
| **A07** průjem | ✔ IMODIUM, ENDITRIL, HIDRASEC | ✔ **CEDEPOS** | ✔ HIDRASEC PRO DĚTI, ERCEFURYL |
| J01 antibiotika | — (prakticky neexistuje) | ✔ ABAKTAL | ✔ AMOKSIKLAV |
| A06 zácpa | ✔ BISACODYL | ✗ | ✗ |
| R01 nos | ✔ AFRIN, OLYNTH | ✗ | ✗ |
| R05 kašel | ✔ ACC | ✗ | ✗ |
| M02 lokální | ✔ ALGESAL | ✗ | ✗ |
| C07 tlak | — | ✔ ACECOR | ✗ |
| H03 štítná | — | ✔ ALTHYXIN | ✗ |
| C10 cholesterol | — | ✗ | ✔ AMEDO |
| D07 kortikoidy | — | ✗ | ✔ ADVANTAN |
| A10 cukrovka | — | ✗ | ✔ ABLYMICO |
| A11 vitaminy | ✗ | ✗ | ✔ ACIDUM ASC. |

**Doplněna 4 léčiva** (hotovo 24.8.), vybraná tak, aby zkompletovala tři
nejvíc předváděné oblasti:

| kód | léčivo | proč právě tohle |
|---|---|---|
| 0109797 | **ULTRACOD** 500MG/30MG | N02 Rx **hrazený** a obsahuje **paracetamol** |
| 0086023 | **TALVOSILEN FORTE** 500MG/30MG | N02 Rx **nehrazený**, taky paracetamol |
| 0232640 | **GASTROFAIT** 1G | jediný A02 Rx nehrazený v celém registru |
| 0155683 | **ZYRTEC** 10MG | R06 volně prodejný, cetirizin — laik ho zná |

**Nejsilnější ukázka filtrování** tím vznikne na paracetamolu — tatáž
účinná látka ve všech třech kombinacích:

| léčivo | výdej | hrazení |
|---|---|---|
| PARALEN | volně prodejný | nehrazený |
| ULTRACOD | na předpis | **hrazený** |
| TALVOSILEN FORTE | na předpis | nehrazený |

U C07, H03, C10, D07 a A10 chybějící kombinace **nemá smysl doplňovat** —
volně prodejné léky na tlak, štítnou žlázu nebo cukrovku neexistují.

---

## 3. Scénáře

**Trojice na paracetamolu** je nejsilnější ukázka filtrování — na dotaz
`lék s paracetamolem` se vrátí všechny čtyři a liší se jen výdejem
a hrazením:

| léčivo | výdej | hrazení |
|---|---|---|
| PARALEN, ACIFEIN | volně prodejný | nehrazený |
| **ULTRACOD** | na předpis | **hrazený** |
| **TALVOSILEN FORTE** | na předpis | nehrazený |

### A. Laik píše po svém (jádro ukázky)

Ukazuje, že se hledá **význam, ne slova**.

| dotaz | co vrátí | proč to je zajímavé |
|---|---|---|
| `pálí mě žáha` | MAALOX (0,86) | v textu je „pyróza" |
| `mám reflux` | MAALOX (0,86), OMEPRAZOL, CONTROLOC | slovo „reflux" v MAALOXu **není vůbec** |
| `porad kaslu` | ACC (0,75) | bez diakritiky a v jiném pádě |
| `mam ucpany nos` | AFRIN (0,68), OLYNTH (0,67) | bez diakritiky |
| `mam zacpu` | BISACODYL (0,66) | |
| `mam alergii` | DITHIADEN (0,70), AERIUS | |
| `mám horečku` | PARALEN (0,84) | v textu „zvýšená tělesná teplota" |
| `bolí mě v krku` | ACIFEIN (0,74) | |
| `bolí mě zuby` | ACIFEIN (0,85) | |

### B. Filtry — tady se hodí matice výš

| dotaz | co se předvádí |
|---|---|
| `volně prodejný lék na bolest hlavy` | filtr výdeje (ACIFEIN 1,00, PARALEN 0,78) |
| `hrazený lék na bolest` | **ULTRACOD (0,80)** — Rx a hrazený |
| `nehrazený lék na předpis proti bolesti` | **TALVOSILEN FORTE (0,74)** |
| `volně prodejný lék na alergii` | **ZYRTEC (0,70)** |
| `lék s paracetamolem` | PARALEN, ACIFEIN, **ULTRACOD**, **TALVOSILEN** — tatáž látka, tři kombinace filtrů |
| `hrazené antibiotikum` | hrazení ≠ výdej — ABAKTAL ano, AMOKSIKLAV ne |
| `hrazený lék na štítnou žlázu` | ALTHYXIN (0,60) |

**Pointa k vypíchnutí:** hrazení a výdej jsou dvě nezávislé věci.
V korpusu je 5 léčiv na předpis, která hrazená nejsou.

### C. Čtení celé sekce (nové 24.8.)

Když dotaz jmenuje **konkrétní lék a konkrétní sekci**, systém pozná, že
si ji chce člověk **přečíst**, ne v ní hledat. Vrátí ji **celou v pořadí
dokumentu** — ne jednu „nejpodobnější" pasáž.

| dotaz | co vrátí |
|---|---|
| `dávkování zyrtec` | ZYRTEC, **6 položek**, obecné dávkování první |
| `nežádoucí účinky amoksiklav` | AMOKSIKLAV, **44 položek** |
| `kdy se nesmí brát paralen` | PARALEN, kontraindikace celé |
| `kolik paralenu můžu dát dítěti` | PARALEN, dávkování celé |

**Proč to tak je** — dobrá věta do prezentace: do vektoru jde jen název
léku, který v textu sekce vůbec není. Podobnosti vyjdou 0,320 / 0,307 /
0,303, což je šum. Řadit podle toho by znamenalo ukázat náhodnou pasáž.
Výběr už udělal filtr, takže se vrací pořadí z dokumentu.

V GUI je u řádku *„celá sekce, 44 položek — rozbalte ▼"*.

### D. Frekvence nežádoucích účinků (nové 24.8.)

Frekvence je řízená hodnota ze šesti stupňů (velmi časté … není známo),
takže se dá filtrovat.

| dotaz | co vrátí |
|---|---|
| `velmi časté nežádoucí účinky` | 3 léčiva, samé velmi časté |
| `vzácné nežádoucí účinky ablymico` | **jen vzácné** (1 položka) |
| `časté a častější účinky ablymico` | 24 položek — časté **i** velmi časté |
| `velmi časté nežádoucí účinky paralen` | **nic — a je to správně** |

**Dvě pointy k vypíchnutí:**

1. **„Vzácné" znamená vzácné.** Kdyby filtr fungoval jako „stupeň 4
   a níž", vrátil by u ABLYMICA i 19 častých a 5 velmi častých — přesný
   opak toho, co člověk chtěl. Rozšíření na častější se dělá jen
   výslovným „a častější".
2. **Nula u PARALENU je odpověď, ne selhání.** PARALEN velmi časté
   účinky nemá (má jen vzácné, velmi vzácné a není známo). Aplikace to
   napíše natvrdo: *„Filtr nepustil dál ani jeden záznam (… frekvence:
   velmi časté; název obsahuje „Paralen") — taková kombinace v datech
   není."* Když se sekce zúží filtrem, popisek se změní z „celá sekce"
   na **„odpovídá filtru"**, aby netvrdil nepravdu.

### E. Orgánový systém

Nežádoucí účinky mají přiřazenou třídu MedDRA, takže jde filtrovat i podle
postiženého orgánu.

| dotaz | co vrátí |
|---|---|
| `nežádoucí účinky na srdce` | „bušení srdce (palpitace)" a další ze třídy *Srdeční poruchy* |

### F. Vynucení sekce v GUI

Rozbalovátko **Omezit na sekci** přebije router. Omezení platí **jen na
sekční výsledky** — filtry z dotazu (Rx/OTC, hrazení, účinná látka) i
základní údaje o léčivu platí dál.

Ověřeno: `paralen` + vynucená sekce *nežádoucí účinky* dá
`filtr = sekce: nezadouci_ucinky; název obsahuje „Paralen"`.

Hodí se, když router sekci uhodne jinak, než člověk chtěl.

### F2. Práh podobnosti posuvníkem

Dobře se na tom ukazuje, **proč práh vůbec je** a že je naměřený, ne
odhadnutý. Dotaz `mám reflux`:

| práh | vrátí |
|---|---|
| 0,30 | 10 léčiv — mezi nimi BISACODYL (zácpa) a ACIFEIN (bolest) |
| **0,55** | **4 léčiva** — MAALOX, OMEPRAZOL, CONTROLOC + 1 |
| 0,75 | 1 léčivo — jen MAALOX (0,86) |

**Pointa:** systém raději neodpoví, než aby si vymyslel — a kde je ta
hranice, je vidět na živo.

Druhá pointa: u dotazu s přesným filtrem (`dávkování zyrtec`) se práh
**neuplatní ani při 0,9** a aplikace to napíše — výběr už udělal filtr,
podobnost tam nemá co měřit.

### F3. Průjem — celá matice v jedné skupině (nové 25.8.)

Skupina A07 je jediná, kde jsou všechny tři kombinace **a k tomu táž
látka ve dvou výdejových režimech**.

| dotaz | co vrátí |
|---|---|
| `něco na průjem` | ERCEFURYL 0,62, HIDRASEC 0,60, ENDITRIL 0,59, IMODIUM 0,59 |
| `volně prodejný lék na průjem` | ENDITRIL, IMODIUM, HIDRASEC — samé OTC |
| `lék na průjem pro děti` | včetně **HIDRASEC PRO DĚTI** |
| `co může způsobit průjem` | 4 léky se shodou **1,00** — průjem jako nežádoucí účinek |
| `hrazený lék na průjem` | **nic — a je to správně** |

**Tři pointy:**

1. **HIDRASEC:** tatáž látka (racekadotril) je ve 100 mg **volně
   prodejná** a ve 30 mg pro děti **na předpis**. Výdej není vlastnost
   látky, ale konkrétního přípravku — a filtr to rozliší, i když je
   název skoro stejný.
2. **`co může způsobit průjem` vs. `něco na průjem`** — táž věc jednou
   jako nežádoucí účinek, podruhé jako indikace. Router to rozliší
   z formulace.
3. **Hrazený lék na průjem neexistuje.** Běžná antidiarrhoika jsou
   samoléčba, takže je pojišťovna neplatí. Jediný hrazený v A07 je
   CEDEPOS (vankomycin), ale ten má indikaci *„infekce Clostridioides
   difficile"* — nemocniční infekci, ne běžný průjem. Systém ho proto
   nevrátí a **je to správně**: laik hledající lék na průjem nemá
   dostat vankomycin.

### G. Skupiny pacientů

ACC má každou indikaci zvlášť pro **dospělé, dospívající a děti od 2 let**.

| dotaz | co se předvádí |
|---|---|
| `lék pro děti na kašel` | ACC (0,75) + skupina pacientů |

### H. Router sám pozná, na kterou sekci se ptáte

Bez jakéhokoli nastavování — sekci určí z formulace.

| dotaz | sekce, kterou router zvolí |
|---|---|
| `co může způsobit paralen` | nežádoucí účinky |
| `kdy se nesmí brát paralen` | kontraindikace |
| `kolik paralenu můžu dát dítěti` | dávkování |
| `co je paralen` | identita z API SÚKL |

Poslední tři vracejí rovnou **celou sekci** (viz C).

### I. Když se nenajde nic (taky ukázka)

| dotaz | co se stane |
|---|---|
| `lék na schizofrenii` | nevrátí nic — v korpusu není |
| `něco na reflux se silou 999mg` | nic + nabídka podle **ATC skupiny** |

**Pointa:** systém raději neodpoví, než aby si vymyslel. Práh 0,55 je
naměřený, ne odhadnutý.

---

## 4. Slabá místa — na tohle se raději neptat

Zjištěno měřením, neskrývá se to:

| dotaz | co je špatně |
|---|---|
| `mám vysoký tlak` | PARALEN skončí stejně vysoko jako ACECOR (0,59 vs 0,59) |
| `lék na cukrovku` | nevrátí nic — ABLYMICO má v indikaci **hubnutí**, ne cukrovku |
| `mám ekzém` | ADVANTAN jen 0,59, těsně nad prahem |

| `co dělá amoksiklav s kůží` | router třídu MedDRA vytáhne správně, ale výsledek propadne prahem |
| `kašel` | druhý výsledek je ACIFEIN „bolest hlavy" (0,57) — viz níž |

První dva jsou vlastnost dat, ne chyba hledání: ABLYMICO opravdu má
v SPC indikaci na obezitu.

**Proč u `kašel` vyleze ACIFEIN:** krátké názvy příznaků si jsou
navzájem podobné, protože pro model jsou to všechno „potíže, se kterými
jde laik do lékárny". Změřeno mezi **nesouvisejícími** příznaky: průměr
0,485 a 4 z 28 dvojic jsou nad prahem. „Bolest hlavy" je z nich
nejcentrálnější (0,567 s kašlem, 0,565 s horečkou, 0,552 s ucpaným
nosem). **Není to chyba dat ani routeru, je to vlastnost embedovacího
modelu.** V ukázce je to obhajitelné — první výsledek je správný
a s velkým náskokem (ACC 0,75 proti 0,57).

Odříznout to relativním odstupem nejde, změřeno: `mám horečku` má
odstup 0,230 a druhý výsledek je přitom **správný**, kdežto `kašel` má
odstup 0,185 a druhý je šum.

**A jedna nestabilita, o které je dobré vědět:** router občas ztratí
název léčiva. `časté nežádoucí účinky amoksiklav` vytáhne jednou
`nazev='Amoksiklav'`, podruhé `nazev=None` — a bez názvu se nespustí
čtení sekce, takže místo 6 položek přijdou 2. Když se to při ukázce
stane, stačí dotaz zopakovat. Je to rozepsané v `todo.md`.
