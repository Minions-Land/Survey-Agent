"""
pdf_reference_extractor.py

Extract structured reference entries from a PDF file.

Pipeline:
  1. PyMuPDF reads the last N pages (reference section is always at the end)
  2. LLMProvider parses the raw text into structured RefEntry objects
  3. Fallback: regex heuristics when no LLM is available
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from survey_agent.interfaces.llm_provider import LLMProvider


@dataclass
class RefEntry:
    """A single parsed reference from a paper."""
    title: str = ""
    authors: str = ""
    year: int | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    raw: str = ""

    def has_locator(self) -> bool:
        """Return True if we have at least one identifier to search with."""
        return bool(self.doi or self.arxiv_id or self.title)


# ── Constants ──────────────────────────────────────────────────────────────────

_REF_SECTION_HEADERS = re.compile(
    r"^\s*(references|bibliography|works cited|literature cited)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_ARXIV_PAT = re.compile(r"arXiv[:\s]*([\d]{4}\.\d{4,5}(?:v\d+)?)", re.IGNORECASE)
_DOI_PAT = re.compile(r"\b(10\.\d{4,9}/[^\s,;>\]\"']+)")
_YEAR_PAT = re.compile(r"\b(19|20)\d{2}\b")

_LLM_PROMPT_TEMPLATE = """\
Below is the reference section of an academic paper. Extract every cited work as a JSON array.

Each element must have these fields:
  "title"    : string (full paper/book title, required)
  "authors"  : string (e.g. "Smith, J. and Lee, K." — best effort)
  "year"     : integer or null
  "doi"      : string or null (e.g. "10.1234/abc")
  "arxiv_id" : string or null (e.g. "2301.00001")

Return ONLY valid JSON — no explanation, no markdown fences.

REFERENCE SECTION:
{text}
"""


# ── Public API ─────────────────────────────────────────────────────────────────

async def extract_references(
    pdf_path: Path,
    llm_provider: "LLMProvider | None" = None,
    max_ref_pages: int = 8,
) -> list[RefEntry]:
    """
    Extract structured references from a PDF file.

    Args:
        pdf_path:      Path to the PDF file.
        llm_provider:  Optional LLM for semantic parsing (uses cheap_model).
                       Falls back to regex when None.
        max_ref_pages: Maximum number of trailing pages to scan for references.

    Returns:
        List of RefEntry objects, deduplicated by title.
    """
    text = _extract_reference_text(pdf_path, max_ref_pages)
    if not text.strip():
        return []

    if llm_provider is not None:
        refs = await _llm_parse(text, llm_provider)
    else:
        refs = _regex_parse(text)

    return _deduplicate(refs)


# ── Text extraction ────────────────────────────────────────────────────────────

def _extract_reference_text(pdf_path: Path, max_pages: int) -> str:
    """Extract text from the reference section (last N pages) of a PDF."""
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:
        raise RuntimeError("PyMuPDF (fitz) is required: pip install pymupdf") from exc

    doc = fitz.open(str(pdf_path))
    total = len(doc)
    start_page = max(0, total - max_pages)

    pages_text: list[str] = []
    for i in range(start_page, total):
        pages_text.append(doc[i].get_text())
    full_text = "\n".join(pages_text)

    # Try to trim to just the reference section
    match = _REF_SECTION_HEADERS.search(full_text)
    if match:
        full_text = full_text[match.start():]

    return full_text


# ── LLM parsing ───────────────────────────────────────────────────────────────

async def _llm_parse(text: str, llm_provider: "LLMProvider") -> list[RefEntry]:
    """Use LLM to parse references. Returns list of RefEntry."""
    import json

    # Truncate to stay within token budget (~12k chars ≈ 3k tokens)
    prompt = _LLM_PROMPT_TEMPLATE.format(text=text[:12_000])

    try:
        raw = await llm_provider.complete_cheap(prompt)
        # Strip any accidental markdown fences
        raw = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.MULTILINE)
        raw = re.sub(r"\s*```$", "", raw.strip(), flags=re.MULTILINE)
        data = json.loads(raw)
    except Exception:
        # LLM failed or returned invalid JSON — fall back to regex
        return _regex_parse(text)

    refs: list[RefEntry] = []
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict):
            continue
        refs.append(RefEntry(
            title=str(item.get("title") or "").strip(),
            authors=str(item.get("authors") or "").strip(),
            year=int(item["year"]) if item.get("year") else None,
            doi=str(item["doi"]).strip() if item.get("doi") else None,
            arxiv_id=_clean_arxiv(str(item["arxiv_id"])) if item.get("arxiv_id") else None,
            raw="",
        ))
    return refs


# ── Regex fallback ────────────────────────────────────────────────────────────

def _regex_parse(text: str) -> list[RefEntry]:
    """
    Heuristic regex parser for common reference formats.
    Handles numbered ([1], 1., [Smith2020]) and author-date styles.
    """
    # Split on common reference markers
    entries = re.split(
        r"\n\s*(?:\[\d+\]|\d+\.)\s+",
        text,
        flags=re.MULTILINE,
    )
    # Also try splitting on author-year markers like "\nSmith et al. (2020)"
    if len(entries) <= 2:
        entries = re.split(r"\n(?=[A-Z][a-z])", text)

    refs: list[RefEntry] = []
    for raw in entries:
        raw = raw.strip()
        if len(raw) < 20:
            continue
        ref = _parse_single_entry(raw)
        if ref.title:
            refs.append(ref)
    return refs


def _parse_single_entry(raw: str) -> RefEntry:
    """Parse a single reference string into a RefEntry."""
    raw_clean = re.sub(r"\s+", " ", raw)

    doi_match = _DOI_PAT.search(raw_clean)
    arxiv_match = _ARXIV_PAT.search(raw_clean)
    year_match = _YEAR_PAT.search(raw_clean)

    # Title heuristic: text inside quotes or after year, or first long phrase
    title = _extract_title(raw_clean)

    return RefEntry(
        title=title,
        authors=_extract_authors(raw_clean),
        year=int(year_match.group()) if year_match else None,
        doi=doi_match.group(1) if doi_match else None,
        arxiv_id=_clean_arxiv(arxiv_match.group(1)) if arxiv_match else None,
        raw=raw_clean,
    )


def _extract_title(text: str) -> str:
    """Best-effort title extraction from a reference string."""
    # Quoted title
    m = re.search(r'"([^"]{10,})"', text)
    if m:
        return m.group(1).strip()
    # "Title." pattern after author block
    m = re.search(r"\.\s+([A-Z][^.]{15,})\.", text)
    if m:
        return m.group(1).strip()
    # Fallback: first 120 chars
    return text[:120].strip()


def _extract_authors(text: str) -> str:
    """Extract author string (first 100 chars before year or title)."""
    m = re.match(r"^([A-Z][^.]{0,80})\.", text)
    if m:
        return m.group(1).strip()
    return ""


def _clean_arxiv(raw: str) -> str | None:
    """Normalise arXiv ID to plain YYMM.NNNNN format."""
    raw = raw.strip()
    m = re.search(r"(\d{4}\.\d{4,5}(?:v\d+)?)", raw)
    return m.group(1) if m else None


# ── Deduplication ─────────────────────────────────────────────────────────────

def _deduplicate(refs: list[RefEntry]) -> list[RefEntry]:
    """Remove duplicates by normalised title."""
    seen: set[str] = set()
    out: list[RefEntry] = []
    for ref in refs:
        key = re.sub(r"\W+", "", ref.title.lower())[:60]
        if key and key not in seen:
            seen.add(key)
            out.append(ref)
    return out
