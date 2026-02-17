from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from app.models.user import User
from fastapi import HTTPException, status
import datetime
from app.models.task import Task
from app.schemas.task import TaskCreate, TaskOut
from app.database.session import get_db
from app.models.project import Project
from app.schemas.project import ProjectCreate, ProjectOut
from app.core.dependencies import get_current_admin
from sqlalchemy.orm import Session



router = APIRouter(prefix="/admin/projects", tags=["Projects"])

@router.post("/", response_model=ProjectOut)
def create_project(
    data: ProjectCreate,
    db: Session = Depends(get_db),
    admin = Depends(get_current_admin)
):
    project = Project(
        name=data.name,
        description=data.description,
        start_date=data.start_date,
        end_date=data.end_date,
        created_by=admin.id,
        owner_id=data.owner_id
    )

         
    owner = db.query(User).filter(User.id == data.owner_id).first()
    if owner:
        project.team_members.append(owner)

  
    if data.team_members:
        users = db.query(User).filter(User.id.in_(data.team_members)).all()
        for user in users:
            if user.id != data.owner_id:
                project.team_members.append(user)

    db.add(project)
    db.commit()
    db.refresh(project)

    return project



@router.get("/", response_model=List[ProjectOut])
def get_projects(
    db: Session = Depends(get_db),
    admin = Depends(get_current_admin)
):
    return db.query(Project).order_by(Project.created_at.desc()).all()


@router.post("/{project_id}/team")
def assign_team_members(
    project_id: int,
    user_ids: List[int],
    db: Session = Depends(get_db),
    admin = Depends(get_current_admin)
):
    project = db.query(Project).filter(Project.id == project_id).first()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    users = db.query(User).filter(User.id.in_(user_ids)).all()
    project.team_members = users

    db.commit()
    return {"message": "Team assigned successfully"}

from app.core.dependencies import get_current_user


@router.get("/{project_id}/tasks", response_model=List[TaskOut])
def get_project_tasks_admin(
    project_id: int,
    db: Session = Depends(get_db),
    admin = Depends(get_current_admin)
):
    project = db.query(Project).filter(Project.id == project_id).first()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    return project.tasks


@router.get("/{project_id}", response_model=ProjectOut)
def get_project_detail(
    project_id: int,
    db: Session = Depends(get_db),
    admin = Depends(get_current_admin)
):
    project = db.query(Project).filter(Project.id == project_id).first()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    return project




