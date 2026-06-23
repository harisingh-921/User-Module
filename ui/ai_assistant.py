# user_masters/ui/ai_assistant.py
"""
AI Configuration Assistant panel.

Renders: mapping file uploader, command text input, history,
Apply AI button, and the two-step preview/confirm flow.
"""
import concurrent.futures
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
        key="ai_mapping_file",
        help="Upload a file with lookup data, such as mapping Client Departments to Medblaze Departments."
    )

    _is_ai_running = bool(st.session_state.get('_ai_running'))

    # ── Command input + Apply button — hidden while AI is in flight ───────────
    # Hiding completely (not just disabling) prevents any chance of a second
    # parallel API call being submitted while one is already running.
    if not _is_ai_running:
        # Ensure text input is ALWAYS rendered first
        chat_input_key = f"ai_chat_cmd_{st.session_state.chat_input_key}"

        # If a history pill was clicked, copy it to the text input state before the widget is instantiated
        if st.session_state.get("selected_history_cmd"):
            st.session_state[chat_input_key] = st.session_state["selected_history_cmd"]
            st.session_state["selected_history_cmd"] = None

        chat_cmd = st.text_input(
            "✍️ Command / Changes to make",
            placeholder="e.g. 'Map the departments column' or 'Set isEnabled to Yes for all'",
            key=chat_input_key
        )

        # Inject HTML5 datalist to show history as native browser dropdown suggestions on input focus
        if st.session_state.ai_cmd_history:
            unique_history = list(dict.fromkeys(st.session_state.ai_cmd_history))[:10]
            options_html = "".join([f'<option value="{cmd}">' for cmd in unique_history])

            datalist_html = f"""
            <script>
                const parentDoc = window.parent.document;

                function attachDatalist() {{
                    const inputs = parentDoc.querySelectorAll('input[type="text"]');
                    for (const input of inputs) {{
                        if (input.placeholder && input.placeholder.includes("Map the departments column")) {{
                            input.setAttribute("list", "ai-cmd-history-list");
                            input.setAttribute("autocomplete", "on");

                            let dl = parentDoc.getElementById("ai-cmd-history-list");
                            if (!dl) {{
                                dl = parentDoc.createElement("datalist");
                                dl.id = "ai-cmd-history-list";
                                parentDoc.body.appendChild(dl);
                            }}
                            dl.innerHTML = `{options_html}`;
                            break;
                        }}
                    }}
                }}

                attachDatalist();
                setTimeout(attachDatalist, 300);
                setTimeout(attachDatalist, 800);
            </script>
            """
            import streamlit.components.v1 as components
            components.html(datalist_html, height=0, width=0)

        if st.button("🪄 Apply AI"):
            if not api_key:
                st.error("🔑 **API Key Missing**: Please configure `OPENAI_API_KEY` (or `GEMINI_API_KEY`) in Streamlit Cloud Secrets (or `.streamlit/secrets.toml` locally) to use the AI Assistant.")
            elif not chat_cmd:
                st.warning("Please enter a command.")
            else:
                # Read mapping file NOW on main thread (UploadedFile is not thread-safe)
                context_df = None
                if mapping_file is not None:
                    try:
                        if mapping_file.name.endswith('.csv'):
                            context_df = pd.read_csv(mapping_file)
                        else:
                            context_df = pd.read_excel(mapping_file)
                    except Exception as e:
                        st.error(f"Error reading mapping file: {e}")

                # Snapshot df for thread (avoid shared mutable state)
                df_snapshot = df.copy()

                # Launch background thread — exactly ONE call, no double-submit possible
                executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
                from ai.openai_service import apply_ai_smart_context
                future = executor.submit(apply_ai_smart_context, df_snapshot, chat_cmd, api_key, context_df)
                executor.shutdown(wait=False)

                st.session_state._ai_running = {
                    'future':    future,
                    'cmd':       chat_cmd,
                    'cancelled': False,
                }
                st.rerun()

    # ── AI Status — only this fragment re-renders every 2s while AI is running ─
    # Uses st.fragment so the heavy AgGrid above is NOT touched during polling.
    if st.session_state.get('_ai_running'):

        @st.fragment(run_every=2)
        def _ai_status_fragment():
            run = st.session_state.get('_ai_running')
            if not run:
                # Already finished / cancelled on a previous cycle
                st.rerun()
                return

            future = run['future']

            if run.get('cancelled'):
                future.cancel()
                st.session_state._ai_running = None
                st.toast("🛑 AI request cancelled.", icon="🛑")
                st.rerun()
                return

            if future.done():
                # Result ready — collect and store, then trigger full rerun
                st.session_state._ai_running = None
                try:
                    updated_df, summary = future.result()
                except Exception as e:
                    st.session_state._ai_error = str(e)[:200]
                    st.rerun()
                    return

                if updated_df is not None:
                    diff_df = _compute_ai_diff(df, updated_df)
                    st.session_state._ai_preview = {
                        'updated_df': updated_df,
                        'summary':    summary,
                        'diff_df':    diff_df,
                        'cmd':        run['cmd'],
                    }
                else:
                    st.session_state._ai_error = summary
                st.rerun()
                return

            # Still running — render status + Cancel (only this widget box refreshes)
            col_status, col_cancel = st.columns([5, 1])
            with col_status:
                with st.status("🧠 AI is processing your request…", expanded=True):
                    st.write("⏳ Waiting for AI response — this usually takes 5–30 seconds…")
            with col_cancel:
                st.write("")  # vertical spacing to align with status box
                if st.button("🛑 Cancel", type="secondary", use_container_width=True, key="ai_cancel_btn"):
                    st.session_state._ai_running['cancelled'] = True


        _ai_status_fragment()

    # Show any error that came back from the AI thread
    if st.session_state.get('_ai_error'):
        st.error(f"❌ {st.session_state.pop('_ai_error')}")

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
                st.session_state.df_users       = preview['updated_df']
                _recalculate_duplicates()
                _update_users_hash()
                st.session_state._ai_preview    = None
                st.session_state.grid_key       += 1
                st.session_state.ai_cmd_history.insert(0, preview['cmd'])
                st.session_state.chat_input_key += 1
                st.rerun()
            if pc2.button("❌ Cancel", width="stretch"):
                st.session_state._ai_preview = None
                st.rerun()
