import pandas as pd
import io
import datetime

def generate_segregation_workbook(client_df: pd.DataFrame, duplicates_df: pd.DataFrame, file_names: dict) -> bytes:
    """
    Generates a multi-sheet Excel workbook from the segregation results.
    """
    buf = io.BytesIO()
    
    # Extract data subsets
    existing_users = client_df[client_df['User Type'] == 'Existing User'].copy() if not client_df.empty else pd.DataFrame()
    new_users = client_df[client_df['User Type'] == 'New User'].copy() if not client_df.empty else pd.DataFrame()
    
    # Validation errors (Mock for now, could be expanded based on mandatory fields)
    validation_errors = []
    if not new_users.empty:
        for idx, row in new_users.iterrows():
            missing = []
            for col in ['userName', 'email', 'roles']: # Example mandatory fields
                if col in row and pd.isna(row[col]) or str(row.get(col, '')).strip() == '':
                    missing.append(col)
            if missing:
                validation_errors.append({
                    'Row #': row.get('#', idx + 1),
                    'User Identifier': row.get('userName', row.get('email', '')),
                    'Error': f"Missing mandatory fields: {', '.join(missing)}"
                })
    df_errors = pd.DataFrame(validation_errors) if validation_errors else pd.DataFrame(columns=['Row #', 'User Identifier', 'Error'])
    
    # Audit Log
    audit_data = []
    if not client_df.empty:
        for idx, row in client_df.iterrows():
            audit_data.append({
                'Record Number': row.get('#', idx + 1),
                'User Identifier': row.get('userName', row.get('email', row.get('employeeId', ''))),
                'Action Taken': 'Processed',
                'Match Type': row.get('Match Status', ''),
                'Matched By': row.get('Matched By', ''),
                'Timestamp': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'Processing Status': 'Success'
            })
    df_audit = pd.DataFrame(audit_data) if audit_data else pd.DataFrame(columns=['Record Number', 'User Identifier', 'Action Taken', 'Match Type', 'Matched By', 'Timestamp', 'Processing Status'])
    
    # Summary Sheet Data
    total_uploaded = len(client_df) + len(duplicates_df)
    counts = client_df['Matched By'].value_counts() if not client_df.empty and 'Matched By' in client_df.columns else {}
    
    summary_data = [
        {'Metric': 'Processing Date & Time', 'Value': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
        {'Metric': 'Client File', 'Value': file_names.get('client', 'Unknown')},
        {'Metric': 'Medblaze Master File', 'Value': file_names.get('master', 'Unknown')},
        {'Metric': 'Total Records Uploaded', 'Value': total_uploaded},
        {'Metric': 'Existing Users Count', 'Value': len(existing_users)},
        {'Metric': 'New Users Count', 'Value': len(new_users)},
        {'Metric': 'Duplicate Records Count', 'Value': len(duplicates_df)},
        {'Metric': 'Validation Error Count', 'Value': len(df_errors)},
    ]
    
    for k, v in counts.items():
        if k: # Ignore empty matched_by (for New Users)
            summary_data.append({'Metric': f'Matched By {k} Count', 'Value': v})
            
    df_summary = pd.DataFrame(summary_data)
    
    # Clean up master_ columns from Existing/New users for display
    # But for Existing users, we want to highlight changes. We will add Change Summary columns.
    
    if not existing_users.empty:
        change_cols = []
        for col in existing_users.columns:
            if not col.startswith('master_') and col not in ['User Type', 'Match Status', 'Matched By', 'Matched Medblaze Record', 'Remarks', '#']:
                master_col = f"master_{col}"
                if master_col in existing_users.columns:
                    # Compare and add Current/New columns
                    # We will create "Current {col}" and "New {col}" only if differences exist in the dataset
                    diff_mask = existing_users[col].astype(str).str.strip() != existing_users[master_col].astype(str).str.strip()
                    if diff_mask.any():
                        existing_users[f"Current {col}"] = existing_users[master_col]
                        existing_users[f"New {col}"] = existing_users[col]
                        change_cols.extend([f"Current {col}", f"New {col}"])
                        
        # Drop all master_ cols
        master_drop = [c for c in existing_users.columns if c.startswith('master_')]
        existing_users.drop(columns=master_drop, inplace=True)
        
    if not new_users.empty:
        master_drop = [c for c in new_users.columns if str(c).startswith('master_')]
        new_users.drop(columns=master_drop, inplace=True, errors='ignore')
        
    # Write to Excel
    with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
        df_summary.to_excel(writer, sheet_name='Summary', index=False)
        existing_users.to_excel(writer, sheet_name='Existing Users', index=False)
        new_users.to_excel(writer, sheet_name='New Users', index=False)
        if not duplicates_df.empty:
            duplicates_df.to_excel(writer, sheet_name='Duplicate Records', index=False)
        else:
            pd.DataFrame([{'Message': 'No duplicates found'}]).to_excel(writer, sheet_name='Duplicate Records', index=False)
            
        if not df_errors.empty:
            df_errors.to_excel(writer, sheet_name='Validation Errors', index=False)
        else:
            pd.DataFrame([{'Message': 'No validation errors'}]).to_excel(writer, sheet_name='Validation Errors', index=False)
            
        df_audit.to_excel(writer, sheet_name='Audit Log', index=False)
        
        # Formatting (Autofit columns)
        workbook = writer.book
        for sheet_name in writer.sheets:
            worksheet = writer.sheets[sheet_name]
            worksheet.autofit()
            
            # Optional: Add conditional formatting to highlight "New " columns in Existing Users
            if sheet_name == 'Existing Users':
                highlight_format = workbook.add_format({'bg_color': '#FFEB9C', 'font_color': '#9C0006'})
                for col_num, col_name in enumerate(existing_users.columns):
                    if str(col_name).startswith('New '):
                        worksheet.conditional_format(1, col_num, len(existing_users), col_num,
                                                     {'type': 'no_blanks', 'format': highlight_format})
                                                     
    return buf.getvalue()
