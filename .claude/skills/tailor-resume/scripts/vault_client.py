"""
vault_client.py
Store and retrieve resume versions in the narendranathe/resume-vault GitHub repo.

Architecture:
  - One private repo: narendranathe/resume-vault
  - One branch per user: vault/{user_id}
  - Two files per generation committed atomically:
      {Company}_{Role}_{YYYYMMDD_HHMMSS}.tex       <- LaTeX source
      {Company}_{Role}_{YYYYMMDD_HHMMSS}.meta.json <- ATS score, JD hash, engine used

Auth:
  GITHUB_VAULT_TOKEN env var (fine-grained PAT, contents:write on resume-vault repo).
  If token absent: push_version returns None silently (non-blocking failure).

Naming convention (from autoapply-ai):
  version_tag      = "{FirstName}_{Company}_{Role}[_{JobID}]"
  filename pattern = "{Company}_{Role}_{YYYYMMDD_HHMMSS}"
  recruiter dl     = always "{FirstName}.pdf" at download (not enforced here)
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

_SCRIPTS = Path(__file__).parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

VAULT_REPO = "narendranathe/resume-vault"
VAULT_BRANCH_PREFIX = "vault/"


@dataclass
class VaultEntry:
    version_tag: str
    filename: str
    branch: str
    company: str
    role: str
    ats_score: Optional[float]
    committed_at: str
    github_path: str
    commit_sha: str = ""


def _token() -> Optional[str]:
    return os.getenv("GITHUB_VAULT_TOKEN")


def _api(path: str, method: str = "GET", body: Optional[Dict] = None) -> Optional[Dict]:
    """Make a GitHub REST API call. Returns parsed JSON or None on error."""
    token = _token()
    if not token:
        return None
    url = f"https://api.github.com/repos/{VAULT_REPO}{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "tailor-resume/2.0")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        body_bytes = e.read() if e.fp else b""
        body_text = body_bytes.decode(errors="replace")[:200]
        print(f"[vault_client] HTTP {e.code}: {body_text}")
        return None
    except Exception as e:
        print(f"[vault_client] Error: {e}")
        return None


def _branch_name(user_id: str) -> str:
    uid = user_id.strip() or "anonymous"
    return f"{VAULT_BRANCH_PREFIX}{uid}"


def _ensure_branch(user_id: str) -> bool:
    """Create vault/{user_id} from main if it doesn't exist. Returns True on success."""
    branch = _branch_name(user_id)
    existing = _api(f"/git/ref/heads/{branch}")
    if existing and "object" in existing:
        return True
    # Try main, then master
    for base in ("main", "master"):
        ref = _api(f"/git/ref/heads/{base}")
        if ref and "object" in ref:
            sha = ref["object"]["sha"]
            _api("/git/refs", method="POST", body={"ref": f"refs/heads/{branch}", "sha": sha})
            return True
    print(f"[vault_client] Cannot find main/master in {VAULT_REPO}")
    return False


def _file_sha(path: str, branch: str) -> Optional[str]:
    """Get the blob SHA of an existing file (needed to update rather than create)."""
    result = _api(f"/contents/{path}?ref={branch}")
    if result and "sha" in result:
        return result["sha"]
    return None


def push_version(
    user_id: str,
    company: str,
    role: str,
    tex_content: str,
    metadata: Dict,
    first_name: str = "",
) -> Optional[VaultEntry]:
    """
    Commit .tex + .meta.json to vault/{user_id} branch.

    Returns VaultEntry on success, None if token absent or push fails.
    Non-blocking: caller should handle None gracefully.
    """
    if not _token():
        print("[vault_client] GITHUB_VAULT_TOKEN not set — skipping vault push.")
        return None

    branch = _branch_name(user_id)
    if not _ensure_branch(user_id):
        return None

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    safe_company = company.replace(" ", "").replace("/", "-")[:30]
    safe_role = role.replace(" ", "").replace("/", "-")[:30]
    base_name = f"{safe_company}_{safe_role}_{ts}"

    if first_name:
        version_tag = f"{first_name}_{safe_company}_{safe_role}"
    else:
        version_tag = f"{safe_company}_{safe_role}"

    content_hash = hashlib.sha256(tex_content.encode()).hexdigest()[:12]

    # Upload .tex
    tex_path = f"{base_name}.tex"
    tex_b64 = base64.b64encode(tex_content.encode()).decode()
    tex_sha = _file_sha(tex_path, branch)
    tex_body: Dict = {
        "message": f"Add resume: {version_tag}",
        "content": tex_b64,
        "branch": branch,
    }
    if tex_sha:
        tex_body["sha"] = tex_sha

    tex_result = _api(f"/contents/{tex_path}", method="PUT", body=tex_body)
    commit_sha = ""
    if tex_result and "commit" in tex_result:
        commit_sha = tex_result["commit"]["sha"]

    # Upload .meta.json
    meta = {
        "version_tag": version_tag,
        "committed_at": ts,
        "content_hash": content_hash,
        **metadata,
    }
    meta_path = f"{base_name}.meta.json"
    meta_b64 = base64.b64encode(json.dumps(meta, indent=2).encode()).decode()
    meta_sha = _file_sha(meta_path, branch)
    meta_body: Dict = {
        "message": f"Add meta: {version_tag}",
        "content": meta_b64,
        "branch": branch,
    }
    if meta_sha:
        meta_body["sha"] = meta_sha
    _api(f"/contents/{meta_path}", method="PUT", body=meta_body)

    return VaultEntry(
        version_tag=version_tag,
        filename=base_name,
        branch=branch,
        company=company,
        role=role,
        ats_score=metadata.get("ats_score"),
        committed_at=ts,
        github_path=tex_path,
        commit_sha=commit_sha,
    )


def list_versions(user_id: str, limit: int = 20) -> List[VaultEntry]:
    """List resume versions for a user, sorted by filename (timestamp) descending."""
    if not _token():
        return []
    branch = _branch_name(user_id)
    tree = _api(f"/git/trees/{branch}?recursive=1")
    if not tree or "tree" not in tree:
        return []

    tex_files = [f for f in tree["tree"] if f["path"].endswith(".tex")]
    tex_files.sort(key=lambda f: f["path"], reverse=True)

    entries = []
    for f in tex_files[:limit]:
        path = f["path"]
        name = path[: -len(".tex")]
        # Parse Company_Role_YYYYMMDD_HHMMSS
        parts = name.rsplit("_", 2)
        ts_part = "_".join(parts[-2:]) if len(parts) >= 3 else ""
        company_role = parts[0] if len(parts) >= 3 else name

        entries.append(
            VaultEntry(
                version_tag=company_role,
                filename=name,
                branch=branch,
                company="",
                role="",
                ats_score=None,
                committed_at=ts_part,
                github_path=path,
                commit_sha=f.get("sha", ""),
            )
        )
    return entries


def get_version(user_id: str, filename: str) -> Optional[str]:
    """Return .tex content of a specific version. Adds .tex if missing."""
    if not _token():
        return None
    branch = _branch_name(user_id)
    path = filename if filename.endswith(".tex") else f"{filename}.tex"
    result = _api(f"/contents/{path}?ref={branch}")
    if not result or "content" not in result:
        return None
    try:
        return base64.b64decode(result["content"].replace("\n", "")).decode()
    except Exception:
        return None


def delete_branch(user_id: str) -> None:
    """Delete vault/{user_id} branch (user data erasure). Irreversible."""
    if not _token():
        print("[vault_client] GITHUB_VAULT_TOKEN not set — cannot delete branch.")
        return
    branch = _branch_name(user_id)
    _api(f"/git/refs/heads/{branch}", method="DELETE")
    print(f"[vault_client] Deleted branch: {branch}")
