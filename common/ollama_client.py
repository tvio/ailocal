"""Wrapper pro Ollama REST API – chat, embed, vision."""

import json
import base64
from pathlib import Path

import requests

from common.config import OLLAMA_TIMEOUT, MODEL_EMBED, MODEL_CHAT
from ollama_health import get_working_url


# ---------------------------------------------------------------------------
# Zjištění dostupné Ollama URL – delegováno na ollama_health.py
# ---------------------------------------------------------------------------

def get_ollama_url() -> str:
    """Vrátí první dostupnou Ollama base URL, nebo vyhodí výjimku."""
    url = get_working_url()
    if url is None:
        raise ConnectionError("Žádná Ollama není dostupná – viz ollama_health.py")
    return url


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------

def embed_text(text: str, *, model: str = MODEL_EMBED, base_url: str | None = None) -> list[float]:
    """Vrátí embedding vektor pro zadaný text."""
    url = base_url or get_ollama_url()
    resp = requests.post(
        f"{url}/api/embed",
        json={"model": model, "input": text},
        timeout=OLLAMA_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    # Ollama vrací {"embeddings": [[...]]}
    return data["embeddings"][0]


def embed_texts(texts: list[str], *, model: str = MODEL_EMBED, base_url: str | None = None) -> list[list[float]]:
    """Vrátí embedding vektory pro seznam textů (batch)."""
    url = base_url or get_ollama_url()
    resp = requests.post(
        f"{url}/api/embed",
        json={"model": model, "input": texts},
        timeout=OLLAMA_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["embeddings"]


# ---------------------------------------------------------------------------
# Chat (generování textu)
# ---------------------------------------------------------------------------

def chat(
    prompt: str,
    *,
    system: str = "",
    model: str = MODEL_CHAT,
    base_url: str | None = None,
    stream: bool = False,
    options: dict | None = None,
) -> str:
    """Pošle prompt modelu a vrátí odpověď jako string."""
    url = base_url or get_ollama_url()
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    default_options = {"num_ctx": 8192}
    if options:
        default_options.update(options)
    payload = {"model": model, "messages": messages, "stream": stream, "options": default_options}

    resp = requests.post(
        f"{url}/api/chat",
        json=payload,
        stream=stream,
        timeout=OLLAMA_TIMEOUT,
    )
    resp.raise_for_status()

    if not stream:
        return resp.json()["message"]["content"]

    # Streamovaná odpověď – sbíráme tokeny
    tokens = []
    for line in resp.iter_lines():
        if not line:
            continue
        chunk = json.loads(line)
        token = chunk.get("message", {}).get("content", "")
        if token:
            print(token, end="", flush=True)
            tokens.append(token)
    print()
    return "".join(tokens)


def chat_with_history(
    messages: list[dict],
    *,
    model: str = MODEL_CHAT,
    base_url: str | None = None,
    stream: bool = False,
) -> str:
    """Chat s plnou historií zpráv (pro pokročilé scénáře)."""
    url = base_url or get_ollama_url()
    resp = requests.post(
        f"{url}/api/chat",
        json={"model": model, "messages": messages, "stream": stream},
        stream=stream,
        timeout=OLLAMA_TIMEOUT,
    )
    resp.raise_for_status()

    if not stream:
        return resp.json()["message"]["content"]

    tokens = []
    for line in resp.iter_lines():
        if not line:
            continue
        chunk = json.loads(line)
        token = chunk.get("message", {}).get("content", "")
        if token:
            print(token, end="", flush=True)
            tokens.append(token)
    print()
    return "".join(tokens)


# ---------------------------------------------------------------------------
# Vision (multimodální – obrázky)
# ---------------------------------------------------------------------------

def vision(
    prompt: str,
    image_path: str | Path,
    *,
    model: str = MODEL_CHAT,
    base_url: str | None = None,
) -> str:
    """Pošle obrázek + prompt modelu s vision podporou."""
    url = base_url or get_ollama_url()
    image_bytes = Path(image_path).read_bytes()
    b64 = base64.b64encode(image_bytes).decode("utf-8")

    resp = requests.post(
        f"{url}/api/chat",
        json={
            "model": model,
            "messages": [
                {"role": "user", "content": prompt, "images": [b64]},
            ],
            "stream": False,
        },
        timeout=OLLAMA_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["message"]["content"]
