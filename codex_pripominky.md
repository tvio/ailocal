**Ano — přesun následné extrakce do cloudu neodstraní náklad na přípravu PDF. V tomto projektu bych nejdřív omezil rozsah práce Doclingu a odstranil opakovanou inicializaci. Plošné nahrazení za `pymupdf4llm` zatím nemá dostatečně ověřenou kvalitu.**

Prošel jsem implementaci, poznámky i uložený benchmark. Kód jsem neměnil ani nespouštěl dlouhou konverzi.

**Co už projekt zjistil**

Relevantní jsou zejména [poznatky.md:142](/C:/python/ailocal/poznatky.md:142), starší rozbor [poznatky.md:3620](/C:/python/ailocal/poznatky.md:3620) a [todo.md:50](/C:/python/ailocal/todo.md:50). Jejich závěry si částečně odporují, proto bych vycházel z konkrétních výsledků.

V přečteném okamžiku obsahoval [bench_konverze.json](/C:/python/ailocal/bench_konverze.json) výsledky pro 16 PDF:

| Varianta | Celkový čas | Zjištění |
|---|---:|---|
| Docling | 347,9 s | Referenční výstup |
| Docling bez OCR | 326,4 s | Markdown totožný u všech 16 PDF |
| `pymupdf4llm` | 106,9 s | Asi 3,25× rychlejší; současná metrika našla 482/504 buněk ve stejném sloupci |

Vypnutí OCR zde ušetřilo **6 %**, nikoli dříve uváděných 15 %. Rozdíly u `pymupdf4llm` ještě samy neprokazují ztrátu informací: mohou zahrnovat odlišné mezery či rozdělení buněk.

**1. První konkrétní oprava: používat jeden převodník opakovaně**

V [common/konverze.py:152](/C:/python/ailocal/common/konverze.py:152) se při každém PDF vytváří nový `DocumentConverter`. Instalovaný Docling přitom uchovává inicializovanou pipeline uvnitř této instance. Nová instance tedy tuto již připravenou pipeline nevyužije.

Benchmark naopak [převodník uchovává](/C:/python/ailocal/bench_konverze.py:52) a měří po zahřátí. **Produkce a benchmark tak nemají stejné podmínky.**

Nejjednodušší změna je jeden převodník na celý sekvenční běh. Přínos je potřeba změřit; z dostupných čísel ho nelze oddělit. Je to ale první úprava, kterou bych udělal, protože nemění způsob převodu dokumentu.

**2. Největší potenciál: Docling jen pro potřebné části**

V místním vzorku 32 SPC:

- 23 sekcí nežádoucích účinků používá tabulku z Doclingu, 9 používá surový text.
- U dávkování je poměr 7 tabulkových ku 25 textovým sekcím.
- Indikace a kontraindikace používají Docling i kvůli nadpisům skupin pacientů.

To poslední je důležité: **Docling zde nezajišťuje pouze tabulky MedDRA.** Zachování nadpisu „Děti“ například umožňuje přiřadit následující indikace správné skupině.

Postupoval bych ve dvou stupních:

1. **Nejdřív převádět Doclingem pouze stránky sledovaných sekcí** 4.1, 4.2, 4.3 a 4.8. Hranice najít levným průchodem textové vrstvy PDF; při nejistotě použít současnou cestu. Tím zachováme stávající převod a vynecháme stránky, jejichž výstup následná extrakce nepotřebuje. Docling podporuje omezení přes `page_range`. [Dokumentace](https://docling-project.github.io/docling/_generated/examples/run_with_accelerator/)
2. **Potom omezovat Docling na skutečně obtížné tabulky.** Textové části zpracovávat přes PyMuPDF, případně ověřený `pymupdf4llm`, se zachováním potřebných podnadpisů.

Pro nový dokument nemůžeme rozhodovat podle současných `_prehled.json` a `strany.json`: **vznikají až po konverzi Doclingem**. Pro benchmark jsou užitečné, pro přeskočení první konverze potřebujeme nezávislé určení hranic. Také neplatí „rychlý převodník nenašel tabulku → tabulka neexistuje“.

**3. Před výměnou převodníku opravit měření věrnosti**

V [bench_konverze.py:128](/C:/python/ailocal/bench_konverze.py:128) se hledá obsah buněk ve stejném sloupci, ale napříč všemi řádky. Na malém umělém příkladu jsem ověřil, že:

- záměna účinků mezi řádky „časté“ a „vzácné“ dostane **100% shodu**;
- zkrácení buňky „vyrážka, bolest hlavy, nevolnost“ na samotnou „vyrážku“ může také dostat **100% shodu**.

Proto dosavadní „8 z 8 správně“ není důkaz zachování vazby frekvence–účinek. Potřebujeme kontrolovat společně **orgánový systém, frekvenci a celý obsah příslušné buňky**, včetně pokračování přes stránku. U vybraných obtížných případů musí být referencí původní PDF; Docling také může chybovat.

**Ještě k počtu SPC:** [poznámky uvádějí](/C:/python/ailocal/poznatky.md:426) 8 803 kódů a 6 618 registračních čísel. To ale samo neprokazuje 6 618 různých PDF. Před konverzí bych deduplikoval podle identity dokumentu a následně otisku jeho obsahu. Tvůj odhad kolem 3 000 SPC zatím nemáme potvrzený ani vyvrácený.

**Začal bych tedy sdílením převodníku a měřením Doclingu pouze nad stránkami potřebných sekcí.** To řeší zbytečnou práci při zachování současného způsobu čtení tabulek. Náhradu `pymupdf4llm` bych rozhodoval až podle opraveného benchmarku, který skutečně odhalí záměnu frekvencí.