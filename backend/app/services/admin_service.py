from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.models.user import User
from app.core.security import hash_password
from app.utils.generator import generate_employee_id, generate_temp_password

def create_employee(
    db: Session,
    name: str,
    email: str,
    department: str | None,
    designation: str | None
):
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=400, detail="Email already exists")

    count = db.query(User).count()
    employee_id = generate_employee_id(count)
    temp_password = generate_temp_password()

    user = User(
        name=name,
        email=email,
        employee_id=employee_id,
        password_hash=hash_password(temp_password),
        role="employee",
        department=department,
        designation=designation,
        is_active=True,
        force_password_change=True
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user, temp_password
