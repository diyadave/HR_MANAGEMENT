from __future__ import annotations

from typing import Any, Iterable

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.user import User


def require_non_empty_text(value: Any, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field_name} is required",
        )
    return text


def require_non_empty_list(values: Iterable[Any] | None, detail: str) -> list[Any]:
    normalized = list(values or [])
    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
        )
    return normalized


def require_employee_exists(db: Session, user_id: int, detail: str = "Employee not found") -> User:
    employee = db.query(User).filter(
        User.id == user_id,
        User.role == "employee",
        User.is_active == True,  # noqa: E712
    ).first()
    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail,
        )
    return employee


def ensure_employees_available(db: Session) -> int:
    count = db.query(User).filter(
        User.role == "employee",
        User.is_active == True,  # noqa: E712
    ).count()
    if count <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No employees available. Please create an employee first.",
        )
    return count
