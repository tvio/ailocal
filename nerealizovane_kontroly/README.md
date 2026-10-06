# Nerealizované kontroly extrakce

Skripty kontrol a údržby dat, které vznikly nad **původním korpusem 32
léčiv** (`data/leciva/`) a **nad celým korpusem (`data/spc/`) neběží**.
Na jejich přepsání nezbyl čas. Leží tu jako předloha, ne jako součást
pipeline – seznam kroků pipeline je nevolá.

**Nespustitelné bez úprav:** čtou `data/leciva/` a importují `common/`
z kořene projektu (po přesunu sem by se musely pouštět z kořene jako
modul, nebo upravit cesty).

Co má být hotové a co chybí, je v `extrakce_kontroly.md`.

| skript | co dělá | stav |
|---|---|---|
| `zkontroluj_json.py` | **Kontrola 4a, bez modelu.** Každou extrahovanou položku hledá doslova ve zdrojovém textu sekce (po normalizaci). Mění **stav** sekce: `ok` / `zamitnuto_kontrolou`. | vypnuto od 29. 9. (`config.KONTROLY_ZAPNUTE`) |
| `zkontroluj_modelem.py` | **Kontrola 4b, jiným modelem** (gemma4:26b). Tam, kde doslovná shoda nestačí (indikace, kontraindikace, sporné případy). Mění **stav** sekce. | vypnuto od 29. 9. |
| `postav_slovnik.py` | **Číselník pojmů** odborný termín → laický tvar: posbírá dvojice ze VŠECH extrakcí do `slovnik_pojmu.json`, najde termíny s víc různými laickými tvary a volitelně ověří překlad modelem. Je to kontrola a sjednocení překladu, **pro běh pipeline potřeba není**. | generovaný slovník smazán 29. 9. (stavěl ho qwen, 42 % tvarů přepisovalo lepší výstup luny) |
| `ocisti_json.py` | **Znovu uplatní řízené číselníky na už vytěžená data**, bez modelu: frekvence → 6 hodnot, orgánový systém → MedDRA, laický tvar → podle číselníku pojmů. | u cloudové extrakce to samé dělá `common/extrakce.py` hned při zápisu JSON; skript by byl potřeba jen po změně číselníku, aby se nemuselo přeextrahovávat |

## Co z toho ŽIJE dál v pipeline

- `common/slovnik.py` + `slovnik_rucni.json` – ruční číselník pojmů se
  při extrakci uplatňuje pořád (položky s `laicky_ze_slovniku: true`).
- `common/meddra.py`, `extrakce.normalizuj_frekvenci()` – normalizace
  při zápisu JSON.

## Když se k tomu někdo vrátí

1. Přepsat vstup z `data/leciva/<kód>_<NÁZEV>/` na `data/spc/<identita>/`
   (stav po SPC × sekce je v `data/spc/_extrakce/stav.sqlite`).
2. Zařadit jako kroky do seznamu kroků pipeline za extrakci.
3. Nálezy N1–N5, N8 a regresní sada: `extrakce_kontroly.md`.
