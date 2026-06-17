# user_masters/ui/state_manager.py
"""
Centralised Streamlit session-state initialisation and helpers.

Every key that app.py needs at runtime is declared here so that
`KeyError` / `AttributeError` surprises are impossible.
"""
import streamlit as st


def init_session_state():
    """Call once at the top of the app to guarantee all state keys exist."""
    _defaults = {
        "undo_stack":       [],
        "redo_stack":       [],
        "_df_users_hash":   None,
        "_ai_preview":      None,
        "_excel_cache":     {},          # {hash: bytes}
        "current_nav":      "Both (Segregation New & Existing Users)",
        "nav_radio_key":    "Both (Segregation New & Existing Users)",
        "pass_prefix":      "Med",
        "user_intent":      "",
        "ai_cmd_history":   [],
        "chat_input_key":   0,
        "grid_key":         0,
    }
    for key, default in _defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default
