from pydantic import BaseModel, EmailStr, field_validator, model_validator
from datetime import datetime
from typing import Optional
from datetime import date
import re

class LoginRequest(BaseModel):
    employee_id: str
    password: str

class UserInfo(BaseModel):
    id: int
    name: str
    role: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    force_password_change: bool
    user: UserInfo


class RefreshRequest(BaseModel):
    refresh_token: str

class ForgotPasswordRequest(BaseModel):
    employee_id: str
    email: EmailStr




class EmployeeCreate(BaseModel):
    employee_id: str
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
    profile_image: Optional[str] = None
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
    profile_image: Optional[str] = None
    is_active: bool = True
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class ChangePasswordRequest(BaseModel):
    new_password: str

class AdminCreate(BaseModel):
    name: str
    email: EmailStr
    password: str

INDIA_PHONE_REGEX = re.compile(r"^\+91\d{10}$")
BANK_NAME_REGEX = re.compile(r"^[A-Za-z][A-Za-z .,&'-]{1,99}$")
ACCOUNT_NUMBER_REGEX = re.compile(r"^\d{9,18}$")


class AdminProfileUpdateSchema(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    department: Optional[str] = None
    designation: Optional[str] = None

    @field_validator("*", mode="before")
    @classmethod
    def normalize_optional_strings(cls, value):
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: Optional[str]):
        if value is None:
            return value
        if not INDIA_PHONE_REGEX.fullmatch(value):
            raise ValueError("Phone must be in +91XXXXXXXXXX format")
        return value


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

    @field_validator("*", mode="before")
    @classmethod
    def normalize_optional_strings(cls, value):
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @field_validator("phone", "emergency_contact_phone")
    @classmethod
    def validate_indian_phone(cls, value: Optional[str]):
        if value is None:
            return value
        if not INDIA_PHONE_REGEX.fullmatch(value):
            raise ValueError("Phone must be in +91XXXXXXXXXX format")
        return value

    @field_validator("bank_name")
    @classmethod
    def validate_bank_name(cls, value: Optional[str]):
        if value is None:
            return value
        if not BANK_NAME_REGEX.fullmatch(value):
            raise ValueError("Bank name is invalid")
        return value

    @field_validator("account_number")
    @classmethod
    def validate_account_number(cls, value: Optional[str]):
        if value is None:
            return value
        if not ACCOUNT_NUMBER_REGEX.fullmatch(value):
            raise ValueError("Account number must be 9 to 18 digits")
        return value

    @model_validator(mode="after")
    def validate_bank_fields_together(self):
        bank_name = self.bank_name
        account_number = self.account_number
        if (bank_name and not account_number) or (account_number and not bank_name):
            raise ValueError("Bank name and account number must be provided together")
        return self


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
