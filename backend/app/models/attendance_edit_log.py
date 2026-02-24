from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, String, Text

from app.database.base import Base


class AttendanceEditLog(Base):
    __tablename__ = "attendance_edit_logs"

    id = Column(Integer, primary_key=True, index=True)
    attendance_id = Column(Integer, ForeignKey("attendance_logs.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    admin_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    date = Column(Date, nullable=False)
    action = Column(String(32), nullable=False)  # create | update | delete | bulk_mark
    reason = Column(Text, nullable=True)
    old_payload = Column(Text, nullable=True)
    new_payload = Column(Text, nullable=True)
    manual_override = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
