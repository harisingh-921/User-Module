import pandas as pd
import re
from typing import List, Dict, Any, Tuple

def normalize_value(val: Any, col_name: str) -> str:
    """Normalizes a single value based on the column name."""
    if pd.isna(val):
        return ""
    
    val_str = str(val).strip()
    col_lower = col_name.lower()
    
    if 'email' in col_lower:
        return val_str.lower()
    elif 'mobile' in col_lower or 'phone' in col_lower:
        # Remove spaces and non-numeric characters (keep + for country codes)
        return re.sub(r'[^\d+]', '', val_str)
    elif 'user' in col_lower and 'name' in col_lower:
        return val_str.lower()
    else:
        # For Employee ID and others
        return val_str

def normalize_dataframe(df: pd.DataFrame, columns: List[str]) -> pd.DataFrame:
    """Returns a copy of the dataframe with normalized values for specified columns."""
    df_norm = df.copy()
    for col in columns:
        if col in df_norm.columns:
            df_norm[col] = df_norm[col].apply(lambda x: normalize_value(x, col))
    return df_norm

def detect_duplicates(df: pd.DataFrame, check_cols: List[str]) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Detects duplicates in the client file based on the selected matching columns.
    A row is considered a duplicate if ANY of the non-empty check_cols match another row.
    Returns (cleaned_df, duplicates_df).
    """
    df = df.copy()
    # To properly identify duplicates across ANY column, we iterate.
    # A simple approach: for each col, find rows with duplicated values (excluding empty strings).
    duplicate_indices = set()
    
    for col in check_cols:
        if col not in df.columns:
            continue
            
        # Get non-empty values
        non_empty_mask = df[col].astype(str).str.strip() != ""
        
        # Find duplicates within this column
        # keep=False marks ALL duplicates as True
        col_dups = df[non_empty_mask].duplicated(subset=[col], keep=False)
        dup_idx = df[non_empty_mask][col_dups].index
        
        duplicate_indices.update(dup_idx)
        
    dup_list = list(duplicate_indices)
    duplicates_df = df.loc[dup_list].copy()
    cleaned_df = df.drop(index=dup_list).copy()
    
    return cleaned_df, duplicates_df

def build_master_lookup_dicts(master_df: pd.DataFrame, priority_cols: List[str]) -> Dict[str, Dict[str, dict]]:
    """
    Builds optimized O(1) dictionary lookups for Medblaze master data.
    Returns: { 'col_name': { 'normalized_value': master_row_dict } }
    """
    lookups = {}
    for col in priority_cols:
        lookups[col] = {}
        if col not in master_df.columns:
            continue
            
        for _, row in master_df.iterrows():
            val = normalize_value(row[col], col)
            if val: # Only hash non-empty values
                lookups[col][val] = row.to_dict()
                
    return lookups

def compare_users(client_df: pd.DataFrame, master_df: pd.DataFrame, priority_cols: List[str]) -> pd.DataFrame:
    """
    Compares client users against Medblaze users using priority-based dictionary lookups.
    Returns an enriched client dataframe with segregation results.
    """
    # 1. Normalize master lookup dictionaries
    lookups = build_master_lookup_dicts(master_df, priority_cols)
    
    results = []
    
    for _, client_row in client_df.iterrows():
        match_status = "Not Matched"
        user_type = "New User"
        matched_by = ""
        matched_record = ""
        remarks = "No matching user found"
        master_match = None
        
        # 2. Iterate through priority fields
        for col in priority_cols:
            if col not in client_row:
                continue
                
            val = normalize_value(client_row[col], col)
            if not val:
                continue
                
            if col in lookups and val in lookups[col]:
                # Found a match!
                master_match = lookups[col][val]
                match_status = "Matched"
                user_type = "Existing User"
                matched_by = col
                # Try to find a good identifier from master (username or email or empid)
                matched_record = master_match.get('userName', master_match.get('email', master_match.get('employeeId', val)))
                remarks = f"Matched by {col}"
                break # Stop checking lower priorities
                
        # 3. Build enriched row
        enriched_row = client_row.to_dict()
        enriched_row['User Type'] = user_type
        enriched_row['Match Status'] = match_status
        enriched_row['Matched By'] = matched_by
        enriched_row['Matched Medblaze Record'] = matched_record
        enriched_row['Remarks'] = remarks
        
        # Attach the matched master data for diffing later (prefix with master_)
        if master_match:
            for k, v in master_match.items():
                enriched_row[f"master_{k}"] = v
                
        results.append(enriched_row)
        
    return pd.DataFrame(results)
