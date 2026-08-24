# UC3 – Extrakce sekcí z PDF: Poznatky z testování

## 1. Dva přístupy k extrakci

### Regex (strukturální)

Regex hledá nadpisy SPC sekcí na začátku řádku (`^\s*4.1\s+Terapeutické indikace`) a extrahuje text mezi nimi. Konec sekce = začátek další sekce (pattern `\d+\.\d*\s+[A-Z]`).

**Výhody:**
- Deterministický – stejný vstup = stejný výstup, vždy.
- Rychlý – milisekundy, žádný GPU.
- Přesný pro regulované dokumenty (SPC) s pevnou strukturou sekcí.

**Nevýhody:**
- Křehký na variabilitu formátování – jiné PDF renderery, jiné mezery, jiné kódování.
- Nezvládá nestandardní dokumenty (jiný jazyk, jiná struktura).

### LLM (jazykový model)

LLM dostane text a instrukci k extrakci konkrétní sekce. V ideálním případě zvládne variabilní formáty bez úprav kódu.

**Výhody:**
- Flexibilní – zvládne různé formáty dokumentů bez změny kódu.
- Umí „pochopit" kontext – rozliší nadpis od tabulky s čísly.

**Nevýhody:**
- Nedeterministický – dva běhy mohou dát mírně odlišný výsledek.
- Závislý na kvalitě a velikosti modelu (viz níže).
- Pomalý – sekundy až minuty na sekci.

## 2. Architektura řešení: Regex + LLM

V praxi se osvědčila kombinace:

1. **Regex najde hrubý výřez** sekce z dokumentu.
2. **LLM text vyčistí** – přepíše do souvislé podoby, opraví OCR artefakty.

LLM tak dělá jen jednoduchou úlohu (přepis), ne složitou (hledání v 20k textu). To dramaticky zvyšuje spolehlivost malých modelů.

Alternativa pro větší modely (20B+, GPT-4, Claude): poslat celý dokument a nechat model najít i extrahovat sekci sám. Malé modely (≤14B) na to nemají dostatečný kontext ani schopnosti.

## 3. Testované modely pro extrakci

| Model | Velikost | Výsledek | Poznámka |
|-------|----------|----------|----------|
| **gemma3:12b** | 12B | ✅ Nejlepší | Přesný přepis, drží se textu, nehallucinuje |
| **qwen3:14b** | 14B | ❌ Nevhodný | Thinking mode, čínské znaky, hallucince |
| **ministral-3** | 3B | ⚠️ Nepřesný | Rychlý, ale přidává text navíc (2.5×) |
| **gpt-oss:20b** | 20B | ❌ Timeout | Příliš velký pro dostupný HW, swapuje |

### Klíčové poznatky

**Thinking modely (qwen3) jsou nevhodné pro extrakci.** Model s reasoning režimem generuje interní úvahy (`<think>` bloky, často v čínštině), místo aby jednoduše kopíroval text. Thinking mode se dá vypnout (`/no_think`), ale model i tak tenduje k hallucincím místo verbatimního přepisu. Reasoning modely jsou navržené pro úlohy vyžadující logiku (matematika, kód), ne pro doslovné kopírování textu.

**Malé modely potřebují malý kontext.** Když gemma3:12b dostala 15 000 znaků textu a instrukci „najdi sekci indikace", často odmítla nebo vrátila nesmysl. Když dostala jen 200 znaků samotné sekce a instrukci „přepiš čistě", fungovala spolehlivě. Menší kontext = jednodušší úloha = lepší výsledek.

**Větší model ≠ lepší výsledek (na omezeném HW).** Model gpt-oss:20b by mohl být přesnější, ale na 16 GB VRAM swapuje do RAM a nedokončí odpověď v timeout limitu (120s). Prakticky použitelný model musí odpovědět do desítek sekund.

## 4. Limity regex extrakce

Regex funguje výborně pro **české SPC dokumenty** s pevnou strukturou (sekce 4.1–6.1). Problémy nastávají:

- **Nestandardní číslování** – některé EU registrace mají jiné formátování nadpisů.
- **Tabulky uvnitř sekcí** – regex musí rozlišit „4.8 Nežádoucí účinky" (nadpis) od „4.8 mg" (hodnota v tabulce). Řešeno matchem `\d+\.\d*\s+[A-Z]` – vyžaduje velké písmeno za číslem.
- **Velmi dlouhé sekce** – sekce 4.8 (nežádoucí účinky) může mít 10 000+ znaků s komplexními tabulkami. Regex ji ořízne správně, ale ztratí formátování tabulek.

Pro variabilní dokumenty (různé jazyky, různé struktury) je regex křehký a větší LLM model s celým dokumentem by byl lepší volbou.

## 5. Validace LLM výstupu

LLM může místo extrakce vrátit odmítnutí: „Omlouvám se, sekce nebyla nalezena." Takové odpovědi se nesmí ukládat do DB jako extrakce.

Validace kontroluje klíčová slova: `nenalezeno`, `chybí`, `nemám`, `nemohu`, `omlouvám`, `nemůžu`. Pokud odpověď obsahuje některé z nich, je označena jako odmítnutí a neuloží se.

## 6. Skrytý problém: Ollama `num_ctx` (kontextové okno)

Toto je pravděpodobně **nejdůležitější praktický poznatek** z celého testování.

### Problém

Ollama spouští modely s defaultním kontextem **2048–4096 tokenů**, i když model oficiálně podporuje 128k. Pokud prompt + vstupní text přesáhne tento limit, Ollama **tiše ořízne vstup** – žádná chyba, žádné varování. Model pak pracuje s neúplným textem a výsledky jsou nesmyslné.

Uživatel si myslí, že model je hloupý nebo nevhodný pro danou úlohu. Ve skutečnosti **model nikdy neviděl celý vstup**.

### Důsledky pro testování modelů

Bez znalosti tohoto parametru je jakékoli srovnávání modelů na delších textech **zavádějící**. Pokud jeden model "selže" na 20k znakovém dokumentu, nemusí to být jeho vina – mohl dostat jen prvních 3000 znaků. To vysvětluje, proč gemma3:12b při přímé extrakci (bez regexu) tak často:

- **Odmítala** extrahovat ("sekce nenalezena") – protože v oříznutém textu skutečně nebyla.
- **Hallucinovala** – model se snažil odpovědět z neúplného kontextu.
- **Shrnovala** místo kopírování – zkrácený vstup vyvolal jiné chování.

### Řešení

V `common/ollama_client.py` jsme nastavili default `num_ctx: 8192`, což odpovídá ~10 000–12 000 znakům českého textu. To je maximum pro 12 GB VRAM s gemma3:12b bez swapování.

```python
default_options = {"num_ctx": 8192}
```

### Kolik textu se vejde

| `num_ctx` | ~CZ znaků | Stačí na |
|-----------|-----------|----------|
| 2048 (Ollama default) | ~2 500–3 000 | Krátká sekce (indikace) |
| 4096 | ~5 000–6 000 | Střední sekce |
| **8192 (náš default)** | **~10 000–12 000** | **Dlouhá sekce (nežádoucí účinky)** |
| 16384 | ~20 000 | Celý krátký SPC (swapuje na 12 GB) |

Proto zůstává regex preprocessing klíčový – ořízne text na relevantní sekci (200–3000 znaků), což se bezpečně vejde do kontextu.

## 7. Doporučení pro produkci

- **Regulované dokumenty (SPC, SmPC):** Regex jako primární metoda, LLM pro čištění.
- **Variabilní dokumenty:** Větší model (20B+, nebo API – GPT-4, Claude) s celým dokumentem.
- **Embedding model:** Vždy `nomic-embed-text` (768 dim) – stejný pro indexaci i vyhledávání.
- **Timeout:** 120s je rozumný limit. Model, který nestihne odpovědět, je příliš velký pro daný HW.
- **`num_ctx`:** Vždy explicitně nastavit v Ollama. Default je příliš malý pro většinu reálných úloh.
