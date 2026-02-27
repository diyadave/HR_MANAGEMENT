import secrets
import json
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import and_, extract, or_
from typing import List, Optional
from datetime import date, datetime, time, timezone
from calendar import monthrange
from pydantic import ValidationError

from app.database.session import get_db
from app.core.dependencies import get_current_admin
from app.core.security import hash_password, verify_password

from app.models.user import User
from app.models.attendance import Attendance
from app.models.attendance_edit_log import AttendanceEditLog
from app.models.holiday import Holiday
from app.models.leave import Leave
from app.models.project import Project
from app.models.task import Task
from app.models.task_time_log import TaskTimeLog
from app.services.attendance_service import (
    IST,
    LATE_THRESHOLD,
    auto_close_open_attendances_for_user,
    calculate_overtime_seconds,
    calculate_work_seconds,
    ensure_attendance_schema,
    get_attendance_status_meta,
    get_attendance_worked_seconds,
)
from app.core.attendance_ws_manager import attendance_ws_manager

from app.schemas.user import EmployeeCreate, EmployeeCreateResponse, EmployeeOut, AdminCreate, AdminProfileUpdateSchema
from app.schemas.task import TaskCreate, TaskOut

from app.utils.email import send_employee_credentials

import shutil
import os

router = APIRouter(prefix="/admin", tags=["Admin"])

def _send_employee_credentials_safely(
    to_email: str,
    employee_id: str,
    temp_password: str,
    employee_name: str
) -> None:
    try:
        send_employee_credentials(
            to_email=to_email,
            employee_id=employee_id,
            temp_password=temp_password,
            employee_name=employee_name
        )
    except Exception as exc:
        print(f"Email sending failed for employee {employee_id}: {exc}")


# ================= EMPLOYEE CREATION =================
@router.post("/employees", response_model=EmployeeCreateResponse)
def create_employee(
    payload: EmployeeCreate,
    background_tasks: BackgroundTasks,
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

    background_tasks.add_task(
            _send_employee_credentials_safely,
            to_email=employee.email,
            employee_id=employee.employee_id,
            temp_password=temp_password,
            employee_name=employee.name
        )

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
            "created_by": task.created_by,
            "created_by_name": task.created_user.name if task.created_user else None,
            "created_by_profile_image": task.created_user.profile_image if task.created_user else None,
            "priority": task.priority,
            "status": task.status,
            "due_date": task.due_date,
            "estimated_hours": task.estimated_hours
        })

    return result
# ================= ATTENDANCE REPORT =================


def parse_iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD") from exc


def parse_time_on_date(target_date: date, value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None

    try:
        parsed_dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed_dt.tzinfo is None:
            parsed_dt = parsed_dt.replace(tzinfo=IST)
        return parsed_dt.astimezone(timezone.utc)
    except Exception:
        pass

    try:
        parts = raw.split(":")
        hour = int(parts[0])
        minute = int(parts[1])
        second = int(parts[2]) if len(parts) > 2 else 0
        return datetime(target_date.year, target_date.month, target_date.day, hour, minute, second, tzinfo=IST).astimezone(timezone.utc)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid time format. Use HH:MM, HH:MM:SS or ISO datetime") from exc


def compute_total_seconds(clock_in_time: Optional[datetime], clock_out_time: Optional[datetime]) -> int:
    if not clock_in_time or not clock_out_time:
        return 0
    if clock_out_time <= clock_in_time:
        return 0
    return calculate_work_seconds(clock_in_time, clock_out_time)


def get_holiday_dates_for_month(db: Session, month: int, year: int) -> set[date]:
    direct = db.query(Holiday).filter(extract("month", Holiday.date) == month, extract("year", Holiday.date) == year).all()
    repeating = db.query(Holiday).filter(Holiday.repeat_yearly == True, extract("month", Holiday.date) == month).all()
    result = {h.date for h in direct}
    for h in repeating:
        result.add(date(year, h.date.month, h.date.day))
    return result


def get_approved_leave_statuses_for_month(db: Session, user_id: int, month: int, year: int) -> dict[date, str]:
    first_day = date(year, month, 1)
    last_day = date(year, month, monthrange(year, month)[1])
    leaves = db.query(Leave).filter(
        Leave.user_id == user_id,
        Leave.status == "approved",
        Leave.start_date <= last_day,
        Leave.end_date >= first_day,
    ).all()

    leave_dates: dict[date, str] = {}
    for leave in leaves:
        start = max(leave.start_date, first_day)
        end = min(leave.end_date, last_day)
        current = start
        while current <= end:
            leave_dates[current] = "halfday" if leave.duration_type in {"first_half", "second_half"} else "leave"
            current = current.fromordinal(current.toordinal() + 1)
    return leave_dates


def get_leave_status_for_date(db: Session, user_id: int, target_date: date) -> Optional[str]:
    leave = db.query(Leave).filter(
        Leave.user_id == user_id,
        Leave.status == "approved",
        Leave.start_date <= target_date,
        Leave.end_date >= target_date,
    ).order_by(Leave.id.desc()).first()
    if not leave:
        return None
    return "halfday" if leave.duration_type in {"first_half", "second_half"} else "leave"


def normalize_status_value(raw_status: Optional[str]) -> Optional[str]:
    value = (raw_status or "").strip().lower()
    if not value:
        return None
    mapping = {
        "halfday_first": "halfday",
        "halfday_second": "halfday",
        "on_leave": "leave",
    }
    return mapping.get(value, value)


def parse_overtime_hours(value) -> float:
    if value is None or value == "":
        return 0.0
    try:
        parsed = float(value)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid overtime value") from exc
    if parsed < 0:
        raise HTTPException(status_code=400, detail="Overtime cannot be negative")
    return round(parsed, 2)


def infer_status_from_clock_times(
    *,
    clock_in_time: Optional[datetime],
    clock_out_time: Optional[datetime],
    total_seconds: int,
) -> tuple[str, Optional[str], bool]:
    inferred_status = "absent"
    inferred_half_day_type: Optional[str] = None
    inferred_is_late = False

    if clock_in_time:
        inferred_is_late = clock_in_time.astimezone(IST).time() > time(9, 30)

    # Half day if both times exist and worked seconds are less than 4 hours.
    if clock_in_time and clock_out_time and total_seconds < (4 * 3600):
        inferred_status = "halfday"
        hour = int(clock_in_time.astimezone(IST).strftime("%H"))
        inferred_half_day_type = "first_half" if hour < 13 else "second_half"
        inferred_is_late = False
    elif clock_in_time:
        inferred_status = "late" if inferred_is_late else "present"

    return inferred_status, inferred_half_day_type, inferred_is_late


def get_effective_day_status(
    row: Optional[Attendance],
    current_date: date,
    holiday_dates: set[date],
    leave_statuses: dict[date, str],
    now: datetime
) -> tuple[str, dict]:
    meta = get_attendance_status_meta(row, now) if row else {
        "status": "absent",
        "seconds": 0,
        "is_running": False,
        "is_late_entry": False,
        "is_overtime": False,
        "overtime_seconds": 0,
        "overtime_hours": 0,
        "half_day_type": None,
        "effective_clock_in_time": None,
    }

    manual_status = normalize_status_value(row.status if row else None)
    if row and row.is_manual_edit and manual_status:
        status = manual_status
    elif current_date in holiday_dates:
        status = "holiday"
    else:
        status = leave_statuses.get(current_date) or meta["status"]

    return status, meta


def status_from_attendance(attendance: Optional[Attendance]) -> str:
    if not attendance:
        return "absent"
    manual_status = normalize_status_value(attendance.status)
    if attendance.is_manual_edit and manual_status:
        return manual_status
    return get_attendance_status_meta(attendance)["status"]


def serialize_attendance(attendance: Optional[Attendance]) -> dict:
    if not attendance:
        return {}
    return {
        "id": attendance.id,
        "user_id": attendance.user_id,
        "date": attendance.date.isoformat(),
        "clock_in_time": attendance.clock_in_time.isoformat() if attendance.clock_in_time else None,
        "clock_out_time": attendance.clock_out_time.isoformat() if attendance.clock_out_time else None,
        "total_seconds": int(attendance.total_seconds or 0),
        "status": attendance.status,
        "overtime_hours": float(attendance.overtime_hours or 0),
        "half_day_type": attendance.half_day_type,
        "is_late": bool(attendance.is_late),
        "working_from": attendance.working_from,
        "location": attendance.location,
        "manual_override": bool(attendance.manual_override),
        "is_manual_edit": bool(attendance.is_manual_edit),
        "updated_by_admin_id": attendance.updated_by_admin_id,
        "edit_reason": attendance.edit_reason,
    }


def append_edit_log(
    db: Session,
    *,
    attendance_id: Optional[int],
    user_id: int,
    admin_id: int,
    target_date: date,
    action: str,
    reason: Optional[str],
    old_payload: dict,
    new_payload: dict,
) -> None:
    db.add(AttendanceEditLog(
        attendance_id=attendance_id,
        user_id=user_id,
        admin_id=admin_id,
        date=target_date,
        action=action,
        reason=reason,
        old_payload=json.dumps(old_payload or {}),
        new_payload=json.dumps(new_payload or {}),
        manual_override=True,
    ))


@router.get("/attendance")
def get_monthly_attendance(
    month: int,
    year: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    ensure_attendance_schema(db)
    now = datetime.now(timezone.utc)
    users = db.query(User).filter(User.role == "employee").all()
    days_in_month = monthrange(year, month)[1]
    holiday_dates = get_holiday_dates_for_month(db, month, year)
    result = []

    for user in users:
        auto_close_open_attendances_for_user(user.id, db, now=now)
        records = db.query(Attendance).filter(
            Attendance.user_id == user.id,
            extract("month", Attendance.date) == month,
            extract("year", Attendance.date) == year
        ).all()
        attendance_by_date = {r.date: r for r in records}
        leave_statuses = get_approved_leave_statuses_for_month(db, user.id, month, year)

        days_map = {}
        day_details = {}
        total_days = 0.0
        late_days = 0
        leave_days = 0
        holidays = 0
        overtime_hours_total = 0.0

        for day in range(1, days_in_month + 1):
            current_date = date(year, month, day)
            row = attendance_by_date.get(current_date)
            status, meta = get_effective_day_status(row, current_date, holiday_dates, leave_statuses, now)

            if status == "holiday":
                holidays += 1
            elif status == "leave":
                leave_days += 1
            elif status in {"present", "late", "in_progress"}:
                total_days += 1
                if status == "late":
                    late_days += 1
            elif status == "halfday":
                total_days += 0.5

            days_map[day] = status
            overtime_seconds = int(meta.get("overtime_seconds") or 0) if status not in {"holiday", "leave"} else 0
            overtime_hours = round(overtime_seconds / 3600, 2)
            overtime_hours_total += overtime_hours
            day_details[day] = {
                "status": status,
                "half_day_type": row.half_day_type if row else None,
                "manual_override": bool(row.manual_override) if row else False,
                "is_manual_edit": bool(row.is_manual_edit) if row else False,
                "is_late": bool(row.is_late) if row else False,
                "clock_in_time": meta["effective_clock_in_time"].isoformat() if row and meta.get("effective_clock_in_time") else None,
                "clock_out_time": row.clock_out_time.isoformat() if row and row.clock_out_time else None,
                "total_seconds": get_attendance_worked_seconds(row, now) if row else 0,
                "is_running": meta["is_running"] if row else False,
                "is_late_entry": meta["is_late_entry"] if row else False,
                "is_overtime": bool(overtime_seconds > 0),
                "overtime_seconds": overtime_seconds,
                "overtime_hours": overtime_hours,
            }

        working_days = max(days_in_month - holidays - leave_days, 0)
        attendance_percentage = round((total_days / working_days) * 100, 2) if working_days else 0.0
        absent_days = max(working_days - total_days, 0)

        result.append({
            "employee_id": user.id,
            "name": user.name,
            "department": user.department,
            "designation": user.designation,
            "profile_image": user.profile_image,
            "days": days_map,
            "day_details": day_details,
            "total_present_days": round(total_days, 2),
            "present_days": round(total_days, 2),
            "late_days": late_days,
            "leave_days": leave_days,
            "holidays": holidays,
            "absent_days": round(absent_days, 2),
            "overtime_hours_total": round(overtime_hours_total, 2),
            "attendance_percentage": attendance_percentage,
        })

    return result


@router.get("/attendance/details")
def get_attendance_details(
    user_id: int,
    date: str,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    ensure_attendance_schema(db)
    now = datetime.now(timezone.utc)
    target_date = parse_iso_date(date)
    auto_close_open_attendances_for_user(user_id, db, now=now)

    employee = db.query(User).filter(User.id == user_id, User.role == "employee").first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    is_holiday = db.query(Holiday).filter(
        or_(
            and_(Holiday.date == target_date, Holiday.repeat_yearly == False),
            and_(
                Holiday.repeat_yearly == True,
                extract("month", Holiday.date) == target_date.month,
                extract("day", Holiday.date) == target_date.day,
            ),
        )
    ).first() is not None

    attendance = db.query(Attendance).filter(
        Attendance.user_id == user_id,
        Attendance.date == target_date,
    ).first()
    leave_status = get_leave_status_for_date(db, user_id, target_date) if not is_holiday else None
    leave_statuses = {target_date: leave_status} if leave_status else {}
    status, meta = get_effective_day_status(
        attendance,
        target_date,
        {target_date} if is_holiday else set(),
        leave_statuses,
        now,
    )

    display_clock_in = meta.get("effective_clock_in_time") if attendance else None
    total_seconds = int(meta.get("seconds") or 0)

    return {
        "employee": {
            "id": employee.id,
            "name": employee.name,
            "designation": employee.designation,
        },
        "attendance_id": attendance.id if attendance else None,
        "date": target_date.isoformat(),
        "status": status,
        "clock_in_time": display_clock_in.isoformat() if display_clock_in else None,
        "clock_out_time": attendance.clock_out_time.isoformat() if attendance and attendance.clock_out_time else None,
        "total_seconds": total_seconds,
        "half_day_type": attendance.half_day_type if attendance else None,
        "is_late": bool(attendance.is_late) if attendance else False,
        "working_from": attendance.working_from if attendance else None,
        "location": attendance.location if attendance else None,
        "manual_override": bool(attendance.manual_override) if attendance else False,
        "is_manual_edit": bool(attendance.is_manual_edit) if attendance else False,
        "overtime_hours": float(attendance.overtime_hours or 0) if attendance else 0,
        "edit_reason": attendance.edit_reason if attendance else None,
        "is_active_tracker": meta["is_running"],
        "is_late_entry": meta["is_late_entry"],
        "is_overtime": meta["is_overtime"],
        "overtime_seconds": meta["overtime_seconds"],
    }


@router.post("/attendance/mark")
def mark_attendance(
    payload: dict,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    ensure_attendance_schema(db)

    try:
        user_id = int(payload.get("user_id"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="user_id is required") from exc
    if not payload.get("date"):
        raise HTTPException(status_code=400, detail="date is required")
    target_date = parse_iso_date(str(payload.get("date")))
    reason = payload.get("reason")
    raw_status = normalize_status_value(payload.get("status"))
    status = raw_status or "absent"
    if status not in {"present", "late", "absent", "leave", "halfday", "holiday"}:
        raise HTTPException(status_code=400, detail="Invalid status")

    employee = db.query(User).filter(User.id == user_id, User.role == "employee").first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    attendance = db.query(Attendance).filter(
        Attendance.user_id == user_id,
        Attendance.date == target_date,
    ).first()

    old_payload = serialize_attendance(attendance)

    clock_in_time = parse_time_on_date(target_date, payload.get("clock_in_time"))
    clock_out_time = parse_time_on_date(target_date, payload.get("clock_out_time"))
    if clock_in_time and clock_out_time and clock_out_time <= clock_in_time:
        raise HTTPException(status_code=400, detail="Clock-out must be later than clock-in")

    half_day_type = payload.get("half_day_type") or None
    if payload.get("status") in {"halfday_first", "halfday_second"}:
        half_day_type = "first_half" if payload.get("status") == "halfday_first" else "second_half"

    overtime_supplied = payload.get("overtime_hours") is not None and payload.get("overtime_hours") != ""
    manual_overtime_hours = parse_overtime_hours(payload.get("overtime_hours"))

    if not attendance:
        attendance = Attendance(user_id=user_id, date=target_date)
        db.add(attendance)
        db.flush()

    attendance.status = status
    attendance.clock_in_time = clock_in_time
    attendance.clock_out_time = clock_out_time
    attendance.half_day_type = half_day_type if status == "halfday" else None
    attendance.working_from = payload.get("working_from") or None
    attendance.location = payload.get("location") or None
    attendance.manual_override = True
    attendance.is_manual_edit = True
    attendance.updated_by_admin_id = admin.id
    attendance.edit_reason = reason

    if status in {"absent", "leave", "holiday"}:
        attendance.clock_in_time = None
        attendance.clock_out_time = None
        attendance.total_seconds = 0
        attendance.half_day_type = None
        attendance.is_late = False
    elif status == "halfday":
        if not attendance.half_day_type:
            attendance.half_day_type = "first_half"
        if not attendance.clock_in_time and not attendance.clock_out_time:
            if attendance.half_day_type == "second_half":
                attendance.clock_in_time = datetime(target_date.year, target_date.month, target_date.day, 14, 0, tzinfo=IST).astimezone(timezone.utc)
                attendance.clock_out_time = datetime(target_date.year, target_date.month, target_date.day, 18, 30, tzinfo=IST).astimezone(timezone.utc)
            else:
                attendance.clock_in_time = datetime(target_date.year, target_date.month, target_date.day, 9, 0, tzinfo=IST).astimezone(timezone.utc)
                attendance.clock_out_time = datetime(target_date.year, target_date.month, target_date.day, 13, 0, tzinfo=IST).astimezone(timezone.utc)
    else:
        if not attendance.clock_in_time:
            attendance.clock_in_time = datetime(target_date.year, target_date.month, target_date.day, 9, 0, tzinfo=IST).astimezone(timezone.utc)
        if not attendance.clock_out_time:
            attendance.clock_out_time = datetime(target_date.year, target_date.month, target_date.day, 18, 30, tzinfo=IST).astimezone(timezone.utc)

    attendance.total_seconds = compute_total_seconds(attendance.clock_in_time, attendance.clock_out_time)

    if status not in {"absent", "leave", "holiday"}:
        inferred_status, inferred_half_day_type, inferred_is_late = infer_status_from_clock_times(
            clock_in_time=attendance.clock_in_time,
            clock_out_time=attendance.clock_out_time,
            total_seconds=int(attendance.total_seconds or 0),
        )
        status = inferred_status
        attendance.status = status
        if status == "halfday":
            attendance.half_day_type = inferred_half_day_type or attendance.half_day_type or "first_half"
        else:
            attendance.half_day_type = None
        attendance.is_late = inferred_is_late
    else:
        attendance.status = status
        attendance.is_late = False

    auto_overtime_seconds = calculate_overtime_seconds(attendance, attendance.total_seconds, datetime.now(timezone.utc))
    attendance.overtime_hours = manual_overtime_hours if overtime_supplied else round(auto_overtime_seconds / 3600, 2)

    try:
        db.flush()
        new_payload = serialize_attendance(attendance)
        append_edit_log(
            db,
            attendance_id=attendance.id,
            user_id=user_id,
            admin_id=admin.id,
            target_date=target_date,
            action="update" if old_payload else "create",
            reason=reason,
            old_payload=old_payload,
            new_payload=new_payload,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    attendance_ws_manager.notify_attendance_change_threadsafe(user_id)

    meta = get_attendance_status_meta(attendance, datetime.now(timezone.utc))
    return {
        "message": "Attendance saved",
        "attendance_id": attendance.id,
        "status": status,
        "total_seconds": get_attendance_worked_seconds(attendance, datetime.now(timezone.utc)),
        "overtime_hours": float(attendance.overtime_hours or 0),
        "is_overtime": bool(meta["is_overtime"]),
        "is_late_entry": bool(meta["is_late_entry"]),
    }


@router.delete("/attendance/{attendance_id}")
def delete_attendance_entry(
    attendance_id: int,
    reason: Optional[str] = None,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    ensure_attendance_schema(db)
    attendance = db.query(Attendance).filter(Attendance.id == attendance_id).first()
    if not attendance:
        raise HTTPException(status_code=404, detail="Attendance not found")
    if not attendance.manual_override:
        raise HTTPException(status_code=400, detail="Only manual override attendance can be deleted")
    if attendance.clock_in_time and not attendance.clock_out_time:
        raise HTTPException(status_code=400, detail="Cannot delete active tracker attendance")

    old_payload = serialize_attendance(attendance)
    append_edit_log(
        db,
        attendance_id=attendance.id,
        user_id=attendance.user_id,
        admin_id=admin.id,
        target_date=attendance.date,
        action="delete",
        reason=reason,
        old_payload=old_payload,
        new_payload={},
    )
    db.delete(attendance)
    db.commit()
    attendance_ws_manager.notify_attendance_change_threadsafe(attendance.user_id)
    return {"message": "Attendance deleted"}


@router.post("/attendance/bulk-mark")
def bulk_mark_attendance(
    payload: dict,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    ensure_attendance_schema(db)
    employee_ids = payload.get("employee_ids") or []
    if not employee_ids:
        raise HTTPException(status_code=400, detail="employee_ids is required")

    status = (payload.get("status") or "").strip().lower()
    if not status:
        raise HTTPException(status_code=400, detail="status is required")

    if payload.get("date"):
        target_dates = [parse_iso_date(str(payload["date"]))]
    else:
        now_ist = datetime.now(timezone.utc).astimezone(IST)
        month = int(payload.get("month") or now_ist.month)
        year = int(payload.get("year") or now_ist.year)
        target_dates = [date(year, month, d) for d in range(1, monthrange(year, month)[1] + 1)]

    results = []
    for employee_id in employee_ids:
        for target_date in target_dates:
            try:
                response = mark_attendance({
                    "user_id": int(employee_id),
                    "date": target_date.isoformat(),
                    "clock_in_time": payload.get("clock_in_time"),
                    "clock_out_time": payload.get("clock_out_time"),
                    "half_day_type": payload.get("half_day_type"),
                    "is_late": payload.get("is_late"),
                    "working_from": payload.get("working_from"),
                    "location": payload.get("location"),
                    "overtime_hours": payload.get("overtime_hours"),
                    "reason": payload.get("reason"),
                    "status": status,
                }, db, admin)
                results.append({"user_id": employee_id, "date": target_date.isoformat(), "ok": True, "result": response})
            except HTTPException as exc:
                results.append({"user_id": employee_id, "date": target_date.isoformat(), "ok": False, "error": exc.detail})

    return {
        "message": "Bulk mark completed",
        "processed": len(results),
        "success": sum(1 for r in results if r["ok"]),
        "failed": sum(1 for r in results if not r["ok"]),
        "results": results,
    }


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
    now = datetime.now(timezone.utc)
    month_start = datetime(year, month, 1, tzinfo=timezone.utc)
    month_end = datetime(
        year + 1 if month == 12 else year,
        1 if month == 12 else month + 1,
        1,
        tzinfo=timezone.utc
    )

    for user in users:
        # Keep attendance rows consistent by closing stale active sessions server-side.
        auto_close_open_attendances_for_user(user.id, db, now=now)

        attendance_records = db.query(Attendance).filter(
            Attendance.user_id == user.id,
            extract("month", Attendance.date) == month,
            extract("year", Attendance.date) == year
        ).all()
        attendance_seconds = 0
        for record in attendance_records:
            total = int(record.total_seconds or 0)
            if record.clock_in_time:
                attendance_day_end = datetime.combine(record.date, time.max, tzinfo=timezone.utc)
                total += int((min(now, attendance_day_end) - record.clock_in_time).total_seconds())
            attendance_seconds += max(total, 0)

        logs = db.query(TaskTimeLog).filter(
            TaskTimeLog.user_id == user.id,
            TaskTimeLog.start_time < month_end,
            or_(TaskTimeLog.end_time == None, TaskTimeLog.end_time >= month_start)
        ).all()
        task_seconds = 0
        for log in logs:
            segment_start = max(log.start_time, month_start)
            segment_end = min(log.end_time or now, month_end)
            if segment_end > segment_start:
                task_seconds += int((segment_end - segment_start).total_seconds())

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
    try:
        validated = AdminProfileUpdateSchema(
            name=name,
            email=email,
            phone=phone,
            department=department,
            designation=designation,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    
    # Check email uniqueness if changing
    if email is not None and not validated.email:
        raise HTTPException(status_code=422, detail="Email is required")

    if validated.email and validated.email != current_admin.email:
        existing = db.query(User).filter(User.email == validated.email).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already exists")
        current_admin.email = validated.email
    
    # Update basic info
    if validated.name:
        current_admin.name = validated.name
    if phone is not None:
        current_admin.phone = validated.phone
    if department is not None:
        current_admin.department = validated.department
    if designation is not None:
        current_admin.designation = validated.designation
    
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
