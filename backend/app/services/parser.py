"""Document parsing.

Primary parser is Docling (layout-aware, keeps page numbers and section
headings). If Docling is unavailable or fails (corrupt/protected file, missing
models), we fall back to pypdf / python-docx so ingestion still completes.
Every failure is surfaced through the caller, never silently swallowed into
fake content.
"""

import logging
from typing import List, Optional

from app.services.chunking import ParsedBlock

logger = logging.getLogger(__name__)


class ParseError(Exception):
    pass


def _parse_with_docling(file_path: str) -> List[ParsedBlock]:
    from docling.document_converter import DocumentConverter

    converter = DocumentConverter()
    result = converter.convert(file_path)
    document = result.document

    blocks: List[ParsedBlock] = []
    section: Optional[str] = None

    for item, _level in document.iterate_items():
        text = getattr(item, "text", None)
        if not text or not str(text).strip():
            continue

        label = str(getattr(item, "label", "")).lower()
        page_number = None
        prov = getattr(item, "prov", None)
        if prov:
            page_number = getattr(prov[0], "page_no", None)

        if "section_header" in label or "title" in label:
            section = str(text).strip()[:200]

        blocks.append(ParsedBlock(text=str(text), page_number=page_number, section=section))

    if not blocks:
        raise ParseError("Docling no extrajo texto (¿PDF escaneado sin OCR?)")
    return blocks


def _parse_pdf_fallback(file_path: str) -> List[ParsedBlock]:
    import pypdf

    reader = pypdf.PdfReader(file_path)
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception as exc:  # pragma: no cover - depends on file
            raise ParseError(f"PDF protegido: {exc}") from exc

    blocks: List[ParsedBlock] = []
    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if text.strip():
            blocks.append(ParsedBlock(text=text, page_number=index))

    if not blocks:
        raise ParseError("El PDF no contiene texto extraíble (¿escaneado?)")
    return blocks


def _parse_docx_fallback(file_path: str) -> List[ParsedBlock]:
    import docx

    document = docx.Document(file_path)
    blocks: List[ParsedBlock] = []
    section: Optional[str] = None

    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue
        if paragraph.style is not None and "Heading" in (paragraph.style.name or ""):
            section = text[:200]
        blocks.append(ParsedBlock(text=text, section=section))

    if not blocks:
        raise ParseError("El DOCX no contiene texto")
    return blocks


def parse_document(file_path: str, parser: str = "docling") -> List[ParsedBlock]:
    """Return parsed blocks with page/section metadata."""
    lower = file_path.lower()

    if parser == "docling":
        try:
            return _parse_with_docling(file_path)
        except Exception as exc:  # fallback keeps ingestion alive
            logger.warning("Docling falló (%s); usando parser de respaldo: %s", type(exc).__name__, exc)

    if lower.endswith(".pdf"):
        return _parse_pdf_fallback(file_path)
    if lower.endswith(".docx"):
        return _parse_docx_fallback(file_path)

    raise ParseError(f"Formato no soportado: {file_path}")
