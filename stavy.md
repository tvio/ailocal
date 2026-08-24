# Stavy extrakce — co který znamená a kdo ho nastavuje

Každá sekce každého léčiva má **vždy explicitní stav**, nikdy `NULL`.
Uloženo v `data/leciva/<kod>_<NAZEV>/json/_stav.json`, klíč `stav`.

Aktuální přehled: `uv run python pipeline.py --stav`

---

## Proč to nejde řešit NULLem

`NULL` znamená dvě úplně různé věci a nejde je rozlišit:

- lék **opravdu nemá** uvedené nežádoucí účinky (některá SPC sekci nemají)
- extrakce **selhala** a data chybí

Pro aplikaci pro laiky je ten rozdíl zásadní. Nikdy nesmí vzniknout dojem
„tenhle lék nemá žádné nežádoucí účinky", když jsme je jen nedokázali
vytáhnout. **Přiznat mezeru je lepší než mlčky tvrdit opak.**

Zároveň vyhledávač potřebuje vědět, že v dané sekci nemá co hledat — aby
nehlásil „nenašli jsme nic" tam, kde ve skutečnosti nic nemáme.

---

## Číselník stavů

| stav | znamená | nastavuje | smí se ukázat uživateli? |
|---|---|---|---|
| `ok` | ověřeno proti zdroji | `zkontroluj_json.py`, `zkontroluj_modelem.py` | **ano** |
| `neovereno` | extrakce proběhla, nikdo neověřil | `common/extrakce.py` | ne |
| `castecna` | část položek se zachránit dala, část ne | `common/extrakce.py` | ne |
| `zamitnuto_kontrolou` | kontrola našla položku bez opory ve zdroji | `zkontroluj_modelem.py` | **ne** |
| `chybi_v_dokumentu` | sekce v SPC vůbec není | `extrahuj_json.py` | ano, jako „není uvedeno" |
| `selhala_extrakce` | model neodpověděl použitelně | `common/extrakce.py` | ne |
| `prazdna` | sekce existuje, ale nic z ní nevzešlo | `common/extrakce.py` | ne |

### Podrobně

**`ok`** — jediný stav, na kterém se smí stavět výstup pro uživatele.
Znamená, že sekce prošla aspoň jednou kontrolou:

- **doslovným porovnáním se zdrojem** (`zkontroluj_json.py`) — `ucinek`,
  `organovy_system` a `frekvence` se ve zdrojovém textu opravdu vyskytují,
  čísla v dávce sedí; nebo
- **kontrolním modelem** (`zkontroluj_modelem.py`) — jiný model než ten,
  který extrahoval, neoznačil ani jednu položku

**POZOR na rozsah:** `ok` u nežádoucích účinků říká, že sedí **struktura**
— účinek, frekvence, orgánový systém. **Neříká nic o laickém tvaru.**
Ten se ověřuje jinde, v číselníku pojmů (`slovnik_pojmu.md`).

**`neovereno`** — výchozí stav po extrakci. Data existují, ale nikdo je
neporovnal se zdrojem. **Není to totéž co „je to špatně"** — je to
„nevíme". Do aplikace se takové sekce pouštět nemají.

**`castecna`** — model vrátil položky, u kterých části chyběly povinné
klíče. Použitelné se ponechaly, zbytek zahodil. Důvod říká kolik a proč.
Vzniklo z poznatku, že zahodit kvůli pár položkám celou sekci je horší —
ale zamlčet ztrátu je taky horší, takže to stav přiznává.

**`zamitnuto_kontrolou`** — kontrolní model označil aspoň jednu položku
jako nepodloženou zdrojem. **Neznamená to, že je sekce celá špatně** —
znamená to, že se **nesmí použít, dokud na ni nekoukne člověk**.
Seznam takových sekcí je v `todo.md`.

**`chybi_v_dokumentu`** — sekce se v SPC nenašla. Legitimní stav, ne chyba.
Musí být odlišený od `selhala_extrakce`, jinak by aplikace tvrdila
„nemá nežádoucí účinky" tam, kde se jen nepovedla extrakce.

**`selhala_extrakce`** — model neodpověděl použitelně: nevalidní JSON,
spojení spadlo, žádná položka nemá povinné klíče. Reálné příčiny, na které
jsme narazili: markdownová ohrádka kolem JSONu, překlep v názvu klíče,
timeout, rozpadlé spojení.

**`prazdna`** — sekce v dokumentu je, ale nic z ní nevzešlo. Buď byl text
kratší než 20 znaků, nebo model vrátil prázdné pole.

---

## Přechody

```
                    extrakce (krok 3)
                          |
       +------------------+------------------+---------------+
       |          |            |             |               |
  neovereno   castecna   selhala_extrakce  prazdna   chybi_v_dokumentu
       |          |
       |          |   kontrola 4a — doslovné porovnání se zdrojem
       |          |
   bez neshody    +--- (zůstává castecna, částečná data zůstávají částečná)
       |
       v
      ok
       |
  s neshodou --> kontrola 4b — JINÝ model
                    |                    |
              neoznačil nic        označil položku
                    |                    |
                    v                    v
                   ok          zamitnuto_kontrolou --> todo.md, člověk
```

**Dvě pravidla, která z toho plynou:**

1. **Do `ok` se dá dostat jen z `neovereno`.** `castecna` zůstává
   `castecna` i když kontroly projdou — částečná data zůstávají částečná
   a nemá je co povýšit.
2. **`zamitnuto_kontrolou` neopravuje stroj.** Přeextrahování to nespraví
   — ověřeno, že se reprodukovatelné chyby zopakují a vzniknou nové.
   Řeší to člověk, případně zápisem do `slovnik_rucni.json`.

---

## Co stavy NEpokrývají

**Laický tvar (`ucinek_laicky`) není součástí stavu sekce.** Ani jedna
kontrola ho neověřuje:

- doslovné porovnání ho ověřit nemůže — je to překlad, ve zdroji doslova není
- kontrolnímu modelu je v promptu **výslovně řečeno**, že zjednodušení
  se za chybu nepovažuje (jinak by hlásil falešné poplachy na každou parafrázi)

Ověřuje se proto **zvlášť, na úrovni termínu**, v číselníku pojmů —
419 dvojic v `slovnik_pojmu.md`, kontrolovaných samostatnou úlohou
„odpovídá tenhle laický tvar tomuhle odbornému termínu?".

Výjimka: u `indikace` a `kontraindikace` žádný odborný tvar vedle sebe
není — položka **je** ten laický text, takže ho kontrolní model posuzuje
proti zdroji normálně. Právě tak se našla obrácená věková hranice
u OLYNTHU a záměna „akutní" za „těžké" u DITHIADENU.
