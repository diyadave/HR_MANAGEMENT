from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from app.models.user import User
from fastapi import HTTPException, status
from datetime import datetime, timezone
from app.models.task import Task
from app.schemas.task import TaskCreate, TaskOut
from app.database.session import get_db
from app.models.project import Project
from app.schemas.project import ProjectCreate, ProjectOut
from app.core.dependencies import get_current_admin
from sqlalchemy.orm import Session



router = APIRouter(prefix="/admin/projects", tags=["Projects"])


def serialize_project(project: Project):
    tasks = project.tasks or []
    task_count = len(tasks)
    completed_count = len([t for t in tasks if t.status == "completed"])
    project_progress = int(round((completed_count / task_count) * 100)) if task_count else 0

    now = datetime.now(timezone.utc)
    total_seconds = 0
    for task in tasks:
        for log in (task.time_logs or []):
            if not log.start_time:
                continue
            end_time = log.end_time or now
            if end_time > log.start_time:
                total_seconds += int((end_time - log.start_time).total_seconds())

    return {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "start_date": project.start_date,
        "end_date": project.end_date,
        "status": project.status,
        "created_by": project.created_by,
        "owner_id": project.owner_id,
        "created_at": project.created_at,
        "owner": project.owner,
        "team_members": project.team_members or [],
        "tasks": tasks,
        "task_count": task_count,
        "project_progress": project_progress,
        "total_hours": round(total_seconds / 3600, 1),
    }

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
    projects = db.query(Project).order_by(Project.created_at.desc()).all()
    return [serialize_project(project) for project in projects]


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

    return serialize_project(project)




