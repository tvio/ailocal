# Zadání – Dema použití lokálních LLM pro podnikovou praxi

## Přehled use casů

| UC | Název | Soubor | Obtížnost |
|----|-------|--------|-----------|
| 1 | PDF → vektory (jeden dokument) | `demo01_pdf_to_vectors.py` | ⭐⭐ |
| 2 | Více PDF → společná vektorová DB | `demo02_multi_pdf_vectors.py` | ⭐⭐ |
| 3 | Extrakce konkrétní sekce z PDF | `demo03_pdf_section_extract.py` | ⭐⭐ |
| 4 | Zjednodušení odborného textu | `demo04_simplify_text.py` | ⭐ |
| 5 | Sémantické vyhledávání (RAG) | `demo05_semantic_search.py` | ⭐⭐⭐ |
| 6 | Zpracování obrazu (vision) | `demo06_image_analysis.py` | ⭐⭐ |
| 7 | MCP protokol – praktické demo | `demo07_mcp_protocol.py` | ⭐⭐⭐ |
| 8 | Oracle 23ai vs. Postgres pgvector | `demo08_oracle_vs_postgres.py` | ⭐⭐⭐ |
| 9 | *(nový)* Klasifikace e-mailů / tiketů | `demo09_classify_tickets.py` | ⭐⭐ |
| 10 | *(nový)* Sumarizace zápisu z porady | `demo10_meeting_summary.py` | ⭐ |
| 11 | *(nový)* Anomálie v strukturovaných datech | `demo11_anomaly_detection.py` | ⭐⭐ |
| 12 | *(nový)* Generování SQL z přirozeného jazyka | `demo12_text_to_sql.py` | ⭐⭐⭐ |

---

## UC 1 – PDF → vektory (jeden dokument)

**Cíl:** Ukázat kompletní pipeline: načtení PDF → extrakce textu → rozdělení na chunky → embedding přes lokální model → uložení do pgvector.

**Co se ukáže:**
- Jak LLM embedding model převádí text na vektory (co to vlastně znamená)
- Proč je potřeba chunking (kontextové okno, kvalita embeddingů)
- Strategie chunkování: pevná délka vs. overlap vs. rekurzivní (RecursiveCharacterTextSplitter)
- Uložení chunků + metadat (číslo stránky, offset) do PostgreSQL s pgvector

**Model pro embedding:** `nomic-embed-text` (768 dimenzí, přes Ollama endpoint `/api/embed`)
**Knihovny:** `PyMuPDF` (fitz) pro extrakci textu z PDF, `psycopg` pro Postgres

**Ukázkový dokument:** Příbalový leták léku (veřejně dostupné z SÚKL – viz sekce Dokumenty)

---

## UC 2 – Více PDF → společná vektorová DB

**Cíl:** Rozšíření UC1 – zpracovat adresář s více PDF a vytvořit jednotnou prohledávatelnou databázi.

**Co se ukáže:**
- Batch zpracování dokumentů
- Metadata per-dokument (název souboru, kategorie) pro filtrování
- Deduplikace chunků (hash kontrola)
- Dotaz přes všechny dokumenty najednou s filtrací

**Navazuje na:** UC1 (sdílí chunkovací a embedding logiku)

---

## UC 3 – Extrakce konkrétní sekce z PDF

**Cíl:** Z PDF příbalového letáku vytáhnout pouze sekci "Indikace" (nebo jinou konkrétní část).

**Co se ukáže:**
- Dva přístupy:
  1. **Regex/strukturální** – hledání nadpisů a extrakce textu mezi nimi
  2. **LLM-based** – poslat celý text (nebo chunk) modelu s instrukcí "Vytáhni pouze indikace"
- Porovnání přesnosti obou přístupů
- Praktické použití: automatizovaná extrakce strukturovaných dat z nestrukturovaných dokumentů

**Model:** `gemma3:12b` nebo `qwen3:14b` (generativní, pro extrakci)

---

## UC 4 – Zjednodušení odborného textu

**Cíl:** Převést odborný lékařský text na srozumitelný jazyk pro laika.

**Co se ukáže:**
- Prompt engineering – jak formulovat instrukci pro zjednodušení
- Porovnání výstupů různých modelů (gemma3 vs. qwen3)
- Zachování faktické správnosti vs. srozumitelnost
- Měření čitelnosti (Flesch-Kincaid adaptovaný pro češtinu / počet slov nad N slabik)

**Model:** `gemma3:12b` (dobré výsledky v češtině)
**Vstup:** Výstup z UC3 (extrahovaná indikace)

---

## UC 5 – Sémantické vyhledávání (RAG)

**Cíl:** Kompletní RAG (Retrieval-Augmented Generation) pipeline – uživatel položí otázku česky, systém najde relevantní chunky a vygeneruje odpověď.

**Co se ukáže:**
- Embedding dotazu → cosine similarity hledání v pgvector
- Top-K retrieval + reranking
- Sestavení promptu s kontextem (retrieved chunks) + otázkou
- Generování odpovědi s citací zdrojů
- Porovnání kvality: s RAG vs. bez RAG (model "halucinuje" vs. odpovídá z dat)

**Modely:** `nomic-embed-text` (embedding) + `gemma3:12b` (generování)
**Navazuje na:** UC1/UC2 (data v pgvector)

---

## UC 6 – Zpracování obrazu (vision)

**Cíl:** Ukázat multimodální schopnosti – analýza obrázků přes lokální model.

**Co se ukáže:**
- Popis obsahu obrázku (image captioning)
- Vyhledání konkrétního objektu/informace na obrázku
- Kategorizace obrázků (např. typ dokumentu: faktura vs. smlouva vs. leták)
- OCR alternativa – extrakce textu z obrázku dokumentu

**Model:** `gemma3:12b` (podporuje vision – Ollama endpoint přijímá base64 obrázek)
**Endpoint:** `/api/chat` s parametrem `images: [base64_string]`

**Příklady vstupů:**
- Foto faktury → extrakce částky a dodavatele
- Screenshot tabulky → převod na strukturovaná data
- Foto produktu → popis a kategorizace

---

## UC 7 – MCP protokol – praktické demo

**Cíl:** Ukázat Model Context Protocol jako standard pro propojení LLM s externími nástroji a daty.

**Co se ukáže:**
- Co je MCP a proč vznikl (standardizace tool-use)
- Implementace jednoduchého MCP serveru v Pythonu (např. kalkulačka, databázový dotaz, souborový systém)
- Klient, který se připojí k MCP serveru a LLM rozhodne, který nástroj použít
- Reálné scénáře:
  1. **Databázový asistent** – MCP server obaluje PostgreSQL, LLM se ptá na data
  2. **Firemní knowledge base** – MCP server zpřístupňuje interní dokumenty
  3. **Automatizace workflow** – MCP server volá interní API (JIRA, Confluence…)

**Knihovny:** `mcp` (oficiální Python SDK)

---

## UC 8 – Oracle 23ai vs. Postgres pgvector

**Cíl:** Porovnat vektorové schopnosti Oracle Free 23ai (AI Vector Search) s PostgreSQL + pgvector.

**Co se ukáže:**
- Stejná data, stejné embeddingy, dva různé databázové enginy
- Oracle AI Vector Search: `VECTOR` datový typ, `VECTOR_DISTANCE()`, indexy (IVF, HNSW)
- Postgres pgvector: `vector` typ, `<=>` operátor (cosine), `<->` (L2), HNSW/IVFFlat indexy
- Porovnání:
  - **Rychlost** hledání (benchmark na N tisíc vektorů)
  - **Přesnost** (recall@K)
  - **Jednoduchost** nasazení a správy
  - **Integrace** s Oracle ekosystémem (APEX, ORDS) vs. open-source stack

**Poznámka:** Oracle Free 23ai má limit na resources, ale pro demo stačí.

---

## UC 9 *(nový)* – Klasifikace e-mailů / tiketů

**Cíl:** Automatická kategorizace příchozích požadavků (e-mail, helpdesk tiket) do předdefinovaných kategorií.

**Proč je to zajímavé pro podnik:**
- Zrychlení triáže helpdesku – automatické přiřazení priority a kategorie
- Nulová závislost na cloudu – citlivá firemní data zůstávají lokálně
- Jednoduché na pochopení pro management

**Co se ukáže:**
- Zero-shot klasifikace (model dostane kategorie v promptu, bez trénování)
- Few-shot klasifikace (přidání příkladů do promptu)
- Strukturovaný výstup (JSON s kategorií, prioritou, krátkým shrnutím)
- Porovnání přesnosti na 20–30 ukázkových tiketech

**Model:** `gemma3:12b` nebo `qwen3:14b`

---

## UC 10 *(nový)* – Sumarizace zápisu z porady

**Cíl:** Z dlouhého nestrukturovaného zápisu porady vytvořit strukturované shrnutí.

**Proč je to zajímavé pro podnik:**
- Každý to zná – po poradě nikdo neví, co se dohodlo
- Okamžitě viditelný přínos LLM pro běžnou kancelářskou práci
- Snadná ukázka pro kohokoliv

**Co se ukáže:**
- Vstup: volný text (zápis, přepis, poznámky)
- Výstup: strukturovaný JSON/markdown s body: rozhodnutí, úkoly (kdo, do kdy), otevřené otázky
- Chain-of-thought prompting pro lepší extrakci
- Zpracování dlouhého textu (chunking + merge shrnutí)

**Model:** `qwen3:14b` (silný v structured output)

---

## UC 11 *(nový)* – Detekce anomálií v strukturovaných datech

**Cíl:** LLM jako "druhý pár očí" – kontrola tabulkových dat (CSV/JSON) a hledání podezřelých záznamů.

**Proč je to zajímavé pro podnik:**
- Kontrola faktur, objednávek, účetních zápisů
- LLM může najít vzory, které uniknou jednoduchým pravidlům
- Doplněk k tradičním BI nástrojům

**Co se ukáže:**
- Vstup: CSV s fakturami (částka, dodavatel, datum, popis)
- LLM analyzuje a hledá: neobvyklé částky, duplicity, podezřelé kombinace
- Porovnání: pravidlový přístup (pandas) vs. LLM přístup
- Limity: LLM není 100% spolehlivý na numerická data – ukázat kde selhává

**Model:** `qwen3:14b`

---

## UC 12 *(nový)* – Generování SQL z přirozeného jazyka (Text-to-SQL)

**Cíl:** Uživatel popíše dotaz česky, LLM vygeneruje SQL dotaz nad známým schématem.

**Proč je to zajímavé pro podnik:**
- Business uživatelé neznají SQL, ale potřebují data
- Nahrazení jednoduchých ad-hoc reportů
- Velmi efektní demo

**Co se ukáže:**
- Předání DB schématu (CREATE TABLE statements) v systémovém promptu
- Uživatel se česky zeptá → model vrátí SQL
- Validace: SQL se spustí na reálné DB a výsledek se zobrazí
- Bezpečnost: sandboxed spuštění (READ-ONLY role v Postgres)

**Model:** `qwen3:14b` (dobrý v code generation)
**DB:** Jednoduchá ukázková tabulka v Postgres (objednávky, zákazníci)

---

# Použité technologie

| Technologie | Účel |
|-------------|------|
| Python 3.13+ | Všechna dema |
| PostgreSQL 18 + pgvector (Docker) | Vektorová DB |
| PgAdmin (Docker) | Správa a vizualizace DB |
| Ollama | Lokální inference modelů |
| `nomic-embed-text` | Embedding model (768 dim) |
| `gemma3:12b` | Generativní model + vision |
| `qwen3:14b` | Generativní model (structured output, code) |
| `minitral-3:latest` | Lehký model pro jednoduché úlohy |
| Oracle Free 23ai (Docker) | Porovnání vektorového vyhledávání |
| Nvidia RTX 3060 12GB | GPU pro lokální inference |

**Remote Ollama:** `http://192.168.1.215:11434`
**Lokální Ollama:** `http://127.0.0.1:11434`

---

# Struktura projektu

```
ailocal/
├── common/                     # Sdílené moduly
│   ├── __init__.py
│   ├── ollama_client.py        # Ollama API wrapper (chat, embed, vision)
│   ├── pdf_utils.py            # Extrakce textu z PDF, chunking
│   ├── db_postgres.py          # PostgreSQL + pgvector operace
│   ├── db_oracle.py            # Oracle AI Vector Search operace
│   └── config.py               # Společná konfigurace (URL, modely, DB)
├── data/                       # Vstupní dokumenty pro dema
│   ├── pdf/                    # PDF příbalové letáky, smlouvy…
│   ├── images/                 # Obrázky pro UC6
│   ├── emails/                 # Ukázkové e-maily/tikety pro UC9
│   └── meetings/               # Ukázkové zápisy z porad pro UC10
├── demo01_pdf_to_vectors.py
├── demo02_multi_pdf_vectors.py
├── demo03_pdf_section_extract.py
├── demo04_simplify_text.py
├── demo05_semantic_search.py
├── demo06_image_analysis.py
├── demo07_mcp_protocol.py
├── demo08_oracle_vs_postgres.py
├── demo09_classify_tickets.py
├── demo10_meeting_summary.py
├── demo11_anomaly_detection.py
├── demo12_text_to_sql.py
├── docker-compose.yml          # Postgres 18 + pgvector + PgAdmin + Oracle Free
├── ollama_health.py            # Stávající health check
├── chat_self.py                # Stávající demo – dva agenti
├── pyproject.toml
└── README.md
```

---

# Doporučené pořadí implementace

1. **Infrastruktura** – `docker-compose.yml` (Postgres + PgAdmin), `common/` moduly
2. **UC1** – PDF → vektory (základ pro vše ostatní)
3. **UC5** – Sémantické vyhledávání / RAG (navazuje na UC1, nejefektnější demo)
4. **UC3** – Extrakce sekce z PDF
5. **UC4** – Zjednodušení textu (triviální, rychlá ukázka)
6. **UC2** – Multi-dokument (rozšíření UC1)
7. **UC10** – Sumarizace porady (jednoduchý, rychlý wow efekt)
8. **UC9** – Klasifikace tiketů
9. **UC6** – Zpracování obrazu (vision)
10. **UC12** – Text-to-SQL
11. **UC11** – Detekce anomálií
12. **UC7** – MCP protokol
13. **UC8** – Oracle vs. Postgres (na konec, vyžaduje Oracle setup)

---

# České dokumenty – zdroje

Pro dema je potřeba české dokumenty. Doporučené veřejné zdroje:

1. **Příbalové letáky léků (SÚKL)** – https://www.sukl.cz/modules/medication/search.php
   - Volně stažitelné PDF, strukturovaný text, ideální pro UC1–UC5
   - Příklady: Ibalgin, Paralen, Nurofen (známé léky, srozumitelné)

2. **Sbírka zákonů** – https://www.zakonyprolidi.cz/
   - Texty zákonů v češtině, různá délka a složitost

3. **Česká Wikipedie** – exporty článků
   - Vhodné pro testování obecného sémantického vyhledávání

4. **Vzorové smlouvy** – https://www.vzory.cz/ nebo generované
   - Pro UC s klasifikací dokumentů

5. **Vlastní generovaná data:**
   - Ukázkové e-maily/tikety – vygenerujeme přes LLM
   - Zápisy z porad – vygenerujeme přes LLM
   - CSV s fakturami – vygenerujeme syntetická data

**Doporučení:** Stáhnout 5–10 příbalových letáků ze SÚKL jako hlavní dataset. Pro ostatní UC vygenerovat syntetická data přímo v přípravném skriptu.

---

# Podmínky
- Demo musí být jednoduché a snadno pochopitelné
- Cíl: ukazovat kolegům jako reálné možnosti použití LLM v podnikové praxi
- Každé demo = samostatný spustitelný Python skript
- Sdílená logika v `common/` modulech (DRY)
- Komentáře v kódu česky pro srozumitelnost