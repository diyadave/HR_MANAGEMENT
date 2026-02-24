from sqlalchemy import Column, Integer, String, Date, Boolean, Enum
from app.database.base import Base
import enum


class HolidayType(str, enum.Enum):
    full_day = "Full Day"
    first_half = "First Half"
    second_half = "Second Half"


class Holiday(Base):
    __tablename__ = "holidays"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    date = Column(Date, nullable=False)
    type = Column(Enum(HolidayType), default=HolidayType.full_day, nullable=False)

    # Optional: comma-separated dept names, or "All"
    department = Column(String, default="All", nullable=False)

    # Repeat every year on same month/day
    repeat_yearly = Column(Boolean, default=False, nullable=False)