# Audit hledání — 22. 9. 2026

**Doporučení: fulltext používat i pro příznaky a klíče, ale rozlišovat úplnou shodu pojmu od shody jednoho obecného slova. Váhu fulltextu zatím nezvyšovat. Nejdřív opravit význam rozšíření a měření šumu.**

Prošel jsem hlavní dokumentaci, historii relevantních pokusů v poznatky.md, cestu router → slovník → hledání → API, extrakci a plnění klíčů, evaluaci a živou databázi v Dockeru. Databáze má 32 léčiv a 1 346 řádků; všech 166 indikací má embedding, 90 také klíč a jeho embedding. Přístup do DB byl přes účet readonly. Produkční kód, slovník, prahy ani data se při auditu neměnily.

Reprodukce: `.venv\Scripts\python.exe audit_hledani.py`. Skript používá stávající Ollamu a uloží audit_hledani.json: 21 dotazů, 44 unikátních formulací, skóre po jednotlivých řádcích, původ vítězného skóre a pět experimentálních režimů. Experimenty používají pevnou sekci indikace, bez routeru, práh 0,60 a RRF 0,8/0,2. Shody skóre stabilizují podle id, takže pořadí shodných pasáží se může od aplikace lišit. Dva dotazy jsou navíc ověřené přímo produkční funkcí hledej.

**1. Problém je v kombinaci rozšíření a maxima přes klíč.**

Pro dotaz `rýma` vznikají varianty `rýma`, `ucpaný nos`, `zánět sliznice nosu`. Rozklad na konkrétních řádcích:

| Pasáž | Původní dotaz, lepší z textu/klíče | Rozšíření, jen celý text | Rozšíření, text i klíč — dnes |
|---|---:|---:|---:|
| OLYNTH, přetížení nosu, id 12648 | 0,387 | 0,642 | 0,726 |
| AMOKSIKLAV, zánět kosti, id 12877 | 0,407 | 0,513 | 0,692 |
| OMEPRAZOL, zánět jícnu, id 12515 | 0,404 | 0,450 | 0,675 |

AMOKSIKLAV i OMEPRAZOL vyhrají porovnáním varianty `zánět sliznice nosu` s krátkým klíčem. Samotné rozšíření nad celým textem by tyto dvě pasáže přes práh 0,60 nedostalo. Rozšíření je přitom pro OLYNTH potřebné: jeho úplné vypnutí není řešení.

Komentáře „maximum může jen pomoci“ v common/hledani.py a dokumentaci platí pro číselné skóre jednotlivého řádku. Neplatí pro přesnost výsledků, jejich pořadí ani odstup od nesouvisejících pasáží. Stejný problém již historie popsala u původní věty uživatele; pro slovníkové varianty a klíče zůstává.

Pravidlo „alespoň dvě slova, jedno konkrétní“ nestačí: `zánět sliznice nosu` i `zánět kosti` ho splňují. Rozhodující je soulad konkrétního významu. Stejně tak současná kontrola klic_ma_oporu vyžaduje jen polovinu významových slov: ověřeno, že pustí klíč `zánět kosti` proti zdroji `zánět sliznice nosu`. To je samostatná slabina kontroly klíčů, nikoli důkaz, že právě tak vznikl existující řádek AMOKSIKLAVU.

**2. Fulltext má smysl pro příznaky; současný OR ničí jejich konkrétnost.**

Počet indikací s nenulovým FTS skóre na dotaz `rýma`:

| Sestavení fulltextového dotazu | Zasažené řádky |
|---|---:|
| Dnes: jen původní rýma | 3 |
| Rozšíření, OR mezi všemi slovy | 43 |
| Rozšíření, AND uvnitř varianty, OR mezi variantami | 5 |

Poslední varianta významově odpovídá `rýma OR (ucpaný AND nos) OR (zánět AND sliznice AND nos)`. Skutečné tvary lexémů a dotazů jsou v JSON výstupu.

Úplné varianty přidají podporu OLYNTHU a AFRINU; pasáže zánětu kosti a jícnu mají nadále FTS 0. Široký OR jim přidá každé 2,0. U samostatného `zánět kůže` zasahuje dnešní OR 43 indikací, úplný AND jednu. Zde se chyba projevuje i bez slovníkového rozšíření.

Pouhé přeskládání FTS ale nesouvisející výsledky neodstraní: stále mají vysoké cosine a projdou prahem. S úplnými variantami se u rýmy zlepší první místa, AMOKSIKLAV však zůstává třetí. RRF určuje pořadí; způsobilost výsledku dnes určuje maximum cosine. Proto je nutné řešit obě vrstvy.

Technická oprava dokumentace: binární je podmínka `@@`, nikoli skóre `ts_rank_cd`. To zohledňuje výskyty, vzdálenost a váhy. Kód má klíč i text ve stejné váze A a připojuje také podobu bez diakritiky; surový rank proto není míra jistoty ani pravděpodobnost. Viz [PostgreSQL 17 — řízení fulltextu](https://www.postgresql.org/docs/17/textsearch-controls.html).

Nedoporučuji mechanicky změnit všechny dotazy na AND. Celá věta `mám rýmu` obsahuje i další lexémy a v tomto pokusu přísný AND nemá žádnou shodu. Úplná shoda se má týkat normalizovaného příznaku nebo řízené varianty; původní věta má jinou roli. Frázová shoda může být silnější bonus, ale jako jediná podmínka by byla zbytečně citlivá na pořadí a vložená slova.

**3. Číselník obsahuje také změny významu, které fulltext nespraví.**

- `bolest hlavy` se rozšíří na `bolest`, `bolesti`, `tlumení bolesti`, `středně silné až silné bolesti`. Tím se ztratí hlava. Proto i úplný AND nad variantami dál pustí obecnou bolest.
- `nízký tlak` i `tlak v uchu` se přes podřetězec `tlak` rozšíří na `vysoký krevní tlak` a `hypertenze`. ACECOR pak dostane cosine 1,000. Přesná shoda s chybnou variantou chybu jen zesílí.
- `kašlu` dostane navíc variantu `zánět průdušek`, zatímco `kašel` ji nedostane. Výsledky se liší kvůli různým pravidlům slovníku, nejen embeddingu.
- `mám rýmu` nezachytí klíč `rýma`: rozsir používá podřetězce bez diakritiky, nikoli lemmatizaci. Čísla z TODO se reprodukují na normalizovaném `rýma`. V GUI záleží na routeru.

Rozšíření musí zachovat konkrétní část těla, typ potíže i zápor. Synonymum, širší pojem a související stav nemají dostávat stejnou váhu ani stejnou možnost samostatně prosadit výsledek. Nejde o to zakázat slova „bolest“ a „zánět“: u obecného dotazu mohou být přesně tím, co uživatel hledá.

**4. Malý experiment ukazuje cestu, ne hotové řešení.**

V režimu `gated/strict` smí slovníková varianta zvýšit cosine jen při úplné lexikální shodě varianty na daném řádku. Původní dotaz zůstává sémantický i bez FTS. Pro `rýma` zůstanou nad 0,60 pouze OLYNTH a AFRIN; pasáž zánětu kosti klesne z 0,692 na 0,407.

Tento experiment není vhodný k plošnému nasazení bez dalšího měření:

- Nepomůže proti chybnému rozšíření `nízký tlak` na vysoký tlak ani proti obecnému `bolest`.
- Nepotlačí šum vytvořený už původním dotazem. Například u refluxu zůstávají některé nesouvisející pasáže nad prahem i po omezení rozšíření.
- Může zahodit legitimní synonymní shodu bez stejných slov. U OLYNTHU konkrétně přestane podporovat variantu `ucpaný nos` na pasáži s výrazem `přetížení nosu`, byť ji zachrání jiná varianta.
- Používá současný index obsahující také generovaný klíč. Pro kontrolu opory odvozeného klíče je silnější důkaz původní obsahový text; klíč by neměl potvrzovat sám sebe.

**5. Existující zelená evaluace tento problém téměř neměří.**

Přímo spuštěný evaluate.test4 dal 10/10 v dnešním nastavení, ale s předaným prahem 0,60 jen 9/10. Test volá hledání bez prahu a bez routeru; kontroluje alespoň jeden očekávaný lék v první pětici. Nekontroluje, zda ostatní čtyři výsledky odpovídají.

`hledej('mám rýmu', sekce=indikace, prah=0.60)` vrací ENDITRIL, HIDRASEC a IMODIUM se skóre přibližně 0,607; AFRIN má 0,567 a vypadne. To je ověření vyhledávací funkce bez routeru, nikoli tvrzení o každém běhu GUI. S normalizovaným `rýma` se reprodukuje problém z TODO. Všech pět experimentálních režimů má na deseti parafrázích s prahem 0,60 shodně 9/10: samotné toto číslo mezi nimi nerozhodne.

Potřebné testy mají obsahovat správné i zakázané PASÁŽE pro týž dotaz. U rýmy hlídat, že se najde nosní pasáž a nevrátí zánět kosti či jícnu. Nezakazovat automaticky celý lék: například AMOKSIKLAV má v datech také jinou, nosní indikaci. Měřit precision@5 / počet známých chybných pasáží nad prahem, recall očekávaných pasáží a výsledky po seskupení po léčivech. Zvlášť testovat normalizované dotazy a celou cestu přes router. Současných osm dotazů na témata mimo korpus tyto záměny uvnitř korpusu nenahradí.

**Doporučené pořadí práce:**

1. Přidat regresní sadu konkrétních záměn a rozklad skóre: původní/rozšířený dotaz × text/klíč, vítězná varianta a úplná/částečná FTS shoda. Zaznamenávat i text vrácený routerem.
2. Opravit slovník tak, aby neztrácel konkrétnost dotazu; sjednotit české tvary a odlišit ekvivalentní varianty od volných souvislostí. Překontrolovat i oporu klíčů v konkrétních významových slovech.
3. Zapojit normalizované varianty do FTS přes OR mezi pojmy, AND uvnitř pojmu. Oddělit potvrzenou shodu původního dotazu od odvozené shody. Přesné názvy, látky a síly nadále řešit primárně existujícími relačními filtry.
4. Omezit možnost, aby rozšíření × krátký klíč samo prosadilo výsledek. Změřit potvrzení úplným pojmem či zachovaným konkrétním významem; nepodmínit veškerou sémantiku doslovnou shodou. Samotná změna FTS pořadí tuto část nenahradí.
5. Teprve potom přeměřit prahy a váhy na rozšířené sadě i stávající evaluaci. Rozlišit pravidla pro identitu a pro obsahové hledání. Silná úplná shoda může mít jiné zacházení než jediný společný obecný token; jeden globální posuvník vah to nevystihuje.

První rozhodnutí tedy není „FTS 20 %, nebo víc“. Je to „co přesně považujeme za shodu a kdy smí odvozený klíč prosadit výsledek“. Z dnešních dat vychází podpora fulltextu pro celé příznakové pojmy jako užitečná; plošné zvýšení váhy současného OR by posílilo prokázaný šum.