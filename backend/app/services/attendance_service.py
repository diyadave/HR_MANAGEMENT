import os
from datetime import date, datetime, time, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import inspect, text

from app.core.attendance_ws_manager import attendance_ws_manager
from app.models.attendance import Attendance
from app.models.holiday import Holiday
from app.models.leave import Leave
from app.models.task_time_log import TaskTimeLog

IST = timezone(timedelta(hours=5, minutes=30))


def _parse_time_env(name: str, default_value: time) -> time:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default_value
    try:
        hour, minute = raw.split(":", 1)
        return time(int(hour), int(minute))
    except Exception:
        return default_value


def _parse_float_env(name: str, default_value: float) -> float:
    try:
        return float(os.getenv(name, str(default_value)))
    except Exception:
        return default_value


SHIFT_START = _parse_time_env("ATTENDANCE_SHIFT_START", time(9, 0))
LATE_THRESHOLD = _parse_time_env("ATTENDANCE_LATE_THRESHOLD", time(9, 30))
SHIFT_END = _parse_time_env("ATTENDANCE_SHIFT_END", time(18, 0))

BREAK_START_HOUR = int(os.getenv("ATTENDANCE_BREAK_START_HOUR", "13"))
BREAK_END_HOUR = int(os.getenv("ATTENDANCE_BREAK_END_HOUR", "14"))
STANDARD_WORK_SECONDS = int(_parse_float_env("ATTENDANCE_STANDARD_WORK_HOURS", 8.25) * 3600)
HALF_DAY_MIN_SECONDS = 4 * 3600
SECOND_HALF_START = time(14, 0)
FIRST_HALF_END = time(13, 0)


def ensure_attendance_schema(db) -> None:
    inspector = inspect(db.bind)
    existing_cols = {c["name"] for c in inspector.get_columns("attendance_logs")}
    ddl = {
        "half_day_type": "ALTER TABLE attendance_logs ADD COLUMN half_day_type VARCHAR(20)",
        "is_late": "ALTER TABLE attendance_logs ADD COLUMN is_late BOOLEAN DEFAULT FALSE NOT NULL",
        "working_from": "ALTER TABLE attendance_logs ADD COLUMN working_from VARCHAR(30)",
        "location": "ALTER TABLE attendance_logs ADD COLUMN location VARCHAR(255)",
        "manual_override": "ALTER TABLE attendance_logs ADD COLUMN manual_override BOOLEAN DEFAULT FALSE NOT NULL",
        "edit_reason": "ALTER TABLE attendance_logs ADD COLUMN edit_reason TEXT",
        "status": "ALTER TABLE attendance_logs ADD COLUMN status VARCHAR(20)",
        "first_clock_in_time": "ALTER TABLE attendance_logs ADD COLUMN first_clock_in_time TIMESTAMPTZ",
        "overtime_hours": "ALTER TABLE attendance_logs ADD COLUMN overtime_hours DOUBLE PRECISION DEFAULT 0 NOT NULL",
        "is_manual_edit": "ALTER TABLE attendance_logs ADD COLUMN is_manual_edit BOOLEAN DEFAULT FALSE NOT NULL",
        "updated_by_admin_id": "ALTER TABLE attendance_logs ADD COLUMN updated_by_admin_id INTEGER",
    }
    for col, statement in ddl.items():
        if col in existing_cols:
            continue
        try:
            db.execute(text(statement))
            db.commit()
        except Exception:
            db.rollback()


def _notify_attendance_state_change(user_id: int) -> None:
    attendance_ws_manager.notify_attendance_change_threadsafe(user_id)


def _ensure_aware_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _break_window_utc_for_ist_date(day: date) -> tuple[datetime, datetime]:
    break_start_ist = datetime.combine(day, time(hour=BREAK_START_HOUR, minute=0), tzinfo=IST)
    break_end_ist = datetime.combine(day, time(hour=BREAK_END_HOUR, minute=0), tzinfo=IST)
    return break_start_ist.astimezone(timezone.utc), break_end_ist.astimezone(timezone.utc)


def _shift_end_utc_for_ist_date(day: date) -> datetime:
    shift_end_ist = datetime.combine(day, SHIFT_END, tzinfo=IST)
    return shift_end_ist.astimezone(timezone.utc)


def is_break_time_ist(now: datetime | None = None) -> bool:
    current = _ensure_aware_utc(now or datetime.now(timezone.utc)).astimezone(IST)
    return BREAK_START_HOUR <= current.hour < BREAK_END_HOUR


def get_ist_date(now: datetime | None = None) -> date:
    current = _ensure_aware_utc(now or datetime.now(timezone.utc))
    return current.astimezone(IST).date()


def _is_holiday_for_user(db, user, target_date: date) -> bool:
    holidays = db.query(Holiday).filter(
        Holiday.date == target_date
    ).all()
    repeating = db.query(Holiday).filter(
        Holiday.repeat_yearly == True
    ).all()

    all_holidays = list(holidays)
    for holiday in repeating:
        if holiday.date and holiday.date.month == target_date.month and holiday.date.day == target_date.day:
            all_holidays.append(holiday)

    user_dept = (user.department or "").strip().lower()
    for holiday in all_holidays:
        dept_raw = (holiday.department or "all").strip().lower()
        if dept_raw in {"all", ""}:
            return True
        allowed = {d.strip().lower() for d in dept_raw.split(",") if d.strip()}
        if user_dept and user_dept in allowed:
            return True
    return False


def _leave_status_for_date(db, user_id: int, target_date: date) -> str | None:
    leave = db.query(Leave).filter(
        Leave.user_id == user_id,
        Leave.start_date <= target_date,
        Leave.end_date >= target_date
    ).order_by(Leave.created_at.desc()).first()
    if not leave:
        return None
    if leave.status == "approved":
        return "leave"
    return "absent"


def _upsert_non_working_attendance(user_id: int, target_date: date, status: str, db) -> None:
    attendance = db.query(Attendance).filter(
        Attendance.user_id == user_id,
        Attendance.date == target_date
    ).first()
    if not attendance:
        attendance = Attendance(user_id=user_id, date=target_date)
        db.add(attendance)
        db.flush()

    attendance.clock_in_time = None
    attendance.clock_out_time = None
    attendance.first_clock_in_time = None
    attendance.total_seconds = 0
    attendance.half_day_type = None
    attendance.is_late = False
    attendance.status = status
    attendance.is_manual_edit = False
    attendance.manual_override = False


def calculate_work_seconds(clock_in: datetime, clock_out: datetime) -> int:
    if not clock_in or not clock_out:
        return 0

    clock_in = _ensure_aware_utc(clock_in)
    clock_out = _ensure_aware_utc(clock_out)
    if clock_out <= clock_in:
        return 0

    total_seconds = int((clock_out - clock_in).total_seconds())
    break_overlap = 0

    current_day = clock_in.astimezone(IST).date()
    last_day = clock_out.astimezone(IST).date()

    while current_day <= last_day:
        break_start, break_end = _break_window_utc_for_ist_date(current_day)
        overlap_start = max(clock_in, break_start)
        overlap_end = min(clock_out, break_end)
        if overlap_end > overlap_start:
            break_overlap += int((overlap_end - overlap_start).total_seconds())
        current_day += timedelta(days=1)

    return max(total_seconds - break_overlap, 0)


def calculate_work_hours(clock_in: datetime, clock_out: datetime) -> float:
    return round(calculate_work_seconds(clock_in, clock_out) / 3600, 2)


def get_effective_clock_in_time(attendance: Attendance | None) -> datetime | None:
    if not attendance:
        return None
    if getattr(attendance, "first_clock_in_time", None):
        return _ensure_aware_utc(attendance.first_clock_in_time)
    if attendance.clock_in_time:
        return _ensure_aware_utc(attendance.clock_in_time)
    if attendance.clock_out_time and (attendance.total_seconds or 0) > 0:
        inferred = _ensure_aware_utc(attendance.clock_out_time) - timedelta(seconds=int(attendance.total_seconds or 0))
        return inferred
    return None


def get_attendance_worked_seconds(attendance: Attendance | None, now: datetime | None = None) -> int:
    if not attendance:
        return 0
    current = _ensure_aware_utc(now or datetime.now(timezone.utc))
    total = int(attendance.total_seconds or 0)
    today_ist = get_ist_date(current)
    if attendance.clock_in_time and not attendance.clock_out_time and attendance.date == today_ist:
        total += calculate_work_seconds(attendance.clock_in_time, current)
    return max(total, 0)


def calculate_overtime_seconds(
    attendance: Attendance | None,
    worked_seconds: int,
    now: datetime | None = None
) -> int:
    if not attendance:
        return 0

    manual_overtime = float(attendance.overtime_hours or 0)
    if attendance.is_manual_edit and manual_overtime > 0:
        return int(round(manual_overtime * 3600))

    current = _ensure_aware_utc(now or datetime.now(timezone.utc))
    reference_out = _ensure_aware_utc(attendance.clock_out_time) if attendance.clock_out_time else None

    if attendance.clock_in_time and not attendance.clock_out_time and attendance.date == get_ist_date(current):
        reference_out = current

    overtime_by_shift_end = 0
    if reference_out:
        shift_end_utc = _shift_end_utc_for_ist_date(attendance.date)
        overtime_by_shift_end = max(0, int((reference_out - shift_end_utc).total_seconds()))

    overtime_by_hours = max(0, int(worked_seconds or 0) - STANDARD_WORK_SECONDS)
    return max(overtime_by_shift_end, overtime_by_hours)


def determine_attendance_status(attendance: Attendance | None, seconds: int, now: datetime | None = None) -> str:
    if not attendance:
        return "absent"

    manual_status = (attendance.status or "").strip().lower()
    if attendance.is_manual_edit and manual_status:
        return manual_status

    effective_clock_in = get_effective_clock_in_time(attendance)
    if not effective_clock_in:
        return "absent"
    current = _ensure_aware_utc(now or datetime.now(timezone.utc))
    reference_out = _ensure_aware_utc(attendance.clock_out_time) if attendance.clock_out_time else None
    if attendance.clock_in_time and not attendance.clock_out_time and attendance.date == get_ist_date(current):
        reference_out = current
    if not reference_out:
        return "in_progress"

    start_ist = effective_clock_in.astimezone(IST)
    end_ist = reference_out.astimezone(IST)
    start_t = start_ist.time()
    end_t = end_ist.time()
    worked_seconds = int(seconds or 0)

    # Full day present: on-time entry and day completed until 6:00 PM.
    if SHIFT_START <= start_t <= LATE_THRESHOLD and end_t >= SHIFT_END:
        return "present"

    # Late but full day: post 9:30 AM entry and completed day till/after 6:01 PM.
    if start_t > LATE_THRESHOLD and end_t > SHIFT_END:
        return "late"

    # First half pattern: 9:00-9:30 entry and leaves around 1:00 PM.
    if SHIFT_START <= start_t <= LATE_THRESHOLD and FIRST_HALF_END <= end_t < SECOND_HALF_START and worked_seconds >= HALF_DAY_MIN_SECONDS:
        attendance.half_day_type = "first_half"
        return "halfday"

    # Second half pattern: starts at/after 2:00 PM and leaves at/after 6:00 PM.
    if start_t >= SECOND_HALF_START and end_t >= SHIFT_END and worked_seconds >= HALF_DAY_MIN_SECONDS:
        attendance.half_day_type = "second_half"
        return "halfday"

    # Fallback half day based on worked hours.
    if worked_seconds >= HALF_DAY_MIN_SECONDS:
        if not attendance.half_day_type:
            attendance.half_day_type = "second_half" if start_t >= SECOND_HALF_START else "first_half"
        return "halfday"

    return "absent"


def get_attendance_status_meta(attendance: Attendance | None, now: datetime | None = None) -> dict:
    current = _ensure_aware_utc(now or datetime.now(timezone.utc))
    today_ist = get_ist_date(current)
    seconds = get_attendance_worked_seconds(attendance, current)
    status = determine_attendance_status(attendance, seconds, current)
    effective_clock_in = get_effective_clock_in_time(attendance)
    is_late_entry = bool(effective_clock_in and effective_clock_in.astimezone(IST).time() > LATE_THRESHOLD)
    overtime_seconds = calculate_overtime_seconds(attendance, seconds, current)
    half_day_type = attendance.half_day_type if attendance else None
    return {
        "status": status,
        "seconds": seconds,
        "is_running": bool(
            attendance and attendance.clock_in_time and not attendance.clock_out_time and attendance.date == today_ist
        ),
        "is_late_entry": is_late_entry,
        "overtime_seconds": overtime_seconds,
        "overtime_hours": round(overtime_seconds / 3600, 2),
        "is_overtime": overtime_seconds > 0,
        "half_day_type": half_day_type,
        "effective_clock_in_time": effective_clock_in,
    }


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


def _sync_status_fields(attendance: Attendance, now: datetime | None = None) -> None:
    seconds = get_attendance_worked_seconds(attendance, now)
    status = determine_attendance_status(attendance, seconds, now)
    meta = get_attendance_status_meta(attendance, now)
    attendance.status = status
    if status != "halfday":
        attendance.half_day_type = None
    attendance.is_late = bool(meta["is_late_entry"] or status == "late")
    if not attendance.is_manual_edit:
        attendance.overtime_hours = round(float(meta["overtime_seconds"] or 0) / 3600, 2)


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
    _sync_status_fields(attendance, now=effective_close)


def close_open_attendances_for_user(user_id: int, close_at: datetime, db) -> int:
    open_rows = db.query(Attendance).filter(
        Attendance.user_id == user_id,
        Attendance.clock_in_time != None,
        Attendance.clock_out_time == None
    ).all()

    closed = 0
    changed_users: set[int] = set()
    for row in open_rows:
        _close_attendance(row, close_at, db)
        closed += 1
        changed_users.add(row.user_id)
    if closed:
        db.commit()
        for changed_user_id in changed_users:
            _notify_attendance_state_change(changed_user_id)
    else:
        close_running_tasks_for_user(user_id, close_at, db)
    return closed


def auto_close_if_needed(attendance: Attendance, db, now: datetime | None = None) -> bool:
    if not attendance or not attendance.clock_in_time:
        return False

    now = _ensure_aware_utc(now or datetime.now(timezone.utc))
    now_ist_date = now.astimezone(IST).date()
    clock_in_utc = _ensure_aware_utc(attendance.clock_in_time)
    local_day = clock_in_utc.astimezone(IST).date()
    break_start, _ = _break_window_utc_for_ist_date(local_day)
    shift_end = _shift_end_utc_for_ist_date(local_day)

    if local_day < now_ist_date:
        _close_attendance(attendance, shift_end, db)
        db.commit()
        _notify_attendance_state_change(attendance.user_id)
        return True

    if clock_in_utc < break_start <= now:
        _close_attendance(attendance, break_start, db)
        db.commit()
        _notify_attendance_state_change(attendance.user_id)
        return True

    if clock_in_utc < shift_end <= now:
        _close_attendance(attendance, shift_end, db)
        db.commit()
        _notify_attendance_state_change(attendance.user_id)
        return True

    return False


def auto_close_open_attendances_for_user(user_id: int, db, now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    open_rows = db.query(Attendance).filter(
        Attendance.user_id == user_id,
        Attendance.clock_in_time != None,
        Attendance.clock_out_time == None
    ).order_by(Attendance.date.asc()).all()

    closed = 0
    for row in open_rows:
        if auto_close_if_needed(row, db, now=now):
            closed += 1
    return closed


def clock_in(current_user, db):
    ensure_attendance_schema(db)
    now = _ensure_aware_utc(datetime.now(timezone.utc))
    now_ist = now.astimezone(IST)
    today = now_ist.date()

    auto_close_open_attendances_for_user(current_user.id, db, now=now)

    if _is_holiday_for_user(db, current_user, today):
        _upsert_non_working_attendance(current_user.id, today, "holiday", db)
        db.commit()
        _notify_attendance_state_change(current_user.id)
        raise HTTPException(status_code=400, detail="Today is a holiday. Clock-in is disabled.")

    leave_status = _leave_status_for_date(db, current_user.id, today)
    if leave_status:
        _upsert_non_working_attendance(current_user.id, today, leave_status, db)
        db.commit()
        _notify_attendance_state_change(current_user.id)
        if leave_status == "leave":
            raise HTTPException(status_code=400, detail="Approved leave for today. Clock-in is disabled.")
        raise HTTPException(status_code=400, detail="Leave is not approved for today. Attendance marked absent.")

    if BREAK_START_HOUR <= now_ist.hour < BREAK_END_HOUR:
        raise HTTPException(status_code=400, detail="Break time is active. Please clock in after break.")

    attendance = db.query(Attendance).filter(
        Attendance.user_id == current_user.id,
        Attendance.date == today
    ).first()

    if not attendance:
        attendance = Attendance(
            user_id=current_user.id,
            date=today,
            clock_in_time=now,
            first_clock_in_time=now,
            total_seconds=0,
            status="late" if now_ist.time() > LATE_THRESHOLD else "present",
            is_late=now_ist.time() > LATE_THRESHOLD,
            overtime_hours=0,
        )
        db.add(attendance)
        db.commit()
        db.refresh(attendance)
        _notify_attendance_state_change(current_user.id)
        return attendance

    if attendance.clock_in_time is not None:
        raise HTTPException(status_code=400, detail="Already clocked in")

    attendance.clock_in_time = now
    attendance.clock_out_time = None
    if not attendance.first_clock_in_time:
        attendance.first_clock_in_time = now
    attendance.is_manual_edit = False
    attendance.manual_override = False
    attendance.updated_by_admin_id = None
    attendance.status = "late" if now_ist.time() > LATE_THRESHOLD else "present"
    _sync_status_fields(attendance, now=now)
    db.commit()
    db.refresh(attendance)
    _notify_attendance_state_change(current_user.id)
    return attendance


def clock_out(attendance: Attendance, db):
    if not attendance or not attendance.clock_in_time:
        raise HTTPException(status_code=400, detail="Not clocked in")

    ensure_attendance_schema(db)
    now = datetime.now(timezone.utc)
    _close_attendance(attendance, now, db)
    db.commit()
    db.refresh(attendance)
    _notify_attendance_state_change(attendance.user_id)
    return attendance


def get_today_total(user_id, db):
    ensure_attendance_schema(db)
    now = datetime.now(timezone.utc)
    today = now.astimezone(IST).date()

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

    return max(total, 0)


def get_clock_in_lock_reason(current_user, db, now: datetime | None = None) -> str | None:
    current = _ensure_aware_utc(now or datetime.now(timezone.utc))
    today = current.astimezone(IST).date()

    if _is_holiday_for_user(db, current_user, today):
        return "holiday"

    leave_status = _leave_status_for_date(db, current_user.id, today)
    if leave_status == "leave":
        return "leave"
    if leave_status == "absent":
        return "unapproved_leave"

    if BREAK_START_HOUR <= current.astimezone(IST).hour < BREAK_END_HOUR:
        return "break"

    return None
