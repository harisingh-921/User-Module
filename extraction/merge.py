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
        # Prefer the row with an Employee ID first, then by cleanest (shortest) firstName.
        # This guarantees that the row with the ID acts as the primary name/username source!
        if len(group) > 1:
            group = group.copy()
            # 0 for rows with a valid ID (floats to top), 1 for blank IDs
            group['_has_emp'] = group['employeeId'].apply(
                lambda x: 0 if has_value(x) else 1
            )
            group['_fn_len'] = group['firstName'].astype(str).str.replace('|', '', regex=False).str.strip().str.len()
            group = group.sort_values(by=['_has_emp', '_fn_len']).drop(columns=['_has_emp', '_fn_len'])
        merged = group.iloc[0].copy()
        # Keep the earliest original order!
        if '_original_order' in group.columns:
            merged['_original_order'] = group['_original_order'].min()
        # Merge all role strings across duplicates
        if 'roles' in group.columns:
            all_roles = []
            for r in group['roles'].dropna():
                for part in str(r).split('|'):
                    part = part.strip()
                    if has_value(part):
                        if part not in all_roles:
                            all_roles.append(part)
            merged['roles'] = '|'.join(all_roles)
        # Fill blank fields from other rows in the group
        for col in group.columns:
            if col in ('roles', '_group_key'):
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

        # Safety 2: Anti-Merge (If AI returned "Priyodarshini Manisha" without a pipe)
        if ' ' in fn:
            fn = fn.split(' ')[0].strip()

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
    merged_df['_final_group_key'] = merged_df['userName']
    
    for _, group in merged_df.groupby('_final_group_key', sort=False):
        if len(group) == 1:
            final_rows.append(group.iloc[0])
        else:
            final_rows.append(merge_group(group))
    
    merged_df = pd.DataFrame(final_rows).reset_index(drop=True)
    merged_df = merged_df.drop(columns=['_final_group_key'], errors='ignore')
    
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

    # Preserve 100% of the original Excel sheet row order and drop helper column
    if '_original_order' in merged_df.columns:
        merged_df = merged_df.sort_values('_original_order').reset_index(drop=True)
        merged_df = merged_df.drop(columns=['_original_order'])

    return merged_df

