# Scénáře pro předvádění – celý trh

Korpus **5 880 SPC obchodovaných léčiv** (8 778 kódů SÚKL), stav 1. 10. 2026.
Starší verze pro 32 léčiv je v gitu (commit `1aae11f` a starší).

**Všechny dotazy jsou odzkoušené** stejnou cestou jako GUI (router →
filtry → hledání, práh 0,60). V tabulkách jsou skutečné první výsledky.
Router je nedeterministický, pořadí se může mírně lišit – když se dotaz
„pokazí", stačí ho zopakovat.

★ = doporučeno do prezentace.

---

## 0. Před ukázkou

```
docker compose up -d
uv run uvicorn api:app --port 8000          # GUI http://localhost:8000/
```

- **Po změně kódu vždy restart API** a v prohlížeči **Ctrl+F5**.
- **První dotaz trvá ~12 s** (načítá se model routeru), další 2–3 s.
  Před publikem jeden dotaz „na zahřátí" předem.
- Ollama a Docling běží na DGX – musí být dostupné.

---

## 1. Co je v datech (na otázky publika)

| | |
|---|---|
| léčiva | **5 880 SPC** = všechna obchodovaná léčiva ČR (zářijové vydání SÚKL) |
| hledatelných položek | **451 186** (indikace, kontraindikace, dávkování, nežádoucí účinky) |
| zdroj | oficiální SPC ze SÚKL a EMA, odkaz do PDF na konkrétní stranu |
| extrakce | cloudový model (gpt-6-luna, Batch API), **~8 $ za celý trh** |
| hledání | lokálně: router gemma4:26b + embedding bge-m3 + český fulltext |
| věk použití | odvozen z SPC bez modelu u **87 % léčiv** |

---

## 2. Tahák – všechny hledací vzory

| vzor | jak napsat | příklad | co se stane |
|---|---|---|---|
| **příznak laicky** | běžnou češtinou | `pálí mě žáha` | sémantika v indikacích |
| **výdej** | volně prodejný / na předpis | `volně prodejný lék na bolest hlavy` | filtr OTC / Rx |
| **hrazení** | hrazený / nehrazený | `hrazený lék na reflux` | filtr hrazení pojišťovnou |
| **účinná látka** | lék s X | `volně prodejný lék s paracetamolem` | filtr látky |
| **síla** | název + síla | `paralen 500mg` | přesná síla |
| **kód SÚKL** | 7 číslic | `0218102` | přesný lék |
| **sekce léku** | dávkování / nežádoucí účinky / kontraindikace / na co je + název | `dávkování vibrocil` | **celá sekce** v pořadí dokumentu |
| **frekvence NÚ** | velmi časté / časté / vzácné… nežádoucí účinky + název | `vzácné nežádoucí účinky paralen` | jen daná frekvence |
| **lék + příznak** | název + příznak | `paralen bolest hlavy` | indikace I nežádoucí účinky |
| **NÚ napříč léky** | po kterém léku… | `po kterém léku můžou vypadávat vlasy` | hledá v nežádoucích účincích |
| **věk – děti** | pro děti / dětský | `lék na kašel pro děti` | jen léky s dávkováním pro děti |
| **věk – konkrétní** | dítě X let / X-letý / X měsíců | `horečka dítě šest let` | jen léky od ≤ X let |
| **věk – dospělí** | pro dospělé / u dospělých | `horečka pro dospělé` | léky od 12 let výš nebo bez údaje o věku; bez dětských přípravků |
| **název začíná** | `lék začíná [na] XXX` (≥ 3 znaky) | `lék začíná oxy` | název začíná; řazeno abecedně |
| **název obsahuje** | `lék obsahuje XXX` | `lék obsahuje pox` | část názvu |
| **název končí** | `lék končí [na] XXX` | `lék končí na prazol` | konec slova v názvu |
| **název přibližně** | `lék přibližně XXX` | `lék přibližně zirtek` | překlepy a fonetika; řazeno podle podobnosti |
| **kombinace** | cokoli z výše + příznak | `lék začíná nuro na horečku` | vzory se sčítají |

---

## 3. Scénáře

### A. Laik píše po svém (jádro ukázky)

| dotaz | první výsledky | co ukazuje |
|---|---|---|
| ★ `pálí mě žáha` | ČAJ ZE ŠALVĚJE, OMEPRAZOLE OLIKLA, MAALOX („pálení žáhy (pyróza)") | laické slovo najde odborné „pyróza" |
| ★ `mám reflux` | RENNIE, GAPULSID | slovo „reflux" v textu RENNIE není – „návrat žaludečního obsahu do úst" |
| ★ `bolí mě v krku` | PARAPYREX COMBI, PARACETAMOL DR. MAX, TRACHISAN | jiné druhy léků na tentýž příznak |
| `nemůžu dýchat nosem` | OLYNTH PLUS, SEPTANAZAL | zápor zůstává součástí příznaku |
| `nemůžu spát` | čajová směs, SÉDATIF PC, ADORMA | mezi výsledky i homeopatikum (otevřené rozhodnutí) |
| `pálí mě při močení` | UROLOGICKÁ ČAJOVÁ SMĚS, URCYSTON PLANTA | trefa, ale jen bylinné přípravky |

### B. Filtry výdeje a hrazení

| dotaz | první výsledky | co ukazuje |
|---|---|---|
| ★ `hrazený lék na reflux` | GAPULSID, HELICID, OMEPRAZOLE OLIKLA | filtr z registru SÚKL, ne ze SPC |
| ★ `volně prodejný lék na bolest hlavy` | ACYLPYRIN, VALETOL | OTC |
| `lék na alergii hrazený pojišťovnou` | TAMALIS, FLUTIKASON TEVA (na 1. místě ale MUTAFLOR) | viz slabá místa |

### C. Látka, síla, kód

| dotaz | první výsledky | co ukazuje |
|---|---|---|
| ★ `volně prodejný lék s paracetamolem` | PARALEN (čípky, tablety) | látka + výdej |
| `lék s ibuprofenem` | IBUPROFEN DR. MAX gel, BRUFEN, IBOVAL | různé formy jedné látky |
| `paralen 500mg` | PARALEN 500 MG čípky, tablety, horký nápoj | přesná síla |
| `0218102` | VIBROCIL kapky | kód SÚKL |

### D. Čtení celé sekce konkrétního léku

| dotaz | co se ukáže | co ukazuje |
|---|---|---|
| ★ `dávkování vibrocil` | **tabulka** dávkování kapek i spreje pro všechny věky, rozbaleno samo | čtení sekce, pořadí dokumentu |
| ★ `nežádoucí účinky paralen` | souhrn po frekvencích, rozbalení **seskupené podle četnosti** | tlačítka „zúžit podle četnosti" |
| `kontraindikace aspirin` | všechny kontraindikace ASPIRINU | |
| `na co je zyrtec` | alergická rýma, kopřivka… | indikace jako celek |

### E. Frekvence nežádoucích účinků

| dotaz | první výsledky | co ukazuje |
|---|---|---|
| ★ `velmi časté nežádoucí účinky ibalgin` | nevolnost (nauzea) | přesná frekvence z číselníku |
| `vzácné nežádoucí účinky paralen` | vyrážka, alergický zánět kůže, neklid | „vzácné" = jen vzácné, ne „aspoň vzácné" |
| `co dělá ibalgin se žaludkem` | zánět žaludku (gastritida) | lék + orgán, oba směry |

### F. Lék + příznak a nežádoucí účinky napříč léky

| dotaz | první výsledky | co ukazuje |
|---|---|---|
| ★ `paralen bolest hlavy` | PARALEN – bolest hlavy (indikace) | router hledá v indikacích i NÚ, rozhodnou data |
| `po kterém léku můžou vypadávat vlasy` | METOJECT, AMARHYTON – vypadávání vlasů | NÚ napříč trhem (~10 s) |

### G. Věk pacienta ★ (nové)

| dotaz | první výsledky | co ukazuje |
|---|---|---|
| ★ `horečka dítě šest let` | PARACETAMOL DR. MAX, PANADOL NOVUM (od 6 let) | **BRUFEN od 12 let se neukáže** |
| ★ `suchý kašel dítě pět let` | DITUZDIN, ROBITUSSIN JUNIOR, BRONCHOSTOP | věk slovem i číslem |
| ★ `volně prodejný lék na horečku pro dítě 5 let` | IBUPROFEN DR. MAX sirup, NUROFEN PRO DĚTI | věk + OTC dohromady |
| `kašel u tříletého dítěte` | ROBITUSSIN, ROBITUSSIN JUNIOR | „tříletého" → 3 roky |
| `hrazený lék na reflux pro děti` | HELICID, OMEPRAZOLE OLIKLA | hrazení + děti |

**Pro dospělé ★ (nové 6. 10.)** – opačný směr: zmizí léky pro menší děti.

| dotaz | první výsledky | co ukazuje |
|---|---|---|
| ★ `horečka` | NUROFEN PRO DĚTI JAHODA (2×), VOLTAREN ACTIGO, NOVALGIN, PANADOL NOVUM | bez věku jsou nahoře dětské sirupy |
| ★ `horečka pro dospělé` | VOLTAREN ACTIGO EXTRA, NOVALGIN, CETALGEN, IBOVAL RAPID, PARAPYREX COMBI, PARALEN GRIP | dětské sirupy pryč, zůstaly běžné léky z lékárny |
| ★ `bolí mě v krku pro dospělé` | VOLTAREN ACTIGO EXTRA, STREPFEN, PARAPYREX COMBI, STREPSILS PLUS, CETALGEN | |
| `něco na kocovinu pro dospělé` | IMIGRAN, IBALGIN RAPIDCAPS, CETALGEN, IBALGIN 400, NUROFEN 400 | funguje jen s výrazem `kocovin` v hledacím slovníku (slovník + věk dohromady) |

Co k tomu říct: „pro dospělé" = léky, které SPC připouští **nejdřív od
12 let**, a léky, u kterých SPC věk neuvádí; přípravky určené jen dětem
vypadnou. Projde 4 256 z 5 880 SPC. Hranice 12 let je záměr: přísných
18 let by vyhodilo i IBALGIN a zbyly by hlavně nemocniční léky.

U výsledku je štítek **„věk: od X let"** – vidět, proč lék prošel. Věk se
z SPC odvozuje bez modelu (`vek_pacienta.md`). Kontrolní příklad:
VIBROCIL kapky od 1 roku, sprej od 6 let – rozdíl je v SPC.

### H. Hledání podle názvu ★ (nové)

| dotaz | první výsledky | co ukazuje |
|---|---|---|
| ★ `lék přibližně zirtek` | ZYRTEC | fonetika: i/y, k/c |
| ★ `lék přibližně oftalmoframikoin` | OPHTHALMO-FRAMYKOIN | ph/th, y, spojovník |
| `lék přibližně kalideko` | KALYDECO | |
| `lék přibližně nurophen pro děti` | NUROFEN PRO DĚTI | přibližně + věk |
| ★ `lék začíná oxy` | OXYBUPROCAINE, OXYCODON… abecedně | |
| `lék končí na prazol` | ARIPIPRAZOL, OMEPRAZOL… abecedně | pozor: koncovka chytí i antipsychotika |
| `lék obsahuje pox` | RAPOXOL | |
| ★ `lék začíná nuro na horečku` | NUROFEN PRO DĚTI, NUROFEN 200 | vzor názvu + sémantika |
| ★ `lék začíná ibal na bolest zubů` | IBALGIN 400 – bolest zubů | |

Další krkolomné názvy na zkoušku (všechny ověřené): `eufilin` (EUPHYLLIN),
`chloramfenikol` (CHLORAMPHENICOL), `koldreks` (COLDREX), `klostilbegit`
(CLOSTILBEGYT), `sugamadex` (SUGAMMADEX), `likvifilm` (EFFLUMIDEX LIQUIFILM).

### I. Když to nic nenajde (taky ukázka)

| dotaz | výsledek | co ukazuje |
|---|---|---|
| ★ `recept na svíčkovou` | nic | systém si nevymýšlí |
| `kurz eura dnes` | nic | |
| `lék začíná ox` | vzor nepoužit – „potřeba aspoň 3 písmena" | popis filtru řekne proč |

---

## 4. Slabá místa – na tohle se při prezentaci NEPTAT

| dotaz | co se stane | proč |
|---|---|---|
| `něco na kocovinu` | léky na **covid** | práh 0,60 je z 32 léků, na trhu pouští falešné shody (todo: přeměřit) |
| `lék na plešatost` | čaje na **plynatost** | dtto |
| `rýma miminko`, `ucpaný nos miminko`, `nosní kapky pro kojence` | nemocniční antibiotika v injekcích | léky „od narození" jsou hlavně nemocniční; chybí upřednostnění OTC a formy podání |
| `lék na kašel pro děti` | na 1. místě DALACIN (antibiotikum na bronchitidu) | lepší `suchý kašel dítě pět let` |
| `mám zácpu`, `lék na alergii…` | na 1. místě MUTAFLOR | probiotikum s mnoha indikacemi |
| `nežádoucí účinky paralenu na kůži` | celá sekce, orgán se neuplatní | router orgánový systém nepozná vždy |
| `velmi časté nežádoucí účinky xarelto` | nic | XARELTO velmi časté NÚ nemá (správně, ale vypadá to jako chyba) |
| `lék končí na prazol` bez vysvětlení | i antipsychotika | koncovka ≠ skupina léků |
| hledání podle věku u neobvyklé formulace | věk se nepozná | parser zná dítě X let, X-letý, X měsíců, kojenec, batole, miminko |
| `… pro dospělé` a PARALEN 500, NUROFEN 200, PANADOL NOVUM | chybí, přestože jsou i pro dospělé | SPC je připouští už od 6 let → spodní hranice pod 12; filtr zná jen spodní hranici věku |
| `pro seniory`, `pro člověka 70 let` | filtr na konkrétní věk dospělého není | umí jen „pro dospělé" |
| neobchodovaný lék (např. ALLERGODIL FORTE) | nic | v korpusu jen obchodovaná léčiva |

---

## 5. Kdyby se to pokazilo během ukázky

- **Divný výsledek** → zopakovat dotaz (router je nedeterministický).
- **Špatná sekce** → v GUI vynutit sekci (rozbalovací seznam „sekce").
- **Nic nenalezeno, ale mělo** → posuvník prahu dolů (dnes má smysl jen
  u sémantického hledání; u filtrů a vzorů se neuplatní).
- **GUI se chová postaru** → restart API + Ctrl+F5.
- **Dlouho nic** → model se načítá (stavová hláška v GUI), počkat.

---

## 6. Ukázka chyb v datech ★ – COLDREX HORKÝ NÁPOJ CITRON S MEDEM

**K čemu:** poctivě ukázat, že data z automatické extrakce obsahují
chyby a jak vypadají. Jeden lék, jedna věta SPC, tři chyby. Stav 6. 10.,
neopraveno (`poznatky.md` 6. 10.).

**Dotaz:** `na co je coldrex horký nápoj citron s medem` → celá sekce
indikací (10 položek), kód SÚKL 0260480. Odkaz na PDF otevře bod 4.1.

**Co říká SPC (4.1):**

> Krátkodobá léčba příznaků chřipky a akutního zánětu horních cest
> dýchacích, jako je např. horečka, bolest hlavy, bolest v krku, bolest
> kloubů a svalů, kongesce nosní sliznice, zánět vedlejších dutin nosních
> **a s ním spojená bolest** a akutní katarální zánět nosní sliznice.
>
> Přípravek je určen pro dospělé a dospívající **od 15 let** s tělesnou
> hmotností nad 50 kg.

**Co je v aplikaci:**

| | SPC říká | aplikace ukazuje | proč |
|---|---|---|---|
| 1 | bolest spojená se zánětem dutin | samostatná indikace **„bolest"** | model dělí větu na každém „a"; „s ním spojená" je dovětek, ne další nemoc |
| 2 | pro dospělé a dospívající od 15 let | skupina pacientů **neuvedena** | věta je v jiném odstavci, model ji k indikacím nepřiřadil |
| 3 | od 15 let | štítek **„věk: od 18 let"** | pravidlo pro věk přečte „15–18 let s hmotností pod 50 kg: není určen" jako zákaz do 18 pro všechny |

**Co k tomu říct:**

- 8 z 10 indikací je správně (chřipka, horečka, bolest hlavy, bolest
  v krku, ucpaný nos…). Chyba není „všechno špatně", ale jednotlivé
  položky – a ty se špatně hledají, protože vypadají věrohodně.
- Holá „bolest" je nebezpečnější, než vypadá: lék pak vyjde vysoko
  na každý dotaz o bolesti. V celém trhu ji má 37 léků.
- Srovnání: sesterský `na co je coldrex maxgrip citron` má skoro stejnou
  větu, ale v jednom odstavci – skupinu „od 15 let" i věk má správně.
  Rozhoduje tedy drobnost v úpravě dokumentu.
- Proto je u každého výsledku **odkaz na stranu PDF**: aplikace je
  vyhledávač v oficiálních dokumentech, ne zdroj pravdy.
- Automatické kontroly extrakce existují, ale nad novým korpusem zatím
  neběží – je to další krok, ne hotová věc.
