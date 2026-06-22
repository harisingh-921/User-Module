from typing import List, Optional
from pydantic import BaseModel, Field

class UserField(BaseModel):
    userName: Optional[str] = Field(None, description="System username")
    password: Optional[str] = Field(None, description="Initial password")
    departments: Optional[str] = Field(None, description="Pipe-separated departments")
    roles: Optional[str] = Field(None, description="Pipe-separated roles")
    units: Optional[str] = Field(None, description="Assigned units")
    locations: Optional[str] = Field(None, description="Assigned locations")
    email: Optional[str] = Field(None, description="Primary email")
    phone: Optional[str] = Field(None, description="Primary mobile phone")
    employeeId: Optional[str] = Field(None, description="Unique employee identifier")
    firstName: Optional[str] = Field(None, description="User first name")
    middleName: Optional[str] = Field(None, description="User middle name")
    lastName: Optional[str] = Field(None, description="User last name")
    designation: Optional[str] = Field(None, description="Job title")
    timezone: Optional[str] = Field("UTC+05:30", description="Preferred timezone")
    shiftDuration: Optional[str] = Field(None, description="Standard shift length")
    thirdPartyUsername: Optional[str] = Field(None, description="External system username")
    dateOfJoining: Optional[str] = Field(None, description="Date of joining")
    lastWorkingDate: Optional[str] = Field(None, description="Last working date")
    reportingTo: Optional[str] = Field(None, description="Manager username or ID")
    isEnabled: Optional[str] = Field("Yes", description="Account status (Yes/No)")
    passwordPolicy: Optional[str] = Field(None, description="Password policy constraint")

class UserMasterResult(BaseModel):
    document_name: str
    users: List[UserField]


class MappingIntent(BaseModel):
    target_col: str = Field(description="The column name in the staff list to update/map (e.g. 'departments', 'roles')")
    lookup_col: str = Field(description="The key/lookup column name in the external mapping file")
    value_col: str = Field(description="The value column name in the external mapping file to get replacements from")


class ReplaceIntent(BaseModel):
    target_col: str = Field(description="The column name in the staff list to perform replacement on (e.g. 'roles', 'departments')")
    search_text: str = Field(description="The exact text or substring to search for")
    replace_text: str = Field(description="The replacement text")


class SetValueIntent(BaseModel):
    target_col: str = Field(description="The column name in the staff list to update (e.g. 'isEnabled')")
    value: str = Field(description="The new value to set")
    filter_col: Optional[str] = Field(None, description="Optional column name to filter by (e.g. 'designation')")
    filter_value: Optional[str] = Field(None, description="Optional value in filter_col to match")


class RowUpdate(BaseModel):
    serial_number: int = Field(alias="#", description="The '#' (serial number) identifying the row to update")
    userName: Optional[str] = Field(None, description="Updated username")
    password: Optional[str] = Field(None, description="Updated password")
    departments: Optional[str] = Field(None, description="Updated pipe-separated departments")
    roles: Optional[str] = Field(None, description="Updated pipe-separated roles")
    units: Optional[str] = Field(None, description="Updated assigned units")
    locations: Optional[str] = Field(None, description="Updated assigned locations")
    email: Optional[str] = Field(None, description="Updated email")
    phone: Optional[str] = Field(None, description="Updated mobile phone")
    employeeId: Optional[str] = Field(None, description="Updated employee identifier")
    firstName: Optional[str] = Field(None, description="Updated first name")
    middleName: Optional[str] = Field(None, description="Updated middle name")
    lastName: Optional[str] = Field(None, description="Updated last name")
    designation: Optional[str] = Field(None, description="Updated job title")
    timezone: Optional[str] = Field(None, description="Updated timezone")
    shiftDuration: Optional[str] = Field(None, description="Updated shift length")
    thirdPartyUsername: Optional[str] = Field(None, description="Updated external system username")
    dateOfJoining: Optional[str] = Field(None, description="Updated date of joining")
    lastWorkingDate: Optional[str] = Field(None, description="Updated last working date")
    reportingTo: Optional[str] = Field(None, description="Updated manager username or ID")
    isEnabled: Optional[str] = Field(None, description="Updated account status")
    passwordPolicy: Optional[str] = Field(None, description="Updated password policy")

    model_config = {
        "populate_by_name": True
    }


class AISmartResponse(BaseModel):
    mapping_intent: Optional[MappingIntent] = Field(None, description="Populate this only if the user wants to map values using an external file")
    replace_intent: Optional[ReplaceIntent] = Field(None, description="Populate this only if the user wants to perform a search and replace on a column")
    set_value_intent: Optional[SetValueIntent] = Field(None, description="Populate this only if the user wants to set a column to a fixed value")
    updates: Optional[List[RowUpdate]] = Field(None, description="Populate this list of specific row updates for all other edits")


class VerificationResult(BaseModel):
    is_hallucinated: bool = Field(description="Set to True if any of the extracted users do not actually exist in the source text, or if their details are fabricated.")
    reason: Optional[str] = Field(None, description="The reason for the hallucination flag, indicating which field or record is invalid.")


