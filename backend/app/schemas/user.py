from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    role: str
    force_password_change: bool



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

    class Config:
        orm_mode = True



class ChangePasswordRequest(BaseModel):
    new_password: str