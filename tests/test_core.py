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


def test_local_extraction_subheaders_and_contacts():
    import io
    from extraction.local import local_extract_users

    # Mock Excel sheet mimicking subheaders, multiple emails/phones and multiple roles columns
    data = [
        ["Unit Name", "Jaipur", "", "User Name", "", "", "", "", "", "", "", ""],
        ["", "Audit USER", "Suggested User", "First Name", "Middle Name", "Last Name", "Employee Id", "Designation", "Departments", "Email", "Mobile", "Third Party Username (Name as in email)"],
        ["", "Audit User - CESC - SSI", "ICN", "Sarita", "", "", "180783", "ICN", "Infection Control", "icn.jaipur@fortishealthcare.com | vidhya.kanwar@FORTISHEALTHCARE.COM", "9376950533 | 7023701893 | 3", "icn.jaipur | vidhya.kanwar"],
        ["", "Audit User - CESC - CLABSI", "ICN", "Vidhya", "", "Kanwar", "221020", "ICN", "Infection Control", "icn.jaipur@fortishealthcare.com | vidhya.kanwar@FORTISHEALTHCARE.COM", "9376950533 | 7023701893 | 3", "icn.jaipur | vidhya.kanwar"],
        ["", "Audit User - MOS - Prevention of CLABSI", "ICN", "Sarita", "", "", "180783", "ICN", "Infection Control", "icn.jaipur@fortishealthcare.com | vidhya.kanwar@FORTISHEALTHCARE.COM", "9376950533 | 7023701893 | 3", "icn.jaipur | vidhya.kanwar"]
    ]

    df = pd.DataFrame(data)
    towrite = io.BytesIO()
    with pd.ExcelWriter(towrite, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, header=False, sheet_name="Sheet1")
    towrite.seek(0)
    file_bytes = towrite.read()

    res = local_extract_users(file_bytes, "test.xlsx", pass_prefix="Med")
    assert not res.empty
    assert len(res) == 2
    
    sarita = res[res['firstName'] == 'Sarita'].iloc[0]
    assert sarita['lastName'] == ''
    assert sarita['email'] == 'icn.jaipur@fortishealthcare.com'
    assert sarita['phone'] == '9376950533'
    assert sarita['thirdPartyUsername'] == 'icn.jaipur'
    assert 'Audit User - CESC - SSI' in sarita['roles']
    assert 'Audit User - MOS - Prevention of CLABSI' in sarita['roles']
    assert 'ICN' not in sarita['roles']
    
    vidhya = res[res['firstName'] == 'Vidhya'].iloc[0]
    assert vidhya['lastName'] == 'Kanwar'
    assert vidhya['email'].lower() == 'vidhya.kanwar@fortishealthcare.com'
    assert vidhya['phone'] == '7023701893'
    assert vidhya['thirdPartyUsername'] == 'vidhya.kanwar'
    assert 'Audit User - CESC - CLABSI' in vidhya['roles']
    assert 'ICN' not in vidhya['roles']


def test_merge_double_pass_keeps_different_employee_ids():
    from extraction.merge import _merge_duplicate_users
    import pandas as pd
    
    # Mock data where two different employees share the same username (e.g. vidhyakanwar)
    data = [
        {
            "employeeId": "EMP001",
            "firstName": "Vidhya",
            "lastName": "Kanwar",
            "userName": "vidhyakanwar",
            "email": "vidhya@fortis.com",
            "phone": "9999999999",
            "roles": "ICN"
        },
        {
            "employeeId": "EMP002",
            "firstName": "Sarita",
            "lastName": "Devi",
            "userName": "vidhyakanwar",  # Colliding username
            "email": "sarita@fortis.com",
            "phone": "8888888888",
            "roles": "Audit User"
        }
    ]
    df = pd.DataFrame(data)
    res = _merge_duplicate_users(df, pass_prefix="Med")
    
    # They should NOT be merged since they have different non-empty employee IDs
    assert len(res) == 2
    
    emp1 = res[res['employeeId'] == 'EMP001'].iloc[0]
    assert emp1['firstName'] == 'Vidhya'
    
    emp2 = res[res['employeeId'] == 'EMP002'].iloc[0]
    assert emp2['firstName'] == 'Sarita'


def test_construct_username_with_prefixes():
    from extraction.merge import _merge_duplicate_users
    import pandas as pd
    
    # Test prefix handling in construct_username
    data = [
        {
            "employeeId": "EMP010",
            "firstName": "Dr. Nivedita",
            "lastName": "Sharma",
            "userName": "",
            "roles": "Med Admin"
        },
        {
            "employeeId": "EMP011",
            "firstName": "Mr. Tanveer",
            "lastName": "Kumawat",
            "userName": "",
            "roles": "OT Manager"
        },
        {
            "employeeId": "EMP012",
            "firstName": "Priyodarshini Manisha",  # No prefix, should split on space
            "lastName": "Saha",
            "userName": "",
            "roles": "Doctor"
        }
    ]
    df = pd.DataFrame(data)
    res = _merge_duplicate_users(df, pass_prefix="Med")
    
    nivedita = res[res['employeeId'] == 'EMP010'].iloc[0]
    assert nivedita['userName'] == 'drniveditasharma'
    
    tanveer = res[res['employeeId'] == 'EMP011'].iloc[0]
    assert tanveer['userName'] == 'mrtanveerkumawat'
    
    priyodarshini = res[res['employeeId'] == 'EMP012'].iloc[0]
    assert priyodarshini['userName'] == 'priyodarshinisaha'


def test_local_extraction_roles_merging_for_doctors():
    import io
    from extraction.local import local_extract_users

    data = [
        ["Unit Name", "Jaipur", "", "", "", "", "", "", "", "", ""],
        ["Audit USER", "Suggested User", "First Name", "Middle Name", "Last Name", "Third party/ AD username", "Email Address", "Phone", "Designation", "Roles", "Department"],
        ["Audit User - CESC - Death within 48 hours of surgery", "Med Admin / Nursing", "Dr. Nivedita", "", "Sharma", "nivedita.sharma", "nivedita.sharma@FORTISHEALTHCARE.COM", "9588060430", "AMS", "", "Medical Admin"],
        ["Audit User - CESC - Death within 48 hours of Procedure", "Med Admin / Nursing", "Dr. Nivedita", "", "Sharma", "nivedita.sharma", "nivedita.sharma@FORTISHEALTHCARE.COM", "9588060430", "AMS", "", "Medical Admin"],
        ["Audit User - CESC - VTE", "Med Admin", "Dr. Nivedita", "", "Sharma", "nivedita.sharma", "nivedita.sharma@FORTISHEALTHCARE.COM", "9588060430", "AMS", "", "Medical Admin"]
    ]

    df = pd.DataFrame(data)
    towrite = io.BytesIO()
    with pd.ExcelWriter(towrite, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, header=False, sheet_name="Sheet1")
    towrite.seek(0)
    file_bytes = towrite.read()

    res = local_extract_users(file_bytes, "test.xlsx", pass_prefix="Med")
    assert not res.empty
    assert len(res) == 1
    
    nivedita = res.iloc[0]
    assert nivedita['userName'] == 'drniveditasharma'
    
    # Assert all roles from columns and rows are merged
    roles = nivedita['roles'].split('|')
    assert 'Audit User - CESC - Death within 48 hours of surgery' in roles
    assert 'Med Admin / Nursing' not in roles
    assert 'Audit User - CESC - Death within 48 hours of Procedure' in roles
    assert 'Audit User - CESC - VTE' in roles
    assert 'Med Admin' not in roles


def test_resolve_duplicate_usernames():
    from utils.common import resolve_duplicate_usernames

    df = pd.DataFrame([
        {"#": 1, "userName": "arvindkumar"},
        {"#": 2, "userName": "Arvindkumar"},  # duplicate -> Arvindkumar2 (since arvindkumar1 exists at #4)
        {"#": 3, "userName": "drarvindkumar"},  # substring, not duplicate
        {"#": 4, "userName": "arvindkumar1"},  # already exists, keeps original
        {"#": 5, "userName": "arvindkumar"},  # duplicate -> arvindkumar3 (since 1 and 2 are taken)
        {"#": 6, "userName": "johndoe"},
        {"#": 7, "userName": ""},
        {"#": 8, "userName": None}
    ])

    res_df, count = resolve_duplicate_usernames(df)

    assert count == 2
    assert res_df.loc[0, "userName"] == "arvindkumar"
    assert res_df.loc[1, "userName"] == "Arvindkumar2"
    assert res_df.loc[2, "userName"] == "drarvindkumar"
    assert res_df.loc[3, "userName"] == "arvindkumar1"
    assert res_df.loc[4, "userName"] == "arvindkumar3"
    assert res_df.loc[5, "userName"] == "johndoe"
    assert res_df.loc[6, "userName"] == ""
    assert res_df.loc[7, "userName"] is None


def test_on_nav_change_no_active_data():
    """Verify on_nav_change switches previous_nav immediately when there is no active data."""
    import streamlit as st
    from ui.sidebar import on_nav_change
    
    st.session_state.clear()
    st.session_state.previous_nav = "Both (Segregation New & Existing Users)"
    st.session_state.nav_radio_key = "New User"
    
    on_nav_change()
    
    assert st.session_state.previous_nav == "New User"
    assert "pending_nav" not in st.session_state


def test_on_nav_change_with_active_data():
    """Verify on_nav_change sets pending_nav and reverts nav_radio_key when active data is present."""
    import streamlit as st
    from ui.sidebar import on_nav_change
    
    st.session_state.clear()
    st.session_state.df_users = pd.DataFrame([{"userName": "johndoe"}])
    st.session_state.previous_nav = "Both (Segregation New & Existing Users)"
    st.session_state.nav_radio_key = "New User"
    
    on_nav_change()
    
    assert st.session_state.pending_nav == "New User"
    assert st.session_state.nav_radio_key == "Both (Segregation New & Existing Users)"





# ── enforce_contract tests ────────────────────────────────────────────────────

def test_enforce_contract_renames_aliases():
    """enforce_contract must rename all known column aliases to their canonical names."""
    from models.dataframe_contract import enforce_contract

    df = pd.DataFrame([{
        "mobile": "9999999999",
        "Email": "user@example.com",
        "username": "jdoe",
        "first_name": "John",
        "last_name": "Doe",
        "EmployeeID": "EMP001",
        "department": "ICU",
    }])
    result = enforce_contract(df)

    # Aliases renamed
    assert "phone" in result.columns,       "mobile → phone"
    assert "mobile" not in result.columns
    assert "email" in result.columns,       "Email → email"
    assert "Email" not in result.columns
    assert "userName" in result.columns,    "username → userName"
    assert "firstName" in result.columns,   "first_name → firstName"
    assert "lastName" in result.columns,    "last_name → lastName"
    assert "employeeId" in result.columns,  "EmployeeID → employeeId"
    assert "departments" in result.columns, "department → departments"


def test_enforce_contract_adds_missing_columns():
    """enforce_contract must add missing canonical columns as empty strings."""
    from models.dataframe_contract import enforce_contract
    from config.constants import USER_MASTER_COLS

    df = pd.DataFrame([{"firstName": "Jane", "lastName": "Smith"}])
    result = enforce_contract(df)

    for col in USER_MASTER_COLS:
        assert col in result.columns, f"Missing canonical column: {col}"
        # Newly added columns should be empty string
        if col not in ("firstName", "lastName"):
            assert result.iloc[0][col] == "", f"Column '{col}' should default to ''"


def test_enforce_contract_no_mutation():
    """enforce_contract must not mutate the original DataFrame."""
    from models.dataframe_contract import enforce_contract

    original = pd.DataFrame([{"mobile": "9876543210", "firstName": "Alice"}])
    original_cols = list(original.columns)
    enforce_contract(original)
    assert list(original.columns) == original_cols, "Original DataFrame was mutated"


def test_enforce_contract_canonical_wins_over_alias():
    """If both the canonical column and an alias already exist, the alias is NOT renamed (canonical wins)."""
    from models.dataframe_contract import enforce_contract

    df = pd.DataFrame([{"phone": "111", "mobile": "222", "firstName": "Bob"}])
    result = enforce_contract(df)

    # 'phone' already present — 'mobile' alias should not overwrite it
    assert "phone" in result.columns
    assert result.iloc[0]["phone"] == "111"


def test_enforce_contract_empty_df_passes_through():
    """enforce_contract must return an empty DataFrame unchanged when given one."""
    from models.dataframe_contract import enforce_contract

    df = pd.DataFrame()
    result = enforce_contract(df)
    assert result.empty


# ── compare_users / segregation integration tests ────────────────────────────

def test_compare_users_match_by_employee_id():
    """compare_users correctly marks a row as 'Existing User' when employeeId matches."""
    from segregation.core import compare_users

    master_df = pd.DataFrame([
        {"employeeId": "EMP001", "userName": "jdoe", "email": "john@example.com", "roles": "Admin"}
    ])
    client_df = pd.DataFrame([
        {"employeeId": "EMP001", "email": "john@example.com"}
    ])
    priority_mappings = [
        {"name": "Employee ID", "master_col": "employeeId", "client_col": "employeeId"},
        {"name": "Email",       "master_col": "email",       "client_col": "email"},
    ]

    result = compare_users(client_df, master_df, priority_mappings)

    assert len(result) == 1
    assert result.iloc[0]["User Type"] == "Existing User"
    assert result.iloc[0]["Matched By"] == "Employee ID"


def test_compare_users_match_by_email_fallback():
    """compare_users falls back to email match when employeeId is absent in client row."""
    from segregation.core import compare_users

    master_df = pd.DataFrame([
        {"employeeId": "EMP002", "userName": "jsmith", "email": "jane@example.com", "roles": "Nurse"}
    ])
    client_df = pd.DataFrame([
        {"employeeId": "", "email": "jane@example.com"}
    ])
    priority_mappings = [
        {"name": "Employee ID", "master_col": "employeeId", "client_col": "employeeId"},
        {"name": "Email",       "master_col": "email",       "client_col": "email"},
    ]

    result = compare_users(client_df, master_df, priority_mappings)

    assert result.iloc[0]["User Type"] == "Existing User"
    assert result.iloc[0]["Matched By"] == "Email"


def test_compare_users_new_user_when_no_match():
    """compare_users marks a row as 'New User' when neither employeeId nor email match."""
    from segregation.core import compare_users

    master_df = pd.DataFrame([
        {"employeeId": "EMP003", "userName": "bob", "email": "bob@example.com"}
    ])
    client_df = pd.DataFrame([
        {"employeeId": "EMP999", "email": "nobody@example.com"}
    ])
    priority_mappings = [
        {"name": "Employee ID", "master_col": "employeeId", "client_col": "employeeId"},
        {"name": "Email",       "master_col": "email",       "client_col": "email"},
    ]

    result = compare_users(client_df, master_df, priority_mappings)

    assert result.iloc[0]["User Type"] == "New User"
    assert result.iloc[0]["Match Status"] == "Not Matched"


def test_compare_users_email_normalised_case_insensitive():
    """compare_users normalises email to lowercase before matching."""
    from segregation.core import compare_users

    master_df = pd.DataFrame([{"employeeId": "", "email": "john@example.com"}])
    client_df  = pd.DataFrame([{"employeeId": "", "email": "JOHN@EXAMPLE.COM"}])
    priority_mappings = [
        {"name": "Employee ID", "master_col": "employeeId", "client_col": "employeeId"},
        {"name": "Email",       "master_col": "email",       "client_col": "email"},
    ]

    result = compare_users(client_df, master_df, priority_mappings)
    assert result.iloc[0]["User Type"] == "Existing User"


# ── local_extract_users edge-case tests ──────────────────────────────────────

def test_local_extract_users_tick_roles():
    """local_extract_users correctly picks tick-marked role columns and assigns them per user."""
    import io
    from extraction.local import local_extract_users

    # Sheet with tick columns representing roles
    data = [
        ["First Name", "Last Name", "Employee ID", "Audit User",   "Incident Reporter", "QI Viewer"],
        ["Alice",      "Brown",     "EMP301",       "✓",            "",                   "✓"],
        ["Bob",        "Green",     "EMP302",       "",             "✓",                  "✓"],
    ]
    df = pd.DataFrame(data)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, header=False, sheet_name="Roles")
    buf.seek(0)

    result = local_extract_users(buf.read(), "test_ticks.xlsx", pass_prefix="Med")
    assert not result.empty
    assert len(result) == 2

    alice = result[result['firstName'] == 'Alice'].iloc[0]
    assert 'Audit User' in alice['roles']
    assert 'QI Viewer' in alice['roles']
    assert 'Incident Reporter' not in alice['roles']

    bob = result[result['firstName'] == 'Bob'].iloc[0]
    assert 'Incident Reporter' in bob['roles']
    assert 'QI Viewer' in bob['roles']
    assert 'Audit User' not in bob['roles']


def test_local_extract_users_pipe_split_multi_user():
    """local_extract_users splits pipe-delimited rows into individual user records."""
    import io
    from extraction.local import local_extract_users

    data = [
        ["First Name",          "Last Name",      "Employee ID",     "Email",                                       "Department"],
        ["Alice | Bob",         "Smith | Jones",  "EMP401 | EMP402", "alice@example.com | bob@example.com",         "ICU"],
    ]
    df = pd.DataFrame(data)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, header=False, sheet_name="Sheet1")
    buf.seek(0)

    result = local_extract_users(buf.read(), "test_pipe.xlsx", pass_prefix="Med")
    assert len(result) == 2

    alice = result[result['firstName'] == 'Alice'].iloc[0]
    assert alice['lastName'] == 'Smith'
    assert alice['employeeId'] == 'EMP401'

    bob = result[result['firstName'] == 'Bob'].iloc[0]
    assert bob['lastName'] == 'Jones'
    assert bob['employeeId'] == 'EMP402'
    # Non-pipe column (Department) must NOT be copied to Bob
    # (department goes to both since it has no pipe — that is the correct behaviour)
    assert bob['departments'] == 'ICU'


def test_local_extract_users_csv():
    """local_extract_users handles CSV files the same as Excel."""
    import io
    from extraction.local import local_extract_users

    csv_content = "First Name,Last Name,Employee ID,Email\nCarol,White,EMP501,carol@example.com\n"
    file_bytes = csv_content.encode("utf-8")

    result = local_extract_users(file_bytes, "test.csv", pass_prefix="Med")
    assert not result.empty
    carol = result[result['firstName'] == 'Carol'].iloc[0]
    assert carol['employeeId'] == 'EMP501'
    assert carol['email'] == 'carol@example.com'



