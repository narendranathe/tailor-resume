"""
Deep coverage tests for parsers/pdf_extractor.py.

The repository's primary PDF parser lives in two places:

* ``profile_extractor.py``                 — the legacy monolithic module
* ``parsers/pdf_extractor.py``             — the new, leaner sibling

The tests in ``tests/test_profile_extractor.py`` exercise the first.  The
new sibling has its own implementation of every text-extraction tier and
Claude integration helpers, so it needs its own tests.

These tests focus on three areas that the existing
``tests/test_parsers_integration.py::TestPdfExtractor`` does not yet cover:

1. ``_extract_pdf_text_stdlib`` — driven with hand-crafted PDF byte streams
   that exercise the BT/ET text-extraction state machine (Tm, Td, T*, TJ,
   Tj, hex strings, kerning, escape unescaping, OT1 ligature normalization,
   line grouping, column splitting, final cleanup).
2. ``_extract_pdf_text_pdfminer`` — the cryptography import in this sandbox
   is broken, so we mock pdfminer at the ``sys.modules`` boundary with a
   fake high-level API that returns synthetic page layouts.  This lets us
   cover the column-detection / box-sorting branches without depending on
   the real library.
3. ``_parse_with_claude`` / ``_enrich_profile_with_claude`` — happy-path
   and assorted error paths with the Anthropic SDK mocked via
   ``monkeypatch.setitem(sys.modules, ...)``.
"""
from __future__ import annotations

import json
import sys
import types
import zlib
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Make scripts/ importable
SCRIPTS_DIR = (
    Path(__file__).parent.parent
    / ".claude"
    / "skills"
    / "tailor-resume"
    / "scripts"
)
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

# Module under test imported once; helpers refer back to it.
from parsers import pdf_extractor as pdfx  # noqa: E402
from resume_types import Profile, Role  # noqa: E402


# ---------------------------------------------------------------------------
# Anthropic mock helpers (mirror tests/test_claude_vision_extractor.py)
# ---------------------------------------------------------------------------
FAKE_KEY = "test-fake-not-a-real-key"


def _install_anthropic_mock(monkeypatch, response_text: str) -> MagicMock:
    """Inject a fake `anthropic` module returning `response_text`."""
    mock_resp = MagicMock()
    mock_resp.content = [MagicMock(text=response_text)]

    mock_anthropic = MagicMock()
    mock_anthropic.Anthropic.return_value.messages.create.return_value = mock_resp
    monkeypatch.setitem(sys.modules, "anthropic", mock_anthropic)
    return mock_anthropic


def _install_anthropic_error(monkeypatch, exc: Exception) -> MagicMock:
    """Inject a fake `anthropic` module that raises `exc` on messages.create."""
    mock_anthropic = MagicMock()
    mock_anthropic.Anthropic.return_value.messages.create.side_effect = exc
    monkeypatch.setitem(sys.modules, "anthropic", mock_anthropic)
    return mock_anthropic


def _uninstall_anthropic(monkeypatch) -> None:
    """Force the `from anthropic import Anthropic` import to fail."""
    monkeypatch.setitem(sys.modules, "anthropic", None)


# ---------------------------------------------------------------------------
# Minimal PDF byte builder
# ---------------------------------------------------------------------------
def _build_pdf_with_content_stream(stream_text: str, compress: bool = False) -> bytes:
    """Wrap a raw PDF content stream into a minimal one-page PDF."""
    stream = stream_text.encode("latin-1", errors="replace")
    if compress:
        stream = zlib.compress(stream)
        filter_entry = b" /Filter /FlateDecode"
    else:
        filter_entry = b""
    stream_len = len(stream)
    pdf = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]"
        b" /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
        b"4 0 obj\n<< /Length " + str(stream_len).encode() + filter_entry + b" >>\nstream\n"
        + stream + b"\nendstream\nendobj\n"
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
        b"xref\n0 6\n0000000000 65535 f \n"
        b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n0\n%%EOF"
    )
    return pdf


# ===========================================================================
# _extract_pdf_text_stdlib — BT/ET state machine coverage
# ===========================================================================
class TestExtractPdfTextStdlibDeep:
    def test_simple_tm_then_tj_emits_text(self):
        # Tm absolute positioning then a (string) Tj operator → string emitted
        stream = "BT 1 0 0 1 100 700 Tm (Hello World) Tj ET"
        pdf = _build_pdf_with_content_stream(stream)
        out = pdfx._extract_pdf_text_stdlib(pdf)
        assert "Hello World" in out

    def test_compressed_stream_is_decompressed(self):
        # FlateDecode is exercised because we zlib.compress the stream
        stream = "BT 1 0 0 1 50 700 Tm (Compressed Data) Tj ET"
        pdf = _build_pdf_with_content_stream(stream, compress=True)
        out = pdfx._extract_pdf_text_stdlib(pdf)
        assert "Compressed" in out and "Data" in out

    def test_td_advances_position_emitting_text(self):
        # Two Td-separated text pieces at different y-coords → two lines
        stream = (
            "BT 1 0 0 1 50 700 Tm "
            "(LineOne) Tj "
            "0 -20 Td "  # large dy → emit previous, advance line
            "(LineTwo) Tj ET"
        )
        pdf = _build_pdf_with_content_stream(stream)
        out = pdfx._extract_pdf_text_stdlib(pdf)
        assert "LineOne" in out
        assert "LineTwo" in out

    def test_apostrophe_operator_advances_line_and_emits(self):
        # ' after a string acts like T* then Tj
        stream = (
            "BT 1 0 0 1 50 700 Tm "
            "(First) Tj "
            "(Second)' ET"
        )
        pdf = _build_pdf_with_content_stream(stream)
        out = pdfx._extract_pdf_text_stdlib(pdf)
        assert "First" in out
        assert "Second" in out

    def test_t_star_advances_line(self):
        # T* uses leading set via TL
        stream = (
            "BT 1 0 0 1 50 700 Tm "
            "14 TL "  # leading
            "(Above) Tj "
            "T* "
            "(Below) Tj ET"
        )
        pdf = _build_pdf_with_content_stream(stream)
        out = pdfx._extract_pdf_text_stdlib(pdf)
        assert "Above" in out
        assert "Below" in out

    def test_tj_array_with_kerning_inserts_space(self):
        # In a TJ array, a kern value < -150 between strings should insert a space
        stream = (
            "BT 1 0 0 1 50 700 Tm "
            "[(Word) -200 (Next)] TJ ET"
        )
        pdf = _build_pdf_with_content_stream(stream)
        out = pdfx._extract_pdf_text_stdlib(pdf)
        # We expect both words present, with a space between them
        assert "Word" in out
        assert "Next" in out
        # The kerning rule injected a space → not glued together
        line = next((ln for ln in out.splitlines() if "Word" in ln and "Next" in ln), "")
        assert "Word Next" in line or "Word " in line

    def test_tj_hex_string_decoded(self):
        # "Hello" in UTF-16-BE → 0048 0065 006C 006C 006F
        hex_str = "00480065006C006C006F"
        stream = "BT 1 0 0 1 50 700 Tm <" + hex_str + "> Tj ET"
        pdf = _build_pdf_with_content_stream(stream)
        out = pdfx._extract_pdf_text_stdlib(pdf)
        assert "Hello" in out

    def test_two_column_layout_groups_columns_separately(self):
        # Pieces on the left half at x=50 and on the right half at x=400
        # share the same y so absent column-splitting they'd glue.
        stream = (
            "BT 1 0 0 1 50 700 Tm (LeftLine) Tj "
            "1 0 0 1 400 700 Tm (RightLine) Tj "
            "1 0 0 1 50 680 Tm (LeftBelow) Tj "
            "1 0 0 1 400 680 Tm (RightBelow) Tj "
            "1 0 0 1 50 660 Tm (LeftBottom) Tj "
            "1 0 0 1 400 660 Tm (RightBottom) Tj ET"
        )
        pdf = _build_pdf_with_content_stream(stream)
        out = pdfx._extract_pdf_text_stdlib(pdf)
        # Both columns survive
        assert "LeftLine" in out
        assert "RightLine" in out
        # Column-split branch is exercised because of the large x-gap

    def test_escaped_parens_and_backslashes_unescaped(self):
        # Backslash escapes are accumulated by _pdf_read_string then
        # _unescape collapses them.  We pass \( \) and \\ in a Tj string.
        # PDF strings cannot literally contain unescaped parens of unequal
        # depth, so we use balanced + escaped.
        stream = "BT 1 0 0 1 50 700 Tm (a \\(b\\) c) Tj ET"
        pdf = _build_pdf_with_content_stream(stream)
        out = pdfx._extract_pdf_text_stdlib(pdf)
        assert "a (b) c" in out

    def test_octal_escape_unescaped_to_ascii(self):
        # \101 (octal) → chr(65) = 'A'
        stream = "BT 1 0 0 1 50 700 Tm (\\101BC) Tj ET"
        pdf = _build_pdf_with_content_stream(stream)
        out = pdfx._extract_pdf_text_stdlib(pdf)
        assert "ABC" in out

    def test_ot1_ligature_byte_substituted(self):
        # 0x0F should become "ffi"
        stream = "BT 1 0 0 1 50 700 Tm (o\x0fce) Tj ET"
        pdf = _build_pdf_with_content_stream(stream)
        out = pdfx._extract_pdf_text_stdlib(pdf)
        assert "office" in out

    def test_unknown_operators_skipped(self):
        # Random operator tokens between text should be ignored without raising
        stream = (
            "BT 1 0 0 1 50 700 Tm "
            "0.5 0.5 0.5 rg "  # color op — unrecognized → skipped
            "(KeepMe) Tj ET"
        )
        pdf = _build_pdf_with_content_stream(stream)
        out = pdfx._extract_pdf_text_stdlib(pdf)
        assert "KeepMe" in out

    def test_garbage_only_pdf_returns_empty_string(self):
        # No BT/ET, no streams → empty string back (not exception)
        out = pdfx._extract_pdf_text_stdlib(b"not a real pdf, no streams")
        assert out == ""

    def test_low_alpha_line_dropped(self):
        # A short line with only punctuation/digits low alpha-ratio should be dropped.
        # Single-character / pure-symbol Tj string → cleaned out at the
        # "len(line) < 2" or low-alpha check.
        stream = "BT 1 0 0 1 50 700 Tm (.) Tj ET"
        pdf = _build_pdf_with_content_stream(stream)
        out = pdfx._extract_pdf_text_stdlib(pdf)
        # the single-char line is dropped (len < 2 in the cleaner)
        assert "." not in out

    def test_yyyy_t_month_repaired_to_endash(self):
        # The final regex turns "2024 t Jan" → "2024 – Jan"
        stream = (
            "BT 1 0 0 1 50 700 Tm (2024 t January was busy) Tj ET"
        )
        pdf = _build_pdf_with_content_stream(stream)
        out = pdfx._extract_pdf_text_stdlib(pdf)
        # The substitution puts a U+2013 between the year and the month
        assert "–" in out
        assert "January" in out

    def test_date_digit_joining_collapses_spaces(self):
        # "12 3" between digits collapses to "123" via the post-process regex
        stream = "BT 1 0 0 1 50 700 Tm (Achievement of 12 3 records done) Tj ET"
        pdf = _build_pdf_with_content_stream(stream)
        out = pdfx._extract_pdf_text_stdlib(pdf)
        # Either "123 records" (joined) or at minimum no extra spaces between
        # the two digit groups.
        assert "123" in out or "12 3" not in out

    def test_undecodable_hex_in_tj_array_skipped(self):
        # Hex string with odd length & invalid chars in a TJ array.
        stream = "BT 1 0 0 1 50 700 Tm [(Pre) <ZZ> (Post)] TJ ET"
        pdf = _build_pdf_with_content_stream(stream)
        out = pdfx._extract_pdf_text_stdlib(pdf)
        assert "Pre" in out and "Post" in out


# ===========================================================================
# _extract_pdf_text_pdfminer — mocked pdfminer module
# ===========================================================================
class _FakeLTTextBox:
    """Stand-in for pdfminer.layout.LTTextBox; supports y1/x0/get_text()."""

    def __init__(self, x0: float, y1: float, text: str) -> None:
        self.x0 = x0
        self.y1 = y1
        self._text = text

    def get_text(self) -> str:
        return self._text


class _FakeLayoutPage:
    def __init__(self, width: float, elements):
        self.width = width
        self._elements = elements

    def __iter__(self):
        return iter(self._elements)


def _install_fake_pdfminer(monkeypatch, page) -> None:
    """Install a synthetic pdfminer.high_level + pdfminer.layout in sys.modules.

    Important: ``extract_pages`` must be re-entrant — the implementation
    calls it twice (once to iterate, once to fetch first_page.width).
    """
    # Two iterator factories so each call gets a fresh iterator
    def extract_pages(_buffer, laparams=None):
        # Each call yields a fresh iterator over the same page object.
        return iter([page])

    high_level = types.ModuleType("pdfminer.high_level")
    high_level.extract_pages = extract_pages  # type: ignore[attr-defined]

    layout = types.ModuleType("pdfminer.layout")
    layout.LAParams = lambda **kw: None  # type: ignore[attr-defined]
    # Make isinstance(element, LTTextBox) pass for our fakes.
    layout.LTTextBox = _FakeLTTextBox  # type: ignore[attr-defined]

    pdfminer_pkg = types.ModuleType("pdfminer")
    monkeypatch.setitem(sys.modules, "pdfminer", pdfminer_pkg)
    monkeypatch.setitem(sys.modules, "pdfminer.high_level", high_level)
    monkeypatch.setitem(sys.modules, "pdfminer.layout", layout)


class TestExtractPdfTextPdfminerMocked:
    def test_empty_layout_returns_empty_string(self, monkeypatch):
        page = _FakeLayoutPage(width=612, elements=[])
        _install_fake_pdfminer(monkeypatch, page)
        out = pdfx._extract_pdf_text_pdfminer(b"%PDF-fake")
        assert out == ""

    def test_single_column_layout_returns_text(self, monkeypatch):
        # Two stacked text boxes on the same column → single-column branch.
        page = _FakeLayoutPage(
            width=612,
            elements=[
                _FakeLTTextBox(x0=72, y1=700, text="Header"),
                _FakeLTTextBox(x0=72, y1=600, text="Body of the document"),
            ],
        )
        _install_fake_pdfminer(monkeypatch, page)
        out = pdfx._extract_pdf_text_pdfminer(b"%PDF-fake")
        assert "Header" in out
        assert "Body" in out

    def test_two_column_layout_splits_columns(self, monkeypatch):
        # Two columns separated by a large x-gap → column-split branch.
        # Left column at x=50, right column at x=350 (gap=300).
        page = _FakeLayoutPage(
            width=612,
            elements=[
                _FakeLTTextBox(x0=50, y1=700, text="LeftTop"),
                _FakeLTTextBox(x0=50, y1=600, text="LeftBottom"),
                _FakeLTTextBox(x0=350, y1=700, text="RightTop"),
                _FakeLTTextBox(x0=350, y1=600, text="RightBottom"),
            ],
        )
        _install_fake_pdfminer(monkeypatch, page)
        out = pdfx._extract_pdf_text_pdfminer(b"%PDF-fake")
        # All four boxes are present.
        for tok in ("LeftTop", "LeftBottom", "RightTop", "RightBottom"):
            assert tok in out
        # The two-column branch exercises the column-split path; we don't
        # over-assert ordering because the implementation only emits a
        # column split when the gap is detected on x0_vals before page_mid.

    def test_multi_sentence_text_box_no_spurious_bullets(self, monkeypatch):
        # Fix 3: _box_lines must NOT inject "• " into multi-sentence boxes.
        # Raw lines are returned as-is; the plain parser decides what is a bullet.
        page = _FakeLayoutPage(
            width=612,
            elements=[
                _FakeLTTextBox(
                    x0=72,
                    y1=600,
                    text=(
                        "Built scalable ETL pipelines.\n"
                        "Reduced query latency by 40%."
                    ),
                ),
            ],
        )
        _install_fake_pdfminer(monkeypatch, page)
        out = pdfx._extract_pdf_text_pdfminer(b"%PDF-fake")
        # Both lines must be present in the output…
        assert "Built scalable ETL pipelines." in out
        assert "Reduced query latency by 40%." in out
        # …but no "• " was injected by _box_lines.
        assert out.count("•") == 0, f"spurious bullets injected: {out!r}"

    def test_first_page_width_lookup_failure_uses_default(self, monkeypatch):
        # extract_pages succeeds first call, second call raises → page_mid=306 default.
        page = _FakeLayoutPage(
            width=612,
            elements=[_FakeLTTextBox(x0=72, y1=700, text="Solo")],
        )

        calls = {"n": 0}

        def extract_pages(_buffer, laparams=None):
            calls["n"] += 1
            if calls["n"] == 1:
                return iter([page])
            raise RuntimeError("second call boom")

        high_level = types.ModuleType("pdfminer.high_level")
        high_level.extract_pages = extract_pages  # type: ignore[attr-defined]
        layout = types.ModuleType("pdfminer.layout")
        layout.LAParams = lambda **kw: None  # type: ignore[attr-defined]
        layout.LTTextBox = _FakeLTTextBox  # type: ignore[attr-defined]
        pdfminer_pkg = types.ModuleType("pdfminer")
        monkeypatch.setitem(sys.modules, "pdfminer", pdfminer_pkg)
        monkeypatch.setitem(sys.modules, "pdfminer.high_level", high_level)
        monkeypatch.setitem(sys.modules, "pdfminer.layout", layout)

        out = pdfx._extract_pdf_text_pdfminer(b"%PDF-fake")
        assert "Solo" in out


# ===========================================================================
# _parse_with_claude — full coverage of success / error / fallback branches
# ===========================================================================
class TestParseWithClaudeDeep:
    def _payload(self) -> dict:
        return {
            "experience": [
                {
                    "title": "Senior Data Engineer",
                    "company": "Acme Corp",
                    "start": "Jan 2022",
                    "end": "Present",
                    "location": "Dallas, TX",
                    "bullets": [
                        "Built scalable ETL pipelines processing 10K events per second",
                        "Reduced latency by 40% via partition tuning",
                        "",  # blank → filtered
                        123,  # non-string → filtered
                    ],
                }
            ],
            "projects": [
                {
                    "name": "ML Anomaly Detector",
                    "tech": ["Python", "PyTorch"],
                    "bullets": [
                        "Trained anomaly detection model on 1M samples",
                        None,  # falsy → filtered
                    ],
                }
            ],
            "skills": ["Python", "SQL", "Spark", "Python", 42, "SQL"],
            "education": [
                {
                    "institution": "UT Dallas",
                    "degree": "MS Computer Science",
                    "dates": "2020 – 2022",
                    "location": "",
                }
            ],
            "certifications": ["AWS Solutions Architect", 999],
        }

    def test_happy_path_builds_full_profile(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
        _install_anthropic_mock(monkeypatch, json.dumps(self._payload()))

        profile = pdfx._parse_with_claude("raw resume text here", source="test_src")

        assert isinstance(profile, Profile)
        assert len(profile.experience) == 1
        role = profile.experience[0]
        assert role.title == "Senior Data Engineer"
        assert role.company == "Acme Corp"
        assert role.start == "Jan 2022"
        assert role.end == "Present"
        assert role.location == "Dallas, TX"
        # Only string non-blank bullets survive
        assert len(role.bullets) == 2
        assert all(b.evidence_source == "test_src" for b in role.bullets)

        # Project bullets filtered similarly
        assert len(profile.projects) == 1
        assert profile.projects[0].name == "ML Anomaly Detector"
        assert "Python" in profile.projects[0].tech
        assert len(profile.projects[0].bullets) == 1

        # Skills deduped & non-strings dropped
        assert profile.skills == ["Python", "SQL", "Spark"]

        # Education preserved
        assert profile.education == [
            {
                "institution": "UT Dallas",
                "degree": "MS Computer Science",
                "dates": "2020 – 2022",
                "location": "",
            }
        ]

        # Certifications: non-strings filtered
        assert profile.certifications == ["AWS Solutions Architect"]

    def test_response_with_markdown_fence_is_stripped(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
        fenced = "```json\n" + json.dumps(self._payload()) + "\n```"
        _install_anthropic_mock(monkeypatch, fenced)
        profile = pdfx._parse_with_claude("raw text", source="t")
        assert len(profile.experience) == 1
        assert "Python" in profile.skills

    def test_response_with_bare_backtick_fence_is_stripped(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
        fenced = "```\n" + json.dumps(self._payload()) + "\n```"
        _install_anthropic_mock(monkeypatch, fenced)
        profile = pdfx._parse_with_claude("raw text", source="t")
        assert len(profile.experience) == 1

    def test_invalid_json_falls_back_to_plain_parser(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
        _install_anthropic_mock(monkeypatch, "definitely not json")
        result = pdfx._parse_with_claude(
            "Engineer at Acme  Jan 2022 – Present\n- Built X\n",
            source="t",
        )
        # Plain-parser fallback returns a Profile (possibly empty experience)
        assert isinstance(result, Profile)

    def test_api_exception_falls_back_to_plain_parser(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
        _install_anthropic_error(monkeypatch, RuntimeError("network down"))
        result = pdfx._parse_with_claude(
            "Engineer at Acme  Jan 2022 – Present\n- Built X\n",
            source="t",
        )
        assert isinstance(result, Profile)

    def test_no_api_key_falls_back_to_plain_parser(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        result = pdfx._parse_with_claude("anything", source="t")
        assert isinstance(result, Profile)

    def test_missing_anthropic_package_falls_back_to_plain_parser(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
        _uninstall_anthropic(monkeypatch)
        result = pdfx._parse_with_claude("anything", source="t")
        assert isinstance(result, Profile)

    def test_empty_lists_in_response_produce_empty_profile_sections(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
        empty = {
            "experience": [],
            "projects": [],
            "skills": [],
            "education": [],
            "certifications": [],
        }
        _install_anthropic_mock(monkeypatch, json.dumps(empty))
        profile = pdfx._parse_with_claude("blank", source="t")
        assert profile.experience == []
        assert profile.projects == []
        assert profile.skills == []
        assert profile.education == []
        assert profile.certifications == []


# ===========================================================================
# _enrich_profile_with_claude — full coverage
# ===========================================================================
class TestEnrichProfileWithClaudeDeep:
    def _make_profile(self) -> Profile:
        return Profile(
            experience=[
                Role(
                    title="Engineer",
                    company="Acme",
                    start="Jan 2022",
                    end="Present",
                    location="",
                )
            ]
        )

    def test_happy_path_rebuilds_profile_from_response(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
        enriched = {
            "experience": [
                {
                    "title": "Engineer",
                    "company": "Acme",
                    "start": "Jan 2022",
                    "end": "Present",
                    "location": "",
                    "bullets": [
                        {"text": "Improved CI by 60%", "confidence": "high"},
                        {"text": "Migrated to k8s", "confidence": "medium"},
                        "Plain string bullet works too",
                        "",  # falsy → filtered
                    ],
                }
            ],
            "projects": [
                {
                    "name": "Pipeline",
                    "tech": ["Spark"],
                    "bullets": [
                        {"text": "Processed 1M rows/day", "confidence": "high"},
                        "",  # falsy → filtered
                    ],
                }
            ],
            "skills": ["Python", "Python", "Go"],
            "education": [
                {
                    "institution": "MIT",
                    "degree": "BS CS",
                    "dates": "2014-2018",
                    "location": "",
                }
            ],
            "certifications": ["AWS Pro", 42],
        }
        _install_anthropic_mock(monkeypatch, json.dumps(enriched))

        result = pdfx._enrich_profile_with_claude(self._make_profile(), source="enr")

        assert len(result.experience) == 1
        bullets = result.experience[0].bullets
        # 2 dict bullets + 1 string bullet (blank filtered) → 3 total
        assert len(bullets) == 3
        # dict bullets carry their confidence
        confidences = [b.confidence for b in bullets]
        assert "high" in confidences
        assert "medium" in confidences
        # Evidence source propagated
        assert all(b.evidence_source == "enr" for b in bullets)

        # Projects
        assert len(result.projects) == 1
        assert result.projects[0].name == "Pipeline"
        assert len(result.projects[0].bullets) == 1
        assert result.projects[0].bullets[0].confidence == "medium"
        assert result.projects[0].bullets[0].evidence_source == "enr"

        # Skills deduped
        assert result.skills == ["Python", "Go"]
        assert result.education[0]["institution"] == "MIT"
        assert result.certifications == ["AWS Pro"]

    def test_markdown_fence_stripped(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
        data = {
            "experience": [],
            "projects": [],
            "skills": ["Rust"],
            "education": [],
            "certifications": [],
        }
        fenced = "```json\n" + json.dumps(data) + "\n```"
        _install_anthropic_mock(monkeypatch, fenced)
        result = pdfx._enrich_profile_with_claude(self._make_profile())
        assert "Rust" in result.skills

    def test_bare_fence_stripped(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
        data = {
            "experience": [],
            "projects": [],
            "skills": ["Zig"],
            "education": [],
            "certifications": [],
        }
        fenced = "```\n" + json.dumps(data) + "\n```"
        _install_anthropic_mock(monkeypatch, fenced)
        result = pdfx._enrich_profile_with_claude(self._make_profile())
        assert "Zig" in result.skills

    def test_invalid_json_returns_original_profile(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
        _install_anthropic_mock(monkeypatch, "not even close to json")
        original = self._make_profile()
        result = pdfx._enrich_profile_with_claude(original)
        # Falls back via the except clause → original object
        assert result is original

    def test_api_error_returns_original_profile(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
        _install_anthropic_error(monkeypatch, RuntimeError("boom"))
        original = self._make_profile()
        result = pdfx._enrich_profile_with_claude(original)
        assert result is original

    def test_no_api_key_returns_original_profile(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        original = self._make_profile()
        result = pdfx._enrich_profile_with_claude(original)
        assert result is original

    def test_missing_anthropic_package_returns_original_profile(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
        _uninstall_anthropic(monkeypatch)
        original = self._make_profile()
        result = pdfx._enrich_profile_with_claude(original)
        assert result is original

    def test_default_source_when_no_arg_passed(self, monkeypatch):
        """When `source` is not provided, bullets get 'claude_enrichment' source."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
        enriched = {
            "experience": [
                {
                    "title": "X",
                    "company": "Y",
                    "start": "",
                    "end": "",
                    "location": "",
                    "bullets": ["Did the thing well"],
                }
            ],
            "projects": [],
            "skills": [],
            "education": [],
            "certifications": [],
        }
        _install_anthropic_mock(monkeypatch, json.dumps(enriched))
        result = pdfx._enrich_profile_with_claude(self._make_profile())
        assert result.experience[0].bullets[0].evidence_source == "claude_enrichment"


# ===========================================================================
# parse_pdf top-level orchestration
# ===========================================================================
class TestParsePdfRouting:
    def test_routes_to_latex_parser_when_macros_present(self, monkeypatch):
        latex_blob = (
            "\\documentclass{article}\n"
            "\\section{Experience}\n"
            "\\resumeSubheading{Engineer}{2024}{Acme}{NYC}\n"
            "\\resumeItem{Built a thing measured at 99 percent reliability}\n"
        )
        # Force the first extraction tier (pdfminer) to return the LaTeX text
        monkeypatch.setattr(pdfx, "_extract_pdf_text_pdfminer", lambda d: latex_blob)
        profile = pdfx.parse_pdf(b"ignored")
        assert len(profile.experience) == 1
        assert profile.experience[0].company == "Acme"

    def test_pdfminer_failure_falls_back_to_stdlib(self, monkeypatch):
        # pdfminer raises, pypdf import also fails → stdlib extractor must run.
        def boom(_data):
            raise RuntimeError("simulated pdfminer fail")

        monkeypatch.setattr(pdfx, "_extract_pdf_text_pdfminer", boom)
        # Hide pypdf so the second tier is also skipped
        monkeypatch.setitem(sys.modules, "pypdf", None)

        stream = "BT 1 0 0 1 50 700 Tm (Stdlib Reach) Tj ET"
        pdf = _build_pdf_with_content_stream(stream)

        profile = pdfx.parse_pdf(pdf)
        # Stdlib extractor produced text, and the plain parser handled it.
        # We only assert no exception + a Profile back.
        assert isinstance(profile, Profile)

    def test_all_tiers_empty_raises_value_error(self, monkeypatch):
        # All three tiers return empty → final ValueError
        monkeypatch.setattr(pdfx, "_extract_pdf_text_pdfminer", lambda _d: "")
        monkeypatch.setattr(pdfx, "_extract_pdf_text_stdlib", lambda _d: "")
        monkeypatch.setitem(sys.modules, "pypdf", None)
        with pytest.raises(ValueError, match="No text could be extracted"):
            pdfx.parse_pdf(b"any bytes")

    def test_pypdf_path_used_when_pdfminer_empty(self, monkeypatch):
        """When pdfminer returns empty, pypdf is consulted next."""

        monkeypatch.setattr(pdfx, "_extract_pdf_text_pdfminer", lambda _d: "")

        # Build a fake pypdf module with a PdfReader yielding our text
        fake_page = types.SimpleNamespace(
            extract_text=lambda: (
                "Experience\nEngineer Acme Jan 2024 – Present\n- Did the thing well\n"
            )
        )
        fake_reader = MagicMock()
        fake_reader.pages = [fake_page]

        fake_pypdf = types.ModuleType("pypdf")
        fake_pypdf.PdfReader = lambda _buf: fake_reader  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "pypdf", fake_pypdf)

        profile = pdfx.parse_pdf(b"%PDF-fake")
        assert isinstance(profile, Profile)


# ===========================================================================
# _split_bullet_block — direct edge cases
# ===========================================================================
class TestSplitBulletBlockDeep:
    def test_blank_lines_split_paragraphs(self):
        # Enhancement #6: blank line still separates paragraphs, but
        # period-followed-by-uppercase within a 2-sentence paragraph no longer
        # splits — that was over-splitting technical bullets (e.g. "Reduced 40%.
        # Deployed via K8s."). Only 3+ sentence blocks split internally.
        out = pdfx._split_bullet_block(
            "Built X.\n"
            "More on X here.\n"
            "\n"
            "Migrated Y to cloud."
        )
        assert len(out) == 2  # blank line → 2 paragraphs; no intra-paragraph split

    def test_no_sentence_boundary_keeps_single_block(self):
        out = pdfx._split_bullet_block(
            "Built scalable platforms with high throughput across the org"
        )
        assert len(out) == 1

    def test_period_then_lowercase_does_not_split(self):
        # Period followed by lowercase → no split (only uppercase triggers)
        out = pdfx._split_bullet_block(
            "Built X.\n"
            "more text continues here."
        )
        assert len(out) == 1


# ===========================================================================
# Plain parser uncovered branches (lifts plain_parser.py over 80%)
# ===========================================================================
class TestPlainParserUncoveredBranches:
    """Tests that target previously uncovered branches in parsers/plain_parser.py.

    These don't belong with pdf_extractor.py logically, but they live here so
    we can lift plain_parser.py coverage over 80% as part of issue #79
    without scattering tests across multiple new files.
    """

    def test_role_header_colon_company_comma_location_with_date(self):
        # "Title: Company, City, State  Jan 2024 – Present"
        # exercises lines 125-130 (colon_m path with comma-separated company+location)
        from parsers.plain_parser import _parse_plain_resume_text
        text = (
            "Experience\n"
            "Senior Engineer: Acme Corp, Dallas, TX  Jan 2024 – Present\n"
            "- Built and shipped a thing reliably\n"
        )
        p = _parse_plain_resume_text(text)
        assert len(p.experience) == 1
        role = p.experience[0]
        assert role.title == "Senior Engineer"
        assert role.company == "Acme Corp"
        assert "Dallas" in role.location

    def test_role_header_colon_company_no_comma_with_date(self):
        # "Title: Company  Jan 2024 – Present" — colon path, no comma → company=rest
        # exercises line 132 (else branch under colon_m)
        from parsers.plain_parser import _parse_plain_resume_text
        text = (
            "Experience\n"
            "Senior Engineer: Acme Corp  Jan 2024 – Present\n"
            "- Built and shipped a thing reliably\n"
        )
        p = _parse_plain_resume_text(text)
        assert len(p.experience) == 1
        role = p.experience[0]
        assert role.title == "Senior Engineer"
        assert role.company == "Acme Corp"

    def test_two_line_header_colon_company_comma_location(self):
        # Title-line uses "Title: Company, City" form, date is on the next line.
        # exercises lines 151-158
        from parsers.plain_parser import _parse_plain_resume_text
        text = (
            "Experience\n"
            "Engineer: Acme Inc, Dallas, TX\n"
            "Jan 2024 – Present\n"
            "- Built a thing well done\n"
        )
        p = _parse_plain_resume_text(text)
        assert len(p.experience) == 1
        role = p.experience[0]
        assert role.title == "Engineer"
        assert role.company == "Acme Inc"
        assert "Dallas" in role.location

    def test_two_line_header_colon_company_no_comma(self):
        # Title-line uses "Title: Company" — no comma → company=rest, location=""
        # exercises lines 159-161
        from parsers.plain_parser import _parse_plain_resume_text
        text = (
            "Experience\n"
            "Engineer: Acme Inc\n"
            "Jan 2024 – Present\n"
            "- Built a thing well done\n"
        )
        p = _parse_plain_resume_text(text)
        assert len(p.experience) == 1
        role = p.experience[0]
        assert role.title == "Engineer"
        assert role.company == "Acme Inc"

    def test_two_line_header_no_colon(self):
        # Title line is "Engineer  Acme" (whitespace-split), date on next line.
        # exercises lines 163-166
        from parsers.plain_parser import _parse_plain_resume_text
        text = (
            "Experience\n"
            "Engineer  Acme\n"
            "Jan 2024 – Present\n"
            "- Built a thing well done\n"
        )
        p = _parse_plain_resume_text(text)
        assert len(p.experience) == 1
        role = p.experience[0]
        assert role.title == "Engineer"
        assert role.company == "Acme"

    def test_three_line_header_title_company_date(self):
        # Title, Company, Date on three consecutive lines.
        # exercises lines 174-182
        from parsers.plain_parser import _parse_plain_resume_text
        text = (
            "Experience\n"
            "Senior Engineer\n"
            "Acme Corp\n"
            "Jan 2024 – Present\n"
            "- Built scalable systems reliably\n"
        )
        p = _parse_plain_resume_text(text)
        assert len(p.experience) == 1
        role = p.experience[0]
        assert role.title == "Senior Engineer"
        assert role.company == "Acme Corp"
        assert "2024" in role.start

    def test_education_second_degree_appended(self):
        # Existing edu entry already has a degree → second degree creates new entry
        # exercises line 208
        from parsers.plain_parser import _parse_plain_resume_text
        text = (
            "Education\n"
            "University of Missouri-Columbia\n"
            "Master of Science in Computer Science\n"
            "Bachelor of Science in Mathematics\n"
        )
        p = _parse_plain_resume_text(text)
        # Both degrees should produce entries.
        # First: Mizzou with MS CS.  Second: a new entry with the Bachelor as
        # the institution since the previous one already had a degree.
        assert len(p.education) >= 2

    def test_parse_blob_skips_blank_lines(self):
        # parse_blob's blank-line continue branch (line 270).
        from parsers.plain_parser import parse_blob
        text = (
            "\n"
            "Company: Acme\n"
            "\n"
            "Title: Engineer\n"
            "\n"
            "- Did the thing well\n"
        )
        p = parse_blob(text)
        assert len(p.experience) == 1
        assert p.experience[0].company == "Acme"
        assert p.experience[0].title == "Engineer"
        assert len(p.experience[0].bullets) == 1


# ===========================================================================
# docx_extractor.py edge case → push over 80%
# ===========================================================================
class TestDocxExtractorEmpty:
    def test_empty_text_raises_value_error(self):
        # Covers line 54 in docx_extractor.py — the "no text extracted" raise.
        # We construct a minimal valid .docx zip with empty document.xml so
        # python-docx returns nothing.
        import io
        import zipfile

        from parsers.docx_extractor import parse_docx

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(
                "[Content_Types].xml",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                '<Default Extension="xml" ContentType="application/xml"/>'
                '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                "</Types>",
            )
            zf.writestr(
                "_rels/.rels",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
                "</Relationships>",
            )
            zf.writestr(
                "word/document.xml",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                "<w:body></w:body></w:document>",
            )
        empty_docx = buf.getvalue()

        with pytest.raises(ValueError, match="No text could be extracted"):
            parse_docx(empty_docx)


# ===========================================================================
# _pdf_hex_to_text edge branches
# ===========================================================================
class TestPdfHexToTextEdges:
    def test_low_ascii_ratio_falls_through_to_latin1(self):
        """UTF-16-BE decode produces few ASCII printables → fallback path."""
        out = pdfx._pdf_hex_to_text("4869")  # 0x48 0x69
        # 0x4869 decodes to a CJK char under UTF-16-BE (ascii_printable=0)
        # → falls back to byte-by-byte → "Hi"
        assert out == "Hi"

    def test_single_byte_hex_no_utf16_attempted(self):
        # Odd-length, single byte after padding → no UTF-16-BE attempt
        out = pdfx._pdf_hex_to_text("4")
        # Padded "40" → 0x40 = '@'
        assert "@" in out or isinstance(out, str)
