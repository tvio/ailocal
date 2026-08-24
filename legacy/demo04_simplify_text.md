# UC4 – Strukturované zjednodušení sekcí SPC dokumentu

Převede odborný farmaceutický text z tabulky `extrakty_json` na strukturovaný JSON srozumitelný pro laika. Výstup se ukládá do tabulky `simplify`.

## Pipeline

```
extrakty_json (JSONB)
    │  sekce_json: { text_content, has_table, tables[{headers, rows}] }
    │
    ▼
LLM (OpenAI nebo Ollama)
    │  vstup: celý sekce_json jako JSON (ne text!)
    │  per-section prompt + JSON schema
    │
    ▼
simplify (PostgreSQL)
    ├── source_json     JSONB  ← kopie sekce_json pro porovnání
    └── simplified_json JSONB  ← zjednodušený výstup
```

Klíčový princip: LLM dostane přímo strukturovaný JSONB (včetně rozpadlých tabulek v `tables[].rows`), nikoliv zpětně převedený text. Tím se zachová přesnost tabulkových dat – zejména u sekcí `vedlejsi_ucinky` a `davkovani`, kde jsou tabulky nosičem informace.

## Výstupní schémata per sekce

| Sekce | Klíč | Typ položky |
|---|---|---|
| `slozeni` | `ucinne_latky` | `["paracetamol 500 mg"]` |
| `indikace` | `indikace` | `["horečka při infekcích"]` |
| `kontraindikace` | `kontraindikace` | `["těžké selhání jater"]` |
| `davkovani` | `davkovani` | `[{pacient, davka, frekvence, poznamka}]` |
| `vedlejsi_ucinky` | `vedlejsi_ucinky` | `[{frekvence, ucinek}]` |
| `interakce` | `interakce` | `[{latka, efekt}]` |

Schémata jsou vynucena přes OpenAI `response_format` (strict JSON schema) nebo Ollama JSON mode.

## Databázová struktura

### Zdroj: `extrakty_json`

```sql
SELECT document_name, typ_sekce, typ_modelu, sekce_json
FROM extrakty_json
WHERE document_name = 'SPC_0254048_PARALEN';
```

Sloupec `sekce_json` obsahuje:

```json
{
  "section_id": "4.8",
  "section_name": "Nežádoucí účinky",
  "has_table": true,
  "text_content": "Popis vybraných nežádoucích účinků...",
  "tables": [
    {
      "title": "Frekvence nežádoucích účinků",
      "headers": ["Orgánový systém", "Velmi časté", "Časté", "Vzácné"],
      "rows": [
        ["Poruchy krve", "", "", "trombocytopenie"]
      ]
    }
  ]
}
```

### Cíl: `simplify`

```sql
SELECT typ_sekce, typ_modelu, zdroj_modelu, source_json, simplified_json
FROM simplify
WHERE document_name = 'SPC_0254048_PARALEN'
ORDER BY typ_sekce, typ_modelu;
```

| Sloupec | Typ | Popis |
|---|---|---|
| `source_json` | JSONB | Původní `sekce_json` z `extrakty_json` – pro přímé porovnání kvality |
| `simplified_json` | JSONB | Zjednodušený výstup dle per-section schématu |
| `typ_modelu` | TEXT | Model který zjednodušoval: `openai(gpt-5.4-nano)`, `ollama(gemma3:12b)` |
| `zdroj_modelu` | TEXT | Model který extrahoval zdrojový JSON: `openai(gpt-5.4-nano)` |

Oba JSONB sloupce vedle sebe umožňují v pgAdmin nebo SQL okamžitě vidět, jak model kvalitně zjednodušil a kategorizoval sekci oproti originálu.

## Použití

```bash
# Všechny sekce, oba režimy (výchozí)
uv run python demo04_simplify_text.py SPC_0254048_PARALEN

# Jen OpenAI
uv run python demo04_simplify_text.py SPC_0254048_PARALEN --mode openai

# Jen lokální model
uv run python demo04_simplify_text.py SPC_0254048_PARALEN --mode local

# Jen jedna sekce
uv run python demo04_simplify_text.py SPC_0254048_PARALEN --section vedlejsi_ucinky

# Bez uložení do DB (preview)
uv run python demo04_simplify_text.py SPC_0254048_PARALEN --no-save

# PDF jako vstup (odstraní .pdf příponu automaticky)
uv run python demo04_simplify_text.py SPC_0254048_PARALEN.pdf --mode openai
```

## Auto-fallback

Pokud pro daný dokument chybí záznamy v `extrakty_json`, demo04 automaticky spustí `demo03d_json_extract.py --mode openai` a po úspěšné extrakci pokračuje se zjednodušením. PDF musí existovat v `data/pdf/`.

```
demo04 spuštěn
    │
    ├── extrakty_json má data? → ano → pokračuj
    │
    └── ne → spusť demo03d (OpenAI extrakce)
                │
                ├── PDF existuje? → ano → extrahuj + pokračuj
                └── ne → chyba, exit
```

## Modely a kvalita

### OpenAI `gpt-5.4-nano`
- Výstup vynucen přes `response_format` se strict JSON schema → vždy validní struktura
- Přesný překlad odborných termínů do laického jazyka (trombocytopenie → nízké krevní destičky)
- Projde tabulkové řádky kompletně, zachová vazby frekvence–účinek

### Ollama `gemma3:12b` (kvantizovaný)
- JSON mode přes Ollama API – měkčí než strict schema, občas odchylky ve struktuře
- Odborné termíny občas ponechá nepřeložené
- U komplexních tabulek (vedlejsi_ucinky, davkovani) může přeskočit řádky nebo sloučit kategorie
- Vhodné pro offline provoz bez API klíče; pro produkci doporučit větší model (27b+)

## Závislosti

| Krok | Script | Tabulka |
|---|---|---|
| 1. Extrakce PDF do JSON | `demo03d_json_extract.py` | → `extrakty_json` |
| 2. Zjednodušení | `demo04_simplify_text.py` | `extrakty_json` → `simplify` |
