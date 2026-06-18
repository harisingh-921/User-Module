# user_masters/ui/sidebar.py
"""
Sidebar UI component for User Master Intelligence.

Renders: navigation radio, global settings (password prefix, smart context),
reset button, and how-to-use expander.
"""
import os
import streamlit as st


def render_sidebar():
    """Render the full sidebar. Returns the current navigation mode string."""
    with st.sidebar:
        # Brand Logo
        _logo_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logo.png")
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

        selected_nav = st.radio("Navigation Mode", ["New User", "Update User", "Both (Segregation New & Existing Users)"], key="nav_radio_key")
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

        st.markdown("""<div style='height:4px'></div>""", unsafe_allow_html=True)
        if st.button("🗑️ Full Reset", width="stretch"):
            st.cache_data.clear()
            for key in list(st.session_state.keys()):
                del st.session_state[key]
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

    return navigation
