# Benchmarky – co je k dispozici

Jen benchmarky, které měří **dnešní** pipeline a hledání (stav 6. 10. 2026).
Starší (lokální qwen, gpt-5-nano, cloudové embeddingy, lokální Docling,
pymupdf4llm, audit hledání nad 32 léky) byly smazány – jejich závěry jsou
v `poznatky.md` a v tabulce slepých uliček v `CLAUDE.md`, skripty v gitu
do commitu `71c761c`.

**Pravidla:** nový benchmark patří do `benchmarky/<téma>/` a zapíše se do
tabulky níž i do `CLAUDE.md` (oddíl „Benchmarky"). Skripty do gitu ano,
vygenerované výstupy (`*.json`, `*.jsonl`, `vystupy/`) ne. Pouští se
z kořene projektu. Výsledek s čísly patří do `poznatky.md`.

| benchmark | na jakou otázku odpovídá | kdy pustit | co potřebuje | cena |
|---|---|---|---|---|
| `router/bench_router.py` | Který lokální model má dělat router: rychlost (medián, p90, tok/s), správnost na pravidlech (sekce, filtry, zápor, diakritika) a stabilita při opakování. | změna modelu routeru nebo promptu routeru | Ollama, Postgres | zdarma, minuty na model |
| `extrakce_cloud/bench_extrakce_luna.py` | Kolik bude stát extrakce celého korpusu v cloudu (`--tokeny`) a jak vypadá výstup na malém, středním a velkém SPC (`--beh`). | před každým hromadným cloudovým během; po změně promptu nebo modelu | `data/spc/`, pro `--beh` klíč OpenAI | `--tokeny` zdarma, `--beh` centy |
| `indikace_fragmenty/detektory.py` | Kolik položek indikací je podezřelých (kus věty, začíná předložkou, nesoulad s ATC). Bez modelu. | po přeextrahování indikací | Postgres | zdarma, sekundy |
| `indikace_fragmenty/soudce.py` | Kolik z podezřelých položek je opravdu chyba (skupina pacientů / kus věty) – soudí gemma nad celým textem 4.1. | když je potřeba skutečný podíl chyb, ne jen počet podezřelých | Ollama, Postgres, výstup `detektory.py` | zdarma, desítky minut |
| `indikace_fragmenty/test_promptu.py` | Je nový prompt indikací lepší než starý? Stejné sekce, stejný soudce. | před nasazením změny promptu indikací | Ollama, Postgres, klíč OpenAI | centy |

## Poznámky k jednotlivým

- **`router/bench_router.py`** – část B (end-to-end) bere parafráze podle ATC
  z `evaluate.py` (`PARAFRAZE_KORPUS`): trefa = v top 5 je lék ze správné
  skupiny. Po přesunu a téhle úpravě (6. 10.) jsem celý benchmark nepouštěl,
  jen `--help`.
- **`indikace_fragmenty/detektory.py`** předchozí `podezrele.jsonl` odloží
  jako `podezrele_<datum>.jsonl` a zapíše nový – srovnání „před / po" tak
  jde udělat kdykoli. Stav z 2. 10. (před promptem v2) se 6. 10. omylem
  přepsal; jeho čísla jsou v `poznatky.md` 4. 10. (6 427 → 5 944).

## Evaluace není benchmark

`evaluate.py` (kořen projektu) je regresní test hledání a pouští
se po **každé** změně promptu, modelu, vah nebo prahu – viz `CLAUDE.md`.
