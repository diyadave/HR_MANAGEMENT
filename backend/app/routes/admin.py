import secrets
import json
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from sqlalchemy import and_, extract, inspect, or_, text
from typing import List, Optional
from datetime import date, datetime, time, timezone, timedelta
from calendar import monthrange

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
from app.services.attendance_service import auto_close_open_attendances_for_user

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
OFFICE_START = time(9, 0)
LATE_AFTER = time(9, 30)


def ensure_attendance_schema(db: Session) -> None:
    inspector = inspect(db.bind)
    existing_cols = {c["name"] for c in inspector.get_columns("attendance_logs")}
    ddl = {
        "half_day_type": "ALTER TABLE attendance_logs ADD COLUMN half_day_type VARCHAR(20)",
        "is_late": "ALTER TABLE attendance_logs ADD COLUMN is_late BOOLEAN DEFAULT FALSE NOT NULL",
        "working_from": "ALTER TABLE attendance_logs ADD COLUMN working_from VARCHAR(30)",
        "location": "ALTER TABLE attendance_logs ADD COLUMN location VARCHAR(255)",
        "manual_override": "ALTER TABLE attendance_logs ADD COLUMN manual_override BOOLEAN DEFAULT FALSE NOT NULL",
        "edit_reason": "ALTER TABLE attendance_logs ADD COLUMN edit_reason TEXT",
    }
    for col, statement in ddl.items():
        if col in existing_cols:
            continue
        try:
            db.execute(text(statement))
            db.commit()
        except Exception:
            db.rollback()


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
            parsed_dt = parsed_dt.replace(tzinfo=timezone.utc)
        return parsed_dt.astimezone(timezone.utc)
    except Exception:
        pass

    try:
        parts = raw.split(":")
        hour = int(parts[0])
        minute = int(parts[1])
        second = int(parts[2]) if len(parts) > 2 else 0
        return datetime(target_date.year, target_date.month, target_date.day, hour, minute, second, tzinfo=timezone.utc)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid time format. Use HH:MM, HH:MM:SS or ISO datetime") from exc


def compute_total_seconds(clock_in_time: Optional[datetime], clock_out_time: Optional[datetime]) -> int:
    if not clock_in_time or not clock_out_time:
        return 0
    if clock_out_time <= clock_in_time:
        return 0
    return int((clock_out_time - clock_in_time).total_seconds())


def infer_clock_in_time(attendance: Optional[Attendance]) -> Optional[datetime]:
    if not attendance:
        return None
    if attendance.clock_in_time:
        return attendance.clock_in_time
    if attendance.clock_out_time and (attendance.total_seconds or 0) > 0:
        return attendance.clock_out_time - timedelta(seconds=int(attendance.total_seconds or 0))
    return None


def get_holiday_dates_for_month(db: Session, month: int, year: int) -> set[date]:
    direct = db.query(Holiday).filter(extract("month", Holiday.date) == month, extract("year", Holiday.date) == year).all()
    repeating = db.query(Holiday).filter(Holiday.repeat_yearly == True, extract("month", Holiday.date) == month).all()
    result = {h.date for h in direct}
    for h in repeating:
        result.add(date(year, h.date.month, h.date.day))
    return result


def get_approved_leave_dates_for_month(db: Session, user_id: int, month: int, year: int) -> set[date]:
    first_day = date(year, month, 1)
    last_day = date(year, month, monthrange(year, month)[1])
    leaves = db.query(Leave).filter(
        Leave.user_id == user_id,
        Leave.status == "approved",
        Leave.start_date <= last_day,
        Leave.end_date >= first_day,
    ).all()

    leave_dates = set()
    for leave in leaves:
        start = max(leave.start_date, first_day)
        end = min(leave.end_date, last_day)
        for day in range(start.day, end.day + 1):
            leave_dates.add(date(year, month, day))
    return leave_dates


def status_from_attendance(attendance: Optional[Attendance]) -> str:
    if not attendance:
        return "absent"

    if (attendance.working_from or "").lower() == "holiday":
        return "holiday"

    if attendance.half_day_type in {"first_half", "second_half"}:
        return "halfday"

    # Manual late override should remain late even if computed hours are below full-day threshold.
    if attendance.is_late and attendance.clock_in_time:
        return "late"

    # Live tracker awareness: if currently clocked-in, reflect status immediately.
    if attendance.clock_in_time and not attendance.clock_out_time:
        clock_in_local = attendance.clock_in_time.astimezone(timezone.utc).time()
        return "late" if clock_in_local > LATE_AFTER else "present"

    total_seconds = int(attendance.total_seconds or 0)
    if total_seconds >= 9 * 3600:
        status = "present"
    elif total_seconds >= 4 * 3600:
        status = "halfday"
    else:
        status = "absent"

    if attendance.clock_in_time and attendance.clock_in_time.astimezone(timezone.utc).time() > LATE_AFTER and status == "present":
        status = "late"
    if attendance.is_late and attendance.clock_in_time:
        status = "late"
    return status


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
        "half_day_type": attendance.half_day_type,
        "is_late": bool(attendance.is_late),
        "working_from": attendance.working_from,
        "location": attendance.location,
        "manual_override": bool(attendance.manual_override),
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
    users = db.query(User).filter(User.role == "employee").all()
    days_in_month = monthrange(year, month)[1]
    holiday_dates = get_holiday_dates_for_month(db, month, year)
    result = []

    for user in users:
        records = db.query(Attendance).filter(
            Attendance.user_id == user.id,
            extract("month", Attendance.date) == month,
            extract("year", Attendance.date) == year
        ).all()
        attendance_by_date = {r.date: r for r in records}
        leave_dates = get_approved_leave_dates_for_month(db, user.id, month, year)

        days_map = {}
        day_details = {}
        present_days = 0.0
        half_days = 0
        leave_days = 0
        holidays = 0

        for day in range(1, days_in_month + 1):
            current_date = date(year, month, day)
            row = attendance_by_date.get(current_date)

            if current_date in holiday_dates:
                status = "holiday"
                holidays += 1
            elif current_date in leave_dates:
                status = "leave"
                leave_days += 1
            else:
                status = status_from_attendance(row)
                if status in {"present", "late"}:
                    present_days += 1
                elif status == "halfday":
                    half_days += 1

            days_map[day] = status
            day_details[day] = {
                "status": status,
                "half_day_type": row.half_day_type if row else None,
                "manual_override": bool(row.manual_override) if row else False,
                "is_late": bool(row.is_late) if row else False,
            }

        working_days = max(days_in_month - holidays - leave_days, 0)
        score = present_days + (0.5 * half_days)
        attendance_percentage = round((score / working_days) * 100, 2) if working_days else 0.0
        absent_days = max(working_days - int(present_days) - half_days, 0)

        result.append({
            "employee_id": user.id,
            "name": user.name,
            "department": user.department,
            "designation": user.designation,
            "profile_image": user.profile_image,
            "days": days_map,
            "day_details": day_details,
            "total_present_days": present_days,
            "present_days": present_days,
            "half_days": half_days,
            "leave_days": leave_days,
            "holidays": holidays,
            "absent_days": absent_days,
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
    target_date = parse_iso_date(date)

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

    has_approved_leave = db.query(Leave).filter(
        Leave.user_id == user_id,
        Leave.status == "approved",
        Leave.start_date <= target_date,
        Leave.end_date >= target_date,
    ).first() is not None

    attendance = db.query(Attendance).filter(
        Attendance.user_id == user_id,
        Attendance.date == target_date,
    ).first()

    if is_holiday:
        status = "holiday"
    elif has_approved_leave:
        status = "leave"
    else:
        status = status_from_attendance(attendance)

    display_clock_in = infer_clock_in_time(attendance)

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
        "total_seconds": int(attendance.total_seconds or 0) if attendance else 0,
        "half_day_type": attendance.half_day_type if attendance else None,
        "is_late": bool(attendance.is_late) if attendance else False,
        "working_from": attendance.working_from if attendance else None,
        "location": attendance.location if attendance else None,
        "manual_override": bool(attendance.manual_override) if attendance else False,
        "edit_reason": attendance.edit_reason if attendance else None,
        "is_active_tracker": bool(attendance and attendance.clock_in_time and not attendance.clock_out_time),
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
    status = (payload.get("status") or "").strip().lower() or None

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

    has_approved_leave = db.query(Leave).filter(
        Leave.user_id == user_id,
        Leave.status == "approved",
        Leave.start_date <= target_date,
        Leave.end_date >= target_date,
    ).first() is not None

    if (is_holiday or has_approved_leave) and status != "holiday":
        raise HTTPException(status_code=400, detail="Cannot edit attendance for holiday/approved leave")

    attendance = db.query(Attendance).filter(
        Attendance.user_id == user_id,
        Attendance.date == target_date,
    ).first()

    old_payload = serialize_attendance(attendance)

    if not attendance:
        attendance = Attendance(user_id=user_id, date=target_date)
        db.add(attendance)
        db.flush()

    attendance.clock_in_time = parse_time_on_date(target_date, payload.get("clock_in_time"))
    attendance.clock_out_time = parse_time_on_date(target_date, payload.get("clock_out_time"))
    attendance.half_day_type = payload.get("half_day_type") or None
    attendance.is_late = bool(payload.get("is_late")) if payload.get("is_late") is not None else False
    attendance.working_from = payload.get("working_from") or None
    attendance.location = payload.get("location") or None
    attendance.manual_override = True
    attendance.edit_reason = reason

    if status == "absent":
        attendance.clock_in_time = None
        attendance.clock_out_time = None
        attendance.total_seconds = 0
        attendance.half_day_type = None
        attendance.is_late = False
    elif status in {"halfday", "halfday_first", "halfday_second"}:
        attendance.half_day_type = "first_half" if status == "halfday_first" else (
            "second_half" if status == "halfday_second" else (attendance.half_day_type or "first_half")
        )
        attendance.is_late = False
        if not attendance.clock_in_time and not attendance.clock_out_time:
            if attendance.half_day_type == "second_half":
                attendance.clock_in_time = datetime(target_date.year, target_date.month, target_date.day, 14, 0, tzinfo=timezone.utc)
                attendance.clock_out_time = datetime(target_date.year, target_date.month, target_date.day, 18, 0, tzinfo=timezone.utc)
            else:
                attendance.clock_in_time = datetime(target_date.year, target_date.month, target_date.day, 9, 0, tzinfo=timezone.utc)
                attendance.clock_out_time = datetime(target_date.year, target_date.month, target_date.day, 13, 0, tzinfo=timezone.utc)
    elif status == "late":
        attendance.half_day_type = None
        attendance.is_late = True
        if not attendance.clock_in_time:
            attendance.clock_in_time = datetime(target_date.year, target_date.month, target_date.day, 9, 45, tzinfo=timezone.utc)
        if not attendance.clock_out_time:
            attendance.clock_out_time = datetime(target_date.year, target_date.month, target_date.day, 18, 0, tzinfo=timezone.utc)
    elif status == "present":
        attendance.half_day_type = None
        attendance.is_late = False
        if not attendance.clock_in_time:
            attendance.clock_in_time = datetime(target_date.year, target_date.month, target_date.day, 9, 0, tzinfo=timezone.utc)
        if not attendance.clock_out_time:
            attendance.clock_out_time = datetime(target_date.year, target_date.month, target_date.day, 18, 0, tzinfo=timezone.utc)
    elif status == "holiday":
        attendance.clock_in_time = None
        attendance.clock_out_time = None
        attendance.total_seconds = 0
        attendance.half_day_type = None
        attendance.is_late = False
        attendance.working_from = "holiday"

    if attendance.clock_in_time and attendance.clock_out_time:
        attendance.total_seconds = compute_total_seconds(attendance.clock_in_time, attendance.clock_out_time)
    else:
        attendance.total_seconds = int(attendance.total_seconds or 0)

    if attendance.clock_in_time and attendance.clock_in_time.astimezone(timezone.utc).time() > LATE_AFTER:
        attendance.is_late = True

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

    return {
        "message": "Attendance saved",
        "attendance_id": attendance.id,
        "status": status_from_attendance(attendance),
        "total_seconds": int(attendance.total_seconds or 0),
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
        month = int(payload.get("month") or datetime.now(timezone.utc).month)
        year = int(payload.get("year") or datetime.now(timezone.utc).year)
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
