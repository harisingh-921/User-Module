USER_MASTER_COLS = [
    "userName", "password", "departments", "roles", "units", "locations", "email", 
    "phone", "employeeId", "firstName", "middleName", "lastName", "designation", 
    "timezone", "shiftDuration", "thirdPartyUsername", "dateOfJoining", 
    "lastWorkingDate", "reportingTo", "isEnabled", "passwordPolicy"
]

SEMANTIC_MAPPINGS = {
    'userName': ['user name', 'username', 'login name', 'user login id', 'login id', 'user id'],
    'employeeId': ['emp id', 'employee id', 'employee no', 'staff code', 'associate id', 'uhid', 'id no', 'staff id'],
    'departments': ['department', 'departments', 'dept', 'department name', 'specialty', 'unit', 'cost center', 'branch', 'facility'],
    'firstName': ['first name', 'fname', 'given name', 'name 1', 'employee name', 'emp name', 'staff name', 'full name', 'name'],
    'lastName': ['last name', 'lname', 'surname', 'family name', 'name 2'],
    'email': ['e-mail', 'mail id', 'official email', 'email address'],
    'phone': ['contact', 'mobile', 'mobile no', 'cell', 'telephone', 'phone number', 'personal phone'],
    'designation': ['position', 'rank', 'job title', 'role name', 'category'],
    'isEnabled': ['enabled', 'status', 'active', 'is active', 'user status'],
    'roles': ['role', 'roles', 'user role', 'user roles', 'access', 'privilege'],
    'units': ['unit', 'units', 'facility', 'hospital', 'branch'],
    'locations': ['location', 'locations', 'site'],
    'thirdPartyUsername': ['third party/ ad username', 'third party username', 'ad username', 'third party/']
}
