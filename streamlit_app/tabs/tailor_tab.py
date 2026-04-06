import sys
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(_HERE))

for _p in [
    os.path.join(_REPO, ".claude", "skills", "tailor-resume", "scripts"),
    os.path.join(_REPO, "tailor_resume", "_scripts"),
]:
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

import streamlit as st
from jd_gap_analyzer import run_analysis
from latex_renderer import build_from_profile
from dataclasses import asdict
import tempfile
from pathlib import Path

def render():
    st.header("Tailor to Job Description")
    if not st.session_state.get("profile_dict"):
        st.warning("Go to the Profile tab first and parse your resume.")
        return
    jd = st.text_area("Paste the Job Description here", height=250)
    name = st.text_input("Your name (for resume header)", value="")
    email = st.text_input("Email", value="")
    if st.button("Analyse & Tailor", type="primary"):
        if not jd.strip():
            st.error("Please paste a job description.")
            return
        profile_text = st.session_state.get("profile_text", "")
        try:
            report = asdict(run_analysis(jd, profile_text))
            score = report["ats_score_estimate"]
            st.session_state.ats_score = score
            st.session_state.gap_report = report
            col1, col2 = st.columns(2)
            col1.metric("ATS Score", f"{score}/100", delta=f"{'Same role target: 97+' if score >= 80 else 'Overlapping role: 90+' if score >= 60 else 'Low alignment'}")
            if score < 50:
                st.error("This role doesn't align with your profile (ATS: {}/100). Generating a resume would require fabrication.".format(score))
                st.session_state.tailored_tex = None
                return
            if report.get("top_missing"):
                st.subheader("Top Gaps")
                rows = [{"Category": g["category"], "Coverage": f"{g['resume_coverage']:.0%}", "Priority": g["priority"]} for g in report["top_missing"]]
                st.dataframe(rows, use_container_width=True)
            # Build .tex — build_from_profile writes to a file, so use a temp path then read back
            profile = st.session_state.profile_dict
            header = {"name": name or "Candidate", "email": email or ""}
            try:
                tmpl_path = os.path.join(_REPO, '.claude', 'skills', 'tailor-resume', 'templates', 'resume_template.tex')
                with tempfile.NamedTemporaryFile(suffix='.tex', delete=False, mode='w') as tf:
                    tmp_path = tf.name
                build_from_profile(profile, template_path=tmpl_path, output_path=tmp_path, header=header)
                tex = Path(tmp_path).read_text(encoding='utf-8')
                os.unlink(tmp_path)
                st.session_state.tailored_tex = tex
                st.success("Resume tailored! Go to the Download tab.")
            except Exception as e:
                st.warning(f"LaTeX render note: {e}")
        except Exception as e:
            st.error(f"Analysis error: {e}")
