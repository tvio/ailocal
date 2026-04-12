#!/usr/bin/env python3
"""UC3 – Extrakce konkrétní sekce z PDF.

Dva přístupy:
  1. Regex/strukturální – hledání nadpisů SPC a extrakce textu mezi nimi
  2. LLM-based – model dostane text a instrukci "Vytáhni pouze indikace"

Použití:
  # Všechny sekce do DB (výchozí chování):
  uv run python demo03_pdf_section_extract.py SPC_0254048_PARALEN.pdf

  # Jen jedna sekce:
  uv run python demo03_pdf_section_extract.py SPC_0254048_PARALEN.pdf --section kontraindikace

  # Jen regex (bez LLM) – rychlé:
  uv run python demo03_pdf_section_extract.py SPC_0254048_PARALEN.pdf --method regex

  # Jen LLM extrakce:
  uv run python demo03_pdf_section_extract.py SPC_0254048_PARALEN.pdf --method llm --section indikace

  # Bez ukládání do DB:
  uv run python demo03_pdf_section_extract.py SPC_0254048_PARALEN.pdf --no-save
"""

import re
import sys
import argparse
from pathlib import Path

from common.config import MODEL_CHAT, PDF_DIR
from common.ollama_client import get_ollama_url, chat, embed_text
from common.pdf_utils import extract_full_text
from common.db_postgres import get_connection, insert_extrakt, get_extrakty_stats


# SPC sekce – pevná struktura dle regulace (body 4.1–6.1)
SECTION_PATTERNS = {
    "indikace": [
        r"[Tt]erapeutick[áé]\s+indikace",
    ],
    "kontraindikace": [
        r"[Kk]ontraindikace",
    ],
    "davkovani": [
        r"[Dd]ávkování\s+a\s+způsob\s+podání",
    ],
    "vedlejsi_ucinky": [
        r"[Nn]ežádoucí\s+účinky",
    ],
    "interakce": [
        r"[Ii]nterakce\s+s\s+jinými\s+léčivými\s+přípravky",
    ],
    "slozeni": [
        r"[Kk]valitativní\s+a\s+kvantitativní\s+složení",
    ],
}

# Mapování klíčů na plné SPC názvy sekcí (pro LLM prompt)
SECTION_LABELS = {
    "indikace": "Terapeutické indikace (4.1)",
    "kontraindikace": "Kontraindikace (4.3)",
    "davkovani": "Dávkování a způsob podání (4.2)",
    "vedlejsi_ucinky": "Nežádoucí účinky (4.8)",
    "interakce": "Interakce s jinými léčivými přípravky (4.5)",
    "slozeni": "Kvalitativní a kvantitativní složení (2)",
}


def extract_section_regex(text: str, section: str) -> str | None:
    """Extrahuje sekci z textu pomocí regex hledání nadpisů.

    Hledá nadpis na začátku řádku, volitelně s číslem sekce (např. "4.8 Nežádoucí účinky").
    Vrací čistý text sekce (bez nadpisu, normalizovaný whitespace).
    """
    patterns = SECTION_PATTERNS.get(section.lower())
    if not patterns:
        patterns = [re.escape(section)]

    # Nadpis musí být na začátku řádku, volitelně s číslem sekce (4.1, 4.8, 2. atd.)
    # Tím se vyhneme matchování uprostřed věty ("různé nežádoucí účinky, včetně...")
    heading_prefix = r"^\s*(?:\d+(?:\.\d+)?\s+)?"

    # Najdi začátek sekce (konec nadpisu = match.end())
    match = None
    for pattern in patterns:
        full_pattern = heading_prefix + pattern
        match = re.search(full_pattern, text, re.IGNORECASE | re.MULTILINE)
        if match:
            break

    if match is None:
        return None

    # Začátek obsahu = za nadpisem
    remaining = text[match.end():]

    # Konec = další SPC nadpis (X.Y nebo X.) – ne holé číslo (tabulky, výčty)
    # Matchuje: "4.9 Předávkování", "5. FARMAKOLOGICKÉ", "4.10 Interakce"
    end_match = re.search(r"\n\s*\d+\.\d*\s+[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ]", remaining)
    if end_match:
        body = remaining[:end_match.start()]
    else:
        body = remaining

    # Normalizace: sjednotit whitespace na jednoduché mezery
    result = re.sub(r"\s+", " ", body).strip()
    return result if result else None


def extract_section_llm(text: str, section: str, *, model: str, base_url: str) -> str:
    """Extrahuje sekci z textu pomocí LLM.

    Nejdřív regex najde hrubý výřez sekce, pak LLM text vyčistí a přepíše.
    """
    # Regex najde hrubý obsah sekce (stejná logika jako extract_section_regex)
    raw_section = extract_section_regex(text, section)
    if not raw_section:
        return "NENALEZENO"

    label = SECTION_LABELS.get(section.lower(), section)

    system = "Přepiš odborný text SPC dokumentu čistě a přesně. Nic nepřidávej, nic nevynechej."

    prompt = f"""Následující text je sekce „{label}" z SPC dokumentu.
Přepiš ho čistě jako souvislý text. Zachovej veškerý obsah.

{raw_section}"""

    return chat(prompt, system=system, model=model, base_url=base_url)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="UC3 – Extrakce konkrétní sekce z PDF"
    )
    parser.add_argument("pdf", help="Název PDF souboru (hledá se v data/pdf/)")
    parser.add_argument("--section", default=None, help="Jen konkrétní sekce (výchozí: všechny)")
    parser.add_argument("--method", choices=["regex", "llm", "both"], default="both", help="Metoda extrakce (výchozí: both)")
    parser.add_argument("--model", default=MODEL_CHAT, help=f"Model pro LLM extrakci (výchozí {MODEL_CHAT})")
    parser.add_argument("--no-save", action="store_true", help="Neukládat do DB (výchozí: ukládá)")
    return parser.parse_args()


def _save_extrakt(
    text: str, section: str, typ_extraktu: str,
    *, document_name: str, base_url: str,
) -> None:
    """Uloží extrakt do DB s embeddingem."""
    embed_input = text[:6000] if len(text) > 6000 else text
    vec = embed_text(embed_input, base_url=base_url)
    conn = get_connection()
    insert_extrakt(
        conn,
        document_name=document_name,
        typ_sekce=section,
        typ_extraktu=typ_extraktu,
        sekce_text=text,
        sekce_vector=vec,
    )
    conn.close()
    print(f"  💾 [{section}/{typ_extraktu}] Uloženo do DB ({len(vec)} dim)")


def extract_and_save(
    full_text: str,
    section: str,
    *,
    document_name: str,
    method: str,
    model: str,
    base_url: str,
    save: bool,
) -> dict[str, str]:
    """Extrahuje sekci, volitelně uloží do DB. Vrátí dict {typ_extraktu: text}."""
    results = {}

    # Regex
    if method in ("regex", "both"):
        regex_result = extract_section_regex(full_text, section)
        if regex_result:
            print(f"  ✓ [{section}] Regex: {len(regex_result)} znaků")
            results["regex"] = regex_result
            if save:
                _save_extrakt(regex_result, section, "regex",
                              document_name=document_name, base_url=base_url)
        else:
            print(f"  ✗ [{section}] Regex: nenalezeno")

    # LLM
    if method in ("llm", "both"):
        llm_result = extract_section_llm(
            full_text, section, model=model, base_url=base_url,
        )
        # Validace: odmítnout prázdné, krátké a odmítavé odpovědi
        refusal_markers = ["nenalezeno", "chybí", "nemám", "nemohu", "omlouvám", "nemůžu"]
        is_refusal = any(m in llm_result.lower() for m in refusal_markers) if llm_result else True
        if llm_result and len(llm_result.strip()) > 20 and not is_refusal:
            print(f"  ✓ [{section}] LLM:   {len(llm_result)} znaků")
            results["llm"] = llm_result
            if save:
                _save_extrakt(llm_result, section, "llm",
                              document_name=document_name, base_url=base_url)
        else:
            reason = "odmítnutí" if is_refusal else "příliš krátká odpověď"
            print(f"  ✗ [{section}] LLM:   {reason}")

    return results


def main() -> None:
    args = parse_args()
    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        pdf_path = PDF_DIR / args.pdf
    if not pdf_path.exists():
        print(f"Chyba: soubor '{args.pdf}' nenalezen (ani v {PDF_DIR}/).", file=sys.stderr)
        sys.exit(1)

    document_name = pdf_path.stem
    save = not args.no_save
    sections_to_extract = [args.section] if args.section else list(SECTION_PATTERNS.keys())

    print("=" * 60)
    print("UC3 – Extrakce konkrétní sekce z PDF")
    print("=" * 60)
    print(f"\n📄 Soubor:  {pdf_path}")
    print(f"🔍 Sekce:   {', '.join(sections_to_extract)}")
    print(f"⚙️  Metoda:  {args.method}")
    print(f"💾 DB:      {'ano' if save else 'ne'}")

    # Extrakce celého textu
    print("\nExtrahuji text z PDF...")
    full_text = extract_full_text(pdf_path)
    print(f"  ✓ {len(full_text):,} znaků extrahováno")

    base_url = get_ollama_url()
    print(f"  ✓ Ollama: {base_url}")

    # Extrakce sekcí
    print(f"\n{'='*60}")
    extracted = {}  # {section: {typ_extraktu: text}}
    for section in sections_to_extract:
        results = extract_and_save(
            full_text, section,
            document_name=document_name,
            method=args.method,
            model=args.model,
            base_url=base_url,
            save=save,
        )
        if results:
            extracted[section] = results
        print()

    # Souhrn
    print("=" * 60)
    print(f"📊 Extrahováno {len(extracted)}/{len(sections_to_extract)} sekcí")
    for sec, variants in extracted.items():
        for typ, text in variants.items():
            print(f"  • {sec}/{typ}: {len(text)} znaků")

    if save:
        conn = get_connection()
        stats = get_extrakty_stats(conn)
        conn.close()
        print(f"\n💾 Extrakty v DB: {len(stats)} záznamů")
        for s in stats:
            print(f"  • {s['document_name']} / {s['typ_sekce']} / {s['typ_extraktu']}: {s['sekce_len']} znaků")

    print(f"\n✅ Hotovo!")


if __name__ == "__main__":
    main()
