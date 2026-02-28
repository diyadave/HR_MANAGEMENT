from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import extract, or_, inspect, text
from datetime import datetime, timezone
from fastapi import Query
from datetime import date as date_cls
from calendar import monthrange

from app.database.session import get_db
from app.core.dependencies import get_current_user
from app.models.attendance import Attendance
from app.models.holiday import Holiday
from app.models.leave import Leave
from datetime import time
from app.models.task_time_log import TaskTimeLog
from app.services.attendance_service import (
    clock_in,
    clock_out,
    auto_close_open_attendances_for_user,
    calculate_overtime_seconds,
    ensure_attendance_schema,
    get_attendance_worked_seconds,
    get_attendance_status_meta,
    get_clock_in_lock_reason,
    get_ist_date,
    IST
)

router = APIRouter()


def _holiday_dates_for_month(db: Session, month: int, year: int) -> set[date_cls]:
    direct = db.query(Holiday).filter(
        extract("month", Holiday.date) == month,
        extract("year", Holiday.date) == year
    ).all()
    repeating = db.query(Holiday).filter(
        Holiday.repeat_yearly == True,
        extract("month", Holiday.date) == month
    ).all()
    out = {h.date for h in direct}
    for h in repeating:
        out.add(date_cls(year, h.date.month, h.date.day))
    return out


def _approved_leave_statuses_for_month(db: Session, user_id: int, month: int, year: int) -> dict[date_cls, str]:
    inspector = inspect(db.bind)
    leave_cols = {c["name"] for c in inspector.get_columns("leaves")}
    if "leave_hours" not in leave_cols:
        try:
            db.execute(text("ALTER TABLE leaves ADD COLUMN leave_hours DOUBLE PRECISION"))
            db.commit()
        except Exception:
            db.rollback()

    first_day = date_cls(year, month, 1)
    last_day = date_cls(year, month, monthrange(year, month)[1])
    leaves = db.query(Leave).filter(
        Leave.user_id == user_id,
        Leave.status == "approved",
        Leave.start_date <= last_day,
        Leave.end_date >= first_day
    ).all()
    out: dict[date_cls, str] = {}
    for leave in leaves:
        start = max(leave.start_date, first_day)
        end = min(leave.end_date, last_day)
        current = start
        while current <= end:
            if leave.duration_type in {"first_half", "second_half"}:
                out[current] = "halfday"
            elif (
                leave.duration_type == "duration"
                and leave.start_date == leave.end_date
            ):
                out[current] = "hourly_leave"
            else:
                out[current] = "leave"
            current = current.fromordinal(current.toordinal() + 1)
    return out


# ---------------- CLOCK IN ----------------
@router.post("/clock-in")
def clock_in_route(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    ensure_attendance_schema(db)
    return clock_in(current_user, db)


# ---------------- CLOCK OUT ----------------
@router.post("/clock-out")
def clock_out_route(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    ensure_attendance_schema(db)
    now = datetime.now(timezone.utc)
    today = get_ist_date(now)
    auto_close_open_attendances_for_user(current_user.id, db, now=now)

    attendance = db.query(Attendance).filter(
        Attendance.user_id == current_user.id,
        Attendance.clock_in_time != None,
        Attendance.clock_out_time == None
    ).order_by(Attendance.date.desc()).first()

    if not attendance:
        today_attendance = db.query(Attendance).filter(
            Attendance.user_id == current_user.id,
            Attendance.date == today
        ).first()
        if today_attendance and today_attendance.clock_out_time:
            return {"message": "Already clocked out", "auto_closed": True}
        raise HTTPException(status_code=400, detail="Not clocked in")

    clock_out(attendance, db)
    return {"message": "Clocked out successfully"}


# ---------------- ACTIVE ATTENDANCE ----------------
@router.get("/active")
def active_attendance(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    ensure_attendance_schema(db)
    now = datetime.now(timezone.utc)
    today = get_ist_date(now)

    auto_close_open_attendances_for_user(current_user.id, db, now=now)

    attendance = db.query(Attendance).filter(
    Attendance.user_id == current_user.id,
    Attendance.date == today
    ).first()
    lock_reason = get_clock_in_lock_reason(current_user, db, now=now)
    if not attendance:
        return {"worked_seconds": 0, "is_running": False, "clock_in_locked": bool(lock_reason), "clock_in_lock_reason": lock_reason}

    if attendance.date != today:
        return {"worked_seconds": 0, "is_running": False, "clock_in_locked": bool(lock_reason), "clock_in_lock_reason": lock_reason}

    worked_seconds = attendance.total_seconds or 0
    worked_seconds = get_attendance_worked_seconds(attendance, now)

    return {
        "worked_seconds": worked_seconds,
        "is_running": attendance.clock_in_time is not None and attendance.clock_out_time is None,
        "clock_in_locked": bool(lock_reason),
        "clock_in_lock_reason": lock_reason
    }


# ---------------- SUMMARY ----------------
@router.get("/summary")
def attendance_summary(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    ensure_attendance_schema(db)
    now = datetime.now(timezone.utc)
    today = get_ist_date(now)

    auto_close_open_attendances_for_user(current_user.id, db, now=now)

    attendance = db.query(Attendance).filter(
        Attendance.user_id == current_user.id,
        Attendance.date == today
    ).first()

    attendance_seconds = get_attendance_worked_seconds(attendance, now)

    # -------- TASK TIME --------
    start_of_day = datetime.combine(today, time.min, tzinfo=IST).astimezone(timezone.utc)
    end_of_day = datetime.combine(today, time.max, tzinfo=IST).astimezone(timezone.utc)

    task_logs = db.query(TaskTimeLog).filter(
        TaskTimeLog.user_id == current_user.id,
        TaskTimeLog.start_time <= end_of_day,
        or_(TaskTimeLog.end_time == None, TaskTimeLog.end_time >= start_of_day)
    ).all()

    task_seconds = 0
    for log in task_logs:
        segment_start = max(log.start_time, start_of_day)
        segment_end = min(log.end_time or now, end_of_day)
        if segment_end > segment_start:
            task_seconds += int((segment_end - segment_start).total_seconds())

    idle_seconds = max(attendance_seconds - task_seconds, 0)
    overtime_seconds = calculate_overtime_seconds(attendance, attendance_seconds, now)

    return {
        "attendance_seconds": attendance_seconds,
        "task_seconds": task_seconds,
        "idle_seconds": idle_seconds,
        "overtime_seconds": overtime_seconds
    }


# ---------------- HISTORY ----------------
@router.get("/history")
def attendance_history(
    month: int = Query(default=None, ge=1, le=12),
    year: int = Query(default=None, ge=2000, le=2100),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    ensure_attendance_schema(db)
    now = datetime.now(timezone.utc)
    auto_close_open_attendances_for_user(current_user.id, db, now=now)
    
    now_ist = now.astimezone(IST)
    target_month = month or now_ist.month
    target_year = year or now_ist.year

    # Get first and last day of the month
    first_day = datetime(target_year, target_month, 1, tzinfo=timezone.utc).date()
    last_day = datetime(
        target_year,
        target_month,
        monthrange(target_year, target_month)[1],
        tzinfo=timezone.utc
    ).date()

    records = db.query(Attendance).filter(
        Attendance.user_id == current_user.id,
        Attendance.date >= first_day,
        Attendance.date <= last_day
    ).order_by(Attendance.date.desc()).all()
    records_by_date = {r.date: r for r in records}
    holiday_dates = _holiday_dates_for_month(db, target_month, target_year)
    leave_statuses = _approved_leave_statuses_for_month(db, current_user.id, target_month, target_year)

    result = []
    present_days = 0
    late_days = 0
    total_work_seconds = 0
    absent_days = 0
    days_in_month = monthrange(target_year, target_month)[1]

    for day in range(1, days_in_month + 1):
        current_date = datetime(target_year, target_month, day).date()
        row = records_by_date.get(current_date)
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

        leave_status = leave_statuses.get(current_date)

        if current_date in holiday_dates:
            status = "holiday"
        elif leave_status:
            status = "hourly_leave" if leave_status == "hourly_leave" and meta["status"] == "late" else leave_status
        else:
            status = meta["status"]

        seconds = int(meta["seconds"] or 0) if status not in {"holiday", "leave"} else 0
        if status in {"present", "in_progress"}:
            present_days += 1
        elif status == "late":
            late_days += 1
            present_days += 1
        elif status == "hourly_leave":
            late_days += 1
            present_days += 1
        elif status == "halfday":
            present_days += 0.5
        elif status == "absent":
            absent_days += 1

        total_work_seconds += max(0, seconds)

        result.append({
            "date": str(current_date),
            "clock_in_time": meta["effective_clock_in_time"].isoformat() if meta.get("effective_clock_in_time") else None,
            "clock_out_time": row.clock_out_time.isoformat() if row and row.clock_out_time else None,
            "total_seconds": max(0, seconds),
            "status": status,
            "is_running": bool(meta["is_running"]) if status not in {"holiday", "leave"} else False,
            "is_late_entry": bool(meta["is_late_entry"]) if status not in {"holiday", "leave"} else False,
            "is_overtime": bool(meta["is_overtime"]) if status not in {"holiday", "leave"} else False,
            "overtime_seconds": int(meta.get("overtime_seconds") or 0) if status not in {"holiday", "leave"} else 0,
            "overtime_hours": float(meta.get("overtime_hours") or 0) if status not in {"holiday", "leave"} else 0,
            "half_day_type": meta["half_day_type"] if status == "halfday" else None
        })

    avg_hours = (total_work_seconds / max(days_in_month - absent_days, 1)) / 3600 if result else 0
    result.sort(key=lambda item: item["date"], reverse=True)

    return {
        "month": target_month,
        "year": target_year,
        "records": result,
        "stats": {
            "present_days": present_days,
            "absent_days": absent_days,
            "late_days": late_days,
            "avg_hours": f"{avg_hours:.1f}h"
        }
    }
