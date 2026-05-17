"""Tests for github_ingester.py — GitHub repo ingestion for resume projects."""
from __future__ import annotations

import base64
import json
import sys
import urllib.error
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / ".claude" / "skills" / "tailor-resume" / "scripts"))

from github_ingester import (  # noqa: E402
    _bullets_from_readme,
    _extract_metrics,
    _extract_readme_bullets,
    _parse_repo_url,
    _repo_to_project,
    fetch_repo,
    fetch_user_repos,
    ingest_repo,
    ingest_repo_project,
    inject_github_projects,
)

# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

_SAMPLE_REPO = {
    "name": "autoapply-ai",
    "full_name": "narendranathe/autoapply-ai",
    "description": "AI-powered job application assistant with Chrome extension.",
    "language": "Python",
    "stargazers_count": 42,
    "topics": ["fastapi", "chrome-extension", "ai"],
    "html_url": "https://github.com/narendranathe/autoapply-ai",
    "fork": False,
}

_SAMPLE_README = """\
# autoapply-ai

AI-powered job automation tool.

## Features

- Reduced application time by 80% using LLM-generated answers
- Supports 12+ job platforms including LinkedIn and Greenhouse
- Built with FastAPI, Chrome MV3, PostgreSQL, and Redis
"""


# ---------------------------------------------------------------------------
# _extract_readme_bullets
# ---------------------------------------------------------------------------


def test_extract_readme_bullets_finds_dashes():
    bullets = _extract_readme_bullets(_SAMPLE_README)
    assert len(bullets) >= 1
    assert any("80%" in b for b in bullets)


def test_extract_readme_bullets_max_three():
    readme = "\n".join(f"- Bullet {i} about something interesting here" for i in range(10))
    bullets = _extract_readme_bullets(readme)
    assert len(bullets) == 3


def test_extract_readme_bullets_skips_short():
    readme = "- OK\n- This is a long enough bullet point here\n"
    bullets = _extract_readme_bullets(readme)
    assert all(len(b) > 15 for b in bullets)


# ---------------------------------------------------------------------------
# _extract_metrics
# ---------------------------------------------------------------------------


def test_extract_metrics_percent():
    assert "80%" in _extract_metrics("Reduced time by 80% using CDC.")


def test_extract_metrics_empty_on_no_match():
    assert _extract_metrics("No numbers here at all.") == []


def test_extract_metrics_multiple():
    metrics = _extract_metrics("Saved 30% cost, processed 1M events/s.")
    assert len(metrics) >= 1


# ---------------------------------------------------------------------------
# _repo_to_project
# ---------------------------------------------------------------------------


def test_repo_to_project_structure():
    project = _repo_to_project(_SAMPLE_REPO)
    assert project["name"] == "autoapply-ai"
    assert project["source"] == "github"
    assert project["stars"] == 42
    assert "Python" in project["tools"]
    assert "fastapi" in project["tools"]
    assert project["url"] == "https://github.com/narendranathe/autoapply-ai"


def test_repo_to_project_description_as_bullet():
    project = _repo_to_project(_SAMPLE_REPO)
    texts = [b["text"] for b in project["bullets"]]
    assert any("AI-powered" in t for t in texts)


def test_repo_to_project_star_bullet_added():
    project = _repo_to_project(_SAMPLE_REPO)
    texts = [b["text"] for b in project["bullets"]]
    assert any("42" in t for t in texts)


def test_repo_to_project_no_star_bullet_below_10():
    repo = {**_SAMPLE_REPO, "stargazers_count": 3}
    project = _repo_to_project(repo)
    texts = [b["text"] for b in project["bullets"]]
    assert not any("stars" in t.lower() for t in texts)


def test_repo_to_project_readme_bullets():
    project = _repo_to_project(_SAMPLE_REPO, readme=_SAMPLE_README)
    texts = [b["text"] for b in project["bullets"]]
    assert any("80%" in t for t in texts)


# ---------------------------------------------------------------------------
# fetch_user_repos
# ---------------------------------------------------------------------------


def test_fetch_user_repos_no_token_uses_public(monkeypatch):
    """Runs without token — headers should not include Authorization."""
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    with patch("github_ingester._get", return_value=[_SAMPLE_REPO]):
        with patch("github_ingester._fetch_readme", return_value=""):
            projects = fetch_user_repos("narendranathe", limit=5)
    assert len(projects) == 1
    assert projects[0]["name"] == "autoapply-ai"


def test_fetch_user_repos_skips_forks():
    fork_repo = {**_SAMPLE_REPO, "fork": True, "name": "some-fork"}
    with patch("github_ingester._get", return_value=[fork_repo, _SAMPLE_REPO]):
        with patch("github_ingester._fetch_readme", return_value=""):
            projects = fetch_user_repos("user", include_forks=False)
    assert all(p["name"] != "some-fork" for p in projects)


def test_fetch_user_repos_includes_forks_when_requested():
    fork_repo = {**_SAMPLE_REPO, "fork": True, "name": "some-fork"}
    with patch("github_ingester._get", return_value=[fork_repo, _SAMPLE_REPO]):
        with patch("github_ingester._fetch_readme", return_value=""):
            projects = fetch_user_repos("user", include_forks=True)
    assert any(p["name"] == "some-fork" for p in projects)


def test_fetch_user_repos_api_error_returns_empty():
    with patch("github_ingester._get", return_value=None):
        projects = fetch_user_repos("no_such_user")
    assert projects == []


def test_fetch_user_repos_respects_limit():
    repos = [{**_SAMPLE_REPO, "name": f"repo{i}", "full_name": f"u/repo{i}"} for i in range(10)]
    with patch("github_ingester._get", return_value=repos):
        with patch("github_ingester._fetch_readme", return_value=""):
            projects = fetch_user_repos("user", limit=3)
    assert len(projects) == 3


# ---------------------------------------------------------------------------
# fetch_repo
# ---------------------------------------------------------------------------


def test_fetch_repo_returns_project():
    with patch("github_ingester._get", return_value=_SAMPLE_REPO):
        with patch("github_ingester._fetch_readme", return_value=_SAMPLE_README):
            project = fetch_repo("narendranathe/autoapply-ai")
    assert project is not None
    assert project["name"] == "autoapply-ai"


def test_fetch_repo_returns_none_on_error():
    with patch("github_ingester._get", return_value=None):
        result = fetch_repo("invalid/repo")
    assert result is None


# ---------------------------------------------------------------------------
# inject_github_projects
# ---------------------------------------------------------------------------


def test_inject_github_projects_adds_to_profile():
    profile = {"projects": [{"name": "existing-project", "description": "pre-existing"}]}
    with patch("github_ingester.fetch_user_repos", return_value=[_repo_to_project(_SAMPLE_REPO)]):
        updated = inject_github_projects(profile, "narendranathe")
    names = [p["name"] for p in updated["projects"]]
    assert "existing-project" in names
    assert "autoapply-ai" in names


def test_inject_github_projects_no_duplicates():
    existing = _repo_to_project(_SAMPLE_REPO)
    profile = {"projects": [existing]}
    with patch("github_ingester.fetch_user_repos", return_value=[_repo_to_project(_SAMPLE_REPO)]):
        updated = inject_github_projects(profile, "narendranathe")
    names = [p["name"] for p in updated["projects"]]
    assert names.count("autoapply-ai") == 1


def test_inject_github_projects_creates_projects_key():
    profile = {}
    with patch("github_ingester.fetch_user_repos", return_value=[_repo_to_project(_SAMPLE_REPO)]):
        updated = inject_github_projects(profile, "narendranathe")
    assert "projects" in updated
    assert len(updated["projects"]) == 1


# ---------------------------------------------------------------------------
# Issue #66: ingest_repo(url, token) — flat bullet list from a single URL
# ---------------------------------------------------------------------------


_README_FOR_INGEST = """\
# tailor-resume

Some prose paragraph that should be ignored.

## Features

- Reduced application time by 80% using FastAPI for the backend
- Supports 12 platforms including LinkedIn and Greenhouse exporters
- Built with Python, Redis, and PostgreSQL for high-throughput ingestion

## Other

1. Numbered item one with FastAPI and metrics 50%
"""


def _b64(s: str) -> str:
    return base64.b64encode(s.encode("utf-8")).decode("ascii")


class _FakeResp:
    """Minimal context-manager response stub for urllib.request.urlopen."""

    def __init__(self, payload):
        if isinstance(payload, (dict, list)):
            self._raw = json.dumps(payload).encode("utf-8")
        elif isinstance(payload, bytes):
            self._raw = payload
        else:
            self._raw = str(payload).encode("utf-8")

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _make_urlopen(meta_payload, readme_payload=None, capture=None):
    """Build a fake urlopen that routes by URL path."""

    def fake_urlopen(req, timeout=15):
        if capture is not None:
            capture.setdefault("calls", []).append(
                {"url": req.full_url, "headers": dict(req.header_items())}
            )
        if req.full_url.endswith("/readme"):
            if readme_payload is None:
                raise urllib.error.HTTPError(
                    req.full_url, 404, "Not Found", hdrs=None, fp=None
                )
            return _FakeResp(readme_payload)
        return _FakeResp(meta_payload)

    return fake_urlopen


# --- _parse_repo_url ---------------------------------------------------------


def test_parse_repo_url_basic():
    assert _parse_repo_url("https://github.com/narendranathe/tailor-resume") == (
        "narendranathe",
        "tailor-resume",
    )


def test_parse_repo_url_trailing_slash():
    assert _parse_repo_url("https://github.com/narendranathe/tailor-resume/") == (
        "narendranathe",
        "tailor-resume",
    )


def test_parse_repo_url_dot_git_suffix():
    assert _parse_repo_url("https://github.com/narendranathe/tailor-resume.git") == (
        "narendranathe",
        "tailor-resume",
    )


def test_parse_repo_url_no_scheme():
    assert _parse_repo_url("github.com/foo/bar") == ("foo", "bar")


def test_parse_repo_url_www():
    assert _parse_repo_url("https://www.github.com/foo/bar") == ("foo", "bar")


def test_parse_repo_url_http_scheme():
    assert _parse_repo_url("http://github.com/foo/bar") == ("foo", "bar")


def test_parse_repo_url_invalid_host():
    assert _parse_repo_url("https://gitlab.com/foo/bar") is None


def test_parse_repo_url_missing_repo():
    assert _parse_repo_url("https://github.com/foo") is None


def test_parse_repo_url_empty():
    assert _parse_repo_url("") is None


def test_parse_repo_url_non_string():
    assert _parse_repo_url(None) is None  # type: ignore[arg-type]


# --- _bullets_from_readme ----------------------------------------------------


def test_bullets_from_readme_handles_multiple_markers():
    text = "- one\n* two\n+ three\n1. four\n"
    out = _bullets_from_readme(text)
    assert out == ["one", "two", "three", "four"]


def test_bullets_from_readme_strips_emphasis():
    out = _bullets_from_readme("- **bold** and _italic_ and `code` text")
    assert out == ["bold and italic and code text"]


def test_bullets_from_readme_skips_non_bullets():
    out = _bullets_from_readme("Just a paragraph.\nAnother line.\n")
    assert out == []


# --- ingest_repo: happy path -------------------------------------------------


def test_ingest_repo_happy_path(monkeypatch):
    meta = {
        "name": "tailor-resume",
        "full_name": "narendranathe/tailor-resume",
        "description": "ATS-optimized resume tailoring tool built with Python.",
        "language": "Python",
        "topics": ["fastapi", "resume", "ats"],
        "default_branch": "main",
    }
    readme_payload = {"content": _b64(_README_FOR_INGEST), "encoding": "base64"}

    monkeypatch.setattr(
        "urllib.request.urlopen", _make_urlopen(meta, readme_payload)
    )

    bullets = ingest_repo("https://github.com/narendranathe/tailor-resume")
    assert isinstance(bullets, list)
    assert len(bullets) >= 2  # description + at least one README bullet
    # Description bullet leads
    assert bullets[0]["text"].startswith("ATS-optimized")
    assert bullets[0]["evidence_source"] == "github"
    assert bullets[0]["confidence"] == "medium"
    # All bullets share the issue-spec shape
    for b in bullets:
        assert set(b.keys()) >= {"text", "metrics", "tools", "evidence_source", "confidence"}
        assert b["evidence_source"] == "github"
        assert b["confidence"] == "medium"
    # README bullets came through parse_blob (tools should be detected)
    texts = [b["text"] for b in bullets]
    assert any("80%" in t for t in texts)


def test_ingest_repo_no_readme_returns_description_only(monkeypatch):
    meta = {
        "name": "no-readme-repo",
        "full_name": "owner/no-readme-repo",
        "description": "A small CLI tool.",
        "language": "Python",
        "topics": [],
    }
    # readme_payload=None makes the fake raise 404 for /readme
    monkeypatch.setattr(
        "urllib.request.urlopen", _make_urlopen(meta, readme_payload=None)
    )

    bullets = ingest_repo("https://github.com/owner/no-readme-repo")
    assert len(bullets) == 1
    assert bullets[0]["text"] == "A small CLI tool."
    assert bullets[0]["evidence_source"] == "github"
    assert bullets[0]["confidence"] == "medium"
    # Tools include the repo language
    assert "Python" in bullets[0]["tools"]


def test_ingest_repo_no_readme_no_description_returns_empty(monkeypatch):
    meta = {
        "name": "bare",
        "full_name": "owner/bare",
        "description": None,
        "language": None,
        "topics": [],
    }
    monkeypatch.setattr(
        "urllib.request.urlopen", _make_urlopen(meta, readme_payload=None)
    )

    assert ingest_repo("https://github.com/owner/bare") == []


def test_ingest_repo_invalid_url_returns_empty(caplog):
    with caplog.at_level("WARNING", logger="github_ingester"):
        result = ingest_repo("not-a-url")
    assert result == []
    assert any("invalid" in rec.message.lower() for rec in caplog.records)


def test_ingest_repo_http_error_returns_empty(monkeypatch, caplog):
    def boom(req, timeout=15):
        raise urllib.error.HTTPError(req.full_url, 500, "Server Error", hdrs=None, fp=None)

    monkeypatch.setattr("urllib.request.urlopen", boom)
    with caplog.at_level("WARNING", logger="github_ingester"):
        result = ingest_repo("https://github.com/foo/bar")
    assert result == []
    assert any("HTTP" in rec.message for rec in caplog.records)


def test_ingest_repo_url_error_returns_empty(monkeypatch):
    def boom(req, timeout=15):
        raise urllib.error.URLError("dns failure")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    assert ingest_repo("https://github.com/foo/bar") == []


def test_ingest_repo_malformed_json_returns_empty(monkeypatch):
    def fake_urlopen(req, timeout=15):
        return _FakeResp(b"{not-valid-json")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    assert ingest_repo("https://github.com/foo/bar") == []


def test_ingest_repo_trailing_slash_parses(monkeypatch):
    meta = {"name": "r", "full_name": "o/r", "description": "desc", "topics": []}
    monkeypatch.setattr(
        "urllib.request.urlopen", _make_urlopen(meta, readme_payload=None)
    )
    bullets = ingest_repo("https://github.com/o/r/")
    assert len(bullets) == 1
    assert bullets[0]["text"] == "desc"


def test_ingest_repo_dot_git_parses(monkeypatch):
    meta = {"name": "r", "full_name": "o/r", "description": "desc", "topics": []}
    monkeypatch.setattr(
        "urllib.request.urlopen", _make_urlopen(meta, readme_payload=None)
    )
    bullets = ingest_repo("https://github.com/o/r.git")
    assert len(bullets) == 1


def test_ingest_repo_token_adds_authorization_header(monkeypatch):
    meta = {"name": "r", "full_name": "o/r", "description": "desc", "topics": []}
    capture = {}
    monkeypatch.setattr(
        "urllib.request.urlopen",
        _make_urlopen(meta, readme_payload=None, capture=capture),
    )

    ingest_repo("https://github.com/o/r", token="ghp_secret123")

    # Headers are normalised to title-case by urllib.
    auth_values = [
        v
        for call in capture["calls"]
        for k, v in call["headers"].items()
        if k.lower() == "authorization"
    ]
    assert auth_values
    assert all(v == "Bearer ghp_secret123" for v in auth_values)


def test_ingest_repo_user_agent_always_set(monkeypatch):
    meta = {"name": "r", "full_name": "o/r", "description": "desc", "topics": []}
    capture = {}
    monkeypatch.setattr(
        "urllib.request.urlopen",
        _make_urlopen(meta, readme_payload=None, capture=capture),
    )

    ingest_repo("https://github.com/o/r")

    ua_values = [
        v
        for call in capture["calls"]
        for k, v in call["headers"].items()
        if k.lower() == "user-agent"
    ]
    assert ua_values, "Expected User-Agent header on every request"
    assert all("tailor-resume" in v for v in ua_values)


def test_ingest_repo_no_token_omits_authorization(monkeypatch):
    meta = {"name": "r", "full_name": "o/r", "description": "desc", "topics": []}
    capture = {}
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(
        "urllib.request.urlopen",
        _make_urlopen(meta, readme_payload=None, capture=capture),
    )

    ingest_repo("https://github.com/o/r")

    for call in capture["calls"]:
        keys = {k.lower() for k in call["headers"].keys()}
        assert "authorization" not in keys


def test_ingest_repo_readme_with_no_bullets_falls_back_to_description(monkeypatch):
    meta = {
        "name": "r",
        "full_name": "o/r",
        "description": "Plain text repo.",
        "topics": [],
    }
    readme = {"content": _b64("Just a paragraph, no bullets here.\nAnother line.")}
    monkeypatch.setattr(
        "urllib.request.urlopen", _make_urlopen(meta, readme_payload=readme)
    )
    bullets = ingest_repo("https://github.com/o/r")
    assert len(bullets) == 1
    assert bullets[0]["text"] == "Plain text repo."


def test_ingest_repo_readme_undecodable_base64(monkeypatch):
    meta = {
        "name": "r",
        "full_name": "o/r",
        "description": "desc here",
        "topics": [],
    }
    readme = {"content": "!!!not-base64!!!"}
    monkeypatch.setattr(
        "urllib.request.urlopen", _make_urlopen(meta, readme_payload=readme)
    )
    bullets = ingest_repo("https://github.com/o/r")
    # README decode failed silently → still get the description bullet
    assert len(bullets) == 1
    assert bullets[0]["text"] == "desc here"


def test_ingest_repo_readme_missing_content_key(monkeypatch):
    meta = {"name": "r", "full_name": "o/r", "description": "desc here", "topics": []}
    readme = {"encoding": "base64"}  # no content
    monkeypatch.setattr(
        "urllib.request.urlopen", _make_urlopen(meta, readme_payload=readme)
    )
    bullets = ingest_repo("https://github.com/o/r")
    assert len(bullets) == 1
    assert bullets[0]["text"] == "desc here"


def test_ingest_repo_topics_become_tools_on_description(monkeypatch):
    meta = {
        "name": "r",
        "full_name": "o/r",
        "description": "A toolkit",
        "language": "Python",
        "topics": ["fastapi", "ats"],
    }
    monkeypatch.setattr(
        "urllib.request.urlopen", _make_urlopen(meta, readme_payload=None)
    )
    bullets = ingest_repo("https://github.com/o/r")
    assert "Python" in bullets[0]["tools"]
    assert "fastapi" in bullets[0]["tools"]
    assert "ats" in bullets[0]["tools"]


# --- ingest_repo_project (convenience wrapper) -------------------------------


def test_ingest_repo_project_extracts_repo_name(monkeypatch):
    meta = {
        "name": "tailor-resume",
        "full_name": "narendranathe/tailor-resume",
        "description": "ATS-optimized resume tailoring tool.",
        "topics": [],
    }
    monkeypatch.setattr(
        "urllib.request.urlopen", _make_urlopen(meta, readme_payload=None)
    )
    project = ingest_repo_project("https://github.com/narendranathe/tailor-resume")
    assert project is not None
    assert project["name"] == "tailor-resume"
    assert project["source"] == "github"
    assert project["url"] == "https://github.com/narendranathe/tailor-resume"
    assert len(project["bullets"]) == 1


def test_ingest_repo_project_invalid_url_returns_none():
    assert ingest_repo_project("not-a-github-url") is None
