from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.database.session import get_db
from app.models.project import Project
from app.schemas.project import ProjectOut
from app.core.dependencies import get_current_user

router = APIRouter(prefix="/projects", tags=["Employee Projects"])

@router.get("/my", response_model=List[ProjectOut])
def get_my_projects(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    return db.query(Project).filter(
        (Project.owner_id == current_user.id) |
        (Project.team_members.any(id=current_user.id))
    ).all()

@router.get("/my/{project_id}", response_model=ProjectOut)
def get_my_project_detail(
    project_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    project = db.query(Project).filter(Project.id == project_id).first()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # 🔐 Security check
    if (
        project.owner_id != current_user.id
        and current_user not in project.team_members
    ):
        raise HTTPException(status_code=403, detail="Access denied")

    return project
