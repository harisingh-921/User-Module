# user_masters/extraction/utils.py
import os
import logging
import streamlit as st

log = logging.getLogger(__name__)

def find_matching_excel_roles(user_dict, excel_rows_data):
    emp_id = str(user_dict.get('employeeId', '')).strip().lower()
    email = str(user_dict.get('email', '')).strip().lower()
    uname = str(user_dict.get('userName', '')).strip().lower()
    
    # Priority 1: Match by Employee ID
    if emp_id and emp_id not in ('nan', 'none', '-', ''):
        for row_info in excel_rows_data:
            if emp_id in row_info['raw_values']:
                return row_info['roles']
                
    # Priority 2: Match by Email
    if email and email not in ('nan', 'none', '-', ''):
        for row_info in excel_rows_data:
            if email in row_info['raw_values']:
                return row_info['roles']
                
    # Priority 3: Match by Username
    if uname and uname not in ('nan', 'none', '-', ''):
        for row_info in excel_rows_data:
            if uname in row_info['raw_values'] or any(uname in str(val) for val in row_info['raw_values']):
                return row_info['roles']
                
    # Fallback: return whatever roles the LLM extracted
    return user_dict.get('roles', '')

def get_all_api_keys(primary_key=None):
    keys = []
    if primary_key:
        p_str = str(primary_key).strip()
        if p_str and p_str not in keys:
            keys.append(p_str)
            
    # Load from st.secrets
    try:
        # Check standard names
        for k in ["OPENAI_API_KEY", "OPENAI_API_KEY_2", "OPENAI_API_KEY_3", "GEMINI_API_KEY", "GEMINI_API_KEY_2", "GEMINI_API_KEY_3"]:
            val = str(st.secrets.get(k, "")).strip()
            if val and val not in keys:
                keys.append(val)
                
        # Also grab any key matching dynamic pattern
        for k in st.secrets.keys():
            val = str(st.secrets.get(k, "")).strip()
            if (val.startswith("sk-") or val.startswith("AIzaSy")) and val not in keys:
                keys.append(val)
    except Exception:
        pass
        
    # Manual fallback: load from secrets.toml relative to this file's folder
    if not keys or len(keys) <= (1 if primary_key else 0):
        try:
            import toml
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            secrets_path = os.path.join(base_dir, ".streamlit", "secrets.toml")
            if os.path.exists(secrets_path):
                secrets_data = toml.load(secrets_path)
                for k in ["OPENAI_API_KEY", "OPENAI_API_KEY_2", "OPENAI_API_KEY_3", "GEMINI_API_KEY", "GEMINI_API_KEY_2", "GEMINI_API_KEY_3"]:
                    val = str(secrets_data.get(k, "")).strip()
                    if val and val not in keys:
                        keys.append(val)
        except Exception:
            pass
            
    return keys
