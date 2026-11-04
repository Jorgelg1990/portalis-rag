"""Chunking with document/page/section metadata.

Kept in a dedicated module so it is unit-testable without Celery, Docling or a
database. The worker only orchestrates: parse -> chunk -> embed -> persist.
"""

import re
from typing import Iterable, List, Optional, Tuple


class ParsedBlock:
    """A block of text extracted from the source document."""

    __slots__ = ("text", "page_number", "section")

    def __init__(self, text: str, page_number: Optional[int] = None, section: Optional[str] = None):
        self.text = text
        self.page_number = page_number
        self.section = section


def _normalise(text: str) -> str:
    return re.sub(r"[ \t]+", " ", text.replace("\r\n", "\n")).strip()


def chunk_blocks(
    blocks: Iterable[ParsedBlock],
    max_chars: int = 800,
    overlap_chars: int = 120,
) -> List[dict]:
    """Group blocks into chunks of at most ``max_chars`` characters.

    A chunk never spans two pages: page/section metadata must stay exact for
    citations. Oversized blocks are split with a small overlap so a sentence
    cut in half can still be retrieved.
    """
    chunks: List[dict] = []
    buffer: List[str] = []
    buffer_len = 0
    page: Optional[int] = None
    section: Optional[str] = None

    def flush() -> None:
        nonlocal buffer, buffer_len
        content = _normalise("\n\n".join(buffer))
        if content:
            chunks.append(
                {
                    "content": content,
                    "page_number": page,
                    "section": section,
                    "chunk_index": len(chunks),
                }
            )
        buffer = []
        buffer_len = 0

    for block in blocks:
        text = _normalise(block.text)
        if not text:
            continue

        new_page = block.page_number
        new_section = block.section or section

        if buffer and (new_page != page or buffer_len + len(text) > max_chars):
            flush()

        page = new_page
        section = new_section

        if len(text) <= max_chars:
            buffer.append(text)
            buffer_len += len(text)
            continue

        # Oversized block: split on sentence boundaries when possible.
        start = 0
        while start < len(text):
            end = min(start + max_chars, len(text))
            if end < len(text):
                cut = text.rfind(". ", start, end)
                if cut > start + max_chars // 2:
                    end = cut + 1
            piece = text[start:end].strip()
            if piece:
                chunks.append(
                    {
                        "content": piece,
                        "page_number": page,
                        "section": section,
                        "chunk_index": len(chunks),
                    }
                )
            if end >= len(text):
                break
            start = max(end - overlap_chars, start + 1)

    flush()
    return chunks


def chunk_pages(pages: Iterable[Tuple[Optional[int], str]], max_chars: int = 800) -> List[dict]:
    """Convenience wrapper for parsers that only yield (page_number, text)."""
    return chunk_blocks((ParsedBlock(text, page) for page, text in pages), max_chars=max_chars)
