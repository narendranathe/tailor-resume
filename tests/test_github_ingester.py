"""Tests for github_ingester.py — GitHub repo ingestion for resume projects."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / ".claude" / "skills" / "tailor-resume" / "scripts"))

from github_ingester import (  # noqa: E402
    _extract_metrics,
    _extract_readme_bullets,
    _repo_to_project,
    fetch_repo,
    fetch_user_repos,
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
