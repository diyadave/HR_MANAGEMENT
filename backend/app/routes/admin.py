import secrets
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from sqlalchemy import extract
from typing import List, Optional
from datetime import datetime, timezone

from app.database.session import get_db
from app.core.dependencies import get_current_admin
from app.core.security import hash_password, verify_password

from app.models.user import User
from app.models.attendance import Attendance
from app.models.project import Project
from app.models.task import Task
from app.models.task_time_log import TaskTimeLog

from app.schemas.user import EmployeeCreate, EmployeeCreateResponse, EmployeeOut, AdminCreate
from app.schemas.task import TaskCreate, TaskOut

from app.utils.email import send_employee_credentials

import shutil
import os

router = APIRouter(prefix="/admin", tags=["Admin"])


# ================= EMPLOYEE CREATION =================
@router.post("/employees", response_model=EmployeeCreateResponse)
def create_employee(
    payload: EmployeeCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    employee_id = payload.employee_id.strip().upper()
    if not employee_id:
        raise HTTPException(status_code=400, detail="Employee ID is required")

    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email already exists")
    if db.query(User).filter(User.employee_id == employee_id).first():
        raise HTTPException(status_code=400, detail="Employee ID already exists")

    temp_password = secrets.token_urlsafe(8)

    employee = User(
        name=payload.name,
        email=payload.email,
        department=payload.department,
        designation=payload.designation,
        role="employee",
        employee_id=employee_id,
        password_hash=hash_password(temp_password),
        is_active=True,
        force_password_change=True
    )

    db.add(employee)
    db.commit()
    db.refresh(employee)

    try:
        send_employee_credentials(
            to_email=employee.email,
            employee_id=employee.employee_id,
            temp_password=temp_password,
            employee_name=employee.name
        )
    except Exception as exc:
        # Employee is created already; avoid failing API response due SMTP issues.
        print(f"Email sending failed for employee {employee.employee_id}: {exc}")

    return {
        "employee_id": employee.employee_id,
        "email": employee.email
    }


@router.get("/employees", response_model=List[EmployeeOut])
def get_employees(
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    return db.query(User).filter(User.role == "employee").all()


# ================= PROJECTS =================



# ================= TASKS (ADMIN ASSIGN) =================

@router.post("/tasks", response_model=TaskOut)
def create_task(
    task: TaskCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    new_task = Task(
        title=task.title,
        description=task.description,
        project_id=task.project_id,
        assigned_to=task.assigned_to,
        priority=task.priority,
        due_date=task.due_date,
        estimated_hours=task.estimated_hours,
        created_by=admin.id,
        status="pending"
    )

    db.add(new_task)
    db.commit()
    db.refresh(new_task)

    return new_task


@router.get("/tasks", response_model=List[TaskOut])
def get_all_tasks(
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    tasks = (
        db.query(Task)
        .outerjoin(Project, Task.project_id == Project.id)
        .outerjoin(User, Task.assigned_to == User.id)
        .order_by(Task.id.desc())
        .all()
    )

    result = []

    for task in tasks:
        result.append({
            "id": task.id,
            "title": task.title,
            "description": task.description,
            "project_id": task.project_id,
            "project_name": task.project.name if task.project else None,
            "assigned_to": task.assigned_to,
            "assignee_name": task.assigned_user.name if task.assigned_user else None,
            "assignee_profile_image": task.assigned_user.profile_image if task.assigned_user else None,
            "priority": task.priority,
            "status": task.status,
            "due_date": task.due_date,
            "estimated_hours": task.estimated_hours
        })

    return result
# ================= ATTENDANCE REPORT =================

@router.get("/attendance")
def get_monthly_attendance(
    month: int,
    year: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
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
            "designation": user.designation,
            "profile_image": user.profile_image,
            "days": days_map,
            "total_present_days": total_present
        })

    return result


# ================= PRODUCTIVITY =================

@router.get("/productivity")
def get_productivity(
    month: int,
    year: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    users = db.query(User).filter(User.role == "employee").all()
    result = []

    for user in users:
        attendance_records = db.query(Attendance).filter(
            Attendance.user_id == user.id,
            extract("month", Attendance.date) == month,
            extract("year", Attendance.date) == year
        ).all()
        attendance_seconds = sum([(a.total_seconds or 0) for a in attendance_records])

        logs = db.query(TaskTimeLog).filter(
            TaskTimeLog.user_id == user.id,
            extract("month", TaskTimeLog.start_time) == month,
            extract("year", TaskTimeLog.start_time) == year
        ).all()
        now = datetime.now(timezone.utc)
        task_seconds = 0
        for log in logs:
            if log.end_time:
                task_seconds += int((log.end_time - log.start_time).total_seconds())
            else:
                task_seconds += int((now - log.start_time).total_seconds())

        idle_seconds = max(0, attendance_seconds - task_seconds)
        overtime_seconds = max(0, attendance_seconds - (9 * 3600))
        productivity_percent = 0.0
        if attendance_seconds > 0:
            productivity_percent = round((task_seconds / attendance_seconds) * 100, 1)

        result.append({
            "employee_id": user.id,
            "name": user.name,
            "department": user.department,
            "profile_image": user.profile_image,
            "attendance_seconds": attendance_seconds,
            "task_seconds": task_seconds,
            "idle_seconds": idle_seconds,
            "overtime_seconds": overtime_seconds,
            "productivity_percent": productivity_percent
        })

    return result



# ================= ADMIN PROFILE MANAGEMENT =================

@router.get("/profile")
def get_admin_profile(
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
):
    """Get current admin profile details"""
    return {
        "id": current_admin.id,
        "name": current_admin.name,
        "email": current_admin.email,
        "role": current_admin.role,
        "profile_image": current_admin.profile_image,
        "created_at": current_admin.created_at,
        "phone": current_admin.phone,
        "department": current_admin.department,
        "designation": current_admin.designation,
        "last_login": current_admin.last_login if hasattr(current_admin, 'last_login') else None
    }


@router.put("/profile")
def update_admin_profile(
    name: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    phone: Optional[str] = Form(None),
    department: Optional[str] = Form(None),
    designation: Optional[str] = Form(None),
    current_password: Optional[str] = Form(None),
    new_password: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
):
    """Update admin profile information"""
    
    # Check email uniqueness if changing
    if email and email != current_admin.email:
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already exists")
        current_admin.email = email
    
    # Update basic info
    if name:
        current_admin.name = name
    if phone:
        current_admin.phone = phone
    if department:
        current_admin.department = department
    if designation:
        current_admin.designation = designation
    
    # Handle password change
    if new_password:
        if not current_password:
            raise HTTPException(status_code=400, detail="Current password is required")
        
        if not verify_password(current_password, current_admin.password_hash):
            raise HTTPException(status_code=400, detail="Current password is incorrect")
        
        current_admin.password_hash = hash_password(new_password)
        current_admin.force_password_change = False
    
    db.commit()
    db.refresh(current_admin)
    
    return {
        "message": "Profile updated successfully",
        "user": {
            "id": current_admin.id,
            "name": current_admin.name,
            "email": current_admin.email,
            "role": current_admin.role,
            "profile_image": current_admin.profile_image
        }
    }


@router.post("/profile/upload-image")
def upload_admin_profile_image(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
):
    """Upload admin profile image"""
    
    # Validate file type
    allowed_extensions = {'.jpg', '.jpeg', '.png', '.gif'}
    file_ext = os.path.splitext(file.filename)[1].lower()
    
    if file_ext not in allowed_extensions:
        raise HTTPException(status_code=400, detail="Only image files are allowed")
    
    # Create upload directory if not exists
    upload_dir = "uploads/profile_images"
    os.makedirs(upload_dir, exist_ok=True)
    
    # Generate unique filename
    filename = f"admin_{current_admin.id}_{datetime.now().timestamp()}{file_ext}"
    file_path = os.path.join(upload_dir, filename)
    
    # Save file
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    # Delete old image if exists
    if current_admin.profile_image:
        old_file_path = os.path.join("uploads", current_admin.profile_image.lstrip('/'))
        if os.path.exists(old_file_path):
            os.remove(old_file_path)
    
    # Update database
    current_admin.profile_image = f"/{file_path}"
    db.commit()
    
    return {
        "message": "Profile image uploaded successfully",
        "profile_image": current_admin.profile_image
    }


@router.post("/create")
def create_admin(
    payload: AdminCreate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
):
    """Create a new admin user"""
    
    # Check if email already exists
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already exists")
    
    # Generate employee ID for admin
    admin_count = db.query(User).filter(User.role == "admin").count()
    employee_id = f"ADMIN-{str(admin_count + 1).zfill(4)}"
    
    # Create new admin
    new_admin = User(
        name=payload.name,
        email=payload.email,
        employee_id=employee_id,
        password_hash=hash_password(payload.password),
        role="admin",
        is_active=True,
        force_password_change=False
    )
    
    db.add(new_admin)
    db.commit()
    db.refresh(new_admin)
    
    return {
        "message": "Admin created successfully",
        "admin": {
            "id": new_admin.id,
            "name": new_admin.name,
            "email": new_admin.email,
            "employee_id": new_admin.employee_id
        }
    }


@router.get("/list")
def get_all_admins(
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
):
    """Get list of all admin users"""
    
    admins = db.query(User).filter(User.role == "admin").all()
    
    result = []
    for admin in admins:
        result.append({
            "id": admin.id,
            "name": admin.name,
            "email": admin.email,
            "employee_id": admin.employee_id,
            "profile_image": admin.profile_image,
            "created_at": admin.created_at,
            "is_active": admin.is_active,
            "is_current": admin.id == current_admin.id
        })
    
    return result


@router.post("/toggle-status/{admin_id}")
def toggle_admin_status(
    admin_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
):
    """Toggle admin active status (cannot deactivate yourself)"""
    
    if admin_id == current_admin.id:
        raise HTTPException(status_code=400, detail="Cannot deactivate yourself")
    
    admin = db.query(User).filter(
        User.id == admin_id,
        User.role == "admin"
    ).first()
    
    if not admin:
        raise HTTPException(status_code=404, detail="Admin not found")
    
    admin.is_active = not admin.is_active
    db.commit()
    
    return {
        "message": f"Admin {'activated' if admin.is_active else 'deactivated'} successfully",
        "is_active": admin.is_active
    }
