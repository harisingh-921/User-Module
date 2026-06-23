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
    build_unique_headers, detect_tick_role_columns
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
        is_sub_header = False
        headers_temp = [str(h).strip() for h in raw_df.iloc[header_row_idx].values]
        headers_lower_temp = {str(h).strip(): str(h).lower().strip() for h in raw_df.iloc[header_row_idx].values if 'suggested' not in str(h).lower()}
        
        # Build temp col_mapping to check if next row has actual data in name/email columns
        col_mapping_temp = {}
        headers_temp = [str(h).strip() for h in raw_df.iloc[header_row_idx].values]
        headers_lower_temp = {str(h).strip(): str(h).lower().strip() for h in raw_df.iloc[header_row_idx].values}
        for target_field in USER_MASTER_COLS:
            if target_field == 'roles': continue
            tf_lower = target_field.lower()
            for src_col, src_lower in headers_lower_temp.items():
                if src_col in col_mapping_temp: continue
                src_clean = re.sub(r'\(.*?\)', '', src_lower).strip()
                if src_clean == tf_lower or src_clean.replace(' ', '') == tf_lower.lower():
                    col_mapping_temp[src_col] = target_field
                    break
            else:
                if target_field in SEMANTIC_MAPPINGS:
                    for alias in SEMANTIC_MAPPINGS[target_field]:
                        for src_col, src_lower in headers_lower_temp.items():
                            if src_col in col_mapping_temp: continue
                            child_part = src_lower.split('|')[-1] if '|' in src_lower else src_lower
                            child_clean = re.sub(r'\(.*?\)', '', child_part).strip()
                            if alias == src_lower or src_lower.replace(' ', '') == alias.replace(' ', '') or alias == child_clean:
                                col_mapping_temp[src_col] = target_field
                                break
                        if any(v == target_field for v in col_mapping_temp.values()):
                            break
                            
                if not any(v == target_field for v in col_mapping_temp.values()):
                    broad_keywords = {
                        'departments': ['department', 'dept'],
                        'units': ['unit', 'ward', 'division'],
                        'designation': ['designation', 'position', 'title', 'rank', 'category'],
                        'userName': ['user name', 'username'],
                        'employeeId': ['employee id', 'emp id', 'staff id', 'emp no', 'employee no', 'id no'],
                        'email': ['email', 'e-mail', 'mail'],
                        'phone': ['mobile', 'phone', 'contact', 'cell', 'telephone'],
                        'thirdPartyUsername': ['third party', 'ad username', 'ad user', 'thirdparty'],
                    }
                    if target_field in broad_keywords:
                        for kw in broad_keywords[target_field]:
                            for src_col, src_lower in headers_lower_temp.items():
                                if src_col in col_mapping_temp: continue
                                child_part = src_lower.split('|')[-1] if '|' in src_lower else src_lower
                                child_clean = re.sub(r'\(.*?\)', '', child_part).strip()
                                
                                # Prevent matching third party / AD columns to userName
                                if target_field == 'userName' and any(tp in child_clean for tp in ['third party', 'ad username', 'ad user', 'thirdparty']):
                                    continue
                                    
                                if kw in child_clean:
                                    col_mapping_temp[src_col] = target_field
                                    break
                            if any(v == target_field for v in col_mapping_temp.values()):
                                break
                                
                if target_field == 'firstName' and 'firstName' not in col_mapping_temp.values():
                    for src_col, src_lower in headers_lower_temp.items():
                        if src_col in col_mapping_temp: continue
                        if src_lower in ('name', 'full name', 'fullname', 'staff name', 'employee name'):
                            col_mapping_temp[src_col] = '_fullName'
                            break

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
        col_mapping = {}  # source_col -> target_field
        headers_lower = {h: h.lower().strip() for h in headers if 'suggested' not in h.lower()}
        
        # Pass 1: Direct and Semantic Alias Matches (highest priority)
        for target_field in USER_MASTER_COLS:
            if target_field == 'roles':
                continue
            if any(v == target_field for v in col_mapping.values()):
                continue
                
            # Smart email preference: if both Personal and Official exist, prioritize Official
            if target_field == 'email':
                official_email_cols = [h for h in headers if h not in col_mapping and ('official' in h.lower() or 'work' in h.lower() or 'corp' in h.lower())]
                general_email_cols = [h for h in headers if h not in col_mapping and ('email' in h.lower() or 'mail' in h.lower())]
                best_email_col = None
                for o_col in official_email_cols:
                    if o_col in general_email_cols:
                        best_email_col = o_col
                        break
                if best_email_col:
                    col_mapping[best_email_col] = 'email'
                    continue

            tf_lower = target_field.lower()
            # Direct match
            found = False
            for src_col, src_lower in headers_lower.items():
                if src_col in col_mapping:
                    continue
                src_clean = re.sub(r'\(.*?\)', '', src_lower).strip()
                if src_clean == tf_lower or src_clean.replace(' ', '') == tf_lower.lower():
                    col_mapping[src_col] = target_field
                    found = True
                    break
            
            if not found:
                # Semantic/fuzzy match using SEMANTIC_MAPPINGS
                if target_field in SEMANTIC_MAPPINGS:
                    for alias in SEMANTIC_MAPPINGS[target_field]:
                        for src_col, src_lower in headers_lower.items():
                            if src_col in col_mapping:
                                continue
                            child_part = src_lower.split('|')[-1] if '|' in src_lower else src_lower
                            child_clean = re.sub(r'\(.*?\)', '', child_part).strip()
                            if alias == src_lower or src_lower.replace(' ', '') == alias.replace(' ', '') or alias == child_clean:
                                col_mapping[src_col] = target_field
                                found = True
                                break
                        if found:
                            break

        # Pass 2: Broad Keyword and Full Name Splits (fallback priority)
        for target_field in USER_MASTER_COLS:
            if target_field == 'roles':
                continue
            if any(v == target_field for v in col_mapping.values()):
                continue
                
            # Broad keyword match for common fields
            broad_keywords = {
                'departments': ['department', 'dept'],
                'units': ['unit', 'ward', 'division'],
                'designation': ['designation', 'position', 'title', 'rank', 'category'],
                'userName': ['user name', 'username'],
                'employeeId': ['employee id', 'emp id', 'staff id', 'emp no', 'employee no', 'id no'],
                'email': ['email', 'e-mail', 'mail'],
                'phone': ['mobile', 'phone', 'contact', 'cell', 'telephone'],
                'thirdPartyUsername': ['third party', 'ad username', 'ad user', 'thirdparty'],
            }
            if target_field in broad_keywords:
                found = False
                for kw in broad_keywords[target_field]:
                    for src_col, src_lower in headers_lower.items():
                        if src_col in col_mapping:
                            continue
                        child_part = src_lower.split('|')[-1] if '|' in src_lower else src_lower
                        child_clean = re.sub(r'\(.*?\)', '', child_part).strip()
                        
                        # Prevent matching third party / AD columns to userName
                        if target_field == 'userName' and any(tp in child_clean for tp in ['third party', 'ad username', 'ad user', 'thirdparty']):
                            continue
                            
                        if kw in child_clean:
                            col_mapping[src_col] = target_field
                            found = True
                            break
                    if found:
                        break
                        
            # Handle "Full Name" / "Name" -> firstName + lastName split
            if target_field == 'firstName' and 'firstName' not in col_mapping.values():
                for src_col, src_lower in headers_lower.items():
                    if src_col in col_mapping:
                        continue
                    src_clean = re.sub(r'\(.*?\)', '', src_lower).strip()
                    if src_clean in ('name', 'full name', 'fullname', 'staff name', 'employee name'):
                        col_mapping[src_col] = '_fullName'
                        break
        
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
            'infection', 'statistics', 'survey', 'feedback', 'complaint'
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
                val = str(row.get(src_col, '')).strip()
                if is_empty_value(val):
                    val = ''
                
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
                    rv = str(row.iloc[rc_col] if rc_col < len(row) else '').strip()
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
 
            # --- SPLIT MULTI-USER ROWS (PIPE SEPARATED DELIMITER) ---
            split_trigger_fields = ['firstName', 'lastName', 'employeeId']
            has_split_trigger = any('|' in user.get(f, '') for f in split_trigger_fields)
            
            if has_split_trigger:
                identity_fields = ['firstName', 'middleName', 'lastName', 'userName', 'employeeId', 'email', 'phone']
                max_parts = 1
                for f in identity_fields:
                    val = user.get(f, '')
                    if '|' in val:
                        parts = [p.strip() for p in val.split('|')]
                        max_parts = max(max_parts, len(parts))
                
                if max_parts > 1:
                    for i in range(max_parts):
                        sub_user = user.copy()
                        for f in USER_MASTER_COLS:
                            if f in identity_fields:
                                val = user.get(f, '')
                                parts = [p.strip() for p in val.split('|')] if '|' in val else [val]
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
                        val = user.get(f, '')
                        if '|' in val:
                            user[f] = val.split('|')[0].strip()
                    has_name = (user.get('firstName', '').strip() or 
                               user.get('lastName', '').strip() or 
                               user.get('employeeId', '').strip() or
                               user.get('userName', '').strip())
                    if has_name:
                        all_users.append(user)
            else:
                user = resolve_multi_value_fields(user)
                has_name = (user.get('firstName', '').strip() or 
                           user.get('lastName', '').strip() or 
                           user.get('employeeId', '').strip() or
                           user.get('userName', '').strip())
                if has_name:
                    all_users.append(user)
    
    if not all_users:
        return pd.DataFrame()
    
    raw_df = pd.DataFrame(all_users)
    result_df = _merge_duplicate_users(raw_df, pass_prefix=pass_prefix)
    return enforce_contract(result_df)
