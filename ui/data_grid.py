# user_masters/ui/data_grid.py
"""
AgGrid data-grid rendering and grid-control buttons (add/delete/undo/redo/save).

All grid configuration, duplicate highlighting, visibility toggles,
and cell-sync logic live here — keeping app.py slim.
"""
import io
import pandas as pd
import streamlit as st
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, JsCode

from utils.common import detect_duplicates_in_df, resolve_duplicate_usernames
from models.dataframe_contract import enforce_contract
from utils.history import (
    _compute_ai_diff, _df_hash, _recalculate_duplicates, _update_users_hash,
    _save_snapshot, _save_cell_diff, _pop_undo, _pop_redo
)

_LARGE_DATASET_ROWS = 500   # Row threshold to enable AgGrid large-dataset mode

_CELL_CLICK_MODAL_JS = JsCode("""
function(params) {
    // Only trigger for data columns (not '#')
    if (params.column.getId() === '#') {
        return;
    }
    
    // Stop any active AgGrid inline editing
    params.api.stopEditing(true);
    
    const colId = params.column.getId();
    const colName = params.column.getColDef().headerName || colId;
    const initialVal = params.value || '';
    
    // Ensure document click listener is initialized once to close on outside clicks
    if (typeof window._editorClickListenerInitialized === 'undefined') {
        window._editorClickListenerInitialized = true;
        document.addEventListener('mousedown', function(e) {
            const p = document.getElementById('ag-grid-floating-editor');
            if (p && !p.contains(e.target)) {
                p.remove();
            }
        });
    }
    
    // Get or Create Floating Editor
    let popup = document.getElementById('ag-grid-floating-editor');
    if (!popup) {
        popup = document.createElement('div');
        popup.id = 'ag-grid-floating-editor';
        popup.style.position = 'fixed';
        popup.style.zIndex = '99999';
        popup.style.backgroundColor = '#0f172a';
        popup.style.color = '#f1f5f9';
        popup.style.width = '420px';
        popup.style.padding = '0';
        popup.style.borderRadius = '10px';
        popup.style.boxShadow = '0 20px 25px -5px rgba(0, 0, 0, 0.4), 0 10px 10px -5px rgba(0, 0, 0, 0.3)';
        popup.style.border = '1px solid #3b82f6';
        popup.style.borderLeft = '5px solid #60a5fa';
        popup.style.fontFamily = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
        popup.style.display = 'flex';
        popup.style.flexDirection = 'column';
        popup.style.boxSizing = 'border-box';
        popup.style.resize = 'both';
        popup.style.overflow = 'hidden';
        popup.style.minWidth = '320px';
        popup.style.minHeight = '180px';
        document.body.appendChild(popup);
    }
    
    // Position Popup near the click event
    const clickEvent = params.event || { clientX: window.innerWidth / 2 - 210, clientY: window.innerHeight / 2 - 120 };
    let x = clickEvent.clientX + 15;
    let y = clickEvent.clientY - 20;
    
    // Prevent rendering off-screen
    if (x + 420 > window.innerWidth) {
        x = clickEvent.clientX - 440;
    }
    if (x < 10) x = 10;
    
    if (y + 320 > window.innerHeight) {
        y = window.innerHeight - 340;
    }
    if (y < 10) y = 10;
    
    popup.style.left = x + 'px';
    popup.style.top = y + 'px';
    
    // Clear and build content
    popup.innerHTML = '';
    
    // Create Header bar (for dragging)
    const header = document.createElement('div');
    header.style.backgroundColor = '#1e293b';
    header.style.padding = '10px 14px';
    header.style.display = 'flex';
    header.style.justifyContent = 'space-between';
    header.style.alignItems = 'center';
    header.style.cursor = 'move';
    header.style.borderBottom = '1px solid #334155';
    header.style.userSelect = 'none';
    
    const title = document.createElement('div');
    title.style.fontSize = '13px';
    title.style.fontWeight = '700';
    title.style.color = '#60a5fa';
    title.innerText = '✏️ Edit ' + colName;
    header.appendChild(title);
    
    const closeBtn = document.createElement('div');
    closeBtn.innerHTML = '&times;';
    closeBtn.style.cursor = 'pointer';
    closeBtn.style.fontSize = '18px';
    closeBtn.style.color = '#94a3b8';
    closeBtn.style.lineHeight = '1';
    closeBtn.onclick = () => popup.remove();
    closeBtn.onmouseenter = () => closeBtn.style.color = '#f1f5f9';
    closeBtn.onmouseleave = () => closeBtn.style.color = '#94a3b8';
    header.appendChild(closeBtn);
    
    popup.appendChild(header);
    
    // Dragging Logic
    let isDragging = false;
    let dragStartX, dragStartY;
    let popupStartX, popupStartY;
    
    header.onmousedown = function(e) {
        if (e.target === closeBtn) return;
        isDragging = true;
        dragStartX = e.clientX;
        dragStartY = e.clientY;
        popupStartX = parseInt(popup.style.left) || 0;
        popupStartY = parseInt(popup.style.top) || 0;
        
        document.addEventListener('mousemove', onMouseMove);
        document.addEventListener('mouseup', onMouseUp);
        e.preventDefault();
    };
    
    function onMouseMove(e) {
        if (!isDragging) return;
        const dx = e.clientX - dragStartX;
        const dy = e.clientY - dragStartY;
        popup.style.left = (popupStartX + dx) + 'px';
        popup.style.top = (popupStartY + dy) + 'px';
    }
    
    function onMouseUp() {
        isDragging = false;
        document.removeEventListener('mousemove', onMouseMove);
        document.removeEventListener('mouseup', onMouseUp);
    }
    
    // Body container
    const body = document.createElement('div');
    body.style.padding = '14px';
    body.style.display = 'flex';
    body.style.flexDirection = 'column';
    body.style.gap = '10px';
    body.style.flex = '1';
    body.style.boxSizing = 'border-box';
    body.style.overflow = 'hidden';
    
    // Textarea
    const textarea = document.createElement('textarea');
    textarea.value = initialVal;
    textarea.style.width = '100%';
    textarea.style.flex = '1';
    textarea.style.minHeight = '100px';
    textarea.style.backgroundColor = '#1e293b';
    textarea.style.color = '#f8fafc';
    textarea.style.border = '1px solid #475569';
    textarea.style.borderRadius = '6px';
    textarea.style.padding = '8px';
    textarea.style.fontSize = '13px';
    textarea.style.fontFamily = 'inherit';
    textarea.style.resize = 'none';
    textarea.style.boxSizing = 'border-box';
    textarea.style.outline = 'none';
    textarea.onfocus = () => textarea.style.borderColor = '#3b82f6';
    textarea.onblur = () => textarea.style.borderColor = '#475569';
    body.appendChild(textarea);
    
    // Button Container
    const btnContainer = document.createElement('div');
    btnContainer.style.display = 'flex';
    btnContainer.style.justifyContent = 'flex-end';
    btnContainer.style.gap = '8px';
    btnContainer.style.marginTop = '4px';
    
    const cancelBtn = document.createElement('button');
    cancelBtn.innerText = 'Cancel';
    cancelBtn.style.backgroundColor = '#334155';
    cancelBtn.style.color = '#f1f5f9';
    cancelBtn.style.border = 'none';
    cancelBtn.style.padding = '6px 12px';
    cancelBtn.style.borderRadius = '6px';
    cancelBtn.style.cursor = 'pointer';
    cancelBtn.style.fontSize = '12px';
    cancelBtn.style.fontWeight = '600';
    cancelBtn.onmouseenter = () => cancelBtn.style.backgroundColor = '#475569';
    cancelBtn.onmouseleave = () => cancelBtn.style.backgroundColor = '#334155';
    cancelBtn.onclick = () => {
        popup.remove();
    };
    
    const saveBtn = document.createElement('button');
    saveBtn.innerText = 'Save Changes';
    saveBtn.style.backgroundColor = '#3b82f6';
    saveBtn.style.color = '#ffffff';
    saveBtn.style.border = 'none';
    saveBtn.style.padding = '6px 12px';
    saveBtn.style.borderRadius = '6px';
    saveBtn.style.cursor = 'pointer';
    saveBtn.style.fontSize = '12px';
    saveBtn.style.fontWeight = '600';
    saveBtn.onmouseenter = () => saveBtn.style.backgroundColor = '#2563eb';
    saveBtn.onmouseleave = () => saveBtn.style.backgroundColor = '#3b82f6';
    saveBtn.onclick = () => {
        const newVal = textarea.value;
        params.node.setDataValue(colId, newVal);
        popup.remove();
    };
    
    // Keyboard listener for Ctrl+Enter and Esc
    textarea.onkeydown = function(e) {
        if (e.key === 'Enter' && e.ctrlKey) {
            saveBtn.click();
            e.preventDefault();
        } else if (e.key === 'Escape') {
            cancelBtn.click();
            e.preventDefault();
        }
    };
    
    btnContainer.appendChild(cancelBtn);
    btnContainer.appendChild(saveBtn);
    body.appendChild(btnContainer);
    
    popup.appendChild(body);
    
    // Focus textarea
    setTimeout(() => textarea.focus(), 50);
}
""")


def _detect_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """Add _is_duplicate_user and _is_duplicate_username columns."""
    return detect_duplicates_in_df(df)



def _build_grid_options(df: pd.DataFrame, user_cols: list, visible_cols: list):
    """Create and return AgGrid GridOptionsBuilder."""
    gb = GridOptionsBuilder.from_dataframe(df)
    gb.configure_default_column(
        editable=False, filter='agTextColumnFilter', resizable=True, sortable=True, width=200, minWidth=150
    )
    # '#' always pinned left
    gb.configure_column("#", headerName="#", width=140, minWidth=120, maxWidth=180, pinned='left', editable=False,
                        checkboxSelection=True, headerCheckboxSelection=True, suppressMenu=True, filter=False)
    # Hide internal/utility columns
    for c in df.columns:
        if str(c).startswith('_'):
            gb.configure_column(c, hide=True)

    # Hide all user cols not in visible selection
    for col in user_cols:
        if col not in visible_cols:
            gb.configure_column(col, hide=True)
            continue



        # Enable large text editor popup for columns with long data lists
        if col in ["roles", "departments", "units", "locations", "userName"]:
            gb.configure_column(col, cellEditor="agLargeTextCellEditor", cellEditorParams={"cols": 50, "rows": 6})

        if col in ["thirdPartyUsername", "passwordPolicy", "lastWorkingDate", "dateOfJoining", "shiftDuration"]:
            gb.configure_column(col, minWidth=180)
        elif col == "userName":
            gb.configure_column(col, cellStyle=JsCode("""
                function(params) {
                    if (params.data && params.data._is_duplicate_username === true) {
                        return { 'background-color': '#ffcdd2' };
                    }
                    return null;
                }
            """))
        elif col in ("email", "phone", "departments", "units", "roles"):
            gb.configure_column(col, cellStyle=JsCode(f"""
                function(params) {{
                    if (params.data && params.data._is_updated_{col} === true) {{
                        return {{ 'background-color': '#e8f5e9', 'font-weight': 'bold' }};
                    }}
                    return null;
                }}
            """))

    _is_large = len(df) > _LARGE_DATASET_ROWS
    _row_style_js = JsCode("""
        function(params) {
            if (params.data && params.data._is_duplicate_user === true) {
                return { 'background-color': '#ffcdd2' };
            }
            return null;
        }
    """)

    if _is_large:
        gb.configure_pagination(enabled=True, paginationAutoPageSize=False, paginationPageSize=200)
        gb.configure_grid_options(
            paginationPageSizeSelector=[200, 400, 600, 800, 1000],
            rowSelection='multiple',
            suppressRowClickSelection=True,
            enableRangeSelection=True,
            enableFillHandle=True,
            undoRedoCellEditing=False,
            getRowStyle=_row_style_js,
            onCellDoubleClicked=_CELL_CLICK_MODAL_JS,
            suppressClickEdit=True
        )
    else:
        gb.configure_grid_options(
            rowSelection='multiple',
            suppressRowClickSelection=True,
            enableRangeSelection=True,
            enableFillHandle=True,
            undoRedoCellEditing=True,
            undoRedoCellEditingLimit=20,
            getRowStyle=_row_style_js,
            onCellDoubleClicked=_CELL_CLICK_MODAL_JS,
            suppressClickEdit=True
        )
    return gb


def render_data_grid(df: pd.DataFrame, navigation: str, api_key: str):
    """
    Render the full data grid section: visibility toggles, AgGrid,
    grid controls (add/delete/undo/redo/save), and the download button.

    Mutates ``st.session_state`` as needed and calls ``st.rerun()``
    when state changes require a full page redraw.
    """
    if df.empty:
        st.warning("⚠️ No users were found in the uploaded file.")
        return

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
    user_cols = [c for c in df.columns if c != '#' and not str(c).startswith('_')]
    default_visible = [c for c in ["userName", "firstName", "lastName", "departments", "roles", "units", "locations", "email", "phone", "employeeId", "password", "designation", "isEnabled"] if c in user_cols]

    if 'visible_cols' not in st.session_state:
        st.session_state.visible_cols = default_visible
    else:
        st.session_state.visible_cols = [c for c in st.session_state.visible_cols if c in user_cols]

    # --- SUMMARY DASHBOARD ---
    m1, _, _, _ = st.columns(4)
    m1.metric("Total Users", len(df))

    with st.expander("👁️ Column Visibility"):
        cv1, cv2, cv3, _ = st.columns([1, 1, 1, 3])
        if cv1.button("\u2705 All"):     st.session_state.visible_cols = user_cols
        if cv2.button("\u274c Clear"):   st.session_state.visible_cols = ["userName"]
        if cv3.button("\U0001f504 Default"): st.session_state.visible_cols = default_visible

        new_selection = st.multiselect("Hide/Show Columns", options=user_cols, default=st.session_state.visible_cols)
        if new_selection != st.session_state.visible_cols:
            st.session_state.visible_cols = new_selection

    # --- DUPLICATE DETECTION ---
    df = _detect_duplicates(df)

    # --- AGGRID ---
    gb = _build_grid_options(df, user_cols, st.session_state.visible_cols)
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

    # ── Optimized Grid → SessionState sync ────────────────────────────────────
    _just_undone = st.session_state.pop('just_undone', False)
    if not _just_undone and grid_response['data'] is not None:
        new_data = grid_response['data']
        watch_cols = [
            c for c in new_data.columns
            if not str(c).startswith('_')
            and not str(c).startswith('::')
            and c != '#'
            and c in df.columns
        ]
        new_hash = _df_hash(new_data, watch_cols)
        if new_hash != st.session_state._df_users_hash:
            curr_cleaned = df[watch_cols].astype(object).fillna("").reset_index(drop=True)
            new_cleaned  = new_data[watch_cols].astype(object).fillna("").reset_index(drop=True)
            if not curr_cleaned.equals(new_cleaned):
                _save_cell_diff(df, new_data)
                st.session_state.df_users = enforce_contract(new_data)
                _recalculate_duplicates()
                st.session_state._df_users_hash = new_hash
                st.rerun()
            else:
                st.session_state._df_users_hash = new_hash

    # --- GRID CONTROLS ---
    _render_grid_controls(df, grid_response, navigation, api_key)


def _render_grid_controls(df, grid_response, navigation, api_key):
    """Add Row, Delete, Undo, Redo, Save & Validate, and Download buttons."""

    def _save_state():
        _save_snapshot(df)

    c_add, c_del, c_dedup, c_u, c_r, c_save = st.columns([1.0, 1.0, 1.0, 0.5, 0.5, 2.0])

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
        _update_users_hash()
        st.session_state.grid_key += 1
        st.rerun()

    if c_del.button("🗑️ DELETE", width="stretch"):
        sel_rows = grid_response.get('selected_rows')
        if sel_rows is not None and len(sel_rows) > 0:
            _save_state()
            if isinstance(sel_rows, pd.DataFrame):
                delete_ids = sel_rows['#'].tolist()
            else:
                delete_ids = [r.get('#') for r in sel_rows if r.get('#') is not None]
            st.session_state.df_users = df[~df['#'].isin(delete_ids)].reset_index(drop=True)
            st.session_state.df_users['#'] = range(1, len(st.session_state.df_users) + 1)
            _recalculate_duplicates()
            _update_users_hash()
            st.session_state.grid_key += 1
            st.rerun()
        else:
            st.warning("Please select rows to delete.")

    if c_dedup.button("✨ RESOLVE DUPLICATES", width="stretch", help="Make duplicate usernames unique by appending sequential numbers (e.g. arvindkumar1, arvindkumar2)."):
        _save_state()
        updated_df, resolved_count = resolve_duplicate_usernames(df)
        if resolved_count > 0:
            st.session_state.df_users = updated_df
            _recalculate_duplicates()
            _update_users_hash()
            st.session_state.grid_key += 1
            st.toast(f"✅ Successfully resolved {resolved_count} duplicate username(s)!", icon="✨")
            st.rerun()
        else:
            st.toast("ℹ️ No duplicate usernames found to resolve.", icon="ℹ️")

    if c_u.button("↩️ Undo", help="Undoes bulk actions like Delete/AI. (Jumps to top)"):
        if st.session_state.get('undo_stack'):
            st.session_state.df_users = _pop_undo(df)
            _recalculate_duplicates()
            _update_users_hash()
            st.session_state.grid_key += 1
            st.session_state.just_undone = True
            st.rerun()

    if c_r.button("↪️ Redo", help="Redoes bulk actions. (Jumps to top)"):
        if st.session_state.get('redo_stack'):
            st.session_state.df_users = _pop_redo(df)
            _recalculate_duplicates()
            _update_users_hash()
            st.session_state.grid_key += 1
            st.session_state.just_undone = True
            st.rerun()

    if c_save.button("💾 SAVE AND VALIDATE", type="primary", width="stretch"):
        grid_data = grid_response['data'].copy()
        saved_df = enforce_contract(grid_data)
        if '::auto_unique_id::' in saved_df.columns:
            saved_df = saved_df.drop(columns=['::auto_unique_id::'])
        if '#' in saved_df.columns:
            saved_df['#'] = range(1, len(saved_df) + 1)
        st.session_state.df_users = saved_df
        _recalculate_duplicates()
        _update_users_hash()
        st.session_state._excel_cache = {}

        from ai.openai_service import validate_master_data
        errors, warnings = validate_master_data(grid_data)

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
    from ui.ai_assistant import render_ai_assistant
    render_ai_assistant(df, api_key, grid_response)

    st.markdown("---")

    # --- EXPORT / DOWNLOAD ---
    _render_download(df, grid_response, navigation)


def _render_download(df, grid_response, navigation):
    """Cached Excel export and download button."""
    # Sync back to segregation_dfs if in Both mode
    if navigation == "Both (Segregation New & Existing Users)":
        if 'segregation_view_choice' in st.session_state and 'segregation_dfs' in st.session_state:
            current_choice = st.session_state['segregation_view_choice']
            st.session_state.df_users = enforce_contract(grid_response['data'])
            _recalculate_duplicates()
            st.session_state['segregation_dfs'][current_choice] = st.session_state.df_users.copy()
            _update_users_hash()

    if navigation == "Both (Segregation New & Existing Users)" and 'segregation_dfs' in st.session_state:
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
        _export_hash_key = str(st.session_state._df_users_hash)
        if _export_hash_key not in st.session_state._excel_cache:
            _export_df = grid_response['data'].copy()

            # --- Capture BOTH flags BEFORE dropping internal columns ---
            # Flag 1: full-row exact clone (_is_duplicate_user)
            _dup_full_rows = []
            if '_is_duplicate_user' in _export_df.columns:
                _full_mask = _export_df['_is_duplicate_user'].astype(str).str.strip().str.lower().isin({'true', '1', 't'})
                _dup_full_rows = [i for i, v in enumerate(_full_mask) if v]

            # Flag 2: userName collision only (_is_duplicate_username)
            _dup_uname_rows = []
            if '_is_duplicate_username' in _export_df.columns and 'userName' in _export_df.columns:
                _uname_mask = _export_df['_is_duplicate_username'].astype(str).str.strip().str.lower().isin({'true', '1', 't'})
                _dup_uname_rows = [i for i, v in enumerate(_uname_mask) if v]

            for _drop_col in list(_export_df.columns):
                if _drop_col == '#' or _drop_col == '::auto_unique_id::' or str(_drop_col).startswith('_'):
                    _export_df = _export_df.drop(columns=[_drop_col])

            _export_df = _export_df.reset_index(drop=True)
            _all_cols = list(_export_df.columns)

            _buf = io.BytesIO()
            import pandas.io.formats.excel
            try:
                pandas.io.formats.excel.ExcelFormatter.header_style = None
            except (AttributeError, TypeError):
                pass

            with pd.ExcelWriter(_buf, engine='xlsxwriter') as _writer:
                _export_df.to_excel(_writer, index=False, sheet_name='Users')
                _worksheet = _writer.sheets['Users']
                _workbook = _writer.book

                _text_format = _workbook.add_format({'num_format': '@'})
                for _i, _col in enumerate(_all_cols):
                    _col_str_lengths = [len(str(_val)) for _val in _export_df[_col] if pd.notna(_val)]
                    _max_len = max(
                        max(_col_str_lengths) if _col_str_lengths else 0,
                        len(str(_col))
                    ) + 2
                    _worksheet.set_column(_i, _i, min(_max_len, 50), _text_format)

                # --- Highlight 1: full row pink for exact-clone duplicates ---
                if _dup_full_rows:
                    _full_row_fmt = _workbook.add_format({
                        'num_format': '@',
                        'bg_color':   '#FFCDD2',
                    })
                    for _row_pos in _dup_full_rows:
                        _xl_row = _row_pos + 1
                        for _ci, _col in enumerate(_all_cols):
                            _worksheet.write(_xl_row, _ci, str(_export_df.at[_row_pos, _col]), _full_row_fmt)

                # --- Highlight 2: userName cell pink for username collisions ---
                if _dup_uname_rows and 'userName' in _all_cols:
                    _uname_fmt = _workbook.add_format({
                        'num_format': '@',
                        'bg_color':   '#FFCDD2',
                    })
                    _uname_col_idx = _all_cols.index('userName')
                    for _row_pos in _dup_uname_rows:
                        _xl_row = _row_pos + 1
                        _cell_val = str(_export_df.at[_row_pos, 'userName'])
                        _worksheet.write(_xl_row, _uname_col_idx, _cell_val, _uname_fmt)

            st.session_state._excel_cache = {_export_hash_key: _buf.getvalue()}

        _excel_bytes = st.session_state._excel_cache[_export_hash_key]
        st.download_button(
            label="📥 DOWNLOAD USER MASTER (.xlsx)",
            data=_excel_bytes,
            file_name="user_master_export.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width="stretch"
        )
