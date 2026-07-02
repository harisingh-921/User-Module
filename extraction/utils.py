# user_masters/extraction/utils.py
import os
import logging
import re
import pandas as pd
import streamlit as st
from utils.common import has_value, is_empty_value

log = logging.getLogger(__name__)

def find_matching_excel_roles(user_dict, excel_rows_data):
    emp_id = str(user_dict.get('employeeId', '')).strip().lower()
    email = str(user_dict.get('email', '')).strip().lower()
    uname = str(user_dict.get('userName', '')).strip().lower()
    
    # Priority 1: Match by Employee ID
    if has_value(emp_id):
        for row_info in excel_rows_data:
            if emp_id in row_info['raw_values']:
                return row_info['roles']
                
    # Priority 2: Match by Email
    if has_value(email):
        for row_info in excel_rows_data:
            if email in row_info['raw_values']:
                return row_info['roles']
                
    # Priority 3: Match by Username
    if has_value(uname):
        for row_info in excel_rows_data:
            if uname in row_info['raw_values'] or any(uname in str(val) for val in row_info['raw_values']):
                return row_info['roles']
                
    # Fallback: return whatever roles the LLM extracted
    return user_dict.get('roles', '')

def get_all_api_keys(primary_key=None):
    keys = []
    if primary_key:
        p_str = str(primary_key).strip()
        if p_str and p_str not in keys:
            keys.append(p_str)
            
    # Load from st.secrets
    try:
        # Check standard names
        for k in ["OPENAI_API_KEY", "OPENAI_API_KEY_2", "OPENAI_API_KEY_3", "GEMINI_API_KEY", "GEMINI_API_KEY_2", "GEMINI_API_KEY_3"]:
            val = str(st.secrets.get(k, "")).strip()
            if val and val not in keys:
                keys.append(val)
                
        # Also grab any key matching dynamic pattern
        for k in st.secrets.keys():
            val = str(st.secrets.get(k, "")).strip()
            if (val.startswith("sk-") or val.startswith("AIzaSy")) and val not in keys:
                keys.append(val)
    except Exception:
        pass

    # Load from OS environment variables
    try:
        import os
        for k in ["OPENAI_API_KEY", "OPENAI_API_KEY_2", "OPENAI_API_KEY_3", "GEMINI_API_KEY", "GEMINI_API_KEY_2", "GEMINI_API_KEY_3"]:
            val = str(os.environ.get(k, "")).strip()
            if val and val not in keys:
                keys.append(val)
    except Exception:
        pass
        
    # Manual fallback: load from secrets.toml relative to this file's folder
    if not keys or len(keys) <= (1 if primary_key else 0):
        try:
            import toml
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            secrets_path = os.path.join(base_dir, ".streamlit", "secrets.toml")
            if os.path.exists(secrets_path):
                secrets_data = toml.load(secrets_path)
                for k in ["OPENAI_API_KEY", "OPENAI_API_KEY_2", "OPENAI_API_KEY_3", "GEMINI_API_KEY", "GEMINI_API_KEY_2", "GEMINI_API_KEY_3"]:
                    val = str(secrets_data.get(k, "")).strip()
                    if val and val not in keys:
                        keys.append(val)
        except Exception:
            pass
            
    return keys


def filter_sheets_by_intent(all_sheets: dict[str, pd.DataFrame], user_intent: str) -> dict[str, pd.DataFrame]:
    """Filter raw Excel sheets based on skip/ignore/only user intents."""
    if not user_intent or not isinstance(user_intent, str):
        return all_sheets
        
    intent_lower = user_intent.lower()
    filtered_sheets = {}
    for s_name, s_df in all_sheets.items():
        s_clean = s_name.lower().replace(' ', '')
        should_ignore = False
        
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
    return filtered_sheets


def detect_header_row(raw_df: pd.DataFrame) -> int:
    """Detect the index of the header row in a raw DataFrame based on keyword density."""
    str_df = raw_df.astype(str).map(lambda x: str(x).strip())
    header_row_idx = 0
    max_matches = 0
    for idx, row in str_df.iterrows():
        vals = row.str.lower().tolist()
        header_keywords = ['name', 'email', 'employee', 'id', 'mobile', 'phone', 
                         'department', 'unit', 'role', 'designation', 'staff',
                         'first', 'last', 'username', 'password']
        matches = sum(1 for v in vals if any(kw in str(v).lower() for kw in header_keywords))
        if matches > max_matches:
            max_matches = matches
            header_row_idx = idx
        if matches >= 5:
            break
    return header_row_idx


def check_is_sub_header(raw_df: pd.DataFrame, header_row_idx: int, col_mapping_temp: dict[str, str]) -> bool:
    """Determine if the row following the header row is a sub-header row."""
    if header_row_idx + 1 >= len(raw_df):
        return False
        
    next_row = raw_df.iloc[header_row_idx + 1]
    name_email_empty = True
    header_list = raw_df.iloc[header_row_idx].tolist()
    
    for src_col, target_field in col_mapping_temp.items():
        if target_field in ['firstName', 'lastName', '_fullName', 'employeeId', 'email']:
            if src_col in header_list:
                col_index = header_list.index(src_col)
                val = str(next_row.iloc[col_index]).strip().lower() if col_index < len(next_row) else ""
                if has_value(val):
                    name_email_empty = False
                    break
                    
    text_cells = sum(1 for v in next_row.values if has_value(v))
    return name_email_empty and text_cells >= 2


def build_unique_headers(raw_df: pd.DataFrame, header_row_idx: int, is_sub_header: bool) -> list[str]:
    """Join parent and subheader names, then de-duplicate header names to build clean, unique column keys."""
    if is_sub_header:
        headers = []
        parent_headers = raw_df.iloc[header_row_idx].tolist()
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
    else:
        headers = [str(h).strip() for h in raw_df.iloc[header_row_idx].values]

    # Deduplicate headers by appending numerical suffixes
    unique_headers = []
    header_counts = {}
    for h in headers:
        if h in header_counts:
            header_counts[h] += 1
            unique_headers.append(f"{h}_{header_counts[h]}")
        else:
            header_counts[h] = 0
            unique_headers.append(h)
    return unique_headers


def detect_tick_role_columns(headers: list[str], data_rows_df: pd.DataFrame) -> dict[int, str]:
    """Identify columns that serve as checkboxes / tick-mark targets for user roles."""
    from config.constants import TICK_VALUES, ROLE_NEGATIVE_VALUES
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
    for col_idx, header in enumerate(headers):
        header_lower = header.lower()
        is_role_header = any(kw in header_lower for kw in role_keywords)
        col_values = data_rows_df.iloc[:, col_idx].dropna().astype(str).str.strip().str.lower()
        
        if 'module|' in header_lower:
            has_ticks = col_values.apply(lambda v: v.lower() not in ROLE_NEGATIVE_VALUES).any()
        else:
            has_ticks = col_values.isin(TICK_VALUES).any()
            
        if is_role_header and has_ticks:
            role_cols[col_idx] = header
    return role_cols


def build_temp_col_mapping(headers: list[str]) -> dict[str, str]:
    """
    Builds a temporary column mapping (source_col -> target_field) for headers.
    Used for sub-header checks and pre-mapping identification.
    """
    import re
    from config.constants import USER_MASTER_COLS, SEMANTIC_MAPPINGS

    col_mapping_temp = {}
    headers_lower_temp = {str(h).strip(): str(h).lower().strip() for h in headers if 'suggested' not in str(h).lower()}

    for target_field in USER_MASTER_COLS:
        if target_field == 'roles':
            continue
        if target_field == 'email':
            # Smart email preference: if both Personal and Official exist, prioritize Official
            official_email_cols = [h for h in headers if h not in col_mapping_temp and ('official' in str(h).lower() or 'work' in str(h).lower() or 'corp' in str(h).lower())]
            general_email_cols = [h for h in headers if h not in col_mapping_temp and ('email' in str(h).lower() or 'mail' in str(h).lower())]
            best_email_col = None
            for o_col in official_email_cols:
                if o_col in general_email_cols:
                    best_email_col = o_col
                    break
            if best_email_col:
                col_mapping_temp[best_email_col] = 'email'
                continue
        tf_lower = target_field.lower()
        for src_col, src_lower in headers_lower_temp.items():
            if src_col in col_mapping_temp:
                continue
            src_clean = re.sub(r'\(.*?\)', '', src_lower).strip()
            if src_clean == tf_lower or src_clean.replace(' ', '') == tf_lower.lower():
                col_mapping_temp[src_col] = target_field
                break
        else:
            if target_field in SEMANTIC_MAPPINGS:
                for alias in SEMANTIC_MAPPINGS[target_field]:
                    for src_col, src_lower in headers_lower_temp.items():
                        if src_col in col_mapping_temp:
                            continue
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
                            if src_col in col_mapping_temp:
                                continue
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
                if src_col in col_mapping_temp:
                    continue
                src_clean = re.sub(r'\(.*?\)', '', src_lower).strip()
                if src_clean in ('name', 'full name', 'fullname', 'staff name', 'employee name'):
                    col_mapping_temp[src_col] = '_fullName'
                    break

    return col_mapping_temp


def align_extracted_users_by_registry(all_users: list[dict]) -> list[dict]:
    """
    Registry-based smart post-processing alignment.
    Re-aligns shifted or missing fields (like email/employeeId) in multi-user rows.
    """
    if not all_users:
        return all_users

    # 1. Build a registry of clean reference user profiles
    # CRITICAL: Only non-split (single-user) rows are trusted as reference data.
    # Split rows may have shifted/misaligned IDs and must NEVER be registered.
    registry = {}
    for u in all_users:
        # Only trust single-user rows as reference profiles
        if u.get('_is_split_user', False):
            continue
            
        first = str(u.get('firstName', '')).strip()
        last = str(u.get('lastName', '')).strip()
        eid = str(u.get('employeeId', '')).strip()
        email = str(u.get('email', '')).strip()
        phone = str(u.get('phone', '')).strip()
        uname = str(u.get('userName', '')).strip()
        
        if not (first or last):
            continue
            
        name_key = (first.lower(), last.lower())
        
        if eid or email:
            if name_key not in registry:
                registry[name_key] = {}
            if eid:
                registry[name_key]['employeeId'] = eid
            if email:
                registry[name_key]['email'] = email
            if phone:
                registry[name_key]['phone'] = phone
            if uname and uname.lower() not in ('nan', 'none', '-', 'na', 'n/a'):
                registry[name_key]['userName'] = uname

    # 2. Iterate and correct split users using the registry reference
    for u in all_users:
        if not u.get('_is_split_user', False):
            continue
            
        first = str(u.get('firstName', '')).strip()
        last = str(u.get('lastName', '')).strip()
        if not (first or last):
            continue
            
        name_key = (first.lower(), last.lower())
        if name_key in registry:
            reg_profile = registry[name_key]
            
            # Direct alignment correction from verified registry profile
            if 'email' in reg_profile:
                u['email'] = reg_profile['email']
            if 'employeeId' in reg_profile:
                u['employeeId'] = reg_profile['employeeId']
            if 'phone' in reg_profile:
                u['phone'] = reg_profile['phone']
            if 'userName' in reg_profile:
                u['userName'] = reg_profile['userName']
            else:
                # Clear username to force clean regeneration
                u['userName'] = ''
                    
    return all_users


def parse_header_group(header: str) -> tuple[str, int]:
    """
    Parses a deduplicated column header into its base name and group index.
    e.g., 'firstName_1' -> ('firstName', 1), 'firstName' -> ('firstName', 0)
    """
    import re
    match = re.search(r'^(.*?)(?:_(\d+))?$', str(header).strip())
    if match:
        base = match.group(1)
        group_str = match.group(2)
        group_id = int(group_str) if group_str else 0
        return base, group_id
    return str(header).strip(), 0


def parse_custom_mapping_rules(user_intent: str) -> dict[str, str]:
    """
    Parses custom mapping rules from user_intent string, e.g. "Suggested User = designation"
    Returns a dict of {clean_custom_col_name: target_field}
    """
    rules = {}
    if not user_intent or not isinstance(user_intent, str):
        return rules
        
    for line in user_intent.replace(';', '\n').split('\n'):
        if '=' in line:
            lhs, rhs = line.split('=', 1)
            col_name = lhs.strip().lower()
            field_name = rhs.strip()
            
            # Normalize target field
            from config.constants import USER_MASTER_COLS
            matched_field = None
            for f in USER_MASTER_COLS:
                if f.lower() == field_name.lower():
                    matched_field = f
                    break
            if col_name and matched_field:
                rules[col_name] = matched_field
    return rules


def find_custom_rule_match(base: str, custom_rules: dict[str, str]) -> str:
    """
    Checks if the base column name matches any of the custom rule keys using exact, substring, or fuzzy matching.
    Returns the matched target field name, or None.
    """
    import difflib
    base_lower = base.lower().strip()
    
    # Try exact match first
    if base_lower in custom_rules:
        return custom_rules[base_lower]
        
    # Try fuzzy/substring matching
    for k, field in custom_rules.items():
        if k in base_lower or base_lower in k:
            return field
        # Compute string similarity ratio
        ratio = difflib.SequenceMatcher(None, base_lower, k).ratio()
        if ratio > 0.8:
            return field
            
    return None


def build_group_col_mappings(headers: list[str], user_intent: str = "") -> dict[int, dict[str, str]]:
    """
    Identifies all column groups (e.g. Group 0 for unsuffixed, Group 1 for _1)
    and builds an independent column mapping dict {src_col: target_field} for each group.
    """
    import re
    from config.constants import USER_MASTER_COLS, SEMANTIC_MAPPINGS
    
    custom_rules = parse_custom_mapping_rules(user_intent)
    
    # 1. Group headers by their group suffix
    group_headers = {}
    for h in headers:
        base, g_id = parse_header_group(h)
        matched_field = find_custom_rule_match(base, custom_rules)
        
        # If the column has 'suggested' in its name, we only skip it if there is NO custom rule mapping it!
        if 'suggested' in base.lower() and not matched_field:
            continue
            
        if g_id not in group_headers:
            group_headers[g_id] = []
        group_headers[g_id].append(h)
        
    group_mappings = {}
    for g_id, cols in group_headers.items():
        col_mapping_g = {}
        
        # We will match the base names of the columns (lowercase)
        # but map them to the original source column name in cols
        headers_lower_temp = {}
        for h in cols:
            base, _ = parse_header_group(h)
            headers_lower_temp[h] = base.lower().strip()
            
            # Apply custom rules first
            matched_field = find_custom_rule_match(base, custom_rules)
            if matched_field:
                col_mapping_g[h] = matched_field
            
        for target_field in USER_MASTER_COLS:
            if target_field == 'roles':
                continue
            # If target field is already mapped by a custom rule, skip default mapping for it
            if target_field in col_mapping_g.values():
                continue
                
            if target_field == 'email':
                # Prioritize Official Email
                official_email_cols = [h for h in cols if h not in col_mapping_g and ('official' in str(h).lower() or 'work' in str(h).lower() or 'corp' in str(h).lower())]
                general_email_cols = [h for h in cols if h not in col_mapping_g and ('email' in str(h).lower() or 'mail' in str(h).lower())]
                best_email_col = None
                for o_col in official_email_cols:
                    if o_col in general_email_cols:
                        best_email_col = o_col
                        break
                if best_email_col:
                    col_mapping_g[best_email_col] = 'email'
                    continue
                    
            tf_lower = target_field.lower()
            for src_col, base_lower in headers_lower_temp.items():
                if src_col in col_mapping_g:
                    continue
                src_clean = re.sub(r'\(.*?\)', '', base_lower).strip()
                if src_clean == tf_lower or src_clean.replace(' ', '') == tf_lower.lower():
                    col_mapping_g[src_col] = target_field
                    break
            else:
                if target_field in SEMANTIC_MAPPINGS:
                    for alias in SEMANTIC_MAPPINGS[target_field]:
                        for src_col, base_lower in headers_lower_temp.items():
                            if src_col in col_mapping_g:
                                continue
                            child_part = base_lower.split('|')[-1] if '|' in base_lower else base_lower
                            child_clean = re.sub(r'\(.*?\)', '', child_part).strip()
                            if alias == base_lower or base_lower.replace(' ', '') == alias.replace(' ', '') or alias == child_clean:
                                col_mapping_g[src_col] = target_field
                                break
                        if any(v == target_field for v in col_mapping_g.values()):
                            break

                if not any(v == target_field for v in col_mapping_g.values()):
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
                            for src_col, base_lower in headers_lower_temp.items():
                                if src_col in col_mapping_g:
                                    continue
                                child_part = base_lower.split('|')[-1] if '|' in base_lower else base_lower
                                child_clean = re.sub(r'\(.*?\)', '', child_part).strip()

                                if target_field == 'userName' and any(tp in child_clean for tp in ['third party', 'ad username', 'ad user', 'thirdparty']):
                                    continue

                                if kw in child_clean:
                                    col_mapping_g[src_col] = target_field
                                    break
                            if any(v == target_field for v in col_mapping_g.values()):
                                break

            if target_field == 'firstName' and 'firstName' not in col_mapping_g.values():
                for src_col, base_lower in headers_lower_temp.items():
                    if src_col in col_mapping_g:
                        continue
                    src_clean = re.sub(r'\(.*?\)', '', base_lower).strip()
                    if src_clean in ('name', 'full name', 'fullname', 'staff name', 'employee name'):
                        col_mapping_g[src_col] = '_fullName'
                        break
        group_mappings[g_id] = col_mapping_g
        
    return group_mappings


def filter_hidden_elements(file_bytes: bytes, sheet_dfs: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """
    Parses the workbook with openpyxl to identify hidden columns and rows,
    then drops them from the loaded sheet dataframes.
    """
    import io
    import openpyxl
    from openpyxl.utils import column_index_from_string
    
    try:
        # Load workbook in read/write mode (non-read-only) to query dimensions
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
        new_sheet_dfs = {}
        
        for sheet_name, df in sheet_dfs.items():
            if sheet_name not in wb.sheetnames:
                new_sheet_dfs[sheet_name] = df
                continue
                
            ws = wb[sheet_name]
            
            # Find hidden column indices (0-based)
            hidden_col_indices = set()
            for col_key, col_dim in ws.column_dimensions.items():
                if col_dim.hidden:
                    col_str = str(col_key)
                    if ':' in col_str:
                        try:
                            start_letter, end_letter = col_str.split(':')
                            start_idx = column_index_from_string(start_letter)
                            end_idx = column_index_from_string(end_letter)
                            for idx in range(start_idx, end_idx + 1):
                                hidden_col_indices.add(idx - 1)
                        except Exception:
                            pass
                    else:
                        try:
                            idx = column_index_from_string(col_str) - 1
                            hidden_col_indices.add(idx)
                        except Exception:
                            pass
                            
            # Find hidden row indices (0-based matching pandas read without headers)
            hidden_row_indices = set()
            for r_idx, row_dim in ws.row_dimensions.items():
                if row_dim.hidden:
                    hidden_row_indices.add(r_idx - 1)
                    
            filtered_df = df.copy()
            
            # Drop hidden columns
            cols_to_drop = [c for c in filtered_df.columns if c in hidden_col_indices]
            if cols_to_drop:
                filtered_df = filtered_df.drop(columns=cols_to_drop)
                
            # Drop hidden rows
            rows_to_drop = [r for r in filtered_df.index if r in hidden_row_indices]
            if rows_to_drop:
                filtered_df = filtered_df.drop(index=rows_to_drop)
                
            # Reset columns and index to be sequential integers
            filtered_df.columns = range(len(filtered_df.columns))
            filtered_df = filtered_df.reset_index(drop=True)
            
            new_sheet_dfs[sheet_name] = filtered_df
            
        return new_sheet_dfs
    except Exception as e:
        log.warning("Could not filter hidden rows/columns: %s", e)
        return sheet_dfs


def check_intent_is_local_only(user_intent: str) -> bool:
    """
    Checks if the user_intent contains only instructions that can be handled 
    by the Local Mode (column mappings e.g. 'A = B' or sheet filters e.g. 'ignore sheet 1').
    If it contains any free-text clinical filtering or other complex queries, returns False.
    """
    if not user_intent or not str(user_intent).strip():
        return True
        
    import re
    lines = [line.strip() for line in user_intent.replace(';', '\n').split('\n') if line.strip()]
    for line in lines:
        line_lower = line.lower()
        
        # 1. Check if it is a sheet filter: "ignore sheet 1", "skip sheet 2", "only sheet 3"
        is_sheet_filter = (
            re.search(r'^(?:ignore|skip)\s*sheet\s*[0-9]+$', line_lower) or
            re.search(r'^only\s*sheet\s*[0-9]+$', line_lower)
        )
        if is_sheet_filter:
            continue
            
        # 2. Check if it is a column mapping: "LHS = RHS"
        if '=' in line:
            lhs, rhs = line.split('=', 1)
            # Ensure RHS is one of our target field names (casing ignored)
            from config.constants import USER_MASTER_COLS
            field_name = rhs.strip().lower()
            is_valid_field = any(f.lower() == field_name for f in USER_MASTER_COLS)
            if is_valid_field:
                continue
                
        # If any line is neither a sheet filter nor a valid column mapping rule, we need AI
        return False
        
    return True




