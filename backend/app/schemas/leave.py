from pydantic import BaseModel, field_validator, model_validator
from datetime import date, datetime
from typing import Optional, Literal
from app.schemas.user import UserOut


# -------- CREATE --------
class LeaveCreate(BaseModel):
    leave_type: Literal["casual", "sick", "annual", "unpaid"]
    duration_type: Literal["full_day", "first_half", "second_half", "duration"]
    start_date: date
    end_date: date
    reason: str

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str):
        cleaned = value.strip()
        if len(cleaned) < 3:
            raise ValueError("Reason must be at least 3 characters")
        return cleaned

    @model_validator(mode="after")
    def validate_dates_and_duration(self):
        today = date.today()
        if self.start_date < today or self.end_date < today:
            raise ValueError("Only today or upcoming dates are allowed")
        if self.start_date > self.end_date:
            raise ValueError("Start date cannot be after end date")
        if self.duration_type in {"full_day", "first_half", "second_half"} and self.start_date != self.end_date:
            raise ValueError("For full day or half day leave, start and end date must be the same")
        return self


# -------- RESPONSE --------
class LeaveOut(BaseModel):
    id: int
    leave_type: str
    duration_type: str
    start_date: date
    end_date: date
    total_days: float
    reason: str
    status: str
    created_at: datetime
    employee: UserOut | None
    approver: UserOut | None

    class Config:
        from_attributes = True
