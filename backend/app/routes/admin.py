import secrets
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import extract
from typing import List
from app.utils.email import send_employee_credentials

from app.database.session import get_db
from app.models.user import User
from app.models.attendance import Attendance
from app.core.security import hash_password
from app.schemas.user import EmployeeCreate, EmployeeCreateResponse, EmployeeOut
from app.core.dependencies import get_current_admin

router = APIRouter(prefix="/admin", tags=["Admin"])


def generate_employee_id(db: Session) -> str:
    count = db.query(User).filter(User.role == "employee").count() + 1
    return f"EMP-2026-{str(count).zfill(4)}"


@router.post("/employees", response_model=EmployeeCreateResponse)
def create_employee(
    payload: EmployeeCreate,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin)  
):
    # check email uniqueness
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email already exists")

    temp_password = secrets.token_urlsafe(8)

    employee = User(
        name=payload.name,
        email=payload.email,
        department=payload.department,
        designation=payload.designation,
        role="employee",
        employee_id=generate_employee_id(db),
        password_hash=hash_password(temp_password),
        is_active=True,
        force_password_change=True
    )

    db.add(employee)
    db.commit()
    db.refresh(employee)
    
    send_employee_credentials(
        to_email=employee.email,
        employee_id=employee.employee_id,
        temp_password=temp_password,
        employee_name=employee.name
    )

    # TODO: send email with temp_password (NEXT STEP)

    return {
        "employee_id": employee.employee_id,
        "email": employee.email
    }



@router.get("/employees", response_model=list[EmployeeOut])
def get_employees(db: Session = Depends(get_db)):
    return db.query(User).filter(User.role == "employee").all()

@router.get("/attendance")
def get_monthly_attendance(month: int, year: int, db: Session = Depends(get_db)):

    users = db.query(User).filter(User.role == "employee").all()

    result = []

    for user in users:
        records = db.query(Attendance).filter(
            Attendance.user_id == user.id,
            extract("month", Attendance.date) == month,
            extract("year", Attendance.date) == year
        ).all()

        days_map = {}
        total_present = 0

        for r in records:
            hours = (r.total_seconds or 0) / 3600

            if hours >= 9:
                status = "present"
                total_present += 1
            elif hours >= 4:
                status = "halfday"
                total_present += 0.5
            else:
                status = "absent"

            days_map[r.date.day] = status

        result.append({
            "employee_id": user.id,
            "name": user.name,
            "department": user.department,
            "days": days_map,
            "total_present_days": total_present
        })

    return result

from app.models.task_time_log import TaskTimeLog
from app.models.task import Task

@router.get("/productivity")
def get_productivity(month: int, year: int, db: Session = Depends(get_db)):

    users = db.query(User).filter(User.role == "employee").all()
    result = []

    for user in users:
        logs = db.query(TaskTimeLog).join(Task).filter(
            Task.assigned_to == user.id,
            extract("month", TaskTimeLog.start_time) == month,
            extract("year", TaskTimeLog.start_time) == year
        ).all()

        total_seconds = sum([l.duration_seconds or 0 for l in logs])

        result.append({
            "employee_id": user.id,
            "name": user.name,
            "department": user.department,
            "total_task_hours": round(total_seconds / 3600, 2)
        })

    return result