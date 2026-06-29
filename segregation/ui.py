import streamlit as st
import pandas as pd
from .core import detect_duplicates, compare_users
from .export import generate_segregation_workbook
import io

def read_file(uploaded_file):
    if uploaded_file.name.endswith('.csv'):
        df = pd.read_csv(uploaded_file)
    else:
        df = pd.read_excel(uploaded_file)
    
    # Drop rows that are completely empty (all NaNs)
    df = df.dropna(how='all')
    
    # Silently drop exact identical clones to prevent the UI from surfacing them as errors
    return df.drop_duplicates(keep='first')

def guess_col_index(cols, opt_name):
    """Tries to guess the correct column index for a given standard field."""
    aliases = {
        "Employee ID": ["employeeid", "employee id", "emp id", "employee no", "employeeno", "staff id"],
        "Mail": ["email", "mail", "email address", "e-mail"],
        "Mobile Number": ["mobile", "phone", "mobile number", "contact", "phone number"],
        "Username": ["username", "user name", "name", "full name", "employee name"]
    }
    opt_aliases = aliases.get(opt_name, [opt_name.lower()])
    
    # Exact match in aliases
    for i, col in enumerate(cols):
        if str(col).lower().strip() in opt_aliases:
            return i + 1  # +1 because of "-- Select --" at index 0
            
    # Partial match
    for i, col in enumerate(cols):
        for alias in opt_aliases:
            if alias in str(col).lower().strip():
                return i + 1
    return 0

def render_segregation_ui():
    st.markdown("## 👥 User Segregation & Comparison")
    st.markdown("Upload a Client User file and the Medblaze User Master file to identify new vs existing users.")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### Step 1: Client File")
        client_file = st.file_uploader("Upload Client Config File", key="client_file")
        
    with col2:
        st.markdown("### Step 2: Medblaze Master File")
        master_file = st.file_uploader("Upload Medblaze User Master", key="master_file")
        
    if client_file and master_file:
        try:
            client_df = read_file(client_file)
            master_df = read_file(master_file)
            
            st.markdown("---")
            st.markdown("### Step 3: Matching Configuration")
            
            st.markdown("**Matching Mode:** Priority-Based Matching")
            st.markdown("Select columns in the order of their priority (e.g., Select Employee ID first, then Username).")
            
            standard_options = ["Employee ID", "Mail", "Mobile Number", "Username", "Other"]
            
            selected_options = st.multiselect(
                "Select Matching Fields (Priority Order)",
                options=standard_options,
                default=["Employee ID", "Mail"]
            )
            
            priority_mappings = []
            
            if selected_options:
                st.write("**Map Selected Fields to File Columns:**")
                
                client_cols = list(client_df.columns)
                master_cols = list(master_df.columns)
                
                all_mapped = True
                
                for opt in selected_options:
                    col1, col2 = st.columns(2)
                    with col1:
                        c_idx = guess_col_index(client_cols, opt)
                        c_col = st.selectbox(f"Client Column for '{opt}'", ["-- Select --"] + client_cols, index=c_idx, key=f"client_{opt}")
                    with col2:
                        m_idx = guess_col_index(master_cols, opt)
                        m_col = st.selectbox(f"Master Column for '{opt}'", ["-- Select --"] + master_cols, index=m_idx, key=f"master_{opt}")
                    
                    if c_col != "-- Select --" and m_col != "-- Select --":
                        priority_mappings.append({
                            'name': opt,
                            'client_col': c_col,
                            'master_col': m_col
                        })
                    else:
                        all_mapped = False
                        
                if all_mapped and priority_mappings:
                    st.markdown("---")
                    st.write("**Priority Order Confirmed:**")
                    for i, m in enumerate(priority_mappings):
                        st.write(f"{i+1}. `{m['name']}` (Client: `{m['client_col']}` ↔ Master: `{m['master_col']}`)")
                        
                    if st.button("🚀 Run Segregation & Comparison", type="primary"):
                        with st.status("Processing files...", expanded=True) as status:
                            st.write("Detecting duplicates in client file...")
                            flagged_df = detect_duplicates(client_df, priority_mappings)
                            
                            dup_count = flagged_df['Is Duplicate'].sum()
                            st.write(f"Found {dup_count} duplicates. Proceeding with comparison...")
                            
                            st.write("Running priority-based dictionary matching...")
                            results_df = compare_users(flagged_df, master_df, priority_mappings)
                            
                            st.write("Formatting results...")
                            from .export import format_segregation_results
                            formatted_dfs = format_segregation_results(results_df, priority_mappings)
                            
                            # Store in session state for AgGrid editor
                            st.session_state['segregation_dfs'] = formatted_dfs
                            # Default choice
                            st.session_state['segregation_view_choice'] = 'Existing Users'
                            # Force app.py to reload the new dataframe instead of using the cached one
                            if 'prev_segregation_view_choice' in st.session_state:
                                del st.session_state['prev_segregation_view_choice']
                            
                            status.update(label="✅ Processing Complete!", state="complete")
                            
                    # If we have run segregation, show the results and toggle
                    if 'segregation_dfs' in st.session_state:
                        # Results Dashboard
                        st.markdown("---")
                        st.markdown("### 📊 Results Summary")
                        
                        m1, m2, m3, m4 = st.columns(4)
                        m1.metric("Total Uploaded", len(client_df))
                        m2.metric("Existing Users", len(st.session_state['segregation_dfs']['Existing Users']))
                        m3.metric("New Users", len(st.session_state['segregation_dfs']['New Users']))
                        # Calculate dup count from the saved dataframe
                        dup_existing = st.session_state['segregation_dfs']['Existing Users']['_is_duplicate_user'].sum() if not st.session_state['segregation_dfs']['Existing Users'].empty else 0
                        dup_new = st.session_state['segregation_dfs']['New Users']['_is_duplicate_user'].sum() if not st.session_state['segregation_dfs']['New Users'].empty else 0
                        m4.metric("Duplicates Flagged", dup_existing + dup_new)
                        
                        # Sync logic handled by app.py
                        
                        # Inject custom CSS to enlarge and bold the radio button options
                        st.markdown("""
                        <style>
                        div[role="radiogroup"] label p {
                            font-size: 1.15rem !important;
                            font-weight: bold !important;
                        }
                        </style>
                        """, unsafe_allow_html=True)
                        
                        view_choice = st.radio("Select Dataset to Edit", ["Existing Users", "New Users"], horizontal=True, label_visibility="collapsed")
                        st.session_state['segregation_view_choice'] = view_choice
                        
                else:
                    st.warning("Please map all selected matching fields to continue.")
                    
        except Exception as e:
            st.error(f"Error reading files or processing: {e}")
