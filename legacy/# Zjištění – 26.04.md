# Zjištění – 26.04.2025

## 1. Nevýhody malého embedding modelu
Malé modely (sentence-transformers, nomic-embed-text, 768 dim) zachycují základní sémantiku, ale nemají naučené doménové vztahy. Příklad: dotaz "lék na průjem" nenajde chunk s "loperamid", protože model tuto korelaci nezná. Velké modely a multilinguální modely mají tyto vztahy zakódované ve vyšším počtu dimenzí.

## 2. Embedding modelu musí být stejný pro dokumenty i dotazy
Není to jen o počtu dimenzí – každý model má vlastní souřadnicový prostor. Dva modely se stejnou dimenzí (např. oba 768) produkují vektory v jiných prostorech, cosine similarity mezi nimi je nesmysl. Změna embedding modelu = povinný re-embedding celé DB.

## 3. Velikost chunku zásadně ovlivňuje kvalitu vyhledávání
Chunk 500 znaků obsahuje 5–10 různých symptomů → embedding je průměr všech → dotaz "bolest břicha" nenajde chunk kde je to zmíněno spolu s dalšími 9 příznaky. Chunk 150 znaků = 1–2 koncepty → čistý embedding → výrazně lepší přesnost. Tradeoff: ~3× více chunků v DB.

## 4. Co je uloženo v chunku (embedding jako "komprimovaná znalost")
Embedding není jen text – je to vektor zachycující sémantické vztahy naučené z trénovacích dat. Velký model má v prostoru zakódováno: synonyma, doménové vztahy (symptom↔lék), vícejazyčné ekvivalenty. Malý model má jen povrchovou podobnost slov.

## 5. Omezení bge-m3 přes Ollama (F16)
bge-m3 v F16 kvantizaci produkuje NaN hodnoty pro specifické kombinace tokenů:
- opakující se tečky z PDF (TOC artefakty: `europa.eu. . . . . .`)
- specifické kombinace českých diakritik + číslo + kontext (`teplotě do 25 C`)
- příčina: overflow v BERT attention softmax při F16 precizi
- řešení: normalizace textu před embeddingem + skip NaN chunků (~2% ztráta)

## 7. Multilinguální vektory – stejná věta v CZ a EN nemá stejný vektor
Intuice "stejná věta v jiném jazyce = stejný vektor" je přibližně správná, ale ne přesná. Multilinguální model (bge-m3) umístí "bolest hlavy" a "headache" velmi blízko sebe (cosine similarity ~0.90+), ale ne na identické místo – jazyk nese kulturní kontext a register. Primárně anglický model (nomic-embed-text) má česká slova špatně reprezentovaná → "bolest hlavy" a "headache" budou daleko (similarity ~0.3). Proto při českých dokumentech záleží na multilinguálním modelu.

## 6. Nápad: porovnání lokálního bge-m3 vs. OpenAI text-embedding-3-large
Rozšíření demo01+demo05 o variantu s OpenAI embeddings – stejné PDF, stejné dotazy, porovnání:
- kvalita výsledků (relevance chunků)
- počet NaN / přeskočených chunků
- latence a cena
Zajímavé zejména pro české medicínské texty kde bge-m3 F16 selhává.
