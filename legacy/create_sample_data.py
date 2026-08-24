#!/usr/bin/env python3
"""Stahování SPC dokumentů z SÚKL API pro dema.

Stáhne reálné PDF příbalové letáky (SPC) z veřejného SÚKL API.
Vychází z https://github.com/tvio/ai4/blob/main/step2_sukl_api.py

Použití:
  uv run python create_sample_data.py                # stáhne výchozí sadu léků
  uv run python create_sample_data.py --count 10     # stáhne 10 léků
  uv run python create_sample_data.py --codes 0258021 0241858  # konkrétní kódy
"""

import sys
import time
import argparse
import logging
from pathlib import Path

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

DATA_DIR = Path("data")
PDF_DIR = DATA_DIR / "pdf"

SUKL_API_BASE = "https://prehledy.sukl.cz/dlp/v1"

# Známé kódy SÚKL – léky s kvalitními SPC dokumenty
BONUS_SUKL_CODES = [
    "0258021",  # Endiaron
    "0241858",
    "0087076",
    "0254048",
    "0254302",
    "0000876",
]

# Zajímavé ATC kategorie pro testování
INTERESTING_ATC_PREFIXES = [
    "N02",  # Analgetika (bolest)
    "M01",  # Antirevmatika, protizánětlivé
    "J01",  # Antibiotika
    "R06",  # Antihistaminika
    "A02",  # Léky při poruchách kyselosti
    "C09",  # ACE inhibitory, sartany
    "N05",  # Psycholeptika
    "R03",  # Léky při obstrukčních onemocněních
]


class SUKLClient:
    """Jednoduchý klient pro SÚKL API."""

    def __init__(self, base_url: str = SUKL_API_BASE):
        self.base_url = base_url
        self.session = requests.Session()

    def get_medicine_codes(self) -> list[str]:
        """Stáhne seznam všech kódů SÚKL."""
        url = f"{self.base_url}/lecive-pripravky?uvedeneCeny=false&typSeznamu=dlpo"
        logger.info("Stahuji seznam kódů léků z SÚKL API...")
        resp = self.session.get(url, timeout=30)
        resp.raise_for_status()
        codes = resp.json()
        logger.info(f"Načteno {len(codes)} kódů")
        return codes if isinstance(codes, list) else []

    def get_medicine_detail(self, kod_sukl: str) -> dict:
        """Stáhne detail léku."""
        url = f"{self.base_url}/lecive-pripravky/{kod_sukl}"
        resp = self.session.get(url, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def download_spc(self, kod_sukl: str, max_retries: int = 3) -> bytes:
        """Stáhne SPC PDF dokument. Vrátí prázdné bytes pokud není PDF."""
        url = f"{self.base_url}/dokumenty/{kod_sukl}/spc"
        for attempt in range(max_retries):
            try:
                resp = self.session.get(url, timeout=60)
                resp.raise_for_status()

                # Kontrola redirectu na EMA (vrací HTML místo PDF)
                if resp.url != url:
                    logger.info(f"  Redirect: {resp.url}")

                # Validace: skutečné PDF začíná na %PDF
                if not resp.content[:5].startswith(b"%PDF"):
                    content_type = resp.headers.get("content-type", "")
                    logger.warning(f"  Není PDF (content-type: {content_type}) – přeskakuji")
                    return b""

                return resp.content
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:
                    wait = (2 ** attempt) * 5
                    logger.warning(f"  429 Too Many Requests – čekám {wait}s")
                    time.sleep(wait)
                    continue
                raise
            except requests.RequestException:
                if attempt < max_retries - 1:
                    time.sleep(2)
                    continue
                return b""
        return b""


def download_medicines(count: int = 5, codes: list[str] | None = None) -> None:
    """Stáhne SPC PDF dokumenty ze SÚKL API."""
    PDF_DIR.mkdir(parents=True, exist_ok=True)

    client = SUKLClient()
    saved = 0
    processed = 0
    saved_names: set[str] = set()

    if codes:
        # Konkrétní kódy
        medicine_codes = codes
        logger.info(f"Zpracovávám {len(medicine_codes)} zadaných kódů")
    else:
        # Automatický výběr: bonus kódy + náhodný výběr ze seznamu
        all_codes = client.get_medicine_codes()
        # Bonus kódy na začátek, zbytek sestupně (novější léky)
        all_codes.sort(reverse=True)
        medicine_codes = BONUS_SUKL_CODES + all_codes
        logger.info(f"Celkem {len(medicine_codes)} kódů k procházení (cíl: {count})")

    for kod_sukl in medicine_codes:
        if saved >= count:
            break
        processed += 1

        try:
            # Detail léku
            detail = client.get_medicine_detail(kod_sukl)
            if not detail:
                continue

            nazev = detail.get("nazev", kod_sukl)
            atc = detail.get("ATCkod", "")

            # Filtr: jen zajímavé ATC kategorie (pokud nejsou zadané kódy ručně)
            if not codes and atc:
                if not any(atc.startswith(prefix) for prefix in INTERESTING_ATC_PREFIXES):
                    continue

            # Přeskočit duplicitní názvy
            if nazev in saved_names:
                continue

            # Přeskočit kontrastní látky
            nazev_lower = nazev.lower()
            if any(kw in nazev_lower for kw in ["iomeron", "omnipaque", "kontrast", "diagnostik"]):
                continue

            logger.info(f"[{saved+1}/{count}] {nazev} (kód: {kod_sukl}, ATC: {atc})")

            # Stažení SPC PDF
            pdf_content = client.download_spc(kod_sukl)
            if not pdf_content:
                logger.warning(f"  ⚠️  Prázdný SPC pro {kod_sukl} – přeskakuji")
                continue

            # Uložení
            safe_name = nazev.replace("/", "_").replace(" ", "_").replace(".", "")[:60]
            filename = f"SPC_{kod_sukl}_{safe_name}.pdf"
            filepath = PDF_DIR / filename
            filepath.write_bytes(pdf_content)

            size_kb = len(pdf_content) / 1024
            logger.info(f"  ✓ Uloženo: {filename} ({size_kb:.0f} KB)")

            saved += 1
            saved_names.add(nazev)
            time.sleep(0.5)

        except Exception as e:
            logger.error(f"  Chyba pro {kod_sukl}: {e}")
            continue

    # Souhrn
    print()
    print("=" * 60)
    print(f"📊 Staženo {saved} SPC dokumentů do {PDF_DIR}/")
    print("-" * 60)
    for f in sorted(PDF_DIR.glob("*.pdf")):
        size_kb = f.stat().st_size / 1024
        print(f"  📄 {f.name} ({size_kb:.0f} KB)")

    print(f"\n✅ Data připravena! Nyní můžete spustit:")
    print(f"  uv run python demo01_pdf_to_vectors.py {PDF_DIR}/<soubor>.pdf")
    print(f"  uv run python demo02_multi_pdf_vectors.py {PDF_DIR}/")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stahování SPC z SÚKL API")
    parser.add_argument("--count", type=int, default=5, help="Počet léků ke stažení (výchozí 5)")
    parser.add_argument("--codes", nargs="+", help="Konkrétní kódy SÚKL")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print("=" * 60)
    print("Stahování SPC dokumentů z SÚKL API")
    print("=" * 60)
    download_medicines(count=args.count, codes=args.codes)


if __name__ == "__main__":
    main()
