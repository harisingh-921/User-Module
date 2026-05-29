# user_masters/validation/validator.py
import pandas as pd

def validate_master_data(df: pd.DataFrame):
    """
    Performance-optimized validation service for User Master Data.
    Uses vectorized pandas masks to handle large datasets efficiently.
    
    Returns: (errors_list, warnings_list)
    """
    errors = []
    warnings = []
    
    if df.empty:
        return errors, warnings

    # Regex patterns
    email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    mobile_regex = r'^\+?[0-9\s-]{8,20}$'

    # 1. Vectorized Mandatory Check (userName)
    # Identifies rows where userName is null, empty, or placeholder strings
    unames = df['userName'].astype(str).str.strip().str.lower()
    mask_missing_uname = (unames == '') | (unames == 'nan') | (unames == 'none') | (unames == '-')
    
    if mask_missing_uname.any():
        bad_indices = df[mask_missing_uname]['#'].tolist()
        for b_id in bad_indices:
            errors.append(f"Row {b_id}: Missing mandatory **userName**")

    # 2. Vectorized Email Check (Only for non-empty values)
    if 'email' in df.columns:
        emails = df['email'].astype(str).str.strip()
        # Create mask for rows that ARE NOT empty but DO NOT match regex
        has_email = (emails != '') & (emails != 'nan') & (emails != 'none') & (emails != '-')
        invalid_email = has_email & (~emails.str.match(email_regex, na=False))
        
        if invalid_email.any():
            bad_rows = df[invalid_email][['#', 'email']].values
            for b_id, b_val in bad_rows:
                warnings.append(f"Row {b_id}: Invalid **email** format ('{b_val}')")

    # 3. Vectorized Mobile Check (Only for non-empty values)
    if 'mobile' in df.columns:
        mobiles = df['mobile'].astype(str).str.strip()
        has_mobile = (mobiles != '') & (mobiles != 'nan') & (mobiles != 'none') & (mobiles != '-')
        invalid_mobile = has_mobile & (~mobiles.str.match(mobile_regex, na=False))
        
        if invalid_mobile.any():
            bad_rows = df[invalid_mobile][['#', 'mobile']].values
            for b_id, b_val in bad_rows:
                warnings.append(f"Row {b_id}: Invalid **mobile** format ('{b_val}')")

    return errors, warnings
