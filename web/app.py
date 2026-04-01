"""
web/app.py - Survey Agent Web interface (FastAPI + WebSocket)

Start: survey-agent --web
       or: uvicorn web.app:app --reload

WebSocket protocol:
  Client → Server: {"type": "start", "config": {...}}
                   {"type": "resume", "job_id": "...", "value": "..."}
  Server → Client: {"type": "output", "text": "..."}
                   {"type": "interrupt", "data": {...}}
                   {"type": "progress", "phase": "...", "pct": 0-100}
                   {"type": "done", "files": [...]}
                   {"type": "error", "message": "..."}
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import uuid
from pathlib import Path
from typing import Any

import aiofiles
import httpx
from fastapi import FastAPI, File, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from web.runner import SurveyRunner

logger = logging.getLogger(__name__)

app = FastAPI(title="Survey Agent", docs_url=None, redoc_url=None)

# Static files (CSS, JS)
_STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

# Active runner storage (job_id → SurveyRunner)
_runners: dict[str, SurveyRunner] = {}


@app.get("/", response_class=HTMLResponse)
async def index() -> FileResponse:
    """Return main interface HTML."""
    return FileResponse(str(_STATIC_DIR / "index.html"))


@app.get("/api/search-papers")
async def search_papers(q: str = "", limit: int = 10) -> JSONResponse:
    """Proxy paper title search via Semantic Scholar."""
    if not q.strip():
        return JSONResponse({"results": []})
    s2_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")
    headers = {"x-api-key": s2_key} if s2_key else {}
    params = {
        "query": q,
        "limit": min(limit, 20),
        "fields": "paperId,externalIds,title,authors,year,citationCount",
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://api.semanticscholar.org/graph/v1/paper/search",
                params=params,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        return JSONResponse({"results": [], "error": str(exc)})

    results = []
    for p in data.get("data", []):
        authors = p.get("authors", [])
        author_str = authors[0]["name"] if authors else "Unknown"
        if len(authors) > 1:
            author_str += " et al."
        results.append({
            "id": p.get("paperId", ""),
            "arxiv_id": (p.get("externalIds") or {}).get("ArXiv", ""),
            "doi": (p.get("externalIds") or {}).get("DOI", ""),
            "title": p.get("title", ""),
            "authors": author_str,
            "year": p.get("year"),
            "citations": p.get("citationCount", 0),
        })
    return JSONResponse({"results": results})


@app.post("/api/upload-start-doc")
async def upload_start_doc(file: UploadFile = File(...)) -> JSONResponse:
    """Accept a Start document (PDF/MD/TXT/DOCX), save it, return path."""
    allowed_exts = {".pdf", ".md", ".txt", ".doc", ".docx"}
    ext = Path(file.filename).suffix.lower() if file.filename else ""
    if ext not in allowed_exts:
        return JSONResponse(
            {"error": f"Unsupported format. Allowed: {', '.join(sorted(allowed_exts))}"},
            status_code=400,
        )
    dest_dir = Path("data/start_docs")
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / file.filename

    async with aiofiles.open(str(dest_path), "wb") as f:
        while True:
            chunk = await file.read(1024 * 256)  # 256 KB
            if not chunk:
                break
            await f.write(chunk)

    return JSONResponse({"status": "ok", "filename": file.filename, "path": str(dest_path)})


@app.post("/api/upload-seed-pdf")
async def upload_seed_pdf(file: UploadFile = File(...)) -> JSONResponse:
    """Accept a PDF upload, save it to unclassified/, return a reference ID."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        return JSONResponse({"error": "Only PDF files are accepted"}, status_code=400)

    dest_dir = Path("data/papers/unclassified")
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / file.filename

    import aiofiles
    async with aiofiles.open(str(dest_path), "wb") as f:
        while chunk := await file.read(1024 * 256):
            await f.write(chunk)

    return JSONResponse({
        "status": "ok",
        "filename": file.filename,
        "path": str(dest_path),
        "ref": f"local:{file.filename}",
    })


@app.post("/api/download-refs")
async def download_refs(file: UploadFile = File(...)) -> JSONResponse:
    """
    Accept a PDF upload, extract its reference list, and download each cited paper.

    Returns a JSON report with per-paper download status.
    Long-running: typical papers have 30-80 references; expect 30-120s.
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        return JSONResponse({"error": "Only PDF files are accepted"}, status_code=400)

    # Save upload to a temp location
    import tempfile
    from pathlib import Path as _Path
    from survey_agent.utils.paper_downloader import PaperDownloader

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = _Path(tmp.name)

    try:
        downloader = PaperDownloader(
            save_dir=_Path("data/papers/unclassified"),
            unpaywall_email=os.getenv("UNPAYWALL_EMAIL", ""),
            s2_api_key=os.getenv("SEMANTIC_SCHOLAR_API_KEY", ""),
        )
        report = await downloader.download_from_pdf(tmp_path, llm_provider=None)
    finally:
        tmp_path.unlink(missing_ok=True)

    return JSONResponse({
        "summary": report.summary(),
        "total": report.total,
        "downloaded": report.downloaded,
        "skipped": report.skipped,
        "failed": report.failed,
        "results": [
            {
                "title": r.ref.title[:120],
                "status": r.status,
                "source": r.source,
                "saved_as": r.saved_path.name if r.saved_path else None,
                "error": r.error,
            }
            for r in report.results
        ],
    })


@app.post("/api/taxonomy/edit")
async def taxonomy_edit(body: dict) -> JSONResponse:
    """
    Accept a user-edited taxonomy structure and return it back (with version bump).

    In a full implementation this would trigger re-classification of papers
    via the LLM pipeline. For now it validates structure and echoes the result
    so the frontend can re-render immediately.
    """
    taxonomy = body.get("taxonomy")
    if not taxonomy or not isinstance(taxonomy, dict):
        return JSONResponse({"error": "Invalid taxonomy payload"}, status_code=400)

    # Bump version to signal a manual edit
    taxonomy["version"] = taxonomy.get("version", 0) + 1
    taxonomy.setdefault("changelog", []).append(
        f"v{taxonomy['version']}: manual edit via web interface"
    )

    return JSONResponse({"taxonomy": taxonomy, "status": "ok"})


@app.get("/api/browse-dir")
async def browse_dir() -> JSONResponse:
    """Open a native folder picker dialog (macOS/Linux/Windows via tkinter)."""
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.wm_attributes("-topmost", True)
        path = filedialog.askdirectory(title="Select Papers Directory")
        root.destroy()
        return JSONResponse({"path": path or ""})
    except Exception as exc:
        return JSONResponse({"path": "", "error": str(exc)})


@app.websocket("/ws/{job_id}")
async def websocket_endpoint(websocket: WebSocket, job_id: str) -> None:
    """
    WebSocket endpoint handling the full lifecycle of a single Survey task.

    Protocol:
    1. Client sends {"type": "start", "config": {...}} to start the task
    2. Server streams progress, output, and interrupt events
    3. Client sends {"type": "resume", "value": "..."} to respond to interrupts
    4. Server sends {"type": "done"} on completion
    """
    await websocket.accept()

    runner = SurveyRunner(job_id=job_id, websocket=websocket)
    _runners[job_id] = runner

    try:
        # Wait for start message
        start_msg = await websocket.receive_json()
        if start_msg.get("type") != "start":
            await websocket.send_json({"type": "error", "message": "Expected type=start"})
            return

        config = start_msg.get("config", {})
        await runner.run(config)

    except WebSocketDisconnect:
        logger.info(f"Job {job_id}: client disconnected")
        runner.cancel()
    except Exception as e:
        logger.exception(f"Job {job_id}: unhandled exception")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        _runners.pop(job_id, None)
