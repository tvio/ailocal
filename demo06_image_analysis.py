#!/usr/bin/env python3
"""UC6 – Zpracování obrazu (vision).

Multimodální analýza obrázků přes lokální model s vision podporou.

Použití:
  uv run python demo06_image_analysis.py faktura.jpg
  uv run python demo06_image_analysis.py faktura.jpg --prompt "Jaká je celková částka?"
  uv run python demo06_image_analysis.py --categorize
"""

import sys
import argparse
from pathlib import Path

from common.config import MODEL_CHAT, IMAGES_DIR
from common.ollama_client import get_ollama_url, vision


SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff"}

# Předdefinované úlohy
TASKS = {
    "popis": "Popiš detailně, co vidíš na tomto obrázku. Odpovídej česky.",
    "faktura": (
        "Analyzuj tento obrázek faktury. Vytáhni tyto informace ve formátu JSON:\n"
        '- dodavatel (supplier)\n- odběratel (customer)\n- číslo faktury (invoice_number)\n'
        '- datum (date)\n- celková částka (total_amount)\n- měna (currency)\n'
        "Pokud některou informaci nelze přečíst, napiš null."
    ),
    "tabulka": (
        "Tento obrázek obsahuje tabulku. Převeď její obsah do formátu Markdown tabulky. "
        "Zachovej všechny řádky a sloupce. Odpovídej česky."
    ),
    "kategorie": (
        "Zařaď tento obrázek do jedné z kategorií: faktura, smlouva, leták, fotografie, diagram, jiné. "
        'Odpověz ve formátu JSON: {"kategorie": "...", "duvod": "...", "jazyk_dokumentu": "..."}'
    ),
    "ocr": "Přečti a přepiš VEŠKERÝ text z tohoto obrázku. Zachovej formátování. Odpovídej česky.",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="UC6 – Zpracování obrazu (vision)"
    )
    parser.add_argument("path", nargs="?", default=str(IMAGES_DIR), help="Název obrázku (hledá se v data/images/) nebo adresář")
    parser.add_argument("--prompt", help="Vlastní prompt (otázka k obrázku)")
    parser.add_argument("--task", choices=list(TASKS.keys()), default="popis", help="Předdefinovaná úloha")
    parser.add_argument("--categorize", action="store_true", help="Kategorizovat všechny obrázky v adresáři")
    parser.add_argument("--model", default=MODEL_CHAT, help=f"Model s vision (výchozí {MODEL_CHAT})")
    return parser.parse_args()


def analyze_image(image_path: Path, prompt: str, *, model: str, base_url: str) -> str:
    """Analyzuje jeden obrázek."""
    print(f"\n  🖼️  {image_path.name}")
    print(f"  📝 Prompt: {prompt[:80]}...")
    print(f"  ⏳ Zpracovávám...\n")
    result = vision(prompt, image_path, model=model, base_url=base_url)
    return result


def main() -> None:
    args = parse_args()
    path = Path(args.path)
    if not path.exists():
        path = IMAGES_DIR / args.path
    if not path.exists():
        print(f"Chyba: '{args.path}' nenalezen (ani v {IMAGES_DIR}/).", file=sys.stderr)
        sys.exit(1)

    print("=" * 60)
    print("UC6 – Zpracování obrazu (vision)")
    print("=" * 60)
    print(f"\n🤖 Model: {args.model}")

    base_url = get_ollama_url()
    print(f"  ✓ Ollama dostupná na {base_url}")

    # Určení promptu
    prompt = args.prompt if args.prompt else TASKS[args.task]

    if path.is_dir() or args.categorize:
        # Zpracování adresáře
        if not path.is_dir():
            print(f"Chyba: '{path}' není adresář.", file=sys.stderr)
            sys.exit(1)

        images = sorted(f for f in path.iterdir() if f.suffix.lower() in SUPPORTED_EXTENSIONS)
        if not images:
            print(f"Chyba: v '{path}' nejsou žádné obrázky.", file=sys.stderr)
            sys.exit(1)

        cat_prompt = TASKS["kategorie"]
        print(f"\n📂 Adresář: {path}")
        print(f"🖼️  Obrázků: {len(images)}")
        print("-" * 60)

        for img in images:
            result = analyze_image(
                img,
                cat_prompt if args.categorize else prompt,
                model=args.model,
                base_url=base_url,
            )
            print(result)
            print("-" * 40)

    elif path.is_file():
        # Zpracování jednoho obrázku
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            print(f"Chyba: '{path.suffix}' není podporovaný formát.", file=sys.stderr)
            print(f"Podporované: {', '.join(SUPPORTED_EXTENSIONS)}")
            sys.exit(1)

        result = analyze_image(path, prompt, model=args.model, base_url=base_url)
        print(result)
    else:
        print(f"Chyba: '{path}' neexistuje.", file=sys.stderr)
        sys.exit(1)

    print(f"\n{'='*60}")
    print("✅ Hotovo!")


if __name__ == "__main__":
    main()
