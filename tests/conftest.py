"""Shared fixtures for tailor-resume test suite."""
import json
import sys
from pathlib import Path

import pytest

# Make scripts/ importable from tests/
SCRIPTS_DIR = Path(__file__).parent.parent / ".claude" / "skills" / "tailor-resume" / "scripts"
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
TEMPLATES_DIR = Path(__file__).parent.parent / ".claude" / "skills" / "tailor-resume" / "templates"

sys.path.insert(0, str(SCRIPTS_DIR))


@pytest.fixture
def sample_jd_text():
    return (FIXTURES_DIR / "sample_jd.txt").read_text(encoding="utf-8")


@pytest.fixture
def sample_blob_text():
    return (FIXTURES_DIR / "sample_blob.txt").read_text(encoding="utf-8")


@pytest.fixture
def sample_profile_dict():
    return json.loads((FIXTURES_DIR / "sample_profile.json").read_text(encoding="utf-8"))


@pytest.fixture
def template_path():
    return str(TEMPLATES_DIR / "resume_template.tex")


@pytest.fixture
def out_dir(tmp_path):
    return tmp_path
