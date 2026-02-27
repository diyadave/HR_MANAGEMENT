from pydantic import BaseModel, field_validator
from datetime import date
from typing import Optional
from app.models.holiday import HolidayType


class HolidayCreate(BaseModel):
    name: str
    date: date
    type: HolidayType = HolidayType.full_day
    department: str = "All"
    repeat_yearly: bool = False

    @field_validator("name", "department")
    @classmethod
    def validate_non_empty(cls, value: str):
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("This field is required")
        return cleaned


class HolidayUpdate(BaseModel):
    name: Optional[str] = None
    date: Optional[date] = None
    type: Optional[HolidayType] = None
    department: Optional[str] = None
    repeat_yearly: Optional[bool] = None

    @field_validator("name", "department")
    @classmethod
    def validate_optional_non_empty(cls, value: Optional[str]):
        if value is None:
            return value
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("This field is required")
        return cleaned


class HolidayOut(BaseModel):
    id: int
    name: str
    date: date
    type: HolidayType
    department: str
    repeat_yearly: bool

    class Config:
        from_attributes = True


class HolidayBulkDeleteRequest(BaseModel):
    ids: list[int]
