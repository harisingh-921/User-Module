# user_masters/tests/test_core.py
import pytest
import pandas as pd

from validation.validator import validate_master_data
from extraction.merge import _merge_duplicate_users
from extraction.utils import find_matching_excel_roles

def test_validate_master_data_empty():
    """Verify empty DataFrame returns no errors or warnings."""
    df = pd.DataFrame()
    errors, warnings = validate_master_data(df)
    assert errors == []
    assert warnings == []

def test_validate_master_data_valid():
    """Verify clean DataFrame passes validation."""
    data = [
        {"#": 1, "userName": "johndoe", "email": "john@example.com", "mobile": "+123456789"},
        {"#": 2, "userName": "janesmith", "email": "jane@example.com", "mobile": "9876543210"}
    ]
    df = pd.DataFrame(data)
    errors, warnings = validate_master_data(df)
    assert errors == []
    assert warnings == []

def test_validate_master_data_missing_username():
    """Verify missing userName returns errors."""
    data = [
        {"#": 1, "userName": "", "email": "john@example.com", "mobile": "+123456789"},
        {"#": 2, "userName": "nan", "email": "jane@example.com", "mobile": "9876543210"},
        {"#": 3, "userName": "-", "email": "test@example.com", "mobile": "9876543210"}
    ]
    df = pd.DataFrame(data)
    errors, warnings = validate_master_data(df)
    assert len(errors) == 3
    assert "Row 1: Missing mandatory **userName**" in errors[0]
    assert "Row 2: Missing mandatory **userName**" in errors[1]
    assert "Row 3: Missing mandatory **userName**" in errors[2]

def test_validate_master_data_invalid_email_and_mobile():
    """Verify invalid email and mobile formatting returns warnings."""
    data = [
        {"#": 1, "userName": "johndoe", "email": "invalid-email", "phone": "short"},
        {"#": 2, "userName": "janesmith", "email": "jane@example.com", "phone": "123"}
    ]
    df = pd.DataFrame(data)
    errors, warnings = validate_master_data(df)
    assert errors == []
    assert len(warnings) == 3
    assert any("Invalid **email** format ('invalid-email')" in w for w in warnings)
    assert any("Invalid **phone** format ('short')" in w for w in warnings)
    assert any("Invalid **phone** format ('123')" in w for w in warnings)

def test_validate_master_data_invalid_roles_spaces():
    """Verify spaces around '|' in roles return validation errors."""
    data = [
        {"#": 1, "userName": "johndoe", "roles": "Admin | Doctor"},
        {"#": 2, "userName": "janesmith", "roles": "Nurse| Admin"},
        {"#": 3, "userName": "bobross", "roles": "Artist |Painter"}
    ]
    df = pd.DataFrame(data)
    errors, warnings = validate_master_data(df)
    assert len(errors) == 3
    assert any("roles** contains invalid spaces around '|'" in err for err in errors)

def test_merge_duplicate_users_by_employee_id():
    """Verify rows with matching employeeId are merged and credentials generated."""
    data = [
        {"employeeId": "EMP001", "firstName": "John", "lastName": "Doe", "roles": "Admin", "email": "john@example.com"},
        {"employeeId": "EMP001", "firstName": "John", "lastName": "Doe", "roles": "Doctor", "mobile": "1234567890"}
    ]
    df = pd.DataFrame(data)
    merged_df = _merge_duplicate_users(df, pass_prefix="TestPass")
    
    assert len(merged_df) == 1
    user = merged_df.iloc[0]
    assert user["userName"] == "johndoe"
    assert user["password"] == "TestPass@EMP001"
    assert user["email"] == "john@example.com"
    assert user["mobile"] == "1234567890"
    
    # Combined roles
    roles = user["roles"].split("|")
    assert "Admin" in roles
    assert "Doctor" in roles

def test_merge_duplicate_users_by_email():
    """Verify duplicate merge groups by email when employee ID is missing."""
    data = [
        {"employeeId": "", "firstName": "Jane", "lastName": "Smith", "roles": "Nurse", "email": "jane@example.com"},
        {"employeeId": "-", "firstName": "Jane", "lastName": "Smith", "roles": "Admin", "email": "jane@example.com"}
    ]
    df = pd.DataFrame(data)
    merged_df = _merge_duplicate_users(df, pass_prefix="TestPass")
    
    assert len(merged_df) == 1
    user = merged_df.iloc[0]
    assert user["userName"] == "janesmith"
    assert user["password"] == ""  # blank because employeeId is missing
    roles = user["roles"].split("|")
    assert "Nurse" in roles
    assert "Admin" in roles

def test_find_matching_excel_roles():
    """Verify tick role overrides match correctly by ID, email, and userName."""
    excel_rows_data = [
        {"roles": "Admin|Doctor", "raw_values": ["emp001", "john@example.com", "johndoe"]},
        {"roles": "Nurse", "raw_values": ["emp002", "jane@example.com", "janesmith"]}
    ]
    
    # Match by ID
    user1 = {"employeeId": "EMP001", "email": "", "userName": ""}
    assert find_matching_excel_roles(user1, excel_rows_data) == "Admin|Doctor"
    
    # Match by email
    user2 = {"employeeId": "", "email": "jane@example.com", "userName": ""}
    assert find_matching_excel_roles(user2, excel_rows_data) == "Nurse"
    
    # Fallback to existing roles if not found
    user3 = {"employeeId": "EMP999", "email": "none@example.com", "userName": "guest", "roles": "GuestRole"}
    assert find_matching_excel_roles(user3, excel_rows_data) == "GuestRole"
