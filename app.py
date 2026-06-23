# user_masters/app.py
"""
Thin orchestrator — delegates all heavy UI work to dedicated modules:
  • ui.state_manager  – session-state defaults
  • ui.sidebar        – sidebar rendering
  • ui.data_grid      – AgGrid + grid controls + download
  • ui.ai_assistant   – AI command panel  (called from data_grid)
"""
import streamlit as st
import pandas as pd
import os
import logging
import toml

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler()]
)

from ai.openai_service import openai_extract_users, local_extract_users, _merge_duplicate_users
from utils.history import _update_users_hash

log = logging.getLogger(__name__)

# --- PAGE CONFIG ---
st.set_page_config(
    page_title="User Master Intelligence",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- CUSTOM CSS ---
from utils.styles import GLOBAL_CSS
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)

# --- STATE INIT ---
from ui.state_manager import init_session_state
init_session_state()

# --- HEADER ---
st.markdown("""
<div class="premium-header">
    <h1>User Master Intelligence</h1>
</div>
""", unsafe_allow_html=True)

# --- SIDEBAR ---
from ui.sidebar import render_sidebar
navigation = render_sidebar()

# --- NAVIGATION SWITCH CONFIRMATION ---
def confirm_switch_callback():
    # Clear all data keys
    for key in ['df_users', 'segregation_dfs', 'segregation_view_choice', 'prev_segregation_view_choice', 'uploaded_files', '_df_users_hash', '_ai_preview']:
        if key in st.session_state:
            del st.session_state[key]
    if "pending_nav" in st.session_state:
        pending = st.session_state.pending_nav
        st.session_state.previous_nav = pending
        st.session_state.nav_radio_key = pending
        del st.session_state.pending_nav

def cancel_switch_callback():
    if "pending_nav" in st.session_state:
        del st.session_state["pending_nav"]

if "pending_nav" in st.session_state:
    pending = st.session_state.pending_nav
    st.warning(f"⚠️ **Warning**: You are switching from **{st.session_state.previous_nav}** to **{pending}**. This will clear your current table and session data.")
    col_yes, col_no = st.columns(2)
    col_yes.button("✅ Yes, Switch & Reset Data", type="primary", use_container_width=True, on_click=confirm_switch_callback)
    col_no.button("❌ No, Keep My Data", use_container_width=True, on_click=cancel_switch_callback)
    st.stop()
else:
    st.session_state.previous_nav = navigation

# --- MAIN LOGIC ---
srcs = None

if navigation == "Update User":
    st.info("Update User functionality is coming soon!")
    st.stop()

if navigation == "New User":
    st.markdown("### Step 1: Upload User List(s)")
    srcs = st.file_uploader("Upload an Excel or CSV file to begin automated extraction", accept_multiple_files=True, key="user_file_uploader")
    if srcs:
        st.session_state["uploaded_files"] = srcs
    elif "uploaded_files" in st.session_state:
        srcs = st.session_state["uploaded_files"]
        if srcs:
            st.success(f"📂 **{len(srcs)} file(s)** active")

elif navigation == "Both (Segregation New & Existing Users)":
    from segregation import render_segregation_ui
    render_segregation_ui()

    if 'segregation_dfs' in st.session_state and 'segregation_view_choice' in st.session_state:
        current_choice = st.session_state['segregation_view_choice']

        # If we were previously editing a DIFFERENT choice, save df_users back!
        if 'prev_segregation_view_choice' in st.session_state and 'df_users' in st.session_state:
            prev_choice = st.session_state['prev_segregation_view_choice']
            if prev_choice != current_choice:
                st.session_state['segregation_dfs'][prev_choice] = st.session_state['df_users'].copy()

        # Now, load the newly selected choice into df_users if it changed
        if st.session_state.get('prev_segregation_view_choice') != current_choice:
            st.session_state['df_users'] = st.session_state['segregation_dfs'][current_choice].copy()
            st.session_state['prev_segregation_view_choice'] = current_choice

            # CRITICAL: Force AgGrid to remount completely
            if 'grid_key' in st.session_state:
                st.session_state.grid_key += 1
            _update_users_hash()
    else:
        st.stop()

# --- API KEY ---
api_key = st.secrets.get("OPENAI_API_KEY", "") or st.secrets.get("GEMINI_API_KEY", "")
if not api_key:
    try:
        secrets_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".streamlit", "secrets.toml")
        if os.path.exists(secrets_path):
            secrets_data = toml.load(secrets_path)
            api_key = secrets_data.get("OPENAI_API_KEY", "") or secrets_data.get("GEMINI_API_KEY", "")
    except Exception:
        pass

# --- EXTRACTION ---
user_intent = st.session_state.get("user_intent", "")
pass_prefix = st.session_state.get("pass_prefix", "Med")

if srcs:
    if st.button("🚀 Process User Data", type="primary"):
        with st.status(f"🧠 Analyzing {len(srcs)} Document(s)...", expanded=True) as status:
            all_dfs = []
            ai_triggered_files = []
            local_extracted_files = []

            for src in srcs:
                file_bytes = src.getvalue()
                filename = src.name

                st.write(f"🔍 Parsing layout locally: {filename}...")
                df_local = local_extract_users(file_bytes, filename, pass_prefix, user_intent)

                needs_ai = False
                reason = ""
                if user_intent and str(user_intent).strip():
                    needs_ai = True
                    reason = "User specified custom extraction rules"
                elif filename.lower().endswith(('.pdf', '.docx', '.doc')):
                    needs_ai = True
                    reason = "Document requires layout-aware PDF/Word parsing"
                elif df_local is not None and not df_local.empty:
                    for col in ['firstName', 'lastName', 'employeeId']:
                        if col in df_local.columns:
                            if df_local[col].astype(str).str.contains('|', regex=False).any():
                                needs_ai = True
                                reason = "Delimited multi-user cells detected"
                                break

                if needs_ai and api_key:
                    st.write(f"🧠 Complex format: Running AI Extraction ({reason})...")
                    df_result = openai_extract_users(file_bytes, filename, api_key, user_intent, pass_prefix)
                    if df_result is not None and not df_result.empty:
                        all_dfs.append(df_result)
                        ai_triggered_files.append(filename)
                    else:
                        st.write("⚠️ AI extraction failed or rate limited. Falling back to local data...")
                        if df_local is not None and not df_local.empty:
                            all_dfs.append(df_local)
                            local_extracted_files.append(filename)
                else:
                    if df_local is not None and not df_local.empty:
                        all_dfs.append(df_local)
                        local_extracted_files.append(filename)
                        if needs_ai:
                            st.write("🔑 Complex format detected, but no API key is available. Using best-effort Local Mode.")
                        else:
                            st.write("⚡ Clean layout: Programmatic extraction complete (no AI tokens consumed).")

            if all_dfs:
                combined_df = pd.concat(all_dfs, ignore_index=True)
                final_df = _merge_duplicate_users(combined_df, pass_prefix=pass_prefix)
                st.session_state['df_users'] = final_df

                if ai_triggered_files and local_extracted_files:
                    mode_label = "Hybrid (AI + Local)"
                elif ai_triggered_files:
                    mode_label = "AI"
                else:
                    mode_label = "Local"

                status.update(label=f"✅ {mode_label} Extraction Complete! {len(final_df)} unique users found.", state="complete")
                if local_extracted_files and not ai_triggered_files:
                    st.toast("💡 100% processed offline in Local Mode (no AI tokens consumed).", icon="⚡")
            else:
                status.update(label="⚠️ No users found in any of the files.", state="error")

# --- DATA GRID ---
if 'df_users' in st.session_state:
    from ui.data_grid import render_data_grid
    render_data_grid(st.session_state['df_users'], navigation, api_key)
else:
    st.info("👋 Upload a file above to begin automated extraction.")

# Reload trigger comment to refresh streamlit app state

