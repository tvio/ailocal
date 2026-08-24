# STAV K 24.8.2026 — HOTOVO, PŘIPRAVENO K PŘEDVEDENÍ

**CLI, API i GUI jsou hotové a odzkoušené. Nic neběží na pozadí.**

    docker compose up -d
    uv run uvicorn api:app --port 8000
       aplikace  http://localhost:8000/
       Swagger   http://localhost:8000/docs

Dokumentace: **`scenare.md`** (co zadávat při předvádění), **`gui.md`**
(jak funguje aplikace a API), `hledej.md` (jak funguje hledání),
`poznatky.md` (nejnovější nahoře), `pristupy.md`, `stavy.md`, `todo.md`.

---

## Co je hotové

### Data — 26 léčiv

| krok | skript | výsledek |
|---|---|---|
| stažení ze SÚKL | `stahni_data.py` | 26 léčiv vč. SPC PDF |
| konverze | `konvertuj_spc.py` | Docling, backend `pypdfium2` |
| sekce + ořez | `extrahuj_sekce.py` | **104/104** |
| JSON | `extrahuj_json.py` | 104/104 |
| řízené slovníky | `ocisti_json.py` | bez modelu |
| rozdělení výčtů | `rozdel_vycty.py` | 3 položky → 15 |
| kontrola proti zdroji | `zkontroluj_json.py` | deterministická |
| kontrola jiným modelem | `zkontroluj_modelem.py` | gemma4:31b |
| číselník pojmů | `postav_slovnik.py` | **539 dvojic, 67 ručně** |

Stavy: `ok` 96, `zamitnuto_kontrolou` 6, `castecna` 1, `neovereno` 1.

### Databáze — 1173 hledatelných řádků

| sekce | řádků |
|---|---|
| nezadouci_ucinky | 768 |
| indikace | 155 |
| kontraindikace | 135 |
| davkovani | 89 |
| atributy | 26 |

### Hledání

Router → filtry + sekce, hybridně cosine (bge-m3) + český FTS přes RRF.
Nad tím tři režimy, které vznikly z měření:

- **běžné hledání** — parafráze laika, práh 0,55
- **čtení sekce** — dotaz jmenuje lék a sekci → celá sekce v pořadí
  dokumentu (řadit podle podobnosti tam nemá co měřit)
- **řízené hodnoty** — název, látka, síla, ATC, frekvence → práh se
  neuplatňuje, výběr už udělal filtr

### Evaluace (reprodukovatelná, dva běhy dají totéž)

```
Invarianty filtru           210/210   100%
Auto-recall @5               50/50    100%
Auto-recall @10              54/54    100%
Negativní dotazy (práh 0,55)  7/8      88%
Parafráze (ručně)            10/10    100%
```

Z 60 vzorků je měřitelných 50 (@5) a 54 (@10) — zbytek má text shodný
u víc léčiv, než je hranice, takže tam není co řadit.

Jediný neúspěch: `léčba roztroušené sklerózy` → AMOKSIKLAV 0,564
(„rozlitého zánětu kůže"), tedy nový řádek z rozdělení výčtu.

### Aplikace

`api.py` (FastAPI, Swagger na `/docs`) + `static/` (vanilla JS).
Výpis 26 léčiv A–Z se stránkováním a řazením, hledání s výpisem toho,
co vrátil router, vynucení sekce, rozbalovací metadata, odkaz do PDF
na nalezenou stranu, ATC záchranná síť, předehřátí modelu při startu.

---

## DALŠÍ KROKY

### 1. Ruční projití dat — jediné, co brání „čistému" demu

| co | kde |
|---|---|
| 7 sekcí označených kontrolou | `todo.md` |
| TALVOSILEN — model ztratil část výčtu (bolest hlavy, zubů, nervů) | `todo.md` |
| ZYRTEC — „obecní skupina" místo „obecná" | `todo.md` |
| 1 položka s frekvencí „nejčastějším" (nenormalizovaná) | `todo.md` |

### 2. Nestabilita routeru — vědět o ní při předvádění

`časté nežádoucí účinky amoksiklav` občas ztratí název léčiva a místo
6 položek vrátí 2. **Když se to při ukázce stane, stačí dotaz zopakovat.**
Návrh deterministické pojistky (dohledat název v DB) je v `todo.md`.
Dnes to nechytí žádný test.

### 3. Nedodělky

- **Logování** (krok 16) má zatím jen embedding, zapojit do kroků 1–5
- **Řazení ve výsledcích hledání** — teď jen relevance
- **Filtry Rx/OTC klikáním** v GUI — jde jen dotazem nebo přes API
- **Stránkování hledání** se dělá až v paměti
- Česká **stop-slovníková konfigurace** pro FTS — doměřeno, dopad malý
- **Váha fulltextu podle typu dotazu** (router typ zná přes `je_presny()`)

### 4. Rozhodnutí, která jsou na tobě

- **Generovat nové dvojice slovníku přes `gpt-5-nano`?** Levné a lepší
  čeština, ale naráží to na premisu „všechno lokálně". SPC jsou veřejné
  dokumenty SÚKL, takže riziko je malé — pokud se to tvrzení vedení
  říká, musí se upřesnit.
- **Embedovat odborný a laický tvar zvlášť?** Měřeno: laický opis ředí
  podobnost. Znamená přegenerovat embeddingy (~20 s běhu).

---

## Jak spustit

    uv run python priprav_infrastrukturu.py     # pgpass a bind-mounty
    docker compose up -d
    uv run python pipeline.py --stav            # kde jsme
    uv run uvicorn api:app --port 8000          # GUI + API
    uv run python hledej.py --nahrej            # CLI: předehřát PŘED ukázkou
    uv run python evaluate.py

**Po změně dat vždy v tomhle pořadí:**

    uv run python ocisti_json.py --zapis
    uv run python naplni_db.py --znovu          # --znovu POVINNĚ
    uv run python vytvor_embeddingy.py
    uv run python evaluate.py

## Co pohlídat

- **`naplni_db.py` bez `--znovu` data ZDVOJÍ.** Skript to nově odmítne,
  ale pořadí výš je bezpečnější.
- **Po změně schématu odpovědi restartovat API.** `--reload` po čase
  přestal zabírat a server běžel na starém kódu.
- **Poměr zdrojů sekcí je regresní test** (`extrahuj_sekce.py`).
- **Testovací případy OVĚŘOVAT proti datům, ne vymýšlet.**
- **Nepouštět běhy přes `tail`** — buffer schová průběh i chyby.
- **Přeextrahování chyby neopraví**, jen je přesune jinam.
- **Diakritika v konstantách** — předpony psané v ASCII tiše nefungují.
- **Popisek je součást odpovědi.** Třikrát dnes vypadala chyba tam, kde
  nebyla, protože text tvrdil něco jiného než data.
- **`num_ctx` nejít pod 16384** — Ollama delší prompt tiše usekne.
