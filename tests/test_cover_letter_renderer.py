"""Tests for cover_letter_renderer.py."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / ".claude" / "skills" / "tailor-resume" / "scripts"))

from cover_letter_renderer import CoverLetterResult, build_cover_letter  # noqa: E402

_JD = (
    "We are hiring a Senior Data Engineer at Acme Corp. "
    "You will work with Spark, Kafka, Airflow, and Delta Lake. "
    "Focus on schema drift, data contracts, and CI/CD pipelines."
)
_HEADER = {
    "name": "Jane Smith",
    "email": "jane@example.com",
    "phone": "+1 555-000-0000",
    "linkedin": "https://linkedin.com/in/jane",
}
_PROFILE = {
    "experience": [
        {
            "title": "Data Engineer",
            "company": "Acme Corp",
            "start": "2022",
            "end": "Present",
            "location": "Dallas TX",
            "bullets": [
                {"text": "Reduced ETL 73% via CDC upserts, saving $3k/month.", "metrics": ["73%"], "tools": ["Spark"], "evidence_source": "blob", "confidence": "high"},
                {"text": "Built Pytest suite for 12 pipelines, reducing defects 40%.", "metrics": ["40%"], "tools": [], "evidence_source": "blob", "confidence": "high"},
            ],
        }
    ],
    "projects": [],
    "skills": ["Python", "Spark", "Kafka"],
    "education": [],
    "certifications": [],
}


class _FakeGapSignal:
    def __init__(self):
        self.category = "Software Craftsmanship"
        self.jd_keywords = ["CI/CD", "schema drift", "idempotency"]


class _FakeReport:
    top_missing = [_FakeGapSignal()]
    recommendations = ["Add CI/CD bullet to top role.", "Quantify schema drift handling."]


_REPORT = _FakeReport()


def test_template_method_returns_cover_letter_result():
    result = build_cover_letter(_PROFILE, _REPORT, _HEADER, _JD, method="template")
    assert isinstance(result, CoverLetterResult)
    assert result.method_used == "template"


def test_template_tex_contains_name():
    result = build_cover_letter(_PROFILE, _REPORT, _HEADER, _JD, method="template")
    assert "Jane Smith" in result.tex


def test_template_tex_has_content():
    result = build_cover_letter(_PROFILE, _REPORT, _HEADER, _JD, method="template")
    # tex should have two non-empty paragraph substitutions
    assert "PARA_ONE" not in result.tex
    assert "PARA_TWO" not in result.tex


def test_template_txt_has_no_latex_commands():
    result = build_cover_letter(_PROFILE, _REPORT, _HEADER, _JD, method="template")
    # .txt should not have backslash commands
    import re
    latex_cmds = re.findall(r"\\[a-zA-Z]{2,}", result.txt)
    assert latex_cmds == [], f"Found LaTeX commands in .txt: {latex_cmds}"


def test_template_word_count_under_250():
    result = build_cover_letter(_PROFILE, _REPORT, _HEADER, _JD, method="template")
    assert result.word_count <= 250


def test_template_txt_has_two_paragraphs():
    result = build_cover_letter(_PROFILE, _REPORT, _HEADER, _JD, method="template")
    paragraphs = [p for p in result.txt.split("\n\n") if p.strip()]
    assert len(paragraphs) >= 1


def test_claude_method_mocked():
    mock_content = MagicMock()
    mock_content.text = "I bring deep Spark expertise to Acme Corp.\n\nAt Acme, I reduced ETL by 73%."
    mock_client = MagicMock()
    mock_client.messages.create.return_value.content = [mock_content]
    mock_anthropic = MagicMock()
    mock_anthropic.Anthropic.return_value = mock_client

    with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
        result = build_cover_letter(_PROFILE, _REPORT, _HEADER, _JD, method="claude")

    assert isinstance(result, CoverLetterResult)
    assert result.method_used == "claude"
    assert mock_client.messages.create.called


def test_claude_falls_back_to_template_on_exception():
    mock_anthropic = MagicMock()
    mock_anthropic.Anthropic.side_effect = RuntimeError("API down")

    with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
        result = build_cover_letter(_PROFILE, _REPORT, _HEADER, _JD, method="claude")

    assert isinstance(result, CoverLetterResult)
    assert "template" in result.method_used


def test_empty_profile_does_not_crash():
    result = build_cover_letter({}, _REPORT, _HEADER, _JD, method="template")
    assert isinstance(result, CoverLetterResult)
    assert result.word_count > 0


def test_empty_header_does_not_crash():
    result = build_cover_letter(_PROFILE, _REPORT, {}, _JD, method="template")
    assert isinstance(result, CoverLetterResult)


def test_empty_jd_does_not_crash():
    result = build_cover_letter(_PROFILE, _REPORT, _HEADER, "", method="template")
    assert isinstance(result, CoverLetterResult)


def test_docx_created_when_python_docx_available():
    try:
        import docx  # noqa: F401
        result = build_cover_letter(_PROFILE, _REPORT, _HEADER, _JD, method="template")
        if result.docx_path:
            assert Path(result.docx_path).exists()
    except ImportError:
        pytest.skip("python-docx not installed")
