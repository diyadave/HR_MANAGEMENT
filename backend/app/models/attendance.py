from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
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
    first_clock_in_time = Column(DateTime(timezone=True), nullable=True)

    total_seconds = Column(Integer, default=0)
    status = Column(String(20), nullable=True)
    overtime_hours = Column(Float, default=0, nullable=False)
    half_day_type = Column(String(20), nullable=True)  # first_half | second_half
    is_late = Column(Boolean, default=False, nullable=False)
    working_from = Column(String(30), nullable=True)
    location = Column(String(255), nullable=True)
    manual_override = Column(Boolean, default=False, nullable=False)
    is_manual_edit = Column(Boolean, default=False, nullable=False)
    updated_by_admin_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    edit_reason = Column(Text, nullable=True)

    user = relationship("User", foreign_keys=[user_id])
    updated_by_admin = relationship("User", foreign_keys=[updated_by_admin_id])

    __table_args__ = (
        UniqueConstraint("user_id", "date", name="unique_user_date"),
    )

    
