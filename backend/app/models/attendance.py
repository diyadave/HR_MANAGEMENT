from sqlalchemy import Column, Integer, Date, DateTime, ForeignKey, UniqueConstraint
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

    user = relationship("User")

    __table_args__ = (
        UniqueConstraint("user_id", "date", name="unique_user_date"),
    )