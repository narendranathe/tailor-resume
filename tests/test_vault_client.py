"""Tests for vault_client.py — GitHub resume vault operations."""
from __future__ import annotations

import base64
import io
import json
import sys
import urllib.error
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / ".claude" / "skills" / "tailor-resume" / "scripts"))

from vault_client import (  # noqa: E402
    VaultEntry,
    _api,
    _branch_name,
    _ensure_branch,
    _file_sha,
    delete_branch,
    get_version,
    list_versions,
    push_version,
)

_TEX = r"\documentclass{article}\begin{document}Hello\end{document}"
_META = {"ats_score": 82, "jd_hash": "abc123", "engine": "formula"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _b64(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


# ---------------------------------------------------------------------------
# push_version
# ---------------------------------------------------------------------------


def test_push_version_no_token_returns_none():
    """No token → returns None silently."""
    with patch.dict("os.environ", {}, clear=True):
        result = push_version("user1", "Acme", "Engineer", _TEX, _META)
    assert result is None


def test_push_version_returns_vault_entry():
    """Happy path: _api calls succeed → VaultEntry returned."""
    branch_ref = {"object": {"sha": "deadbeef"}}
    tex_commit = {"commit": {"sha": "abc111"}}
    meta_commit = {"commit": {"sha": "abc222"}}

    with patch.dict("os.environ", {"GITHUB_VAULT_TOKEN": "tok"}):
        with patch("vault_client._api") as mock_api:
            # _ensure_branch checks existing, finds it; push_version calls _api for files
            mock_api.side_effect = [
                branch_ref,   # _ensure_branch: GET existing branch → found
                None,         # _file_sha(.tex) → not found
                tex_commit,   # PUT .tex
                None,         # _file_sha(.meta.json) → not found
                meta_commit,  # PUT .meta.json
            ]
            entry = push_version("user1", "Acme", "DataEngineer", _TEX, _META, first_name="Jane")

    assert entry is not None
    assert isinstance(entry, VaultEntry)
    assert entry.company == "Acme"
    assert entry.role == "DataEngineer"
    assert entry.version_tag.startswith("Jane_Acme_DataEngineer")
    assert entry.branch == "vault/user1"
    assert entry.github_path.endswith(".tex")
    assert entry.ats_score == 82


def test_push_version_creates_branch_when_missing():
    """_ensure_branch falls back to main SHA when branch doesn't exist."""
    main_ref = {"object": {"sha": "mainsha"}}
    tex_commit = {"commit": {"sha": "c1"}}

    with patch.dict("os.environ", {"GITHUB_VAULT_TOKEN": "tok"}):
        with patch("vault_client._api") as mock_api:
            mock_api.side_effect = [
                None,         # check existing branch → not found
                main_ref,     # check main → found
                {"ref": "refs/heads/vault/u2"},  # create branch
                None,         # _file_sha .tex
                tex_commit,   # PUT .tex
                None,         # _file_sha .meta
                {"commit": {"sha": "c2"}},  # PUT .meta
            ]
            entry = push_version("u2", "Stripe", "MLEngineer", _TEX, _META)

    assert entry is not None
    assert entry.branch == "vault/u2"


def test_push_version_without_first_name():
    """version_tag omits first name when not provided."""
    with patch.dict("os.environ", {"GITHUB_VAULT_TOKEN": "tok"}):
        with patch("vault_client._api") as mock_api:
            mock_api.side_effect = [
                {"object": {"sha": "sha1"}},  # branch exists
                None,
                {"commit": {"sha": "c1"}},
                None,
                {"commit": {"sha": "c2"}},
            ]
            entry = push_version("u3", "Google", "SRE", _TEX, {})

    assert entry is not None
    assert entry.version_tag == "Google_SRE"


# ---------------------------------------------------------------------------
# list_versions
# ---------------------------------------------------------------------------


def test_list_versions_no_token_returns_empty():
    with patch.dict("os.environ", {}, clear=True):
        result = list_versions("user1")
    assert result == []


def test_list_versions_returns_sorted_entries():
    tree_response = {
        "tree": [
            {"path": "Acme_DE_20240201_120000.tex", "sha": "sha2"},
            {"path": "Acme_DE_20240301_090000.tex", "sha": "sha1"},
            {"path": "Acme_DE_20240201_120000.meta.json", "sha": "shaM"},
        ]
    }
    with patch.dict("os.environ", {"GITHUB_VAULT_TOKEN": "tok"}):
        with patch("vault_client._api", return_value=tree_response):
            entries = list_versions("user1")

    # .meta.json filtered out; sorted descending by filename
    assert len(entries) == 2
    assert entries[0].filename == "Acme_DE_20240301_090000"
    assert entries[1].filename == "Acme_DE_20240201_120000"


def test_list_versions_respects_limit():
    files = [{"path": f"Co_Role_2024010{i}_120000.tex", "sha": f"s{i}"} for i in range(1, 8)]
    tree_response = {"tree": files}
    with patch.dict("os.environ", {"GITHUB_VAULT_TOKEN": "tok"}):
        with patch("vault_client._api", return_value=tree_response):
            entries = list_versions("user1", limit=3)
    assert len(entries) == 3


# ---------------------------------------------------------------------------
# get_version
# ---------------------------------------------------------------------------


def test_get_version_no_token_returns_none():
    with patch.dict("os.environ", {}, clear=True):
        result = get_version("user1", "SomeCo_SWE_20240101_120000")
    assert result is None


def test_get_version_returns_decoded_tex():
    encoded = _b64(_TEX) + "\n"
    api_response = {"content": encoded}
    with patch.dict("os.environ", {"GITHUB_VAULT_TOKEN": "tok"}):
        with patch("vault_client._api", return_value=api_response):
            result = get_version("user1", "SomeCo_SWE_20240101_120000")
    assert result == _TEX


def test_get_version_adds_tex_extension():
    """Filename without .tex extension gets it appended."""
    encoded = _b64(_TEX)
    with patch.dict("os.environ", {"GITHUB_VAULT_TOKEN": "tok"}):
        with patch("vault_client._api", return_value={"content": encoded}) as mock_api:
            get_version("user1", "SomeCo_SWE_20240101_120000")
    called_path = mock_api.call_args[0][0]
    assert ".tex" in called_path


# ---------------------------------------------------------------------------
# delete_branch
# ---------------------------------------------------------------------------


def test_delete_branch_no_token_logs_and_returns():
    with patch.dict("os.environ", {}, clear=True):
        with patch("vault_client._api") as mock_api:
            delete_branch("user1")
    mock_api.assert_not_called()


def test_delete_branch_calls_delete():
    with patch.dict("os.environ", {"GITHUB_VAULT_TOKEN": "tok"}):
        with patch("vault_client._api") as mock_api:
            delete_branch("user1")
    mock_api.assert_called_once_with("/git/refs/heads/vault/user1", method="DELETE")


# ---------------------------------------------------------------------------
# _branch_name
# ---------------------------------------------------------------------------


def test_branch_name_strips_whitespace():
    assert _branch_name("  alice  ") == "vault/alice"


def test_branch_name_empty_uses_anonymous():
    assert _branch_name("") == "vault/anonymous"


# ---------------------------------------------------------------------------
# _api — exercises urllib.request.urlopen wrapper, error paths, token redaction
# ---------------------------------------------------------------------------


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


def test_api_no_token_returns_none(monkeypatch):
    monkeypatch.delenv("GITHUB_VAULT_TOKEN", raising=False)
    assert _api("/git/ref/heads/main") is None


def test_api_success_returns_parsed_json(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout=15):
        captured["url"] = req.full_url
        captured["method"] = req.get_method()
        captured["headers"] = dict(req.header_items())
        captured["data"] = req.data
        return _FakeResp({"ok": True})

    monkeypatch.setenv("GITHUB_VAULT_TOKEN", "ghp_secret_value_XYZ")
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    result = _api("/git/ref/heads/main")
    assert result == {"ok": True}
    assert captured["url"].endswith("/repos/narendranathe/resume-vault/git/ref/heads/main")
    assert captured["method"] == "GET"
    auth = {k.lower(): v for k, v in captured["headers"].items()}.get("authorization")
    assert auth == "Bearer ghp_secret_value_XYZ"


def test_api_empty_body_returns_empty_dict(monkeypatch):
    def fake_urlopen(req, timeout=15):
        return _FakeResp(b"")

    monkeypatch.setenv("GITHUB_VAULT_TOKEN", "tok")
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    assert _api("/whatever", method="DELETE") == {}


def test_api_post_serializes_json_body(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout=15):
        captured["data"] = req.data
        captured["method"] = req.get_method()
        return _FakeResp({"created": True})

    monkeypatch.setenv("GITHUB_VAULT_TOKEN", "tok")
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    body = {"ref": "refs/heads/vault/x", "sha": "abc"}
    _api("/git/refs", method="POST", body=body)
    assert captured["method"] == "POST"
    assert json.loads(captured["data"].decode()) == body


def test_api_http_error_returns_none_and_does_not_log_token(monkeypatch, capsys):
    def boom(req, timeout=15):
        raise urllib.error.HTTPError(
            req.full_url, 422, "Unprocessable", hdrs=None, fp=io.BytesIO(b"error body")
        )

    monkeypatch.setenv("GITHUB_VAULT_TOKEN", "ghp_super_secret_TOKEN_VALUE")
    monkeypatch.setattr("urllib.request.urlopen", boom)

    assert _api("/git/refs", method="POST", body={"ref": "x"}) is None
    captured = capsys.readouterr()
    assert "ghp_super_secret_TOKEN_VALUE" not in captured.out
    assert "ghp_super_secret_TOKEN_VALUE" not in captured.err
    assert "422" in captured.out


def test_api_http_error_no_fp_handles_gracefully(monkeypatch):
    def boom(req, timeout=15):
        raise urllib.error.HTTPError(req.full_url, 404, "Not Found", hdrs=None, fp=None)

    monkeypatch.setenv("GITHUB_VAULT_TOKEN", "tok")
    monkeypatch.setattr("urllib.request.urlopen", boom)
    assert _api("/contents/missing.tex") is None


def test_api_url_error_returns_none_and_does_not_log_token(monkeypatch, capsys):
    def boom(req, timeout=15):
        raise urllib.error.URLError("dns failure")

    monkeypatch.setenv("GITHUB_VAULT_TOKEN", "ghp_another_secret_TOKEN")
    monkeypatch.setattr("urllib.request.urlopen", boom)
    assert _api("/git/ref/heads/main") is None
    captured = capsys.readouterr()
    assert "ghp_another_secret_TOKEN" not in captured.out
    assert "ghp_another_secret_TOKEN" not in captured.err


# ---------------------------------------------------------------------------
# _ensure_branch — failure path when neither main nor master exist
# ---------------------------------------------------------------------------


def test_ensure_branch_returns_false_when_no_base_branch(capsys):
    with patch.dict("os.environ", {"GITHUB_VAULT_TOKEN": "tok"}):
        with patch("vault_client._api") as mock_api:
            mock_api.side_effect = [None, None, None]
            assert _ensure_branch("ghost") is False
    out = capsys.readouterr().out
    assert "Cannot find main/master" in out


def test_push_version_returns_none_when_ensure_branch_fails():
    with patch.dict("os.environ", {"GITHUB_VAULT_TOKEN": "tok"}):
        with patch("vault_client._api") as mock_api:
            mock_api.side_effect = [None, None, None]
            entry = push_version("u9", "Acme", "DE", _TEX, _META)
    assert entry is None


# ---------------------------------------------------------------------------
# _file_sha — covers update path (existing file)
# ---------------------------------------------------------------------------


def test_file_sha_returns_sha_when_present():
    with patch.dict("os.environ", {"GITHUB_VAULT_TOKEN": "tok"}):
        with patch("vault_client._api", return_value={"sha": "blob123"}):
            assert _file_sha("Acme_DE_20240101_000000.tex", "vault/u1") == "blob123"


def test_file_sha_returns_none_when_absent():
    with patch.dict("os.environ", {"GITHUB_VAULT_TOKEN": "tok"}):
        with patch("vault_client._api", return_value=None):
            assert _file_sha("missing.tex", "vault/u1") is None


def test_push_version_updates_existing_files():
    """When .tex / .meta.json already exist, _file_sha returns a sha that gets
    threaded into the PUT body (update mode)."""
    branch_ref = {"object": {"sha": "deadbeef"}}
    tex_commit = {"commit": {"sha": "newcommit"}}
    meta_commit = {"commit": {"sha": "newmeta"}}

    with patch.dict("os.environ", {"GITHUB_VAULT_TOKEN": "tok"}):
        with patch("vault_client._api") as mock_api:
            mock_api.side_effect = [
                branch_ref,                # branch exists
                {"sha": "tex_blob_sha"},   # _file_sha .tex → existing
                tex_commit,                # PUT .tex
                {"sha": "meta_blob_sha"},  # _file_sha .meta → existing
                meta_commit,               # PUT .meta
            ]
            entry = push_version("u_update", "Acme", "DE", _TEX, _META)

    assert entry is not None
    put_calls = [c for c in mock_api.call_args_list if c.kwargs.get("method") == "PUT"]
    assert len(put_calls) == 2
    for call in put_calls:
        assert "sha" in call.kwargs["body"]


def test_push_version_commit_sha_empty_on_put_failure():
    """If the .tex PUT returns None (HTTP 500), commit_sha is empty but no crash."""
    branch_ref = {"object": {"sha": "deadbeef"}}
    with patch.dict("os.environ", {"GITHUB_VAULT_TOKEN": "tok"}):
        with patch("vault_client._api") as mock_api:
            mock_api.side_effect = [
                branch_ref,   # branch exists
                None,         # _file_sha .tex → not found
                None,         # PUT .tex → HTTP 500 / failure
                None,         # _file_sha .meta → not found
                None,         # PUT .meta → also fails
            ]
            entry = push_version("u_fail", "Acme", "DE", _TEX, _META)
    assert entry is not None
    assert entry.commit_sha == ""


# ---------------------------------------------------------------------------
# list_versions — error / empty paths
# ---------------------------------------------------------------------------


def test_list_versions_tree_fetch_error_returns_empty():
    with patch.dict("os.environ", {"GITHUB_VAULT_TOKEN": "tok"}):
        with patch("vault_client._api", return_value=None):
            assert list_versions("user_missing") == []


def test_list_versions_empty_tree_returns_empty():
    with patch.dict("os.environ", {"GITHUB_VAULT_TOKEN": "tok"}):
        with patch("vault_client._api", return_value={"tree": []}):
            assert list_versions("user_empty") == []


# ---------------------------------------------------------------------------
# get_version — error paths
# ---------------------------------------------------------------------------


def test_get_version_missing_file_returns_none():
    with patch.dict("os.environ", {"GITHUB_VAULT_TOKEN": "tok"}):
        with patch("vault_client._api", return_value=None):
            assert get_version("user1", "missing_file") is None


def test_get_version_response_without_content_returns_none():
    with patch.dict("os.environ", {"GITHUB_VAULT_TOKEN": "tok"}):
        with patch("vault_client._api", return_value={"sha": "x"}):
            assert get_version("user1", "broken") is None


def test_get_version_undecodable_content_returns_none():
    """Bad base64 → base64.b64decode raises; we return None."""
    with patch.dict("os.environ", {"GITHUB_VAULT_TOKEN": "tok"}):
        with patch("vault_client._api", return_value={"content": "!!!not-base64!!!"}):
            assert get_version("user1", "weird") is None


# ---------------------------------------------------------------------------
# Token redaction — sweep public surface for log leaks
# ---------------------------------------------------------------------------


def test_push_version_does_not_log_token_on_failure(monkeypatch, capsys):
    """Even when everything fails, the token value never appears in stdout/stderr."""
    secret = "ghp_LEAK_CHECK_TOKEN_98765"
    monkeypatch.setenv("GITHUB_VAULT_TOKEN", secret)

    def boom(req, timeout=15):
        raise urllib.error.HTTPError(req.full_url, 500, "Boom", hdrs=None, fp=None)

    monkeypatch.setattr("urllib.request.urlopen", boom)
    result = push_version("u", "Co", "R", _TEX, _META)
    assert result is None
    captured = capsys.readouterr()
    assert secret not in captured.out
    assert secret not in captured.err
