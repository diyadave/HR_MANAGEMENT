from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import inspect, text
from datetime import datetime, timezone

from app.database.session import get_db
from app.models.leave import Leave
from app.schemas.leave import LeaveCreate, LeaveOut
from app.core.dependencies import get_current_user, get_current_admin
from app.models.user import User
from app.services.notification_service import push_notification, notify_all_admins
from app.services.attendance_service import enforce_hourly_leave_window, notify_attendance_state_change

router = APIRouter(prefix="/leaves", tags=["Leaves"])


def ensure_leave_schema(db: Session) -> None:
    inspector = inspect(db.bind)
    existing_cols = {c["name"] for c in inspector.get_columns("leaves")}
    ddl = {
        "leave_hours": "ALTER TABLE leaves ADD COLUMN leave_hours DOUBLE PRECISION",
        "hourly_start_time": "ALTER TABLE leaves ADD COLUMN hourly_start_time TIME",
        "hourly_end_time": "ALTER TABLE leaves ADD COLUMN hourly_end_time TIME",
    }
    for col, statement in ddl.items():
        if col in existing_cols:
            continue
        try:
            db.execute(text(statement))
            db.commit()
        except Exception:
            db.rollback()


# ======================================
# EMPLOYEE APPLY LEAVE
# ======================================
@router.post("/", response_model=LeaveOut)
def apply_leave(
    payload: LeaveCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    ensure_leave_schema(db)
    if payload.duration_type == "duration":
        if payload.leave_hours is not None and payload.start_date == payload.end_date:
            total_days = round(float(payload.leave_hours) / 8.0, 2)
        else:
            total_days = float((payload.end_date - payload.start_date).days + 1)
    elif payload.duration_type in {"first_half", "second_half"}:
        total_days = 0.5
    else:
        total_days = 1.0

    leave = Leave(
        user_id=current_user.id,
        leave_type=payload.leave_type,
        duration_type=payload.duration_type,
        start_date=payload.start_date,
        end_date=payload.end_date,
        total_days=total_days,
        leave_hours=payload.leave_hours,
        hourly_start_time=payload.hourly_start_time,
        hourly_end_time=payload.hourly_end_time,
        reason=payload.reason,
        status="pending"
    )

    db.add(leave)
    db.commit()
    db.refresh(leave)

    notify_all_admins(
        db,
        title="New leave request",
        message=f"{current_user.name} requested {leave.leave_type} leave from {leave.start_date} to {leave.end_date}.",
        event_type="leave_request_submitted",
        reference_type="leave",
        reference_id=leave.id,
        created_by=current_user.id
    )

    return leave


# ======================================
# EMPLOYEE VIEW OWN LEAVES
# ======================================
@router.get("/my", response_model=list[LeaveOut])
def get_my_leaves(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    ensure_leave_schema(db)
    return db.query(Leave).filter(
        Leave.user_id == current_user.id
    ).order_by(Leave.created_at.desc()).all()


# ======================================
# ADMIN VIEW ALL LEAVES
# ======================================
@router.get("/", response_model=list[LeaveOut])
def get_all_leaves(
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin)
):
    ensure_leave_schema(db)
    query = db.query(Leave)
    if status:
        query = query.filter(Leave.status == status)
    return query.order_by(Leave.created_at.desc()).all()


# ======================================
# ADMIN APPROVE
# ======================================
@router.put("/{leave_id}/approve")
def approve_leave(
    leave_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    ensure_leave_schema(db)
    leave = db.query(Leave).filter(Leave.id == leave_id).first()

    if not leave:
        raise HTTPException(status_code=404, detail="Leave not found")
    if leave.status != "pending":
        raise HTTPException(status_code=400, detail="Only pending leaves can be approved")

    leave.status = "approved"
    leave.approved_by = admin.id
    leave.approved_at = datetime.now(timezone.utc)

    db.commit()
    enforce_hourly_leave_window(leave.user_id, db)
    notify_attendance_state_change(leave.user_id)
    push_notification(
        db,
        user_id=leave.user_id,
        title="Leave request approved",
        message=f"Your {leave.leave_type} leave from {leave.start_date} to {leave.end_date} has been approved.",
        event_type="leave_approved",
        reference_type="leave",
        reference_id=leave.id,
        created_by=admin.id
    )

    return {"message": "Leave approved"}


# ======================================
# ADMIN REJECT
# ======================================
@router.put("/{leave_id}/reject")
def reject_leave(
    leave_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    ensure_leave_schema(db)
    leave = db.query(Leave).filter(Leave.id == leave_id).first()

    if not leave:
        raise HTTPException(status_code=404, detail="Leave not found")
    if leave.status != "pending":
        raise HTTPException(status_code=400, detail="Only pending leaves can be rejected")

    leave.status = "rejected"
    leave.approved_by = admin.id
    leave.approved_at = datetime.now(timezone.utc)

    db.commit()
    enforce_hourly_leave_window(leave.user_id, db)
    notify_attendance_state_change(leave.user_id)
    push_notification(
        db,
        user_id=leave.user_id,
        title="Leave request rejected",
        message=f"Your {leave.leave_type} leave from {leave.start_date} to {leave.end_date} has been rejected.",
        event_type="leave_rejected",
        reference_type="leave",
        reference_id=leave.id,
        created_by=admin.id
    )

    return {"message": "Leave rejected"}
