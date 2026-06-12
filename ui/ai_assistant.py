# user_masters/ui/ai_assistant.py
"""
AI Configuration Assistant panel.

Renders: mapping file uploader, command text input, history,
Apply AI button, and the two-step preview/confirm flow.
"""
import pandas as pd
import streamlit as st

from utils.history import (
    _compute_ai_diff, _recalculate_duplicates, _update_users_hash,
    _save_snapshot
)


def render_ai_assistant(df: pd.DataFrame, api_key: str, grid_response):
    """Render the AI assistant section below the data grid."""
    st.markdown("---")
    st.subheader("💬 AI Configuration Assistant")

    mapping_file = st.file_uploader(
        "Upload Context/Mapping File (Optional)",
        type=["xlsx", "xls", "csv"],
        key="ai_mapping_file",
        help="Upload a file with lookup data, such as mapping Client Departments to Medblaze Departments."
    )

    # Ensure text input is ALWAYS rendered first
    chat_input_key = f"ai_chat_cmd_{st.session_state.chat_input_key}"

    chat_cmd = st.text_input(
        "✍️ Command / Changes to make",
        placeholder="e.g. 'Map the departments column' or 'Set isEnabled to Yes for all'",
        key=chat_input_key
    )

    # Render clean, clickable suggestion pills for 5-10 recent history items
    if st.session_state.ai_cmd_history:
        unique_history = list(dict.fromkeys(st.session_state.ai_cmd_history))[:8]
        st.markdown(
            "<div style='font-size:12px; font-weight:600; color:#64748b; margin-top:-8px; margin-bottom:4px;'>🕒 RECENT COMMANDS (click to fill):</div>",
            unsafe_allow_html=True
        )
        
        # Display as a grid of 4 columns per row
        cols_per_row = 4
        for i in range(0, len(unique_history), cols_per_row):
            chunk = unique_history[i:i+cols_per_row]
            cols = st.columns(cols_per_row)
            for idx, cmd in enumerate(chunk):
                label = cmd
                if len(label) > 35:
                    label = label[:32] + "..."
                if cols[idx].button(f"💬 {label}", key=f"hist_btn_{i+idx}_{st.session_state.chat_input_key}", help=cmd, use_container_width=True):
                    st.session_state[chat_input_key] = cmd
                    st.rerun()

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

    # ── AI Change Preview (two-step confirm) ──────────────────────────────────
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
                _save_snapshot(df)
                st.session_state.df_users        = preview['updated_df']
                _recalculate_duplicates()
                _update_users_hash()
                st.session_state._ai_preview     = None
                st.session_state.grid_key        += 1
                st.session_state.ai_cmd_history.insert(0, preview['cmd'])
                st.session_state.chat_input_key  += 1
                st.rerun()
            if pc2.button("❌ Cancel", width="stretch"):
                st.session_state._ai_preview = None
                st.rerun()


