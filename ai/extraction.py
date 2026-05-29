# user_masters/ai/extraction.py
import io
import time
import json
import logging
import pandas as pd
import streamlit as st
import fitz
import docx
from openai import OpenAI
from concurrent.futures import ThreadPoolExecutor, as_completed

from config.constants import USER_MASTER_COLS
from models.schemas import UserMasterResult
from extraction.merge import _merge_duplicate_users
from extraction.utils import get_all_api_keys, find_matching_excel_roles

log = logging.getLogger(__name__)

# ── Enterprise Safety Limits (edit here to tune) ─────────────────────────────
_MAX_FILE_SIZE_MB   = 20      # Hard reject uploads larger than this
_MAX_PDF_PAGES      = 60      # Cap PDF pages sent to AI
_MAX_AI_CONTEXT_KB  = 80      # Approx token guard: skip AI call if context > 80 KB
_AI_RETRY_ATTEMPTS  = 3       # Transient error retries for apply_ai_smart_context
_AI_RETRY_BASE_WAIT = 2       # Base seconds for exponential backoff
# Columns the AI is permitted to modify via apply_ai_smart_context
_AI_ALLOWED_EDIT_COLS = {
    'firstName', 'middleName', 'lastName', 'userName', 'email', 'mobile',
    'employeeId', 'departments', 'roles', 'units', 'designation',
    'isEnabled', 'password',
}
# ─────────────────────────────────────────────────────────────────────────────

USER_EXTRACTION_PROMPT = """
You are a High-Precision, Format-Agnostic User Data Extraction Engine.
Your task is to extract a structured user list from ANY document format — staff rosters, HR matrices, Word tables, PDFs, CSV exports, or any custom layout.

=== STEP 1: UNDERSTAND THE STRUCTURE ===
Before extracting, ANALYZE the document layout:
- Is this a STANDARD ROSTER? (one row per person with named columns like Name, Email, Department...)
- Is this a ROLE MATRIX? (columns represent roles, cells are Yes/No, and a separate column has the person name)
- Is this a FREE-FORMAT LIST? (names and details listed without a strict table structure)
- Could there be MERGED HEADERS or multi-row headers above the data?
DO NOT assume any fixed column order or name. Identify each column by its CONTENT and SEMANTIC MEANING.

=== STEP 2: FIELD IDENTIFICATION ===
Identify fields by MEANING, not by position or exact column header name:
- NAME field: Contains full person names including titles (e.g. "Dr. NG SWEET MAY", "Mr. RAMESH JOSHI"). Capture prefixes as part of the first name.
- EMAIL field: Contains @ symbols
- PHONE/MOBILE: Contains 010/011/012 patterns or dashes like 012-345-6789
- EMPLOYEE ID: Alphanumeric codes like CA00001, GB10007, EMP001
- DEPARTMENT: Hospital departments (Emergency Room, ICU, OPD, Surgery...)
- UNIT/FACILITY: Hospital branches or facility names (CAH Bukit Jalil, Ankura...)
- DESIGNATION/POSITION: Job titles (Doctor, Nurse, Consultant, Locum MO...)
- ROLES: Either a column with slash-separated text OR multiple Yes/No columns whose HEADERS are role names

=== STEP 3: EXTRACTION RULES ===
1. ROW INTEGRITY (MANDATORY): You MUST extract EVERY person in the data. Do not skip anyone. Do not summarize.
2. MULTI-USER SPLIT RULE (MANDATORY): A single row may contain data for MULTIPLE people, separated by a CONSISTENT DELIMITER. The delimiter can be ANY of: "|", ",", ";", "/", " & ", " and " — whichever is used consistently across that row.
   DETECTION: If the SAME delimiter appears in MULTIPLE columns of the same row (e.g. firstName has "Bijay | Maumita" AND employeeId has "1035708 | 192004"), that row contains multiple users. You MUST create SEPARATE JSON objects for each person.
   SPLITTING RULES:
   - Identify the delimiter being used (e.g. "|" or "," or "&").
   - User 1 takes the 1st part of EVERY delimited column.
   - User 2 takes the 2nd part of EVERY delimited column.
   - For columns with NO delimiter (e.g. middleName "Krishna" when others use "|"), apply the value ONLY to User 1. Leave it BLANK for User 2.
   - NEVER include the delimiter symbol in your final JSON fields — strip it out completely.
   - WORKED EXAMPLE with "|" delimiter (follow exactly):
       Source row: firstName="Bijay | Maumita", middleName="Krishna", lastName="Maity | Saha", employeeId="1035708 | 192004"
       firstName has "|" → 2 users. lastName has "|" → 2 users. employeeId has "|" → 2 users. middleName has NO "|" → belongs to User 1 only.
       Correct output:
         User 1: firstName="Bijay",   middleName="Krishna", lastName="Maity", employeeId="1035708"
         User 2: firstName="Maumita", middleName="",        lastName="Saha",  employeeId="192004"
   - WORKED EXAMPLE with "|" delimiter and MISSING lastName/employeeId for User 2 (follow exactly):
        Source row: firstName="Arindam | Riya", middleName="", lastName="Chakraborty", employeeId="10092"
        firstName has "|" → 2 users. middleName has NO "|" → blank for both. lastName has NO "|" → belongs ONLY to User 1. employeeId has NO "|" → belongs ONLY to User 1.
        Correct output:
          User 1: firstName="Arindam", middleName="", lastName="Chakraborty", employeeId="10092"
          User 2: firstName="Riya",    middleName="", lastName="",            employeeId=""
        WRONG output (never do this):
          User 2: firstName="Riya", lastName="Chakraborty"  ← copying no-pipe lastName to User 2 is FORBIDDEN.
          User 2: employeeId="10092" ← copying no-pipe employeeId to User 2 is FORBIDDEN.
   - WORKED EXAMPLE with 3-user split and NO middle names (follow exactly):
       Source row: firstName="Priyadarshini | Manisha | Anasuya", middleName="", lastName="Roy | Santra | Bajpaye"
       Correct output:
         User 1: firstName="Priyadarshini", lastName="Roy"
         User 2: firstName="Manisha",      lastName="Santra"
         User 3: firstName="Anasuya",     lastName="Bajpaye"
       WRONG output (never do this):
         User 1: firstName="Priyadarshini Manisha", lastName="Roy"  ← Merging names is FORBIDDEN.
   - WORKED EXAMPLE with "," delimiter:
       Source row: firstName="Anjali, Priya", lastName="Sen, Sharma", employeeId="101, 102"
       Correct output:
         User 1: firstName="Anjali", lastName="Sen",    employeeId="101"
         User 2: firstName="Priya",  lastName="Sharma", employeeId="102"
 3. FIELD MAPPING:
    - firstName, middleName, lastName: Extract logically from the source data.
    - STRICT COLUMN ALIGNMENT (CRITICAL): Do NOT shift data across columns. If the "Middle Name" column in Excel is blank for a specific user, the "middleName" field in JSON MUST be blank. NEVER move the second person's first name (from a pipe-split) into the first person's middleName field.
    - If the document has a "Full Name" column, split it logically into firstName and lastName.
    - employeeId: Extract the unique ID.
    - roles: This is CRITICAL. In this Excel format, the roles are often found in Column A as "floating headers" (e.g. 'Audit User - CESC - CAUTI') or are provided in the [ROLE SECTION:] tag at the start of the row. Combine all applicable roles found in Column A and [ROLE SECTION:] into this field, separated by "|".
    - departments / units / designation / email / mobile: Map correctly based on column headers.
4. UNIT NAME: Look at the COLUMN HEADERS for a global "Unit Name" (e.g. Unit Name | Anandpur) and apply it to every user.
5. NO LOGIC: Do not try to generate usernames or complex passwords. Just extract the raw name parts. Python will handle the rest.
6. NA LOGIC: If a value is "-", leave it blank.
7. ROLE SECTION TAGS (CRITICAL): Lines tagged with [ROLE SECTION: ...] are SECTION HEADERS, NOT people. NEVER create a user record from a [ROLE SECTION:] tag. Only use them to determine the `roles` value for the real data rows that follow. If a row has no valid name or employee ID, SKIP it entirely.
8. MIDDLE NAME RULE (CRITICAL): The `middleName` field is ONLY for a person's own middle name or initial (e.g. "K", "Kumar", "Rani"). It must NEVER contain another person's first name from a pipe-split. If firstName is "Arindam | Riya", you must create TWO separate users: User 1 has firstName="Arindam" and middleName="" (blank). User 2 has firstName="Riya" and middleName="" (blank). The text after the "|" is a second person, not a middle name.

OUTPUT FORMAT (JSON):
{{
  "document_name": "",
  "users": [
    {{
      "userName": "",
      "firstName": "",
      "middleName": "",
      "lastName": "",
      "employeeId": "",
      "departments": "",
      "roles": "",
      "units": "",
      "designation": "",
      "email": "",
      "mobile": "",
      "isEnabled": "Yes"
    }}
  ]
}}
"""

def get_openai_client(api_key):
    if not api_key:
        return None
    api_key_str = str(api_key).strip()
    if api_key_str.startswith("AIzaSy"):
        # This is a Gemini API Key! Use Gemini's OpenAI-compatible endpoint.
        return OpenAI(
            api_key=api_key_str,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
        )
    return OpenAI(api_key=api_key_str)

def probe_api_key(key):
    """Probes an API key with a fast 3-second timeout request to verify it's working."""
    if not key:
        return False
    key_str = str(key).strip()
    client = get_openai_client(key_str)
    if not client:
        return False
    
    if key_str.startswith("AIzaSy"):
        model = "gemini-2.5-flash"
    else:
        model = "gpt-4o-mini"
        
    try:
        # A simple lightweight chat completion to test connectivity and quota
        client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1,
            timeout=3.0
        )
        return True
    except Exception as e:
        log.warning("Pre-flight check failed for key prefix %s...: %s: %s", key_str[:12], type(e).__name__, e)
        return False

def get_healthy_api_keys(api_key):
    """
    Returns only verified, active API keys.
    Results are cached in Streamlit session state to avoid running probes on every rerun.
    """
    all_keys = get_all_api_keys(api_key)
    if not all_keys:
        return []
        
    if "healthy_api_keys" in st.session_state:
        cached_keys = [k for k in st.session_state.healthy_api_keys if k in all_keys]
        if cached_keys:
            return cached_keys
            
    healthy_keys = []
    with ThreadPoolExecutor(max_workers=len(all_keys)) as executor:
        future_to_key = {executor.submit(probe_api_key, key): key for key in all_keys}
        for future in as_completed(future_to_key):
            key = future_to_key[future]
            try:
                if future.result():
                    healthy_keys.append(key)
            except Exception:
                pass
                
    ordered_healthy = [k for k in all_keys if k in healthy_keys]
    st.session_state.healthy_api_keys = ordered_healthy
    return ordered_healthy

def openai_extract_users(file_bytes, filename, api_key, intent="", pass_prefix="Med"):
    """Universal AI User Extraction Engine with Chunking & Failover."""
    # ── File-size guard ───────────────────────────────────────────────────────
    size_mb = len(file_bytes) / 1_048_576
    if size_mb > _MAX_FILE_SIZE_MB:
        st.error(f"❌ **{filename}** is {size_mb:.1f} MB — exceeds the {_MAX_FILE_SIZE_MB} MB limit. "
                 f"Please split the file and re-upload.")
        return pd.DataFrame()
    # ─────────────────────────────────────────────────────────────────────────

    try:
        healthy_keys = get_healthy_api_keys(api_key)
        if not healthy_keys:
            log.warning("No healthy API keys available. Skipping AI extraction.")
            return None
            
        any_openai_healthy = any(not k.startswith("AIzaSy") for k in healthy_keys)
        # Gemini: use 1 worker per healthy key (round-robin). OpenAI: up to 5.
        max_workers = 5 if any_openai_healthy else min(len(healthy_keys), 3)
        log.info("Starting AI extraction. Healthy keys: %d, OpenAI healthy: %s, Workers: %d", len(healthy_keys), any_openai_healthy, max_workers)

        dynamic_prompt = USER_EXTRACTION_PROMPT.format(pass_prefix=pass_prefix)
        ext = filename.lower()
        
        if ext.endswith(('.xlsx', '.xls', '.csv')):
            if ext.endswith('.csv'):
                raw_df = pd.read_csv(io.BytesIO(file_bytes), header=None)
                sheet_dfs = {'Sheet1': raw_df}
            else:
                # Read ALL sheets — sheet_name=None returns {sheet_name: DataFrame}
                all_sheets = pd.read_excel(io.BytesIO(file_bytes), header=None, sheet_name=None)
                sheet_dfs = all_sheets
                st.toast(f"📋 Found {len(sheet_dfs)} sheet(s): {', '.join(sheet_dfs.keys())}")
            
            # We collect all chunks across all sheets, each with its own correct header context
            all_chunks_to_process = []
            
            global_excel_rows_data = []
            has_tick_role_columns = False
            
            for sheet_name, raw_df in sheet_dfs.items():
                raw_df = raw_df.dropna(how='all')
                mask = raw_df.astype(str).apply(lambda x: x.str.contains(r'[a-zA-Z0-9]', na=False)).any(axis=1)
                raw_df = raw_df[mask].reset_index(drop=True)
                if raw_df.empty: continue
                
                str_df = raw_df.astype(str).map(lambda x: str(x).strip())
                
                # --- Improved Auto-detect header and sub-header row (aligned exactly with local_extract_users) ---
                header_row_idx = 0
                max_matches = 0
                for idx, row in str_df.iterrows():
                    vals = row.str.lower().tolist()
                    header_keywords = ['name', 'email', 'employee', 'id', 'mobile', 'phone', 
                                     'department', 'unit', 'role', 'designation', 'staff',
                                     'first', 'last', 'username', 'password']
                    matches = sum(1 for v in vals if any(kw in str(v).lower() for kw in header_keywords))
                    if matches > max_matches:
                        max_matches = matches
                        header_row_idx = idx
                    if matches >= 5:
                        break
                
                is_sub_header = False
                if header_row_idx + 1 < len(raw_df):
                    next_row = raw_df.iloc[header_row_idx + 1]
                    name_email_empty = True
                    
                    headers_lower_temp = {str(h).strip(): str(h).lower().strip() for h in raw_df.iloc[header_row_idx].values}
                    col_mapping_temp = {}
                    for target_field in ['firstName', 'lastName', 'employeeId', 'email']:
                        tf_lower = target_field.lower()
                        for src_col, src_lower in headers_lower_temp.items():
                            if src_lower == tf_lower or src_lower.replace(' ', '') == tf_lower.lower():
                                col_mapping_temp[src_col] = target_field
                                break
                        else:
                            aliases = {
                                'employeeId': ['emp id', 'employee no', 'staff code', 'associate id', 'uhid', 'id no', 'serial no', 'sl no', 'staff id'],
                                'email': ['e-mail', 'mail id', 'official email', 'email address'],
                                'firstName': ['first name', 'fname', 'given name', 'name', 'employee name', 'staff name'],
                            }.get(target_field, [])
                            for alias in aliases:
                                for src_col, src_lower in headers_lower_temp.items():
                                    if alias in src_lower:
                                        col_mapping_temp[src_col] = target_field
                                        break
                                if target_field in col_mapping_temp.values():
                                    break

                    for src_col, target_field in col_mapping_temp.items():
                        col_index = raw_df.iloc[header_row_idx].tolist().index(src_col)
                        val = str(next_row.iloc[col_index]).strip().lower() if col_index < len(next_row) else ""
                        if val and val not in ('nan', 'none', '-'):
                            name_email_empty = False
                            break
                    
                    text_cells = sum(1 for v in next_row.values if str(v).strip() and str(v).strip().lower() not in ('nan', 'none', '-'))
                    if name_email_empty and text_cells >= 2:
                        is_sub_header = True

                first_data_row = header_row_idx + 2 if is_sub_header else header_row_idx + 1
                header_rows_df = raw_df.iloc[:first_data_row]
                data_rows_df = raw_df.iloc[first_data_row:]
                
                def row_to_str(row):
                    return " ; ".join([str(v).strip().replace(';', ',') if str(v).strip().lower() not in ('nan','none','') else '-' for v in row.values])
                
                sheet_header_context = f"COLUMN HEADERS (from '{sheet_name}'):\n" + "\n".join(row_to_str(r) for _, r in header_rows_df.iterrows())
                
                # --- IDENTIFY TICK-MARKED ROLE COLUMNS IN PYTHON ---
                # Robust sub-header and parent forward-filling (aligned with local_extract_users)
                if is_sub_header:
                    headers = []
                    parent_headers = raw_df.iloc[header_row_idx].tolist()
                    filled_parents = []
                    last_parent = ""
                    for p in parent_headers:
                        p_str = str(p).strip()
                        if p_str and p_str.lower() not in ('nan', 'none', '-'):
                            last_parent = p_str
                        filled_parents.append(last_parent)

                    for c_idx in range(len(raw_df.columns)):
                        parent_h = filled_parents[c_idx]
                        child_h = str(raw_df.iloc[header_row_idx + 1].iloc[c_idx]).strip()
                        
                        parent_clean = "" if parent_h.lower() in ('nan', 'none', '-') else parent_h
                        child_clean = "" if child_h.lower() in ('nan', 'none', '-') else child_h
                        
                        if parent_clean and child_clean:
                            if parent_clean.lower() == child_clean.lower():
                                headers.append(child_clean)
                            else:
                                headers.append(f"{parent_clean}|{child_clean}")
                        elif child_clean:
                            headers.append(child_clean)
                        elif parent_clean:
                            headers.append(parent_clean)
                        else:
                            headers.append(f"col_{c_idx}")
                else:
                    headers = [str(h).strip() for h in raw_df.iloc[header_row_idx].values]

                # Deduplicate columns to prevent Series indexing issues
                unique_headers = []
                header_counts = {}
                for h in headers:
                    if h in header_counts:
                        header_counts[h] += 1
                        unique_headers.append(f"{h}_{header_counts[h]}")
                    else:
                        header_counts[h] = 0
                        unique_headers.append(h)
                headers = unique_headers

                role_cols = {}
                role_keywords = ['role', 'audit', 'incharge', 'admin', 'user', 'manager', 
                                'operator', 'reporter', 'viewer', 'approver', 'officer', 'staff', 'analyst', 'advisor', 'preventionist']
                for col_idx, header in enumerate(headers):
                    header_lower = header.lower()
                    is_role_header = any(kw in header_lower for kw in role_keywords)
                    col_values = data_rows_df.iloc[:, col_idx].dropna().astype(str).str.strip().str.lower()
                    
                    if 'module|' in header_lower:
                        NEGATIVE_VALUES = {'', 'nan', 'none', '-', 'no', 'false', '0'}
                        has_ticks = col_values.apply(lambda v: v.lower() not in NEGATIVE_VALUES).any()
                    else:
                        TICK_VALUES = {'✓', '✔', 'yes', 'y', 'x', '1', 'true', 'v', '\u221a', '\u2713', '\u2714', '\u2611'}
                        has_ticks = col_values.isin(TICK_VALUES).any()
                        
                    if is_role_header and has_ticks:
                        role_cols[col_idx] = header
                        has_tick_role_columns = True
                
                # --- EXTRACT ROLE TICKS PER ROW ---
                for idx, row in data_rows_df.iterrows():
                    row_roles = []
                    for col_idx, role_name in role_cols.items():
                        val = str(row.iloc[col_idx]).strip().lower() if col_idx < len(row) else ""
                        
                        is_ticked = False
                        if 'module|' in role_name.lower():
                            NEGATIVE_VALUES = {'', 'nan', 'none', '-', 'no', 'false', '0'}
                            is_ticked = val not in NEGATIVE_VALUES
                        else:
                            TICK_VALUES = {'✓', '✔', 'yes', 'y', 'x', '1', 'true', 'v', '\u221a', '\u2713', '\u2714', '\u2611'}
                            is_ticked = val in TICK_VALUES
                            
                        if is_ticked:
                            clean_role_name = role_name
                            if '|' in clean_role_name:
                                clean_role_name = clean_role_name.split('|')[-1]
                            row_roles.append(clean_role_name)
                    
                    raw_vals = []
                    for v in row.values:
                        if pd.notna(v):
                            v_str = str(v).strip().lower()
                            if v_str not in ('nan', 'none', '', '-'):
                                raw_vals.append(v_str)
                    
                    global_excel_rows_data.append({
                        'roles': '|'.join(row_roles),
                        'raw_values': raw_vals
                    })
                
                sheet_lines = []
                last_col_a_value = ""
                for _, row in data_rows_df.iterrows():
                    line = row_to_str(row)
                    if not line.strip(): continue
                    col_a_val = str(row.iloc[0]).strip() if len(row) > 0 else ""
                    if col_a_val.lower() not in ('nan', 'none', '', '-'):
                        last_col_a_value = col_a_val
                    tag = f"[SHEET: {sheet_name}]"
                    if last_col_a_value:
                        tag += f" [ROLE SECTION: {last_col_a_value}]"
                    sheet_lines.append(f"{tag} {line}")
                
                # Create chunks for this specific sheet
                # Small chunks (10 rows) = higher precision, fewer skipped users
                chunk_size = 40
                for i in range(0, len(sheet_lines), chunk_size):
                    chunk = sheet_lines[i:i + chunk_size]
                    all_chunks_to_process.append({
                        'text': sheet_header_context + "\n\nDATA:\n" + "\n".join(chunk),
                        'sheet': sheet_name,
                        'line_start': i
                    })

            if not all_chunks_to_process:
                st.error("⚠️ No data found in any of the Excel sheets.")
                return pd.DataFrame()
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            status_text.info(f"🚀 Started extraction of {len(all_chunks_to_process)} batches...")
            
            all_users = []
            
            def process_chunk(chunk_data, batch_idx):
                chunk_text = chunk_data['text']
                # Round-robin: assign each batch a primary key to spread load
                key_order = [healthy_keys[(batch_idx + i) % len(healthy_keys)] for i in range(len(healthy_keys))]
                
                for k_idx, current_key in enumerate(key_order):
                    current_client = get_openai_client(current_key)
                    if not current_client:
                        continue
                    
                    if current_key.startswith("AIzaSy"):
                        models_to_try = ["gemini-2.5-flash"]
                    else:
                        models_to_try = ["gpt-4o-mini", "gpt-4o"]
                        
                    for model in models_to_try:
                        try:
                            completion = current_client.chat.completions.parse(
                                model=model,
                                messages=[
                                    {"role": "system", "content": dynamic_prompt},
                                    {"role": "user", "content": f"USER INTENT: {intent}\n\nINPUT DATA TABLE:\n{chunk_text}"}
                                ],
                                response_format=UserMasterResult,
                                timeout=60,
                                temperature=0.0
                            )
                            result = [u.__dict__ for u in completion.choices[0].message.parsed.users]
                            if not result and (model == "gpt-4o-mini" or model == "gemini-2.5-flash"):
                                time.sleep(1)
                                completion2 = current_client.chat.completions.parse(
                                    model=model,
                                    messages=[
                                        {"role": "system", "content": dynamic_prompt},
                                        {"role": "user", "content": f"USER INTENT: {intent}\n\nINPUT DATA TABLE:\n{chunk_text}"}
                                    ],
                                    response_format=UserMasterResult,
                                    timeout=60,
                                    temperature=0.0
                                )
                                result = [u.__dict__ for u in completion2.choices[0].message.parsed.users]
                            return result
                        except Exception as e:
                            log.warning("Batch %d AI error model=%s: %s", batch_idx, model, e, exc_info=True)
                            err_str = str(e).lower()
                            if "quota" in err_str or "rate limit" in err_str or "429" in err_str:
                                log.info("Batch %d key #%d rate limited. Trying next key...", batch_idx, k_idx + 1)
                                break
                            else:
                                if model == models_to_try[0] and len(models_to_try) > 1:
                                    time.sleep(1)
                                    continue
                return []

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_idx = {executor.submit(process_chunk, chunk, i): i for i, chunk in enumerate(all_chunks_to_process)}
                completed = 0
                # Store results by index to preserve source order
                ordered_results = {}
                for future in as_completed(future_to_idx):
                    idx = future_to_idx[future]
                    ordered_results[idx] = future.result()
                    completed += 1
                    progress_bar.progress(completed / len(all_chunks_to_process))
                    captured = sum(len(v) for v in ordered_results.values())
                    status_text.info(f"⚡ Extraction: {completed}/{len(all_chunks_to_process)} batches done ({captured} users captured)")
            
            # Flatten in chunk order to preserve original row sequence
            all_users = []
            for i in sorted(ordered_results.keys()):
                all_users.extend(ordered_results[i])
            
            status_text.empty()
            progress_bar.empty()
            
            # Override roles with exact Excel ticks if available
            if has_tick_role_columns and global_excel_rows_data:
                for user in all_users:
                    matched_roles = find_matching_excel_roles(user, global_excel_rows_data)
                    user['roles'] = matched_roles
            
            raw_df = pd.DataFrame(all_users)
            result_df = _merge_duplicate_users(raw_df, pass_prefix=pass_prefix)
            st.toast(f"✅ {len(raw_df)} raw rows → {len(result_df)} unique users after merge.")
            return result_df

        elif ext.endswith('.pdf'):
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            total_pages = len(doc)
            if total_pages > _MAX_PDF_PAGES:
                st.warning(f"⚠️ **{filename}** has {total_pages} pages — processing first {_MAX_PDF_PAGES} only.")
            all_lines = []
            for page in doc.pages(0, min(total_pages, _MAX_PDF_PAGES)):
                text = page.get_text("text")
                lines = [line.strip() for line in text.split("\n") if line.strip()]
                all_lines.extend(lines)
            st.toast(f"📄 Read {min(total_pages, _MAX_PDF_PAGES)}/{total_pages} PDF pages.")
            header_context = "SOURCE: PDF Document\n"
            
        elif ext.endswith(('.docx', '.doc')):
            doc = docx.Document(io.BytesIO(file_bytes))
            all_lines = []
            for para in doc.paragraphs:
                if para.text.strip():
                    all_lines.append(para.text.strip())
            for table in doc.tables:
                for row in table.rows:
                    row_data = [cell.text.strip().replace('\n', ' ') for cell in row.cells]
                    if any(row_data):
                        all_lines.append(" | ".join(row_data))
            st.toast(f"📄 Read Word document.")
            header_context = "SOURCE: Word Document\n"
            
        else:
            st.error(f"Unsupported file format: {ext}")
            return None

        # Fallback for PDF/Word
        chunk_size = 30
        chunks = []
        for i in range(0, len(all_lines), chunk_size):
            chunk = all_lines[i:i + chunk_size]
            chunks.append(header_context + "\n\nDATA:\n" + "\n".join(chunk))
        
        if not chunks: return pd.DataFrame()
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        def process_simple_chunk(chunk_text, batch_idx):
            key_order = [healthy_keys[(batch_idx + i) % len(healthy_keys)] for i in range(len(healthy_keys))]
            for k_idx, current_key in enumerate(key_order):
                current_client = get_openai_client(current_key)
                if not current_client:
                    continue
                
                if current_key.startswith("AIzaSy"):
                    models_to_try = ["gemini-2.5-flash"]
                else:
                    models_to_try = ["gpt-4o-mini", "gpt-4o"]
                    
                for model in models_to_try:
                    try:
                        completion = current_client.chat.completions.parse(
                            model=model,
                            messages=[
                                {"role": "system", "content": dynamic_prompt},
                                {"role": "user", "content": f"USER INTENT: {intent}\n\nINPUT DATA TABLE:\n{chunk_text}"}
                            ],
                            response_format=UserMasterResult,
                            timeout=60,
                            temperature=0.0
                        )
                        return [u.__dict__ for u in completion.choices[0].message.parsed.users]
                    except Exception as e:
                        log.warning("PDF/Word Batch %d AI error model=%s: %s", batch_idx, model, e, exc_info=True)
                        err_str = str(e).lower()
                        if "quota" in err_str or "rate limit" in err_str or "429" in err_str:
                            break
                        else:
                            if model == models_to_try[0] and len(models_to_try) > 1:
                                time.sleep(1)
                                continue
            return []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_idx = {executor.submit(process_simple_chunk, text, i): i for i, text in enumerate(chunks)}
            completed = 0
            ordered_results = {}
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                ordered_results[idx] = future.result()
                completed += 1
                progress_bar.progress(completed / len(chunks))
        
        status_text.empty()
        progress_bar.empty()
        
        all_users = []
        for i in sorted(ordered_results.keys()):
            all_users.extend(ordered_results[i])
        
        raw_df = pd.DataFrame(all_users)
        return _merge_duplicate_users(raw_df, pass_prefix=pass_prefix)

    except Exception as e:
        log.error("Exception in openai_extract_users", exc_info=True)
        st.error(f"AI Extraction Error: {str(e)[:200]}")
        return None

def apply_ai_smart_context(df, command, api_key):
    """
    Applies natural language commands to the user dataframe using AI.
    Includes: 60s timeout, exponential-backoff retry, column allowlist guard.
    """
    api_key_str = str(api_key).strip()
    if api_key_str.startswith("AIzaSy"):
        client = OpenAI(
            api_key=api_key_str,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
        )
        model = "gemini-2.5-flash"
    else:
        client = OpenAI(api_key=api_key_str)
        model = "gpt-4o-mini"

    # Context size guard: truncate rows if JSON would be too large
    context_df = df
    context_json = context_df.to_json(orient='records')
    if len(context_json) > _MAX_AI_CONTEXT_KB * 1024:
        # Send only first 200 rows and warn
        context_df = df.head(200)
        context_json = context_df.to_json(orient='records')
        st.warning("⚠️ Dataset is large — AI command applied to first 200 rows only.")

    prompt = f"""
    You are a User Master Data Expert. The user wants to modify the following staff list.

    USER COMMAND: {command}

    CURRENT DATA (JSON):
    {context_json}

    INSTRUCTIONS:
    1. Understand the user's request (e.g., "Set role to X for all users in Y").
    2. Respond ONLY with a valid JSON list of objects representing the UPDATED rows.
    3. Each object MUST contain the '#' (serial number) to identify the row and ONLY the fields that changed.
    4. If the user wants to "Delete" or "Remove", return a field "::action": "delete" for those rows.

    FORMAT EXAMPLE:
    [{{"#": 1, "roles": "Admin|Doctor"}}, {{"#": 5, "isEnabled": "No"}}]
    """

    last_error = "Unknown error"
    for attempt in range(_AI_RETRY_ATTEMPTS):
        try:
            completion = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a data patching engine. Return ONLY JSON."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                timeout=60,
            )

            raw_res = completion.choices[0].message.content
            if not raw_res or not raw_res.strip():
                last_error = "AI returned an empty response."
                time.sleep(_AI_RETRY_BASE_WAIT * (2 ** attempt))
                continue

            res_data = json.loads(raw_res)

            # Normalise: AI may return {"updates": [...]} or bare list
            updates = res_data.get('updates', res_data) if isinstance(res_data, dict) else res_data
            if not isinstance(updates, list):
                last_error = "AI returned invalid format (expected a JSON list)."
                break

            # Apply updates with column allowlist guard
            new_df = df.copy()
            affected = 0
            blocked_fields = set()
            
            # Safety: Prevent mass-hallucination (If AI tries to change > 80% of rows)
            if len(updates) > len(df) * 0.8 and len(df) > 10:
                 return None, "⚠️ AI suggested a mass-change of >80% of your data. Operation blocked for safety."

            for update in updates:
                if '#' not in update:
                    continue
                idx = new_df[new_df['#'] == update['#']].index
                if idx.empty:
                    continue
                row_i = idx[0]
                for field, val in update.items():
                    if field == '#':
                        continue
                    if field not in _AI_ALLOWED_EDIT_COLS:
                        blocked_fields.add(field)   # log but don't apply
                        continue
                    if field in new_df.columns:
                        new_df.at[row_i, field] = val
                        affected += 1

            if blocked_fields:
                log.warning("AI Safety: Blocked hallucinated field(s): %s", blocked_fields)

            summary = f"AI applied changes to {len(updates)} row(s) ({affected} cell update(s))."
            if blocked_fields:
                summary += f" ⚠️ Blocked invalid field(s): {', '.join(sorted(blocked_fields))}."
            return new_df, summary

        except json.JSONDecodeError as e:
            last_error = f"AI returned malformed JSON: {e}"
            log.warning("Smart Context attempt %d JSONDecodeError: %s", attempt + 1, e)
            break   # No point retrying a parse error

        except Exception as e:
            err_str = str(e)
            last_error = err_str[:200]
            log.warning("Smart Context attempt %d %s: %s", attempt + 1, type(e).__name__, err_str)
            # Rate limit or transient: back off and retry
            if "429" in err_str or "timeout" in err_str.lower() or "connection" in err_str.lower():
                wait = _AI_RETRY_BASE_WAIT * (2 ** attempt)
                log.info("Retrying in %ds...", wait)
                time.sleep(wait)
                continue
            break  # Non-retryable error

    return None, f"AI command failed after {_AI_RETRY_ATTEMPTS} attempt(s): {last_error}"
