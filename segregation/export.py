import pandas as pd
import io
import datetime
import re
import streamlit as st
from utils.common import detect_duplicates_in_df, has_value
from config.constants import USER_MASTER_COLS, SEMANTIC_MAPPINGS

def format_segregation_results(client_df: pd.DataFrame, priority_mappings: list = None) -> dict:
    """
    Separates the client data into Existing and New users and formats them to the target template.
    Returns a dict with 'Existing Users' and 'New Users' dataframes.
    """
    if not client_df.empty:
        client_df = client_df.copy()
        # Detect the client department column (using semantic mappings)
        dept_aliases = SEMANTIC_MAPPINGS.get('departments', ['department', 'departments', 'dept'])
        dept_col = None
        for col in client_df.columns:
            col_str = str(col).strip().lower()
            if col_str in dept_aliases or any(alias == col_str for alias in dept_aliases):
                dept_col = col
                break
        
        if dept_col:
            # Collect all unique departments (excluding placeholders and 'all')
            unique_depts = []
            for val in client_df[dept_col].dropna():
                for part in str(val).split('|'):
                    part = part.strip()
                    if has_value(part) and part.lower() not in ('all', 'nan', 'none', '-', 'na', 'n/a'):
                        if part not in unique_depts:
                            unique_depts.append(part)
            
            if unique_depts:
                combined_depts = '|'.join(unique_depts)
                def expand_all_depts(x):
                    if pd.isna(x):
                        return x
                    if str(x).strip().lower() == 'all':
                        return combined_depts
                    return x
                client_df[dept_col] = client_df[dept_col].apply(expand_all_depts)

    existing_users = client_df[client_df['User Type'] == 'Existing User'].copy() if not client_df.empty else pd.DataFrame()
    new_users = client_df[client_df['User Type'] == 'New User'].copy() if not client_df.empty else pd.DataFrame()
    
    def format_to_template(df: pd.DataFrame, is_new: bool = False) -> pd.DataFrame:
        if df.empty:
            return df
            
        # First, apply the explicit priority mappings from the UI selection if available
        if priority_mappings:
            for mapping in priority_mappings:
                name = mapping.get('name')
                c_col = mapping.get('client_col')
                
                target_col = None
                if name == "Employee ID":
                    target_col = "employeeId"
                elif name == "Mail":
                    target_col = "email"
                elif name == "Mobile Number":
                    target_col = "phone"
                elif name == "Username":
                    target_col = "userName"
                    
                if target_col and c_col in df.columns:
                    from utils.common import has_value
                    if df[c_col].apply(has_value).any():
                        df[target_col] = df[c_col]
            
        # Try to find and split Full Name if firstName is empty/missing
        from utils.common import has_value
        if 'firstName' not in df.columns or not df['firstName'].apply(has_value).any():
            name_aliases = ('name', 'full name', 'fullname', 'staff name', 'employee name')
            name_col = None
            for col_name in df.columns:
                if str(col_name).strip().lower() in name_aliases:
                    name_col = col_name
                    break
            if name_col:
                def extract_first_name(val):
                    if pd.isna(val) or str(val).strip().lower() in ('', 'nan', 'none', '-', 'na', 'n/a'):
                        return ""
                    parts = str(val).strip().split()
                    return parts[0] if parts else ""
                
                def extract_last_name(val):
                    if pd.isna(val) or str(val).strip().lower() in ('', 'nan', 'none', '-', 'na', 'n/a'):
                        return ""
                    parts = str(val).strip().split()
                    return " ".join(parts[1:]) if len(parts) >= 2 else ""

                df['firstName'] = df[name_col].apply(extract_first_name)
                df['lastName'] = df[name_col].apply(extract_last_name)

        # Fallbacks to capture incorrectly named columns from the client file
        fallbacks = SEMANTIC_MAPPINGS
        from utils.common import has_value
        
        for col in USER_MASTER_COLS:
            is_empty_col = False
            if col in df.columns:
                if not df[col].apply(has_value).any():
                    is_empty_col = True
                    
            if col not in df.columns or is_empty_col:
                found = False
                if col in fallbacks:
                    for fb in fallbacks[col]:
                        # Case insensitive match for fallback columns
                        matching_cols = [c for c in df.columns if str(c).strip().lower() == fb]
                        if matching_cols:
                            candidate_col = matching_cols[0]
                            if df[candidate_col].apply(has_value).any():
                                df[col] = df[candidate_col]
                                found = True
                                break
                if not found and col not in df.columns:
                    df[col] = ''
                    
        # Intelligent Merge for Existing Users
        # Uses master data exactly, except for email, phone, and roles columns which can merge/fallback
        for col in USER_MASTER_COLS:
            master_col = f"master_{col}"
            if master_col in df.columns:
                if col in ('email', 'phone', 'departments', 'units'):
                    def merge_fallback_columns(row):
                        m_val = row.get(master_col, '')
                        c_val = row.get(col, '')
                        if pd.notna(m_val) and str(m_val).strip() != '' and str(m_val).strip().lower() != 'nan':
                            return m_val
                        return c_val if pd.notna(c_val) else ''
                    df[col] = df.apply(merge_fallback_columns, axis=1)
                elif col == 'roles':
                    def merge_roles(row):
                        m_role = str(row.get(master_col, '')).strip()
                        c_role = str(row.get(col, '')).strip()
                        if m_role.lower() == 'nan': m_role = ''
                        if c_role.lower() == 'nan': c_role = ''
                        
                        # Clean spaces around '|' inside individual roles first
                        m_role = "|".join([r.strip() for r in m_role.split('|') if r.strip()])
                        c_role = "|".join([r.strip() for r in c_role.split('|') if r.strip()])
                        
                        if m_role and c_role and m_role.lower() != c_role.lower():
                            if c_role.lower() not in m_role.lower():
                                return f"{m_role}|{c_role}"
                            return m_role
                        elif m_role:
                            return m_role
                        else:
                            return c_role
                    df[col] = df.apply(merge_roles, axis=1)
                else:
                    def keep_master_exactly(row):
                        m_val = row.get(master_col, '')
                        if pd.isna(m_val) or str(m_val).strip().lower() == 'nan':
                            return ''
                        return str(m_val).strip()
                    df[col] = df.apply(keep_master_exactly, axis=1)

                if not is_new and col in ('email', 'phone', 'departments', 'units', 'roles'):
                    def check_if_updated(row):
                        m_val = row.get(master_col, '')
                        final_val = row.get(col, '')
                        s_m = str(m_val).strip() if pd.notna(m_val) else ''
                        s_f = str(final_val).strip() if pd.notna(final_val) else ''
                        if s_m.lower() == 'nan': s_m = ''
                        if s_f.lower() == 'nan': s_f = ''
                        return s_m != s_f
                    df[f"_is_updated_{col}"] = df.apply(check_if_updated, axis=1)
                    
                    
        # Clean userName for new users: lowercase, no spaces, no special characters
        if is_new and 'userName' in df.columns:
            def clean_new_username(row):
                uname = str(row.get('userName', '')).strip()
                if pd.isna(row.get('userName', '')) or uname.lower() in ('', 'nan', 'none', '-', 'na', 'n/a'):
                    fn = str(row.get('firstName', '')).strip()
                    mn = str(row.get('middleName', '')).strip()
                    ln = str(row.get('lastName', '')).strip()
                    parts = []
                    for name_part in [fn, mn, ln]:
                        if pd.notna(name_part) and name_part.lower() not in ('', 'nan', 'none', '-', 'na', 'n/a'):
                            parts.append(name_part)
                    full_name = "".join(parts)
                    uname = full_name
                cleaned = re.sub(r'[^a-zA-Z0-9]', '', uname).lower()
                return cleaned
            df['userName'] = df.apply(clean_new_username, axis=1)

        # Default isEnabled to 'Yes' for new users if blank
        if is_new and 'isEnabled' in df.columns:
            df['isEnabled'] = df['isEnabled'].apply(
                lambda x: 'Yes' if pd.isna(x) or str(x).strip().lower() in ('', 'nan', 'none', '-', 'na', 'n/a') else x
            )

        # Generate password using Password Prefix for new users if not provided by client
        if is_new and 'password' in df.columns:
            pass_prefix = st.session_state.get("pass_prefix", "Med")
            
            def fill_new_password(row):
                pwd = str(row.get('password', '')).strip()
                if pd.isna(row.get('password')) or pwd.lower() in ('', 'nan', 'none', '-', 'na', 'n/a'):
                    emp_id = str(row.get('employeeId', '')).strip()
                    if emp_id and emp_id.lower() not in ('', 'nan', 'none', '-', 'na', 'n/a'):
                        return f"{pass_prefix}@{emp_id}"
                    return ''
                return pwd
            df['password'] = df.apply(fill_new_password, axis=1)

        # Clean spaces around '|' in roles column for all users
        if 'roles' in df.columns:
            def clean_roles_spaces(val):
                if pd.isna(val):
                    return ''
                val_str = str(val).strip()
                if val_str.lower() in ('', 'nan', 'none', '-', 'na', 'n/a'):
                    return ''
                return "|".join([r.strip() for r in val_str.split('|') if r.strip()])
            df['roles'] = df['roles'].apply(clean_roles_spaces)

        # Keep exactly the target columns
        final_cols = USER_MASTER_COLS.copy()
        
        # Add internal duplicate flag for AgGrid highlighting
        if 'Is Duplicate' in df.columns:
            df['_is_duplicate_user'] = df['Is Duplicate'].fillna(False).astype(bool)
            final_cols.append('_is_duplicate_user')
            
        df_final = df[final_cols].copy()
        
        # Add updated flags for highlighting
        for col in ('email', 'phone', 'departments', 'units', 'roles'):
            up_col = f"_is_updated_{col}"
            if up_col in df.columns:
                df_final[up_col] = df[up_col].fillna(False).astype(bool)
        
        # After mapping and stripping unmapped columns, drop any resulting exact clones
        check_cols = [c for c in df_final.columns if not str(c).startswith('_')]
        df_final = df_final.drop_duplicates(subset=check_cols, keep='first')
        
        # Since we just dropped exact clones, none of the remaining rows have exact clones in this dataframe!
        if '_is_duplicate_user' in df_final.columns:
            df_final['_is_duplicate_user'] = False
            
        return df_final
        
    return {
        'Existing Users': detect_duplicates_in_df(format_to_template(existing_users, is_new=False)),
        'New Users': detect_duplicates_in_df(format_to_template(new_users, is_new=True))
    }

def generate_segregation_workbook(dfs: dict) -> bytes:
    """
    Generates a multi-sheet Excel workbook from the dictionary of formatted dataframes.
    """
    buf = io.BytesIO()
    
    existing_users = detect_duplicates_in_df(dfs.get('Existing Users', pd.DataFrame())).copy()
    new_users = detect_duplicates_in_df(dfs.get('New Users', pd.DataFrame())).copy()

    def get_dup_full_indices(df):
        """Row indices (1-based, for xlsxwriter) of exact-clone duplicate rows."""
        if '_is_duplicate_user' in df.columns:
            return [i + 1 for i, val in enumerate(df['_is_duplicate_user']) if str(val).strip().lower() in ('true', '1', 't')]
        return []

    def get_dup_uname_indices(df):
        """Row indices (0-based) of userName-collision rows."""
        if '_is_duplicate_username' in df.columns:
            return [i for i, val in enumerate(df['_is_duplicate_username']) if str(val).strip().lower() in ('true', '1', 't')]
        return []

    existing_dup_full_idx  = get_dup_full_indices(existing_users)
    existing_dup_uname_idx = get_dup_uname_indices(existing_users)
    new_dup_full_idx       = get_dup_full_indices(new_users)
    new_dup_uname_idx      = get_dup_uname_indices(new_users)

    # Collect coordinates of updated cells for Existing Users (1-based row index)
    existing_updated_cells = []
    if not existing_users.empty:
        excel_cols = [c for c in existing_users.columns if c != '#' and not str(c).startswith('_')]
        for col in ('email', 'phone', 'departments', 'units', 'roles'):
            up_col = f"_is_updated_{col}"
            if up_col in existing_users.columns and col in excel_cols:
                col_idx = excel_cols.index(col)
                df_reset = existing_users.reset_index(drop=True)
                for row_pos, val in enumerate(df_reset[up_col]):
                    if str(val).strip().lower() in ('true', '1', 't'):
                        cell_val = df_reset.at[row_pos, col]
                        existing_updated_cells.append((row_pos + 1, col_idx, str(cell_val) if pd.notna(cell_val) else ''))

    # Drop internal columns before exporting to Excel
    for df in [existing_users, new_users]:
        cols_to_drop = [c for c in df.columns if str(c).startswith('_') or c == '#']
        if cols_to_drop:
            df.drop(columns=cols_to_drop, inplace=True)

    # Write to Excel
    with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
        # Formatting
        workbook = writer.book
        duplicate_format  = workbook.add_format({'bg_color': '#FFC7CE'})
        uname_dup_format  = workbook.add_format({'bg_color': '#FFC7CE', 'num_format': '@'})
        header_format     = workbook.add_format()  # Plain format with no bold or borders
        updated_format    = workbook.add_format({'bg_color': '#E8F5E9', 'font_color': '#2E7D32', 'num_format': '@'})

        # Prepare datasets with fallback messages
        sheets_data = [
            ('Existing Users', existing_users if not existing_users.empty else pd.DataFrame([{'Message': 'No existing users found'}]), existing_dup_full_idx, existing_dup_uname_idx),
            ('New Users',      new_users      if not new_users.empty      else pd.DataFrame([{'Message': 'No new users found'}]),      new_dup_full_idx,      new_dup_uname_idx),
        ]

        for sheet_name, df_sheet, dup_full_indices, dup_uname_indices in sheets_data:
            if df_sheet.empty or 'Message' in df_sheet.columns:
                df_sheet.to_excel(writer, sheet_name=sheet_name, index=False)
                continue

            # Write data without headers starting from row 1 (second row)
            df_sheet.to_excel(writer, sheet_name=sheet_name, index=False, header=False, startrow=1)
            worksheet = writer.sheets[sheet_name]

            # Write plain headers manually
            for col_num, value in enumerate(df_sheet.columns.values):
                worksheet.write(0, col_num, value, header_format)

            # Create a text format for the cells
            text_format = workbook.add_format({'num_format': '@'})

            # Set all column widths based on maximum string length in each column to auto-fit
            for col_idx, col_name in enumerate(df_sheet.columns):
                col_str_lengths = [len(str(val)) for val in df_sheet[col_name] if pd.notna(val)]
                max_len = max(
                    max(col_str_lengths) if col_str_lengths else 0,
                    len(str(col_name))
                ) + 2
                worksheet.set_column(col_idx, col_idx, min(max_len, 50), text_format)

            # --- Highlight 1: full row pink for exact-clone duplicate rows ---
            if dup_full_indices:
                for row_idx in dup_full_indices:
                    worksheet.conditional_format(row_idx, 0, row_idx, len(df_sheet.columns) - 1,
                                                 {'type': 'no_blanks', 'format': duplicate_format})
                    worksheet.conditional_format(row_idx, 0, row_idx, len(df_sheet.columns) - 1,
                                                 {'type': 'blanks', 'format': duplicate_format})

            # --- Highlight 2: userName cell pink+bold for username collisions ---
            if dup_uname_indices and 'userName' in df_sheet.columns:
                uname_col_idx = list(df_sheet.columns).index('userName')
                df_sheet_reset = df_sheet.reset_index(drop=True)
                for row_pos in dup_uname_indices:
                    xl_row   = row_pos + 1   # +1 for the manually-written header at row 0
                    cell_val = str(df_sheet_reset.at[row_pos, 'userName'])
                    worksheet.write(xl_row, uname_col_idx, cell_val, uname_dup_format)

            # --- Highlight 3: soft green cell background for updated/merged columns (Existing Users only) ---
            if sheet_name == 'Existing Users' and existing_updated_cells:
                for xl_row, col_idx, cell_val in existing_updated_cells:
                    worksheet.write(xl_row, col_idx, cell_val, updated_format)

    return buf.getvalue()

