# Benchmark PDF extrakce

Srovnání převodníků PDF → Markdown na **100 SPC** (32 z korpusu +
68 náhodných, jedno SPC na přípravek, 15 EU). Převádí se **celý
dokument** každým nástrojem — měří se převodník, ne hledání sekcí.

## Spuštění

```bash
uv run python benchmarky/pdfextrakce/bench_pdfextrakce.py vzorek     # výběr + stažení PDF
uv run python benchmarky/pdfextrakce/bench_pdfextrakce.py konverze   # navazuje na hotové
uv run python benchmarky/pdfextrakce/bench_pdfextrakce.py report     # metriky + HTML
```

## Varianty

| varianta | co to je |
|---|---|
| `docling` | reference, nastavená jako produkce (pypdfium2, bez OCR) |
| `p4l` | pymupdf4llm, **starý režim** (`use_layout(False)`) |
| `p4l_layout` | pymupdf4llm, **výchozí layout režim** |
| `marker` | Marker — na Windows potřebuje `llama-server` (llama.cpp), zatím neběží |

## Co kde je

| cesta | obsah |
|---|---|
| `vzorek.json` | seznam měřených SPC |
| `pdf/` | stažená SPC *(gitignore)* |
| `vystupy/<lék>/<varianta>.md` | markdown každé varianty *(gitignore)* |
| `report/index.html` | **přehled — začni tady** *(gitignore)* |
| `report/<lék>.html` | sekce 4.8 a 4.1 vedle sebe, chybějící vazby, odkaz na stranu v PDF |
| `vysledky.json` | všechna čísla |

## Jak číst metriky

- **vazby 4.8** — kolik buněk tabulky nežádoucích účinků z Doclingu je
  ve variantě jako přesná trojice *(text, sloupec, popisek řádku)*.
  Odhalí záměnu účinku mezi řádky „časté"/„vzácné" i zkrácenou buňku.
  Stará metrika (jen sloupec) tohle nepoznala — viz `poznatky.md` 24. 9.
- **formát 2** — totéž jen u tabulek, kde sloupce jsou frekvence.
- **podnadpisy 4.1+4.3** — nadpisy skupin („Děti") z Doclingu, které
  jsou ve variantě jako samostatný řádek (formát je jedno).
- **slepená slova** — slovo, které v Doclingu není, ale dá se rozdělit
  na dvě jeho slova („srdečníporuchy").

**Reference je Docling, ne pravda.** Kde se varianty liší, rozhoduje
PDF — detail léku odkazuje na stranu sekce.
