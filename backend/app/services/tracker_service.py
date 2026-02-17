from datetime import datetime, date, time
from sqlalchemy.orm import Session

from app.models.attendance import Attendance
from app.models.task_time_log import TaskTimeLog
from app.services.attendance_service import get_today_total

MAX_WORK_SECONDS = 9 * 3600  # 9 hours


def get_daily_summary(user_id: int, db: Session):
    """
    Returns:
        - total attendance seconds
        - total task seconds
        - idle time
        - overtime
    """

    today = datetime.now(timezone.utc).date()

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
