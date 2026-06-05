import streamlit as st
import pandas as pd
from .core import detect_duplicates, compare_users
from .export import generate_segregation_workbook
import io

def read_file(uploaded_file):
    if uploaded_file.name.endswith('.csv'):
        return pd.read_csv(uploaded_file)
    else:
        return pd.read_excel(uploaded_file)

def render_segregation_ui():
    st.markdown("## 👥 User Segregation & Comparison")
    st.markdown("Upload a Client User file and the Medblaze User Master file to identify new vs existing users.")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### Step 1: Client File")
        client_file = st.file_uploader("Upload Client Config File", type=["xlsx", "xls", "csv"], key="client_file")
        
    with col2:
        st.markdown("### Step 2: Medblaze Master File")
        master_file = st.file_uploader("Upload Medblaze User Master", type=["xlsx", "xls", "csv"], key="master_file")
        
    if client_file and master_file:
        try:
            client_df = read_file(client_file)
            master_df = read_file(master_file)
            
            # Identify common columns
            common_cols = list(set(client_df.columns).intersection(set(master_df.columns)))
            
            if not common_cols:
                st.error("No common columns found between the two files. Cannot perform matching.")
                return
                
            st.markdown("---")
            st.markdown("### Step 3: Matching Configuration")
            st.info(f"Found {len(common_cols)} common columns. Please select the fields to use for matching and their priority.")
            
            # Let user select priority fields using a multiselect.
            # Streamlit preserves the order of selection in the returned list.
            st.markdown("**Matching Mode:** Priority-Based Matching")
            st.markdown("Select columns in the order of their priority (e.g., Select Employee ID first, then Username).")
            
            priority_cols = st.multiselect(
                "Select Matching Fields (Priority Order)",
                options=common_cols,
                default=[c for c in ['employeeId', 'userName', 'email', 'mobile'] if c in common_cols]
            )
            
            if priority_cols:
                st.write("**Priority Order:**")
                for i, col in enumerate(priority_cols):
                    st.write(f"{i+1}. `{col}`")
                    
                if st.button("🚀 Run Segregation & Comparison", type="primary"):
                    with st.status("Processing files...", expanded=True) as status:
                        st.write("Detecting duplicates in client file...")
                        cleaned_client_df, duplicates_df = detect_duplicates(client_df, priority_cols)
                        
                        st.write(f"Found {len(duplicates_df)} duplicates. Proceeding with {len(cleaned_client_df)} unique records.")
                        
                        st.write("Running priority-based dictionary matching...")
                        results_df = compare_users(cleaned_client_df, master_df, priority_cols)
                        
                        st.write("Generating output workbook...")
                        file_names = {
                            'client': client_file.name,
                            'master': master_file.name
                        }
                        excel_data = generate_segregation_workbook(results_df, duplicates_df, file_names)
                        
                        status.update(label="✅ Processing Complete!", state="complete")
                        
                    # Results Dashboard
                    st.markdown("---")
                    st.markdown("### 📊 Results Summary")
                    
                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("Total Uploaded", len(client_df))
                    m2.metric("Existing Users", len(results_df[results_df['User Type'] == 'Existing User']))
                    m3.metric("New Users", len(results_df[results_df['User Type'] == 'New User']))
                    m4.metric("Duplicates", len(duplicates_df))
                    
                    st.download_button(
                        label="📥 Download Segregation Report (.xlsx)",
                        data=excel_data,
                        file_name="User_Segregation_Report.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        type="primary"
                    )
                    
        except Exception as e:
            st.error(f"Error reading files or processing: {e}")
