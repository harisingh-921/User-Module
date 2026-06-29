import pandas as pd
import re
from typing import List, Dict, Any, Tuple

def normalize_value(val: Any, col_name: str) -> str:
    """Normalizes a single value based on the column name."""
    if pd.isna(val):
        return ""
    
    val_str = str(val).strip()
    col_lower = col_name.lower()
    
    if 'email' in col_lower or 'mail' in col_lower:
        return val_str.lower()
    elif 'employee' in col_lower or 'emp' in col_lower:
        return val_str.lower()
    elif 'mobile' in col_lower or 'phone' in col_lower:
        # Remove spaces and non-numeric characters (keep + for country codes)
        return re.sub(r'[^\d+]', '', val_str)
    elif 'user' in col_lower and 'name' in col_lower:
        return val_str.lower()
    else:
        # For other custom columns
        return val_str

def detect_duplicates(df: pd.DataFrame, priority_mappings: List[dict]) -> pd.DataFrame:
    """
    Detects full-row duplicates in the client file.
    A row is considered a duplicate only if ALL its columns match another row.
    Adds a boolean 'Is Duplicate' column to the dataframe.
    """
    df = df.copy()
    
    # Identify full row duplicates
    # keep=False ensures all copies of the duplicate row are flagged
    df['Is Duplicate'] = df.duplicated(keep=False)
        
    return df

def build_master_lookup_dicts(master_df: pd.DataFrame, priority_mappings: List[dict]) -> Dict[str, Dict[str, dict]]:
    """
    Builds optimized O(1) dictionary lookups for Medblaze master data.
    """
    from config.constants import SEMANTIC_MAPPINGS, USER_MASTER_COLS
    
    # Normalize master_df columns first
    normalized_master_df = master_df.copy()
    for col in normalized_master_df.columns:
        col_lower = str(col).strip().lower()
        
        # Check explicit mappings first
        renamed = False
        for target_col, aliases in SEMANTIC_MAPPINGS.items():
            if col_lower in aliases or col_lower == target_col.lower():
                normalized_master_df.rename(columns={col: target_col}, inplace=True)
                renamed = True
                break
                
        # If not renamed by explicit mapping, check against standard target columns directly
        if not renamed:
            for target_col in USER_MASTER_COLS:
                if col_lower == target_col.lower() or col_lower.replace(" ", "") == target_col.lower():
                    normalized_master_df.rename(columns={col: target_col}, inplace=True)
                    break
                
    lookups = {}
    for m in priority_mappings:
        name = m['name']
        original_col = m['master_col']
        
        # Find what this column was renamed to
        col = original_col
        col_lower = str(original_col).strip().lower()
        for target_col, aliases in SEMANTIC_MAPPINGS.items():
            if col_lower in aliases or col_lower == target_col.lower():
                col = target_col
                break
                
        lookups[name] = {}
        
        if col not in normalized_master_df.columns:
            continue
            
        for _, row in normalized_master_df.iterrows():
            val = normalize_value(row[col], name)
            if val:
                lookups[name][val] = row.to_dict()
                
    return lookups

def compare_users(client_df: pd.DataFrame, master_df: pd.DataFrame, priority_mappings: List[dict]) -> pd.DataFrame:
    """
    Compares client users against Medblaze users using priority-based dictionary lookups.
    """
    lookups = build_master_lookup_dicts(master_df, priority_mappings)
    
    results = []
    
    for _, client_row in client_df.iterrows():
        match_status = "Not Matched"
        user_type = "New User"
        matched_by = ""
        matched_record = ""
        remarks = "No matching user found"
        master_match = None
        
        for m in priority_mappings:
            name = m['name']
            c_col = m['client_col']
            
            if c_col not in client_row:
                continue
                
            val = normalize_value(client_row[c_col], name)
            if not val:
                continue
                
            if name in lookups and val in lookups[name]:
                master_match = lookups[name][val]
                match_status = "Matched"
                user_type = "Existing User"
                matched_by = name
                matched_record = master_match.get('userName', master_match.get('email', master_match.get('employeeId', val)))
                remarks = f"Matched by {name}"
                break
                
        enriched_row = client_row.to_dict()
        enriched_row['User Type'] = user_type
        enriched_row['Match Status'] = match_status
        enriched_row['Matched By'] = matched_by
        enriched_row['Matched Medblaze Record'] = matched_record
        enriched_row['Remarks'] = remarks
        
        if master_match:
            for k, v in master_match.items():
                enriched_row[f"master_{k}"] = v
                
        results.append(enriched_row)
        
    return pd.DataFrame(results)
