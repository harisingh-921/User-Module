import pandas as pd
import io
import datetime

def format_segregation_results(client_df: pd.DataFrame) -> dict:
    """
    Separates the client data into Existing and New users and formats them to the target template.
    Returns a dict with 'Existing Users' and 'New Users' dataframes.
    """
    existing_users = client_df[client_df['User Type'] == 'Existing User'].copy() if not client_df.empty else pd.DataFrame()
    new_users = client_df[client_df['User Type'] == 'New User'].copy() if not client_df.empty else pd.DataFrame()
    
    from config.constants import USER_MASTER_COLS, SEMANTIC_MAPPINGS
    
    def format_to_template(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
            
        # Fallbacks to capture incorrectly named columns from the client file
        fallbacks = SEMANTIC_MAPPINGS
        
        for col in USER_MASTER_COLS:
            if col not in df.columns:
                found = False
                if col in fallbacks:
                    for fb in fallbacks[col]:
                        # Case insensitive match for fallback columns
                        matching_cols = [c for c in df.columns if str(c).strip().lower() == fb]
                        if matching_cols:
                            df[col] = df[matching_cols[0]]
                            found = True
                            break
                if not found:
                    df[col] = ''
                    
        # Intelligent Merge for Existing Users
        # Uses master data as base, overwrites with client data, applies special rules for roles and employeeId
        for col in USER_MASTER_COLS:
            master_col = f"master_{col}"
            if master_col in df.columns:
                if col == 'employeeId':
                    def merge_emp_id(row):
                        m_val = row.get(master_col, '')
                        c_val = row.get(col, '')
                        if pd.notna(m_val) and str(m_val).strip() != '' and str(m_val).strip().lower() != 'nan':
                            return m_val
                        return c_val if pd.notna(c_val) else ''
                    df[col] = df.apply(merge_emp_id, axis=1)
                elif col == 'roles':
                    def merge_roles(row):
                        m_role = str(row.get(master_col, '')).strip()
                        c_role = str(row.get(col, '')).strip()
                        if m_role.lower() == 'nan': m_role = ''
                        if c_role.lower() == 'nan': c_role = ''
                        
                        if m_role and c_role and m_role.lower() != c_role.lower():
                            if c_role.lower() not in m_role.lower():
                                return f"{m_role} | {c_role}"
                            return m_role
                        elif m_role:
                            return m_role
                        else:
                            return c_role
                    df[col] = df.apply(merge_roles, axis=1)
                else:
                    def merge_general(row):
                        m_val = row.get(master_col, '')
                        c_val = row.get(col, '')
                        if pd.notna(m_val) and str(m_val).strip() != '' and str(m_val).strip().lower() != 'nan':
                            return m_val
                        return c_val if pd.notna(c_val) else ''
                    df[col] = df.apply(merge_general, axis=1)
                    
        # Keep exactly the target columns
        final_cols = USER_MASTER_COLS.copy()
        
        # Add internal duplicate flag for AgGrid highlighting
        if 'Is Duplicate' in df.columns:
            df['_is_duplicate_user'] = df['Is Duplicate'].fillna(False).astype(bool)
            final_cols.append('_is_duplicate_user')
            
        df_final = df[final_cols].copy()
        
        # After mapping and stripping unmapped columns, drop any resulting exact clones
        check_cols = [c for c in df_final.columns if c != '_is_duplicate_user']
        df_final = df_final.drop_duplicates(subset=check_cols, keep='first')
        
        # Since we just dropped exact clones, none of the remaining rows have exact clones in this dataframe!
        if '_is_duplicate_user' in df_final.columns:
            df_final['_is_duplicate_user'] = False
            
        return df_final
        
    return {
        'Existing Users': format_to_template(existing_users),
        'New Users': format_to_template(new_users)
    }

def generate_segregation_workbook(dfs: dict) -> bytes:
    """
    Generates a multi-sheet Excel workbook from the dictionary of formatted dataframes.
    """
    buf = io.BytesIO()
    
    existing_users = dfs.get('Existing Users', pd.DataFrame()).copy()
    new_users = dfs.get('New Users', pd.DataFrame()).copy()
        
    def get_dup_indices(df):
        if '_is_duplicate_user' in df.columns:
            return [i + 1 for i, val in enumerate(df['_is_duplicate_user']) if str(val).strip().lower() in ('true', '1', 't')]
        return []
        
    existing_dup_idx = get_dup_indices(existing_users)
    new_dup_idx = get_dup_indices(new_users)
    
    # Drop internal columns before exporting to Excel
    for df in [existing_users, new_users]:
        if '_is_duplicate_user' in df.columns:
            df.drop(columns=['_is_duplicate_user'], inplace=True)
        if '_is_duplicate_username' in df.columns:
            df.drop(columns=['_is_duplicate_username'], inplace=True)
        if '#' in df.columns:
            df.drop(columns=['#'], inplace=True)
        
    # Write to Excel
    with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
        # Formatting
        workbook = writer.book
        duplicate_format = workbook.add_format({'bg_color': '#FFC7CE', 'font_color': '#9C0006'})
        header_format = workbook.add_format() # Plain format with no bold or borders
        
        # Prepare datasets with fallback messages
        sheets_data = [
            ('Existing Users', existing_users if not existing_users.empty else pd.DataFrame([{'Message': 'No existing users found'}]), existing_dup_idx),
            ('New Users', new_users if not new_users.empty else pd.DataFrame([{'Message': 'No new users found'}]), new_dup_idx)
        ]
        
        for sheet_name, df_sheet, dup_indices in sheets_data:
            if df_sheet.empty or 'Message' in df_sheet.columns:
                # If it's a message sheet, write normally
                df_sheet.to_excel(writer, sheet_name=sheet_name, index=False)
                continue
                
            # Write data without headers starting from row 1 (second row)
            df_sheet.to_excel(writer, sheet_name=sheet_name, index=False, header=False, startrow=1)
            worksheet = writer.sheets[sheet_name]
            
            # Write plain headers manually
            for col_num, value in enumerate(df_sheet.columns.values):
                worksheet.write(0, col_num, value, header_format)
                
            # Set all column widths to a fixed value (12 units)
            worksheet.set_column(0, len(df_sheet.columns) - 1, 12)
            
            # Apply formatting directly to duplicate rows without needing a helper column
            if dup_indices:
                for row_idx in dup_indices:
                    worksheet.conditional_format(row_idx, 0, row_idx, len(df_sheet.columns) - 1,
                                                 {'type': 'no_blanks', 'format': duplicate_format})
                    worksheet.conditional_format(row_idx, 0, row_idx, len(df_sheet.columns) - 1,
                                                 {'type': 'blanks', 'format': duplicate_format})
                                                     
    return buf.getvalue()
