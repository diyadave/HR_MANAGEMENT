import secrets
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.config import settings
from app.database.session import get_db
from app.models.user import User
from app.models.user_session import UserSession
from app.core.security import (
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password
)
from app.schemas.user import LoginRequest, TokenResponse, ChangePasswordRequest, RefreshRequest
from app.schemas.user import ForgotPasswordRequest
from app.core.dependencies import get_current_user
from app.services.attendance_service import close_open_attendances_for_user
from app.utils.email import send_password_reset_credentials

router = APIRouter(prefix="/auth", tags=["Auth"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def _create_user_session(user_id: int, db: Session, now: datetime) -> UserSession:
    session_id = f"{user_id}_{int(now.timestamp())}_{now.microsecond}"
    session = UserSession(
        session_id=session_id,
        user_id=user_id,
        last_seen_at=now,
        expires_at=now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def _build_auth_response(user: User, session_id: str):
    token_payload = {
        "sub": str(user.id),
        "role": user.role,
        "sid": session_id
    }
    return {
        "access_token": create_access_token(token_payload),
        "refresh_token": create_refresh_token(
            token_payload,
            expires_days=settings.REFRESH_TOKEN_EXPIRE_DAYS
        ),
        "token_type": "bearer",
        "force_password_change": user.force_password_change,
        "user": {
            "id": user.id,
            "name": user.name,
            "role": user.role
        }
    }


@router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    login_id = (data.employee_id or "").strip()
    user = None

    # Hidden admin path: if login field looks like an email, allow admin login by email.
    if "@" in login_id:
        user = db.query(User).filter(
            User.email == login_id.lower(),
            User.role == "admin"
        ).first()
    else:
        user = db.query(User).filter(User.employee_id == login_id.upper()).first()

    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is inactive")

    now = datetime.now(timezone.utc)
    session = _create_user_session(user.id, db, now)
    return _build_auth_response(user, session.session_id)


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(data: RefreshRequest, db: Session = Depends(get_db)):
    payload = decode_token(data.refresh_token)
    if payload is None or payload.get("token_type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    sub = payload.get("sub")
    sid = payload.get("sid")
    if not sub or not sid:
        raise HTTPException(status_code=401, detail="Invalid refresh token payload")

    try:
        user_id = int(sub)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid refresh token subject")

    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not available")

    now = datetime.now(timezone.utc)
    session = db.query(UserSession).filter(
        UserSession.session_id == sid,
        UserSession.user_id == user_id,
        UserSession.revoked_at == None
    ).first()

    if not session or session.expires_at < now:
        raise HTTPException(status_code=401, detail="Refresh session expired")

    idle_timeout = timedelta(minutes=settings.SESSION_IDLE_TIMEOUT_MINUTES)
    if session.last_seen_at and (now - session.last_seen_at) > idle_timeout:
        close_at = session.last_seen_at + idle_timeout
        close_open_attendances_for_user(user_id, close_at, db)

    session.last_seen_at = now
    session.expires_at = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    db.commit()

    return _build_auth_response(user, session.session_id)




@router.post("/change-password")
def change_password(
    data: ChangePasswordRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    current_user.password_hash = hash_password(data.new_password)
    current_user.force_password_change = False
    db.commit()

    return {"message": "Password updated successfully"}


@router.post("/forgot-password")
def forgot_password(
    data: ForgotPasswordRequest,
    db: Session = Depends(get_db)
):
    employee_id = (data.employee_id or "").strip()
    email = (data.email or "").strip().lower()

    user = db.query(User).filter(
        User.employee_id == employee_id,
        User.email == email
    ).first()

    if not user:
        raise HTTPException(status_code=404, detail="Employee ID or email is incorrect")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is inactive")

    temp_password = secrets.token_urlsafe(8)
    user.password_hash = hash_password(temp_password)
    user.force_password_change = True
    try:
        send_password_reset_credentials(
            to_email=user.email,
            employee_id=user.employee_id or "",
            temp_password=temp_password,
            employee_name=user.name
        )
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Unable to send reset email. Please try again.")

    return {"message": "Temporary password sent to your email"}


@router.post("/logout")
def logout(
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
    current_user=Depends(get_current_user)
):
    payload = decode_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid token")

    sid = payload.get("sid")
    now = datetime.now(timezone.utc)
    close_open_attendances_for_user(current_user.id, now, db)

    if sid:
        session = db.query(UserSession).filter(
            UserSession.session_id == sid,
            UserSession.user_id == current_user.id,
            UserSession.revoked_at == None
        ).first()
        if session:
            session.revoked_at = now
            db.commit()

    return {"message": "Logged out successfully"}
