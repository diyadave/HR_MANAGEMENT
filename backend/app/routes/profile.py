# backend/app/routes/profile.py

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.user import ProfileUpdateSchema, ProfileResponse
from fastapi import UploadFile, File
import shutil
import os
import uuid

from fastapi import UploadFile, File, HTTPException


UPLOAD_DIR = "uploads/profile_images"
router = APIRouter(prefix="/profile", tags=["Profile"])


# ---------------- GET PROFILE ----------------
@router.get("/", response_model=ProfileResponse)
def get_profile(
    current_user: User = Depends(get_current_user)
):
    return current_user


# ---------------- UPDATE PROFILE ----------------
@router.put("/")
def update_profile(
    data: ProfileUpdateSchema,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    updates = data.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(current_user, field, value)

    db.commit()
    db.refresh(current_user)

    return {"message": "Profile updated successfully"}




@router.post("/upload-image")
def upload_profile_image(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    allowed_types = ["image/jpeg", "image/png", "image/webp"]

    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Invalid file type")

    MAX_FILE_SIZE = 2 * 1024 * 1024
    contents = file.file.read()

    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large")

    file.file.seek(0)

    os.makedirs(UPLOAD_DIR, exist_ok=True)

    extension = file.filename.split(".")[-1]
    unique_filename = f"{current_user.id}_{uuid.uuid4().hex}.{extension}"
    file_path = os.path.join(UPLOAD_DIR, unique_filename)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    current_user.profile_image = file_path
    db.commit()
    db.refresh(current_user)

    return {
        "message": "Image uploaded successfully",
        "path": file_path
    }
