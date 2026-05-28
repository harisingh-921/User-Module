USER_MASTER_COLS = [
    "userName", "password", "departments", "roles", "units", "locations", "email", 
    "mobile", "employeeId", "firstName", "middleName", "lastName", "designation", 
    "timezone", "shiftDuration", "thirdPartyUsername", "dateOfJoining", 
    "lastWorkingDate", "reportingTo", "isEnabled"
]

SEMANTIC_MAPPINGS = {
    'employeeId': ['emp id', 'employee no', 'staff code', 'associate id', 'uhid', 'id no', 'serial no', 'sl no', 'staff id'],
    'departments': ['dept', 'department name', 'specialty', 'unit', 'cost center', 'branch', 'facility'],
    'firstName': ['first name', 'fname', 'given name', 'name 1'],
    'lastName': ['last name', 'lname', 'surname', 'family name', 'name 2'],
    'email': ['e-mail', 'mail id', 'official email', 'email address'],
    'mobile': ['contact', 'phone', 'mobile no', 'cell', 'telephone'],
    'designation': ['position', 'rank', 'job title', 'role name', 'category']
}
