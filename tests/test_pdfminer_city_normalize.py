"""
Regression tests for issue #111:

pdfminer.six occasionally inserts a stray space inside an extracted word when
the source PDF uses a 2-column layout for the role header (company on the
left, location on the right).  The most reproducible instance is
``"Dallas"`` → ``"Dal las"``.

The fix is a deterministic, one-pass dictionary lookup applied to the text
returned by ``_extract_pdf_text_pdfminer`` before it is handed to the plain
text parser.  These tests cover:

1. ``_normalize_pdfminer_split_cities`` rejoins known split city tokens.
2. ``_parse_plain_resume_text`` produces ``location == "Dallas, TX"`` for the
   ``Naren_citi.pdf`` reproduction case once the fix is in place.
3. The normalizer is a no-op on text that has no known split tokens.
"""
from __future__ import annotations

import sys
from pathlib import Path


SCRIPTS_DIR = (
    Path(__file__).parent.parent
    / ".claude"
    / "skills"
    / "tailor-resume"
    / "scripts"
)
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


class TestNormalizePdfminerSplitCities:
    def test_rejoins_dallas(self):
        from parsers.pdf_extractor import _normalize_pdfminer_split_cities

        assert _normalize_pdfminer_split_cities("Dal las, TX") == "Dallas, TX"

    def test_rejoins_rolla(self):
        from parsers.pdf_extractor import _normalize_pdfminer_split_cities

        assert _normalize_pdfminer_split_cities("Rol la, MO") == "Rolla, MO"

    def test_rejoins_multiline(self):
        from parsers.pdf_extractor import _normalize_pdfminer_split_cities

        text = (
            "Acme Corp Dal las, TX\n"
            "Mizzou Rol la, MO\n"
            "Austin office: Au stin, TX\n"
        )
        out = _normalize_pdfminer_split_cities(text)
        assert "Dallas, TX" in out
        assert "Rolla, MO" in out
        assert "Austin, TX" in out
        # Make sure no split form remains.
        assert "Dal las" not in out
        assert "Rol la" not in out
        assert "Au stin" not in out

    def test_no_op_on_clean_text(self):
        from parsers.pdf_extractor import _normalize_pdfminer_split_cities

        clean = "Acme Corp Dallas, TX\nMizzou Rolla, MO\n"
        assert _normalize_pdfminer_split_cities(clean) == clean

    def test_no_op_on_empty(self):
        from parsers.pdf_extractor import _normalize_pdfminer_split_cities

        assert _normalize_pdfminer_split_cities("") == ""

    def test_does_not_join_substring_of_other_word(self):
        from parsers.pdf_extractor import _normalize_pdfminer_split_cities

        # "Pedal las" should not be rewritten — the dictionary uses
        # whole-token (word-boundary) matching so a preceding letter prevents
        # the rejoin.
        out = _normalize_pdfminer_split_cities("Pedal las machines")
        assert out == "Pedal las machines"


class TestParserUsesCityNormalization:
    """End-to-end: a pdfminer-style resume blob with ``Dal las, TX`` must
    produce ``location == "Dallas, TX"`` after the pdfminer extractor runs
    its normalization pass.

    The parser is plain-text, so we simulate the pdfminer post-processing
    by invoking ``_normalize_pdfminer_split_cities`` ourselves (this is
    exactly what ``_extract_pdf_text_pdfminer`` now does internally).
    """

    def test_dallas_split_rejoined_in_role_location(self):
        from parsers.pdf_extractor import _normalize_pdfminer_split_cities
        from parsers.plain_parser import _parse_plain_resume_text

        # Faithful reproduction of the Naren_citi.pdf pdfminer output:
        # 2-line role header (title / company+loc) followed by date line
        # then bullets.
        raw_pdfminer_text = (
            "Experience\n"
            "Software Engineer\n"
            "Citi  Dal las, TX\n"
            "Jan 2022 – Present\n"
            "- Built distributed services\n"
        )
        # Step 1: pdfminer post-processing must rejoin the split city.
        cleaned = _normalize_pdfminer_split_cities(raw_pdfminer_text)
        # Step 2: parser sees the rejoined text and extracts the location.
        profile = _parse_plain_resume_text(cleaned, source="t")
        assert len(profile.experience) == 1
        assert profile.experience[0].location == "Dallas, TX"
        assert profile.experience[0].company == "Citi"
