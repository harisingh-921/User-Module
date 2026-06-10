import pandas as pd
import re

USER_MASTER_COLS = [
    "userName", "password", "departments", "roles", "units", "locations", "email", 
    "phone", "employeeId", "firstName", "middleName", "lastName", "designation", 
    "timezone", "shiftDuration", "thirdPartyUsername", "dateOfJoining", 
    "lastWorkingDate", "reportingTo", "isEnabled", "passwordPolicy"
]

SEMANTIC_MAPPINGS = {
    'userName': ['user name', 'username', 'login name'],
    'employeeId': ['emp id', 'employee id', 'employee no', 'staff code', 'associate id', 'uhid', 'id no', 'staff id', 'user login id', 'login id', 'user id'],
    'departments': ['department', 'departments', 'dept', 'department name', 'specialty', 'unit', 'cost center', 'branch', 'facility'],
    'firstName': ['first name', 'fname', 'given name', 'name 1', 'employee name', 'emp name', 'staff name', 'full name', 'name'],
    'lastName': ['last name', 'lname', 'surname', 'family name', 'name 2'],
    'email': ['e-mail', 'mail id', 'official email', 'email address'],
    'phone': ['contact', 'mobile', 'mobile no', 'cell', 'telephone', 'phone number', 'personal phone', 'phone'],
    'designation': ['position', 'rank', 'job title', 'role name', 'category'],
    'isEnabled': ['enabled', 'status', 'active', 'is active', 'user status'],
    'roles': ['role', 'roles', 'user role', 'user roles', 'access', 'privilege'],
    'units': ['unit', 'units', 'facility', 'hospital', 'branch'],
    'locations': ['location', 'locations', 'site'],
    'thirdPartyUsername': ['third party/ ad username', 'third party username', 'ad username', 'third party/']
}

def format_to_template(df: pd.DataFrame, is_new: bool = False) -> pd.DataFrame:
    df = df.copy()
    fallbacks = SEMANTIC_MAPPINGS
    
    # helper for checking empty
    def is_empty_series(s):
        # Check if the series has any non-empty value
        def has_val(val):
            if pd.isna(val):
                return False
            return str(val).strip().lower() not in ('', 'nan', 'none', '-', 'na', 'n/a')
        return not s.apply(has_val).any()
    
    for col in USER_MASTER_COLS:
        is_empty_col = False
        if col in df.columns:
            if is_empty_series(df[col]):
                is_empty_col = True
                
        if col not in df.columns or is_empty_col:
            found = False
            if col in fallbacks:
                for fb in fallbacks[col]:
                    matching_cols = [c for c in df.columns if str(c).strip().lower() == fb]
                    if matching_cols:
                        candidate_col = matching_cols[0]
                        if not is_empty_series(df[candidate_col]):
                            df[col] = df[candidate_col]
                            found = True
                            break
            if not found and col not in df.columns:
                df[col] = ''
                
    # Clean userName for new users: lowercase, no spaces, no special characters
    if is_new and 'userName' in df.columns:
        def clean_new_username(row):
            uname = str(row.get('userName', '')).strip()
            if pd.isna(row.get('userName', '')) or uname.lower() in ('', 'nan', 'none', '-', 'na', 'n/a'):
                fn = str(row.get('firstName', '')).strip()
                mn = str(row.get('middleName', '')).strip()
                ln = str(row.get('lastName', '')).strip()
                parts = []
                for name_part in [fn, mn, ln]:
                    if pd.notna(name_part) and name_part.lower() not in ('', 'nan', 'none', '-', 'na', 'n/a'):
                        parts.append(name_part)
                full_name = "".join(parts)
                uname = full_name
            cleaned = re.sub(r'[^a-zA-Z0-9]', '', uname).lower()
            return cleaned
        df['userName'] = df.apply(clean_new_username, axis=1)

    if is_new and 'isEnabled' in df.columns:
        df['isEnabled'] = df['isEnabled'].apply(
            lambda x: 'Yes' if pd.isna(x) or str(x).strip().lower() in ('', 'nan', 'none', '-', 'na', 'n/a') else x
        )

    final_cols = USER_MASTER_COLS.copy()
    return df[final_cols]

# Simulate client file columns: no "User ID" column, just "Employee ID" (which maps to employeeId)
test_df = pd.DataFrame([
    {
        "userName": "PARVESH KUMAR",
        "Employee ID": "PK-PAN-00014",
        "password": "Paras@123",
        "departments": "ENGINEERING",
        "roles": "INCIDENT REPORTER",
        "units": "Panchkula",
        "Phone": "9465702447"
    }
])

print("Columns before format:", test_df.columns.tolist())
formatted = format_to_template(test_df, is_new=True)
print("Formatted dataframe:")
print(formatted[["userName", "firstName", "lastName", "employeeId", "phone", "isEnabled"]].to_dict('records'))

