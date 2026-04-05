"""
api_server.py
FastAPI browser UI for the tailor-resume pipeline.
Replaces the CLI for day-to-day use.

Start: python scripts/api_server.py  (binds localhost:8080)
Auth:  X-API-Key header must match API_KEY env var (default: "dev-key")

Endpoints:
    GET  /health   -- liveness probe
    GET  /         -- browser UI (HTML form)
    POST /generate -- full pipeline: JD + artifact -> ATS score + resume.tex
    POST /score    -- score only: JD + resume text -> ATS score + gap report
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

from jd_gap_analyzer import run_analysis  # noqa: E402
from pipeline import execute_text  # noqa: E402

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


class ScoreRequest(BaseModel):
    jd_text: str
    resume_text: str
    top_n: int = 5


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
        return {
            "ats_score": result.ats_score,
            "resume_path": result.output_path,
            "gap_summary": result.gap_summary,
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8080)
