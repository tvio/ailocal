"""Extrakce textu z PDF a chunking."""

import hashlib
from pathlib import Path

import fitz  # PyMuPDF

from common.config import CHUNK_SIZE, CHUNK_OVERLAP


# ---------------------------------------------------------------------------
# Extrakce textu z PDF
# ---------------------------------------------------------------------------

def extract_text_from_pdf(pdf_path: str | Path) -> list[dict]:
    """Vrátí seznam slovníků {"page": int, "text": str} pro každou stránku."""
    doc = fitz.open(str(pdf_path))
    pages = []
    for i, page in enumerate(doc):
        text = page.get_text("text")
        if text.strip():
            pages.append({"page": i + 1, "text": text.strip()})
    doc.close()
    return pages


def extract_full_text(pdf_path: str | Path) -> str:
    """Vrátí celý text z PDF jako jeden řetězec."""
    pages = extract_text_from_pdf(pdf_path)
    return "\n\n".join(p["text"] for p in pages)


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def chunk_text(
    text: str,
    *,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list[str]:
    """Rozdělí text na chunky s překryvem. Jednoduchá strategie po znacích."""
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        chunks.append(chunk.strip())
        start = end - overlap
    return [c for c in chunks if c]


def chunk_by_paragraphs(
    text: str,
    *,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list[str]:
    """Rozdělí text na chunky po odstavcích – respektuje hranice odstavců."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) + 2 > chunk_size and current:
            chunks.append(current.strip())
            # Overlap: vezmeme konec předchozího chunku
            if overlap > 0 and len(current) > overlap:
                current = current[-overlap:] + "\n\n" + para
            else:
                current = para
        else:
            current = current + "\n\n" + para if current else para
    if current.strip():
        chunks.append(current.strip())
    return chunks


def chunk_pages(
    pages: list[dict],
    *,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list[dict]:
    """Chunkuje stránky a zachovává metadata (číslo stránky).

    Vrací: [{"chunk_index": int, "page": int, "text": str, "hash": str}, ...]
    """
    result = []
    idx = 0
    for page_info in pages:
        chunks = chunk_text(page_info["text"], chunk_size=chunk_size, overlap=overlap)
        for chunk in chunks:
            content_hash = hashlib.sha256(chunk.encode("utf-8")).hexdigest()[:16]
            result.append({
                "chunk_index": idx,
                "page": page_info["page"],
                "text": chunk,
                "hash": content_hash,
            })
            idx += 1
    return result
