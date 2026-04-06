"""Tests for vault_client.py — GitHub resume vault operations."""
from __future__ import annotations

import base64
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / ".claude" / "skills" / "tailor-resume" / "scripts"))

from vault_client import (  # noqa: E402
    VaultEntry,
    _branch_name,
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
