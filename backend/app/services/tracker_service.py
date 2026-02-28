from datetime import datetime, time, timezone
from sqlalchemy.orm import Session
from sqlalchemy import inspect, text

from app.models.task import Task
from app.models.task_time_log import TaskTimeLog
from app.services.attendance_service import get_ist_date, get_today_total

MAX_WORK_SECONDS = 9 * 3600  # 9 hours


def ensure_task_schema(db: Session) -> None:
    inspector = inspect(db.bind)
    existing_cols = {c["name"] for c in inspector.get_columns("tasks")}
    if "is_overtime" in existing_cols:
        return
    try:
        db.execute(text("ALTER TABLE tasks ADD COLUMN is_overtime BOOLEAN DEFAULT FALSE NOT NULL"))
        db.commit()
    except Exception:
        db.rollback()


def get_daily_summary(user_id: int, db: Session):
    """
    Returns:
        - total attendance seconds
        - total task seconds
        - idle time
        - overtime
    """

    today = get_ist_date()

    # -------------------------
    # 1️⃣ Attendance Total
    # -------------------------
    attendance_total = get_today_total(user_id, db)

    # -------------------------
    # 2️⃣ Task Time Total
    # -------------------------

    start_of_day = datetime.combine(today, time.min)
    end_of_day = datetime.combine(today, time.max)

    task_logs = db.query(TaskTimeLog).filter(
        TaskTimeLog.user_id == user_id,
        TaskTimeLog.start_time >= start_of_day,
        TaskTimeLog.start_time <= end_of_day
    ).all()

    total_task = 0

    for log in task_logs:
        if log.end_time:
            total_task += int((log.end_time - log.start_time).total_seconds())

    # -------------------------
    # 3️⃣ Idle Time
    # -------------------------
    idle_time = max(0, attendance_total - total_task)

    # -------------------------
    # 4️⃣ Overtime
    # -------------------------
    overtime = max(0, attendance_total - MAX_WORK_SECONDS)

    return {
        "attendance_seconds": attendance_total,
        "task_seconds": total_task,
        "idle_seconds": idle_time,
        "overtime_seconds": overtime
    }


def _task_total_logged_seconds(task_id: int, db: Session) -> int:
    logs = db.query(TaskTimeLog).filter(TaskTimeLog.task_id == task_id).all()
    now = datetime.now(timezone.utc)
    total = 0
    for log in logs:
        end_time = log.end_time or now
        if end_time > log.start_time:
            total += int((end_time - log.start_time).total_seconds())
    return max(total, 0)


def set_task_in_progress(task: Task, db: Session) -> None:
    ensure_task_schema(db)
    task.status = "in_progress"
    db.add(task)


def set_task_paused(task: Task, db: Session) -> None:
    ensure_task_schema(db)
    task.status = "paused"
    db.add(task)


def set_task_completed(task: Task, completed_by: int, db: Session) -> None:
    ensure_task_schema(db)
    task.status = "completed"
    task.completed_at = datetime.now(timezone.utc)
    task.completed_by = completed_by
    db.add(task)


def apply_overtime_status_if_needed(task: Task, db: Session) -> None:
    ensure_task_schema(db)
    if not task.estimated_hours:
        task.is_overtime = False
        db.add(task)
        return
    estimated_seconds = int(float(task.estimated_hours) * 3600)
    if estimated_seconds <= 0:
        task.is_overtime = False
        db.add(task)
        return
    total_logged_seconds = _task_total_logged_seconds(task.id, db)
    task.is_overtime = bool(total_logged_seconds > estimated_seconds)
    db.add(task)
