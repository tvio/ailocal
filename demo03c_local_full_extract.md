# UC3c – Lokální model bez regexu: Výsledky testu

> **Update (DGX Spark, qwen2.5:72b, num_ctx 32768):** Původní test níže (gemma3:12b, 12 GB VRAM, `num_ctx: 8192`) selhal – viz "Závěr". Na DGX Sparku s `qwen2.5:72b` a server-side `OLLAMA_CONTEXT_LENGTH=32768` (systemd `override.conf`) demo03c už funguje: model dostane mnohem víc kontextu a je řádově výkonnější. I tak ale 32k tokenů není nekonečno – SPC dokumenty mají někdy 90k+ znaků (~30k tokenů), takže se celý dokument pořád nemusí vejít najednou spolu se system promptem a rezervou na odpověď.
>
> **Řešení: rozdělení dokumentu na části.** `extract_section_local()` teď dokument nejdřív rozseká přes `chunk_text()` (`common/pdf_utils.py`) na kusy o `CHUNK_CHARS = 15000` znacích s `CHUNK_OVERLAP_CHARS = 2000` překryvem (řez na hranici slova, stejná logika jako v demo01). Model pak sekci hledá postupně část po části – u každé části dostane prompt "pokud sekce je tady, vytáhni ji, jinak odpověz NENALEZENO" a vrátí se první platný (ne-odmítavý, dost dlouhý) nález.
>
> **V čem se tohle liší od demo03's regexu:** demo03 používá regex k **nalezení** hranic sekce (hledá nadpisy typu "4.8 Nežádoucí účinky"). Chunking v demo03c regex k nalezení sekce nepoužívá vůbec – kusy se řežou čistě podle velikosti/pozice v textu, bez ohledu na to, kde skutečně sekce začíná a končí. Najít a vytáhnout sekci pořád dělá výhradně model, jen v menších dávkách. `CHUNK_OVERLAP_CHARS = 2000` je pojistka, aby se sekce nerozdělila přesně na hranici dvou kusů (podobně jako overlap u embedding chunkování v demo01/02).
>
> **Proč zrovna 15 000 znaků na kus:** je to výrazně pod limitem 32768 tokenů (≈ 32k × 3 zn./token pro češtinu ≈ 98k zn. teoretické maximum), s velkou rezervou na system prompt, instrukce a generovanou odpověď – ne proto, že by se víc nevešlo, ale aby zbyl bezpečný prostor a odpovědi modelu nebyly tak pomalé jako při běhu na hraně kontextového okna.
>
> **Cena za robustnost:** u velkých dokumentů se sekce hledá ve víc kusech místo jednoho volání – worst case (sekce nenalezena v žádné části) je `počet_sekcí × počet_kusů` LLM volání místo `počet_sekcí`. Pro malé dokumenty (< 15 000 zn.) žádný rozdíl není, `chunk_text()` vrátí jediný kus = celý dokument.

## Účel testu

Ověřit, zda lokální gemma3:12b zvládne extrakci sekcí z celého SPC dokumentu **bez regex preprocessingu** – tedy stejný přístup jako demo03b (OpenAI API), ale na lokálním HW.

## Výsledek: Selhání

Test na dokumentu PARALEN (20k znaků) dopadl špatně:

### Pozorované problémy

- **Vícejazyčné výstupy** – model vrátil extrakce v němčině, angličtině i dalších jazycích místo češtiny. Příčina: s oříznutým kontextem model ztratí orientaci v jazyce dokumentu a přepne do jiného jazyka ze svých trénovacích dat.
- **Thinking poznámky** – místo čisté extrakce model vrátil interní úvahy a komentáře ("Tato sekce obsahuje...", "Můžeme vidět, že...").
- **Velmi pomalé** – celý dokument se posílal 6× (jednou pro každou sekci), přičemž každý request trval desítky sekund.
- **Žádný viditelný nárůst VRAM** – KV-cache se alokuje dynamicky a uvolní po každém requestu, takže v `nvidia-smi` rozdíl nebyl patrný.

### Proč to selhalo

1. **Oříznutý kontext.** PARALEN má 20k znaků ≈ 13–16k tokenů. S `num_ctx: 8192` Ollama tiše ořízla vstup na ~10k znaků. Model dostal neúplný dokument.
2. **Příliš složitá úloha.** Najít konkrétní sekci v 10k znaků textu je pro 12B model náročnější než přepsat 200 znaků (co dělá demo03 s regex preprocessingem).
3. **Multilingual confusion.** gemma3 je trénovaná na mnoha jazycích. Bez dostatečného kontextu pro "ukotvení" v češtině přeskočí do dominantnějšího jazyka (angličtina, němčina).

## Srovnání přístupů

| | demo03 (regex+LLM) | demo03b (OpenAI API) | demo03c (lokální, celý dok.) |
|---|---|---|---|
| **Přístup** | regex ořez → LLM čištění | celý dok. → cloud LLM | celý dok. → lokální LLM |
| **Kvalita** | ✅ přesná | ✅ přesná | ❌ špatná |
| **Jazyk výstupu** | ✅ čeština | ✅ čeština | ❌ mix jazyků |
| **Rychlost** | 10–30s/sekce | 1–3s/sekce | 30–60s/sekce |
| **PARALEN (20k zn.)** | 6/6 sekcí | 6/6 sekcí | ~2–3/6 použitelné |

## 128k kontext = technická kapacita, ne kvalita

gemma3:12b oficiálně podporuje 128k tokenů. Proč tedy selže na 8k?

### Kapacita ≠ kvalita

128k tokenů znamená, že model je **technicky schopen** je přijmout a zpracovat. Ale **kvalita pozornosti** (attention) na dlouhém kontextu dramaticky klesá. Velké modely (GPT-4, GPT-5.4, Claude) jsou na dlouhé kontexty explicitně trénovány a testovány ("needle in a haystack" testy). Malé modely (12B) mají 128k jako horní limit, ale reálně dobře fungují na **4–8k tokenů**.

Analogie: auto má tachometr do 240 km/h, ale bezpečně jede 130.

### Ollama nepřidává problém (ale ořezává kontext)

Ollama samotná model nezhoršuje. Co dělá:
- **`num_ctx` limit** – ořízne vstup, pokud je delší než nastavený limit. To je ochrana VRAM, ne chyba.
- **Kvantizace** (q4) – zmenšuje model z 24 GB na 8 GB za cenu mírné ztráty kvality. Na krátkém kontextu to nevadí, na dlouhém se ztráty sčítají.
- **Tiché oříznutí** – žádná chyba, žádné varování. Uživatel neví, že model dostal jen polovinu textu.

### Model selhal i na kontextu menším než jeho limit

PARALEN (20k znaků) s `num_ctx: 8192`:
- Prompt (system + instrukce): ~200 tokenů
- Text dokumentu: oříznut na ~8000 tokenů ≈ ~10k znaků (polovina dokumentu)
- I kdyby dostal celý dokument (s `num_ctx: 16384`), **12B model špatně sleduje složité instrukce na dlouhém textu**. To není limit kontextového okna, ale limit schopností modelu.

### Přepočet tokenů pro český text

Český text má vyšší poměr tokenů na znak než angličtina (diakritika, delší slova):
- **1 token ≈ 1.2–1.5 znaku** českého textu
- `num_ctx: 8192` → ~10 000–12 000 znaků (vstup + výstup dohromady)
- PARALEN 20k znaků ≈ 13–16k tokenů → s `num_ctx: 8192` se vejde asi polovina

### Příčiny selhání – Ollama vs. Model

| Příčina | Ollama | Model |
|---|---|---|
| Oříznutý vstup (tiché oříznutí) | ✅ | — |
| Špatné instruction following na dlouhém textu | — | ✅ |
| Vícejazyčný výstup (multilingual confusion) | — | ✅ |
| Kvantizace (q4 místo fp16) | ✅ | — |

### Srovnání podmínek běhu – proč stejně velký model dává jiné výsledky

| | gemma3:12b (lokální) | GPT-5.4 Nano (API) |
|---|---|---|
| **Parametry** | ~12B | ~8–15B (odhad) |
| **Papírový kontext** | 128k tokenů | 400k tokenů |
| **Reálný kontext** | 8k tokenů (VRAM limit) | 400k tokenů (datacenter) |
| **Kvantizace** | q4 (4-bit) | fp16/bf16 (plná přesnost) |
| **VRAM modelu** | ~7–8 GB (q4) | ~16–30 GB (fp16, odhad) |
| **VRAM celkem** | 12 GB (sdíleno s KV-cache) | Desítky GB (dedikované) |
| **Trénink** | General purpose, multilingual | Distilled z GPT-5.4, optimalizován pro extrakci |

I při stejném počtu parametrů je výsledek jiný kvůli: plné přesnosti (fp16 vs q4), neomezenému kontextu a specializovanému tréninku na extrakci.

Selhání je **kombinace obojího** – Ollama ořezává kontext kvůli VRAM, a model i s plným kontextem by na složité extrakci z dlouhého textu nebyl spolehlivý. Regex preprocessing redukuje obě strany problému najednou.

## Závěr

Lokální 12B model na 12 GB VRAM **nemůže nahradit regex preprocessing** pro extrakci sekcí z celého dokumentu. Dvoustupňový přístup (regex najde → LLM čistí) je pro lokální běh jediný spolehlivý.

Pro jednostupňovou extrakci (celý dokument → LLM) je potřeba:
- **Větší kontext** (min. 32k tokenů) → vyžaduje 24+ GB VRAM
- **Silnější model** (20B+) → vyžaduje 24+ GB VRAM
- **Nebo cloud API** (GPT-5.4 Nano, Claude) → demo03b
