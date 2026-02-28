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
    leave_hours: Optional[float] = None

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
        if self.leave_hours is not None:
            if self.leave_hours <= 0:
                raise ValueError("leave_hours must be greater than 0")
            if self.leave_hours > 8:
                raise ValueError("leave_hours cannot exceed 8")
        if self.duration_type == "duration" and self.leave_hours is not None and self.start_date != self.end_date:
            raise ValueError("Hourly leave can only be applied for a single date")
        return self


# -------- RESPONSE --------
class LeaveOut(BaseModel):
    id: int
    leave_type: str
    duration_type: str
    start_date: date
    end_date: date
    total_days: float
    leave_hours: Optional[float] = None
    reason: str
    status: str
    created_at: datetime
    employee: UserOut | None
    approver: UserOut | None

    class Config:
        from_attributes = True
