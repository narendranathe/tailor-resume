import streamlit as st

def render():
    st.header("Download Tailored Resume")
    tex = st.session_state.get("tailored_tex")
    score = st.session_state.get("ats_score")
    if tex is None:
        st.info("Complete the Profile and Tailor steps first.")
        return
    if score:
        st.metric("Final ATS Score", f"{score}/100")
    st.download_button(
        label="Download resume.tex",
        data=tex,
        file_name="resume_tailored.tex",
        mime="text/plain",
        type="primary"
    )
    st.caption("Upload the .tex file to [Overleaf](https://overleaf.com) to compile to PDF.")
