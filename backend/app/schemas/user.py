from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional
from datetime import date

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class UserInfo(BaseModel):
    id: int
    name: str
    role: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    force_password_change: bool
    user: UserInfo




class EmployeeCreate(BaseModel):
    name: str
    email: EmailStr
    department: str | None = None
    designation: str | None = None


class EmployeeCreateResponse(BaseModel):
    employee_id: str
    email: EmailStr


class EmployeeOut(BaseModel):
    id: int                       # from users.id
    employee_id: Optional[str] = None
    name: str
    email: EmailStr
    role: str
    department: Optional[str] = None
    designation: Optional[str] = None
    is_active: bool = True
    created_at: Optional[datetime] = None

    model_config = {
    "from_attributes": True
}



class UserOut(BaseModel):
    id: int
    name: str
    email: EmailStr
    role: str
    department: Optional[str] = None
    designation: Optional[str] = None
    is_active: bool = True
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class ChangePasswordRequest(BaseModel):
    new_password: str

  

# ---------------- PROFILE UPDATE ----------------

class ProfileUpdateSchema(BaseModel):
    phone: Optional[str] = None
    address: Optional[str] = None
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    marital_status: Optional[str] = None
    blood_group: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    bank_name: Optional[str] = None
    account_number: Optional[str] = None
    ifsc_code: Optional[str] = None
    profile_image: Optional[str] = None



# ---------------- PROFILE RESPONSE ----------------

class ProfileResponse(BaseModel):
    id: int
    name: str
    email: EmailStr
    role: str
    department: Optional[str] = None
    designation: Optional[str] = None
    profile_image: Optional[str] = None

    phone: Optional[str] = None
    address: Optional[str] = None
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    marital_status: Optional[str] = None
    blood_group: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    bank_name: Optional[str] = None
    account_number: Optional[str] = None
    ifsc_code: Optional[str] = None

    is_active: bool = True
    created_at: Optional[datetime] = None

    model_config = {
        "from_attributes": True
    }