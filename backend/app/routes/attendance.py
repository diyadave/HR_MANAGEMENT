from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.database.session import get_db
from app.core.dependencies import get_current_user
from app.models.attendance import Attendance
from datetime import time, timezone
from app.models.task_time_log import TaskTimeLog
from app.services.attendance_service import (
    clock_in,
    clock_out,
    auto_close_if_needed
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
    today = datetime.now(timezone.utc).date()

    attendance = db.query(Attendance).filter(
        Attendance.user_id == current_user.id,
        Attendance.date == today
    ).first()

    if not attendance or not attendance.clock_in_time:
        raise HTTPException(status_code=400, detail="Not clocked in")

    clock_out(attendance, db)
    return {"message": "Clocked out successfully"}


# ---------------- ACTIVE ATTENDANCE ----------------
@router.get("/active")
def active_attendance(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    today = datetime.now(timezone.utc).date()

    attendance = db.query(Attendance).filter(
        Attendance.user_id == current_user.id,
        Attendance.date == today
    ).first()

    if not attendance:
        return {"worked_seconds": 0}

    auto_close_if_needed(attendance, db)

    worked_seconds = attendance.total_seconds or 0

    if attendance.clock_in_time:
        now = datetime.now(timezone.utc)
        worked_seconds += int(
            (now - attendance.clock_in_time).total_seconds()
        )

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
    today = datetime.now(timezone.utc).date()

    attendance = db.query(Attendance).filter(
        Attendance.user_id == current_user.id,
        Attendance.date == today
    ).first()

    attendance_seconds = 0

    if attendance:
        attendance_seconds = attendance.total_seconds or 0

        if attendance.clock_in_time:
            now = datetime.now(timezone.utc)
            attendance_seconds += int(
                (now - attendance.clock_in_time).total_seconds()
            )

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