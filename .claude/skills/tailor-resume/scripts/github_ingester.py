"""
github_ingester.py
Fetch GitHub repos and extract project bullets for resume injection.

Architecture:
  - Reads public repos (or private with GITHUB_TOKEN) via GitHub REST API v3
  - Extracts: repo description, README highlights, topics, language, stars
  - Converts each repo to a structured project entry compatible with profile_extractor output
  - Deduplicates by repo full_name; skips forks by default

Auth:
  GITHUB_TOKEN env var (fine-grained PAT, contents:read or classic).
  If absent: public repos only (60 req/hr). With token: 5000 req/hr.

Output shape (matches profile_extractor ProjectEntry):
  {
    "name": str,
    "description": str,
    "bullets": [{"text": str, "metrics": [], "tools": [], "evidence_source": "github"}],
    "tools": [str],        # repo topics + primary language
    "url": str,
    "stars": int,
    "source": "github"
  }
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

_SCRIPTS = Path(__file__).parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

_GITHUB_API = "https://api.github.com"
_DEFAULT_PER_PAGE = 30
_README_MAX_CHARS = 2000


def _token() -> Optional[str]:
    return os.getenv("GITHUB_TOKEN")


def _headers() -> Dict[str, str]:
    h = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "tailor-resume/2.0",
    }
    tok = _token()
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    return h


def _get(url: str) -> Optional[Dict]:
    """GET a GitHub API URL, return parsed JSON or None on error."""
    req = urllib.request.Request(url, headers=_headers())
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:120] if e.fp else ""
        print(f"[github_ingester] HTTP {e.code}: {body}")
        return None
    except Exception as e:
        print(f"[github_ingester] Error: {e}")
        return None


def _fetch_readme(owner: str, repo: str) -> str:
    """Return first _README_MAX_CHARS chars of README content, or empty string."""
    url = f"{_GITHUB_API}/repos/{owner}/{repo}/readme"
    result = _get(url)
    if not result or "content" not in result:
        return ""
    try:
        import base64
        raw = base64.b64decode(result["content"].replace("\n", "")).decode(errors="replace")
        return raw[:_README_MAX_CHARS]
    except Exception:
        return ""


def _extract_readme_bullets(readme: str) -> List[str]:
    """Pull first 3 bullet-like lines from README as potential project highlights."""
    bullets = []
    for line in readme.splitlines():
        line = line.strip()
        # Match markdown bullets or numbered lists
        m = re.match(r"^[-*•]\s+(.+)$", line) or re.match(r"^\d+\.\s+(.+)$", line)
        if m:
            text = m.group(1).strip()
            if len(text) > 15:  # skip trivial short lines
                bullets.append(text)
        if len(bullets) >= 3:
            break
    return bullets


def _repo_to_project(repo: Dict, readme: str = "") -> Dict:
    """Convert a GitHub repo dict to a profile project entry."""
    name = repo.get("name", "")
    full_name = repo.get("full_name", "")
    description = repo.get("description") or ""
    language = repo.get("language") or ""
    stars = repo.get("stargazers_count", 0)
    topics: List[str] = repo.get("topics", [])
    url = repo.get("html_url", f"https://github.com/{full_name}")

    # Build bullets: description + README highlights
    bullets: List[Dict] = []
    if description:
        bullets.append({
            "text": description,
            "metrics": [],
            "tools": [],
            "evidence_source": "github",
            "confidence": "high",
        })

    for b in _extract_readme_bullets(readme):
        bullets.append({
            "text": b,
            "metrics": _extract_metrics(b),
            "tools": [],
            "evidence_source": "github_readme",
            "confidence": "medium",
        })

    if stars >= 10:
        bullets.append({
            "text": f"Open-source project with {stars} GitHub stars.",
            "metrics": [str(stars)],
            "tools": [],
            "evidence_source": "github",
            "confidence": "high",
        })

    tools = list(topics)
    if language and language not in tools:
        tools.insert(0, language)

    return {
        "name": name,
        "description": description,
        "bullets": bullets,
        "tools": tools,
        "url": url,
        "stars": stars,
        "source": "github",
        "full_name": full_name,
    }


def _extract_metrics(text: str) -> List[str]:
    """Extract numeric metrics (%, x, numbers) from text."""
    return re.findall(r"\d+(?:\.\d+)?(?:%|x|X|\s*(?:ms|s|hr|hrs|min|mins|k|M|B))", text)


def fetch_user_repos(
    username: str,
    include_forks: bool = False,
    limit: int = 20,
    fetch_readmes: bool = True,
) -> List[Dict]:
    """
    Fetch public repos for a GitHub user and return profile project entries.

    Args:
        username: GitHub username or org name.
        include_forks: Include forked repositories (default False).
        limit: Max repos to return (default 20).
        fetch_readmes: Fetch README for each repo (slower but richer bullets).

    Returns:
        List of project dicts compatible with profile_extractor output.
    """
    per_page = min(limit, 100)
    url = f"{_GITHUB_API}/users/{username}/repos?sort=pushed&per_page={per_page}&type=owner"
    repos = _get(url)
    if not isinstance(repos, list):
        print(f"[github_ingester] Could not fetch repos for '{username}'")
        return []

    projects = []
    seen = set()
    for repo in repos:
        if len(projects) >= limit:
            break
        full_name = repo.get("full_name", "")
        if full_name in seen:
            continue
        seen.add(full_name)
        if not include_forks and repo.get("fork"):
            continue

        readme = ""
        if fetch_readmes:
            owner, rname = full_name.split("/", 1) if "/" in full_name else (username, full_name)
            readme = _fetch_readme(owner, rname)

        projects.append(_repo_to_project(repo, readme))

    return projects


def fetch_repo(full_name: str, fetch_readme: bool = True) -> Optional[Dict]:
    """
    Fetch a single repo by full_name (e.g. 'narendranathe/autoapply-ai').

    Returns a project dict or None on error.
    """
    url = f"{_GITHUB_API}/repos/{full_name}"
    repo = _get(url)
    if not repo or "name" not in repo:
        return None
    readme = ""
    if fetch_readme:
        owner, rname = full_name.split("/", 1)
        readme = _fetch_readme(owner, rname)
    return _repo_to_project(repo, readme)


def inject_github_projects(
    profile: Dict,
    username: str,
    limit: int = 10,
    fetch_readmes: bool = True,
) -> Dict:
    """
    Fetch GitHub repos for `username` and merge them into `profile["projects"]`.

    Deduplicates by project name (case-insensitive). Existing projects take precedence.
    Returns the updated profile dict (mutates in place).
    """
    existing_names = {p.get("name", "").lower() for p in profile.get("projects", [])}

    github_projects = fetch_user_repos(
        username, include_forks=False, limit=limit, fetch_readmes=fetch_readmes
    )

    new_projects = [p for p in github_projects if p["name"].lower() not in existing_names]

    if "projects" not in profile:
        profile["projects"] = []
    profile["projects"].extend(new_projects)

    return profile


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Fetch GitHub repos as resume project bullets.")
    parser.add_argument("--username", required=True, help="GitHub username")
    parser.add_argument("--limit", type=int, default=10, help="Max repos (default 10)")
    parser.add_argument("--no-readmes", action="store_true", help="Skip README fetching")
    parser.add_argument("--output", help="Write JSON to file instead of stdout")
    args = parser.parse_args()

    projects = fetch_user_repos(
        args.username,
        limit=args.limit,
        fetch_readmes=not args.no_readmes,
    )
    out = json.dumps(projects, indent=2)
    if args.output:
        Path(args.output).write_text(out, encoding="utf-8")
        print(f"[github_ingester] Wrote {len(projects)} projects to {args.output}")
    else:
        print(out)
