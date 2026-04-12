# UC1 – PDF → vektory: Teorie a vysvětlení

## 1. Proč 500 znaků na chunk?

Kompromis mezi dvěma protichůdnými požadavky:

- **Příliš malé chunky** (100–200 znaků) → embedding zachytí málo kontextu, výsledky vyhledávání jsou fragmentované, model nedostane dost informací pro odpověď.
- **Příliš velké chunky** (2000+ znaků) → embedding "rozředí" význam (průměruje příliš mnoho témat do jednoho vektoru), hůř se hledá konkrétní informace.

**500 znaků ≈ 3–5 vět** – dostatečně velký kus textu, aby si zachoval sémantický kontext, ale zároveň dost specifický pro přesné vyhledávání. Pro česká SPC dokumenty to funguje dobře, protože jednotlivé odstavce mají typicky 200–800 znaků.

V praxi se to ladí podle domény – pro právní smlouvy může být lepší 800–1000, pro FAQ zase 200–300.

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

## 3. Proč nomic-embed-text a 768 dimenzí?

`nomic-embed-text` je **sentence transformer** – model trénovaný specificky pro generování embeddingů (na rozdíl od generativních modelů jako gemma3).

Proč zrovna tento:

- **Malý a rychlý** (~137M parametrů) – embedding 48 chunků trvá sekundy, ne minuty. Pro 10 000 dokumentů by velký model byl nepoužitelně pomalý.
- **768 dimenzí** – standardní rozměr BERT-class modelů. Není to kompatibilita s jiným konkrétním modelem, ale dostatečný prostor pro zachycení sémantiky. Více dimenzí (1024, 1536) přináší marginální zlepšení za cenu větší paměti a pomalejšího vyhledávání.
- **Běží lokálně přes Ollama** – na rozdíl od OpenAI `text-embedding-ada-002` (1536 dim) nepotřebujete API klíč ani internet.

### Důležité

Embedding model se používá **dvakrát** – při indexaci (ukládání do DB) i při vyhledávání (embedding dotazu). Musí to být **vždy stejný model**, jinak vektory nejsou srovnatelné. Proto je `nomic-embed-text` v configu jako konstanta.

Generativní model (gemma3, qwen3) pak **nedělá vyhledávání** – ten jen čte nalezené chunky a formuluje odpověď v přirozeném jazyce.

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
