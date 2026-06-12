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
