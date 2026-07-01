# user_masters/extraction/local.py
import io
import re
import pandas as pd
import streamlit as st
from config.constants import USER_MASTER_COLS, SEMANTIC_MAPPINGS, TICK_VALUES, ROLE_NEGATIVE_VALUES
from extraction.merge import _merge_duplicate_users
from models.dataframe_contract import enforce_contract
from utils.common import is_empty_value, has_value
from extraction.utils import (
    filter_sheets_by_intent, detect_header_row, check_is_sub_header,
    build_unique_headers, detect_tick_role_columns, build_temp_col_mapping,
    align_extracted_users_by_registry
)

def resolve_multi_value_fields(user):
    """
    Resolves multi-value fields (delimited by '|') for a single user row.
    Looks for a value matching the user's name across email and username fields.
    If a matched index is found, maps that index for all multi-value contact/username fields.
    If no match is found, falls back to the first value (unit/default value).
    """
    fn = str(user.get('firstName', '')).strip().lower()
    ln = str(user.get('lastName', '')).strip().lower()
    fn_clean = re.sub(r'[^a-z0-9]', '', fn)
    ln_clean = re.sub(r'[^a-z0-9]', '', ln)
    
    fields_to_resolve = ['email', 'phone', 'userName', 'thirdPartyUsername']
    
    # Check if we can find a matching index where a value contains the user's name
    matched_idx = None
    for f in ['email', 'thirdPartyUsername', 'userName']:
        val = user.get(f, '')
        if val and '|' in val:
            parts = [p.strip() for p in val.split('|') if p.strip()]
            for idx, p in enumerate(parts):
                p_lower = p.lower()
                prefix = p_lower.split('@')[0] if '@' in p_lower else p_lower
                prefix_clean = re.sub(r'[^a-z0-9]', '', prefix)
                if (fn_clean and fn_clean in prefix_clean) or (ln_clean and ln_clean in prefix_clean):
                    matched_idx = idx
                    break
            if matched_idx is not None:
                break
                
    for f in fields_to_resolve:
        val = user.get(f, '')
        if val and '|' in val:
            parts = [p.strip() for p in val.split('|') if p.strip()]
            if not parts:
                user[f] = ''
                continue
            if matched_idx is not None and matched_idx < len(parts):
                user[f] = parts[matched_idx]
            else:
                user[f] = parts[0]
                
    return user


def split_multi_value_field(val: str) -> list[str]:
    """
    Splits a multi-value string by pipe or newline characters,
    and cleans up any numbered/bullet prefixes (e.g., "1. Vidhya" -> "Vidhya")
    and trailing commas/semicolons.
    """
    if not val:
        return []
    
    val_str = str(val).replace('\r\n', '\n').replace('\r', '\n')
    if not val_str.strip():
        return []
        
    if '|' in val_str:
        parts = [p.strip() for p in val_str.split('|')]
    elif '\n' in val_str:
        parts = [p.strip() for p in val_str.split('\n')]
    else:
        parts = [val_str.strip()]
        
    cleaned_parts = []
    for p in parts:
        cleaned = re.sub(r'^\d+\.\s*', '', p).strip()
        cleaned = cleaned.rstrip(',').rstrip(';').strip()
        cleaned_parts.append(cleaned)
    return cleaned_parts


def local_extract_users(file_bytes, filename, pass_prefix="Med", user_intent=""):
    """
    LOCAL extraction engine — NO AI, NO API calls.
    Reads Excel/CSV, auto-detects headers, maps columns to our schema using
    fuzzy matching against SEMANTIC_MAPPINGS, and returns a clean DataFrame.
    Works even when all API keys are exhausted.
    """
    ext = filename.lower()
    try:
        if ext.endswith('.csv'):
            all_sheets = {'Sheet1': pd.read_csv(io.BytesIO(file_bytes), header=None)}
        elif ext.endswith(('.xlsx', '.xls')):
            all_sheets = pd.read_excel(io.BytesIO(file_bytes), header=None, sheet_name=None)
        else:
            st.warning(f"Local extraction only supports Excel/CSV. '{filename}' skipped.")
            return pd.DataFrame()
    except Exception as e:
        st.error(f"Error reading {filename}: {e}")
        return pd.DataFrame()
        
    # Simple sheet filtering based on user_intent
    all_sheets = filter_sheets_by_intent(all_sheets, user_intent)
    
    all_users = []
    
    for sheet_name, raw_df in all_sheets.items():
        raw_df = raw_df.dropna(how='all')
        mask = raw_df.astype(str).apply(lambda x: x.str.contains(r'[a-zA-Z0-9]', na=False)).any(axis=1)
        raw_df = raw_df[mask].reset_index(drop=True)
        if raw_df.empty:
            continue
            
        # Try to find a global unit name in the sheet
        global_unit = ""
        for r_idx, row in raw_df.iterrows():
            row_vals = [str(x).strip() for x in row.values]
            for c_idx, val in enumerate(row_vals):
                if val.lower() == 'unit name' and c_idx + 1 < len(row_vals):
                    candidate = row_vals[c_idx + 1]
                    if has_value(candidate):
                        global_unit = candidate
                        break
            if global_unit:
                break
        
        # --- Improved Auto-detect header row ---
        str_df = raw_df.astype(str).map(lambda x: str(x).strip())
        header_row_idx = 0
        max_matches = 0
        for idx, row in str_df.iterrows():
            vals = row.str.lower().tolist()
            # If row contains common header keywords, it's likely the header
            header_keywords = ['name', 'email', 'employee', 'id', 'mobile', 'phone', 
                             'department', 'unit', 'role', 'designation', 'staff',
                             'first', 'last', 'username', 'password']
            matches = sum(1 for v in vals if any(kw in str(v).lower() for kw in header_keywords))
            if matches > max_matches:
                max_matches = matches
                header_row_idx = idx
            if matches >= 5:
                break
        
        # --- Check if the row immediately following the header row is a sub-header row ---
        headers_raw = [str(h).strip() for h in raw_df.iloc[header_row_idx].values]
        col_mapping_temp = build_temp_col_mapping(headers_raw)
        is_sub_header = check_is_sub_header(raw_df, header_row_idx, col_mapping_temp)
        headers = build_unique_headers(raw_df, header_row_idx, is_sub_header)
        first_data_row = header_row_idx + 2 if is_sub_header else header_row_idx + 1
        data_df = raw_df.iloc[first_data_row:].copy().reset_index(drop=True)
        data_df.columns = headers
        
        # Remove rows that are all empty/nan
        data_df = data_df.dropna(how='all').reset_index(drop=True)
        data_str = data_df.astype(str).map(lambda x: str(x).strip())
        has_content = data_str.apply(lambda row: row.str.lower().replace('nan', '').replace('none', '').replace('-', '').str.strip().ne('').any(), axis=1)
        data_df = data_df[has_content].reset_index(drop=True)
        
        if data_df.empty:
            continue
        
        # --- Map columns to our schema ---
        col_mapping = build_temp_col_mapping(headers)
        
        # Check for running/floating roles columns in headers (must not be a tick-marked column)
        roles_col_names = []
        for h in headers:
            if h in col_mapping:
                continue
            if 'suggested' in h.lower():  # Ignore suggested column!
                continue
            if 'module|' in h.lower():  # Specific role columns in module sections are never running roles columns
                continue
            clean_h = h.split('|')[-1].strip().lower() if '|' in h else h.lower()
            if any(kw in clean_h for kw in ['role', 'audit', 'validation', 'incharge', 'admin', 'running role', 'suggested role']):
                col_vals = data_df[h].dropna().astype(str).str.strip()
                has_ticks = col_vals.apply(lambda v: v.lower() in TICK_VALUES or v in TICK_VALUES).any()
                if not has_ticks:
                    roles_col_names.append(h)
 
        # --- Detect tick-marked role columns ---
        role_cols = {}
        role_keywords = [
            'audit', 'non-conformance', 'incident', 'qi', 'risk', 'proms', 'accreditation',
            'role', 'user', 'incharge', 'admin', 'viewer', 'reporter', 'analyst', 'champion',
            'officer', 'owner', 'auditor', 'manager', 'coordinator', 'module', 'hic',
            'infection', 'statistics', 'survey', 'feedback', 'complaint',
            
            # New Module / Process Keywords
            'pre', 'pro', 'pra', 'compliance', 'document', 'dms', 'ticketing', 'employee',
            'cpc', 'credential', 'oppe', 'fppe', 'committee', 'competency', 'lms', 'asset', 'unit',
            
            # New Title / Role Keywords
            'translator', 'approver', 'chairperson', 'secretary', 'convenor', 'member',
            'trainee', 'trainer', 'privileges', 'masking', 'pill', 'access', 'chat'
        ]
        for src_col in headers:
            src_lower = str(src_col).lower()
            if 'suggested' in src_lower:  # Ignore suggested column!
                continue
            is_role_header = any(kw in src_lower for kw in role_keywords)
            if is_role_header and src_col not in col_mapping and src_col not in roles_col_names:
                col_vals = data_df[src_col].dropna().astype(str).str.strip()
                # If it's a module column, any non-empty, non-negative value is considered a valid role assignment tick!
                if 'module|' in src_lower:
                     NEGATIVE_VALUES = {'', 'nan', 'none', '-', 'no', 'false', '0'}
                     has_ticks = col_vals.apply(lambda v: v.lower() not in NEGATIVE_VALUES).any()
                else:
                     has_ticks = col_vals.apply(lambda v: v.lower() in TICK_VALUES or v in TICK_VALUES).any()
                
                if has_ticks:
                    role_cols[src_col] = src_col
        
        # --- Build user records ---
        last_role_val = ""
        last_roles = {}   # tracks the most-recent non-empty value per running-role column
        for _, row in data_df.iterrows():
            user = {col: '' for col in USER_MASTER_COLS}
            
            # Global Unit Name fallback
            if global_unit:
                user['units'] = global_unit
                
            # Running role mapping (gather from all running role columns)
            row_roles = []
            
            # Sheet-level role mapping if sheet name contains role keywords
            sheet_role_keywords = ['role', 'audit', 'validation', 'incharge', 'admin', 'viewer', 'reporter', 'analyst', 'champion', 'officer', 'owner', 'auditor', 'manager', 'coordinator', 'user', 'incident', 'qi', 'risk']
            clean_sheet = sheet_name.strip()
            if any(kw in clean_sheet.lower() for kw in sheet_role_keywords):
                row_roles.append(clean_sheet)

            for r_col in roles_col_names:
                rv = str(row.get(r_col, '')).strip()
                if has_value(rv):
                    last_roles[r_col] = rv
                if r_col in last_roles and last_roles[r_col]:
                    for part in last_roles[r_col].split('|'):
                        part = part.strip()
                        if has_value(part) and part not in row_roles:
                            row_roles.append(part)
            
            if row_roles:
                user['roles'] = '|'.join(row_roles)
            
            for src_col, target_field in col_mapping.items():
                raw_val = str(row.get(src_col, ''))
                val_check = raw_val.strip()
                if is_empty_value(val_check):
                    val = ''
                else:
                    val = raw_val
                
                if target_field == '_fullName':
                    # Split "Full Name" into firstName + lastName
                    parts = val.split()
                    if len(parts) >= 2:
                        user['firstName'] = parts[0]
                        user['lastName'] = ' '.join(parts[1:])
                    elif len(parts) == 1:
                        user['firstName'] = parts[0]
                else:
                    user[target_field] = val
            
            # Collect tick-marked roles
            if role_cols:
                assigned_roles = []
                for rc_col, rc_name in role_cols.items():
                    rv = str(row.get(rc_col, '')).strip()
                    # Check if the row has a valid tick in this role column
                    is_ticked = False
                    if 'module|' in rc_name.lower():
                        is_ticked = rv.lower() not in ROLE_NEGATIVE_VALUES
                    else:
                        is_ticked = rv.lower() in TICK_VALUES or rv in TICK_VALUES
                    
                    if is_ticked:
                        clean_rc_name = rc_name.split('|')[-1] if '|' in rc_name else rc_name
                        # Strip trailing duplicate index suffix (e.g. "Incident Reporter_1" -> "Incident Reporter")
                        clean_rc_name = re.sub(r'_\d+$', '', clean_rc_name)
                        assigned_roles.append(clean_rc_name)
                if assigned_roles:
                    if user['roles']:
                        existing = user['roles'].split('|')
                        for r in assigned_roles:
                            if r not in existing:
                                existing.append(r)
                        user['roles'] = '|'.join(existing)
                    else:
                        user['roles'] = '|'.join(assigned_roles)
            
            # Clean up suffix like "- GB11318" from userName/firstName
            for f in ['userName', 'firstName']:
                val = user.get(f, '')
                if val and '-' in val:
                    match = re.search(r'^(.*?)\s*-\s*([a-zA-Z]+[0-9]+[a-zA-Z0-9\-]*)$', val)
                    if match:
                        user[f] = match.group(1).strip()
                        if not user.get('employeeId'):
                            user['employeeId'] = match.group(2).strip()
 
            # --- SPLIT MULTI-USER ROWS (PIPE OR NEWLINE SEPARATED DELIMITER) ---
            split_trigger_fields = ['firstName', 'lastName', 'employeeId']
            has_split_trigger = any(
                '|' in str(user.get(f, '')) or '\n' in str(user.get(f, '')).replace('\r\n', '\n')
                for f in split_trigger_fields
            )
            
            if has_split_trigger:
                identity_fields = ['firstName', 'middleName', 'lastName', 'userName', 'employeeId', 'email', 'phone']
                
                # Split each identity field and find max parts
                split_fields = {}
                max_parts = 1
                for f in identity_fields:
                    val = str(user.get(f, ''))
                    parts = split_multi_value_field(val)
                    split_fields[f] = parts
                    max_parts = max(max_parts, len(parts))
                
                if max_parts > 1:
                    for i in range(max_parts):
                        sub_user = user.copy()
                        sub_user['_is_split_user'] = True
                        for f in USER_MASTER_COLS:
                            if f in identity_fields:
                                parts = split_fields[f]
                                if i < len(parts):
                                    sub_user[f] = parts[i]
                                else:
                                    sub_user[f] = ''
                        
                        has_name = (sub_user.get('firstName', '').strip() or 
                                   sub_user.get('lastName', '').strip() or 
                                   sub_user.get('employeeId', '').strip() or
                                   sub_user.get('userName', '').strip())
                        if has_name:
                            all_users.append(sub_user)
                else:
                    for f in ['email', 'phone']:
                        parts = split_fields.get(f, [])
                        if parts:
                            user[f] = parts[0]
                    user['_is_split_user'] = False
                    has_name = (user.get('firstName', '').strip() or 
                               user.get('lastName', '').strip() or 
                               user.get('employeeId', '').strip() or
                               user.get('userName', '').strip())
                    if has_name:
                        all_users.append(user)
            else:
                user = resolve_multi_value_fields(user)
                user['_is_split_user'] = False
                has_name = (user.get('firstName', '').strip() or 
                           user.get('lastName', '').strip() or 
                           user.get('employeeId', '').strip() or
                           user.get('userName', '').strip())
                if has_name:
                    all_users.append(user)
    
    if not all_users:
        return pd.DataFrame()
        
    # --- SMART ALIGNMENT POST-PROCESSING STEP ---
    all_users = align_extracted_users_by_registry(all_users)

    raw_df = pd.DataFrame(all_users)
    result_df = _merge_duplicate_users(raw_df, pass_prefix=pass_prefix)
    return enforce_contract(result_df)
