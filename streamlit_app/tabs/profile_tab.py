import sys, os

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(_HERE))
_SCRIPTS = os.path.join(_REPO, '.claude', 'skills', 'tailor-resume', 'scripts')
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import importlib
import streamlit as st
from text_utils import profile_dict_to_text
from dataclasses import asdict

# Force profile_extractor to load from _SCRIPTS path so we always get the
# latest version even if tailor_resume/__init__.py already cached an older one.
if "profile_extractor" in sys.modules and not hasattr(sys.modules["profile_extractor"], "parse_pdf"):
    del sys.modules["profile_extractor"]

from profile_extractor import (
    parse_blob, parse_markdown, parse_latex, parse_linkedin,
    parse_pdf, parse_docx, auto_detect_format,
)

_TEXT_PARSERS = {
    "auto": None,
    "latex (.tex)": parse_latex,
    "markdown": parse_markdown,
    "blob (plain text)": parse_blob,
    "linkedin pdf text": parse_linkedin,
}

_FILE_EXT_MAP = {
    ".tex": "latex (.tex)",
    ".md": "markdown",
    ".txt": "blob (plain text)",
}


def render():
    st.header("Your Resume / Work History")

    input_mode = st.radio("Input method", ["Upload file", "Paste text"], horizontal=True)

    profile = None

    # ---- File upload -------------------------------------------------------
    if input_mode == "Upload file":
        uploaded = st.file_uploader(
            "Upload your resume",
            type=["tex", "md", "txt", "pdf", "docx", "doc"],
            help="Supports LaTeX (.tex), Markdown (.md), plain text (.txt), PDF, and Word (.docx/.doc)",
        )
        if uploaded:
            ext = os.path.splitext(uploaded.name)[1].lower()
            st.caption(f"Detected file: `{uploaded.name}`")

            if st.button("Parse Resume", type="primary"):
                try:
                    raw = uploaded.read()
                    if ext == ".pdf":
                        profile = parse_pdf(raw, source="pdf_upload")
                    elif ext in (".docx", ".doc"):
                        profile = parse_docx(raw, source="docx_upload")
                    else:
                        text = raw.decode("utf-8", errors="replace")
                        fmt = _FILE_EXT_MAP.get(ext, "auto")
                        if fmt == "auto":
                            fmt_key = auto_detect_format(text)
                        else:
                            fmt_key = fmt.split()[0]  # "latex", "markdown", "blob"
                        parsers = {
                            "latex": parse_latex,
                            "markdown": parse_markdown,
                            "blob": parse_blob,
                            "linkedin": parse_linkedin,
                        }
                        profile = parsers.get(fmt_key, parse_blob)(text)
                except ImportError as e:
                    st.error(f"Missing dependency: {e}")
                    return
                except Exception as e:
                    st.error(f"Parse error: {e}")
                    return

    # ---- Paste text --------------------------------------------------------
    else:
        fmt_label = st.selectbox(
            "Format",
            list(_TEXT_PARSERS.keys()),
            help="'auto' detects LaTeX vs Markdown vs plain text automatically",
        )
        text = st.text_area("Paste your resume or work history here", height=300)

        if st.button("Parse Profile", type="primary"):
            if not text.strip():
                st.error("Please paste your resume text.")
                return
            try:
                if fmt_label == "auto":
                    detected = auto_detect_format(text)
                    st.caption(f"Auto-detected format: **{detected}**")
                    parsers = {"latex": parse_latex, "markdown": parse_markdown, "blob": parse_blob}
                    profile = parsers.get(detected, parse_blob)(text)
                else:
                    profile = _TEXT_PARSERS[fmt_label](text)
            except Exception as e:
                st.error(f"Parse error: {e}")
                return

    # ---- Store and display result ------------------------------------------
    if profile is not None:
        d = asdict(profile)
        n_roles = len(d.get("experience", []))
        n_bullets = sum(len(r.get("bullets", [])) for r in d.get("experience", []))
        n_skills = len(d.get("skills", []))
        n_projects = len(d.get("projects", []))

        if n_roles == 0 and n_bullets == 0 and n_skills == 0:
            st.warning(
                "Parser found 0 roles and 0 skills. "
                "If you pasted LaTeX, make sure to select format **'auto'** or **'latex (.tex)'**. "
                "If pasting PDF text, try the 'blob (plain text)' format."
            )
        else:
            st.session_state.profile_dict = d
            st.session_state.profile_text = profile_dict_to_text(d)
            st.success(
                f"Parsed: **{n_roles}** roles, **{n_bullets}** bullets, "
                f"**{n_skills}** skills, **{n_projects}** projects"
            )

    if st.session_state.get("profile_dict"):
        with st.expander("Parsed profile (JSON)", expanded=False):
            st.json(st.session_state.profile_dict)
