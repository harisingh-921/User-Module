import re
import difflib
import pandas as pd
from utils.common import is_empty_value, has_value

def normalize_email(val: str) -> str:
    if not val:
        return ""
    clean = str(val).strip().lower()
    return "" if is_empty_value(clean) else clean

def normalize_mobile(val: str) -> str:
    if not val:
        return ""
    # Extract digits only
    digits = re.sub(r'\D', '', str(val))
    # Match standard 10-digit number from the end
    clean = digits[-10:] if len(digits) >= 10 else digits
    return "" if is_empty_value(clean) else clean


def _merge_duplicate_users(df: pd.DataFrame, pass_prefix: str = "Med") -> pd.DataFrame:
    """
    After AI extraction, merge rows for the same user into one.
    Identifies duplicates by employeeId (preferred) or userName.
    Combines roles from all duplicate rows using '|' separator.
    """
    if df.empty:
        return df

    df = df.copy()
    if '_original_order' not in df.columns:
        df['_original_order'] = range(len(df))

    # ── Drop phantom rows created from role section headers ──────────────────
    # A real user MUST have a name (firstName/lastName) or an employeeId.
    # If userName looks like a role string (e.g. "Audit User - MOS - ...") 
    # and has no employeeId, it's a misextracted header — remove it.
    ROLE_HEADER_KEYWORDS = ['audit user', 'incharge', 'audit incharge', 'med admin', 'ot manager', 
                             'nursing incharge', 'quality', 'infection control', 'micu', 'sicu', 'ccu',
                             'dialysis', 'radiology', 'emergency', 'lab', 'icn', 'icu', 'ot']
    def _is_phantom_row(row):
        has_emp_id = has_value(row.get('employeeId', ''))
        
        first = str(row.get('firstName', '')).strip().lower()
        last = str(row.get('lastName', '')).strip().lower()
        uname = str(row.get('userName', '')).strip().lower()
        
        has_first = has_value(row.get('firstName', ''))
        has_last = has_value(row.get('lastName', ''))
        has_uname = has_value(row.get('userName', ''))
        
        # If absolutely no name fields and no employee ID, it's empty
        if not (has_first or has_last or has_uname) and not has_emp_id:
            return True
            
        if has_emp_id:
            return False  # Has an employee ID → definitely a real user
            
        # Check if name fields look like role strings
        for kw in ROLE_HEADER_KEYWORDS:
            if kw in uname and ' - ' in uname:  # Role section tags have " - " separators
                return True
            if kw in first and not last:  # firstName = role keyword, no lastName
                return True
        return False

    df = df[~df.apply(_is_phantom_row, axis=1)].reset_index(drop=True)

    # ── Resolve duplicate employee ID conflicts with different names ─────────
    # If the same employeeId is shared by two rows with completely different names,
    # we strip it from the one that looks like a generic role/system title.
    if 'employeeId' in df.columns:
        emp_groups = {}
        for idx, row in df.iterrows():
            eid = str(row.get('employeeId', '')).strip().lower()
            if has_value(eid) and eid not in ('nan', 'none', '-', 'na', 'n/a'):
                if eid not in emp_groups:
                    emp_groups[eid] = []
                emp_groups[eid].append(idx)
                
        for eid, indices in emp_groups.items():
            if len(indices) > 1:
                names_and_indices = []
                for idx in indices:
                    row = df.loc[idx]
                    first = str(row.get('firstName', '')).strip()
                    last = str(row.get('lastName', '')).strip()
                    full_name = f"{first} {last}".strip()
                    names_and_indices.append((idx, full_name))
                
                # Check if we have different names
                has_diff = False
                for i in range(len(names_and_indices)):
                    for j in range(i + 1, len(names_and_indices)):
                        n1 = names_and_indices[i][1].lower()
                        n2 = names_and_indices[j][1].lower()
                        if n1 and n2:
                            ratio = difflib.SequenceMatcher(None, n1, n2).ratio()
                            if ratio < 0.7 and n1 not in n2 and n2 not in n1:
                                has_diff = True
                                break
                    if has_diff:
                        break
                        
                if has_diff:
                    role_kws = ['quality', 'manager', 'admin', 'supervisor', 'reporter', 'analyst', 'user', 'incharge', 'officer', 'coordinator']
                    def get_role_score(name):
                        nl = name.lower()
                        return sum(1 for kw in role_kws if kw in nl)
                        
                    # Find the winning name (lowest role score)
                    winning_idx, winning_name = min(names_and_indices, key=lambda x: get_role_score(x[1]))
                    winning_name_lower = winning_name.lower().strip()
                    
                    # Strip employeeId from any row whose name is not similar to the winning name
                    for idx, full_name in names_and_indices:
                        fn_lower = full_name.lower().strip()
                        if fn_lower != winning_name_lower:
                            ratio = difflib.SequenceMatcher(None, fn_lower, winning_name_lower).ratio()
                            if ratio < 0.7 and fn_lower not in winning_name_lower and winning_name_lower not in fn_lower:
                                df.at[idx, 'employeeId'] = ''

    # Determine the key to group by
    def get_master_key(row):
        eid = str(row.get('employeeId', '')).strip().lower()
        if has_value(row.get('employeeId', '')):
            return f"id_{eid}"
        
        email = normalize_email(row.get('email', ''))
        if email:
            return f"email_{email}"
            
        mobile = normalize_mobile(row.get('phone', ''))
        if mobile:
            return f"mobile_{mobile}"
            
        uname = str(row.get('userName', '')).strip().lower()
        if has_value(row.get('userName', '')):
            return f"user_{uname}"
            
        first = str(row.get('firstName', '')).strip().lower()
        last = str(row.get('lastName', '')).strip().lower()
        if has_value(row.get('firstName', '')) and has_value(row.get('lastName', '')):
            f_clean = re.sub(r'[^a-z]', '', first)
            l_clean = re.sub(r'[^a-z]', '', last)
            if f_clean or l_clean:
                return f"name_{f_clean}_{l_clean}"
            
        return f"unkeyed_{row.name}"

    df['_group_key'] = df.apply(get_master_key, axis=1)

    def merge_group(group):
        # Prefer the row with an Employee ID first, then prioritize real names over role keywords, and then keep the longer first name.
        if len(group) > 1:
            group = group.copy()
            # 0 for rows with a valid ID (floats to top), 1 for blank IDs
            group['_has_emp'] = group['employeeId'].apply(
                lambda x: 0 if has_value(x) else 1
            )
            
            # Penalize role titles/placeholder names
            role_kws = ['quality', 'manager', 'admin', 'supervisor', 'reporter', 'analyst', 'user', 'incharge', 'officer', 'coordinator']
            def get_role_penalty(name):
                name_lower = str(name).lower()
                return 1 if any(kw in name_lower for kw in role_kws) else 0
                
            group['_role_penalty'] = group['firstName'].apply(get_role_penalty)
            group['_fn_len'] = group['firstName'].astype(str).str.replace('|', '', regex=False).str.strip().str.len()
            
            # Sort by _has_emp (ascending), _role_penalty (ascending), and _fn_len (descending for fuller name)
            group = group.sort_values(
                by=['_has_emp', '_role_penalty', '_fn_len'], 
                ascending=[True, True, False]
            ).drop(columns=['_has_emp', '_role_penalty', '_fn_len'])
        merged = group.iloc[0].copy()
        # Keep the earliest original order!
        if '_original_order' in group.columns:
            merged['_original_order'] = group['_original_order'].min()
        # Merge all list-like strings (roles, departments, units, locations) across duplicates
        list_cols = ['roles', 'departments', 'units', 'locations']
        for col in list_cols:
            if col in group.columns:
                all_items = []
                for val in group[col].dropna():
                    for part in str(val).split('|'):
                        part = part.strip()
                        if has_value(part):
                            if part not in all_items:
                                all_items.append(part)
                merged[col] = '|'.join(all_items)
        # Fill blank fields from other rows in the group
        for col in group.columns:
            if col in list_cols or col == '_group_key':
                continue
            if is_empty_value(merged.get(col, '')):
                for val in group[col].dropna():
                    if has_value(val):
                        merged[col] = val
                        break
        return merged

    # Use an explicit loop instead of groupby().apply() — in pandas 2.x,
    # apply() with a function returning a Series can silently drop single-occurrence rows.
    result_rows = []
    for _, group in df.groupby('_group_key', sort=False):
        result_rows.append(merge_group(group))

    merged_df = pd.DataFrame(result_rows).reset_index(drop=True)
    merged_df = merged_df.drop(columns=['_group_key'], errors='ignore')
    
    # Programmatic userName construction: use client username if present, otherwise construct from names
    def construct_username(row):
        uname = str(row.get('userName', '')).strip()
        if has_value(uname) and uname.lower() not in ('nan', 'none', '-', 'na', 'n/a'):
            cleaned = re.sub(r'[^a-zA-Z0-9]', '', uname).lower()
            if cleaned:
                return cleaned

        parts = []
        fn = str(row.get('firstName', '')).strip()
        mn = str(row.get('middleName', '')).strip()
        ln = str(row.get('lastName', '')).strip()

        # Safety 1: Stop at pipes (Primary split logic)
        if '|' in fn: fn = fn.split('|')[0].strip()
        if '|' in mn: mn = mn.split('|')[0].strip()
        if '|' in ln: ln = ln.split('|')[0].strip()

        # Safety 2: Anti-Merge (Strip titles if present, but do not truncate multi-word first names)
        if ' ' in fn:
            words = fn.split()
            if words and words[0].lower().rstrip('.') in ('dr', 'mr', 'mrs', 'ms', 'sr', 'prof', 'sister', 'fr'):
                if len(words) >= 2:
                    fn = words[0] + " " + words[1]

        for val in [fn, mn, ln]:
            if has_value(val):
                parts.append(val)
        
        full = "".join(parts)
        # Keep only letters and numbers, lowercase
        clean = re.sub(r'[^a-zA-Z0-9]', '', full).lower()
        return clean if clean else 'user'

    # Programmatic password generation
    def construct_password(row):
        pwd = str(row.get('password', '')).strip()
        if has_value(pwd) and pwd.lower() not in ('nan', 'none', '-', 'na', 'n/a'):
            return pwd

        if not pass_prefix or not str(pass_prefix).strip():
            return ""
        emp_id = str(row.get('employeeId', '')).strip()
        if is_empty_value(emp_id) or emp_id.lower() in ('nan', 'none', '-', 'na', 'n/a'):
            return "" # Keep password blank if employeeId is missing
        return f"{pass_prefix}@{emp_id}"

    merged_df['userName'] = merged_df.apply(construct_username, axis=1)
    merged_df['password'] = merged_df.apply(construct_password, axis=1)

    # ── DOUBLE MERGE PASS ────────────────────────────────────────────────────
    # Now that usernames are clean (no more 'priyodarshinimanisha'), 
    # we run the merger AGAIN. This ensures that a previously 'merged' name 
    # ── DOUBLE MERGE PASS ────────────────────────────────────────────────────
    # Now that usernames are clean (no more 'priyodarshinimanisha'), 
    # we run the merger AGAIN. This ensures that a previously 'merged' name 
    # and a 'clean' name are now recognized as the same person.
    final_rows = []
    
    # Pre-clean suffix employee IDs (e.g. "ayesha-GB11318") in userName
    def clean_uname(u):
        if not u: return u
        u_str = str(u).strip()
        match = re.search(r'^(.*?)\s*-\s*([a-zA-Z]+[0-9]+[a-zA-Z0-9\-]*)$', u_str)
        if match:
            return match.group(1).strip().lower()
        return u_str.lower()
        
    merged_df['userName'] = merged_df['userName'].apply(clean_uname)
    
    for _, group in merged_df.groupby('userName', sort=False):
        if len(group) == 1:
            final_rows.append(group.iloc[0])
        else:
            # Safety check: do not merge rows that have different non-empty employee IDs
            # or different non-empty names.
            emp_ids = group['employeeId'].dropna().astype(str).str.strip().str.lower()
            emp_ids = emp_ids[emp_ids.ne('') & emp_ids.ne('nan') & emp_ids.ne('none')]
            
            names = group['firstName'].dropna().astype(str).str.strip().str.lower()
            names = names[names.ne('') & names.ne('nan') & names.ne('none')]
            
            if len(emp_ids.unique()) > 1 or (len(names.unique()) > 1 and len(emp_ids.unique()) > 0):
                for _, row in group.iterrows():
                    final_rows.append(row)
            else:
                final_rows.append(merge_group(group))
    
    merged_df = pd.DataFrame(final_rows).reset_index(drop=True)
    
    # ── FUZZY NAME SIMILARITY DEDUPLICATION PASS ─────────────────────────────
    # Compare remaining rows fuzzy-wise. If two rows have similar names (ratio > 0.88)
    # and belong to the same department or unit, they are highly likely the same user.
    fuzzy_merged_rows = []
    skipped_indices = set()
    
    for i in range(len(merged_df)):
        if i in skipped_indices:
            continue
        row_i = merged_df.iloc[i].copy()
        
        first_i = str(row_i.get('firstName', '')).strip().lower()
        last_i = str(row_i.get('lastName', '')).strip().lower()
        dept_i = str(row_i.get('departments', '')).strip().lower()
        unit_i = str(row_i.get('units', '')).strip().lower()
        
        name_i = f"{first_i} {last_i}".strip()
        if not name_i:
            fuzzy_merged_rows.append(row_i)
            continue
            
        for j in range(i + 1, len(merged_df)):
            if j in skipped_indices:
                continue
            row_j = merged_df.iloc[j]
            
            first_j = str(row_j.get('firstName', '')).strip().lower()
            last_j = str(row_j.get('lastName', '')).strip().lower()
            dept_j = str(row_j.get('departments', '')).strip().lower()
            unit_j = str(row_j.get('units', '')).strip().lower()
            
            name_j = f"{first_j} {last_j}".strip()
            if not name_j:
                continue
                
            # Compute string similarity ratio
            sim = difflib.SequenceMatcher(None, name_i, name_j).ratio()

            # Same department/unit AND similarity > 0.88 implies same person (e.g. typos like "Aysha" vs "Ayesha")
            same_dept = dept_i and dept_j and dept_i == dept_j
            same_unit = unit_i and unit_j and unit_i == unit_j
            
            # --- SAFETY GUARDS ---
            # If they have DIFFERENT non-empty employee IDs, emails, or mobile numbers, they are DIFFERENT people!
            emp_i = str(row_i.get('employeeId', '')).strip().lower()
            emp_j = str(row_j.get('employeeId', '')).strip().lower()
            has_emp = has_value(emp_i) and has_value(emp_j)
            diff_emp = has_emp and emp_i != emp_j
            
            email_i = normalize_email(row_i.get('email', ''))
            email_j = normalize_email(row_j.get('email', ''))
            has_email = email_i and email_j
            diff_email = has_email and email_i != email_j
            
            mob_i = normalize_mobile(row_i.get('phone', ''))
            mob_j = normalize_mobile(row_j.get('phone', ''))
            has_mob = mob_i and mob_j
            diff_mob = has_mob and mob_i != mob_j
            
            if diff_emp or diff_email or diff_mob:
                continue  # Safety guard: definitely different people! Do NOT merge.
            
            if sim > 0.88 and (same_dept or same_unit or (not dept_i and not dept_j)):
                # Merge row_j into row_i
                skipped_indices.add(j)
                # Combine roles
                roles_i = str(row_i.get('roles', '')).split('|')
                roles_j = str(row_j.get('roles', '')).split('|')
                all_roles = []
                for r in (roles_i + roles_j):
                    r_clean = r.strip()
                    if has_value(r_clean) and r_clean not in all_roles:
                        all_roles.append(r_clean)
                row_i['roles'] = '|'.join(all_roles)
                
                # Backfill blank fields in row_i from row_j
                for col in merged_df.columns:
                    if col == 'roles': continue
                    val_i = str(row_i.get(col, '')).strip().lower()
                    val_j = str(row_j.get(col, '')).strip().lower()
                    if is_empty_value(val_i) and has_value(val_j):
                        row_i[col] = row_j[col]
        
        fuzzy_merged_rows.append(row_i)
    
    merged_df = pd.DataFrame(fuzzy_merged_rows).reset_index(drop=True)
    # ─────────────────────────────────────────────────────────────────────────
    
    # Default isEnabled to 'Yes' for all users if blank or missing
    if 'isEnabled' not in merged_df.columns:
        merged_df['isEnabled'] = 'Yes'
    else:
        def clean_enabled(x):
            if pd.isna(x):
                return 'Yes'
            s = str(x).strip().lower()
            if s in ('', 'nan', 'none', '-', 'na', 'n/a'):
                return 'Yes'
            if s in ('y', 'yes', 'true', '1', 'active', 'enabled'):
                return 'Yes'
            if s in ('n', 'no', 'false', '0', 'inactive', 'disabled'):
                return 'No'
            return x
        merged_df['isEnabled'] = merged_df['isEnabled'].apply(clean_enabled)

    # Expand "All" departments
    if 'departments' in merged_df.columns:
        # Collect all unique departments (excluding placeholders and 'all')
        unique_depts = []
        for val in merged_df['departments'].dropna():
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
            merged_df['departments'] = merged_df['departments'].apply(expand_all_depts)

    # Preserve 100% of the original Excel sheet row order and drop helper column
    if '_original_order' in merged_df.columns:
        merged_df = merged_df.sort_values('_original_order').reset_index(drop=True)
        merged_df = merged_df.drop(columns=['_original_order'])

    return merged_df

