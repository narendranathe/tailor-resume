"""
api_server.py
FastAPI browser UI for the tailor-resume pipeline.
Replaces the CLI for day-to-day use.

Start: python scripts/api_server.py  (binds localhost:8080)
Auth:  X-API-Key header must match API_KEY env var (default: "dev-key")

Endpoints:
    GET  /health                          -- liveness probe
    GET  /                                -- browser UI (HTML form)
    POST /generate                        -- full pipeline: JD + artifact -> ATS score + resume.tex
                                             (vault push runs in BackgroundTasks; vault_version
                                              comes back null — poll GET /vault/{user_id} for it)
    POST /score                           -- score only: JD + resume text -> score + gap report
    POST /compare                         -- formula vs Claude side-by-side score
    POST /cover-letter                    -- generate 2-paragraph cover letter (.tex + .txt)
    POST /ingest/github                   -- fetch GitHub repos as project bullets
    GET  /vault/{user_id}                 -- list resume versions in vault for user
    GET  /vault/{user_id}/{filename}      -- download a vault .tex file
    GET  /vault/{user_id}/{filename}/pdf  -- compile + download a vault .tex as PDF

Rate limit:
    In-process per-user_id limiter (defaults to 20 req/60s). Health + UI exempt.
    Anonymous requests are bucketed by client IP (falls back to "anonymous").
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections import defaultdict, deque
from dataclasses import asdict
from pathlib import Path
from typing import Deque, Dict, Optional

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

_SCRIPTS = Path(__file__).parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import vault_client  # noqa: E402  (imported as module so tests can monkeypatch its functions)
from cover_letter_renderer import _extract_company_from_jd  # noqa: E402
from cover_letter_renderer import build_cover_letter  # noqa: E402
from github_ingester import fetch_user_repos  # noqa: E402
from jd_gap_analyzer import run_analysis  # noqa: E402
from pipeline import execute_text  # noqa: E402
from vault_client import push_version  # noqa: E402

logger = logging.getLogger(__name__)

app = FastAPI(title="tailor-resume", version="2.0.0")

_UI_TEMPLATE = Path(__file__).parent.parent / "templates" / "ui" / "index.html"

# ---------------------------------------------------------------------------
# Rate limiter (in-memory; per process)
# ---------------------------------------------------------------------------

_RATE_LIMIT_PER_MINUTE = 20
_RATE_WINDOW_SECONDS = 60
_rate_buckets: Dict[str, Deque[float]] = defaultdict(deque)


def _rate_limit_key(user_id: str, request: Request) -> str:
    """Derive bucket key: explicit user_id wins; else client IP; else 'anonymous'."""
    uid = (user_id or "").strip()
    if uid:
        return uid
    client = getattr(request, "client", None)
    host = getattr(client, "host", None) if client else None
    return f"anon:{host}" if host else "anonymous"


def _rate_limit_check(request: Request, user_id: str = "") -> None:
    """FastAPI dependency: enforce per-key sliding-window rate limit."""
    key = _rate_limit_key(user_id, request)
    now = time.time()
    bucket = _rate_buckets[key]
    # Evict timestamps older than the window
    cutoff = now - _RATE_WINDOW_SECONDS
    while bucket and bucket[0] < cutoff:
        bucket.popleft()
    if len(bucket) >= _RATE_LIMIT_PER_MINUTE:
        oldest = bucket[0]
        retry_after = max(1, int(oldest + _RATE_WINDOW_SECONDS - now))
        logger.warning(
            "Rate limit hit for user_id=%s (%d req in 60s)", key, len(bucket)
        )
        raise HTTPException(
            status_code=429,
            detail="Too Many Requests",
            headers={"Retry-After": str(retry_after)},
        )
    bucket.append(now)


def _compile_pdf(tex_path: str) -> tuple[Optional[str], Optional[str]]:
    """
    Compile a .tex file to PDF using pdflatex.

    Returns (pdf_path, None) on success.
    Returns (None, None) when pdflatex is not on PATH.
    Returns (None, warning_str) on compilation failure.
    Never raises.
    """
    binary = os.getenv("PDFLATEX_PATH") or shutil.which("pdflatex")
    if not binary:
        return None, None
    out_dir = str(Path(tex_path).parent)
    try:
        result = subprocess.run(
            [binary, "-interaction=nonstopmode", "-halt-on-error",
             f"-output-directory={out_dir}", tex_path],
            capture_output=True,
            timeout=60,
        )
        pdf_path = tex_path.replace(".tex", ".pdf")
        if result.returncode == 0 and Path(pdf_path).exists():
            return pdf_path, None
        stderr = result.stderr.decode(errors="replace")[-300:]
        return None, f"pdflatex exit {result.returncode}: {stderr}"
    except subprocess.TimeoutExpired:
        return None, "pdflatex timed out after 60s"
    except Exception as exc:
        return None, str(exc)


def _check_api_key(x_api_key: str) -> None:
    expected = os.getenv("API_KEY", "dev-key")
    if x_api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid API key")


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class GenerateRequest(BaseModel):
    jd_text: str
    artifact_text: str
    artifact_format: str = "blob"
    output_path: str = "out/resume.tex"
    name: str = ""
    email: str = ""
    phone: str = ""
    linkedin: str = ""
    github: str = ""
    portfolio: str = ""
    user_id: str = ""  # for vault scoping; falls back to email then "anonymous"
    compile_pdf: bool = True  # set False to skip pdflatex and return .tex only
    vault_inline: bool = False  # opt-in: run vault push synchronously so response carries version_tag


class ScoreRequest(BaseModel):
    jd_text: str
    resume_text: str
    top_n: int = 5


class CoverLetterRequest(BaseModel):
    jd_text: str
    artifact_text: str
    artifact_format: str = "blob"
    name: str = ""
    email: str = ""
    phone: str = ""
    linkedin: str = ""
    method: str = "template"  # "claude" | "template"


class GitHubIngestRequest(BaseModel):
    username: str
    limit: int = 10
    fetch_readmes: bool = False  # disabled by default for speed in API context


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok", "version": "2.0.0"}


@app.get("/", response_class=HTMLResponse)
def index():
    if _UI_TEMPLATE.exists():
        return HTMLResponse(_UI_TEMPLATE.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>tailor-resume v2</h1><p>UI template not found at expected path.</p>")


def _vault_push_safe(
    user_id: str,
    company: str,
    role: str,
    tex_content: str,
    metadata: Dict,
    first_name: str,
) -> None:
    """Background-task-safe wrapper around vault_client.push_version.

    Always swallows exceptions so a vault failure never breaks the request.
    The synchronous response cannot expose the resulting version_tag — clients
    poll GET /vault/{user_id} to discover the newest entry.
    """
    try:
        push_version(
            user_id=user_id,
            company=company,
            role=role,
            tex_content=tex_content,
            metadata=metadata,
            first_name=first_name,
        )
    except Exception as exc:
        logger.warning("Background vault push failed for user_id=%s: %s", user_id, exc)


@app.post("/generate")
def generate(
    req: GenerateRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    x_api_key: str = Header(default=""),
):
    """
    Run the full tailor pipeline.

    The vault push is queued via FastAPI BackgroundTasks and runs **after** the
    HTTP response is returned. Because the push has not yet completed when the
    response is serialised, the ``vault_version`` field is always ``null`` here
    — clients should poll ``GET /vault/{user_id}`` for the latest version_tag.
    Set ``vault_inline=true`` on the request body to force a (slower) synchronous
    push that populates ``vault_version`` directly.
    """
    _check_api_key(x_api_key)
    _rate_limit_check(request, req.user_id or req.email)
    if not req.jd_text.strip():
        raise HTTPException(status_code=422, detail="jd_text must not be empty")
    if not req.artifact_text.strip():
        raise HTTPException(status_code=422, detail="artifact_text must not be empty")
    try:
        header = {
            "name": req.name,
            "email": req.email,
            "phone": req.phone,
            "linkedin": req.linkedin,
            "github": req.github,
            "portfolio": req.portfolio,
        }
        result = execute_text(
            jd_text=req.jd_text,
            artifact_text=req.artifact_text,
            artifact_format=req.artifact_format,
            output_path=req.output_path,
            header=header,
        )

        vault_version: Optional[str] = None
        try:
            tex_content = Path(result.output_path).read_text(encoding="utf-8")
            company = _extract_company_from_jd(req.jd_text) if req.jd_text else "Unknown"
            push_user = req.user_id or req.email or "anonymous"
            first_name = req.name.split()[0] if req.name else ""
            metadata = {"ats_score": result.ats_score, "engine": "formula"}
            if req.vault_inline:
                # Opt-in synchronous push: response carries the real version_tag.
                try:
                    entry = push_version(
                        user_id=push_user,
                        company=company,
                        role="Resume",
                        tex_content=tex_content,
                        metadata=metadata,
                        first_name=first_name,
                    )
                    vault_version = entry.version_tag if entry else None
                except Exception:
                    vault_version = None
            else:
                # Default: queue background push; vault_version stays None.
                # Clients call GET /vault/{user_id} to discover the new entry.
                background_tasks.add_task(
                    _vault_push_safe,
                    push_user,
                    company,
                    "Resume",
                    tex_content,
                    metadata,
                    first_name,
                )
        except Exception:
            # If reading the rendered .tex fails, skip the push silently.
            pass

        pdf_path, compile_warning = (
            _compile_pdf(result.output_path)
            if req.compile_pdf and result.output_path
            else (None, None)
        )

        return {
            "ats_score": result.ats_score,
            "resume_path": result.output_path,
            "pdf_path": pdf_path,
            "compile_warning": compile_warning,
            "gap_summary": result.gap_summary,
            # set by background task; check /vault/{user_id} for the latest version
            "vault_version": vault_version,
            "warnings": [],
        }
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/score")
def score(req: ScoreRequest, request: Request, x_api_key: str = Header(default="")):
    _check_api_key(x_api_key)
    _rate_limit_check(request)
    if not req.jd_text.strip():
        raise HTTPException(status_code=422, detail="jd_text must not be empty")
    if not req.resume_text.strip():
        raise HTTPException(status_code=422, detail="resume_text must not be empty")
    try:
        report = run_analysis(req.jd_text, req.resume_text, top_n=req.top_n)
        return {"ats_score": report.ats_score_estimate, "gap_report": asdict(report)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/compare")
def compare(req: ScoreRequest, request: Request, x_api_key: str = Header(default="")):
    """Side-by-side ATS comparison: formula engine vs Claude-as-judge."""
    _check_api_key(x_api_key)
    _rate_limit_check(request)
    if not req.jd_text.strip():
        raise HTTPException(status_code=422, detail="jd_text must not be empty")
    if not req.resume_text.strip():
        raise HTTPException(status_code=422, detail="resume_text must not be empty")
    try:
        from ats_scorer import compare as _compare  # noqa: E402
        formula_r, claude_r = _compare(req.jd_text, req.resume_text)
        return {
            "formula": {
                "score": formula_r.score,
                "method_used": formula_r.method_used,
                "reasoning": formula_r.reasoning,
                "recommendations": formula_r.recommendations,
            },
            "claude": {
                "score": claude_r.score,
                "method_used": claude_r.method_used,
                "reasoning": claude_r.reasoning,
                "recommendations": claude_r.recommendations,
                "bullet_scores": claude_r.bullet_scores,
                "formula_score": claude_r.formula_score,
            },
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/cover-letter")
def cover_letter(req: CoverLetterRequest, request: Request, x_api_key: str = Header(default="")):
    _check_api_key(x_api_key)
    _rate_limit_check(request, req.email)
    if not req.jd_text.strip():
        raise HTTPException(status_code=422, detail="jd_text must not be empty")
    if not req.artifact_text.strip():
        raise HTTPException(status_code=422, detail="artifact_text must not be empty")
    try:
        import dataclasses as _dc
        import profile_extractor as _pe  # noqa: E402
        _parsers = {
            "blob": _pe.parse_blob,
            "markdown": _pe.parse_markdown,
            "latex": _pe.parse_latex,
            "linkedin": _pe.parse_linkedin,
        }
        _parse_fn = _parsers.get(req.artifact_format, _pe.parse_blob)
        profile = _dc.asdict(_parse_fn(req.artifact_text))
        report = run_analysis(req.jd_text, req.artifact_text, top_n=5)
        header = {
            "name": req.name,
            "email": req.email,
            "phone": req.phone,
            "linkedin": req.linkedin,
        }
        result = build_cover_letter(
            profile_dict=profile,
            report=report,
            header=header,
            jd_text=req.jd_text,
            method=req.method,
        )
        # Write .tex to temp file so pdflatex can compile it
        import tempfile as _tf
        _tex_tmp = _tf.NamedTemporaryFile(suffix=".tex", delete=False)
        Path(_tex_tmp.name).write_text(result.tex, encoding="utf-8")
        _tex_tmp.close()
        cl_pdf_path, _ = _compile_pdf(_tex_tmp.name)

        return {
            "txt": result.txt,
            "tex": result.tex,
            "word_count": result.word_count,
            "method_used": result.method_used,
            "docx_path": result.docx_path,
            "pdf_path": cl_pdf_path,
        }
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/ingest/github")
def ingest_github(req: GitHubIngestRequest, request: Request, x_api_key: str = Header(default="")):
    _check_api_key(x_api_key)
    _rate_limit_check(request, req.username)
    if not req.username.strip():
        raise HTTPException(status_code=422, detail="username must not be empty")
    try:
        projects = fetch_user_repos(
            req.username.strip(),
            include_forks=False,
            limit=req.limit,
            fetch_readmes=req.fetch_readmes,
        )
        return {"projects": projects, "count": len(projects)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Vault read endpoints
# ---------------------------------------------------------------------------


@app.get("/vault/{user_id}")
def vault_list(user_id: str, request: Request, x_api_key: str = Header(default="")):
    """List resume versions stored in the vault for a user."""
    _check_api_key(x_api_key)
    _rate_limit_check(request, user_id)
    entries = vault_client.list_versions(user_id)
    return {"user_id": user_id, "count": len(entries), "entries": [asdict(e) for e in entries]}


@app.get("/vault/{user_id}/{filename}")
def vault_get_tex(user_id: str, filename: str, request: Request,
                  x_api_key: str = Header(default="")):
    """Download the raw .tex content of a specific vault entry."""
    _check_api_key(x_api_key)
    _rate_limit_check(request, user_id)
    content = vault_client.get_version(user_id, filename)
    if not content:
        raise HTTPException(status_code=404, detail=f"Vault entry not found: {filename}")
    display_name = filename if filename.endswith(".tex") else f"{filename}.tex"
    return Response(
        content=content,
        media_type="application/x-tex",
        headers={"Content-Disposition": f"attachment; filename={display_name}"},
    )


@app.get("/vault/{user_id}/{filename}/pdf")
def vault_get_pdf(
    user_id: str,
    filename: str,
    request: Request,
    first_name: str = "",
    x_api_key: str = Header(default=""),
):
    """Compile a vault .tex entry on-the-fly and return the resulting PDF."""
    _check_api_key(x_api_key)
    _rate_limit_check(request, user_id)
    tex_content = vault_client.get_version(user_id, filename)
    if not tex_content:
        raise HTTPException(status_code=404, detail=f"Vault entry not found: {filename}")

    # Materialise to a temp .tex so pdflatex can read it.
    with tempfile.TemporaryDirectory() as tmpdir:
        tex_path = Path(tmpdir) / f"{filename.replace('.tex', '')}.tex"
        tex_path.write_text(tex_content, encoding="utf-8")
        pdf_path, warning = _compile_pdf(str(tex_path))
        if pdf_path is None and warning is None:
            raise HTTPException(
                status_code=501,
                detail={
                    "error": "PDF compilation unavailable",
                    "detail": "Install TeX Live to enable PDF export",
                },
            )
        if pdf_path is None:
            raise HTTPException(status_code=500, detail=warning or "pdflatex failed")
        pdf_bytes = Path(pdf_path).read_bytes()

    download_name = f"{first_name}.pdf" if first_name else f"{filename.replace('.tex', '')}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={download_name}"},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8080)
