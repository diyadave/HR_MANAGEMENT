from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
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
        return {"worked_seconds": 0}

    worked_seconds = attendance.total_seconds or 0

    if attendance.clock_in_time:
        worked_seconds += calculate_work_seconds(attendance.clock_in_time, now)

    return {
        "worked_seconds": worked_seconds,
        "is_running": attendance.clock_in_time is not None
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

        if attendance.clock_in_time:
            attendance_seconds += calculate_work_seconds(attendance.clock_in_time, now)

    # -------- TASK TIME --------
   

    start_of_day = datetime.combine(today, time.min, tzinfo=timezone.utc)
    end_of_day = datetime.combine(today, time.max, tzinfo=timezone.utc)

    task_logs = db.query(TaskTimeLog).filter(
        TaskTimeLog.user_id == current_user.id,
        TaskTimeLog.start_time >= start_of_day,
        TaskTimeLog.start_time <= end_of_day
    ).all()

    task_seconds = 0
    now = datetime.now(timezone.utc)

    for log in task_logs:
        if log.end_time:
            task_seconds += int(
                (log.end_time - log.start_time).total_seconds()
            )
        else:
            task_seconds += int(
                (now - log.start_time).total_seconds()
            )

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

    records = db.query(Attendance).filter(
        Attendance.user_id == current_user.id,
        Attendance.date >= datetime(target_year, target_month, 1, tzinfo=timezone.utc).date(),
        Attendance.date <= datetime(
            target_year,
            target_month,
            monthrange(target_year, target_month)[1],
            tzinfo=timezone.utc
        ).date()
    ).order_by(Attendance.date.desc()).all()

    result = []
    present_days = 0
    late_days = 0
    total_work_seconds = 0

    for r in records:
        seconds = r.total_seconds or 0
        if r.clock_in_time and not r.clock_out_time:
            seconds += calculate_work_seconds(r.clock_in_time, now)

        if seconds >= 9 * 3600:
            status = "present"
            present_days += 1
        elif seconds >= 4 * 3600:
            status = "halfday"
            present_days += 0.5
        else:
            status = "absent"

        if r.clock_in_time and r.clock_in_time.hour >= 9 and r.clock_in_time.minute > 10:
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
    absent_days = max(days_in_month - int(present_days), 0)

    return {
        "month": target_month,
        "year": target_year,
        "records": result,
        "stats": {
            "present_days": round(present_days, 1),
            "absent_days": absent_days,
            "late_days": late_days,
            "avg_hours": f"{avg_hours:.1f}h"
        }
    }
