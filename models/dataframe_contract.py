# user_masters/models/dataframe_contract.py
"""
Unified DataFrame Contract (UDC)
=================================
Single source of truth for all canonical column names and aliases.

Any module that produces or consumes a user DataFrame should call
``enforce_contract(df)`` before passing the frame to downstream consumers.

This prevents silent field-name mismatches (e.g. 'mobile' vs 'phone')
from propagating through merge, validation, and UI layers.
"""
import pandas as pd
from config.constants import USER_MASTER_COLS

# ---------------------------------------------------------------------------
# Canonical internal column name → list of known aliases to rename from
# ---------------------------------------------------------------------------
_COLUMN_ALIASES: dict[str, list[str]] = {
    "phone":  ["mobile", "Mobile", "MOBILE", "Phone", "PHONE"],
    "email":  ["Email", "EMAIL", "e-mail", "E-MAIL"],
    "userName":     ["username", "Username", "USERNAME", "user_name"],
    "firstName":    ["first_name", "firstname", "Firstname"],
    "lastName":     ["last_name", "lastname", "Lastname"],
    "middleName":   ["middle_name", "middlename", "Middlename"],
    "employeeId":   ["employee_id", "emp_id", "EmpId", "EmployeeID"],
    "departments":  ["department", "Department", "DEPARTMENT", "Departments"],
    "isEnabled":    ["isenabled", "IsEnabled", "is_enabled", "enabled", "Enabled"],
}


def enforce_contract(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalise a user DataFrame to the application's canonical schema.

    Steps:
    1. Rename any columns that are known aliases for a canonical name.
    2. Add any missing canonical columns as empty-string columns.
    3. Return the normalised DataFrame (original is not mutated).

    Parameters
    ----------
    df : pd.DataFrame
        Raw DataFrame from any extraction engine.

    Returns
    -------
    pd.DataFrame
        DataFrame with canonical column names and all schema columns present.

    Example
    -------
    >>> df = pd.DataFrame([{"firstName": "John", "mobile": "9999999999"}])
    >>> result = enforce_contract(df)
    >>> "phone" in result.columns
    True
    >>> "mobile" in result.columns
    False
    """
    if df.empty:
        return df

    result = df.copy()

    # Step 1: Rename known aliases to their canonical name
    rename_map: dict[str, str] = {}
    for canonical, aliases in _COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in result.columns and alias != canonical:
                # Only rename if the canonical column doesn't already exist
                if canonical not in result.columns:
                    rename_map[alias] = canonical
                break  # Only the first matching alias per canonical field

    if rename_map:
        result = result.rename(columns=rename_map)

    # Step 2: Add missing canonical columns as empty strings, and ensure all are cast to string safely
    def _safe_str(val) -> str:
        if pd.isna(val) or val is None:
            return ""
        if isinstance(val, float):
            if val.is_integer():
                return str(int(val))
            return str(val)
        val_str = str(val).strip()
        if val_str.lower() in ("nan", "none", "<na>"):
            return ""
        if val_str.endswith(".0"):
            try:
                f_val = float(val_str)
                if f_val.is_integer():
                    return str(int(f_val))
            except ValueError:
                pass
        return val_str

    for col in USER_MASTER_COLS:
        if col not in result.columns:
            result[col] = ""
        else:
            result[col] = result[col].apply(_safe_str)

    return result

