from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_
from datetime import datetime, timezone
from fastapi import Query
from calendar import monthrange

from app.database.session import get_db
from app.core.dependencies import get_current_user
from app.models.attendance import Attendance
from datetime import time
from app.models.task_time_log import TaskTimeLog
from app.services.attendance_service import (
    clock_in,
    clock_out,
    auto_close_open_attendances_for_user,
    calculate_work_seconds
)

router = APIRouter()


# ---------------- CLOCK IN ----------------
@router.post("/clock-in")
def clock_in_route(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return clock_in(current_user, db)


# ---------------- CLOCK OUT ----------------
@router.post("/clock-out")
def clock_out_route(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    now = datetime.now(timezone.utc)
    auto_close_open_attendances_for_user(current_user.id, db, now=now)

    attendance = db.query(Attendance).filter(
        Attendance.user_id == current_user.id,
        Attendance.clock_in_time != None
    ).order_by(Attendance.date.desc()).first()

    if not attendance:
        today_attendance = db.query(Attendance).filter(
            Attendance.user_id == current_user.id,
            Attendance.date == now.date()
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
    now = datetime.now(timezone.utc)
    today = now.date()

    auto_close_open_attendances_for_user(current_user.id, db, now=now)

    attendance = db.query(Attendance).filter(
        Attendance.user_id == current_user.id,
        Attendance.date == today
    ).first()

    if not attendance:
        return {"worked_seconds": 0, "is_running": False}

    worked_seconds = attendance.total_seconds or 0

    if attendance.clock_in_time and not attendance.clock_out_time:
        worked_seconds += calculate_work_seconds(attendance.clock_in_time, now)

    return {
        "worked_seconds": worked_seconds,
        "is_running": attendance.clock_in_time is not None and attendance.clock_out_time is None
    }


# ---------------- SUMMARY ----------------
@router.get("/summary")
def attendance_summary(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    now = datetime.now(timezone.utc)
    today = now.date()

    auto_close_open_attendances_for_user(current_user.id, db, now=now)

    attendance = db.query(Attendance).filter(
        Attendance.user_id == current_user.id,
        Attendance.date == today
    ).first()

    attendance_seconds = 0

    if attendance:
        attendance_seconds = attendance.total_seconds or 0

        if attendance.clock_in_time and not attendance.clock_out_time:
            attendance_seconds += calculate_work_seconds(attendance.clock_in_time, now)

    # -------- TASK TIME --------
    start_of_day = datetime.combine(today, time.min, tzinfo=timezone.utc)
    end_of_day = datetime.combine(today, time.max, tzinfo=timezone.utc)

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
    overtime_seconds = max(0, attendance_seconds - (9 * 3600))

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
    now = datetime.now(timezone.utc)
    auto_close_open_attendances_for_user(current_user.id, db, now=now)
    
    target_month = month or now.month
    target_year = year or now.year

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

    result = []
    present_days = 0
    late_days = 0
    total_work_seconds = 0

    for r in records:
        seconds = r.total_seconds or 0
        
        # Add ongoing work if clocked in but not out
        if r.clock_in_time and not r.clock_out_time:
            seconds += calculate_work_seconds(r.clock_in_time, now)

        # Determine status based on attendance record
        if r.clock_in_time:
            if seconds >= 1 * 3600:  # Worked at least 1 hour
                status = "present"
                present_days += 1
            else:
                status = "absent"  # Less than 1 hour worked
        else:
            status = "absent"  # No clock-in

        # Check for late arrival (after 9:10 AM)
        if r.clock_in_time:
            clock_in_local = r.clock_in_time.astimezone(timezone.utc)
            if clock_in_local.hour > 9 or (clock_in_local.hour == 9 and clock_in_local.minute > 10):
                late_days += 1
                if status == "present":
                    status = "late"

        total_work_seconds += max(0, seconds)

        result.append({
            "date": str(r.date),
            "clock_in_time": r.clock_in_time.isoformat() if r.clock_in_time else None,
            "clock_out_time": r.clock_out_time.isoformat() if r.clock_out_time else None,
            "total_seconds": max(0, seconds),
            "status": status
        })

    days_in_month = monthrange(target_year, target_month)[1]
    avg_hours = (total_work_seconds / max(len(records), 1)) / 3600 if records else 0
    
    # Calculate absent days (days with no attendance record or absent status)
    absent_days = 0
    for day in range(1, days_in_month + 1):
        current_date = datetime(target_year, target_month, day).date()
        attendance_record = next((r for r in records if r.date == current_date), None)
        
        if not attendance_record:
            # Weekend check (optional - you might want to exclude weekends)
            # if current_date.weekday() < 5:  # Monday=0, Sunday=6
            absent_days += 1
        elif attendance_record.clock_in_time is None:
            absent_days += 1

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