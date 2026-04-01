"""
paper_downloader.py

Async PDF downloader that resolves references to full-text PDFs.

Download cascade per reference:
  1. arXiv (by explicit arXiv ID, or title search)
  2. Unpaywall (by DOI, or title search)
  3. Semantic Scholar metadata → re-try arXiv/Unpaywall with enriched data
  → Give up and record as failed

Entry point:
  downloader = PaperDownloader(save_dir=Path("data/papers/unclassified"))
  report = await downloader.download_from_pdf(pdf_path, llm_provider=...)
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

from survey_agent.utils.pdf_reference_extractor import RefEntry, extract_references

if TYPE_CHECKING:
    from survey_agent.interfaces.llm_provider import LLMProvider

logger = logging.getLogger(__name__)

_ARXIV_API = "https://export.arxiv.org/api/query"
_ARXIV_PDF_BASE = "https://arxiv.org/pdf"
_UNPAYWALL_API = "https://api.unpaywall.org/v2"
_S2_SEARCH = "https://api.semanticscholar.org/graph/v1/paper/search"
_REQUEST_TIMEOUT = 20
_RATE_LIMIT_DELAY = 1.5  # seconds between requests to same host


# ── Result types ───────────────────────────────────────────────────────────────

@dataclass
class DownloadResult:
    ref: RefEntry
    status: str          # "ok" | "skipped" | "failed"
    source: str = ""     # "arxiv" | "unpaywall" | "s2" | ""
    saved_path: Path | None = None
    error: str = ""


@dataclass
class DownloadReport:
    total: int = 0
    downloaded: int = 0
    skipped: int = 0
    failed: int = 0
    results: list[DownloadResult] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"Total: {self.total} | Downloaded: {self.downloaded} | "
            f"Skipped (already have): {self.skipped} | Failed: {self.failed}"
        )


# ── Main class ─────────────────────────────────────────────────────────────────

class PaperDownloader:
    """
    Async reference downloader.

    Args:
        save_dir:          Directory to save downloaded PDFs.
        unpaywall_email:   Required for Unpaywall API (reads UNPAYWALL_EMAIL env if None).
        s2_api_key:        Optional Semantic Scholar API key for better rate limits.
        concurrency:       Max parallel downloads.
    """

    def __init__(
        self,
        save_dir: Path | str = "data/papers/unclassified",
        unpaywall_email: str | None = None,
        s2_api_key: str | None = None,
        concurrency: int = 3,
    ) -> None:
        self.save_dir = Path(save_dir)
        self.save_dir.mkdir(parents=True, exist_ok=True)
        self._email = unpaywall_email or os.getenv("UNPAYWALL_EMAIL", "")
        self._s2_key = s2_api_key or os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")
        self._semaphore = asyncio.Semaphore(concurrency)
        self._arxiv_last_req = 0.0

    # ── Public API ─────────────────────────────────────────────────────────────

    async def download_from_pdf(
        self,
        pdf_path: Path,
        llm_provider: "LLMProvider | None" = None,
        max_ref_pages: int = 8,
        progress_cb: "callable[[int, int, str], None] | None" = None,
    ) -> DownloadReport:
        """
        Full pipeline: extract references from PDF, then download each one.

        Args:
            pdf_path:      Source PDF containing the reference list.
            llm_provider:  Optional LLM for better reference parsing.
            max_ref_pages: Max trailing pages to search for references.
            progress_cb:   Optional callback(current, total, title) for UI updates.

        Returns:
            DownloadReport with per-paper results.
        """
        refs = await extract_references(pdf_path, llm_provider, max_ref_pages)
        return await self.download_refs(refs, progress_cb)

    async def download_refs(
        self,
        refs: list[RefEntry],
        progress_cb: "callable[[int, int, str], None] | None" = None,
    ) -> DownloadReport:
        """Download a list of pre-parsed RefEntry objects."""
        report = DownloadReport(total=len(refs))

        async def _run(i: int, ref: RefEntry) -> None:
            if progress_cb:
                try:
                    progress_cb(i, len(refs), ref.title[:60])
                except Exception:
                    pass
            result = await self._download_one(ref)
            if result.status == "ok":
                report.downloaded += 1
            elif result.status == "skipped":
                report.skipped += 1
            else:
                report.failed += 1
            report.results.append(result)

        tasks = [_run(i, ref) for i, ref in enumerate(refs)]
        await asyncio.gather(*tasks)
        return report

    # ── Per-paper download ─────────────────────────────────────────────────────

    async def _download_one(self, ref: RefEntry) -> DownloadResult:
        async with self._semaphore:
            if not ref.has_locator():
                return DownloadResult(ref=ref, status="failed", error="no_locator")

            # Skip if we already have a file with the same title hash
            dest = self._dest_path(ref)
            if dest.exists():
                return DownloadResult(ref=ref, status="skipped", saved_path=dest)

            # Cascade: arXiv → Unpaywall
            result = await self._try_arxiv(ref, dest)
            if result:
                return result

            result = await self._try_unpaywall(ref, dest)
            if result:
                return result

            # Enrich via S2, then retry
            enriched = await self._enrich_via_s2(ref)
            if enriched:
                result = await self._try_arxiv(enriched, dest)
                if result:
                    return result
                result = await self._try_unpaywall(enriched, dest)
                if result:
                    return result

            return DownloadResult(ref=ref, status="failed", error="all_sources_exhausted")

    # ── arXiv ──────────────────────────────────────────────────────────────────

    async def _try_arxiv(self, ref: RefEntry, dest: Path) -> DownloadResult | None:
        pdf_url = await self._arxiv_pdf_url(ref)
        if not pdf_url:
            return None
        try:
            await self._save_pdf(pdf_url, dest)
            return DownloadResult(ref=ref, status="ok", source="arxiv", saved_path=dest)
        except Exception as exc:
            logger.debug("arXiv download failed for '%s': %s", ref.title[:50], exc)
            return None

    async def _arxiv_pdf_url(self, ref: RefEntry) -> str | None:
        """Return a direct arXiv PDF URL, or None if not found."""
        # Direct arXiv ID
        if ref.arxiv_id:
            clean = re.sub(r"v\d+$", "", ref.arxiv_id)
            return f"{_ARXIV_PDF_BASE}/{clean}"

        if not ref.title:
            return None

        await self._arxiv_rate_limit()
        query = f'ti:"{ref.title}"'
        if ref.year:
            query += f" AND submittedDate:[{ref.year}01010000 TO {ref.year}12312359]"

        params = {"search_query": query, "max_results": "3", "sortBy": "relevance"}
        try:
            async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
                resp = await client.get(_ARXIV_API, params=params)
                resp.raise_for_status()
                xml = resp.text
        except Exception as exc:
            logger.debug("arXiv API error: %s", exc)
            return None

        # Parse first <entry> → <id>
        id_match = re.search(r"<id>(https?://arxiv\.org/abs/([^<]+))</id>", xml)
        if not id_match:
            return None

        title_match = re.search(r"<title>\s*([^<]+)\s*</title>", xml)
        if title_match:
            found_title = title_match.group(1).strip()
            if not _titles_match(ref.title, found_title):
                logger.debug("arXiv title mismatch: '%s' vs '%s'", ref.title[:40], found_title[:40])
                return None

        arxiv_id = id_match.group(2).strip()
        return f"{_ARXIV_PDF_BASE}/{arxiv_id}"

    async def _arxiv_rate_limit(self) -> None:
        import time
        now = time.monotonic()
        wait = _RATE_LIMIT_DELAY - (now - self._arxiv_last_req)
        if wait > 0:
            await asyncio.sleep(wait)
        self._arxiv_last_req = time.monotonic()

    # ── Unpaywall ─────────────────────────────────────────────────────────────

    async def _try_unpaywall(self, ref: RefEntry, dest: Path) -> DownloadResult | None:
        pdf_url = await self._unpaywall_pdf_url(ref)
        if not pdf_url:
            return None
        try:
            await self._save_pdf(pdf_url, dest)
            return DownloadResult(ref=ref, status="ok", source="unpaywall", saved_path=dest)
        except Exception as exc:
            logger.debug("Unpaywall download failed for '%s': %s", ref.title[:50], exc)
            return None

    async def _unpaywall_pdf_url(self, ref: RefEntry) -> str | None:
        if not self._email:
            return None

        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
            # DOI lookup
            if ref.doi:
                try:
                    resp = await client.get(
                        f"{_UNPAYWALL_API}/{ref.doi}",
                        params={"email": self._email},
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        loc = data.get("best_oa_location") or {}
                        url = loc.get("url_for_pdf")
                        if url:
                            return url
                except Exception as exc:
                    logger.debug("Unpaywall DOI error: %s", exc)

            # Title search
            if ref.title:
                try:
                    resp = await client.get(
                        f"{_UNPAYWALL_API}/search",
                        params={"query": ref.title, "email": self._email},
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        for item in (data.get("results") or [])[:5]:
                            r = item.get("response", {})
                            if not _titles_match(ref.title, r.get("title", "")):
                                continue
                            loc = r.get("best_oa_location") or {}
                            url = loc.get("url_for_pdf")
                            if url:
                                return url
                except Exception as exc:
                    logger.debug("Unpaywall title search error: %s", exc)

        return None

    # ── S2 enrichment ─────────────────────────────────────────────────────────

    async def _enrich_via_s2(self, ref: RefEntry) -> RefEntry | None:
        """Query S2 by title to get DOI / arXiv ID, return enriched RefEntry."""
        if not ref.title:
            return None
        headers = {"x-api-key": self._s2_key} if self._s2_key else {}
        params = {
            "query": ref.title,
            "limit": 3,
            "fields": "externalIds,title",
        }
        try:
            async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
                resp = await client.get(_S2_SEARCH, params=params, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except Exception:
            return None

        for paper in data.get("data", []):
            if not _titles_match(ref.title, paper.get("title", "")):
                continue
            ids = paper.get("externalIds") or {}
            new_doi = ids.get("DOI") or ref.doi
            new_arxiv = ids.get("ArXiv") or ref.arxiv_id
            if new_doi != ref.doi or new_arxiv != ref.arxiv_id:
                from copy import copy
                enriched = copy(ref)
                enriched.doi = new_doi
                enriched.arxiv_id = new_arxiv
                return enriched
        return None

    # ── File save ─────────────────────────────────────────────────────────────

    async def _save_pdf(self, url: str, dest: Path) -> None:
        """Download a PDF from url and save to dest."""
        headers = {"User-Agent": "Mozilla/5.0 (survey-agent research tool)"}
        async with httpx.AsyncClient(
            timeout=60,
            follow_redirects=True,
            headers=headers,
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            ct = resp.headers.get("content-type", "")
            if "pdf" not in ct and not url.endswith(".pdf"):
                raise ValueError(f"Response is not a PDF (content-type: {ct})")
            dest.write_bytes(resp.content)

    def _dest_path(self, ref: RefEntry) -> Path:
        """Generate a safe filename from the reference title + year."""
        safe = re.sub(r"[^\w\s-]", "", ref.title or "untitled")
        safe = re.sub(r"\s+", "_", safe.strip())[:80]
        year = f"_{ref.year}" if ref.year else ""
        # Include a short hash to avoid collisions
        h = hashlib.md5((ref.title + str(ref.year)).encode()).hexdigest()[:6]
        return self.save_dir / f"{safe}{year}_{h}.pdf"


# ── Helpers ────────────────────────────────────────────────────────────────────

def _normalise(s: str) -> str:
    return re.sub(r"\W+", "", s.lower())


def _titles_match(a: str, b: str, threshold: float = 0.6) -> bool:
    """Rough title similarity check (word overlap ratio)."""
    if not a or not b:
        return False
    wa = set(_normalise(a).split()) or set(_normalise(a))
    wb = set(_normalise(b).split()) or set(_normalise(b))
    if not wa or not wb:
        return False
    overlap = len(wa & wb) / min(len(wa), len(wb))
    return overlap >= threshold
