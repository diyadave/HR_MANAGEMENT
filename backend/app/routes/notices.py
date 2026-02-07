from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime

from app.database.session import get_db
from app.models.notice import Notice
from app.schemas.notice import NoticeCreate, NoticeResponse
from app.core.dependencies import get_current_admin, get_current_user

router = APIRouter(prefix="/notices", tags=["Notices"])


# -----------------------------
# Admin: Create Notice
# -----------------------------
@router.post("/", response_model=NoticeResponse)
def create_notice(
    data: NoticeCreate,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin)
):
    notice = Notice(
        title=data.title,
        description=data.description,
        category=data.category,
        expires_at=data.expires_at,
        created_by=admin.id
    )

    db.add(notice)
    db.commit()
    db.refresh(notice)
    return notice


# -----------------------------
# Admin + Employee: Get Notices
# -----------------------------
@router.get("/", response_model=List[NoticeResponse])
def get_notices(
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    query = db.query(Notice).filter(Notice.is_active == True)

    # hide expired notices from employees
    query = query.filter(
        (Notice.expires_at == None) | (Notice.expires_at >= datetime.utcnow())
    )

    return query.order_by(Notice.created_at.desc()).all()


# -----------------------------
# Admin: Disable Notice
# -----------------------------
@router.put("/{notice_id}", response_model=NoticeResponse)
def update_notice(
    notice_id: int,
    data: NoticeCreate,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin)
):
    notice = db.query(Notice).filter(Notice.id == notice_id).first()

    if not notice:
        raise HTTPException(status_code=404, detail="Notice not found")

    notice.title = data.title
    notice.description = data.description
    notice.category = data.category
    notice.expires_at = data.expires_at

    db.commit()
    db.refresh(notice)
    return notice

@router.patch("/{notice_id}/toggle", response_model=NoticeResponse)
def toggle_notice_status(
    notice_id: int,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin)
):
    notice = db.query(Notice).filter(Notice.id == notice_id).first()

    if not notice:
        raise HTTPException(status_code=404, detail="Notice not found")

    notice.is_active = not notice.is_active
    db.commit()
    db.refresh(notice)

    return notice
