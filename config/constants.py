USER_MASTER_COLS = [
    "userName", "password", "departments", "roles", "units", "locations", "email", 
    "phone", "employeeId", "firstName", "middleName", "lastName", "designation", 
    "timezone", "shiftDuration", "thirdPartyUsername", "dateOfJoining", 
    "lastWorkingDate", "reportingTo", "isEnabled", "passwordPolicy"
]

SEMANTIC_MAPPINGS = {
    'employeeId': ['emp id', 'employee no', 'staff code', 'associate id', 'uhid', 'id no', 'serial no', 'sl no', 'staff id'],
    'departments': ['department', 'departments', 'dept', 'department name', 'specialty', 'unit', 'cost center', 'branch', 'facility'],
    'firstName': ['first name', 'fname', 'given name', 'name 1'],
    'lastName': ['last name', 'lname', 'surname', 'family name', 'name 2'],
    'email': ['e-mail', 'mail id', 'official email', 'email address'],
    'phone': ['contact', 'mobile', 'mobile no', 'cell', 'telephone', 'phone number', 'personal phone'],
    'designation': ['position', 'rank', 'job title', 'role name', 'category']
}
