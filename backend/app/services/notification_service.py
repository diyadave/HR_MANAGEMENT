from typing import Iterable, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import and_, extract
from datetime import date, timedelta

from app.core.notification_ws_manager import notification_ws_manager
from app.models.notification import Notification
from app.models.user import User
from app.models.holiday import Holiday


def notification_to_payload(notification: Notification) -> dict:
    return {
        "type": "notification_new",
        "notification": {
            "id": notification.id,
            "user_id": notification.user_id,
            "title": notification.title,
            "message": notification.message,
            "event_type": notification.event_type,
            "reference_type": notification.reference_type,
            "reference_id": notification.reference_id,
            "is_read": bool(notification.is_read),
            "created_at": notification.created_at.isoformat() if notification.created_at else None,
        },
    }


def push_notification(
    db: Session,
    *,
    user_id: int,
    title: str,
    message: str,
    event_type: Optional[str] = None,
    reference_type: Optional[str] = None,
    reference_id: Optional[int] = None,
    created_by: Optional[int] = None
) -> Notification:
    notification = Notification(
        user_id=user_id,
        title=title,
        message=message,
        event_type=event_type,
        reference_type=reference_type,
        reference_id=reference_id,
        created_by=created_by,
        is_read=False,
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)
    notification_ws_manager.notify_threadsafe(user_id, notification_to_payload(notification))
    return notification


def push_notifications(
    db: Session,
    *,
    user_ids: Iterable[int],
    title: str,
    message: str,
    event_type: Optional[str] = None,
    reference_type: Optional[str] = None,
    reference_id: Optional[int] = None,
    created_by: Optional[int] = None
) -> List[Notification]:
    normalized_ids = sorted({int(uid) for uid in user_ids if uid is not None})
    if not normalized_ids:
        return []

    notifications = [
        Notification(
            user_id=user_id,
            title=title,
            message=message,
            event_type=event_type,
            reference_type=reference_type,
            reference_id=reference_id,
            created_by=created_by,
            is_read=False,
        )
        for user_id in normalized_ids
    ]
    db.add_all(notifications)
    db.commit()

    for notification in notifications:
        db.refresh(notification)
        notification_ws_manager.notify_threadsafe(
            notification.user_id, notification_to_payload(notification)
        )

    return notifications


def notify_all_employees(
    db: Session,
    *,
    title: str,
    message: str,
    event_type: Optional[str] = None,
    reference_type: Optional[str] = None,
    reference_id: Optional[int] = None,
    created_by: Optional[int] = None
) -> List[Notification]:
    employee_ids = [
        user_id
        for (user_id,) in db.query(User.id).filter(User.role == "employee", User.is_active == True).all()
    ]
    return push_notifications(
        db,
        user_ids=employee_ids,
        title=title,
        message=message,
        event_type=event_type,
        reference_type=reference_type,
        reference_id=reference_id,
        created_by=created_by,
    )


def notify_all_admins(
    db: Session,
    *,
    title: str,
    message: str,
    event_type: Optional[str] = None,
    reference_type: Optional[str] = None,
    reference_id: Optional[int] = None,
    created_by: Optional[int] = None
) -> List[Notification]:
    admin_ids = [
        user_id
        for (user_id,) in db.query(User.id).filter(User.role == "admin", User.is_active == True).all()
    ]
    return push_notifications(
        db,
        user_ids=admin_ids,
        title=title,
        message=message,
        event_type=event_type,
        reference_type=reference_type,
        reference_id=reference_id,
        created_by=created_by,
    )


def ensure_tomorrow_holiday_notifications(db: Session) -> int:
    tomorrow = date.today() + timedelta(days=1)
    employees = [uid for (uid,) in db.query(User.id).filter(User.role == "employee", User.is_active == True).all()]
    if not employees:
        return 0

    holidays = db.query(Holiday).filter(
        (Holiday.date == tomorrow) |
        and_(
            Holiday.repeat_yearly == True,
            extract("month", Holiday.date) == tomorrow.month,
            extract("day", Holiday.date) == tomorrow.day
        )
    ).all()

    created_count = 0
    for holiday in holidays:
        msg = f"Reminder: Tomorrow ({tomorrow.isoformat()}) is holiday - {holiday.name}."
        for user_id in employees:
            exists = db.query(Notification.id).filter(
                Notification.user_id == user_id,
                Notification.event_type == "holiday_tomorrow_reminder",
                Notification.reference_type == "holiday",
                Notification.reference_id == holiday.id,
                Notification.message == msg
            ).first()
            if exists:
                continue

            notification = Notification(
                user_id=user_id,
                title="Holiday Reminder",
                message=msg,
                event_type="holiday_tomorrow_reminder",
                reference_type="holiday",
                reference_id=holiday.id,
                is_read=False
            )
            db.add(notification)
            db.flush()
            db.refresh(notification)
            notification_ws_manager.notify_threadsafe(user_id, notification_to_payload(notification))
            created_count += 1

    if created_count:
        db.commit()
    return created_count
