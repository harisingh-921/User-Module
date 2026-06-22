# user_masters/utils/common.py
"""
Centralized helpers for detecting and cleaning "empty" / placeholder values.

Every module that needs to test whether a cell is logically blank should import
from here instead of maintaining its own inline tuple of sentinel strings.
"""
import pandas as pd

# ── Canonical set of strings that represent "no data" ────────────────────────
# Kept as a frozenset for O(1) membership tests.
_EMPTY_STRINGS = frozenset({'', 'nan', 'none', '-', 'na', 'n/a'})


def is_empty_value(val) -> bool:
    """Return True if *val* is logically blank / placeholder.

    Handles None, pd.NA / np.nan, and common string sentinels like
    'nan', 'none', '-', 'na', 'n/a' (case-insensitive, stripped).

    >>> is_empty_value(None)
    True
    >>> is_empty_value('  NaN ')
    True
    >>> is_empty_value('John')
    False
    """
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return True
    try:
        if pd.isna(val):
            return True
    except (TypeError, ValueError):
        pass
    return str(val).strip().lower() in _EMPTY_STRINGS


def has_value(val) -> bool:
    """Convenience inverse of :func:`is_empty_value`."""
    return not is_empty_value(val)


def clean_empty_series(series: pd.Series) -> pd.Series:
    """Replace all sentinel strings in a pandas Series with ``pd.NA``.

    Useful before calling ``.dropna()`` or ``.fillna()``.

    >>> import pandas as pd
    >>> s = pd.Series(['hello', 'nan', '-', '', None])
    >>> clean_empty_series(s).tolist()
    ['hello', <NA>, <NA>, <NA>, <NA>]
    """
    cleaned = series.astype(str).str.strip().str.lower()
    return series.where(~cleaned.isin(_EMPTY_STRINGS), other=pd.NA)


def detect_duplicates_in_df(df: pd.DataFrame) -> pd.DataFrame:
    """Add or update _is_duplicate_user and _is_duplicate_username columns."""
    df = df.copy()
    if not df.empty:
        check_cols = [c for c in df.columns if not str(c).startswith('_') and not str(c).startswith('::') and c != '#']
        df['_is_duplicate_user'] = df.duplicated(subset=check_cols, keep=False)

        if 'userName' in df.columns:
            normalized_names = df['userName'].astype(str).str.strip().str.lower()
            valid_names = clean_empty_series(normalized_names).dropna()
            counts = valid_names.value_counts()
            dups = counts[counts > 1].index
            df['_is_duplicate_username'] = normalized_names.isin(dups)
        else:
            df['_is_duplicate_username'] = False
    else:
        df['_is_duplicate_user'] = False
        df['_is_duplicate_username'] = False
    return df


def resolve_duplicate_usernames(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """
    Finds all duplicate values in the 'userName' column case-insensitively.
    Keeps the first occurrence as is, and renames subsequent occurrences by appending
    sequential numbers (1, 2, 3, etc.) to make them unique.
    Guarantees no new collisions are introduced by checking against existing usernames.
    Returns (updated_df, resolved_count).
    """
    df = df.copy()
    if 'userName' not in df.columns or df.empty:
        return df, 0
    
    # Track existing usernames to prevent naming collisions
    existing_names = set(df['userName'].astype(str).str.strip().str.lower().tolist())
    
    clean_names = df['userName'].astype(str).str.strip()
    lower_names = clean_names.str.lower()
    
    valid_names = clean_empty_series(lower_names).dropna()
    counts = valid_names.value_counts()
    duplicate_lowers = set(counts[counts > 1].index)
    
    seen_lowers = {}
    resolved_count = 0
    
    for idx, row in df.iterrows():
        val = str(row['userName']).strip()
        if not val or val.lower() in ('nan', 'none', '-', 'na', 'n/a'):
            continue
        val_lower = val.lower()
        if val_lower in duplicate_lowers:
            if val_lower not in seen_lowers:
                seen_lowers[val_lower] = 1
            else:
                suffix = seen_lowers[val_lower]
                new_val = f"{val}{suffix}"
                while new_val.lower() in existing_names:
                    suffix += 1
                    new_val = f"{val}{suffix}"
                
                seen_lowers[val_lower] = suffix + 1
                existing_names.add(new_val.lower())
                
                df.at[idx, 'userName'] = new_val
                resolved_count += 1
                
    return df, resolved_count


