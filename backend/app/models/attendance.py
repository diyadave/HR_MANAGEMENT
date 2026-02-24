from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from app.database.base import Base
from sqlalchemy.orm import relationship

class Attendance(Base):
    __tablename__ = "attendance_logs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    date = Column(Date, nullable=False)

    # 🔥 VERY IMPORTANT FIX
    clock_in_time = Column(DateTime(timezone=True), nullable=True)
    clock_out_time = Column(DateTime(timezone=True), nullable=True)

    total_seconds = Column(Integer, default=0)
    half_day_type = Column(String(20), nullable=True)  # first_half | second_half
    is_late = Column(Boolean, default=False, nullable=False)
    working_from = Column(String(30), nullable=True)
    location = Column(String(255), nullable=True)
    manual_override = Column(Boolean, default=False, nullable=False)
    edit_reason = Column(Text, nullable=True)

    user = relationship("User")

    __table_args__ = (
        UniqueConstraint("user_id", "date", name="unique_user_date"),
    )

    
