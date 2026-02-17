from pydantic import BaseModel
from datetime import date, datetime
from typing import Optional
from app.schemas.user import UserOut


# -------- CREATE --------
class LeaveCreate(BaseModel):
    leave_type: str
    duration_type: str
    start_date: date
    end_date: date
    reason: str


# -------- RESPONSE --------
class LeaveOut(BaseModel):
    id: int
    leave_type: str
    duration_type: str
    start_date: date
    end_date: date
    total_days: int
    reason: str
    status: str
    created_at: datetime
    employee: UserOut | None
    approver: UserOut | None

    class Config:
        from_attributes = True