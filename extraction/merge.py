# user_masters/extraction/merge.py
import re
import pandas as pd

def _merge_duplicate_users(df: pd.DataFrame, pass_prefix: str = "Med") -> pd.DataFrame:
    """
    After AI extraction, merge rows for the same user into one.
    Identifies duplicates by employeeId (preferred) or userName.
    Combines roles from all duplicate rows using '|' separator.
    """
    if df.empty:
        return df

    df = df.copy()

    # ── Drop phantom rows created from role section headers ──────────────────
    # A real user MUST have a name (firstName/lastName) or an employeeId.
    # If userName looks like a role string (e.g. "Audit User - MOS - ...") 
    # and has no employeeId, it's a misextracted header — remove it.
    ROLE_HEADER_KEYWORDS = ['audit user', 'incharge', 'audit incharge', 'med admin', 'ot manager', 
                             'nursing incharge', 'quality', 'infection control', 'micu', 'sicu', 'ccu',
                             'dialysis', 'radiology', 'emergency', 'lab', 'icn', 'icu', 'ot']
    def _is_phantom_row(row):
        emp = str(row.get('employeeId', '')).strip().lower()
        has_emp_id = emp and emp not in ('nan', 'none', '-', '')
        
        first = str(row.get('firstName', '')).strip().lower()
        last = str(row.get('lastName', '')).strip().lower()
        uname = str(row.get('userName', '')).strip().lower()
        
        has_first = first and first not in ('nan', 'none', '-', '')
        has_last = last and last not in ('nan', 'none', '-', '')
        has_uname = uname and uname not in ('nan', 'none', '-', '')
        
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
        if eid and eid not in ('nan', 'none', '-', ''):
            return f"id_{eid}"
        
        email = str(row.get('email', '')).strip().lower()
        if email and email not in ('nan', 'none', '-', ''):
            return f"email_{email}"
            
        mobile = str(row.get('mobile', '')).strip().lower()
        if mobile and mobile not in ('nan', 'none', '-', ''):
            return f"mobile_{mobile}"
            
        uname = str(row.get('userName', '')).strip().lower()
        if uname and uname not in ('nan', 'none', '-', ''):
            return f"user_{uname}"
            
        first = str(row.get('firstName', '')).strip().lower()
        last = str(row.get('lastName', '')).strip().lower()
        if first and first not in ('nan', 'none', '-', '') and last and last not in ('nan', 'none', '-', ''):
            f_clean = re.sub(r'[^a-z]', '', first)
            l_clean = re.sub(r'[^a-z]', '', last)
            if f_clean or l_clean:
                return f"name_{f_clean}_{l_clean}"
            
        return f"unkeyed_{row.name}"

    df['_group_key'] = df.apply(get_master_key, axis=1)

    def merge_group(group):
        # Prefer the "cleanest" row: sort by firstName length ascending so a short,
        # correctly-split name (e.g. "Arindam") wins over a merged one (e.g. "Arindam Riya").
        # This does NOT affect single-occurrence users at all — sorting a 1-row group is a no-op.
        if len(group) > 1 and 'firstName' in group.columns:
            group = group.copy()
            group['_fn_len'] = group['firstName'].astype(str).str.replace('|', '', regex=False).str.strip().str.len()
            group = group.sort_values('_fn_len').drop(columns=['_fn_len'])
        merged = group.iloc[0].copy()
        # Merge all role strings across duplicates
        if 'roles' in group.columns:
            all_roles = []
            for r in group['roles'].dropna():
                for part in str(r).split('|'):
                    part = part.strip()
                    if part and part.lower() not in ('nan', '-', ''):
                        if part not in all_roles:
                            all_roles.append(part)
            merged['roles'] = '|'.join(all_roles)
        # Fill blank fields from other rows in the group
        for col in group.columns:
            if col in ('roles', '_group_key'):
                continue
            if str(merged.get(col, '')).strip().lower() in ('', 'nan', 'none', '-'):
                for val in group[col].dropna():
                    if str(val).strip().lower() not in ('', 'nan', 'none', '-'):
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
    
    # Programmatic userName construction: join first+middle+last and keep ONLY letters
    def construct_username(row):
        parts = []
        fn = str(row.get('firstName', '')).strip()
        mn = str(row.get('middleName', '')).strip()
        ln = str(row.get('lastName', '')).strip()

        # Safety 1: Stop at pipes (Primary split logic)
        if '|' in fn: fn = fn.split('|')[0].strip()
        if '|' in mn: mn = mn.split('|')[0].strip()
        if '|' in ln: ln = ln.split('|')[0].strip()

        # Safety 2: Anti-Merge (If AI returned "Priyodarshini Manisha" without a pipe)
        # We take only the first word for the first name to prevent merging users.
        if ' ' in fn:
            fn = fn.split(' ')[0].strip()

        for val in [fn, mn, ln]:
            if val and val.lower() not in ('nan', 'none', '-'):
                parts.append(val)
        
        full = "".join(parts)
        # Keep only letters, lowercase
        clean = re.sub(r'[^a-zA-Z]', '', full).lower()
        return clean if clean else row.get('userName', 'user')

    # Programmatic password generation
    def construct_password(row):
        emp_id = str(row.get('employeeId', '')).strip()
        if not emp_id or emp_id.lower() in ('nan', 'none', '-'):
            return "" # Keep password blank if employeeId is missing
        return f"{pass_prefix}@{emp_id}"

    merged_df['userName'] = merged_df.apply(construct_username, axis=1)
    merged_df['password'] = merged_df.apply(construct_password, axis=1)

    # ── DOUBLE MERGE PASS ────────────────────────────────────────────────────
    # Now that usernames are clean (no more 'priyodarshinimanisha'), 
    # we run the merger AGAIN. This ensures that a previously 'merged' name 
    # and a 'clean' name are now recognized as the same person.
    final_rows = []
    merged_df['_final_group_key'] = merged_df['userName']
    for _, group in merged_df.groupby('_final_group_key', sort=False):
        if len(group) == 1:
            final_rows.append(group.iloc[0])
        else:
            # Re-run the role merge logic
            m = group.iloc[0].copy()
            all_roles = []
            for r in group['roles'].dropna():
                for part in str(r).split('|'):
                    part = part.strip()
                    if part and part.lower() not in ('nan', '-', '') and part not in all_roles:
                        all_roles.append(part)
            m['roles'] = '|'.join(all_roles)
            final_rows.append(m)
    
    merged_df = pd.DataFrame(final_rows).reset_index(drop=True)
    merged_df = merged_df.drop(columns=['_final_group_key'], errors='ignore')
    # ─────────────────────────────────────────────────────────────────────────
        
    return merged_df
