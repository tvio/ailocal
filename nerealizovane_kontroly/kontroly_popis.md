# Kontroly extrakce — co existuje, co je vypnuté, co chybí

> **Stav k 6. 10. 2026:** skripty kontrol leží v této složce a umí jen
> původní korpus 32 léků, který je smazaný. `pipeline.py`, o kterém se
> níž píše, už neexistuje (seznam kroků je `extrakce_all.py` a kontroly
> v něm nejsou). Dokument zůstává jako popis toho, co kontroly dělaly
> a co je potřeba dodělat nad `data/spc/`. Přehled skriptů: `README.md`
> v této složce.

**Stav k 29. 9. 2026: kontroly extrakce jsou DOČASNĚ VYPNUTÉ.**
Přepínač je `config.KONTROLY_ZAPNUTE = False`.

Důvod: zbývá jen tento týden a nový korpus (5 880 SPC) půjde přes cloud
(gpt-6-luna, Batch API s oknem až 24 h, tedy ~2 dny běhu). Přednost má
dostat korpus do JSON. **Kontroly se zapracují až nad novým korpusem**
(úkol v `todo.md` nahoře).

Důsledek: sekce z nového korpusu zůstanou ve stavu **`neovereno`**. To
je pravda, ne chyba, a v GUI i v zadání se to tak musí říkat.

Podrobný výklad celé extrakce je v `docs/pipeline_extrakce.md`. Tady je jen výsek
o kontrolách.

---

## 1. Co přesně je vypnuté

| kontrola | soubor | vypnutá jak | co se děje místo ní |
|---|---|---|---|
| opora klíče | [common/extrakce.py](../common/extrakce.py) `klic_ma_oporu()`, volá `_jeden_pokus()` | `if KONTROLY_ZAPNUTE …` | klíč od modelu projde, jak je |
| krok 4a – deterministická proti zdroji | [zkontroluj_json.py](zkontroluj_json.py) | `pipeline.py` přeskočí `kontrola1` | stav zůstane `neovereno` |
| krok 4b – jiným modelem (gemma4:26b) | [zkontroluj_modelem.py](zkontroluj_modelem.py) | `pipeline.py` přeskočí `kontrola2` | stav zůstane `neovereno` |
| kontrola slovníku modelem | [postav_slovnik.py](postav_slovnik.py) `--zkontroluj` | `pipeline.py` ho nepředá | slovník se postaví, ale neověří |

Jednorázově se dají zapnout přes `pipeline.py --vse --s-kontrolami`.
Skripty jdou dál pustit i samostatně.

**Co vypnuté NENÍ** (není to kontrola, ale parsování a čištění):

- povinné klíče položek + oprava překlepů v názvech klíčů
  (`_jeden_pokus`, `_oprav_klice`). Bez nich by nešlo data načíst.
- normalizace frekvence a orgánového systému (`normalizuj_frekvenci`,
  [common/meddra.py](../common/meddra.py)),
- skupina pacientů (`normalizuj_skupinu`),
- laický tvar ze slovníku (`common/slovnik.py: uplatni`),
- `ocisti_json.py` (číselníky, deduplikace, sjednocení klíče),
- kontrola **konverze** ([common/kontrola_konverze.py](../common/kontrola_konverze.py)).
  Ta proběhla na celém korpusu, výsledek je v `data/spc/_report/podezrele.html`
  (395 podezřelých, zatím neprojito).

**`extrakce_4_db.py`** bez `--jen-ok` nahraje i sekce `neovereno`, takže
vypnutí kontrol hledání nerozbije.

---

## 2. Popis existujících kontrol

### 2.1 Opora klíče – `klic_ma_oporu()`

[common/extrakce.py](../common/extrakce.py)

- **Kdy:** hned po odpovědi modelu, u indikací a kontraindikací.
- **Co:** aspoň polovina významových slov klíče (delších než 2 znaky,
  bez předložek a slov „léčba", „prevence") musí mít shodná **první
  4 písmena** se slovem zdroje. Bez opory se nastaví `klic = null`.
- **Proč vznikla:** model klíčoval „nahoru". U ZYRTECu z „kožní vyrážka
  se svěděním" udělal „chronická idiopatická kopřivka", což je pro laika
  horší (0,562 → 0,352).
- **Slabina (N2):** zdrojem je `laicky`, tedy výstup téhož modelu, ne
  `doslovne`. Navíc se ověřuje dřív, než slovník laický tvar přepíše.

### 2.2 Krok 4a – deterministická kontrola proti zdroji

[zkontroluj_json.py](zkontroluj_json.py) — bez modelu, zadarmo

Porovnává se s ořezanou sekcí po normalizaci (malá písmena, bez
diakritiky, bez mezer a interpunkce):

| sekce | pole | test |
|---|---|---|
| NÚ | `ucinek`, `organovy_system`, `frekvence` | hodnota je podřetězec zdroje |
| indikace, kontraindikace | `doslovne` | totéž |
| dávkování | `davka` | jen čísla: každé musí být ve zdroji (u „1 000" platí obě čtení) |
| všechny | jakékoli pole | žádná azbuka ani CJK (`NELATINKA`; řecká písmena povolená kvůli „γ-GT") |

- Hodnoty kratší než 4 znaky se nekontrolují.
- Když nic nenesedí → `ok`, jinak sekce zůstane `neovereno` a jde do 4b.
- **Slabiny:** laický tvar ani klíč vůbec nekontroluje. U frekvence
  zjišťuje jen, jestli se slovo vyskytuje **někde** v sekci, ne u kterého
  účinku (N4).

### 2.3 Krok 4b – kontrola jiným modelem

[zkontroluj_modelem.py](zkontroluj_modelem.py) — gemma4:26b (`config.MODEL_KONTROLY`), umí i `--model gpt-6-luna`

- **Co dostane:** jen sekce, které nejsou `ok`. Ořezaný zdroj
  + očíslované položky.
- **Otázka:** má položka oporu ve zdroji? Za chybu se počítá vymyšlená
  položka, jiná frekvence, jiný SOC nebo věcně jiný obsah.
  **Zjednodušení se za chybu výslovně nepočítá.**
- **Výstup:** `kontrola_modelem.chybne_indexy`. Stav `ok`, nebo
  `zamitnuto_kontrolou`. `extrakce_4_db.py` pak vyřadí jen označené položky.
- **Proč jiný model:** model si neodsouhlasí vlastní chybu.
- **Slabiny:** na gemma4:26b se neměřila (převzato 24. 9. podle routeru).
  Indexy jsou **pozice v seznamu**, takže je `ocisti_json.py`
  a `rozdel_vycty.py` po kontrole posunou (N5).

### 2.4 Kontrola slovníku modelem

[postav_slovnik.py](postav_slovnik.py) `--zkontroluj` — gemma4:26b

- Dávky po 20 dvojicích (odborný termín → laický tvar): „odpovídá laický
  tvar věcně termínu?" Označené dvojice jdou do `slovnik_pojmu.md`
  k ručnímu projití. Ruční dvojice (`slovnik_rucni.json`) se nekontrolují.
- **Slabina:** kontroluje jen kanonický tvar termínu, ne každou položku.
  U indikací a kontraindikací jen termíny do 3 slov (N1).

---

## 3. Co chybí – k zapracování nad novým korpusem

Čísla N odkazují na `docs/pipeline_extrakce.md` kap. 7.

| # | co | návrh | stav |
|---|---|---|---|
| **N1** | laický tvar dlouhých indikací a kontraindikací neověřuje nic | slova laického tvaru bez opory ve zdroji ani ve slovníku = podezření; + kontrola modelem, který smí napadnout i zjednodušení | odloženo |
| **N2** | opora klíče proti `laicky` místo `doslovne` | ověřovat proti `doslovne` (nebo obojímu), **nejdřív změřit**; pouštět až po slovníku | odloženo |
| **N3** | pravidla pro klíč jen v promptu | funkce `zkontroluj_klic()`, bez modelu, viz 3.1 | odloženo |
| **N4** | vazba účinek → frekvence se u sekcí `ok` neověřuje | porovnat s frekvencemi ze značek PDF (kontrola konverze je už má) | odloženo |
| **N5** | posun `chybne_indexy` po `ocisti_json`/`rozdel_vycty` | stabilní ID položky, nebo kontrolovat až po všech úpravách | odloženo |
| N8 | ořez se počítá 3× z plné sekce | uložit ořez, který šel do modelu, a kontrolovat proti němu | odloženo |
| – | kontrola 4b na gemma4:26b nezměřená | změřit na 32 léčivech proti výsledkům z 31b | odloženo |
| – | regresní sada známých zmetků | ULTRACOD „alenzie", OMEPRAZOL „řinčení", BISACODYL „ve třasu", HIDRASEC klíč „onemocnění", ACECOR „hruci" – kontrola je MUSÍ chytit | odloženo |

### 3.1 N3 – naměřeno 29. 9. na 32 léčivech

Z 316 položek indikací a kontraindikací jich klíč mělo 164:

| pravidlo | bez modelu? | nálezy |
|---|---|---|
| délka 1–4 slova | ano | **36 ze 164 (22 %) delších**; délky 1:12, 2:34, 3:47, 4:35, 5:20, 6:10, 7:5, 8:1 |
| obecné slovo | ano, černá listina | „onemocnění" 1× (ENDITRIL), samotná „alergie" 7× v kontraindikacích |
| začíná předložkou / „léčba" / „prevence" | ano | 1× „prevence vzniku vředů" (CONTROLOC) |
| chybí diakritika / překlep | ano, porovnat se slovy zdroje bez diakritiky | „ucpany nos" (AFRIN), „bolest na hruci" (ACECOR) |
| 1. pád | jen přibližně (hunspell-cs), falešné poplachy u přídavných jmen | nedělat |

Návrh: klíč, který pravidla poruší, nastavit na `null`. Položka se pak
hledá jen podle textu jako dnes. Klíči bez diakritiky doplnit tvar ze
zdroje. O přínosu rozhodne `hledani_evaluace.py`.
