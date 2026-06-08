# user_masters/app.py
import streamlit as st
import pandas as pd
import io
import os
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler()]
)

from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, JsCode
from ai.openai_service import openai_extract_users, local_extract_users, _merge_duplicate_users
from config.constants import USER_MASTER_COLS

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
if "undo_stack"       not in st.session_state: st.session_state.undo_stack = []
if "redo_stack"       not in st.session_state: st.session_state.redo_stack = []
if "_df_users_hash"   not in st.session_state: st.session_state._df_users_hash = None
if "_ai_preview"      not in st.session_state: st.session_state._ai_preview   = None
if "_excel_cache"     not in st.session_state: st.session_state._excel_cache   = {}  # {hash: bytes}

_LARGE_DATASET_ROWS = 500   # Row threshold to enable AgGrid large-dataset mode

# ── Diff-based Undo/Redo helpers ──────────────────────────────────────────────
from utils.history import (
    _compute_ai_diff, _df_hash, _recalculate_duplicates, _update_users_hash,
    _push_diff, _df_diff, _apply_diff, _save_cell_diff, _save_snapshot, _pop_undo, _pop_redo
)
# ─────────────────────────────────────────────────────────────────────────────

# --- HEADER ---
st.markdown("""
<div class="premium-header">
    <h1>User Master Intelligence</h1>
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
            st.image(_logo_path, width="stretch")
    else:
        st.markdown("""
    <div style='text-align:center; padding: 20px 10px 14px 10px;'>
        <div style='font-size: 48px !important;'>⚡</div>
        <div style='font-size: 32px !important; font-weight: 800; color: #0f172a; letter-spacing: -0.5px; margin-top: 4px;'>User Master</div>
    </div>
        """, unsafe_allow_html=True)

    if 'current_nav' not in st.session_state:
        st.session_state.current_nav = "Both"
    if 'nav_radio_key' not in st.session_state:
        st.session_state.nav_radio_key = "Both"

    selected_nav = st.radio("Navigation Mode", ["New User", "Update User", "Both"], key="nav_radio_key")
    st.session_state.current_nav = selected_nav
    navigation = st.session_state.current_nav
    
    st.markdown("""
    <hr style='border: none; border-top: 1px solid rgba(15,23,42,0.1); margin: 8px 0 16px 0;'/>
    <div style='display:flex; align-items:center; gap:8px; padding: 0 2px 10px 2px;'>
        <span style='background:#dbeafe; color:#1d4ed8; font-size:10px; font-weight:800; letter-spacing:1.5px;
                     padding:3px 8px; border-radius:20px;'>STEP 1</span>
        <span style='font-size:12px; font-weight:600; color:#334155; letter-spacing:0.3px;'>Global Settings</span>
    </div>
    """, unsafe_allow_html=True)

    pass_prefix = st.text_input("Password Prefix", value="Med", help="Prefix for auto-generated passwords")
    st.session_state.pass_prefix = pass_prefix

    st.markdown("""<div style='height:4px'></div>""", unsafe_allow_html=True)
    st.markdown("""
    <div style='display:flex; align-items:center; gap:8px; padding: 4px 2px 10px 2px;'>
        <span style='background:#dbeafe; color:#1d4ed8; font-size:10px; font-weight:800; letter-spacing:1.5px;
                     padding:3px 8px; border-radius:20px;'>STEP 2</span>
        <span style='font-size:12px; font-weight:600; color:#334155; letter-spacing:0.3px;'>Smart Context</span>
    </div>
    """, unsafe_allow_html=True)

    user_intent = st.text_area("🎯 Smart Context (Optional)", placeholder="e.g. 'Only extract clinical staff'", label_visibility="collapsed", height=80)
    st.session_state.user_intent = user_intent
    
    srcs = None

    st.markdown("""<div style='height:4px'></div>""", unsafe_allow_html=True)
    if st.button("🗑️ Full Reset", width="stretch"):
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
        * *"Fill missing passwords using Med@123"*
        
        **3. Mapping from Files**
        Upload a mapping file and simply say:
        * *"Map departments"*
        * *"Map roles using the file"*
        
        ---
        ### 🎯 Smart Context (Pre-Extraction)
        Use the sidebar input to set rules **before** processing:
        * *"Only extract clinical staff"*
        * *"Ignore the second sheet"*
        * *"Skip rows where designation is Intern"*
        """)

# --- MAIN LOGIC ---
if navigation == "Update User":
    st.info("Update User functionality is coming soon!")
    st.stop()
    
if navigation == "New User":
    st.markdown("### Step 1: Upload User List(s)")
    srcs = st.file_uploader("Upload an Excel or CSV file to begin automated extraction", type=["xlsx", "xls", "csv", "pdf", "docx"], accept_multiple_files=True, key="user_file_uploader")
    if srcs:
        st.session_state["uploaded_files"] = srcs
    elif "uploaded_files" in st.session_state:
        srcs = st.session_state["uploaded_files"]
        if srcs:
            st.success(f"📂 **{len(srcs)} file(s)** active")
            
elif navigation == "Both":
    from segregation import render_segregation_ui
    render_segregation_ui()
    
    if 'segregation_dfs' in st.session_state and 'segregation_view_choice' in st.session_state:
        current_choice = st.session_state['segregation_view_choice']
        
        # If we were previously editing a DIFFERENT choice, save df_users back!
        if 'prev_segregation_view_choice' in st.session_state and 'df_users' in st.session_state:
            prev_choice = st.session_state['prev_segregation_view_choice']
            if prev_choice != current_choice:
                # User just toggled! Save the old state back to segregation_dfs
                st.session_state['segregation_dfs'][prev_choice] = st.session_state['df_users'].copy()
                
        # Now, load the newly selected choice into df_users if it changed
        if st.session_state.get('prev_segregation_view_choice') != current_choice:
            st.session_state['df_users'] = st.session_state['segregation_dfs'][current_choice].copy()
            st.session_state['prev_segregation_view_choice'] = current_choice
            
            # CRITICAL: Force AgGrid to remount completely to prevent previous grid state
            # from bleeding into grid_response['data'] and overwriting the new dataset.
            if 'grid_key' in st.session_state:
                st.session_state.grid_key += 1
                
            # Update hash to force grid redraw
            _update_users_hash()
    else:
        st.stop()

api_key = st.secrets.get("OPENAI_API_KEY", "") or st.secrets.get("GEMINI_API_KEY", "")
if not api_key:
    try:
        import toml
        secrets_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".streamlit", "secrets.toml")
        if os.path.exists(secrets_path):
            secrets_data = toml.load(secrets_path)
            api_key = secrets_data.get("OPENAI_API_KEY", "") or secrets_data.get("GEMINI_API_KEY", "")
    except Exception:
        pass

if srcs:
    if st.button("🚀 Process User Data", type="primary"):
        with st.status(f"🧠 Analyzing {len(srcs)} Document(s)...", expanded=True) as status:
            all_dfs = []
            ai_triggered_files = []
            local_extracted_files = []
            
            for src in srcs:
                file_bytes = src.getvalue()
                filename = src.name
                
                # --- Step 1: Run Local Extraction Parser First ---
                st.write(f"🔍 Parsing layout locally: {filename}...")
                df_local = local_extract_users(file_bytes, filename, pass_prefix, user_intent)
                
                # --- Step 2: Evaluate if AI is needed ---
                needs_ai = False
                reason = ""
                if user_intent and str(user_intent).strip():
                    needs_ai = True
                    reason = "User specified custom extraction rules"
                elif filename.lower().endswith(('.pdf', '.docx', '.doc')):
                    needs_ai = True
                    reason = "Document requires layout-aware PDF/Word parsing"
                elif df_local is not None and not df_local.empty:
                    # 1. Check if there are pipe delimited rows that need complex AI parsing
                    for col in ['firstName', 'lastName', 'employeeId']:
                        if col in df_local.columns:
                            if df_local[col].astype(str).str.contains('|', regex=False).any():
                                needs_ai = True
                                reason = "Delimited multi-user cells detected"
                                break
                    # 2. Removed Yes/No column check as per user request
                
                # --- Step 3: Run AI extraction only when needed and API key is present ---
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
                    # Direct Local extraction completed
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
                
                # Dynamic mode labeling
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
        user_cols = [c for c in df.columns if c != '#' and not str(c).startswith('_')]  # All visible cols except # and internals
        default_visible = [c for c in ["userName", "firstName", "lastName", "departments", "roles", "units", "locations", "email", "phone", "employeeId", "password", "designation", "isEnabled"] if c in user_cols]
        
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
            update_mode=GridUpdateMode.VALUE_CHANGED | GridUpdateMode.SELECTION_CHANGED,
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
                    st.session_state.df_users = new_data
                    _recalculate_duplicates()
                    st.session_state._df_users_hash = new_hash  # update cached hash
                    st.rerun()  # lock in new state
                else:
                    # Hash collision (extremely rare) — sync hash, no rerun needed
                    st.session_state._df_users_hash = new_hash

        # --- GRID CONTROLS ---
        c_add, c_del, c_u, c_r, c_save = st.columns([1, 1, 0.5, 0.5, 2])

        if c_add.button("➕ ADD ROW", width="stretch"):
            _save_state()
            new_row = pd.DataFrame([{col: "" for col in df.columns}])
            new_row['isEnabled'] = "Yes"
            
            sel_rows = grid_response.get('selected_rows')
            if sel_rows is not None and len(sel_rows) > 0:
                if isinstance(sel_rows, pd.DataFrame):
                    insert_after_serial = sel_rows['#'].iloc[-1]
                else:
                    insert_after_serial = sel_rows[-1].get('#')
                
                idx = df[df['#'] == insert_after_serial].index
                if len(idx) > 0:
                    insert_idx = idx[0] + 1
                    st.session_state.df_users = pd.concat([df.iloc[:insert_idx], new_row, df.iloc[insert_idx:]], ignore_index=True)
                else:
                    st.session_state.df_users = pd.concat([df, new_row], ignore_index=True)
            else:
                st.session_state.df_users = pd.concat([df, new_row], ignore_index=True)
                
            st.session_state.df_users['#'] = range(1, len(st.session_state.df_users) + 1)
            _recalculate_duplicates()
            _update_users_hash()  # update cached hash immediately
            st.session_state.grid_key += 1
            st.rerun()

        if c_del.button("🗑️ DELETE", width="stretch"):
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
                _recalculate_duplicates()
                _update_users_hash()  # update cached hash immediately
                st.session_state.grid_key += 1
                st.rerun()
            else:
                st.warning("Please select rows to delete.")

        if c_u.button("↩️ Undo", help="Undoes bulk actions like Delete/AI. (Jumps to top)"):
            if st.session_state.get('undo_stack'):
                st.session_state.df_users = _pop_undo(df)
                _recalculate_duplicates()
                _update_users_hash()  # update cached hash immediately
                st.session_state.grid_key += 1
                st.session_state.just_undone = True
                st.rerun()

        if c_r.button("↪️ Redo", help="Redoes bulk actions. (Jumps to top)"):
            if st.session_state.get('redo_stack'):
                st.session_state.df_users = _pop_redo(df)
                _recalculate_duplicates()
                _update_users_hash()  # update cached hash immediately
                st.session_state.grid_key += 1
                st.session_state.just_undone = True
                st.rerun()

        if c_save.button("💾 SAVE AND VALIDATE", type="primary", width="stretch"):
            grid_data = grid_response['data'].copy()
            
            # 1. ALWAYS SAVE FIRST (As requested: never block the user)
            saved_df = grid_data
            if '::auto_unique_id::' in saved_df.columns:
                saved_df = saved_df.drop(columns=['::auto_unique_id::'])
            
            # Ensure serial numbers are consistent
            if '#' in saved_df.columns:
                saved_df['#'] = range(1, len(saved_df) + 1)
            
            st.session_state.df_users = saved_df
            _recalculate_duplicates()
            _update_users_hash()                    # update cached hash immediately
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
        mapping_file = st.file_uploader("Upload Context/Mapping File (Optional)", type=["xlsx", "xls", "csv"], key="ai_mapping_file", help="Upload a file with lookup data, such as mapping Client Departments to Medblaze Departments.")
        if 'ai_cmd_history' not in st.session_state:
            st.session_state.ai_cmd_history = []
        if 'chat_input_key' not in st.session_state:
            st.session_state.chat_input_key = 0
            
        chat_cmd = st.text_input("✨ Commands...", placeholder="e.g. 'Map the departments column'", key=f"ai_chat_cmd_{st.session_state.chat_input_key}")
        
        if st.session_state.ai_cmd_history:
            with st.expander(f"🕒 Command History ({len(st.session_state.ai_cmd_history)})", expanded=False):
                for hc in st.session_state.ai_cmd_history:
                    st.markdown(f"- `{hc}`")

        if st.button("🪄 Apply AI"):
            if not chat_cmd:
                st.warning("Please enter a command.")
            else:
                with st.status("🧠 AI is processing your request...", expanded=True) as status:
                    context_df = None
                    if mapping_file is not None:
                        try:
                            if mapping_file.name.endswith('.csv'):
                                context_df = pd.read_csv(mapping_file)
                            else:
                                context_df = pd.read_excel(mapping_file)
                            st.write(f"Context file '{mapping_file.name}' loaded successfully.")
                        except Exception as e:
                            st.error(f"Error reading mapping file: {e}")
                            
                    from ai.openai_service import apply_ai_smart_context
                    updated_df, summary = apply_ai_smart_context(df, chat_cmd, api_key, context_df=context_df)
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
                    st.dataframe(preview['diff_df'], width="stretch", hide_index=True)
                pc1, pc2, _ = st.columns([1, 1, 4])
                if pc1.button("✅ Confirm & Apply", type="primary", width="stretch"):
                    _save_state()
                    st.session_state.df_users        = preview['updated_df']
                    _recalculate_duplicates()
                    _update_users_hash()  # update cached hash immediately
                    st.session_state._ai_preview     = None
                    st.session_state.grid_key        += 1
                    st.session_state.ai_cmd_history.insert(0, preview['cmd'])
                    st.session_state.chat_input_key  += 1
                    st.rerun()
                if pc2.button("❌ Cancel", width="stretch"):
                    st.session_state._ai_preview = None
                    st.rerun()
        # ─────────────────────────────────────────────────────────────────────────────

        st.markdown("---")

        # ── Cached Excel Export ───────────────────────────────────────────────────────────
        # Sync back to segregation_dfs if in Both mode
        if navigation == "Both":
            if 'segregation_view_choice' in st.session_state and 'segregation_dfs' in st.session_state:
                current_choice = st.session_state['segregation_view_choice']
                # Sync grid data to df_users first so we can recalculate duplicates properly
                st.session_state.df_users = grid_response['data'].copy()
                _recalculate_duplicates()
                
                # Now push the fully recalculated dataframe back into the segregation bucket
                st.session_state['segregation_dfs'][current_choice] = st.session_state.df_users.copy()
                _update_users_hash()
                
        # --- DOWNLOAD LOGIC ---
        if navigation == "Both" and 'segregation_dfs' in st.session_state:
            _export_hash_key = str(st.session_state._df_users_hash) + "_both"
            if _export_hash_key not in st.session_state._excel_cache:
                from segregation.export import generate_segregation_workbook
                _buf_bytes = generate_segregation_workbook(st.session_state['segregation_dfs'])
                st.session_state._excel_cache = {_export_hash_key: _buf_bytes}
                
            _excel_bytes = st.session_state._excel_cache[_export_hash_key]
            
            st.download_button(
                label="📥 DOWNLOAD SEGREGATION REPORT (.xlsx)",
                data=_excel_bytes,
                file_name="User_Segregation_Report.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                width="stretch"
            )
        else:
            _export_hash_key = str(st.session_state._df_users_hash)  # None → str for dict key
            if _export_hash_key not in st.session_state._excel_cache:
                _export_df = grid_response['data'].copy()
                # Strip display-only and internal columns from the export
                for _drop_col in ['#', '::auto_unique_id::', '_is_duplicate_user']:
                    if _drop_col in _export_df.columns:
                        _export_df = _export_df.drop(columns=[_drop_col])
                
                _buf = io.BytesIO()
                # Set global pandas setting to remove header bold/borders (Matches audit_config style)
                import pandas.io.formats.excel
                pandas.io.formats.excel.ExcelFormatter.header_style = None
    
                with pd.ExcelWriter(_buf, engine='xlsxwriter') as _writer:
                    _export_df.to_excel(_writer, index=False, sheet_name='Users')
                    
                    # Auto-fit column widths
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
                width="stretch"
            )
else:
    st.info("👋 Upload an Excel or CSV file in the sidebar to begin automated extraction.")
