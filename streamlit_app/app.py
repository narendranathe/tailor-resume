import sys
import os

# ---------------------------------------------------------------------------
# Load .env from repo root (ANTHROPIC_API_KEY for Claude-based PDF parsing)
# ---------------------------------------------------------------------------
_ROOT_ENV = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
if os.path.exists(_ROOT_ENV):
    with open(_ROOT_ENV) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip().strip("\"'"))

# ---------------------------------------------------------------------------
# Path setup — must happen before any local imports
# Tries .claude/skills path first (local dev), falls back to tailor_resume/_scripts
# (installed package path), so the app works in both environments.
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(_HERE)

_SCRIPTS_CANDIDATES = [
    os.path.join(_REPO, ".claude", "skills", "tailor-resume", "scripts"),
    os.path.join(_REPO, "tailor_resume", "_scripts"),
]
for _p in _SCRIPTS_CANDIDATES:
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

_TABS = os.path.join(_HERE, "tabs")
if _TABS not in sys.path:
    sys.path.insert(0, _TABS)

# ---------------------------------------------------------------------------
# Streamlit must be imported before any st.* calls
# ---------------------------------------------------------------------------
import streamlit as st

st.set_page_config(page_title="tailor-resume", page_icon="📄", layout="wide")

# ---------------------------------------------------------------------------
# Import pipeline modules — show a clear error if anything is missing
# ---------------------------------------------------------------------------
try:
    from rag_store import SQLiteStore
    from text_utils import profile_dict_to_text
except Exception as _e:
    _searched = "\n".join(f"  • {p}" for p in _SCRIPTS_CANDIDATES)
    st.error(
        f"**Startup failed — could not import pipeline modules.**\n\n"
        f"`{_e}`\n\n"
        f"Searched:\n{_searched}\n\n"
        f"If you're on Streamlit Cloud, click **Manage app → Reboot app** to force a "
        f"fresh environment build."
    )
    st.stop()

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
for _key in ["profile_dict", "profile_text", "tailored_tex", "ats_score", "gap_report"]:
    if _key not in st.session_state:
        st.session_state[_key] = None

# ---------------------------------------------------------------------------
# Sidebar: Save / Load profiles
# ---------------------------------------------------------------------------
try:
    _store = SQLiteStore()
except Exception as _e:
    _store = None
    st.sidebar.warning(f"Profile storage unavailable: {_e}")

with st.sidebar:
    st.header("Saved Profiles")

    if _store and st.session_state.get("profile_dict"):
        save_name = st.text_input("Save as (name / handle)", key="save_name_input")
        if st.button("💾 Save Profile") and save_name.strip():
            _store.store(save_name.strip(), st.session_state.profile_dict)
            st.success(f"Saved as '{save_name.strip()}'")

    if _store:
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

# ---------------------------------------------------------------------------
# Main content
# ---------------------------------------------------------------------------
st.title("tailor-resume")
st.caption("ATS-optimized resume tailoring powered by the tailor-resume pipeline")

try:
    import profile_tab
    import tailor_tab
    import download_tab
except Exception as _e:
    st.error(
        f"**Could not load app tabs.**\n\n`{_e}`\n\n"
        f"Check that `profile_tab.py`, `tailor_tab.py`, and `download_tab.py` "
        f"exist in `streamlit_app/tabs/` and that all imports in those files succeed."
    )
    st.stop()

tab1, tab2, tab3 = st.tabs(["📄 Profile", "🎯 Tailor", "⬇️ Download"])

with tab1:
    profile_tab.render()
with tab2:
    tailor_tab.render()
with tab3:
    download_tab.render()
