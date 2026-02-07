from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.user import User
from app.core.security import verify_password, create_access_token, hash_password
from app.schemas.user import LoginRequest, TokenResponse, ChangePasswordRequest
from app.core.dependencies import get_current_user

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()

    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # ✅ IMPORTANT FIX: sub MUST be user.id
    token = create_access_token({
        "sub": str(user.id),
        "role": user.role
    })

    return {
        "access_token": token,
        "role": user.role,
        "force_password_change": user.force_password_change
    }


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
