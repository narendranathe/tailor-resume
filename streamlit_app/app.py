import sys, os

# Add pipeline scripts to path (absolute so it works on Streamlit Cloud)
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(_HERE)
_SCRIPTS = os.path.join(_REPO, '.claude', 'skills', 'tailor-resume', 'scripts')
_TABS = os.path.join(_HERE, 'tabs')
for _p in (_SCRIPTS, _TABS):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import json
import streamlit as st
from rag_store import SQLiteStore
from text_utils import profile_dict_to_text

st.set_page_config(page_title="tailor-resume", page_icon="📄", layout="wide")

# Init session state
for key in ["profile_dict", "profile_text", "tailored_tex", "ats_score", "gap_report"]:
    if key not in st.session_state:
        st.session_state[key] = None

# ---- Sidebar: Save / Load profiles ----
_store = SQLiteStore()

with st.sidebar:
    st.header("Saved Profiles")

    # Save current profile
    if st.session_state.get("profile_dict"):
        save_name = st.text_input("Save as (name / handle)", key="save_name_input")
        if st.button("💾 Save Profile") and save_name.strip():
            _store.store(save_name.strip(), st.session_state.profile_dict)
            st.success(f"Saved as '{save_name.strip()}'")

    # Load a saved profile
    saved_users = _store.list_users()
    if saved_users:
        selected = st.selectbox("Load saved profile", ["— select —"] + saved_users)
        if st.button("📂 Load") and selected != "— select —":
            results = _store.query(selected, query_text="data engineering", top_k=1)
            if results:
                profile = results[0]["profile"]
                st.session_state.profile_dict = profile
                st.session_state.profile_text = profile_dict_to_text(profile)
                st.success(f"Loaded profile for '{selected}'")
            else:
                st.warning("No stored profile found.")
    else:
        st.caption("No saved profiles yet. Parse a resume and save it here.")

st.title("tailor-resume")
st.caption("ATS-optimized resume tailoring powered by the tailor-resume pipeline")

import profile_tab, tailor_tab, download_tab

tab1, tab2, tab3 = st.tabs(["📄 Profile", "🎯 Tailor", "⬇️ Download"])

with tab1:
    profile_tab.render()
with tab2:
    tailor_tab.render()
with tab3:
    download_tab.render()
