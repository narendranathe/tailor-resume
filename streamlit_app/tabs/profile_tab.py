import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '.claude', 'skills', 'tailor-resume', 'scripts'))
import streamlit as st
from profile_extractor import parse_blob, parse_markdown, parse_latex, parse_linkedin
from text_utils import profile_dict_to_text
from dataclasses import asdict

PARSERS = {"blob": parse_blob, "markdown": parse_markdown, "latex": parse_latex, "linkedin": parse_linkedin}

def render():
    st.header("Your Resume / Work History")
    fmt = st.selectbox("Format", ["blob", "markdown", "latex", "linkedin"])
    text = st.text_area("Paste your resume or work history here", height=300)
    if st.button("Parse Profile", type="primary"):
        if not text.strip():
            st.error("Please paste your resume text.")
            return
        try:
            profile = PARSERS[fmt](text)
            st.session_state.profile_dict = asdict(profile)
            st.session_state.profile_text = profile_dict_to_text(st.session_state.profile_dict)
            st.success("Profile parsed successfully!")
        except Exception as e:
            st.error(f"Parse error: {e}")
    if st.session_state.get("profile_dict"):
        with st.expander("Parsed profile (JSON)", expanded=False):
            st.json(st.session_state.profile_dict)
