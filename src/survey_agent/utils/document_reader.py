"""
document_reader.py — Read various document formats into plain text.

Supported formats:
  .pdf  — PyMuPDF (fitz)
  .md   — read as-is
  .txt  — read as-is
  .docx — python-docx (optional dependency)
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


async def read_document(path: str | Path) -> str:
    """
    Read a document file and return its plain-text content.

    Dispatches to the appropriate reader based on file extension.
    Raises RuntimeError if the format is unsupported or a required library is missing.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Document not found: {p}")

    ext = p.suffix.lower()
    readers = {
        ".pdf": _read_pdf,
        ".md": _read_text,
        ".txt": _read_text,
        ".docx": _read_docx,
        ".doc": _read_docx,
    }
    reader = readers.get(ext)
    if reader is None:
        raise RuntimeError(f"Unsupported document format: {ext}")
    return reader(p)


def _read_text(path: Path) -> str:
    """Read a plain-text or Markdown file."""
    return path.read_text(encoding="utf-8", errors="replace")


def _read_pdf(path: Path) -> str:
    """Extract text from a PDF using PyMuPDF."""
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("PyMuPDF is required for PDF reading: pip install pymupdf") from exc

    doc = fitz.open(str(path))
    pages: list[str] = []
    for i, page in enumerate(doc):
        text = page.get_text().strip()
        if text:
            pages.append(f"[Page {i + 1}]\n{text}")
    return "\n\n".join(pages)


def _read_docx(path: Path) -> str:
    """Extract text from a Word document using python-docx."""
    try:
        import docx
    except ImportError as exc:
        raise RuntimeError(
            "python-docx is required for DOCX reading: pip install python-docx"
        ) from exc

    doc = docx.Document(str(path))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n\n".join(paragraphs)
