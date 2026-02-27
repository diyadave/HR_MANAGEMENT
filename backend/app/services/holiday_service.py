from sqlalchemy.orm import Session
from sqlalchemy import extract
from datetime import date, datetime, timezone
from typing import Optional

from app.models.holiday import Holiday, HolidayType
from app.models.attendance import Attendance
from app.models.user import User
from app.schemas.holiday import HolidayCreate, HolidayUpdate
from fastapi import HTTPException


# ─── HELPERS ──────────────────────────────────────────────────────────────────

def _get_employees_for_department(db: Session, department: str) -> list:
    """
    Return all active users that match the department filter.
    'All' means every user.
    Multiple departments can be stored as comma-separated string.
    """
    query = db.query(User).filter(User.is_active == True)  # noqa: E712

    if department and department.strip().lower() != "all":
        depts = [d.strip() for d in department.split(",")]
        query = query.filter(User.department.in_(depts))

    return query.all()


def _auto_mark_holiday_attendance(
    db: Session,
    holiday: Holiday,
    delete: bool = False,
) -> None:
    """
    For every employee in the target department(s), upsert an Attendance row
    for the holiday date.

    - delete=False  → create/update rows (set clock times to None, mark holiday)
    - delete=True   → remove rows that were holiday-only (no real clock data)

    We store holiday status via total_seconds = -1 as a sentinel, OR simply
    leave clock_in_time / clock_out_time as NULL so the history endpoint
    naturally shows 0 seconds → absent/holiday. A cleaner approach used here:
    set a special `status` field if your Attendance model has one.

    Since your current Attendance model has no `status` column, we mark holiday
    by setting total_seconds = 0 and ensuring clock_in / clock_out are NULL.
    The attendance history endpoint will show those days as "absent" — that is
    correct HR behaviour (holiday ≠ present). The frontend attendance page
    shows the holiday icon from the holiday list, not from attendance rows.

    NOTE: If you add a `status` column later (e.g. "holiday", "leave", etc.)
    just set it here.
    """
    employees = _get_employees_for_department(db, holiday.department)

    for emp in employees:
        existing = db.query(Attendance).filter(
            Attendance.user_id == emp.id,
            Attendance.date == holiday.date,
        ).first()

        if delete:
            # Only remove if it was a holiday-only record (no clock data)
            if existing and existing.clock_in_time is None and existing.clock_out_time is None:
                db.delete(existing)
        else:
            if existing is None:
                # Create placeholder attendance row
                new_att = Attendance(
                    user_id=emp.id,
                    date=holiday.date,
                    clock_in_time=None,
                    clock_out_time=None,
                    total_seconds=0,
                )
                db.add(new_att)
            # If clock data exists we leave it alone — employee actually worked


# ─── CRUD ─────────────────────────────────────────────────────────────────────

def get_all_holidays(
    db: Session,
    year: Optional[int] = None,
    month: Optional[int] = None,
    department: Optional[str] = None,
    holiday_type: Optional[str] = None,
) -> list[Holiday]:
    q = db.query(Holiday)

    if year:
        q = q.filter(extract("year", Holiday.date) == year)
    if month:
        q = q.filter(extract("month", Holiday.date) == month)
    if department and department.lower() not in ("", "all"):
        # match if holiday is 'All' OR contains this department
        q = q.filter(
            (Holiday.department == "All") |
            Holiday.department.ilike(f"%{department}%")
        )
    if holiday_type:
        q = q.filter(Holiday.type == holiday_type)

    return q.order_by(Holiday.date.asc()).all()


def get_holiday_by_id(db: Session, holiday_id: int) -> Optional[Holiday]:
    return db.query(Holiday).filter(Holiday.id == holiday_id).first()


def create_holiday(db: Session, data: HolidayCreate) -> Holiday:
    if data.date < date.today():
        raise HTTPException(status_code=400, detail="Past dates are not allowed for holidays")

    holiday = Holiday(
        name=data.name,
        date=data.date,
        type=data.type,
        department=data.department,
        repeat_yearly=data.repeat_yearly,
    )
    db.add(holiday)
    db.flush()  # get id before commit

    _auto_mark_holiday_attendance(db, holiday)

    db.commit()
    db.refresh(holiday)
    return holiday


def update_holiday(db: Session, holiday_id: int, data: HolidayUpdate) -> Optional[Holiday]:
    holiday = get_holiday_by_id(db, holiday_id)
    if not holiday:
        return None

    if data.date is not None and data.date < date.today() and data.date != holiday.date:
        raise HTTPException(status_code=400, detail="Past dates are not allowed for holidays")

    old_date = holiday.date
    old_dept = holiday.department

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(holiday, field, value)

    # If date or department changed, undo old auto-marks and redo
    if data.date or data.department:
        # Remove old auto-marks using old values
        old_holiday_stub = Holiday(
            id=holiday.id,
            name=holiday.name,
            date=old_date,
            type=holiday.type,
            department=old_dept,
            repeat_yearly=holiday.repeat_yearly,
        )
        _auto_mark_holiday_attendance(db, old_holiday_stub, delete=True)
        _auto_mark_holiday_attendance(db, holiday)

    db.commit()
    db.refresh(holiday)
    return holiday


def delete_holiday(db: Session, holiday_id: int) -> bool:
    holiday = get_holiday_by_id(db, holiday_id)
    if not holiday:
        return False

    _auto_mark_holiday_attendance(db, holiday, delete=True)

    db.delete(holiday)
    db.commit()
    return True


def bulk_delete_holidays(db: Session, ids: list[int]) -> int:
    deleted = 0
    for hid in ids:
        if delete_holiday(db, hid):
            deleted += 1
    return deleted


def get_holidays_for_date(db: Session, target_date: date) -> list[Holiday]:
    """Used by attendance service to check if a date is a holiday."""
    return db.query(Holiday).filter(Holiday.date == target_date).all()


def get_holidays_for_month(db: Session, year: int, month: int) -> list[Holiday]:
    """Used by attendance history to overlay holiday info on calendar."""
    return (
        db.query(Holiday)
        .filter(
            extract("year", Holiday.date) == year,
            extract("month", Holiday.date) == month,
        )
        .all()
    )
