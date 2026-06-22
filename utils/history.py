import pandas as pd
import streamlit as st
import numpy as np
from utils.common import detect_duplicates_in_df

# Configurable guardrails
_UNDO_LIMIT        = 30    # max history depth
_SNAPSHOT_ROW_CAP  = 500   # rows above this → warn + still snapshot (safety)

def _compute_ai_diff(old_df: pd.DataFrame, new_df: pd.DataFrame) -> pd.DataFrame:
    """Return a human-readable summary DataFrame of AI-changed cells."""
    skip = {'#', '_group_key'}
    cols = [c for c in old_df.columns if c in new_df.columns and c not in skip]
    min_len = min(len(old_df), len(new_df))
    if min_len == 0 or not cols:
        return pd.DataFrame(columns=['Row #', 'Column', 'Before', 'After'])
    
    old_vals = old_df[cols].iloc[:min_len].astype(str).apply(lambda x: x.str.strip())
    new_vals = new_df[cols].iloc[:min_len].astype(str).apply(lambda x: x.str.strip())
    
    changed_sparse = old_vals.compare(new_vals, result_names=('Before', 'After'))
    if changed_sparse.empty:
        return pd.DataFrame(columns=['Row #', 'Column', 'Before', 'After', 'Status'])
        
    # Get only the columns that actually had modifications
    changed_cols = changed_sparse.columns.get_level_values(0).unique()
    
    # Rerun compare on just those columns, but keep all rows so we can show 'untouched' cells
    changed = old_vals[changed_cols].compare(new_vals[changed_cols], keep_shape=True, keep_equal=True, result_names=('Before', 'After'))
    
    # Stack to convert to long format efficiently
    changed = changed.stack(level=0).reset_index()
    changed.rename(columns={'level_0': 'row_idx', 'level_1': 'Column'}, inplace=True)
    
    # Map row_idx to Row # using the actual dataframe index
    if '#' in old_df.columns:
        row_nums_map = old_df['#'].iloc[:min_len].to_dict()
    else:
        row_nums_map = {idx: i+1 for i, idx in enumerate(old_df.index[:min_len])}
        
    changed['Row #'] = changed['row_idx'].apply(lambda idx: row_nums_map.get(idx, idx))
    
    # Add Status and sort (Changed at the top, Untouched at the bottom)
    changed['is_changed'] = changed['Before'] != changed['After']
    changed['Status'] = np.where(changed['is_changed'], '✏️ Changed', '➖ Untouched')
    changed = changed.sort_values(by=['is_changed', 'Row #'], ascending=[False, True]).reset_index(drop=True)
    
    return changed[['Row #', 'Column', 'Before', 'After', 'Status']]

def _df_hash(df: pd.DataFrame, cols: list) -> int:
    """Fast structural hash of selected columns using pandas' built-in vectorised
    hash engine.  Returns a single int — suitable for O(1) equality pre-check.
    Strips '#' and AgGrid internal columns before hashing."""
    safe_cols = [c for c in cols if c in df.columns]
    if not safe_cols:
        return 0
    try:
        return hash(tuple(
            pd.util.hash_pandas_object(
                df[safe_cols].astype(str),   # str cast: handles mixed types safely
                index=False
            )
        ))
    except Exception:
        return 0  # fallback: treat as changed so diff runs

def _recalculate_duplicates() -> None:
    """Dynamically recalculates the exact-duplicate flag based on current data."""
    if 'df_users' in st.session_state and st.session_state.df_users is not None:
        st.session_state.df_users = detect_duplicates_in_df(st.session_state.df_users)

def _update_users_hash() -> None:
    """Immediately updates _df_users_hash in SessionState based on current df_users."""
    if 'df_users' in st.session_state and st.session_state.df_users is not None:
        df = st.session_state.df_users
        watch_cols = [
            c for c in df.columns
            if not str(c).startswith('_')
            and not str(c).startswith('::')
            and c != '#'
        ]
        st.session_state._df_users_hash = _df_hash(df, watch_cols)
    else:
        st.session_state._df_users_hash = None

def _push_diff(stack: list, entry: dict) -> None:
    """Append an undo/redo entry and evict the oldest if over limit."""
    stack.append(entry)
    while len(stack) > _UNDO_LIMIT:
        stack.pop(0)   # drop oldest entry (O(n) but stacks are tiny)

def _df_diff(old_df: pd.DataFrame, new_df: pd.DataFrame) -> list:
    """Return list of (row_idx, col, old_val, new_val) for every changed cell.
    Compares only shared columns; ignores '#' and internal AgGrid columns."""
    skip = {'#'}
    cols = [
        c for c in old_df.columns
        if c in new_df.columns and c not in skip
        and not str(c).startswith('_') and not str(c).startswith('::')
    ]
    # Align to same length (structural differences are handled via snapshots)
    min_len = min(len(old_df), len(new_df))
    old_vals = old_df[cols].iloc[:min_len].astype(object).fillna("").reset_index(drop=True)
    new_vals = new_df[cols].iloc[:min_len].astype(object).fillna("").reset_index(drop=True)
    changed = old_vals.compare(new_vals, result_names=('old', 'new'))
    diffs = []
    if changed.empty:
        return diffs
        
    changed_cols = changed.columns.get_level_values(0).unique()
    for row_idx, row in changed.iterrows():
        for col in changed_cols:
            try:
                ov = row[(col, 'old')]
                nv = row[(col, 'new')]
                if pd.notna(ov) or pd.notna(nv):   # skip if both NaN (no real change)
                    diffs.append((int(row_idx), col, ov, nv))
            except KeyError:
                pass
    return diffs

def _apply_diff(df: pd.DataFrame, changes: list, reverse: bool = False) -> pd.DataFrame:
    """Apply (or reverse) a diff list to a DataFrame copy."""
    result = df.copy()
    for row_idx, col, old_val, new_val in changes:
        if row_idx < len(result) and col in result.columns:
            result.at[row_idx, col] = old_val if reverse else new_val
    return result

def _save_cell_diff(old_df: pd.DataFrame, new_df: pd.DataFrame) -> bool:
    """Push a cell-diff entry onto undo_stack. Returns True if changes found."""
    diffs = _df_diff(old_df, new_df)
    if not diffs:
        return False
    _push_diff(st.session_state.undo_stack, {'kind': 'diff', 'changes': diffs})
    st.session_state.redo_stack.clear()
    return True

def _save_snapshot(df: pd.DataFrame) -> None:
    """Push a full snapshot entry (used for structural changes: add/delete rows)."""
    # Keep only data columns — '#' is regenerated; drop AgGrid internals
    clean = df[[c for c in df.columns
                if not str(c).startswith('::') and not str(c).startswith('_')]].copy()
    _push_diff(st.session_state.undo_stack, {'kind': 'snapshot', 'data': clean})
    st.session_state.redo_stack.clear()

def _pop_undo(current_df: pd.DataFrame):
    """Pop the top of undo_stack, push to redo_stack, return restored DataFrame."""
    if not st.session_state.undo_stack:
        return current_df
    entry = st.session_state.undo_stack.pop()
    # Save current state to redo before restoring
    if entry['kind'] == 'diff':
        # For redo we need the inverse diff (new→old already captured)
        _push_diff(st.session_state.redo_stack,
                   {'kind': 'diff', 'changes': entry['changes']})
        return _apply_diff(current_df, entry['changes'], reverse=True)
    else:  # snapshot
        # Push current state as a snapshot to redo
        clean = current_df[[c for c in current_df.columns
                             if not str(c).startswith('::') and not str(c).startswith('_')]].copy()
        _push_diff(st.session_state.redo_stack, {'kind': 'snapshot', 'data': clean})
        return entry['data'].copy()

def _pop_redo(current_df: pd.DataFrame):
    """Pop the top of redo_stack, push to undo_stack, return restored DataFrame."""
    if not st.session_state.redo_stack:
        return current_df
    entry = st.session_state.redo_stack.pop()
    if entry['kind'] == 'diff':
        _push_diff(st.session_state.undo_stack,
                   {'kind': 'diff', 'changes': entry['changes']})
        return _apply_diff(current_df, entry['changes'], reverse=False)
    else:  # snapshot
        clean = current_df[[c for c in current_df.columns
                             if not str(c).startswith('::') and not str(c).startswith('_')]].copy()
        _push_diff(st.session_state.undo_stack, {'kind': 'snapshot', 'data': clean})
        return entry['data'].copy()
