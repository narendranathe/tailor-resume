"""Tests for claude_vision_extractor.py - Tier-0 Claude vision/document extractor.

All tests mock the Anthropic SDK at the import boundary via ``sys.modules``.
No real API calls are ever issued.
"""
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Make scripts/ importable
SCRIPTS_DIR = Path(__file__).parent.parent / ".claude" / "skills" / "tailor-resume" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import claude_vision_extractor as cve  # noqa: E402

VISION_FIXTURES = Path(__file__).parent / "fixtures" / "vision"
SAMPLE_PNG = VISION_FIXTURES / "sample.png"

# Dummy non-credential placeholder used purely to satisfy the env-var check.
# The mocked SDK never validates this string.
FAKE_KEY = "test-fake-placeholder-not-a-credential"
ALT_KEY = "another-fake-placeholder-value"


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------
def _install_anthropic_mock(monkeypatch, response_text: str) -> MagicMock:
    """Inject a fake ``anthropic`` module returning ``response_text`` from messages.create."""
    mock_resp = MagicMock()
    mock_resp.content = [MagicMock(text=response_text)]

    mock_anthropic = MagicMock()
    mock_anthropic.Anthropic.return_value.messages.create.return_value = mock_resp
    monkeypatch.setitem(sys.modules, "anthropic", mock_anthropic)
    return mock_anthropic


def _install_anthropic_error(monkeypatch, exc: Exception) -> MagicMock:
    """Inject a fake ``anthropic`` module that raises ``exc`` on messages.create."""
    mock_anthropic = MagicMock()
    mock_anthropic.Anthropic.return_value.messages.create.side_effect = exc
    monkeypatch.setitem(sys.modules, "anthropic", mock_anthropic)
    return mock_anthropic


def _uninstall_anthropic(monkeypatch) -> None:
    """Force the ``anthropic`` import inside ``_build_client`` to fail."""
    monkeypatch.setitem(sys.modules, "anthropic", None)


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------
class TestModuleConstants:
    def test_supported_extensions_contains_pdf_and_images(self):
        assert ".pdf" in cve.SUPPORTED_EXTENSIONS
        assert ".png" in cve.SUPPORTED_EXTENSIONS
        assert ".jpg" in cve.SUPPORTED_EXTENSIONS
        assert ".jpeg" in cve.SUPPORTED_EXTENSIONS
        assert ".gif" in cve.SUPPORTED_EXTENSIONS
        assert ".webp" in cve.SUPPORTED_EXTENSIONS

    def test_extension_to_media_type_mapping(self):
        assert cve._EXTENSION_TO_MEDIA_TYPE[".pdf"] == "application/pdf"
        assert cve._EXTENSION_TO_MEDIA_TYPE[".png"] == "image/png"
        assert cve._EXTENSION_TO_MEDIA_TYPE[".jpg"] == "image/jpeg"
        assert cve._EXTENSION_TO_MEDIA_TYPE[".jpeg"] == "image/jpeg"

    def test_extraction_prompt_is_well_formed(self):
        # Prompt assembly assertion: required schema sections present
        prompt = cve._EXTRACTION_PROMPT
        assert "experience" in prompt
        assert "projects" in prompt
        assert "education" in prompt
        assert "skills" in prompt
        assert "certifications" in prompt
        assert "summary" in prompt
        assert "JSON" in prompt
        assert "VERBATIM" in prompt


# ---------------------------------------------------------------------------
# _build_client
# ---------------------------------------------------------------------------
class TestBuildClient:
    def test_uses_env_var_when_no_api_key_passed(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
        mock_anthropic = _install_anthropic_mock(monkeypatch, "{}")

        client = cve._build_client()

        mock_anthropic.Anthropic.assert_called_once_with(api_key=FAKE_KEY)
        assert client is mock_anthropic.Anthropic.return_value

    def test_explicit_api_key_overrides_env(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
        mock_anthropic = _install_anthropic_mock(monkeypatch, "{}")

        cve._build_client(api_key=ALT_KEY)

        mock_anthropic.Anthropic.assert_called_once_with(api_key=ALT_KEY)

    def test_missing_key_raises_value_error(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        _install_anthropic_mock(monkeypatch, "{}")

        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
            cve._build_client()

    def test_missing_anthropic_package_raises_import_error(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
        _uninstall_anthropic(monkeypatch)

        with pytest.raises(ImportError, match="anthropic package is required"):
            cve._build_client()


# ---------------------------------------------------------------------------
# _encode_file
# ---------------------------------------------------------------------------
class TestEncodeFile:
    def test_encodes_png_returns_base64_and_media_type(self):
        b64_data, media_type = cve._encode_file(str(SAMPLE_PNG))

        assert media_type == "image/png"
        assert isinstance(b64_data, str)
        # Round-trip decode must succeed and yield the original bytes
        decoded = base64.standard_b64decode(b64_data)
        assert decoded == SAMPLE_PNG.read_bytes()
        # Must be a valid PNG (signature preserved)
        assert decoded.startswith(b"\x89PNG\r\n\x1a\n")

    def test_encodes_pdf_uses_application_pdf(self, tmp_path):
        pdf_path = tmp_path / "tiny.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\n%%EOF\n")

        b64_data, media_type = cve._encode_file(str(pdf_path))

        assert media_type == "application/pdf"
        assert base64.standard_b64decode(b64_data) == b"%PDF-1.4\n%%EOF\n"

    def test_encodes_jpg_uses_image_jpeg(self, tmp_path):
        jpg_path = tmp_path / "photo.jpg"
        jpg_path.write_bytes(b"\xff\xd8\xff\xe0fake-jpeg")

        _, media_type = cve._encode_file(str(jpg_path))
        assert media_type == "image/jpeg"

    def test_uppercase_extension_is_normalized(self, tmp_path):
        png_path = tmp_path / "RESUME.PNG"
        png_path.write_bytes(SAMPLE_PNG.read_bytes())

        _, media_type = cve._encode_file(str(png_path))
        assert media_type == "image/png"

    def test_missing_file_raises_file_not_found(self):
        with pytest.raises(FileNotFoundError, match="File not found"):
            cve._encode_file("/no/such/path/does_not_exist.pdf")

    def test_unsupported_extension_raises_value_error(self, tmp_path):
        bad = tmp_path / "resume.docx"
        bad.write_bytes(b"PK\x03\x04")  # zip header for docx

        with pytest.raises(ValueError, match="Unsupported file type"):
            cve._encode_file(str(bad))


# ---------------------------------------------------------------------------
# _build_content_block
# ---------------------------------------------------------------------------
class TestBuildContentBlock:
    def test_pdf_returns_document_block(self):
        block = cve._build_content_block("BASE64DATA", "application/pdf")
        assert block == {
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": "BASE64DATA",
            },
        }

    def test_png_returns_image_block(self):
        block = cve._build_content_block("PNGB64", "image/png")
        assert block["type"] == "image"
        assert block["source"]["media_type"] == "image/png"
        assert block["source"]["data"] == "PNGB64"

    def test_jpeg_returns_image_block(self):
        block = cve._build_content_block("JPGB64", "image/jpeg")
        assert block["type"] == "image"
        assert block["source"]["media_type"] == "image/jpeg"


# ---------------------------------------------------------------------------
# _parse_response
# ---------------------------------------------------------------------------
class TestParseResponse:
    def test_clean_json_parses(self):
        result = cve._parse_response('{"experience": [], "skills": []}')
        assert result == {"experience": [], "skills": []}

    def test_strips_markdown_fences(self):
        wrapped = "```json\n{\"summary\": \"hello\"}\n```"
        assert cve._parse_response(wrapped) == {"summary": "hello"}

    def test_strips_bare_triple_backtick_fences(self):
        wrapped = "```\n{\"a\": 1}\n```"
        assert cve._parse_response(wrapped) == {"a": 1}

    def test_strips_leading_and_trailing_whitespace(self):
        assert cve._parse_response("   \n{\"x\": 2}\n   ") == {"x": 2}

    def test_invalid_json_raises_value_error(self):
        with pytest.raises(ValueError, match="invalid JSON"):
            cve._parse_response("not valid json {")

    def test_empty_string_raises_value_error(self):
        with pytest.raises(ValueError, match="invalid JSON"):
            cve._parse_response("")

    def test_partial_json_raises_value_error(self):
        with pytest.raises(ValueError, match="invalid JSON"):
            cve._parse_response('{"experience": [{"title": "Engineer"')


# ---------------------------------------------------------------------------
# extract_from_bytes
# ---------------------------------------------------------------------------
class TestExtractFromBytes:
    def test_returns_parsed_profile_for_image(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
        payload = {
            "experience": [
                {"title": "Data Engineer", "company": "Acme", "bullets": []}
            ],
            "projects": [],
            "education": [],
            "skills": {},
            "certifications": [],
            "summary": "ETL specialist",
        }
        mock_anthropic = _install_anthropic_mock(monkeypatch, json.dumps(payload))

        result = cve.extract_from_bytes(b"\x89PNGfake", "image/png")

        assert result == payload

        # Verify the SDK call shape: model + max_tokens + content blocks
        create_call = mock_anthropic.Anthropic.return_value.messages.create
        create_call.assert_called_once()
        kwargs = create_call.call_args.kwargs
        assert kwargs["model"] == "claude-sonnet-4-6"
        assert kwargs["max_tokens"] == 4096
        messages = kwargs["messages"]
        assert messages[0]["role"] == "user"
        # First content block is the file (image), second is the prompt text
        content_blocks = messages[0]["content"]
        assert len(content_blocks) == 2
        assert content_blocks[0]["type"] == "image"
        assert content_blocks[0]["source"]["media_type"] == "image/png"
        # Image data is base64 of original bytes
        assert base64.standard_b64decode(content_blocks[0]["source"]["data"]) == b"\x89PNGfake"
        assert content_blocks[1]["type"] == "text"
        assert content_blocks[1]["text"] == cve._EXTRACTION_PROMPT

    def test_pdf_uses_document_block(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
        mock_anthropic = _install_anthropic_mock(monkeypatch, "{}")

        cve.extract_from_bytes(b"%PDF-1.4 fake", "application/pdf")

        kwargs = mock_anthropic.Anthropic.return_value.messages.create.call_args.kwargs
        assert kwargs["messages"][0]["content"][0]["type"] == "document"
        assert kwargs["messages"][0]["content"][0]["source"]["media_type"] == "application/pdf"

    def test_custom_model_is_forwarded(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
        mock_anthropic = _install_anthropic_mock(monkeypatch, "{}")

        cve.extract_from_bytes(b"data", "image/png", model="claude-opus-4-6")

        kwargs = mock_anthropic.Anthropic.return_value.messages.create.call_args.kwargs
        assert kwargs["model"] == "claude-opus-4-6"

    def test_explicit_api_key_passed_to_client(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        mock_anthropic = _install_anthropic_mock(monkeypatch, "{}")

        cve.extract_from_bytes(b"data", "image/png", api_key=ALT_KEY)

        mock_anthropic.Anthropic.assert_called_once_with(api_key=ALT_KEY)

    def test_malformed_json_response_raises_value_error(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
        _install_anthropic_mock(monkeypatch, "this is not json at all")

        with pytest.raises(ValueError, match="invalid JSON"):
            cve.extract_from_bytes(b"data", "image/png")

    def test_api_error_propagates(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
        _install_anthropic_error(monkeypatch, RuntimeError("API timeout"))

        with pytest.raises(RuntimeError, match="API timeout"):
            cve.extract_from_bytes(b"data", "image/png")


# ---------------------------------------------------------------------------
# extract_from_file
# ---------------------------------------------------------------------------
class TestExtractFromFile:
    def test_extracts_from_png_file(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
        payload = {"experience": [], "projects": [], "skills": [], "summary": "hi"}
        mock_anthropic = _install_anthropic_mock(monkeypatch, json.dumps(payload))

        result = cve.extract_from_file(str(SAMPLE_PNG))

        assert result == payload
        kwargs = mock_anthropic.Anthropic.return_value.messages.create.call_args.kwargs
        assert kwargs["messages"][0]["content"][0]["source"]["media_type"] == "image/png"

    def test_extracts_from_pdf_file(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
        pdf = tmp_path / "resume.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake content")
        mock_anthropic = _install_anthropic_mock(monkeypatch, "{}")

        cve.extract_from_file(str(pdf))

        kwargs = mock_anthropic.Anthropic.return_value.messages.create.call_args.kwargs
        assert kwargs["messages"][0]["content"][0]["type"] == "document"

    def test_missing_file_raises_file_not_found(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
        _install_anthropic_mock(monkeypatch, "{}")

        with pytest.raises(FileNotFoundError):
            cve.extract_from_file("/does/not/exist.pdf")

    def test_unsupported_file_type_raises_value_error(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
        bad = tmp_path / "resume.txt"
        bad.write_bytes(b"plain text resume")

        with pytest.raises(ValueError, match="Unsupported file type"):
            cve.extract_from_file(str(bad))


# ---------------------------------------------------------------------------
# CLI (main)
# ---------------------------------------------------------------------------
class TestCLI:
    def test_writes_output_file_when_output_flag_given(self, monkeypatch, tmp_path, capsys):
        monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
        payload = {
            "experience": [
                {"title": "DE", "company": "X", "bullets": [{"text": "b1"}, {"text": "b2"}]}
            ],
            "projects": [{"name": "P1"}],
        }
        _install_anthropic_mock(monkeypatch, json.dumps(payload))

        out_path = tmp_path / "profile.json"
        monkeypatch.setattr(
            sys, "argv",
            ["claude_vision_extractor.py", "--input", str(SAMPLE_PNG), "--output", str(out_path)],
        )

        cve.main()

        # Output file written and contains parsed JSON
        written = json.loads(out_path.read_text(encoding="utf-8"))
        assert written == payload

        # Status messages go to stderr
        captured = capsys.readouterr()
        assert "Tier-0 extraction" in captured.err
        assert "Written to" in captured.err
        assert "1 roles" in captured.err
        assert "1 projects" in captured.err
        assert "2 bullets" in captured.err

    def test_prints_to_stdout_when_no_output_flag(self, monkeypatch, capsys):
        monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
        payload = {"experience": [], "summary": "hi"}
        _install_anthropic_mock(monkeypatch, json.dumps(payload))

        monkeypatch.setattr(
            sys, "argv",
            ["claude_vision_extractor.py", "--input", str(SAMPLE_PNG)],
        )

        cve.main()

        out = capsys.readouterr().out
        assert json.loads(out) == payload

    def test_custom_model_flag_is_forwarded(self, monkeypatch, capsys):
        monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
        mock_anthropic = _install_anthropic_mock(monkeypatch, "{}")

        monkeypatch.setattr(
            sys, "argv",
            [
                "claude_vision_extractor.py",
                "--input", str(SAMPLE_PNG),
                "--model", "claude-opus-4-6",
            ],
        )

        cve.main()

        kwargs = mock_anthropic.Anthropic.return_value.messages.create.call_args.kwargs
        assert kwargs["model"] == "claude-opus-4-6"
        assert "Model: claude-opus-4-6" in capsys.readouterr().err

    def test_api_key_flag_is_forwarded(self, monkeypatch, capsys):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        mock_anthropic = _install_anthropic_mock(monkeypatch, "{}")

        monkeypatch.setattr(
            sys, "argv",
            [
                "claude_vision_extractor.py",
                "--input", str(SAMPLE_PNG),
                "--api-key", ALT_KEY,
            ],
        )

        cve.main()

        mock_anthropic.Anthropic.assert_called_once_with(api_key=ALT_KEY)

    def test_missing_input_flag_exits_with_error(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["claude_vision_extractor.py"])
        with pytest.raises(SystemExit):
            cve.main()

    def test_file_not_found_propagates(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
        _install_anthropic_mock(monkeypatch, "{}")

        monkeypatch.setattr(
            sys, "argv",
            ["claude_vision_extractor.py", "--input", "/nope/missing.pdf"],
        )

        with pytest.raises(FileNotFoundError):
            cve.main()
