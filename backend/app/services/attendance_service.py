from datetime import datetime, timedelta, date, timezone
from fastapi import HTTPException
from app.models.attendance import Attendance
from app.models.task_time_log import TaskTimeLog

MAX_WORK_SECONDS = 9 * 3600  # 9 hours


# -------------------------------------------------
# CLOCK IN
# -------------------------------------------------
def clock_in(current_user, db):

    now = datetime.now(timezone.utc)
    today = now.date()

    # 🚫 1PM–2PM break restriction
    if 13 <= now.hour < 14:
        raise HTTPException(
            status_code=400,
            detail="Break time (1PM–2PM). Clock-in not allowed."
        )

    attendance = db.query(Attendance).filter(
        Attendance.user_id == current_user.id,
        Attendance.date == today
    ).first()

    # 🆕 First clock-in of day
    if not attendance:
        attendance = Attendance(
            user_id=current_user.id,
            date=today,
            clock_in_time=now,
            total_seconds=0
        )
        db.add(attendance)
        db.commit()
        db.refresh(attendance)
        return attendance

    # 🚫 Already running
    if attendance.clock_in_time is not None:
        raise HTTPException(status_code=400, detail="Already clocked in")

    # 🚫 Already completed 9 hours
    if attendance.total_seconds >= MAX_WORK_SECONDS:
        raise HTTPException(
            status_code=400,
            detail="9 working hours already completed."
        )

    # ✅ Resume same day
    attendance.clock_in_time = now
    db.commit()
    db.refresh(attendance)

    return attendance


# -------------------------------------------------
# CLOCK OUT
# -------------------------------------------------
def clock_out(attendance, db):

    if not attendance.clock_in_time:
        raise HTTPException(status_code=400, detail="Not clocked in")

    now = datetime.now(timezone.utc)

    session_seconds = int(
        (now - attendance.clock_in_time).total_seconds()
    )

    attendance.total_seconds += session_seconds

   

    attendance.clock_out_time = now
    attendance.clock_in_time = None  # 🔥 VERY IMPORTANT
  

    running = db.query(TaskTimeLog).filter(
        TaskTimeLog.user_id == attendance.user_id,
        TaskTimeLog.end_time == None
    ).first()

    if running:
        running.end_time = now
    db.commit()
    db.refresh(attendance)

    return attendance


# -------------------------------------------------
# AUTO CLOSE (used inside /active)
# -------------------------------------------------
def auto_close_if_needed(attendance, db):

    from datetime import datetime, timezone, time

    now = datetime.now(timezone.utc)
    today = now.date()

    if not attendance or not attendance.clock_in_time:
        return

    # 🔥 CASE 1: Midnight crossed
    if attendance.date < today:

        midnight = datetime.combine(
            attendance.date,
            time.max,
            tzinfo=timezone.utc
        )

        session_seconds = int(
            (midnight - attendance.clock_in_time).total_seconds()
        )

        attendance.total_seconds += session_seconds
        attendance.clock_out_time = midnight
        attendance.clock_in_time = None

        # 🔥 Stop running task
        running_task = db.query(TaskTimeLog).filter(
            TaskTimeLog.user_id == attendance.user_id,
            TaskTimeLog.end_time == None
        ).first()

        if running_task:
            running_task.end_time = midnight

        db.commit()
        return

# -------------------------------------------------
# GET TODAY TOTAL
# -------------------------------------------------
def get_today_total(user_id, db):

    today = datetime.now(timezone.utc).date()

    attendance = db.query(Attendance).filter(
        Attendance.user_id == user_id,
        Attendance.date == today
    ).first()

    if not attendance:
        return 0

    total = attendance.total_seconds or 0

    # If still running, include live session
    if attendance.clock_in_time:
        now = datetime.now(timezone.utc)
        total += int((now - attendance.clock_in_time).total_seconds())

    return min(total, MAX_WORK_SECONDS)