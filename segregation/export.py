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
    
    TARGET_COLS = [
        "userName", "password", "departments", "roles", "units", "locations", 
        "email", "phone", "employeeId", "firstName", "middleName", "lastName", 
        "designation", "timezone", "shiftDuration", "thirdPartyUsername", 
        "dateOfJoining", "lastWorkingDate", "reportingTo", "isEnabled", "passwordPolicy"
    ]
    
    def format_to_template(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
            
        # Fallbacks to capture incorrectly named columns from the client file
        fallbacks = {
            'email': ['Mail ID', 'mail', 'Email Address'],
            'phone': ['Personal Phone', 'mobile', 'Mobile Number', 'Phone Number'],
            'employeeId': ['Employee No', 'emp id']
        }
        
        for col in TARGET_COLS:
            if col not in df.columns:
                found = False
                if col in fallbacks:
                    for fb in fallbacks[col]:
                        if fb in df.columns:
                            df[col] = df[fb]
                            found = True
                            break
                if not found:
                    df[col] = ''
                    
        # Keep exactly the target columns
        final_cols = TARGET_COLS.copy()
        
        # Clean userName: lowercase, no spaces, no special characters
        if 'userName' in df.columns:
            import re
            df['userName'] = df['userName'].astype(str).apply(
                lambda x: re.sub(r'[^a-z0-9]', '', x.lower()) if pd.notna(x) and str(x).strip() not in ('', 'nan') else ''
            )
        
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
    
    # Drop the internal grid marker before exporting to Excel
    for df in [existing_users, new_users]:
        if '_is_duplicate_user' in df.columns:
            df.drop(columns=['_is_duplicate_user'], inplace=True)
        
    # Write to Excel
    with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
        if not existing_users.empty:
            existing_users.to_excel(writer, sheet_name='Existing Users', index=False)
        else:
            pd.DataFrame([{'Message': 'No existing users found'}]).to_excel(writer, sheet_name='Existing Users', index=False)
            
        if not new_users.empty:
            new_users.to_excel(writer, sheet_name='New Users', index=False)
        else:
            pd.DataFrame([{'Message': 'No new users found'}]).to_excel(writer, sheet_name='New Users', index=False)
            
        # Formatting
        workbook = writer.book
        duplicate_format = workbook.add_format({'bg_color': '#FFC7CE', 'font_color': '#9C0006'})
        
        for sheet_name, df_sheet, dup_indices in [('Existing Users', existing_users, existing_dup_idx), ('New Users', new_users, new_dup_idx)]:
            if df_sheet.empty or 'Message' in df_sheet.columns:
                continue
                
            worksheet = writer.sheets[sheet_name]
            worksheet.autofit()
            
            # Apply formatting directly to duplicate rows without needing a helper column
            if dup_indices:
                for row_idx in dup_indices:
                    worksheet.conditional_format(row_idx, 0, row_idx, len(df_sheet.columns) - 1,
                                                 {'type': 'no_blanks', 'format': duplicate_format})
                    worksheet.conditional_format(row_idx, 0, row_idx, len(df_sheet.columns) - 1,
                                                 {'type': 'blanks', 'format': duplicate_format})
                                                     
    return buf.getvalue()
