"""Extrakce textu z PDF a chunking."""

import re
import hashlib
from pathlib import Path

import fitz  # PyMuPDF

from common.config import CHUNK_SIZE, CHUNK_OVERLAP


# ---------------------------------------------------------------------------
# Extrakce textu z PDF
# ---------------------------------------------------------------------------

def _clean_page_text(text: str) -> str:
    """Vyčistí text extrahovaný z PDF – ubere strukturální šum, který jen
    plýtvá místem a nenese sémantický obsah:

    - čísla stránek na vlastním řádku (např. "1/8")
    - osamocené číslo sekce na vlastním řádku (např. "4.1") se spojí
      s následujícím nadpisem na jeden řádek ("4.1 Terapeutické indikace")
    - vícenásobné prázdné/whitespace-only řádky (PyMuPDF je často extrahuje
      jako "\\n \\n", ne čisté "\\n\\n") se sjednotí na jeden oddělovač
    """
    text = re.sub(r"(?m)^\d+/\d+[ \t]*\n", "", text)
    text = re.sub(r"(?m)^(\d+(?:\.\d+)*\.?)[ \t]*\n(?!\s*\n)", r"\1 ", text)
    text = re.sub(r"\n[ \t]*(?:\n[ \t]*)+", "\n\n", text)
    return text.strip()


def extract_text_from_pdf(pdf_path: str | Path) -> list[dict]:
    """Vrátí seznam slovníků {"page": int, "text": str} pro každou stránku."""
    doc = fitz.open(str(pdf_path))
    pages = []
    for i, page in enumerate(doc):
        text = _clean_page_text(page.get_text("text"))
        if text:
            pages.append({"page": i + 1, "text": text})
    doc.close()
    return pages


def extract_full_text(pdf_path: str | Path) -> str:
    """Vrátí celý text z PDF jako jeden řetězec."""
    pages = extract_text_from_pdf(pdf_path)
    return "\n\n".join(p["text"] for p in pages)


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def _merge_short_chunks(chunks: list[str], min_chunk_size: int) -> list[str]:
    """Sloučí kusy kratší než min_chunk_size se sousedním (kdekoli v seznamu, ne jen na konci).

    Chunky ze stejného zdroje se navzájem nepřekrývají (na rozdíl od spans
    v chunk_text()), takže prosté spojení stringů je tu bezpečné.
    """
    if not chunks:
        return chunks
    merged = [chunks[0]]
    for c in chunks[1:]:
        if len(c) < min_chunk_size:
            merged[-1] = merged[-1] + " " + c
        else:
            merged.append(c)
    if len(merged) > 1 and len(merged[0]) < min_chunk_size:
        merged[1] = merged[0] + " " + merged[1]
        merged.pop(0)
    return merged


def chunk_text(
    text: str,
    *,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
    min_chunk_size: int = 100,
) -> list[str]:
    """Rozdělí text na chunky s překryvem, řez zarovnaný na konec slova.

    Poslední kus (zbytek textu) může vyjít velmi krátký (i jednotky znaků) –
    takové degenerované mini-chunky mají v embeddingu patologicky vysokou
    podobnost k téměř čemukoli ("hubness" problém u krátkého textu) a matou
    vyhledávání. Kratší než min_chunk_size se proto připojí k předchozímu kusu.
    """
    if not text:
        return []
    spans = []  # (start, end) páry – slicujeme až na konec, ať se překryv nezdvojí
    start = 0
    text_len = len(text)
    while start < text_len:
        end = start + chunk_size
        if end < text_len:
            # posun konce na nejbližší předchozí mezeru/nový řádek, ať neřežeme uprostřed slova
            boundary = max(text.rfind(" ", start, end), text.rfind("\n", start, end))
            if boundary > start:
                end = boundary
        else:
            end = text_len  # poslední kus – neřežeme za konec textu
        if text[start:end].strip():
            spans.append((start, end))
        if end >= text_len:
            break
        start = end - overlap

    # Poslední kus (zbytek textu) může vyjít velmi krátký (i jednotky znaků) –
    # takové degenerované mini-chunky mají v embeddingu patologicky vysokou
    # podobnost k téměř čemukoli ("hubness" problém u krátkého textu) a matou
    # vyhledávání. Kratší než min_chunk_size se proto připojí k předchozímu –
    # spojením přes koncový index (ne stringy), ať se overlap mezi kusy nezdvojí.
    if len(spans) > 1 and (spans[-1][1] - spans[-1][0]) < min_chunk_size:
        prev_start, _ = spans[-2]
        _, last_end = spans[-1]
        spans[-2] = (prev_start, last_end)
        spans.pop()

    return [text[s:e].strip() for s, e in spans if text[s:e].strip()]


def chunk_by_paragraphs(
    text: str,
    *,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
    min_chunk_size: int = 100,
) -> list[str]:
    """Rozdělí text na chunky po odstavcích – respektuje hranice odstavců.

    Prázdný řádek v PDF textu z PyMuPDF často obsahuje osamocenou mezeru
    (artefakt extrakce), proto se dělí na regex \\n\\s*\\n, ne na doslovné "\\n\\n".

    Odstavec delší než chunk_size (např. nepřerušená MedDRA tabulka nežádoucích
    účinků, klidně 800+ znaků bez prázdného řádku uvnitř) se dál rozseká přes
    chunk_text(), ať z něj nevznikne jeden obří nediferencovaný chunk.
    """
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks = []
    current = ""
    for para in paragraphs:
        if len(para) > chunk_size:
            if current:
                chunks.append(current.strip())
                current = ""
            chunks.extend(chunk_text(para, chunk_size=chunk_size, overlap=overlap, min_chunk_size=min_chunk_size))
            continue
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

    return _merge_short_chunks(chunks, min_chunk_size)


def chunk_pages(
    pages: list[dict],
    *,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
    method: str = "paragraphs",
    min_chunk_size: int = 100,
) -> list[dict]:
    """Chunkuje stránky a zachovává metadata (číslo stránky).

    method="paragraphs" (výchozí) respektuje hranice odstavců/podsekcí –
    lépe drží pohromadě krátké pojmenované podsekce (např. "Pacienti se
    sníženou funkcí jater"), které by čisté znakové dělení řezalo napůl.
    method="chars" je starší čistě znakové dělení (chunk_text).

    Chunky kratší než min_chunk_size, které chunk_by_paragraphs/chunk_text
    nemohly slít se sousedem (typicky titulní/dělicí stránka bez dalšího
    textu, např. "18 A. OZNAČENÍ NA OBALU"), se úplně zahodí – krátký text
    má v embeddingu patologicky vysokou podobnost k téměř čemukoli
    ("hubness" problém), bez ohledu na to, jestli je to smysluplná fráze
    nebo náhodný fragment. Nesou minimum informace, ztráta je zanedbatelná.

    Vrací: [{"chunk_index": int, "page": int, "text": str, "hash": str}, ...]
    """
    chunk_fn = chunk_by_paragraphs if method == "paragraphs" else chunk_text
    result = []
    idx = 0
    for page_info in pages:
        chunks = chunk_fn(page_info["text"], chunk_size=chunk_size, overlap=overlap)
        chunks = [c for c in chunks if len(c) >= min_chunk_size]
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
