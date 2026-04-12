# UC3b – Extrakce sekcí přes OpenAI API: Poznatky



## 1. Proč online model?

Lokální gemma3:12b má omezený kontext (~8k tokenů) a pro extrakci sekcí potřebuje regex preprocessing – nejdřív regex najde sekci, pak LLM text vyčistí. To funguje pro standardní SPC dokumenty, ale:

- **Regex je křehký** na variabilní formátování (jiné PDF renderery, EU registrace).
- **Malý model se ztratí** ve velkém textu – odmítá, hallucinuje, shrnuje místo kopírování.
- **Složité sekce** (4.8 Nežádoucí účinky s tabulkami) lokální model nedokáže přesně extrahovat.

Online model s velkým kontextem tyto problémy nemá – dostane celý dokument a sám najde sekci.

## 2. GPT-5.4 Nano – specifikace

| Parametr | Hodnota |
|----------|---------|
| **Kontext** | 400 000 tokenů (~300k znaků CZ textu) |
| **Max output** | 128 000 tokenů |
| **Cena input** | $0.20 / 1M tokenů |
| **Cena output** | $1.25 / 1M tokenů |
| **Optimalizace** | Klasifikace, extrakce dat, ranking |
| **Počet parametrů** | Neveřejný (odhad ~8–15B, distilled z GPT-5.4) |
| **Kvantizace** | fp16/bf16 (plná přesnost) |
| **Odhad VRAM** | ~16–30 GB (fp16, bez kvantizace) |
| **Release** | Březen 2026 |

Pro srovnání lokální gemma3:12b: ~12B parametrů, q4 kvantizace = **~7–8 GB VRAM**. GPT-5.4 Nano v plné přesnosti zabírá odhadem **2–4× víc VRAM**, ale běží na OpenAI datacentru, takže uživatel nic neřeší.

Pro 20k znakový SPC dokument: ~5k input tokenů = **$0.001 za dokument**. Pro 1000 léků/měsíc: ~$1.

## 3. Srovnání výsledků (PARALEN)

| Sekce | Regex | gemma3:12b (lokální) | GPT-5.4 Nano (API) |
|-------|-------|---------------------|---------------------|
| indikace | 200 | 201 | 200 |
| kontraindikace | 233 | 234 | 238 |
| dávkování | 2079 | 2079 | 2147 |
| nežádoucí účinky | 1887 | 1884 | 1995 |
| interakce | 2821 | 2821 | 2848 |
| složení | 86 | 86 | 88 |

GPT-5.4 Nano konzistentně vrací **mírně delší výsledky** – extrahuje kompletněji, protože nepotřebuje regex ořez. Rozdíl je vidět hlavně u složitějších sekcí (nežádoucí účinky: +108 znaků, dávkování: +68 znaků).

## 4. Klíčové rozdíly oproti lokální extrakci

### Přístup k dokumentu
- **Lokální (demo03):** Regex najde sekci → LLM ji přepíše. Dvoustupňový proces.
- **Online (demo03b):** Celý dokument → LLM najde i extrahuje. Jednostupňový.

### Kvalita
- **Regex + gemma3** dává prakticky stejný výstup jako regex samotný (LLM jen přepisuje).
- **GPT-5.4 Nano** extrahuje nezávisle na regexu – může najít obsah, který regex přehlédne.

### Složité sekce (tabulky)
Sekce 4.8 (nežádoucí účinky) často obsahuje rozsáhlé tabulky frekvencí. Lokální gemma3 při přímé extrakci (bez regex preprocessingu) tendovala ke **shrnutí** místo kopírování. GPT-5.4 Nano text extrahoval kompletně.

## 5. Determinismus a konzistence

LLM modely jsou **nedeterministické** – dva běhy mohou dát mírně odlišný výsledek. Pro produkční nasazení (1000 léků/měsíc) je to problém. Mechanismy pro zvýšení konzistence:

- **`temperature: 0`** – minimalizuje náhodnost výběru tokenů (~95% konzistence).
- **`seed`** – OpenAI API parametr pro reprodukovatelnost (~99% konzistence).
- **Structured Output** – JSON schema jako `response_format` nutí model dodržet přesný formát.
- **Post-processing validace** – kontrola délky, porovnání s regex výstupem, flagování outlierů.

Žádný z těchto mechanismů nedává 100% garanci. Pro regulované dokumenty (SPC) je proto doporučený přístup: **regex jako primární extrakce + LLM jako validace/obohacení + lidská kontrola outlierů**.

## 6. Offline vs. online – rozhodovací matice

| Kritérium | Lokální (Ollama) | Online (OpenAI API) |
|-----------|-----------------|---------------------|
| **Bez internetu** | ✅ | ❌ |
| **Bez API klíče** | ✅ | ❌ |
| **Cena** | 0 (vlastní HW) | ~$0.001/dokument |
| **Kontext** | ~8k tokenů | 400k tokenů |
| **Rychlost** | 10–30s/sekce | 1–3s/sekce |
| **Konzistence** | nižší | vyšší (temperature=0, seed) |
| **Data privacy** | ✅ data zůstávají lokálně | ❌ data jdou přes API |
| **Variabilní formáty** | ⚠️ vyžaduje regex | ✅ model si poradí |

Pro **citlivá data** (farma, zdravotnictví) může být lokální model povinností. Pro ostatní případy je API levnější a spolehlivější.

## 7. Proč lokální model nezvládne celý dokument (VRAM a `num_ctx`)

### Papírový vs. reálný kontext

gemma3:12b má oficiálně **128k tokenů** kontextu. Jenže Ollama standardně spouští modely s **kontextem 2048–4096 tokenů**, pokud explicitně nenastavíte `num_ctx`. I když model umí 128k, reálně pracuje s ~4k tokeny.

Nastavení v Ollama API:
```json
{"options": {"num_ctx": 8192}}
```

### VRAM spotřeba podle délky kontextu

Každý token v kontextu potřebuje KV-cache (Key-Value cache) – paměť pro "pozornost" ke všem předchozím tokenům. Pro gemma3:12b (q4 kvantizace, váhy ~7–8 GB):

| `num_ctx` | KV-cache | Celkem (váhy + KV) | Na 12 GB VRAM |
|-----------|----------|-------------------|---------------|
| 2048 (default) | ~0.3 GB | ~8.3 GB | ✅ vejde se |
| 4096 | ~0.6 GB | ~8.6 GB | ✅ vejde se |
| 8192 | ~1.2 GB | ~9.2 GB | ✅ těsně OK |
| 16384 | ~2.4 GB | ~10.4 GB | ⚠️ na hraně |
| 32768 | ~4.8 GB | ~12.8 GB | ❌ swapuje |
| 65536 | ~9.6 GB | ~17.6 GB | ❌ silně swapuje |

### Co se stane při přeplnění VRAM

Ollama automaticky offloaduje vrstvy do systémové RAM. Inference pokračuje, ale **dramaticky zpomalí** (10–50×). Na 12 GB VRAM s gemma3:12b:

- **`num_ctx: 4096`** – bezpečná volba (~5 000 znaků CZ textu)
- **`num_ctx: 8192`** – maximum pro 12 GB VRAM (~10 000 znaků CZ textu)
- **Víc než 8192** – swapuje, odpověď trvá minuty

### Proč regex preprocessing dává smysl

20k znakový SPC dokument ≈ 5–6k tokenů. S defaultním `num_ctx: 4096` se celý dokument do kontextu **nevejde** – Ollama ho tiše ořízne. Proto demo03 používá regex, aby LLM dostal jen relevantní sekci (200–3000 znaků ≈ 100–800 tokenů), což se bezpečně vejde i do minimálního kontextu.

### Srovnání s OpenAI API

OpenAI provozuje modely na clusterech s desítkami GB VRAM na GPU. Kontext 400k tokenů pro GPT-5.4 Nano je **skutečný** – žádné offloading, žádný swap. Celý dokument se pošle najednou, API nic neparceluje.
