# user_masters/app.py
import streamlit as st
import pandas as pd
import io
import os
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, JsCode
from ai.openai_service import openai_extract_users, local_extract_users, _merge_duplicate_users
from config.constants import USER_MASTER_COLS

# --- PAGE CONFIG ---
st.set_page_config(
    page_title="User Master Intelligence",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- CUSTOM CSS (Identical to Audit Master) ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap');
    
    /* Typography & Core Variables */
    .stApp, .stMarkdown, .stText, p, h1, h2, h3, label, .stButton button, .stSelectbox div, .stMultiSelect div, .stTextArea textarea, .stTextInput input {
        font-family: 'Outfit', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
    }
    
    /* Soft Gridded Background */
    .main { 
        background-color: #f8fafc; 
        background-image: radial-gradient(#e2e8f0 1px, transparent 1px);
        background-size: 24px 24px;
    }
    
    /* Full Dashboard Container Card */
    .block-container {
        background-color: #ffffff;
        border-radius: 20px;
        box-shadow: 0 10px 40px -10px rgba(15, 23, 42, 0.15), 0 4px 6px -4px rgba(15, 23, 42, 0.1);
        border: 1px solid rgba(226, 232, 240, 0.8);
        margin-top: 2rem;
        margin-bottom: 2rem;
        padding-top: 2.5rem !important;
        padding-bottom: 2.5rem !important;
        transition: box-shadow 0.4s ease;
    }
    .block-container:hover {
        box-shadow: 0 20px 50px -10px rgba(15, 23, 42, 0.25), 0 10px 15px -3px rgba(15, 23, 42, 0.1);
    }
    
    /* Sidebar Styling */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #eef4fb 0%, #f1f5f9 100%);
        border-right: 1px solid #dde6f0;
    }
    [data-testid="stSidebarContent"] { padding-top: 0 !important; }
    section[data-testid="stSidebar"] > div:first-child { padding-top: 0 !important; }
    [data-testid="stSidebar"] * { color: #334155 !important; font-size: 15.5px !important; }
    [data-testid="stSidebar"] h1, 
    [data-testid="stSidebar"] h2, 
    [data-testid="stSidebar"] h3 { color: #0f172a !important; }
    [data-testid="stSidebar"] .stButton>button {
        background: #ffffff !important;
        border: 1px solid #cbd5e1 !important;
        color: #334155 !important;
        font-size: 15.5px !important;
        width: 100%;
    }
    [data-testid="stSidebar"] .stButton>button:hover {
        background: #e0eaf6 !important;
        border-color: #93c5fd !important;
        color: #1e40af !important;
        transform: translateY(-1px);
    }
    [data-testid="stSidebar"] [data-baseweb="textarea"], 
    [data-testid="stSidebar"] [data-baseweb="input"] {
        background: #ffffff !important;
        border-color: #cbd5e1 !important;
        color: #334155 !important;
        border-radius: 8px;
        font-size: 15.5px !important;
    }
    [data-testid="stSidebar"] [data-testid="stExpander"] {
        background: #ffffff !important;
        border: 1px solid #dde6f0 !important;
    }
    [data-testid="stSidebar"] hr { border-color: #dde6f0 !important; }
    [data-testid="stSidebar"] [data-testid="stFileUploaderDropzoneInstructions"] * {
        font-size: 14px !important;
        color: #475569 !important;
    }
    [data-testid="stFileUploaderDropzone"] {
        background: #ffffff !important;
        border: 2px dashed #93c5fd !important;
        border-radius: 10px !important;
    }
    
    /* Premium Header */
    .premium-header {
        background: linear-gradient(135deg, #0f172a 0%, #1e3a8a 50%, #3b82f6 100%);
        padding: 12px 24px;
        border-radius: 12px;
        margin-bottom: 16px;
        color: white;
        box-shadow: 0 10px 30px -5px rgba(29, 78, 216, 0.4);
        position: relative;
        overflow: hidden;
    }
    .premium-header::before {
        content: ''; position: absolute; top: -50%; left: -50%; width: 200%; height: 200%;
        background: radial-gradient(circle, rgba(255,255,255,0.08) 0%, transparent 60%);
        pointer-events: none;
    }
    .premium-header h1 {
        margin: 0; color: white !important; display: flex; align-items: center; text-shadow: 0 2px 4px rgba(0,0,0,0.2);
    }
    
    /* Button Aesthetics */
    .stButton>button { 
        border-radius: 10px; 
        font-weight: 600; 
        letter-spacing: 0.3px;
        transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1); 
        border: 1px solid #e2e8f0;
        background-color: #ffffff;
        color: #475569;
        box-shadow: 0 2px 4px rgba(0,0,0,0.02);
    }
    .stButton>button:hover { 
        transform: translateY(-2px); 
        box-shadow: 0 8px 16px rgba(0,0,0,0.06); 
        border-color: #3b82f6; 
        color: #2563eb;
    }
    
    /* Primary Action Button */
    .stButton>button[kind="primary"] {
        background: linear-gradient(135deg, #f43f5e 0%, #e11d48 100%);
        color: white !important;
        border: none;
        box-shadow: 0 6px 15px rgba(225, 29, 72, 0.35);
    }
    .stButton>button[kind="primary"]:hover {
        background: linear-gradient(135deg, #fb118e 0%, #be123c 100%);
        box-shadow: 0 10px 25px rgba(225, 29, 72, 0.5);
        color: white !important;
    }
    
    /* Expanders & Containers */
    div[data-testid="stExpander"] {
        border-radius: 12px;
        background: white;
        border: 1px solid #e2e8f0;
        box-shadow: 0 2px 8px rgba(0,0,0,0.03);
        margin-bottom: 15px;
    }
    div[data-testid="stExpander"] div[role="button"] {
        padding: 5px 15px;
    }
    div[data-testid="stExpander"] div[role="button"]:hover {
        background-color: #f8fafc;
    }
    
    /* AgGrid Enhancements */
    .ag-theme-alpine {
        --ag-border-color: #e2e8f0;
        --ag-header-background-color: #f8fafc;
        --ag-row-hover-color: #eff6ff;
        --ag-font-family: 'Outfit';
        --ag-cell-horizontal-border: solid #e2e8f0;
        border-radius: 12px;
        overflow: hidden;
        border: 1px solid #e2e8f0;
        box-shadow: 0 6px 12px rgba(0,0,0,0.04);
    }
    .ag-theme-alpine .ag-cell {
        border-right: 1px solid #e2e8f0 !important;
    }
    .ag-theme-alpine .ag-header-cell {
        border-right: 1px solid #cbd5e1 !important;
    }
    
    /* Multiselect Tags */
    span[data-baseweb="tag"] {
        background-color: #f43f5e !important;
        color: white !important;
        border-radius: 6px !important;
    }
    span[data-baseweb="tag"] span { color: white !important; }
    
    /* Custom Headings */
    h1, h2, h3 { color: #0f172a; font-weight: 700; letter-spacing: -0.5px; }
</style>
""", unsafe_allow_html=True)

# --- STATE INIT ---
if "undo_stack"       not in st.session_state: st.session_state.undo_stack = []
if "redo_stack"       not in st.session_state: st.session_state.redo_stack = []
if "_df_users_hash"   not in st.session_state: st.session_state._df_users_hash = None
if "_ai_preview"      not in st.session_state: st.session_state._ai_preview   = None
if "_excel_cache"     not in st.session_state: st.session_state._excel_cache   = {}  # {hash: bytes}

_LARGE_DATASET_ROWS = 500   # Row threshold to enable AgGrid large-dataset mode

# ── Diff-based Undo/Redo helpers ──────────────────────────────────────────────
# Each entry on the undo/redo stack is a dict with:
#   { 'kind': 'diff',      'changes': [(row_idx, col, old_val, new_val), ...] }
#   { 'kind': 'snapshot',  'data': <compact_df>  }   ← only for add/delete rows
#
# Configurable guardrails
_UNDO_LIMIT        = 30    # max history depth
_SNAPSHOT_ROW_CAP  = 500   # rows above this → warn + still snapshot (safety)

def _compute_ai_diff(old_df: pd.DataFrame, new_df: pd.DataFrame) -> pd.DataFrame:
    """Return a human-readable summary DataFrame of AI-changed cells."""
    rows = []
    skip = {'#', '_group_key'}
    for i in range(min(len(old_df), len(new_df))):
        old_row = old_df.iloc[i]
        new_row = new_df.iloc[i]
        for col in old_df.columns:
            if col in skip: continue
            ov = str(old_row.get(col, '')).strip()
            nv = str(new_row.get(col, '')).strip()
            if ov != nv:
                rows.append({'Row #': old_row.get('#', i + 1), 'Column': col, 'Before': ov, 'After': nv})
    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=['Row #', 'Column', 'Before', 'After'])

def _df_hash(df: pd.DataFrame, cols: list) -> int:
    """Fast structural hash of selected columns using pandas' built-in vectorised
    hash engine.  Returns a single int — suitable for O(1) equality pre-check.
    Strips '#' and AgGrid internal columns before hashing."""
    safe_cols = [c for c in cols if c in df.columns]
    if not safe_cols:
        return 0
    try:
        return int(
            pd.util.hash_pandas_object(
                df[safe_cols].astype(str),   # str cast: handles mixed types safely
                index=False
            ).sum()
        )
    except Exception:
        return 0  # fallback: treat as changed so diff runs

def _push_diff(stack: list, entry: dict) -> None:
    """Append an undo/redo entry and evict the oldest if over limit."""
    stack.append(entry)
    while len(stack) > _UNDO_LIMIT:
        stack.pop(0)   # drop oldest entry (O(n) but stacks are tiny)

def _df_diff(old_df: pd.DataFrame, new_df: pd.DataFrame) -> list:
    """Return list of (row_idx, col, old_val, new_val) for every changed cell.
    Compares only shared columns; ignores '#' and internal AgGrid columns."""
    skip = {'#'}
    cols = [
        c for c in old_df.columns
        if c in new_df.columns and c not in skip
        and not str(c).startswith('_') and not str(c).startswith('::')
    ]
    # Align to same length (structural differences are handled via snapshots)
    min_len = min(len(old_df), len(new_df))
    old_vals = old_df[cols].iloc[:min_len].astype(object).fillna("").reset_index(drop=True)
    new_vals = new_df[cols].iloc[:min_len].astype(object).fillna("").reset_index(drop=True)
    changed = old_vals.compare(new_vals, result_names=('old', 'new'))
    diffs = []
    for row_idx, row in changed.iterrows():
        for col in cols:
            try:
                ov = row[(col, 'old')]
                nv = row[(col, 'new')]
                if pd.notna(ov) or pd.notna(nv):   # skip if both NaN (no real change)
                    diffs.append((int(row_idx), col, ov, nv))
            except KeyError:
                pass
    return diffs

def _apply_diff(df: pd.DataFrame, changes: list, reverse: bool = False) -> pd.DataFrame:
    """Apply (or reverse) a diff list to a DataFrame copy."""
    result = df.copy()
    for row_idx, col, old_val, new_val in changes:
        if row_idx < len(result) and col in result.columns:
            result.at[row_idx, col] = old_val if reverse else new_val
    return result

def _save_cell_diff(old_df: pd.DataFrame, new_df: pd.DataFrame) -> bool:
    """Push a cell-diff entry onto undo_stack. Returns True if changes found."""
    diffs = _df_diff(old_df, new_df)
    if not diffs:
        return False
    _push_diff(st.session_state.undo_stack, {'kind': 'diff', 'changes': diffs})
    st.session_state.redo_stack.clear()
    return True

def _save_snapshot(df: pd.DataFrame) -> None:
    """Push a full snapshot entry (used for structural changes: add/delete rows)."""
    # Keep only data columns — '#' is regenerated; drop AgGrid internals
    clean = df[[c for c in df.columns
                if not str(c).startswith('::') and not str(c).startswith('_')]].copy()
    _push_diff(st.session_state.undo_stack, {'kind': 'snapshot', 'data': clean})
    st.session_state.redo_stack.clear()

def _pop_undo(current_df: pd.DataFrame):
    """Pop the top of undo_stack, push to redo_stack, return restored DataFrame."""
    entry = st.session_state.undo_stack.pop()
    # Save current state to redo before restoring
    if entry['kind'] == 'diff':
        # For redo we need the inverse diff (new→old already captured)
        _push_diff(st.session_state.redo_stack,
                   {'kind': 'diff', 'changes': entry['changes']})
        return _apply_diff(current_df, entry['changes'], reverse=True)
    else:  # snapshot
        # Push current state as a snapshot to redo
        clean = current_df[[c for c in current_df.columns
                             if not str(c).startswith('::') and not str(c).startswith('_')]].copy()
        _push_diff(st.session_state.redo_stack, {'kind': 'snapshot', 'data': clean})
        return entry['data'].copy()

def _pop_redo(current_df: pd.DataFrame):
    """Pop the top of redo_stack, push to undo_stack, return restored DataFrame."""
    entry = st.session_state.redo_stack.pop()
    if entry['kind'] == 'diff':
        _push_diff(st.session_state.undo_stack,
                   {'kind': 'diff', 'changes': entry['changes']})
        return _apply_diff(current_df, entry['changes'], reverse=False)
    else:  # snapshot
        clean = current_df[[c for c in current_df.columns
                             if not str(c).startswith('::') and not str(c).startswith('_')]].copy()
        _push_diff(st.session_state.undo_stack, {'kind': 'snapshot', 'data': clean})
        return entry['data'].copy()
# ─────────────────────────────────────────────────────────────────────────────

# --- HEADER ---
st.markdown("""
<div class="premium-header">
    <h1>User Master Intelligence</h1>
    <p style='margin-top:10px; margin-bottom:0; font-size: 19px; opacity: 0.95; font-weight: 300;'>Automated HR & Access Control Data Mapping</p>
</div>
""", unsafe_allow_html=True)

# --- SIDEBAR ---
with st.sidebar:
    # Brand Logo
    _logo_path = os.path.join(os.path.dirname(__file__), "logo.png")
    if not os.path.exists(_logo_path):
        _logo_path = "logo.png"
    
    if os.path.exists(_logo_path):
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.image(_logo_path, use_container_width=True)
    else:
        st.markdown("""
    <div style='text-align:center; padding: 20px 10px 14px 10px;'>
        <div style='font-size: 48px !important;'>⚡</div>
        <div style='font-size: 32px !important; font-weight: 800; color: #0f172a; letter-spacing: -0.5px; margin-top: 4px;'>User Master</div>
    </div>
        """, unsafe_allow_html=True)

    st.markdown("""
    <hr style='border: none; border-top: 1px solid rgba(15,23,42,0.1); margin: 8px 0 16px 0;'/>
    <div style='display:flex; align-items:center; gap:8px; padding: 0 2px 10px 2px;'>
        <span style='background:#dbeafe; color:#1d4ed8; font-size:10px; font-weight:800; letter-spacing:1.5px;
                     padding:3px 8px; border-radius:20px;'>STEP 1</span>
        <span style='font-size:12px; font-weight:600; color:#334155; letter-spacing:0.3px;'>Source Setup</span>
    </div>
    """, unsafe_allow_html=True)

    srcs = st.file_uploader("Upload User List(s)", type=["xlsx", "xls", "csv", "pdf", "docx"], accept_multiple_files=True, key="user_file_uploader")
    if srcs:
        st.session_state["uploaded_files"] = srcs
    elif "uploaded_files" in st.session_state:
        srcs = st.session_state["uploaded_files"]
        if srcs:
            st.success(f"📂 **{len(srcs)} file(s)** active")

    pass_prefix = st.text_input("Password Prefix", value="Aone", help="Prefix for auto-generated passwords")

    st.markdown("""<div style='height:4px'></div>""", unsafe_allow_html=True)
    st.markdown("""
    <div style='display:flex; align-items:center; gap:8px; padding: 4px 2px 10px 2px;'>
        <span style='background:#dbeafe; color:#1d4ed8; font-size:10px; font-weight:800; letter-spacing:1.5px;
                     padding:3px 8px; border-radius:20px;'>STEP 2</span>
        <span style='font-size:12px; font-weight:600; color:#334155; letter-spacing:0.3px;'>Smart Context</span>
    </div>
    """, unsafe_allow_html=True)

    user_intent = st.text_area("🎯 Smart Context (Optional)", placeholder="e.g. 'Only extract clinical staff'", label_visibility="collapsed", height=80)

    st.markdown("""<div style='height:4px'></div>""", unsafe_allow_html=True)
    if st.button("🗑️ Full Reset", use_container_width=True):
        st.cache_data.clear()
        for key in list(st.session_state.keys()): del st.session_state[key]
        st.rerun()

    with st.expander("❓ **How to use AI Assistant**", expanded=False):
        st.markdown("""
        ### 🤖 Assistant Commands (Post-Extraction)
        
        **1. Bulk Editing**
        * *"Set isEnabled to Yes for all rows"*
        * *"Update department to ICU for all nurses"*
        * *"Set roles to Audit User|Incident Reporter for row 5"*
        
        **2. Smart Fixes**
        * *"Fix all usernames to be lowercase with no spaces"*
        * *"Fill missing passwords using Aone@123"*
        
        ---
        ### 🎯 Smart Context (Pre-Extraction)
        Use the sidebar input to set rules **before** processing:
        * *"Only extract clinical staff"*
        * *"Ignore the second sheet"*
        * *"Skip rows where designation is Intern"*
        """)

# --- MAIN LOGIC ---
api_key = st.secrets.get("OPENAI_API_KEY", "") or st.secrets.get("GEMINI_API_KEY", "")
print(f"[DEBUG] st.secrets.get('OPENAI_API_KEY') found: {bool(st.secrets.get('OPENAI_API_KEY'))}")
if not api_key:
    try:
        import toml
        secrets_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".streamlit", "secrets.toml")
        print(f"[DEBUG] Checking fallback secrets_path: {secrets_path}")
        if os.path.exists(secrets_path):
            print(f"[DEBUG] Fallback secrets_path exists!")
            secrets_data = toml.load(secrets_path)
            api_key = secrets_data.get("OPENAI_API_KEY", "") or secrets_data.get("GEMINI_API_KEY", "")
            print(f"[DEBUG] Loaded api_key from secrets_path: {bool(api_key)}")
        else:
            print(f"[DEBUG] Fallback secrets_path does NOT exist!")
    except Exception as e:
        print(f"[DEBUG] Exception loading fallback secrets: {e}")

if srcs:
    if st.button("🚀 Process User Data", type="primary"):
        with st.status(f"🧠 Analyzing {len(srcs)} Document(s)...", expanded=True) as status:
            all_dfs = []
            ai_failed = False
            
            # --- Try AI extraction first (if API key available) ---
            print(f"[DEBUG] Process button clicked. api_key length: {len(api_key) if api_key else 0}")
            if api_key:
                for src in srcs:
                    st.write(f"📄 AI Extraction: {src.name}...")
                    file_bytes = src.getvalue()
                    df_result = openai_extract_users(file_bytes, src.name, api_key, user_intent, pass_prefix)
                    if df_result is not None and not df_result.empty:
                        all_dfs.append(df_result)
                
                if not all_dfs:
                    ai_failed = True
                    st.write("⚠️ AI extraction returned 0 users (API keys may be exhausted). Switching to **Local Mode**...")
            else:
                ai_failed = True
                st.write("🔑 No API key found. Using **Local Extraction Mode**...")
            
            # --- Fallback to LOCAL extraction (no AI needed) ---
            if ai_failed:
                all_dfs = []
                for src in srcs:
                    st.write(f"📄 Local Extraction: {src.name}...")
                    file_bytes = src.getvalue()
                    df_result = local_extract_users(file_bytes, src.name, pass_prefix)
                    if df_result is not None and not df_result.empty:
                        all_dfs.append(df_result)
            
            if all_dfs:
                combined_df = pd.concat(all_dfs, ignore_index=True)
                # Merge cross-file duplicates — pass_prefix ensures correct passwords
                final_df = _merge_duplicate_users(combined_df, pass_prefix=pass_prefix)
                st.session_state['df_users'] = final_df
                mode_label = "Local" if ai_failed else "AI"
                status.update(label=f"✅ {mode_label} Extraction Complete! {len(final_df)} unique users found.", state="complete")
                if ai_failed:
                    st.toast("💡 Used Local Mode (no AI). Column mapping may need manual review.", icon="ℹ️")
            else:
                status.update(label="⚠️ No users found in any of the files.", state="error")

if 'df_users' in st.session_state:
    df = st.session_state['df_users']
    
    if df.empty:
        st.warning("⚠️ No users were found in the uploaded file.")
    else:
        st.markdown("## 📝 Review & Configure")
        
        # Clean up AgGrid's internal ID if it got saved
        if '::auto_unique_id::' in df.columns:
            df = df.drop(columns=['::auto_unique_id::'])
            st.session_state['df_users'] = df
        
        # --- SERIAL NUMBERS ---
        if '#' not in df.columns:
            df.insert(0, '#', range(1, len(df) + 1))
        else:
            df['#'] = range(1, len(df) + 1)
        
        # --- VISIBILITY MANAGER ---
        # '#' is ALWAYS pinned left — exclude it from visibility toggles entirely
        user_cols = [c for c in df.columns if c != '#']  # All cols except #
        default_visible = [c for c in ["userName", "email", "units", "roles", "mobile", "employeeId", "password", "departments"] if c in user_cols]
        
        if 'visible_cols' not in st.session_state:
            st.session_state.visible_cols = default_visible
        else:
            # Ensure no orphaned columns (like auto_unique_id) remain in visible selection
            st.session_state.visible_cols = [c for c in st.session_state.visible_cols if c in user_cols]
        
        # --- SUMMARY DASHBOARD ---
        m1, _, _, _ = st.columns(4)
        total_users = len(df)
        
        m1.metric("Total Users", total_users)
        
        with st.expander("👁️ Column Visibility"):
            cv1, cv2, cv3, _ = st.columns([1, 1, 1, 3])
            # Button click already triggers a Streamlit rerun — no explicit st.rerun() needed.
            # The grid_key is computed from visible_cols, so it automatically updates.
            if cv1.button("\u2705 All"):     st.session_state.visible_cols = user_cols
            if cv2.button("\u274c Clear"):   st.session_state.visible_cols = ["userName"]
            if cv3.button("\U0001f504 Default"): st.session_state.visible_cols = default_visible
            
            new_selection = st.multiselect("Hide/Show Columns", options=user_cols, default=st.session_state.visible_cols)
            # Widget interaction already causes a Streamlit rerun; no extra st.rerun() needed
            if new_selection != st.session_state.visible_cols:
                st.session_state.visible_cols = new_selection

        # --- DUPLICATE DETECTION FOR UI HIGHLIGHTING ---
        if not df.empty and 'userName' in df.columns:
            # Filter out empty usernames from duplicate check to avoid highlighting all empty rows
            valid_names = df['userName'].astype(str).str.strip().replace(['', 'nan', 'None', '-'], pd.NA).dropna()
            counts = valid_names.value_counts()
            dups = counts[counts > 1].index
            df['_is_duplicate_user'] = df['userName'].isin(dups)
        else:
            df['_is_duplicate_user'] = False

        # --- AGGRID ---
        gb = GridOptionsBuilder.from_dataframe(df)
        gb.configure_default_column(
            editable=True, filter='agTextColumnFilter', resizable=True, sortable=True, width=250, minWidth=100
        )
        # '#' always pinned left — configured first so it's always at position 0
        gb.configure_column("#", headerName="#", width=80, pinned='left', editable=False,
                            checkboxSelection=True, headerCheckboxSelection=True)
        # Hide duplicate flag
        gb.configure_column("_is_duplicate_user", hide=True)
        # Hide all user cols not in visible selection
        for col in user_cols:
            if col not in st.session_state.visible_cols:
                gb.configure_column(col, hide=True)
        _is_large = len(df) > _LARGE_DATASET_ROWS
        if _is_large:
            # Large-dataset mode: pagination + disable expensive grid features
            gb.configure_pagination(enabled=True, paginationAutoPageSize=False, paginationPageSize=100)
            gb.configure_grid_options(
                rowSelection='multiple',
                suppressRowClickSelection=True,
                enableRangeSelection=False,    # disabled for performance
                enableFillHandle=False,         # disabled for performance
                undoRedoCellEditing=False,      # Python-side undo is active
                getRowStyle=JsCode("""
                    function(params) {
                        if (params.data && params.data._is_duplicate_user === true) {
                            return { 'background-color': '#ffcdd2' };
                        }
                        return null;
                    }
                """)
            )
            if 'shown_large_warn' not in st.session_state or \
               st.session_state.get('_large_warn_hash') != st.session_state._df_users_hash:
                st.warning(f"⚠️ Large dataset ({len(df)} rows) — pagination enabled, some grid features reduced for performance.")
                st.session_state.shown_large_warn = True
                st.session_state._large_warn_hash = st.session_state._df_users_hash
        else:
            gb.configure_grid_options(
                rowSelection='multiple',
                suppressRowClickSelection=True,
                enableRangeSelection=True,
                enableFillHandle=True,
                undoRedoCellEditing=True,
                undoRedoCellEditingLimit=20,
                getRowStyle=JsCode("""
                    function(params) {
                        if (params.data && params.data._is_duplicate_user === true) {
                            return { 'background-color': '#ffcdd2' };
                        }
                        return null;
                    }
                """)
            )
        
        if 'grid_key' not in st.session_state: st.session_state.grid_key = 0
        grid_key = f"grid_{st.session_state.grid_key}_{hash(tuple(st.session_state.visible_cols))}"

        grid_response = AgGrid(
            df,
            gridOptions=gb.build(),
            theme='alpine',
            height=600,
            update_mode=GridUpdateMode.VALUE_CHANGED,
            enable_enterprise_modules=True,
            fit_columns_on_grid_load=False,
            reload_data=True,
            allow_unsafe_jscode=True,
            key=grid_key
        )

        # _save_state is now alias for _save_snapshot (structural changes only)
        def _save_state():
            _save_snapshot(df)

        # ── Optimized Grid → SessionState sync (hash-first, diff-second) ──────
        # Stage 1: O(1) hash compare — exits immediately on no-op reruns.
        # Stage 2: precise cell-diff only when hash signals a real change.
        _just_undone = st.session_state.pop('just_undone', False)
        if not _just_undone and grid_response['data'] is not None:
            new_data = grid_response['data']
            # Columns to watch: exclude '#', AgGrid internals (_* and ::*)
            watch_cols = [
                c for c in new_data.columns
                if not str(c).startswith('_')
                and not str(c).startswith('::')
                and c != '#'
                and c in df.columns          # only compare shared columns
            ]

            # Stage 1 — fast hash pre-check (vectorised, no Python loops)
            new_hash = _df_hash(new_data, watch_cols)
            if new_hash != st.session_state._df_users_hash:
                # Stage 2 — hashes differ: run precise cell diff
                curr_cleaned = df[watch_cols].astype(object).fillna("").reset_index(drop=True)
                new_cleaned  = new_data[watch_cols].astype(object).fillna("").reset_index(drop=True)

                if not curr_cleaned.equals(new_cleaned):
                    # Real change confirmed — push diff and update state
                    _save_cell_diff(df, new_data)
                    st.session_state.df_users    = new_data
                    st.session_state._df_users_hash = new_hash  # update cached hash
                    st.rerun()  # lock in new state
                else:
                    # Hash collision (extremely rare) — sync hash, no rerun needed
                    st.session_state._df_users_hash = new_hash

        # --- GRID CONTROLS ---
        c_add, c_del, c_u, c_r, c_save = st.columns([1, 1, 0.5, 0.5, 2])

        if c_add.button("➕ ADD ROW", use_container_width=True):
            _save_state()
            new_row = pd.DataFrame([{col: "" for col in df.columns}])
            new_row['#'] = len(df) + 1
            new_row['isEnabled'] = "Yes"
            st.session_state.df_users = pd.concat([df, new_row], ignore_index=True)
            st.session_state._df_users_hash = None  # invalidate: row count changed
            st.session_state.grid_key += 1
            st.rerun()

        if c_del.button("🗑️ DELETE", use_container_width=True):
            sel_rows = grid_response.get('selected_rows')
            if sel_rows is not None and len(sel_rows) > 0:
                _save_state()
                # Get the '#' (Serial Number) of the rows to delete
                if isinstance(sel_rows, pd.DataFrame):
                    delete_ids = sel_rows['#'].tolist()
                else:
                    delete_ids = [r.get('#') for r in sel_rows if r.get('#') is not None]
                
                # Filter out the rows to delete
                st.session_state.df_users = df[~df['#'].isin(delete_ids)].reset_index(drop=True)
                # Re-generate serial numbers
                st.session_state.df_users['#'] = range(1, len(st.session_state.df_users) + 1)
                st.session_state._df_users_hash = None  # invalidate: row count changed
                st.session_state.grid_key += 1
                st.rerun()
            else:
                st.warning("Please select rows to delete.")

        if c_u.button("↩️ Undo", help="Undoes bulk actions like Delete/AI. (Jumps to top)"):
            if st.session_state.get('undo_stack'):
                st.session_state.df_users = _pop_undo(df)
                st.session_state._df_users_hash = None  # invalidate: state replaced
                st.session_state.grid_key += 1
                st.session_state.just_undone = True
                st.rerun()

        if c_r.button("↪️ Redo", help="Redoes bulk actions. (Jumps to top)"):
            if st.session_state.get('redo_stack'):
                st.session_state.df_users = _pop_redo(df)
                st.session_state._df_users_hash = None  # invalidate: state replaced
                st.session_state.grid_key += 1
                st.session_state.just_undone = True
                st.rerun()

        if c_save.button("💾 SAVE AND VALIDATE", type="primary", use_container_width=True):
            grid_data = grid_response['data'].copy()
            
            # 1. ALWAYS SAVE FIRST (As requested: never block the user)
            saved_df = grid_data
            if '::auto_unique_id::' in saved_df.columns:
                saved_df = saved_df.drop(columns=['::auto_unique_id::'])
            
            # Ensure serial numbers are consistent
            if '#' in saved_df.columns:
                saved_df['#'] = range(1, len(saved_df) + 1)
            
            st.session_state.df_users = saved_df
            st.session_state._df_users_hash = None  # invalidate hash
            st.session_state._excel_cache = {}      # clear excel cache
            
            # 2. RUN VALIDATION (For reporting only)
            from ai.openai_service import validate_master_data
            errors, warnings = validate_master_data(grid_data)
            
            # 3. DISPLAY RESULTS
            if not errors and not warnings:
                st.success("✅ **All changes saved and validated successfully!**")
            else:
                st.info("✅ **Changes saved locally.**")
                
                if errors:
                    with st.expander("🔴 **CRITICAL: Missing Mandatory Data**", expanded=True):
                        st.markdown("The following rows were saved but are **missing mandatory UserNames**:")
                        for err in errors:
                            st.write(f"- {err}")
                
                if warnings:
                    with st.expander("⚠️ **WARNING: Data Quality Issues**", expanded=False):
                        st.markdown("The following rows have format issues in optional fields:")
                        for warn in warnings:
                            st.write(f"- {warn}")
                
                st.info("💡 You can continue editing. Please fix the red items before final system upload.")

        # --- AI CONFIGURATION ASSISTANT ---
        st.markdown("---")
        st.subheader("💬 AI Configuration Assistant")
        chat_cmd = st.text_input("✨ Commands...", placeholder="e.g. 'Set isEnabled to No for all doctors in CAH Bukit Jalil'")

        if st.button("🪄 Apply AI"):
            if not chat_cmd:
                st.warning("Please enter a command.")
            else:
                with st.status("🧠 AI is processing your request...", expanded=True) as status:
                    from ai.openai_service import apply_ai_smart_context
                    updated_df, summary = apply_ai_smart_context(df, chat_cmd, api_key)
                    if updated_df is not None:
                        diff_df = _compute_ai_diff(df, updated_df)
                        st.session_state._ai_preview = {
                            'updated_df': updated_df,
                            'summary':    summary,
                            'diff_df':    diff_df,
                            'cmd':        chat_cmd,
                        }
                        status.update(label=f"✨ Preview ready — {len(diff_df)} change(s) detected. Review below.", state="complete")
                        st.rerun()
                    else:
                        status.update(label=f"❌ {summary}", state="error")

        # ── AI Change Preview (two-step confirm) ─────────────────────────────────────────────
        if st.session_state.get('_ai_preview'):
            preview = st.session_state['_ai_preview']
            n_changes = len(preview['diff_df'])
            with st.expander(f"🔍 AI Preview — {n_changes} cell change(s) pending", expanded=True):
                st.caption(f"💬 Command: *{preview['cmd']}*")
                st.caption(f"💡 {preview['summary']}")
                if preview['diff_df'].empty:
                    st.info("ℹ️ No cell-level changes detected by AI.")
                else:
                    st.dataframe(preview['diff_df'], use_container_width=True, hide_index=True)
                pc1, pc2, _ = st.columns([1, 1, 4])
                if pc1.button("✅ Confirm & Apply", type="primary", use_container_width=True):
                    _save_state()
                    st.session_state.df_users        = preview['updated_df']
                    st.session_state._df_users_hash  = None
                    st.session_state._ai_preview     = None
                    st.session_state.grid_key        += 1
                    st.rerun()
                if pc2.button("❌ Cancel", use_container_width=True):
                    st.session_state._ai_preview = None
                    st.rerun()
        # ─────────────────────────────────────────────────────────────────────────────

        st.markdown("---")

        # ── Cached Excel Export ───────────────────────────────────────────────────────────
        # Regenerate the .xlsx only when the data actually changes (keyed by hash).
        # On no-op reruns (sidebar interactions, column toggles, etc.) this block
        # returns the cached bytes instantly without touching xlsxwriter.
        _export_hash_key = str(st.session_state._df_users_hash)  # None → str for dict key
        if _export_hash_key not in st.session_state._excel_cache:
            _export_df = grid_response['data'].copy()
            # Strip display-only and internal columns from the export
            for _drop_col in ['#', '::auto_unique_id::']:
                if _drop_col in _export_df.columns:
                    _export_df = _export_df.drop(columns=[_drop_col])
            
            _buf = io.BytesIO()
            # Set global pandas setting to remove header bold/borders (Matches audit_config style)
            import pandas.io.formats.excel
            pandas.io.formats.excel.ExcelFormatter.header_style = None

            with pd.ExcelWriter(_buf, engine='xlsxwriter') as _writer:
                _export_df.to_excel(_writer, index=False, sheet_name='Users')
                
                # Auto-fit column widths (kept from previous step for usability)
                _worksheet = _writer.sheets['Users']
                for _i, _col in enumerate(_export_df.columns):
                    _col_str_lengths = [len(str(_val)) for _val in _export_df[_col] if pd.notna(_val)]
                    _max_len = max(
                        max(_col_str_lengths) if _col_str_lengths else 0,
                        len(str(_col))
                    ) + 2
                    _worksheet.set_column(_i, _i, min(_max_len, 50))

            # Keep only the latest entry
            st.session_state._excel_cache = {_export_hash_key: _buf.getvalue()}

        _excel_bytes = st.session_state._excel_cache[_export_hash_key]
        # ─────────────────────────────────────────────────────────────────────────────
        st.download_button(
            label="📥 DOWNLOAD USER MASTER (.xlsx)",
            data=_excel_bytes,
            file_name="user_master_export.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
else:
    st.info("👋 Upload an Excel or CSV file in the sidebar to begin automated extraction.")
