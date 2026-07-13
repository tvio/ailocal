# UC1 – PDF → vektory: Teorie a vysvětlení

> **Update (DGX Spark):** `MODEL_EMBED = qwen3-embedding:8b`. Ollama striktně hlídá capability modelu – `/api/embed` funguje jen u modelů, které mají v manifestu `pooling_type` (tj. jsou od výroby postavené jako embedding model). Takových modelů je málo – oficiálně doporučené jsou jen `embeddinggemma`, `qwen3-embedding`, `all-minilm`. `qwen2.5:72b` (`MODEL_CHAT`) tuhle capabilitu nemá (je to čistě generativní/tool-calling model), takže se pro embeddingy **nepoužívá** – zkoušeli jsme to a Ollama vrací `501 This server does not support embeddings` bez ohledu na server flagy. `qwen2.5:72b` zůstává jen na `MODEL_CHAT`.
>
> `EMBED_DIMENSION` je teď **4096 (nativní, bez ořezu)**, ne 1024 jak popisuje sekce 3 níže – ořez na 1024 (Matryoshka truncation) se empiricky ukázal jako škodlivý: na reálném dotazu ("lék na schizofrenii") systematicky vyhrávaly irelevantní chunky nad relevantními, a na 4096 dim se pořadí otočilo zpátky správně. Cena: žádný HNSW/IVFFlat index (nad limitem 2000 dim pro pgvector), sequential scan – pro objem dat v demech (~1700 chunků) bez dopadu.

> **Update – pravidla pro chunkování (`common/pdf_utils.py`):** Vyšetřování špatných výsledků `demo05` (viz `demo05_semantic_search.py`) odhalilo dva reálné bugy a jednu koncepční změnu:
>
> 1. **Čištění textu při extrakci** (`_clean_page_text()`, volá se v `extract_text_from_pdf()`): odstraní čísla stránek na vlastním řádku (`"1/8"`), spojí osamocené číslo sekce s následujícím nadpisem (`"4.1 \nTerapeutické indikace"` → `"4.1 Terapeutické indikace"`) a sjednotí vícenásobné prázdné řádky. PyMuPDF extrahuje prázdný řádek jako `"\n \n"` (mezera mezi newlines), ne čisté `"\n\n"` – na to je potřeba pamatovat u jakéhokoli regexu nad extrahovaným textem.
> 2. **Chunking přepnut na odstavce** (`chunk_pages(..., method="paragraphs")`, výchozí) – místo čistě znakového dělení (`chunk_text`) se používá `chunk_by_paragraphs()`, která řeže na hranici odstavce (regex `\n\s*\n`, ne doslovné `\n\n` – viz bod 1). Důvod: znakové dělení na pevných 300 znacích běžně řezalo krátké pojmenované podsekce (typicky ~150–300 zn., např. "Pacienti se sníženou funkcí jater") přesně napůl, takže ani jeden výsledný chunk neobsahoval kompletní myšlenku. Odstavec delší než `chunk_size` (např. nepřerušená MedDRA tabulka nežádoucích účinků, klidně 800+ znaků bez prázdného řádku uvnitř) se dál rozseká přes `chunk_text()` jako fallback, ať nevznikne jeden obří nediferencovaný chunk.
> 3. **Dva bugy nalezené a opravené cestou:**
>    - Sloučení příliš krátkého posledního kusu (`min_chunk_size=100`, ochrana proti degenerovaným mini-chunkům typu `"ik"` o 2 znacích, které měly v embeddingu patologicky vysokou podobnost k téměř čemukoli) se dřív dělalo spojením **stringů**, ale sousední kusy v `chunk_text()` se z principu překrývají (`overlap`) – spojení stringů tak zdvojilo překrývající se text. Opraveno na spojení přes **indexy** (`spans`), ne stringy.
>    - Oprava ořezu `end` na `text_len` (aby délka posledního kusu vycházela správně) omylem zavedla nekonečnou smyčku – jakmile `end` uvízl na `text_len`, `start = end - overlap` se přestal posouvat. Opraveno explicitním `break` po zpracování posledního kusu.
>
> Po přeindexaci (`docker exec ailocal-postgres psql ... TRUNCATE document_chunks` + `demo02_multi_pdf_vectors.py`) klesl počet chunků z ~1740 na **1693** (méně, ale kvalitnějších – zmizely degenerované fragmenty a čísla stránek/sekcí přestala plýtvat místem).

## 1. Proč 300 znaků na chunk?

Kompromis mezi dvěma protichůdnými požadavky:

- **Příliš malé chunky** (100–200 znaků) → embedding zachytí málo kontextu, výsledky vyhledávání jsou fragmentované, model nedostane dost informací pro odpověď.
- **Příliš velké chunky** (2000+ znaků) → embedding "rozředí" význam (průměruje příliš mnoho témat do jednoho vektoru), hůř se hledá konkrétní informace.

Původně bylo nastaveno 500 znaků, ale u sekcí typu "nežádoucí účinky" (husté výčty: bolest hlavy, průjem, teplota, ...) 500 znaků často pojme více frekvenčních kategorií najednou → embedding je průměr přes moc různých symptomů a sémantické vyhledávání na konkrétní termín (např. "bolest hlavy") hůř míří. **300 znaků** je kompromis, který výčty zkrátí, ale nefragmentuje zbytečně souvislou prózu (indikace, dávkování).

V praxi se to ladí podle domény – pro právní smlouvy může být lepší 800–1000, pro FAQ zase 200–300.

### Řez na hranici slova, ne uprostřed

`chunk_text()` v `common/pdf_utils.py` neřeže na pevném indexu `text[start:end]`, ale posune konec chunku na nejbližší předchozí mezeru/nový řádek – takže se nikdy neuřízne uprostřed slova (`"...bolest hla" | "vy, průjem..."`).

Zvažovali jsme i zarovnání na konec **věty**, ale zavrhli jsme ho:

- Projekt nemá sentence tokenizer (žádný nltk/spacy v závislostech) a naivní regex na `.`/`!`/`?` je v češtině nespolehlivý (zkratky "cca.", "resp.", "tbl.", desetinná čísla).
- Husté výčty vedlejších účinků jsou oddělené čárkami/středníky, ne tečkami – sentence-boundary by v nich vůbec nezasáhlo, takže by nevyřešilo původní problém rozředění.
- Riziko nekontrolovaného přetečení chunku, pokud je nejbližší tečka daleko za cílovou velikostí; u hranice slova je "škoda" maximálně jedno slovo.

## 2. K čemu je overlap (překryv)?

Overlap řeší problém **rozříznutí uprostřed myšlenky**. Bez překryvu:

```
Chunk 1: "...Paralen se nesmí užívat u pacientů s těžkým"
Chunk 2: "poškozením jater nebo při akutní hepatitidě..."
```

Ani jeden chunk nemá kompletní informaci. S overlap = 50 znaků:

```
Chunk 1: "...Paralen se nesmí užívat u pacientů s těžkým"
Chunk 2: "u pacientů s těžkým poškozením jater nebo při akutní hepatitidě..."
```

Chunk 2 teď obsahuje celou větu. **Overlap = pojistka proti ztrátě kontextu na hranicích chunků.** 50 znaků ≈ konec předchozí věty, což obvykle stačí.

## 3. Proč qwen3-embedding:8b a 1024 dimenzí?

Historie voleb embedding modelu v tomhle projektu (tři pokusy, než se to usadilo):

1. **`nomic-embed-text`** (768 dim) – původní volba, viz zdůvodnění níže.
2. **`qwen2.5:72b`** (8192 dim) – po zpřístupnění DGX Spark jsme zkusili použít stejný velký model pro chat i embedding. Fungovalo to jen zdánlivě: DB šla nastavit na `vector(8192)`, ale ANN index (HNSW/IVFFlat) nešel vytvořit (`ERROR: column cannot have more than 2000 dimensions`), takže by se muselo jet bez indexu (sequential scan).
3. **`qwen3-embedding:8b`, `dimensions: 1024`** – aktuální stav. Důvod zvratu: **Ollama negeneruje embeddingy z libovolného modelu.** `/api/embed` kontroluje, jestli model má v manifestu `pooling_type` (capability `embedding`) – to mají jen modely od výroby postavené jako embedding modely. Zkoušeli jsme `qwen2.5:72b` a Ollama vrátila `501 This server does not support embeddings`, bez ohledu na server flagy (`--embeddings` flag ve skutečnosti v aktuální verzi Ollamy ani neexistuje – to byla zavádějící hláška). Oficiálně doporučené embedding modely jsou jen `embeddinggemma`, `qwen3-embedding`, `all-minilm`.

`qwen3-embedding:8b` je Matryoshka-trénovaný (native 4096 dim, ale podporuje uživatelem zvolenou dimenzi 32–4096 přes parametr `dimensions` v requestu, viz `common/ollama_client.py`) – zvolili jsme **1024**, aby zůstal pod limitem 2000 dim a HNSW index šel použít (viz `init-db.sql`, indexy `idx_chunks_embedding` atd. jsou obnovené). Je to zatím největší embedding model dostupný v Ollama library (tagy `0.6b`/`4b`/`8b`) a je multilingvální (100+ jazyků).

`nomic-embed-text` je **sentence transformer** – model trénovaný specificky pro generování embeddingů. Proč byla původně volba na něj:

- **Malý a rychlý** (~137M parametrů) – embedding 48 chunků trvá sekundy, ne minuty. Pro 10 000 dokumentů by velký model byl nepoužitelně pomalý.
- **768 dimenzí** – standardní rozměr BERT-class modelů, a hlavně pod limitem 2000 dim pro pgvector index.
- **Běží lokálně přes Ollama** – na rozdíl od OpenAI `text-embedding-ada-002` (1536 dim) nepotřebujete API klíč ani internet.

### Důležité

Embedding model se používá **dvakrát** – při indexaci (ukládání do DB) i při vyhledávání (embedding dotazu). Musí to být **vždy stejný model** (a stejná `dimensions` hodnota), jinak vektory nejsou srovnatelné. Proto je `MODEL_EMBED`/`EMBED_DIMENSION` v `config.py` jako konstanty.

Generativní model (`MODEL_CHAT = qwen2.5:72b`) **nedělá vyhledávání** – ten jen čte nalezené chunky a formuluje odpověď v přirozeném jazyce. Embedding a chat role jsou teď na dvou různých modelech, což je architektonicky čistší stav než mezikrok č. 2 výše.

## 4. V čem je výhoda různých modelů?

Každý model má jiné silné stránky:

| Model | Role | Proč zrovna on |
|-------|------|----------------|
| **nomic-embed-text** | Embedding (vektorizace) | Malý, rychlý, kvalitní embeddingy. Nemusí umět generovat text. |
| **gemma3:12b** | Hlavní chat + vision | Rozumí češtině, umí vision (obrázky), dobré reasoning. |
| **qwen3:14b** | Strukturovaný výstup | Lepší na JSON, SQL, klasifikaci – drží formát. |
| **minitral-3** | Lehké úlohy | Rychlý pro jednoduché úlohy kde nepotřebujete 12B model. |

### Klíčový princip

**Embedding model ≠ generativní model.** Embedding model převádí text na vektor (čísla). Generativní model generuje text. Jsou to zásadně jiné úlohy a jiné architektury.

V praxi to znamená:

- Vyměnit generativní model (gemma3 → qwen3) → **bez přeindexace** databáze.
- Vyměnit embedding model (nomic → mxbai-embed-large) → **musíte přeindexovat** všechny dokumenty.
- Použít levný/rychlý model na jednoduché úlohy (klasifikace tiketu) a silnější model na složité (sumarizace, SQL generování).
