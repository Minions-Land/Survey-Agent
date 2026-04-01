"""
utils/paper_storage.py - Local PDF paper storage manager

Features:
1. Manage data/papers/ directory structure (unclassified/ + classified/<category>/)
2. Registry (.registry.json) tracks metadata and read pages for each PDF
3. PDFs are read on demand; read page numbers are recorded to avoid re-reading
4. Automatically detects new PDFs in the unclassified/ directory
5. Reads companion .bib files, or looks up/generates BibTeX via Semantic Scholar

Directory structure:
    data/papers/
    ├── .registry.json          ← Paper metadata + read state registry
    ├── unclassified/           ← PDFs manually placed by author for classification
    │   ├── paper1.pdf
    │   ├── paper1.bib          ← Companion BibTeX (optional)
    │   └── ...
    └── classified/
        ├── cat_01_attention/   ← Classified papers (category_id_name)
        │   └── paper2.pdf
        └── ...

Note: Requires pymupdf (pip install pymupdf) to read PDF text.
      Without it, only metadata management is available, not content extraction.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Data structures
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class PaperRecord:
    """
    Registry record for a local PDF paper.

    Each record corresponds to one PDF file and tracks its state.
    """
    paper_id: str           # Unique ID (file hash or Semantic Scholar ID)
    filename: str           # Original filename
    relative_path: str      # Path relative to papers_root
    title: str = ""
    authors: list[str] = field(default_factory=list)
    year: int = 0
    cite_key: str = ""
    bib_entry: str = ""     # Complete BibTeX entry string
    category_id: str | None = None  # Category ID assigned to (None = unclassified)
    total_pages: int = 0
    pages_read: list[int] = field(default_factory=list)  # Read page numbers (1-indexed)
    extraction_done: bool = False  # Whether information extraction is complete
    s2_paper_id: str = ""   # Semantic Scholar Paper ID (if found)

    def unread_pages(self, max_page: int | None = None) -> list[int]:
        """Return list of unread page numbers."""
        if self.total_pages == 0:
            return []
        end = min(max_page or self.total_pages, self.total_pages)
        read_set = set(self.pages_read)
        return [p for p in range(1, end + 1) if p not in read_set]

    def is_fully_read(self) -> bool:
        """Whether all pages have been read."""
        return self.total_pages > 0 and len(self.pages_read) >= self.total_pages


# ──────────────────────────────────────────────────────────────────────────────
# Main class
# ──────────────────────────────────────────────────────────────────────────────

class PaperStorage:
    """
    Local PDF paper storage manager.

    Provides full lifecycle management of the data/papers/ directory:
    creating directories, registering new PDFs, reading specific pages,
    updating classification, generating BibTeX.
    """

    def __init__(self, root: str | Path = "data/papers") -> None:
        self.root = Path(root)
        self.unclassified_dir = self.root / "unclassified"
        self.classified_dir = self.root / "classified"
        self._registry_path = self.root / ".registry.json"
        self._registry: dict[str, PaperRecord] = {}
        self._ensure_dirs()
        self._load_registry()

    # ── Directory initialization ───────────────────────────────────────────────

    def _ensure_dirs(self) -> None:
        """Ensure required directories exist."""
        self.root.mkdir(parents=True, exist_ok=True)
        self.unclassified_dir.mkdir(exist_ok=True)
        self.classified_dir.mkdir(exist_ok=True)

    # ── Registry I/O ──────────────────────────────────────────────────────────

    def _load_registry(self) -> None:
        """Load registry from disk."""
        if self._registry_path.exists():
            try:
                data = json.loads(self._registry_path.read_text(encoding="utf-8"))
                self._registry = {
                    pid: PaperRecord(**record)
                    for pid, record in data.items()
                }
                logger.debug(f"Loaded {len(self._registry)} paper records")
            except Exception as e:
                logger.warning(f"Registry load failed: {e}, using empty registry")
                self._registry = {}

    def _save_registry(self) -> None:
        """Write registry to disk."""
        data = {pid: asdict(record) for pid, record in self._registry.items()}
        self._registry_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ── Scan unclassified PDFs ─────────────────────────────────────────────────

    def scan_unclassified(self) -> list[PaperRecord]:
        """
        Scan the unclassified/ directory and register any unregistered PDFs.

        Also attempts to read companion .bib files.
        Returns a list of all newly discovered PaperRecords.
        """
        new_records: list[PaperRecord] = []

        for pdf_path in sorted(self.unclassified_dir.glob("*.pdf")):
            paper_id = _file_hash(pdf_path)
            if paper_id in self._registry:
                continue  # Already registered, skip

            logger.info(f"New PDF found: {pdf_path.name}")

            # Read companion .bib file (if exists)
            bib_path = pdf_path.with_suffix(".bib")
            bib_entry = ""
            cite_key = ""
            title = ""
            authors: list[str] = []
            year = 0

            if bib_path.exists():
                bib_entry = bib_path.read_text(encoding="utf-8", errors="replace")
                cite_key, title, authors, year = _parse_bib_entry(bib_entry)
                logger.info(f"  Found companion .bib: {cite_key}")

            # Count PDF pages
            total_pages = _count_pdf_pages(pdf_path)

            record = PaperRecord(
                paper_id=paper_id,
                filename=pdf_path.name,
                relative_path=str(pdf_path.relative_to(self.root)),
                title=title or pdf_path.stem,
                authors=authors,
                year=year,
                cite_key=cite_key or _slugify(pdf_path.stem),
                bib_entry=bib_entry,
                total_pages=total_pages,
            )
            self._registry[paper_id] = record
            new_records.append(record)

        if new_records:
            self._save_registry()

        return new_records

    # ── Read PDF content (by page, no re-reads) ───────────────────────────────

    def read_pages(
        self,
        paper_id: str,
        pages: list[int] | None = None,
        max_chars_per_page: int = 3000,
    ) -> dict[int, str]:
        """
        Read text content from specified PDF pages and record read page numbers.

        Args:
            paper_id: Paper registry ID
            pages: List of page numbers to read (None = read all unread pages)
            max_chars_per_page: Maximum characters to extract per page

        Returns:
            {page_number: page_text} dict (only contains pages not yet read)

        Note: Already-read pages will not be returned again; use force_reread=True to re-read
        """
        record = self._registry.get(paper_id)
        if not record:
            raise KeyError(f"Unknown paper_id: {paper_id}")

        pdf_path = self.root / record.relative_path
        if not pdf_path.exists():
            logger.warning(f"PDF file not found: {pdf_path}")
            return {}

        # Determine pages to read
        if pages is None:
            target_pages = record.unread_pages()
        else:
            read_set = set(record.pages_read)
            target_pages = [p for p in pages if p not in read_set]

        if not target_pages:
            logger.debug(f"{paper_id}: all target pages already read")
            return {}

        # Read PDF text
        result = _extract_pdf_pages(pdf_path, target_pages, max_chars_per_page)

        # Update read records
        record.pages_read = sorted(set(record.pages_read) | set(result.keys()))
        self._save_registry()

        logger.debug(f"{paper_id}: read {len(result)} pages, cumulative {len(record.pages_read)}/{record.total_pages}")
        return result

    def read_abstract_pages(self, paper_id: str) -> str:
        """
        Read the first 3 pages of the PDF (usually contains abstract and introduction),
        used for initial extraction. Returns merged text content.
        """
        pages = self.read_pages(paper_id, pages=[1, 2, 3])
        return "\n\n".join(
            f"[Page {p}]\n{text}" for p, text in sorted(pages.items())
        )

    def read_full_paper(self, paper_id: str) -> str:
        """Read the full PDF (all unread pages)."""
        pages = self.read_pages(paper_id)
        return "\n\n".join(
            f"[Page {p}]\n{text}" for p, text in sorted(pages.items())
        )

    # ── Classification management ──────────────────────────────────────────────

    def classify_paper(
        self,
        paper_id: str,
        category_id: str,
        category_name: str,
    ) -> None:
        """
        Move paper from unclassified to the corresponding category directory.

        On classification change, moves the file (and companion .bib) directly;
        no need to re-read the PDF.

        Args:
            paper_id: Paper registry ID
            category_id: Category ID (e.g. cat_01)
            category_name: Category name (used to create a friendly directory name)
        """
        record = self._registry.get(paper_id)
        if not record:
            raise KeyError(f"Unknown paper_id: {paper_id}")

        old_path = self.root / record.relative_path
        if not old_path.exists():
            logger.warning(f"Source file not found, updating record only: {old_path}")
        else:
            # Create target directory
            safe_name = _slugify(category_name)[:40]
            target_dir = self.classified_dir / f"{category_id}_{safe_name}"
            target_dir.mkdir(parents=True, exist_ok=True)

            # Move PDF
            new_path = target_dir / old_path.name
            old_path.rename(new_path)

            # Move companion .bib (if exists)
            old_bib = old_path.with_suffix(".bib")
            if old_bib.exists():
                old_bib.rename(new_path.with_suffix(".bib"))

            record.relative_path = str(new_path.relative_to(self.root))
            logger.info(f"Paper {record.cite_key} classified to {category_id}")

        record.category_id = category_id
        self._save_registry()

    def reclassify_paper(
        self,
        paper_id: str,
        new_category_id: str,
        new_category_name: str,
    ) -> None:
        """
        Change paper's classification (moves file and updates registry only, no PDF re-read).
        """
        self.classify_paper(paper_id, new_category_id, new_category_name)

    # ── BibTeX management ──────────────────────────────────────────────────────

    def update_bib_entry(self, paper_id: str, bib_entry: str) -> None:
        """Update paper's BibTeX entry (used after Semantic Scholar lookup)."""
        record = self._registry.get(paper_id)
        if record:
            record.bib_entry = bib_entry
            cite_key, title, authors, year = _parse_bib_entry(bib_entry)
            if cite_key:
                record.cite_key = cite_key
            if title:
                record.title = title
            if authors:
                record.authors = authors
            if year:
                record.year = year
            self._save_registry()

    def generate_basic_bib(self, paper_id: str) -> str:
        """
        Generate a basic BibTeX entry for papers without BibTeX.
        (Contains only known fields, low quality; recommend completing via Semantic Scholar)
        """
        record = self._registry.get(paper_id)
        if not record:
            return ""
        first_author = record.authors[0].split()[-1].lower() if record.authors else "unknown"
        cite_key = f"{first_author}{record.year}{_slugify(record.title.split()[0])}" if record.title else record.paper_id[:8]
        return (
            f"@article{{{cite_key},\n"
            f"  title = {{{record.title}}},\n"
            f"  author = {{{' and '.join(record.authors)}}},\n"
            f"  year = {{{record.year}}},\n"
            f"}}\n"
        )

    # ── Query interface ────────────────────────────────────────────────────────

    def get_unclassified(self) -> list[PaperRecord]:
        """Return all unclassified paper records."""
        return [r for r in self._registry.values() if r.category_id is None]

    def get_by_category(self, category_id: str) -> list[PaperRecord]:
        """Return all papers in the specified category."""
        return [r for r in self._registry.values() if r.category_id == category_id]

    def get_all(self) -> list[PaperRecord]:
        """Return all registered paper records."""
        return list(self._registry.values())

    def get(self, paper_id: str) -> PaperRecord | None:
        """Find a paper record by paper_id."""
        return self._registry.get(paper_id)


# ──────────────────────────────────────────────────────────────────────────────
# Helper functions
# ──────────────────────────────────────────────────────────────────────────────

def _file_hash(path: Path) -> str:
    """Compute first 16 characters of SHA256 as file ID."""
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha.update(chunk)
    return sha.hexdigest()[:16]


def _count_pdf_pages(path: Path) -> int:
    """Count total PDF pages (requires pymupdf)."""
    try:
        import fitz  # PyMuPDF
        with fitz.open(str(path)) as doc:
            return len(doc)
    except ImportError:
        logger.debug("pymupdf not installed, cannot count pages")
        return 0
    except Exception as e:
        logger.warning(f"Failed to count pages for {path.name}: {e}")
        return 0


def _extract_pdf_pages(
    path: Path,
    pages: list[int],
    max_chars: int,
) -> dict[int, str]:
    """
    Extract text from specified PDF pages (requires pymupdf).

    Args:
        path: PDF file path
        pages: List of page numbers to extract (1-indexed)
        max_chars: Maximum characters per page

    Returns:
        {page_number: text} dict
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        logger.warning("pymupdf not installed. Run: pip install pymupdf")
        return {}

    result: dict[int, str] = {}
    try:
        with fitz.open(str(path)) as doc:
            total = len(doc)
            for page_num in pages:
                if page_num < 1 or page_num > total:
                    continue
                page = doc[page_num - 1]  # fitz uses 0-indexed
                text = page.get_text()[:max_chars]
                if text.strip():
                    result[page_num] = text
    except Exception as e:
        logger.warning(f"Failed to extract pages from {path.name}: {e}")

    return result


def _parse_bib_entry(bib_text: str) -> tuple[str, str, list[str], int]:
    """
    Extract cite_key, title, authors, year from a BibTeX string.

    Returns:
        (cite_key, title, authors, year)
    """
    cite_key = ""
    title = ""
    authors: list[str] = []
    year = 0

    # Extract cite key: @article{vaswani2017attention,
    m = re.search(r"@\w+\{([^,\s]+),", bib_text)
    if m:
        cite_key = m.group(1)

    # Extract title
    m = re.search(r'title\s*=\s*[{"](.+?)[}"]', bib_text, re.IGNORECASE | re.DOTALL)
    if m:
        title = m.group(1).replace("\n", " ").strip()

    # Extract year
    m = re.search(r'year\s*=\s*[{"]?(\d{4})[}"]?', bib_text, re.IGNORECASE)
    if m:
        year = int(m.group(1))

    # Extract author
    m = re.search(r'author\s*=\s*[{"](.+?)[}"]', bib_text, re.IGNORECASE | re.DOTALL)
    if m:
        raw = m.group(1).replace("\n", " ")
        # "Smith, John and Doe, Jane" → ["Smith, John", "Doe, Jane"]
        parts = [a.strip() for a in re.split(r"\band\b", raw, flags=re.IGNORECASE)]
        authors = [p for p in parts if p]

    return cite_key, title, authors, year


def _slugify(text: str) -> str:
    """Convert text to a filesystem-safe slug (lowercase, spaces to underscores, remove special chars)."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "_", text)
    return text[:50]
