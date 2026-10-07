# Sémantické vyhledávání v lécích — jak to funguje

Podklad pro vedení IT. Popisuje celý řetězec od stažení dokumentů po
vyhledávání, bez potřeby znát detaily implementace. Stav k 6. 10. 2026.
Dotazy na předvedení jsou v `docs/prezentace_scenare.md`.

**Co to je:** aplikace, které položíte otázku běžnou češtinou („mám reflux",
„volně prodejný lék na bolest hlavy") a ona najde odpověď v oficiálních
dokumentech SÚKL — včetně odkazu na konkrétní stranu původního PDF.

**Proč to není jen fulltext:** uživatel napíše „pálí mě žáha", v dokumentu
stojí „pyróza". Fulltext nenajde nic. Tenhle systém najde léky na pálení žáhy.

**Co běží kde:** vyhledávání běží celé lokálně. Jednorázové zpracování
dokumentů (převod textu do strukturovaných dat) dělá cloudový model –
posílají se do něj jen veřejné dokumenty SÚKL, žádná data uživatelů.

---

## 1. Rozsah

| | |
|---|---|
| léčiva | všechna obchodovaná v ČR, zářijové vydání SÚKL |
| kódů SÚKL | 8 778 |
| různých dokumentů (SPC) | 5 880 – víc balení téhož léku sdílí jeden dokument |
| hledatelných položek | 472 844 (indikace, kontraindikace, dávkování, nežádoucí účinky) |
| cena zpracování v cloudu | asi 11 USD za celý trh včetně oprav |

Původní ukázka ze srpna měla 32 léků. Rozšíření na celý trh ukázalo, co
se škáluje samo (převod, hledání) a co ne (kontrola kvality, viz kap. 5).

---

## 2. Jak se z PDF stanou data

Sedm kroků, jeden seznam, jeden příkaz. Každý krok jde pustit i zvlášť
a po výpadku naváže.

| # | krok | jak | model? |
|---|---|---|---|
| 1 | seznam léčiv, stažení SPC, převod PDF do textu | veřejné API SÚKL a EMA; převod nástrojem Docling na vlastním stroji; automatická kontrola převodu proti PDF | ne |
| 2 | vytažení čtyř sekcí (na co lék je, dávkování, kdy ho nebrat, nežádoucí účinky) | pravidla nad textem | ne |
| 3 | převod sekcí do strukturovaných dat | cloudový model: doslovné znění, laický překlad a krátké heslo pro hledání | **ano** |
| 4 | naplnění databáze, odvození věku použití | pravidla | ne |
| 5 | vektory pro sémantické hledání | lokální model | ano, lokální |
| 6 | rejstřík dokumentů podle názvu a kódu | – | ne |
| 7 | automatická evaluace | sada dotazů se známou správnou odpovědí | lokální |

**Model se na data pouští na jediném místě** (krok 3). Všechno ostatní
jsou pravidla nebo údaje z registru – výdej na předpis, hrazení, účinná
látka, síla a ATC skupina se neodhadují, berou se ze SÚKL.

**Jedna položka = jeden řádek.** „Bolest hlavy, zubů a zad" jsou tři
řádky. Krátký text se hledá přesněji než dlouhá věta.

**Laický překlad dělá model při extrakci:** vedle „pyróza" uloží
„pálení žáhy". Ruční opravy překladu jsou v číselníku, který má přednost
před modelem.

---

## 3. Jak funguje hledání

```
dotaz laika ──► router ──► filtry ──► dva žebříčky ──► spojení ──► práh ──► výsledek
              (model)     (registr)   význam + slova
```

1. **Router** (lokální model, asi 1,5 s) rozloží dotaz: „hrazený lék na
   reflux pro děti" → hledat v indikacích, jen hrazené, jen pro děti,
   text „reflux".
2. **Filtry se uplatní před hledáním.** Výdej, hrazení, látka, síla, kód
   a věk jsou údaje z registru – lék, který podmínku nesplňuje, se
   k hledání vůbec nedostane.
3. **Dva žebříčky:** podobnost významu (vektory) a shoda slov (český
   fulltext). Spojí se do jednoho pořadí.
4. **Práh:** co není dost podobné, se neukáže. Na „recept na svíčkovou"
   aplikace odpoví „nic nenalezeno" – nevymýšlí si.
5. **Výsledek** je věta z dokumentu s odkazem na stranu PDF.

Co umí navíc:

- **číst celou sekci** konkrétního léku („dávkování vibrocil") v pořadí
  dokumentu, dávkování jako tabulku;
- **věk pacienta:** „horečka dítě šest let" vyřadí léky od 12 let,
  „pro dospělé" vyřadí dětské sirupy;
- **hledání podle názvu** i s překlepem („lék přibližně zirtek");
- **hledací slovník:** když aplikace nějakému slovu nerozumí, dá se ji
  to v GUI naučit („kocovina" → hledej i „bolest hlavy").

---

## 4. Jak se měří, že to funguje

Kvalita se měří automaticky po každé změně, ne dojmem.

| test | výsledek | co říká |
|---|---|---|
| laická formulace najde lék ze správné skupiny (20 dotazů) | 18 z 20 | „mám cukrovku" → v první pětici jsou antidiabetika |
| přesnost první pětice | 69 % | zbytek jsou většinou příbuzné přípravky (čaje, homeopatika) |
| dotazy mimo medicínu nevrátí nic (6 dotazů) | 5 z 6 | „jak vyměnit pneumatiku" jednou našlo „výměnu dýchací trubičky" |
| pokrytí: dokument má všechny čtyři sekce | 96 % | zbylé dokumenty některou sekci nemají nebo se nenašla |

Správnost se posuzuje podle skupiny léků z registru (ATC), ne podle
názoru modelu.

---

## 5. Co aplikace neumí a kde chybuje

Tohle je potřeba říct nahlas.

- **Vytěžená data nikdo nekontroluje.** Na 32 lécích se dala projít
  očima; na 5 880 dokumentech ne. Automatické kontroly existují jen pro
  původní malý vzorek a nad celým trhem neběží.
- **Model při dělení textu chybuje.** Před opravou zadání bylo chybných
  asi 4 % položek indikací. Příklad jednoho léku se třemi různými chybami
  z jedné věty je ve scénářích (kapitola 6): lék na chřipku má mezi
  indikacemi holou „bolest", chybí mu věková skupina a místo „od 15 let"
  ukazuje „od 18 let".
- **Práh podobnosti je nastavený na malém vzorku.** Na celém trhu pouští
  falešné shody: „něco na kocovinu" bez slovníku vrátí léky na covid.
- **Neupřednostňuje běžné léky.** Na dotaz o miminku můžou vyjít
  nemocniční antibiotika v injekcích.
- **Router není vždy stejný.** Tentýž dotaz může dopadnout mírně jinak;
  občas ztratí název léku.

**Proto je u každého výsledku odkaz na stranu původního PDF.** Aplikace
je vyhledávač v oficiálních dokumentech, ne zdroj pravdy.

---

## 6. Provoz a náklady

| | |
|---|---|
| zpracování celého trhu | asi 9 hodin čekání na cloud, 11 USD; převod PDF běží na vlastním stroji |
| měsíční aktualizace | plánovaná jako úloha na serveru; dnes se plní vše znovu, zpracování jen změněných dokumentů je další krok |
| jeden dotaz | 2–3 sekundy, z toho router asi 1,5 s |
| co musí běžet pro hledání | databáze, dva lokální modely (router 19 GB, vektory) |
| víc uživatelů najednou | router je úzké hrdlo; druhý stejný stroj ho zdvojí |

**Modely:** lokálně `gemma4:26b` (router) a `bge-m3` (vektory), v cloudu
`gpt-6-luna` (extrakce) – jako jediná z měřených překládá latinu do
laické češtiny a je nejlevnější.

**Technologie:** Python, PostgreSQL s rozšířením pro vektory a českým
fulltextem, Ollama pro lokální modely, Docling pro převod PDF, FastAPI
a jednoduché webové rozhraní bez frameworku.

---

## 7. Co dál

1. Kontrola vytěžených dat nad celým trhem (bez ní nelze data vydávat za
   ověřená).
2. Přeměřit práh a upřednostnit volně prodejné léky a běžné formy podání.
3. Měsíční úloha na serveru se zpracováním jen změněných dokumentů.
4. Přihlášení pro úpravy hledacího slovníku.
