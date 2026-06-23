USER_MASTER_COLS = [
    "userName", "password", "departments", "roles", "units", "locations", "email", 
    "phone", "employeeId", "firstName", "middleName", "lastName", "designation", 
    "timezone", "shiftDuration", "thirdPartyUsername", "dateOfJoining", 
    "lastWorkingDate", "reportingTo", "isEnabled", "passwordPolicy"
]

SEMANTIC_MAPPINGS = {
    'userName': ['user name', 'username', 'login name', 'emp name'],
    'employeeId': ['emp id', 'employee id', 'employee no', 'staff code', 'associate id', 'uhid', 'id no', 'staff id', 'user id', 'login id', 'e_id', 'e id', 'eid'],
    'firstName': ['first name', 'fname', 'name 1'],
    'middleName': ['middle name', 'mname', 'mid name'],
    'lastName': ['last name', 'lname', 'surname', 'family name', 'name 2'],
    'email': ['e-mail', 'mail id', 'official email', 'email address'],
    'phone': ['contact', 'mobile', 'mobile no', 'cell', 'telephone', 'phone number', 'personal phone'],
    'departments': ['department', 'departments', 'dept', 'department name', 'specialty', 'cost center'],
    'designation': ['position', 'rank', 'job title', 'role name', 'category'],
    'isEnabled': ['enabled', 'status', 'active', 'is active', 'user status'],
    'roles': ['role', 'roles', 'user role', 'user roles', 'access', 'privilege'],
    'units': ['unit', 'units', 'facility', 'hospital', 'branch'],
    'locations': ['location', 'locations', 'site'],
    'thirdPartyUsername': ['third party/ ad username', 'third party username', 'ad username', 'third party/']
}

# ── Tick-mark detection: values that indicate a role/checkbox is "ticked" ──────
TICK_VALUES = frozenset({'yes', 'y', 'x', '1', 'true', 'v', '\u221a', '\u2713', '\u2714', '\u2611'})

# ── Negative values for role-matrix columns (module|SubRole style) ────────────
ROLE_NEGATIVE_VALUES = frozenset({'', 'nan', 'none', '-', 'no', 'false', '0'})
