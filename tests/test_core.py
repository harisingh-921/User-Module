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
        {"#": 1, "userName": "johndoe", "email": "john@example.com", "phone": "+123456789"},
        {"#": 2, "userName": "janesmith", "email": "jane@example.com", "phone": "9876543210"}
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
        {"employeeId": "EMP001", "firstName": "John", "lastName": "Doe", "roles": "Doctor", "phone": "1234567890"}
    ]
    df = pd.DataFrame(data)
    merged_df = _merge_duplicate_users(df, pass_prefix="TestPass")
    
    assert len(merged_df) == 1
    user = merged_df.iloc[0]
    assert user["userName"] == "johndoe"
    assert user["password"] == "TestPass@EMP001"
    assert user["email"] == "john@example.com"
    assert user["phone"] == "1234567890"
    
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

def test_segregation_password_prefix():
    """Verify that segregation format_segregation_results applies pass_prefix to new users without passwords."""
    import streamlit as st
    st.session_state['pass_prefix'] = "SegPrefix"
    
    from segregation.export import format_segregation_results
    
    # Create mock client df
    client_data = [
        # Existing User (should not get pass_prefix password generation)
        {"User Type": "Existing User", "employeeId": "EMP101", "password": "", "userName": "exuser", "roles": "Admin"},
        # New User with existing password (should keep existing password)
        {"User Type": "New User", "employeeId": "EMP102", "password": "ClientPass123", "userName": "newuser1", "roles": "Doctor"},
        # New User with empty password (should generate password)
        {"User Type": "New User", "employeeId": "EMP103", "password": "", "userName": "newuser2", "roles": "Nurse"}
    ]
    client_df = pd.DataFrame(client_data)
    
    results = format_segregation_results(client_df)
    
    existing_df = results['Existing Users']
    new_df = results['New Users']
    
    # Check existing user did NOT get password generated
    assert existing_df.loc[existing_df['userName'] == 'exuser', 'password'].values[0] == ''
    
    # Check new user with client password kept client password
    assert new_df.loc[new_df['userName'] == 'newuser1', 'password'].values[0] == 'ClientPass123'
    
    # Check new user with empty password got SegPrefix@EMP103
    assert new_df.loc[new_df['userName'] == 'newuser2', 'password'].values[0] == 'SegPrefix@EMP103'

def test_merge_preserves_provided_credentials():
    """Verify that _merge_duplicate_users preserves client-provided userName and password."""
    data = [
        {
            "employeeId": "EMP201",
            "firstName": "John",
            "lastName": "Doe",
            "userName": "johndoe_custom",
            "password": "CustomPassword123",
            "roles": "Admin"
        }
    ]
    df = pd.DataFrame(data)
    merged_df = _merge_duplicate_users(df, pass_prefix="TestPass")
    
    assert len(merged_df) == 1
    user = merged_df.iloc[0]
    assert user["userName"] == "johndoecustom"
    assert user["password"] == "CustomPassword123"
    assert user["isEnabled"] == "Yes"


def test_detect_duplicates_in_df():
    """Verify that detect_duplicates_in_df correctly flags exact clones and username collisions."""
    from utils.common import detect_duplicates_in_df
    
    data = [
        # Exact duplicate clone rows
        {"firstName": "John", "lastName": "Doe", "userName": "johndoe", "email": "john@example.com"},
        {"firstName": "John", "lastName": "Doe", "userName": "johndoe", "email": "john@example.com"},
        # Username collision but not exact clone (different email)
        {"firstName": "John", "lastName": "Smith", "userName": "johndoe", "email": "jsmith@example.com"},
        # Unique row
        {"firstName": "Jane", "lastName": "Smith", "userName": "janesmith", "email": "jane@example.com"}
    ]
    df = pd.DataFrame(data)
    flagged_df = detect_duplicates_in_df(df)
    
    # Check exact clone rows
    assert flagged_df.loc[0, "_is_duplicate_user"] == True
    assert flagged_df.loc[1, "_is_duplicate_user"] == True
    assert flagged_df.loc[2, "_is_duplicate_user"] == False
    assert flagged_df.loc[3, "_is_duplicate_user"] == False
    
    # Check username collisions (johndoe is used in row 0, 1, and 2)
    assert flagged_df.loc[0, "_is_duplicate_username"] == True
    assert flagged_df.loc[1, "_is_duplicate_username"] == True
    assert flagged_df.loc[2, "_is_duplicate_username"] == True
    assert flagged_df.loc[3, "_is_duplicate_username"] == False


def test_merge_combines_units_and_departments():
    """Verify that _merge_duplicate_users merges records and combines different units/departments via pipes."""
    data = [
        {
            "employeeId": "EMP999",
            "firstName": "Ram",
            "lastName": "Prasad Golli",
            "userName": "ramprasadgolli",
            "units": "Health city",
            "departments": "Quality"
        },
        {
            "employeeId": "EMP999",
            "firstName": "Ram",
            "lastName": "Prasad Golli",
            "userName": "ramprasadgolli",
            "units": "Ram Nagar",
            "departments": "Accreditation"
        }
    ]
    df = pd.DataFrame(data)
    merged_df = _merge_duplicate_users(df)
    
    assert len(merged_df) == 1
    user = merged_df.iloc[0]
    
    # Verify units are pipe-separated
    units = user["units"].split("|")
    assert "Health city" in units
    assert "Ram Nagar" in units
    
    # Verify departments are pipe-separated
    depts = user["departments"].split("|")
    assert "Quality" in depts
    assert "Accreditation" in depts


def test_merge_expands_all_departments():
    """Verify that _merge_duplicate_users replaces 'All' departments with a combination of all unique departments."""
    data = [
        {"employeeId": "EMP001", "firstName": "User1", "departments": "Nursing"},
        {"employeeId": "EMP002", "firstName": "User2", "departments": "Cathlab"},
        {"employeeId": "EMP003", "firstName": "User3", "departments": "All"}
    ]
    df = pd.DataFrame(data)
    merged_df = _merge_duplicate_users(df)
    
    # User3 should have departments: "Nursing|Cathlab" (or "Cathlab|Nursing")
    user3 = merged_df[merged_df["employeeId"] == "EMP003"].iloc[0]
    depts = user3["departments"].split("|")
    assert len(depts) == 2
    assert "Nursing" in depts
    assert "Cathlab" in depts


def test_apply_ai_smart_context_replace_intent():
    from unittest.mock import MagicMock, patch
    from ai.extraction import apply_ai_smart_context
    from models.schemas import AISmartResponse, ReplaceIntent

    df = pd.DataFrame([
        {"#": 1, "userName": "johndoe", "roles": "Admin|INCIDENT REPORTER"},
        {"#": 2, "userName": "janesmith", "roles": "User|INCIDENT REPORTER"}
    ])

    mock_response = MagicMock()
    mock_parsed = AISmartResponse(
        replace_intent=ReplaceIntent(
            target_col="roles",
            search_text="INCIDENT REPORTER",
            replace_text="Incident Reporter"
        )
    )
    mock_response.choices[0].message.parsed = mock_parsed

    with patch("ai.extraction.OpenAI") as mock_openai:
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        mock_client.chat.completions.parse.return_value = mock_response

        result_df, summary = apply_ai_smart_context(df, "replace INCIDENT REPORTER with Incident Reporter", "mock-key")

        assert "programmatically replaced" in summary
        assert result_df.loc[0, "roles"] == "Admin|Incident Reporter"
        assert result_df.loc[1, "roles"] == "User|Incident Reporter"


def test_apply_ai_smart_context_updates_preserves_other_values():
    from unittest.mock import MagicMock, patch
    from ai.extraction import apply_ai_smart_context
    from models.schemas import AISmartResponse, RowUpdate

    df = pd.DataFrame([
        {"#": 36, "userName": "testuser", "roles": "Audit Incharge|Incident Reporter|QI Viewer"}
    ])

    mock_response = MagicMock()
    mock_parsed = AISmartResponse(
        updates=[
            RowUpdate(
                **{"#": 36},
                roles="Audit Incharge|Incident Reporter|QI Viewer|NewRole"
            )
        ]
    )
    mock_response.choices[0].message.parsed = mock_parsed

    with patch("ai.extraction.OpenAI") as mock_openai:
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        mock_client.chat.completions.parse.return_value = mock_response

        result_df, summary = apply_ai_smart_context(df, "Add NewRole to row 36 roles", "mock-key")

        assert "applied changes" in summary
        assert result_df.loc[0, "roles"] == "Audit Incharge|Incident Reporter|QI Viewer|NewRole"


def test_verify_extracted_user_source_valid():
    from ai.extraction import verify_extracted_user_source
    raw_text = "Name: John Doe, Email: john.doe@example.com, Emp ID: EMP101, Username: jdoe101"
    
    # Valid exact match
    user_dict_1 = {
        "firstName": "John",
        "lastName": "Doe",
        "email": "john.doe@example.com",
        "employeeId": "EMP101",
        "userName": "jdoe101"
    }
    assert verify_extracted_user_source(user_dict_1, raw_text) is True

    # Case-insensitive match and trailing/leading space checks
    user_dict_2 = {
        "firstName": "  john  ",
        "lastName": "DOE",
        "email": "JOHN.DOE@example.com",
        "employeeId": "emp101",
        "userName": "JDOE101"
    }
    assert verify_extracted_user_source(user_dict_2, raw_text) is True

    # Non-string representation check
    user_dict_3 = {
        "firstName": "John",
        "lastName": None,
        "email": "-",
        "employeeId": "EMP101",
        "userName": ""
    }
    assert verify_extracted_user_source(user_dict_3, raw_text) is True


def test_verify_extracted_user_source_hallucinated():
    from ai.extraction import verify_extracted_user_source
    raw_text = "Name: John Doe, Email: john.doe@example.com, Emp ID: EMP101, Username: jdoe101"

    # Fails Person Validation Rule (all blank/None/empty)
    user_dict_empty = {
        "firstName": "",
        "lastName": "",
        "email": "-",
        "employeeId": "  ",
        "userName": None
    }
    assert verify_extracted_user_source(user_dict_empty, raw_text) is False

    # Hallucinated firstName
    user_dict_hallucinated_first = {
        "firstName": "Alice",
        "lastName": "Doe",
        "email": "john.doe@example.com",
        "employeeId": "EMP101",
        "userName": "jdoe101"
    }
    assert verify_extracted_user_source(user_dict_hallucinated_first, raw_text) is False

    # Hallucinated lastName
    user_dict_hallucinated_last = {
        "firstName": "John",
        "lastName": "Smith",
        "email": "john.doe@example.com",
        "employeeId": "EMP101",
        "userName": "jdoe101"
    }
    assert verify_extracted_user_source(user_dict_hallucinated_last, raw_text) is False

    # Hallucinated employeeId
    user_dict_hallucinated_emp = {
        "firstName": "John",
        "lastName": "Doe",
        "email": "john.doe@example.com",
        "employeeId": "EMP999",
        "userName": "jdoe101"
    }
    assert verify_extracted_user_source(user_dict_hallucinated_emp, raw_text) is False

    # Hallucinated email
    user_dict_hallucinated_email = {
        "firstName": "John",
        "lastName": "Doe",
        "email": "alice@example.com",
        "employeeId": "EMP101",
        "userName": "jdoe101"
    }
    assert verify_extracted_user_source(user_dict_hallucinated_email, raw_text) is False

    # Hallucinated userName
    user_dict_hallucinated_username = {
        "firstName": "John",
        "lastName": "Doe",
        "email": "john.doe@example.com",
        "employeeId": "EMP101",
        "userName": "alicedoe"
    }
    assert verify_extracted_user_source(user_dict_hallucinated_username, raw_text) is False


def test_cross_examine_extracted_users():
    from unittest.mock import MagicMock
    from ai.extraction import cross_examine_extracted_users
    from models.schemas import VerificationResult

    # Mock client and response structure
    mock_client = MagicMock()
    mock_parsed_clean = VerificationResult(is_hallucinated=False, reason=None)
    mock_response_clean = MagicMock()
    mock_response_clean.choices[0].message.parsed = mock_parsed_clean
    mock_client.chat.completions.parse.return_value = mock_response_clean

    raw_text = "John Doe, EMP101"
    extracted_users = [{"firstName": "John", "lastName": "Doe", "employeeId": "EMP101"}]

    # Case 1: Valid batch (cross-examination returns is_hallucinated=False)
    res_clean = cross_examine_extracted_users(mock_client, "gpt-4o-mini", raw_text, extracted_users)
    assert res_clean is True

    # Case 2: Hallucinated batch (cross-examination returns is_hallucinated=True)
    mock_parsed_hallucinated = VerificationResult(is_hallucinated=True, reason="Alice Smith does not exist in the source")
    mock_response_hallucinated = MagicMock()
    mock_response_hallucinated.choices[0].message.parsed = mock_parsed_hallucinated
    mock_client.chat.completions.parse.return_value = mock_response_hallucinated

    res_hallucinated = cross_examine_extracted_users(mock_client, "gpt-4o-mini", raw_text, extracted_users)
    assert res_hallucinated is False

    # Case 3: Empty extracted_users list should bypass and return True immediately without LLM call
    mock_client.reset_mock()
    assert cross_examine_extracted_users(mock_client, "gpt-4o-mini", raw_text, []) is True
    mock_client.chat.completions.parse.assert_not_called()

    # Case 4: Exception scenario - should catch and return True (fallback)
    mock_client.chat.completions.parse.side_effect = Exception("API connection error")
    res_exception = cross_examine_extracted_users(mock_client, "gpt-4o-mini", raw_text, extracted_users)
    assert res_exception is True


def test_enforce_contract_type_safety():
    from models.dataframe_contract import enforce_contract
    import numpy as np
    
    # Test data frame with various mixed/numeric types
    data = {
        "phone": [9376950533, "8521766053", 9588060430.0, np.nan, None],
        "employeeId": [1035605, "EMP002", np.nan, None, 12345.0],
        "userName": ["testuser", "nan", None, "None", "normal"]
    }
    df = pd.DataFrame(data)
    result = enforce_contract(df)
    
    # Assert type normalization to string
    assert result.at[0, "phone"] == "9376950533"
    assert result.at[1, "phone"] == "8521766053"
    assert result.at[2, "phone"] == "9588060430"
    assert result.at[3, "phone"] == ""
    assert result.at[4, "phone"] == ""
    
    assert result.at[0, "employeeId"] == "1035605"
    assert result.at[1, "employeeId"] == "EMP002"
    assert result.at[2, "employeeId"] == ""
    assert result.at[3, "employeeId"] == ""
    assert result.at[4, "employeeId"] == "12345"
    
    assert result.at[0, "userName"] == "testuser"
    assert result.at[1, "userName"] == ""
    assert result.at[2, "userName"] == ""
    assert result.at[3, "userName"] == ""
    assert result.at[4, "userName"] == "normal"


def test_ignore_suggested_columns():
    from extraction.local import local_extract_users
    
    csv_data = (
        "Employee Name,Suggested UserName,Audit User,employeeId,email,phone\n"
        "Sarita Sharma,saritasharma1,Audit User - CES,1035605,sarita@example.com,9876543210\n"
    )
    file_bytes = csv_data.encode("utf-8")
    
    df = local_extract_users(file_bytes, "test.csv")
    
    assert len(df) == 1
    user = df.iloc[0]
    assert user["firstName"] == "Sarita"
    assert user["lastName"] == "Sharma"
    assert user["roles"] == "Audit User - CES"
    assert user["userName"] == "saritasharma"
    assert user["employeeId"] == "1035605"


def test_designation_not_mapped_as_username():
    from extraction.local import local_extract_users
    
    csv_data = (
        "User Name,User Name|First Name,User Name|Last Name,User Name|Designation,User Name|Employee Id,User Name|Email,User Name|Mobile\n"
        "Jaipur,Vidhya,Kanwar,ICN,221020,icn.jaipur@fortishealthcare.com | vidhya.kanwar@FORTISHEALTHCARE.COM,9376950533 |7023701893\n"
    )
    file_bytes = csv_data.encode("utf-8")
    
    df = local_extract_users(file_bytes, "test.csv")
    
    user = df.iloc[0]
    assert user["firstName"] == "Vidhya"
    assert user["lastName"] == "Kanwar"
    assert user["designation"] == "ICN"
    assert "icn" not in user["userName"]


def test_no_merge_different_employee_ids():
    from extraction.merge import _merge_duplicate_users
    
    data = [
        {"userName": "icn", "firstName": "Vidhya", "employeeId": "221020", "email": "icn.jaipur@fortis.com"},
        {"userName": "icn", "firstName": "Sarita", "employeeId": "180783", "email": "icn.jaipur@fortis.com"}
    ]
    df = pd.DataFrame(data)
    merged_df = _merge_duplicate_users(df)
    
    assert len(merged_df) == 2
    users = merged_df["firstName"].tolist()
    assert "Vidhya" in users
    assert "Sarita" in users


def test_segregation_full_name_fallback():
    """Verify format_segregation_results does NOT split Employee Name and fields remain empty."""
    from segregation.export import format_segregation_results
    
    client_data = [
        {
            "User Type": "New User",
            "Employee ID": "EMP999",
            "Employee Name": "Rohit Kumar Singh",
            "password": "",
            "departments": "IT",
            "roles": "Admin",
            "units": "Delhi",
            "locations": ""
        }
    ]
    client_df = pd.DataFrame(client_data)
    
    priority_mappings = [
        {"name": "Employee ID", "client_col": "Employee ID", "master_col": "Employee Id"}
    ]
    
    results = format_segregation_results(client_df, priority_mappings)
    new_users = results['New Users']
    
    assert len(new_users) == 1
    user = new_users.iloc[0]
    assert user["userName"] == "rohitkumarsingh"
    assert user["firstName"] == ""
    assert user["lastName"] == ""


def test_resolve_multi_value_fields_single_row():
    """Verify that multi-value email, phone, and username fields are resolved using the user name."""
    from extraction.local import local_extract_users
    
    csv_data = (
        "User Name,User Name|First Name,User Name|Last Name,User Name|Designation,User Name|Employee Id,User Name|Email,User Name|Mobile\n"
        "Jaipur,Vidhya,Kanwar,ICN,221020,icn.jaipur@fortishealthcare.com | vidhya.kanwar@FORTISHEALTHCARE.COM,9376950533 |7023701893\n"
    )
    file_bytes = csv_data.encode("utf-8")
    df = local_extract_users(file_bytes, "test.csv")
    
    assert len(df) == 1
    user = df.iloc[0]
    assert user["email"] == "vidhya.kanwar@FORTISHEALTHCARE.COM"
    assert user["phone"] == "7023701893"


def test_third_party_username_not_mapped_to_username():
    """Verify that a column containing 'Third Party Username' is mapped to thirdPartyUsername, not userName."""
    from extraction.local import local_extract_users
    
    csv_data = (
        "First Name,Last Name,Employee Id,Email,Mobile,Third Party Username (Name as in email ID)\n"
        "Sarita,,180783,icn.jaipur@fortishealthcare.com | vidhya.kanwar@FORTISHEALTHCARE.COM,9376950533 | 7023701893,icn.jaipur| vidhya.kanwar\n"
    )
    file_bytes = csv_data.encode("utf-8")
    df = local_extract_users(file_bytes, "test.csv")
    
    assert len(df) == 1
    user = df.iloc[0]
    assert user["firstName"] == "Sarita"
    assert user["lastName"] == ""
    assert user["userName"] == "sarita"  # constructed from first/last name
    assert user["thirdPartyUsername"] == "icn.jaipur"  # resolved from the column


def test_tick_marked_role_column_extraction():
    """Verify that tick-marked role columns are correctly processed without raising TypeError."""
    from extraction.local import local_extract_users
    
    csv_data = (
        "First Name,Last Name,Employee Id,Email,Mobile,Audit User,Infection Control\n"
        "John,Doe,EMP001,john@example.com,9876543210,Y,\n"
        "Jane,Smith,EMP002,jane@example.com,9876543211,,Y\n"
    )
    file_bytes = csv_data.encode("utf-8")
    df = local_extract_users(file_bytes, "test.csv")
    
    assert len(df) == 2
    user1 = df[df["employeeId"] == "EMP001"].iloc[0]
    user2 = df[df["employeeId"] == "EMP002"].iloc[0]
    
    assert "Audit User" in user1["roles"].split("|")
    assert "Infection Control" in user2["roles"].split("|")


def test_gemini_client_routing_by_key_prefix():
    """Verify that get_openai_client properly routes Gemini and standard keys."""
    from ai.extraction import get_openai_client
    
    # 1. Gemini Key (starts with AIzaSy)
    gemini_key = "AIzaSyFakeKey12345"
    client_gemini = get_openai_client(gemini_key)
    assert client_gemini is not None
    assert str(client_gemini.base_url) == "https://generativelanguage.googleapis.com/v1beta/openai/"
    
    # 2. Standard OpenAI Key (starts with sk- or anything else)
    openai_key = "sk-fakeopenai12345"
    client_openai = get_openai_client(openai_key)
    assert client_openai is not None
    assert "googleapis.com" not in str(client_openai.base_url)


def test_gemini_model_selection_in_smart_context():
    """Verify that smart context selection uses gemini-1.5-flash when a Gemini key is passed."""
    from unittest.mock import MagicMock, patch
    from ai.extraction import apply_ai_smart_context
    from models.schemas import AISmartResponse
    
    df = pd.DataFrame([
        {"#": 1, "userName": "testuser", "roles": "User"}
    ])
    
    mock_response = MagicMock()
    mock_parsed = AISmartResponse(
        updates=[]
    )
    mock_response.choices[0].message.parsed = mock_parsed
    
    # We patch OpenAI and get_healthy_api_keys
    with patch("ai.extraction.get_healthy_api_keys", return_value=["AIzaSyFakeKey"]):
        with patch("ai.extraction.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_openai.return_value = mock_client
            mock_client.chat.completions.parse.return_value = mock_response
            
            apply_ai_smart_context(df, "do nothing", "AIzaSyFakeKey")
            
            # Assert that the chat completions parse was called with the gemini-1.5-flash model
            mock_client.chat.completions.parse.assert_called_once()
            kwargs = mock_client.chat.completions.parse.call_args[1]
            assert kwargs["model"] == "gemini-1.5-flash"


def test_segregation_existing_user_restricted_merge():
    """Verify that existing users merge only email/phone/roles/departments/units from client, keeping everything else exactly from master."""
    from segregation.export import format_segregation_results
    import pandas as pd
    
    # Existing user with client data having values, but master data having blank names/roles/departments/units
    client_data = [
        {
            "User Type": "Existing User",
            "employeeId": "EMP101",
            "userName": "testuser",
            "firstName": "Dr.",
            "lastName": "Pradeep",
            "email": "drpradeep@example.com",
            "phone": "9876543210",
            "roles": "Admin",
            "departments": "IT",
            "units": "Panchkula",
            "master_employeeId": "EMP101",
            "master_userName": "testuser",
            "master_firstName": "",  # Empty name in master
            "master_lastName": "",   # Empty name in master
            "master_email": "",      # Empty email in master
            "master_phone": "",      # Empty phone in master
            "master_roles": "",      # Empty roles in master
            "master_departments": "", # Empty departments in master
            "master_units": "",       # Empty units in master
        }
    ]
    client_df = pd.DataFrame(client_data)
    
    results = format_segregation_results(client_df)
    existing_users = results['Existing Users']
    
    assert len(existing_users) == 1
    user = existing_users.iloc[0]
    
    # 1. Names and other columns must be kept exactly as blank from master file
    assert user["firstName"] == ""
    assert user["lastName"] == ""
    
    # 2. Email, phone, roles, departments, and units must fallback/merge from client file
    assert user["email"] == "drpradeep@example.com"
    assert user["phone"] == "9876543210"
    assert user["roles"] == "Admin"
    assert user["departments"] == "IT"
    assert user["units"] == "Panchkula"


def test_segregation_existing_user_highlight_flags():
    """Verify that _is_updated_<col> flags are set correctly for merged columns of existing users."""
    from segregation.export import format_segregation_results
    import pandas as pd

    client_data = [
        {
            "User Type": "Existing User",
            "employeeId": "EMP101",
            "userName": "testuser",
            "email": "drpradeep@example.com",  # Fell back (master was empty)
            "phone": "9876543210",           # Identical to master
            "roles": "Admin|Doctor",          # Merged with master role 'Admin' -> new value is Admin|Doctor
            "departments": "IT",             # Fell back (master was empty)
            "units": "",                     # Both empty
            "master_employeeId": "EMP101",
            "master_userName": "testuser",
            "master_email": "",
            "master_phone": "9876543210",
            "master_roles": "Admin",
            "master_departments": "",
            "master_units": "",
        }
    ]
    client_df = pd.DataFrame(client_data)
    results = format_segregation_results(client_df)
    existing_users = results['Existing Users']

    assert len(existing_users) == 1
    user = existing_users.iloc[0]

    # Email was blank in master, populated from client -> updated
    assert user["_is_updated_email"] == True

    # Phone was identical -> not updated
    assert user["_is_updated_phone"] == False

    # Roles was merged (Admin -> Admin|Doctor) -> updated
    assert user["_is_updated_roles"] == True

    # Departments was blank in master, populated from client -> updated
    assert user["_is_updated_departments"] == True

    # Units was blank in both -> not updated
    assert user["_is_updated_units"] == False


def test_segregation_expanded_name_aliases():
    """Verify format_segregation_results maps explicit name columns but does NOT split full name columns."""
    from segregation.export import format_segregation_results
    import pandas as pd

    client_data = [
        {
            "User Type": "New User",
            "Employee ID": "EMP999",
            "first_name": "Rohit",
            "last_name": "Singh",
            "Employee Name": "Rohit Kumar Singh", # Should be ignored (not split)
            "password": "",
            "departments": "IT",
            "roles": "Admin",
            "units": "Delhi",
            "locations": ""
        }
    ]
    client_df = pd.DataFrame(client_data)
    
    results = format_segregation_results(client_df)
    new_users = results['New Users']
    
    assert len(new_users) == 1
    user = new_users.iloc[0]
    
    assert user["firstName"] == "Rohit"
    assert user["lastName"] == "Singh"
    assert user["userName"] == "rohitsingh"


def test_segregation_new_user_preserve_client_fields():
    """Verify that new users' fields (userName, firstName, lastName) are preserved from explicit client fields and not split from full name columns."""
    from segregation.export import format_segregation_results
    import pandas as pd

    client_data = [
        {
            "User Type": "New User",
            "Employee ID": "EMP999",
            "Employee Name": "Dr. Amit Kumar Patel", # Should not be split, firstName/lastName remain empty since not explicitly provided
            "userName": "amitpatel",
            "password": "",
            "departments": "Emergency",
            "roles": "INCIDENT",
            "units": "Ranchi",
            # Simulate master columns being present in the combined dataframe
            "master_userName": "amitpatel",
            "master_firstName": "Amit",
            "master_lastName": "Patel",
            "master_employeeId": "EMP999"
        }
    ]
    client_df = pd.DataFrame(client_data)
    results = format_segregation_results(client_df)
    new_users = results['New Users']

    assert len(new_users) == 1
    user = new_users.iloc[0]

    assert user["firstName"] == ""
    assert user["lastName"] == ""
    assert user["userName"] == "amitpatel"
    assert user["departments"] == "Emergency"
    assert user["units"] == "Ranchi"


def test_segregation_username_fallback_from_employee_name():
    """Verify that format_segregation_results generates userName from Employee Name and keeps firstName/lastName blank."""
    from segregation.export import format_segregation_results
    import pandas as pd

    client_data = [
        {
            "User Type": "New User",
            "User Login ID": "RN-RAN-00034",
            "Employee Name": "Loknath Sahu",
            "password": "Paras@123",
            "departments": "Finance_and_Account",
            "email": "loknath.sahu@parashospital",
            "mobile": "9534185264",
            "roles": "INCIDENT",
            "units": "Ranchi"
        }
    ]
    client_df = pd.DataFrame(client_data)
    
    priority_mappings = [
        {"name": "Employee ID", "client_col": "User Login ID", "master_col": "Employee Id"}
    ]
    
    results = format_segregation_results(client_df, priority_mappings)
    new_users = results['New Users']

    assert len(new_users) == 1
    user = new_users.iloc[0]

    assert user["userName"] == "loknathsahu"
    assert user["employeeId"] == "RN-RAN-00034"
    assert user["email"] == "loknath.sahu@parashospital"
    assert user["phone"] == "9534185264"
    assert user["firstName"] == ""
    assert user["lastName"] == ""


