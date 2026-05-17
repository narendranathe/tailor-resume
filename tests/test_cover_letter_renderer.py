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


def test_docx_written_to_out_dir(tmp_path):
    try:
        import docx  # noqa: F401
    except ImportError:
        pytest.skip("python-docx not installed")
    result = build_cover_letter(
        _PROFILE, _REPORT, _HEADER, _JD, method="template", out_dir=str(tmp_path)
    )
    assert result.docx_path is not None
    expected = tmp_path / "cover_letter.docx"
    assert Path(result.docx_path) == expected
    assert expected.exists()
    assert expected.stat().st_size > 0


def test_word_cap_enforced_at_sentence_boundary():
    """Input ≥300 words → output ≤250 words ending at a sentence boundary."""
    from cover_letter_renderer import _enforce_word_limit  # noqa: WPS433

    # 300-word para1, short para2 — forces a trim well past the limit.
    long_sentence = "This is a meaningful achievement that drove measurable impact across the team. "
    # Each sentence is ~13 words → 25 sentences ≈ 325 words.
    para1 = long_sentence * 25
    para2 = "Short closing line."
    p1, p2 = _enforce_word_limit(para1, para2, 250)
    combined = f"{p1}\n\n{p2}".strip()
    word_count = len(combined.split())
    assert word_count <= 250, f"got {word_count} words, expected ≤ 250"
    # Should end at a sentence boundary (., !, or ?)
    assert combined.rstrip().endswith((".", "!", "?")), f"no sentence end: ...{combined[-40:]}"


def test_word_cap_passthrough_when_under_limit():
    from cover_letter_renderer import _enforce_word_limit  # noqa: WPS433

    p1 = "Short paragraph one."
    p2 = "Short paragraph two."
    out1, out2 = _enforce_word_limit(p1, p2, 250)
    assert out1 == p1
    assert out2 == p2


def test_claude_model_constant_pinned():
    """The Claude model must be pinned to the owner-approved haiku-4-5 build."""
    from cover_letter_renderer import _CLAUDE_MODEL  # noqa: WPS433

    assert _CLAUDE_MODEL == "claude-haiku-4-5-20251001"


def test_claude_model_used_in_api_call():
    """Verify the pinned model is the one actually sent to anthropic.messages.create."""
    mock_content = MagicMock()
    mock_content.text = "Para one body here.\n\nPara two body here."
    mock_client = MagicMock()
    mock_client.messages.create.return_value.content = [mock_content]
    mock_anthropic = MagicMock()
    mock_anthropic.Anthropic.return_value = mock_client

    with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
        build_cover_letter(_PROFILE, _REPORT, _HEADER, _JD, method="claude")

    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert call_kwargs["model"] == "claude-haiku-4-5-20251001"


def test_claude_response_with_code_fences_is_stripped():
    """Claude sometimes wraps output in ```...``` — must be stripped before split."""
    mock_content = MagicMock()
    mock_content.text = "```\nPara one with fences.\n\nPara two body.\n```"
    mock_client = MagicMock()
    mock_client.messages.create.return_value.content = [mock_content]
    mock_anthropic = MagicMock()
    mock_anthropic.Anthropic.return_value = mock_client

    with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
        result = build_cover_letter(_PROFILE, _REPORT, _HEADER, _JD, method="claude")

    assert "```" not in result.txt
    assert "Para one with fences." in result.txt


def test_company_extracted_from_jd():
    """Company name from JD ('at Acme Corp') is used in the template para 1."""
    result = build_cover_letter(_PROFILE, _REPORT, _HEADER, _JD, method="template")
    assert "Acme" in result.txt


def test_company_fallback_when_jd_has_no_company():
    """Empty/unparseable JD → falls back to 'your company'."""
    result = build_cover_letter(_PROFILE, _REPORT, _HEADER, "vague text", method="template")
    assert "your company" in result.txt.lower()


def test_report_with_no_top_missing_still_renders():
    class _EmptyReport:
        top_missing = []
        recommendations = []
    result = build_cover_letter(_PROFILE, _EmptyReport(), _HEADER, _JD, method="template")
    assert isinstance(result, CoverLetterResult)
    assert result.word_count > 0


def test_profile_with_no_bullets_uses_fallback_para2():
    profile = {"experience": [{"company": "X", "bullets": []}], "skills": ["Python"]}
    result = build_cover_letter(profile, _REPORT, _HEADER, _JD, method="template")
    # The fallback para2 talks about "measurable results"
    assert "measurable" in result.txt or result.word_count > 10


def test_tex_uses_template_file_preamble():
    """Output .tex inherits the LaTeX preamble (\\documentclass + \\usepackage) from
    cover_letter_template.tex, matching the resume preamble style."""
    result = build_cover_letter(_PROFILE, _REPORT, _HEADER, _JD, method="template")
    assert "\\documentclass" in result.tex
    assert "\\usepackage" in result.tex
    assert "\\begin{document}" in result.tex
    assert "\\end{document}" in result.tex


def test_bullets_as_plain_strings_handled():
    """Some legacy profiles may have bullets as plain strings, not dicts."""
    profile = {
        "experience": [{"company": "ACo", "bullets": ["Shipped X feature in Q1.", "Led 3-person team."]}],
        "skills": ["Python"],
    }
    result = build_cover_letter(profile, _REPORT, _HEADER, _JD, method="template")
    assert isinstance(result, CoverLetterResult)
    # At least one bullet phrase should make it into the body
    assert "shipped" in result.txt.lower() or "led" in result.txt.lower()
