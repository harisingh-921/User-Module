# user_masters/extraction/local.py
import io
import pandas as pd
import streamlit as st
from config.constants import USER_MASTER_COLS, SEMANTIC_MAPPINGS
from extraction.merge import _merge_duplicate_users
from models.dataframe_contract import enforce_contract
from utils.common import is_empty_value, has_value

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
    if user_intent and isinstance(user_intent, str):
        intent_lower = user_intent.lower()
        filtered_sheets = {}
        for s_name, s_df in all_sheets.items():
            s_clean = s_name.lower().replace(' ', '')
            should_ignore = False
            
            import re
            ignore_matches = re.findall(r'(?:ignore|skip)\s*sheet\s*([0-9]+)', intent_lower)
            for num in ignore_matches:
                if f"sheet{num}" == s_clean or num == s_clean.replace('sheet', ''):
                    should_ignore = True
                    break
                    
            if should_ignore:
                continue
                
            only_matches = re.findall(r'only\s*sheet\s*([0-9]+)', intent_lower)
            if only_matches:
                matches_any_only = False
                for num in only_matches:
                    if f"sheet{num}" == s_clean or num == s_clean.replace('sheet', ''):
                        matches_any_only = True
                        break
                if not matches_any_only:
                    continue
                    
            filtered_sheets[s_name] = s_df
        all_sheets = filtered_sheets
    
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
        headers_lower_temp = {str(h).strip(): str(h).lower().strip() for h in raw_df.iloc[header_row_idx].values}
        
        # Build temp col_mapping to check if next row has actual data in name/email columns
        col_mapping_temp = {}
        for target_field in USER_MASTER_COLS:
            if target_field == 'roles': continue
            tf_lower = target_field.lower()
            for src_col, src_lower in headers_lower_temp.items():
                if src_col in col_mapping_temp: continue
                if src_lower == tf_lower or src_lower.replace(' ', '') == tf_lower.lower():
                    col_mapping_temp[src_col] = target_field
                    break
            else:
                if target_field in SEMANTIC_MAPPINGS:
                    for alias in SEMANTIC_MAPPINGS[target_field]:
                        for src_col, src_lower in headers_lower_temp.items():
                            if src_col in col_mapping_temp: continue
                            if alias == src_lower or src_lower.replace(' ', '') == alias.replace(' ', ''):
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
                    }
                    if target_field in broad_keywords:
                        for kw in broad_keywords[target_field]:
                            for src_col, src_lower in headers_lower_temp.items():
                                if src_col in col_mapping_temp: continue
                                if kw in src_lower:
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
 
        if header_row_idx + 1 < len(raw_df):
            next_row = raw_df.iloc[header_row_idx + 1]
            name_email_empty = True
            for src_col, target_field in col_mapping_temp.items():
                if target_field in ['firstName', 'lastName', '_fullName', 'employeeId', 'email']:
                    col_index = raw_df.iloc[header_row_idx].tolist().index(src_col)
                    val = str(next_row.iloc[col_index]).strip().lower() if col_index < len(next_row) else ""
                    if has_value(val):
                        name_email_empty = False
                        break
            text_cells = sum(1 for v in next_row.values if has_value(v))
            if name_email_empty and text_cells >= 2:
                is_sub_header = True
 
        if is_sub_header:
            headers = []
            parent_headers = raw_df.iloc[header_row_idx].tolist()
            # Forward-fill parent headers to handle merged cells!
            filled_parents = []
            last_parent = ""
            for p in parent_headers:
                p_str = str(p).strip()
                if has_value(p_str):
                    last_parent = p_str
                filled_parents.append(last_parent)
 
            for c_idx in range(len(raw_df.columns)):
                parent_h = filled_parents[c_idx]
                child_h = str(raw_df.iloc[header_row_idx + 1].iloc[c_idx]).strip()
                
                parent_clean = "" if is_empty_value(parent_h) else parent_h
                child_clean = "" if is_empty_value(child_h) else child_h
                
                if parent_clean and child_clean:
                    if parent_clean.lower() == child_clean.lower():
                        headers.append(child_clean)
                    else:
                        headers.append(f"{parent_clean}|{child_clean}")
                elif child_clean:
                    headers.append(child_clean)
                elif parent_clean:
                    headers.append(parent_clean)
                else:
                    headers.append(f"col_{c_idx}")
            data_df = raw_df.iloc[header_row_idx + 2:].copy().reset_index(drop=True)
        else:
            headers = [str(h).strip() for h in raw_df.iloc[header_row_idx].values]
            data_df = raw_df.iloc[header_row_idx + 1:].copy().reset_index(drop=True)
 
        # Ensure unique headers by adding suffixes to duplicates to prevent pandas Series mapping issues
        unique_headers = []
        header_counts = {}
        for h in headers:
            if h in header_counts:
                header_counts[h] += 1
                unique_headers.append(f"{h}_{header_counts[h]}")
            else:
                header_counts[h] = 0
                unique_headers.append(h)
        headers = unique_headers
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
        headers_lower = {h: h.lower().strip() for h in headers}
        
        # Pass 1: Direct and Semantic Alias Matches (highest priority)
        for target_field in USER_MASTER_COLS:
            if target_field == 'roles':
                continue
            if any(v == target_field for v in col_mapping.values()):
                continue
                
            # Smart email preference: if both Personal and Official exist, prioritize Official
            if target_field == 'email':
                official_email_cols = [h for h in headers if 'official' in h.lower() or 'work' in h.lower() or 'corp' in h.lower()]
                general_email_cols = [h for h in headers if 'email' in h.lower() or 'mail' in h.lower()]
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
                if src_lower == tf_lower or src_lower.replace(' ', '') == tf_lower.lower():
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
                            if alias == src_lower or src_lower.replace(' ', '') == alias.replace(' ', '') or alias == child_part:
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
            }
            if target_field in broad_keywords:
                found = False
                for kw in broad_keywords[target_field]:
                    for src_col, src_lower in headers_lower.items():
                        if src_col in col_mapping:
                            continue
                        if kw in src_lower:
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
                    if src_lower in ('name', 'full name', 'fullname', 'staff name', 'employee name'):
                        col_mapping[src_col] = '_fullName'
                        break
        
        # Check for running/floating roles column in headers (must not be a tick-marked column)
        TICK_VALUES = {'yes', 'y', 'x', '1', 'true', 'v', '\u221a', '\u2713', '\u2714', '\u2611'}  # includes √ ✓ ✔ ☑
        roles_col_name = None
        for h in headers:
            if h in col_mapping:
                continue
            if 'module|' in h.lower():  # Specific role columns in module sections are never running roles columns
                continue
            if any(kw in h.lower() for kw in ['role', 'audit user', 'assigned role', 'user role', 'incharge', 'admin', 'running role']):
                col_vals = data_df[h].dropna().astype(str).str.strip()
                has_ticks = col_vals.apply(lambda v: v.lower() in TICK_VALUES or v in TICK_VALUES).any()
                if not has_ticks:
                    roles_col_name = h
                    break
 
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
            is_role_header = any(kw in src_lower for kw in role_keywords)
            if is_role_header and src_col not in col_mapping and src_col != roles_col_name:
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
        for _, row in data_df.iterrows():
            user = {col: '' for col in USER_MASTER_COLS}
            
            # Global Unit Name fallback
            if global_unit:
                user['units'] = global_unit
                
            # Running role mapping
            if roles_col_name:
                rv = str(row.get(roles_col_name, '')).strip()
                if has_value(rv):
                    last_role_val = rv
            
            if last_role_val:
                user['roles'] = last_role_val
            
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
                    rv = str(row.get(rc_col, '')).strip()
                    # Check if the row has a valid tick in this role column
                    is_ticked = False
                    if 'module|' in rc_col.lower():
                        NEGATIVE_VALUES = {'', 'nan', 'none', '-', 'no', 'false', '0'}
                        is_ticked = rv.lower() not in NEGATIVE_VALUES
                    else:
                        is_ticked = rv.lower() in TICK_VALUES or rv in TICK_VALUES
                    
                    if is_ticked:
                        clean_rc_name = rc_name.split('|')[-1] if '|' in rc_name else rc_name
                        # Strip trailing duplicate index suffix (e.g. "Incident Reporter_1" -> "Incident Reporter")
                        import re
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
            import re
            for f in ['userName', 'firstName']:
                val = user.get(f, '')
                if val and '-' in val:
                    match = re.search(r'^(.*?)\s*-\s*([a-zA-Z]+[0-9]+[a-zA-Z0-9\-]*)$', val)
                    if match:
                        user[f] = match.group(1).strip()
                        if not user.get('employeeId'):
                            user['employeeId'] = match.group(2).strip()

            # --- SPLIT MULTI-USER ROWS (PIPE SEPARATED DELIMITER) ---
            split_trigger_fields = ['firstName', 'lastName', 'userName', 'employeeId']
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
                    has_name = (user.get('firstName', '').strip() or 
                               user.get('lastName', '').strip() or 
                               user.get('employeeId', '').strip() or
                               user.get('userName', '').strip())
                    if has_name:
                        all_users.append(user)
            else:
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
