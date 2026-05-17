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

import base64
import json
import logging
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_LOG = logging.getLogger(__name__)

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
# Issue #66: ingest_repo(url, token) — flat bullet list from a single repo URL
# ---------------------------------------------------------------------------

_REPO_URL_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?github\.com/([^/\s]+)/([^/\s]+?)(?:\.git)?/?$",
    re.IGNORECASE,
)


def _parse_repo_url(url: str) -> Optional[Tuple[str, str]]:
    """Extract (owner, repo) from a GitHub URL.

    Handles trailing slashes, .git suffix, http/https, and optional www.
    Returns None for unparseable input.
    """
    if not url or not isinstance(url, str):
        return None
    m = _REPO_URL_RE.match(url.strip())
    if not m:
        return None
    owner, repo = m.group(1), m.group(2)
    if not owner or not repo:
        return None
    return owner, repo


def _ingest_headers(token: Optional[str] = None) -> Dict[str, str]:
    """Build headers for the ingest_repo API path (separate from module _headers
    so that the explicit `token` arg always wins over the GITHUB_TOKEN env var).
    """
    h = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "tailor-resume/2.0",
    }
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _api_get(url: str, token: Optional[str] = None) -> Optional[Dict]:
    """GET a GitHub API URL with the User-Agent + optional Bearer auth.

    Returns parsed JSON or None on any error (HTTP, URL, decode).
    """
    req = urllib.request.Request(url, headers=_ingest_headers(token))
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        _LOG.warning("github_ingester: HTTP %s fetching %s", exc.code, url)
        return None
    except urllib.error.URLError as exc:
        _LOG.warning("github_ingester: URL error %s fetching %s", exc.reason, url)
        return None
    except Exception as exc:  # pragma: no cover - defensive
        _LOG.warning("github_ingester: unexpected error fetching %s: %s", url, exc)
        return None

    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (ValueError, TypeError) as exc:
        _LOG.warning("github_ingester: malformed JSON from %s: %s", url, exc)
        return None


def _fetch_repo_meta(owner: str, repo: str, token: Optional[str] = None) -> Optional[Dict]:
    return _api_get(f"{_GITHUB_API}/repos/{owner}/{repo}", token)


def _fetch_repo_readme(owner: str, repo: str, token: Optional[str] = None) -> str:
    """Return UTF-8 decoded README content or empty string if absent/error."""
    data = _api_get(f"{_GITHUB_API}/repos/{owner}/{repo}/readme", token)
    if not data or not isinstance(data, dict):
        return ""
    encoded = data.get("content")
    if not encoded or not isinstance(encoded, str):
        return ""
    try:
        return base64.b64decode(encoded.replace("\n", "")).decode("utf-8", errors="replace")
    except (ValueError, TypeError, base64.binascii.Error) as exc:
        _LOG.warning("github_ingester: failed to decode README: %s", exc)
        return ""


def _bullets_from_readme(readme: str) -> List[str]:
    """Pull all markdown bullet lines from a README (no cap, no length filter).

    Used as the input to parse_blob — let parse_blob's downstream consumers
    decide which bullets matter.
    """
    out: List[str] = []
    for raw in readme.splitlines():
        line = raw.strip()
        m = re.match(r"^[-*+•]\s+(.+)$", line) or re.match(r"^\d+\.\s+(.+)$", line)
        if not m:
            continue
        text = m.group(1).strip()
        # Strip surrounding markdown emphasis markers but keep the content.
        text = re.sub(r"[`*_]+", "", text).strip()
        if text:
            out.append(text)
    return out


def _bullet_to_dict(bullet) -> Dict:
    """Convert a profile_extractor Bullet dataclass to the issue-spec dict shape."""
    return {
        "text": getattr(bullet, "text", ""),
        "metrics": list(getattr(bullet, "metrics", []) or []),
        "tools": list(getattr(bullet, "tools", []) or []),
        "evidence_source": "github",
        "confidence": "medium",
    }


def _description_bullet(description: str, tools: Optional[List[str]] = None) -> Dict:
    """Build a fallback bullet from the repo description alone."""
    try:
        from text_utils import extract_metrics as _xm, extract_tools as _xt
        metrics = _xm(description)
        tool_list = list(tools or []) + _xt(description)
        # Dedupe while preserving order.
        seen = set()
        deduped_tools = []
        for t in tool_list:
            if t not in seen:
                seen.add(t)
                deduped_tools.append(t)
        tool_list = deduped_tools
    except Exception:  # pragma: no cover - defensive
        metrics = []
        tool_list = list(tools or [])
    return {
        "text": description,
        "metrics": metrics,
        "tools": tool_list,
        "evidence_source": "github",
        "confidence": "medium",
    }


def ingest_repo(url: str, token: Optional[str] = None) -> List[Dict]:
    """Fetch README + description for a GitHub repo URL and return project bullets.

    Public repos work without ``token``; supplying a PAT raises the rate limit
    and (in v3) will permit private repos.

    Returns a list of dicts shaped like::

        {"text": ..., "metrics": [...], "tools": [...],
         "evidence_source": "github", "confidence": "medium"}

    Behaviour:
        * Invalid URL → ``[]`` with a logged warning.
        * No README and no description → ``[]``.
        * No README but description present → single description-only bullet.
        * Any HTTP/URL/JSON error → ``[]`` with a logged warning.
        * Never raises ``urllib`` errors to the caller.
    """
    parsed = _parse_repo_url(url)
    if parsed is None:
        _LOG.warning("github_ingester: invalid GitHub repo URL: %r", url)
        return []
    owner, repo = parsed

    meta = _fetch_repo_meta(owner, repo, token=token)
    if not isinstance(meta, dict):
        # Network/HTTP failure already logged in _api_get.
        return []

    description = (meta.get("description") or "").strip()
    language = (meta.get("language") or "").strip()
    topics = meta.get("topics") or []
    if not isinstance(topics, list):
        topics = []
    base_tools: List[str] = []
    if language:
        base_tools.append(language)
    for t in topics:
        if isinstance(t, str) and t and t not in base_tools:
            base_tools.append(t)

    readme = _fetch_repo_readme(owner, repo, token=token)

    # Extract bullet candidates from the README and feed them — together with
    # the description as a synthetic header bullet — through parse_blob using
    # the repo name as the "company" so the lines get associated with a role.
    readme_bullets = _bullets_from_readme(readme) if readme else []

    bullets: List[Dict] = []

    if readme_bullets:
        # Construct a synthetic blob parse_blob can consume.
        try:
            from profile_extractor import parse_blob
            blob_lines = [f"Company: {repo}"]
            blob_lines.extend(f"- {b}" for b in readme_bullets)
            profile = parse_blob("\n".join(blob_lines), source="github")
            for role in profile.experience:
                for b in role.bullets:
                    bullets.append(_bullet_to_dict(b))
        except Exception as exc:  # pragma: no cover - defensive
            _LOG.warning("github_ingester: parse_blob failed: %s", exc)

    if description:
        # Prepend the description bullet so it leads the list.
        bullets.insert(0, _description_bullet(description, tools=base_tools))

    if not bullets:
        return []

    return bullets


def ingest_repo_project(url: str, token: Optional[str] = None) -> Optional[Dict]:
    """Convenience wrapper that returns a *project entry* dict (with title
    extracted from the repo name) ready to append to ``profile['projects']``.

    Returns None for invalid URLs or fetch errors. Returns a project dict with
    an empty ``bullets`` list if the repo has neither description nor README.
    """
    parsed = _parse_repo_url(url)
    if parsed is None:
        _LOG.warning("github_ingester: invalid GitHub repo URL: %r", url)
        return None
    _owner, repo_name = parsed
    bullets = ingest_repo(url, token=token)
    return {
        "name": repo_name,
        "bullets": bullets,
        "source": "github",
        "url": url,
    }


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
