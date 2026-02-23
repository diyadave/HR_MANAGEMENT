from datetime import datetime, timedelta, timezone, time
from fastapi import HTTPException

from app.models.attendance import Attendance
from app.models.task_time_log import TaskTimeLog

MAX_WORK_SECONDS = 9 * 3600  # 9 hours
BREAK_START_HOUR = 13  # 1 PM
BREAK_END_HOUR = 14    # 2 PM
OFFICE_END_HOUR = 18   # 6 PM


def calculate_work_seconds(clock_in: datetime, clock_out: datetime) -> int:
    """Calculate worked seconds after subtracting break-time overlap (1PM-2PM)."""
    if not clock_in or not clock_out or clock_out <= clock_in:
        return 0

    total_seconds = int((clock_out - clock_in).total_seconds())
    break_overlap = 0

    current_day = clock_in.date()
    last_day = clock_out.date()
    tz = clock_in.tzinfo or timezone.utc

    while current_day <= last_day:
        break_start = datetime.combine(current_day, time(hour=BREAK_START_HOUR, minute=0), tzinfo=tz)
        break_end = datetime.combine(current_day, time(hour=BREAK_END_HOUR, minute=0), tzinfo=tz)

        overlap_start = max(clock_in, break_start)
        overlap_end = min(clock_out, break_end)

        if overlap_end > overlap_start:
            break_overlap += int((overlap_end - overlap_start).total_seconds())

        current_day += timedelta(days=1)

    return max(total_seconds - break_overlap, 0)


def calculate_work_hours(clock_in: datetime, clock_out: datetime) -> float:
    """Compute decimal hours with break deduction."""
    return round(calculate_work_seconds(clock_in, clock_out) / 3600, 2)


def _close_running_tasks(user_id: int, close_at: datetime, db) -> None:
    running_tasks = db.query(TaskTimeLog).filter(
        TaskTimeLog.user_id == user_id,
        TaskTimeLog.end_time == None
    ).all()

    for log in running_tasks:
        log.end_time = close_at


def close_running_tasks_for_user(user_id: int, close_at: datetime, db) -> int:
    running_tasks = db.query(TaskTimeLog).filter(
        TaskTimeLog.user_id == user_id,
        TaskTimeLog.end_time == None
    ).all()
    for log in running_tasks:
        log.end_time = close_at
    if running_tasks:
        db.commit()
    return len(running_tasks)


def _close_attendance(attendance: Attendance, close_at: datetime, db) -> None:
    if not attendance.clock_in_time:
        return

    effective_close = max(close_at, attendance.clock_in_time)
    attendance.total_seconds = (attendance.total_seconds or 0) + calculate_work_seconds(
        attendance.clock_in_time,
        effective_close
    )
    attendance.clock_out_time = effective_close
    attendance.clock_in_time = None
    _close_running_tasks(attendance.user_id, effective_close, db)


def close_open_attendances_for_user(user_id: int, close_at: datetime, db) -> int:
    """Force-close all currently open attendance rows for a user at a specific timestamp."""
    open_rows = db.query(Attendance).filter(
        Attendance.user_id == user_id,
        Attendance.clock_in_time != None
    ).all()

    closed = 0
    for row in open_rows:
        _close_attendance(row, close_at, db)
        closed += 1
    if closed:
        db.commit()
    else:
        close_running_tasks_for_user(user_id, close_at, db)
    return closed


def auto_close_if_needed(attendance: Attendance, db, now: datetime | None = None) -> bool:
    """Auto-close open attendance at 6PM (server-side)."""
    if not attendance or not attendance.clock_in_time:
        return False

    now = now or datetime.now(timezone.utc)
    office_end = datetime.combine(
        attendance.date,
        time(hour=OFFICE_END_HOUR, minute=0),
        tzinfo=timezone.utc
    )

    if now < office_end:
        return False

    _close_attendance(attendance, office_end, db)
    db.commit()
    return True


def auto_close_open_attendances_for_user(user_id: int, db, now: datetime | None = None) -> int:
    """Close all stale/open attendance rows for a user when eligible."""
    now = now or datetime.now(timezone.utc)

    open_rows = db.query(Attendance).filter(
        Attendance.user_id == user_id,
        Attendance.clock_in_time != None
    ).order_by(Attendance.date.asc()).all()

    closed = 0
    for row in open_rows:
        if auto_close_if_needed(row, db, now=now):
            closed += 1
    return closed


def clock_in(current_user, db):
    now = datetime.now(timezone.utc)
    today = now.date()

    # Close stale sessions before new clock-in.
    auto_close_open_attendances_for_user(current_user.id, db, now=now)

    attendance = db.query(Attendance).filter(
        Attendance.user_id == current_user.id,
        Attendance.date == today
    ).first()

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

    if attendance.clock_in_time is not None:
        raise HTTPException(status_code=400, detail="Already clocked in")

    if (attendance.total_seconds or 0) >= MAX_WORK_SECONDS:
        raise HTTPException(status_code=400, detail="9 working hours already completed.")

    attendance.clock_in_time = now
    attendance.clock_out_time = None
    db.commit()
    db.refresh(attendance)
    return attendance


def clock_out(attendance: Attendance, db):
    if not attendance or not attendance.clock_in_time:
        raise HTTPException(status_code=400, detail="Not clocked in")

    now = datetime.now(timezone.utc)
    office_end = datetime.combine(
        attendance.date,
        time(hour=OFFICE_END_HOUR, minute=0),
        tzinfo=timezone.utc
    )
    close_at = min(now, office_end)

    _close_attendance(attendance, close_at, db)
    db.commit()
    db.refresh(attendance)
    return attendance


def get_today_total(user_id, db):
    now = datetime.now(timezone.utc)
    today = now.date()

    auto_close_open_attendances_for_user(user_id, db, now=now)

    attendance = db.query(Attendance).filter(
        Attendance.user_id == user_id,
        Attendance.date == today
    ).first()

    if not attendance:
        return 0

    total = attendance.total_seconds or 0
    if attendance.clock_in_time:
        total += calculate_work_seconds(attendance.clock_in_time, now)

    return min(total, MAX_WORK_SECONDS)
