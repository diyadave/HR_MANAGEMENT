from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.sql import func
from app.database.base import Base

from sqlalchemy import Date, Text

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

    # 🔹 PROFILE FIELDS (Employee Editable)
    phone = Column(String, nullable=True)
    address = Column(Text, nullable=True)

    date_of_birth = Column(Date, nullable=True)
    gender = Column(String, nullable=True)
    marital_status = Column(String, nullable=True)
    blood_group = Column(String, nullable=True)

    emergency_contact_name = Column(String, nullable=True)
    emergency_contact_phone = Column(String, nullable=True)

    bank_name = Column(String, nullable=True)
    account_number = Column(String, nullable=True)
    ifsc_code = Column(String, nullable=True)

    # 🔹 SYSTEM CONTROLLED (Admin Only)
    salary = Column(String, nullable=True)

    is_active = Column(Boolean, default=True)
    force_password_change = Column(Boolean, default=True)
    profile_image = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())