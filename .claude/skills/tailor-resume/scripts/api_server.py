"""
api_server.py
FastAPI browser UI for the tailor-resume pipeline.
Replaces the CLI for day-to-day use.

Start: python scripts/api_server.py  (binds localhost:8080)
Auth:  X-API-Key header must match API_KEY env var (default: "dev-key")

Endpoints:
    GET  /health          -- liveness probe
    GET  /                -- browser UI (HTML form)
    POST /generate        -- full pipeline: JD + artifact -> ATS score + resume.tex
                             (pushes to vault if GITHUB_VAULT_TOKEN is set)
    POST /score           -- score only: JD + resume text -> ATS score + gap report
    POST /cover-letter    -- generate 2-paragraph cover letter (.tex + .txt)
    POST /ingest/github   -- fetch GitHub repos as project bullets
"""
from __future__ import annotations

import os
import sys
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

_SCRIPTS = Path(__file__).parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from cover_letter_renderer import _extract_company_from_jd  # noqa: E402
from cover_letter_renderer import build_cover_letter  # noqa: E402
from github_ingester import fetch_user_repos  # noqa: E402
from jd_gap_analyzer import run_analysis  # noqa: E402
from pipeline import execute_text  # noqa: E402
from vault_client import push_version  # noqa: E402

app = FastAPI(title="tailor-resume", version="2.0.0")

_UI_TEMPLATE = Path(__file__).parent.parent / "templates" / "ui" / "index.html"


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


@app.post("/generate")
def generate(req: GenerateRequest, x_api_key: str = Header(default="")):
    _check_api_key(x_api_key)
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
        # Non-blocking vault push — fails silently if GITHUB_VAULT_TOKEN not set
        vault_entry = None
        try:
            tex_content = Path(result.output_path).read_text(encoding="utf-8")
            company = _extract_company_from_jd(req.jd_text) if req.jd_text else "Unknown"
            vault_entry = push_version(
                user_id=req.user_id or req.email or "anonymous",
                company=company,
                role="Resume",
                tex_content=tex_content,
                metadata={"ats_score": result.ats_score, "engine": "formula"},
                first_name=req.name.split()[0] if req.name else "",
            )
        except Exception:
            pass

        return {
            "ats_score": result.ats_score,
            "resume_path": result.output_path,
            "gap_summary": result.gap_summary,
            "vault_version": vault_entry.version_tag if vault_entry else None,
            "warnings": [],
        }
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/score")
def score(req: ScoreRequest, x_api_key: str = Header(default="")):
    _check_api_key(x_api_key)
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
def compare(req: ScoreRequest, x_api_key: str = Header(default="")):
    """Side-by-side ATS comparison: formula engine vs Claude-as-judge."""
    _check_api_key(x_api_key)
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
def cover_letter(req: CoverLetterRequest, x_api_key: str = Header(default="")):
    _check_api_key(x_api_key)
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
        return {
            "txt": result.txt,
            "tex": result.tex,
            "word_count": result.word_count,
            "method_used": result.method_used,
            "docx_path": result.docx_path,
        }
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/ingest/github")
def ingest_github(req: GitHubIngestRequest, x_api_key: str = Header(default="")):
    _check_api_key(x_api_key)
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8080)
