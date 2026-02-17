from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.database.session import get_db
from app.models.task import Task
from app.models.project import Project
from app.schemas.task import TaskCreate, TaskOut, TaskUpdate
from app.models.task_time_log import TaskTimeLog
from app.core.dependencies import get_current_user
from app.models.user import User

from datetime import datetime, timezone
router = APIRouter(
    prefix="/tasks",
    tags=["Tasks"]
)


# =====================================
# CREATE TASK (Only Project Owner)
# =====================================
@router.post("/", response_model=TaskOut)
def create_task(
    payload: TaskCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    project = db.query(Project).filter(Project.id == payload.project_id).first()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # 🔐 Only owner can create tasks
    if project.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only project owner can create tasks"
        )


    team_ids = [u.id for u in project.team_members]
    if payload.assigned_to not in team_ids:
        raise HTTPException(
            status_code=400,
            detail="User is not a team member of this project"
        )

    task = Task(
    title=payload.title,
    description=payload.description,
    due_date=payload.due_date,
    project_id=payload.project_id,
    assigned_to=payload.assigned_to,
    created_by=current_user.id,
    priority=payload.priority,
    estimated_hours=payload.estimated_hours
    )


    db.add(task)
    db.commit()
    db.refresh(task)

    return task


# =====================================
# GET TASKS (Employee sees only theirs)
# =====================================
@router.get("/", response_model=List[TaskOut])
def get_my_tasks(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return db.query(Task).filter(
        Task.assigned_to == current_user.id
    ).all()

@router.put("/{task_id}", response_model=TaskOut)
def update_task(task_id: int, payload: TaskUpdate, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    for key, value in payload.dict(exclude_unset=True).items():
        setattr(task, key, value)

    db.commit()
    db.refresh(task)
    return task


from app.models.attendance import Attendance
from datetime import date

@router.post("/{task_id}/start")
def start_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    today = datetime.now(timezone.utc).date()

    attendance = db.query(Attendance).filter(
        Attendance.user_id == current_user.id,
        Attendance.date == today,
        Attendance.clock_in_time != None
    ).first()

    if not attendance:
        raise HTTPException(
            status_code=400,
            detail="Clock in before starting a task"
        )

    task = db.query(Task).filter(
        Task.id == task_id,
        Task.assigned_to == current_user.id
    ).first()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    running = db.query(TaskTimeLog).filter(
        TaskTimeLog.user_id == current_user.id,
        TaskTimeLog.end_time == None
    ).first()

    if running:
        raise HTTPException(status_code=400, detail="Another task is already running")

    log = TaskTimeLog(
        task_id=task_id,
        user_id=current_user.id,
        start_time=datetime.now(timezone.utc)
    )

    db.add(log)
    db.commit()

    return {"message": "Timer started"}

@router.get("/active")
def get_active_task(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    log = db.query(TaskTimeLog).filter(
        TaskTimeLog.user_id == current_user.id,
        TaskTimeLog.end_time == None
    ).first()

    if not log:
        return None

    task = db.query(Task).filter(Task.id == log.task_id).first()

    return {
        "task_id": task.id,
        "task_title": task.title,
        "start_time": log.start_time
    }


from datetime import datetime, date

@router.post("/{task_id}/stop")
def stop_task(
    task_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    log = db.query(TaskTimeLog).filter(
        TaskTimeLog.task_id == task_id,
        TaskTimeLog.user_id == current_user.id,
        TaskTimeLog.end_time == None
    ).first()

    if not log:
        raise HTTPException(status_code=400, detail="No running task found")

    log.end_time = datetime.now(timezone.utc)
    db.commit()

    return {"message": "Task stopped successfully"}
