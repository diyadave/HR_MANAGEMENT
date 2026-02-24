from pydantic import BaseModel
from datetime import date
from typing import Optional
from app.models.holiday import HolidayType


class HolidayCreate(BaseModel):
    name: str
    date: date
    type: HolidayType = HolidayType.full_day
    department: str = "All"
    repeat_yearly: bool = False


class HolidayUpdate(BaseModel):
    name: Optional[str] = None
    date: Optional[date] = None
    type: Optional[HolidayType] = None
    department: Optional[str] = None
    repeat_yearly: Optional[bool] = None


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