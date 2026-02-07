from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.sql import func
from app.database.base import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)

    employee_id = Column(String, unique=True, index=True, nullable=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)

    password_hash = Column(String, nullable=False)

    role = Column(String, nullable=False)  # admin | employee

    department = Column(String, nullable=True)
    designation = Column(String, nullable=True)

    is_active = Column(Boolean, default=True)
    force_password_change = Column(Boolean, default=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
