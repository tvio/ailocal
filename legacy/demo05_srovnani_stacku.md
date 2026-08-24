# UC5 – Srovnání s alternativním RAG stackem (kolega, DGX Spark)

Poznámky ze srovnání aktuálního stacku projektu (PyMuPDF + pgvector + qwen3-embedding)
s produkčním řešením kolegy (Docling + LangChain + Qdrant + BGE-M3 + LangGraph + Gradio),
běžícím na podobném HW (NVIDIA DGX Spark). Vzniklo v návaznosti na ladění `demo05`
(sémantické vyhledávání) a objevené problémy s kvalitou chunkování/embeddingů.

## Kolegův stack (shrnutí)

1. **Ingest**: Docling (PDF/DOCX → Markdown) + LangChain `MarkdownHeaderTextSplitter`,
   plus vlastní parser generující "syntetický obsah" z nadpisů (mapa dokumentu předem)
2. **Embeddingy**: `BAAI/bge-m3` (dense) + BM25 přes `fastembed` (sparse), dvě oddělené
   Qdrant databáze (jedna pro logy/dokumentaci, druhá pro směrnice/Linux)
3. **Sémantická cache** v Qdrantu – shoda nad 98 % vrátí odpověď z cache bez volání LLM
4. **Router**: `qwen2.5:14b` – vyhodnotí dotaz, vrátí JSON s cílovým expertem/DB
5. **Generátor**: `qwen2.5:72b` – finální odpověď striktně z dodaného kontextu (XML tagy proti halucinaci)
6. **Orchestrace**: LangGraph (stavový automat, expertní uzly)
7. **UI**: Gradio `ChatInterface` se streamováním a ruční volbou DB

## 1. Extrakce dokumentů: Docling vs. PyMuPDF (`get_text("text")`)

Projekt teď používá čistě plochou extrakci (`common/pdf_utils.py`) – žádná struktura,
proto jsme dnes ručně řešili regex na nadpisy, `\n \n` artefakty a zploštění MedDRA tabulky.

- **Docling** (TableFormer + DocLayNet): silné rozpoznání layoutu a tabulek, ale
  5–30× pomalejší než PyMuPDF, potřebuje ~1–2 GB modelových vah a GPU.
- **`pymupdf4llm`** (sesterská knihovna PyMuPDF, stejný vydavatel, `PyMuPDF>=1.25`
  už je závislost projektu): převádí PDF do Markdownu s **reálnými nadpisy**
  (`#`/`##` podle velikosti fontu nebo TOC) a **tabulkami jako Markdown pipe tables**.
  Výrazně levnější krok než Docling, který by dnešní ruční heuristiky z velké části nahradil.

**Doporučení**: zkusit `pymupdf4llm` dřív než Docling – nízké náklady, řeší kořen
dnešních problémů (struktura nadpisů, tabulky).

## 2. Chunking: MarkdownHeaderTextSplitter vs. naše regexy/paragraph-splitting

S reálným Markdown výstupem (z `pymupdf4llm` nebo Doclingu) by `MarkdownHeaderTextSplitter`
řezal přesně na hranicích sekcí – bez hádání podle prázdných řádků a bez fallbacků na
"odstavec delší než chunk_size" (viz `chunk_by_paragraphs()` v `common/pdf_utils.py`,
kam jsme dnes museli přidat fallback přesně kvůli chybějící strukturu).

## 3. Embeddingy: BGE-M3 (dense+sparse) vs. čistě dense (qwen3-embedding)

`BAAI/bge-m3` umí současně dense vektory (význam) i sparse váhy (přesná klíčová slova,
podobné BM25) z jednoho modelu. Přímo řeší dnešní hlavní zjištění: dotaz "schizofrenie"
nebo "kůže a podkožní tkáně" skoro doslovně z dokumentu, a přesto sémantika chunk
nenašla v top-5 – přesně případ, kdy by sparse/keyword složka zachránila výsledek
bez ohledu na kvalitu dense embeddingu. Benchmarky potvrzují: hybrid dense+sparse
soustavně překonává čistě dense i čistě BM25.

Projekt na to má částečně postavenou infrastrukturu – `hybrid_search()`
v `common/db_postgres.py` dělá RRF fúzi sémantiky + české fulltextu, ale
**zatím jen pro tabulku `extrakty`**, ne pro `document_chunks` (probíráno a odloženo
dřív v konverzaci). Dokončení pro `document_chunks` by byl nejbližší ekvivalent
kolegova hybrid přístupu bez nutnosti měnit DB.

## 4. Vektorová DB: Qdrant vs. pgvector

| | Qdrant | pgvector (my) |
|---|---|---|
| Hybrid dense+sparse | nativní, jeden dotaz | ruční SQL (RRF) |
| Filtrování metadat | uvnitř HNSW grafu | post-filter na kandidátech (pomalejší při vysoké selektivitě) |
| Škálování | desítky milionů vektorů | do ~10M v pohodě s HNSW |
| Transakce/joins s ostatními daty | ne | ano – sdílí DB s `extrakty`/`simplify` |
| Provoz | další služba navíc | žádná, už běží |

Pro tenhle projekt (řádově tisíce chunků, teaching/demo účel, sdílená DB) je pgvector
rozumnější – komplexita Qdrantu by se vyplatila až při výrazně větším objemu nebo
potřebě sofistikovaného filtrování. Kolegův use-case (produkční multi-doménový
asistent) je jiná váhová kategorie.

## 5. Router (qwen2.5:14b) + Generátor (qwen2.5:72b) + LangGraph

Malý model rozhoduje **kam** poslat dotaz (levné, rychlé i na pomalé paměti DGX
Sparku – krátký JSON výstup), velký model dělá jen finální generování. Sedí na
dnešní zjištění: **délka generovaného výstupu**, ne velikost modelu, je hlavní
náklad na tomhle HW (viz demo03/03c/03d – timeouty u dlouhých sekcí, ne u krátkých
ANO/NE ověření). Krátký routing dotaz je levný bez ohledu na model.

LangGraph formalizuje orchestraci jako stavový automat – vyplatí se u více
expertů/domén, pro jednodoménový demo projekt jako tenhle pravděpodobně zbytečná
komplexita navíc.

## 6. Sémantická cache

Chybí nám úplně. Princip: embedovat dotaz, zkontrolovat podobnost s uloženými
předchozími dotazy (>98 % → vrátit uloženou odpověď bez volání LLM). Vzhledem
k naměřené pomalosti generování na 72B modelu (desítky sekund až minuty) by
u opakovaných/podobných testovacích dotazů ušetřila reálný čas. Šlo by
implementovat jako malá doplňková tabulka vedle `document_chunks`.

## 7. Gradio UI vs. CLI demo skripty

Jiný cíl, ne technická nadřazenost – `demo05` a spol. jsou záměrně CLI výukové
skripty (viz CLAUDE.md architektura), Gradio dává použitelné webové UI pro
koncového uživatele.

## Web of Science / Scopus / Google Scholar

Akademické vyhledávače literatury, ne technologie k nasazení – relevantní pro
podložení metodologie RAG/chunkování publikovaným výzkumem.

## Shrnutí – priorita podle poměru přínos/náklad

1. **`pymupdf4llm` místo `get_text("text")`** – nejvyšší páka, nejnižší náklad,
   řeší kořen dnešních problémů (struktura nadpisů, tabulky)
2. **Dokončit hybrid search i pro `document_chunks`** (ne jen `extrakty`) –
   infrastruktura na to už částečně existuje
3. Sémantická cache – levné, užitečné pro iterativní testování
4. Qdrant/LangGraph/Gradio – technicky validní, ale řeší jinou váhovou kategorii
   problému, než tenhle demo projekt má

---

## Dodatek – vysvětlivky a prohloubení

### Co znamená "ingest"

Celá vstupní pipeline, která surový dokument promění na něco prohledávatelného –
běží **jednou** při nahrání dokumentu, ne při každém dotazu (na rozdíl od
"retrieval", to je `demo05`). V tomhle projektu = `demo01`/`demo02`:
extrakce textu → chunking → embedding → uložení do DB.

### Výhoda převodu na Markdown vs. plochý text – konkrétní příklad

Plochý text (dnešní realita, PyMuPDF `get_text("text")`):
```
1. 
NÁZEV PŘÍPRAVKU 
 
PARALEN 500 mg tablety
```
Nadpis vypadá stejně jako běžný text – proto vznikla nutnost ručních regexů
(`_clean_page_text`, `extract_section_regex`) a museli jsme objevit, že PyMuPDF
píše prázdný řádek jako `"\n \n"`, ne čisté `"\n\n"`.

Markdown:
```
## 1. NÁZEV PŘÍPRAVKU

PARALEN 500 mg tablety
```
Nadpis je explicitně označený – žádné hádání.

Nejvýraznější rozdíl je u MedDRA tabulky nežádoucích účinků. Plochý text ji
zploští na řadu nerozlišitelných řádků (proto se nám dnes řezala přesně napůl –
nadpis v jednom chunku, obsah v druhém). V Markdownu je to `|`-oddělená tabulka,
kterou chunker pozná jako jeden strukturovaný celek.

Hranice: Markdown je jen tak dobrý, jak dobře nástroj rozpozná nadpisy/tabulky.
Nekonzistentní typografie nebo sken (obrázek, ne text) může rozpoznávání pořád zmást.

### Používají Docling/pymupdf4llm interně LLM?

Ne, ani jeden negeneruje Markdown přes LLM:

- **`pymupdf4llm`** – čistě heuristický/deterministický kód, žádný model. Nadpisy
  podle velikosti/tučnosti fontu, tabulky podle vestavěného geometrického
  algoritmu PyMuPDF (mezery, čáry, zarovnání sloupců).
- **Docling** – používá specializované **vision/computer-vision modely**, ne
  generativní LLM: layout model (RT-DETR architektura, trénovaný na DocLayNet –
  object detector, stejná rodina jako rozpoznávání objektů na fotkách) a
  TableFormer (vision-transformer na strukturu tabulky z obrázku stránky).

### Docling vs. pymupdf4llm – konkrétní benchmark

| | `pymupdf4llm` | Docling |
|---|---|---|
| Rychlost | ~0,01 s/stránka | 0,3–3 s/stránka (30–300× pomalejší) |
| Přesnost tabulek (TEDS) | neměřeno v benchmarku, u jednoduchých mřížek slušná | 0,887 (89 %) |
| Hardware | jen CPU | ideálně GPU, ~1–2 GB vah |
| Slabina | na skenech tiše vrátí prázdný text, bez chyby | zvládá i skeny |

**Pro naše PDF (SÚKL SPC dokumenty)**: nejsou skeny (dnes úspěšně extrahováno),
tabulky jsou jednoduché mřížky (2–4 sloupce, žádné sloučené buňky) → `pymupdf4llm`
by měl stačit, Docling je investice navíc (GPU, 30–300× pomalejší), která se
nemusí vyplatit na demo projektu s pár desítkami dokumentů.

### Co jsou "váhy" (parametry) modelu a proč u embeddingů méně bolí velikost

Váhy = počet čísel, která se model naučil při trénování. Víc vah = jemnější
vzory, ale větší stažení a víc výpočtu. `qwen3-embedding:8b` = 8 miliard vah,
neobvykle hodně na embedding model (pro srovnání: `embeddinggemma` 300M,
`all-minilm` 22–33M, `bge-m3` ~560M).

Klíčový rozdíl oproti chat modelům (`qwen2.5:72b` a spol.): embedding model
**negeneruje text**, udělá jeden průchod sítí → jeden vektor. Proto velikost
tolik nebolí rychlost jako u chatu (kde jsme na DGX Sparku měřili jednotky
tokenů/s kvůli šířce paměťové sběrnice) – embed volání dnes trvala 0,2–4,6 s
i s 8B modelem.

### Qwen3-Embedding-8B vs. BGE-M3 – MTEB skóre

| | MTEB multilingual | Čeština |
|---|---|---|
| **Qwen3-Embedding-8B** (náš) | **70,58** – špička žebříčku | explicitně v trénovacích jazycích |
| **BGE-M3** (kolega) | 63,0 | podporovaná, nižší celkové skóre |

Model samotný nebyl dnešní problém – na čistě dense kvalitu je `qwen3-embedding:8b`
lepší volba než BGE-M3. Rozbité bylo: (1) ořez na 1024 dim místo nativních 4096,
(2) chunking řezající věty napůl. Obojí opraveno dnes, viz update bloky
v `demo01_pdf_to_vectors.md`.

### Dense vs. sparse (a dense+sparse hybrid)

**Dense vektor** (náš `qwen3-embedding`): 4096 čísel, skoro všechna nenulová,
význam rozprostřený po celém vektoru – zachycuje **téma/význam**, ne přesná
slova. Najde i parafráze (jiná slova, stejný smysl).

**Sparse vektor**: desítky tisíc dimenzí, ale skoro všechny nula – nenulová
hodnota jen u slov, co se v textu opravdu vyskytují, vážená podle vzácnosti/
důležitosti (princip BM25/TF-IDF). V podstatě matematicky formalizovaný keyword
search.

Dnešní problém (dotazy "schizofrenie", "kůže a podkožní tkáně", "sníženou funkcí
jater" – doslovné citace z dokumentu) byl přesně případ pro sparse: keyword
vyhledávání by je našlo okamžitě, dense selhávalo, protože embeduje celý chunk
jako směs témat a přesná shoda slova se v "průměru významu" ztrácí.

| | Dense | Sparse |
|---|---|---|
| Parafráze/synonyma | ✅ | ❌ |
| Spolehlivá přesná shoda termínu | ❌ (citlivé na chunking/dimenzi) | ✅ vždy |
| Napříč jazyky | ✅ | ❌ |

**Dense+sparse (hybrid)** = spočítat oba skóre a zkombinovat (typicky RRF –
Reciprocal Rank Fusion). Přesně tohle dělá `hybrid_search()` v
`common/db_postgres.py` – jen místo BM25/sparse vektoru používá klasický
Postgres fulltext (`ts_rank_cd`, `websearch_to_tsquery`) jako tu keyword
polovinu. Zatím pokrývá jen `extrakty`, ne `document_chunks`.

### BGE-M3 + BM25 – jsou to oba vektory z BGE-M3?

Ne. Kolega používá **dvě různé technologie**:

- **Dense** → `BGE-M3`, skutečný neuronový model (stejná kategorie jako náš
  `qwen3-embedding`)
- **Sparse** → `BM25` přes `fastembed` – **žádná neuronová síť**. Klasický
  statistický vzorec (frekvence slova v dokumentu, vzácnost napříč kolekcí,
  délka dokumentu), žádné trénování.

`fastembed` jen zabalí BM25 výpočet do stejného rozhraní jako neuronové
embeddingy, aby šel poslat do Qdrantu stejným způsobem – uvnitř žádný model
neběží. (BGE-M3 by teoreticky uměl vlastní sparse výstup vyprodukovat sám, ale
podle popisu kolega tuhle vlastní schopnost nevyužívá a lepí BM25 jako
samostatný krok.)

Ukládá se to do Qdrantu jako dva samostatné vektory na jeden bod ("named
vectors"), při dotazu se spustí oba a výsledky se sloučí – stejný vzorec jako
náš `hybrid_search()` (neuronový dense + klasická lexikální technika, uložené
zvlášť, zkombinované při dotazu).

### Příklad hledání: Qdrant vs. pgvector (stejný scénář, dotaz "schizofrenie")

**pgvector** (vzor z `hybrid_search()` v `common/db_postgres.py`, aplikovaný na
`document_chunks` – potřeba: `embedding vector(4096)` sloupec, který máme, +
`content_fts tsvector` sloupec, který zatím nemáme). RRF se musí napsat ručně v SQL:

```sql
WITH semantic AS (
    SELECT id, 1 - (embedding <=> %(vec)s::vector) AS sem_score,
           ROW_NUMBER() OVER (ORDER BY embedding <=> %(vec)s::vector) AS sem_rank
    FROM document_chunks
    ORDER BY embedding <=> %(vec)s::vector
    LIMIT %(limit)s
),
fulltext AS (
    SELECT id,
           ts_rank_cd(content_fts, websearch_to_tsquery('czech_unaccent', %(txt)s)) AS fts_score,
           ROW_NUMBER() OVER (
               ORDER BY ts_rank_cd(content_fts, websearch_to_tsquery('czech_unaccent', %(txt)s)) DESC
           ) AS fts_rank
    FROM document_chunks
    WHERE content_fts @@ websearch_to_tsquery('czech_unaccent', %(txt)s)
    LIMIT %(limit)s
)
SELECT c.id, c.document_name, c.content,
       COALESCE(1.0 / (60 + s.sem_rank), 0) * %(sw)s
     + COALESCE(1.0 / (60 + f.fts_rank), 0) * (1 - %(sw)s) AS combined_score
FROM document_chunks c
LEFT JOIN semantic s ON c.id = s.id
LEFT JOIN fulltext f ON c.id = f.id
WHERE s.id IS NOT NULL OR f.id IS NOT NULL
ORDER BY combined_score DESC
LIMIT %(limit)s
```

V Pythonu je navíc potřeba nejdřív ručně zavolat `embed_text(query)` a hotový
vektor poslat jako parametr `%(vec)s`.

**Qdrant** (ekvivalent, ověřená aktuální syntax klienta):

```python
from qdrant_client import QdrantClient, models
from common.ollama_client import embed_text, get_ollama_url

client = QdrantClient(url="http://localhost:6333")

query_text = "jaky lek je na schizofrenii"
query_vector = embed_text(query_text, base_url=get_ollama_url())  # vlastní Ollama, vrátí list[float]

results = client.query_points(
    collection_name="document_chunks",
    prefetch=[
        models.Prefetch(
            query=query_vector,   # hotový vektor z vlastní Ollamy, ne models.Document
            using="dense",
            limit=20,
        ),
        models.Prefetch(
            query=models.Document(text=query_text, model="Qdrant/bm25"),  # BM25 z FastEmbed katalogu, OK jako zkratka
            using="sparse",
            limit=20,
        ),
    ],
    query=models.FusionQuery(fusion=models.Fusion.RRF),
    limit=5,
)
```

**Důležitá oprava oproti prvnímu návrhu výše:** `models.Document(text=..., model="BAAI/bge-m3")`
**nevolá vaši Ollamu.** Je to zkratka jen pro dvě konkrétní cesty:

1. **FastEmbed** (lokálně u klienta) – Qdrant si sám stáhne kvantizovaná ONNX
   váhy modelu z **omezeného, předdefinovaného katalogu** FastEmbed a spočítá
   embedding lokálně (ONNX Runtime), nebo
2. **Qdrant Cloud server-side inference** – jen pro modely hostované přímo
   Qdrant Cloudem nebo napojené třetí strany (OpenAI, Cohere, Jina AI, OpenRouter).

Váš `qwen3-embedding:8b` běžící ve vlastní Ollamě (`10.6.38.10:11434`) **není
v žádném z těchto katalogů** – Qdrant nemá jak vědět, že má zavolat zrovna váš
server. Pro vlastní/cizí model musíte embedding spočítat sami (přesně jako
u pgvectoru) a poslat **hotový vektor** místo `models.Document(...)`. Tahle
zkratka funguje jen pro modely, které Qdrant/FastEmbed zná samo – u sparse
BM25 přes `Qdrant/bm25` to naopak sedí, protože ten model je přímo součástí
FastEmbed katalogu.

**Rozdíl v praxi:**

| | pgvector | Qdrant |
|---|---|---|
| RRF vzorec | píšete ručně v SQL (CTE, `ROW_NUMBER()`, `1/(60+rank)`) | deklarujete `fusion=models.Fusion.RRF`, engine dopočítá sám |
| Embedding dotazu (vlastní Ollama model) | musíte předpočítat v Pythonu (`embed_text()`) a poslat jako vektor | **stejně tak** – `models.Document()` zkratka funguje jen pro FastEmbed katalog/Qdrant Cloud modely, ne pro vlastní Ollama server |
| Dvě "kolekce" polí | dva sloupce v jedné tabulce (`embedding`, `content_fts`) | dva pojmenované vektory na jednom bodě (`using="dense"`/`"sparse"`) |
| Čitelnost | nižší – RRF matematika viditelná a laditelná přímo v SQL | vyšší – fúze je černá skříňka, ale kratší kód |

Naše SQL verze má výhodu, že přesně vidíme, jak RRF funguje (dobré pro
výuku/demo účel projektu) – Qdrant to schová za jeden parametr, což je
pohodlnější v produkci, ale méně transparentní.

### Co přesně dělá FastEmbed

Knihovna od Qdrantu na **lokální** generování embeddingů – importuje se přímo
do Python kódu, žádný server, žádné síťové volání.

**Jak to technicky funguje:**
- Místo PyTorch/TensorFlow používá **ONNX Runtime** – PyTorch je stavěný na
  inferenci *i* trénování/fine-tuning, což nese zbytečnou zátěž, když chcete
  jen spočítat vektor. ONNX Runtime je odlehčený, jen na spouštění už
  natrénovaných modelů.
- Váhy modelů jsou **kvantizované** (přes Hugging Face Optimum) – komprimované,
  menší soubor, rychlejší běh na CPU, minimální ztráta přesnosti.
- Díky tomu běží i v prostředích jako AWS Lambda, kde by PyTorch byl
  nepraktický (moc těžký/pomalý start).

**Co všechno umí generovat** (mapuje se na dense/sparse rozdělení probírané výš):
- **Dense**: `bge-small`, `multilingual-e5`, `nomic-embed-text-v2-moe`...
- **Sparse**: `BM25`, `SPLADE`, `miniCOIL` – keyword polovina
- **Multi-vector**: `ColBERT` ("late interaction" – srovnává jednotlivé tokeny
  místo jednoho souhrnného vektoru, třetí přístup vedle dense/sparse)
- **Obrázky**: `CLIP`
- **Reranking**: cross-encoder modely na přeřazení výsledků

**Klíčový rozdíl od Ollamy:** Ollama je **server**, se kterým se mluví přes
HTTP API (přesně to, co dělá náš `embed_text()` – REST volání na `/api/embed`).
FastEmbed je **knihovna ve vlastním procesu** – žádný server běžící vedle,
žádný network round-trip.

**Proč se to týká naší situace:** FastEmbed má **pevný, kurátorovaný katalog**
modelů – nejde mu jen tak říct "spočítej to přes libovolný model". Modely
v katalogu jsou navíc vesměs malé (řádově 100M–600M parametrů, optimalizované
na rychlost na CPU) – nic v kategorii našeho `qwen3-embedding:8b`. Ollama
naopak dovolí spustit prakticky cokoli stažené (včetně velkého 8B modelu
s vyšším MTEB skóre), za cenu vlastního provozovaného serveru a bez omezení
na FastEmbed katalog.
