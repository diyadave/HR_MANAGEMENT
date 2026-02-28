from sqlalchemy import Column, Integer, String, Date, DateTime, ForeignKey, Text, Float
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.database.base import Base


class Leave(Base):
    __tablename__ = "leaves"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    leave_type = Column(String(50), nullable=False)   # casual, sick, annual, unpaid
    duration_type = Column(String(20), nullable=False)  # full_day | first_half | second_half | duration

    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)

    total_days = Column(Float, nullable=False)
    leave_hours = Column(Float, nullable=True)

    reason = Column(Text, nullable=False)

    status = Column(String(20), default="pending")  
    # pending | approved | rejected | cancelled

    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.now(timezone.utc))

    # relationships
    employee = relationship("User", foreign_keys=[user_id])
    approver = relationship("User", foreign_keys=[approved_by])
