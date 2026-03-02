from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime, timezone

from app.database.session import get_db
from app.models.project import Project
from app.schemas.project import ProjectOut
from app.core.dependencies import get_current_user

router = APIRouter(prefix="/projects", tags=["Employee Projects"])


def serialize_project(project: Project) -> dict:
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


@router.get("/my", response_model=List[ProjectOut])
def get_my_projects(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    projects = db.query(Project).filter(
        (Project.owner_id == current_user.id) |
        (Project.team_members.any(id=current_user.id))
    ).all()
    return [serialize_project(project) for project in projects]

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

    return serialize_project(project)
