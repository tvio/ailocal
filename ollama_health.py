#!/usr/bin/env python3
"""Health check Ollama – zkusí po řadě URL (api/tags), vrátí první dostupnou nebo skončí s chybou."""

import sys
import requests

# Pořadí: nejdřív vzdálený, pak localhost
OLLAMA_CANDIDATES = [
    "http://127.0.0.1:11434",
    "http://192.168.1.215:11434",
  
]
HEALTH_PATH = "/api/tags"
TIMEOUT = 5


def is_available(base_url: str) -> bool:
    """Ověří, že Ollama na dané base_url odpovídá (GET /api/tags)."""
    try:
        r = requests.get(
            f"{base_url.rstrip('/')}{HEALTH_PATH}",
            timeout=TIMEOUT,
        )
        return r.status_code == 200
    except (requests.RequestException, OSError):
        return False


def get_working_url() -> str | None:
    """Vrátí první dostupnou base URL z OLLAMA_CANDIDATES, nebo None."""
    for base in OLLAMA_CANDIDATES:
        if is_available(base):
            return base.rstrip("/")
    return None


def main() -> None:
    url = get_working_url()
    if url is None:
        print("Chyba: žádná Ollama není dostupná (zkoušeno: " + ", ".join(OLLAMA_CANDIDATES) + ")", file=sys.stderr)
        sys.exit(1)
    print(url)


if __name__ == "__main__":
    main()
