from typing import List, Optional
from pydantic import BaseModel, Field

class UserField(BaseModel):
    userName: Optional[str] = Field(None, description="System username")
    password: Optional[str] = Field("Medblaze@123", description="Initial password")
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

class UserMasterResult(BaseModel):
    document_name: str
    users: List[UserField]
