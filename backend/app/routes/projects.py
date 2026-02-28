from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from app.models.user import User
from fastapi import HTTPException
from datetime import datetime, timezone
from app.models.task import Task
from app.schemas.task import TaskOut
from app.database.session import get_db
from app.models.project import Project
from app.schemas.project import ProjectCreate, ProjectOut
from app.core.dependencies import get_current_admin
from app.services.notification_service import push_notifications
from app.core.validation import require_employee_exists, require_non_empty_list, require_non_empty_text



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
    data.name = require_non_empty_text(data.name, "Project name")
    data.description = require_non_empty_text(data.description, "Project description")
    if data.end_date < data.start_date:
        raise HTTPException(status_code=400, detail="Project end date cannot be before start date")

    owner = require_employee_exists(db, int(data.owner_id), detail="Project owner not found")
    project = Project(
        name=data.name,
        description=data.description,
        start_date=data.start_date,
        end_date=data.end_date,
        created_by=admin.id,
        owner_id=data.owner_id
    )

    project.team_members.append(owner)

    member_ids = sorted({int(uid) for uid in (data.team_members or []) if int(uid) > 0})
    if member_ids:
        users = db.query(User).filter(
            User.id.in_(member_ids),
            User.role == "employee",
            User.is_active == True,  # noqa: E712
        ).all()
        if len(users) != len(member_ids):
            raise HTTPException(status_code=400, detail="One or more team members are invalid")
        for user in users:
            if user.id != data.owner_id:
                project.team_members.append(user)

    if not project.team_members:
        raise HTTPException(status_code=400, detail="Please select at least one employee.")

    db.add(project)
    db.commit()
    db.refresh(project)

    assigned_user_ids = [member.id for member in (project.team_members or []) if member.role == "employee"]
    push_notifications(
        db,
        user_ids=assigned_user_ids,
        title="Added to a project",
        message=f"You have been added to project: {project.name}",
        event_type="project_assigned",
        reference_type="project",
        reference_id=project.id,
        created_by=admin.id
    )

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

    validated_user_ids = require_non_empty_list(user_ids, "Please select at least one employee.")
    unique_user_ids = sorted({int(uid) for uid in validated_user_ids if int(uid) > 0})
    if not unique_user_ids:
        raise HTTPException(status_code=400, detail="Please select at least one employee.")

    old_member_ids = {member.id for member in (project.team_members or [])}
    users = db.query(User).filter(
        User.id.in_(unique_user_ids),
        User.role == "employee",
        User.is_active == True,  # noqa: E712
    ).all()
    if len(users) != len(unique_user_ids):
        raise HTTPException(status_code=400, detail="One or more team members are invalid")
    project.team_members = users

    db.commit()
    new_member_ids = {member.id for member in users}
    added_member_ids = sorted(new_member_ids - old_member_ids)
    push_notifications(
        db,
        user_ids=added_member_ids,
        title="Added to a project",
        message=f"You have been added to project: {project.name}",
        event_type="project_assigned",
        reference_type="project",
        reference_id=project.id,
        created_by=admin.id
    )
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


@router.put("/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: int,
    data: ProjectCreate,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin)
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    data.name = require_non_empty_text(data.name, "Project name")
    data.description = require_non_empty_text(data.description, "Project description")
    if data.end_date < data.start_date:
        raise HTTPException(status_code=400, detail="Project end date cannot be before start date")

    owner = require_employee_exists(db, int(data.owner_id), detail="Project owner not found")

    old_member_ids = {member.id for member in (project.team_members or []) if member.role == "employee"}

    project.name = data.name
    project.description = data.description
    project.start_date = data.start_date
    project.end_date = data.end_date
    project.owner_id = data.owner_id

    member_ids = sorted({int(uid) for uid in (data.team_members or []) if int(uid) > 0})
    users = []
    if member_ids:
        users = db.query(User).filter(
            User.id.in_(member_ids),
            User.role == "employee",
            User.is_active == True,  # noqa: E712
        ).all()
        if len(users) != len(member_ids):
            raise HTTPException(status_code=400, detail="One or more team members are invalid")

    team_by_id = {owner.id: owner}
    for user in users:
        team_by_id[user.id] = user
    project.team_members = list(team_by_id.values())

    db.commit()
    db.refresh(project)

    new_member_ids = {member.id for member in (project.team_members or []) if member.role == "employee"}
    added_member_ids = sorted(new_member_ids - old_member_ids)
    push_notifications(
        db,
        user_ids=added_member_ids,
        title="Added to a project",
        message=f"You have been added to project: {project.name}",
        event_type="project_assigned",
        reference_type="project",
        reference_id=project.id,
        created_by=admin.id
    )

    return serialize_project(project)


@router.delete("/{project_id}")
def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    admin=Depends(get_current_admin)
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    db.delete(project)
    db.commit()
    return {"message": "Project deleted successfully"}




