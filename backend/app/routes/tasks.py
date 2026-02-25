from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc, case, func
from typing import List, Optional
from datetime import datetime, timezone, timedelta

from app.database.session import get_db
from app.models.task import Task
from app.models.project import Project
from app.schemas.task import (
    TaskCreate, TaskOut, TaskUpdate, 
    TaskHistoryResponse, TaskTimeLogOut
)
from app.models.task_time_log import TaskTimeLog
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.attendance import Attendance
from app.services.attendance_service import auto_close_open_attendances_for_user, is_break_time_ist

router = APIRouter(prefix="/tasks", tags=["Tasks"])


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
        estimated_hours=payload.estimated_hours,
        status="pending"
    )

    db.add(task)
    db.commit()
    db.refresh(task)

    return task


# =====================================
# GET TASKS (Limited to 15 active tasks)
# =====================================
@router.get("/", response_model=List[TaskOut])
def get_my_tasks(
    limit: int = Query(15, ge=1, le=50),
    include_completed: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get tasks for current user - limited to 15 active tasks by default"""
    query = db.query(Task).filter(Task.assigned_to == current_user.id)
    
    if not include_completed:
        # Exclude completed tasks from main view
        query = query.filter(Task.status != "completed")
    
    # Order by: active first, then by created_at desc
    query = query.order_by(
        # Custom ordering: in_progress first, then pending, then others
        case(
            (Task.status == "in_progress", 0),
            (Task.status == "pending", 1),
            else_=2
        ),
        desc(Task.created_at)
    )
    
    tasks = query.limit(limit).all()
    if not tasks:
        return []

    task_ids = [t.id for t in tasks]
    now = datetime.now(timezone.utc)

    totals = db.query(
        TaskTimeLog.task_id,
        func.coalesce(
            func.sum(
                case(
                    (TaskTimeLog.end_time.is_(None), func.extract("epoch", now - TaskTimeLog.start_time)),
                    else_=func.extract("epoch", TaskTimeLog.end_time - TaskTimeLog.start_time)
                )
            ),
            0
        ).label("total_seconds")
    ).filter(
        TaskTimeLog.user_id == current_user.id,
        TaskTimeLog.task_id.in_(task_ids)
    ).group_by(TaskTimeLog.task_id).all()

    totals_map = {task_id: int(total_seconds or 0) for task_id, total_seconds in totals}

    result = []
    for task in tasks:
        payload = TaskOut.model_validate(task).model_dump()
        payload["total_time_spent"] = round((totals_map.get(task.id, 0) / 3600), 2)
        result.append(payload)

    return result


# =====================================
# GET TASK HISTORY (All time logs)
# =====================================
@router.get("/history", response_model=List[TaskHistoryResponse])
def get_task_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=200)
):
    """Get completed tasks with their time logs"""
    
    # Get completed tasks for this user
    completed_tasks = db.query(Task).filter(
        Task.assigned_to == current_user.id,
        Task.status == "completed"
    ).order_by(desc(Task.completed_at)).limit(limit).all()
    
    result = []
    
    for task in completed_tasks:
        # Get all time logs for this task
        logs = db.query(TaskTimeLog).filter(
            TaskTimeLog.task_id == task.id,
            TaskTimeLog.user_id == current_user.id
        ).order_by(desc(TaskTimeLog.start_time)).all()
        
        # Calculate total time
        total_seconds = 0
        log_list = []
        
        for log in logs:
            log_out = TaskTimeLogOut.model_validate(log)
            if log.end_time:
                duration = (log.end_time - log.start_time).total_seconds()
                log_out.duration_seconds = int(duration)
                total_seconds += duration
            log_list.append(log_out)
        
        result.append(TaskHistoryResponse(
            task_id=task.id,
            task_title=task.title,
            total_time_seconds=int(total_seconds),
            total_time_hours=round(total_seconds / 3600, 2),
            logs=log_list,
            completed_at=task.completed_at,
            completed_by_name=task.completed_user.name if task.completed_user else None
        ))
    
    return result


# =====================================
# UPDATE TASK
# =====================================
@router.put("/{task_id}", response_model=TaskOut)
def update_task(
    task_id: int, 
    payload: TaskUpdate, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    task = db.query(Task).filter(
        Task.id == task_id,
        Task.assigned_to == current_user.id
    ).first()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    for key, value in payload.dict(exclude_unset=True).items():
        setattr(task, key, value)

    db.commit()
    db.refresh(task)
    return task


# =====================================
# START TASK
# =====================================
@router.post("/{task_id}/start")
def start_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    now = datetime.now(timezone.utc)
    auto_close_open_attendances_for_user(current_user.id, db, now=now)

    if is_break_time_ist(now):
        raise HTTPException(
            status_code=400,
            detail="Task timer is disabled during break time (1:00 PM to 2:00 PM IST)."
        )

    # Check if user is clocked in today
    today = now.date()
    attendance = db.query(Attendance).filter(
        Attendance.user_id == current_user.id,
        Attendance.date == today,
        Attendance.clock_in_time != None
    ).first()

    if not attendance:
        raise HTTPException(
            status_code=400,
            detail="You must be clocked in to start a task"
        )

    # Get task and verify assignment
    task = db.query(Task).filter(
        Task.id == task_id,
        Task.assigned_to == current_user.id
    ).first()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Check if task is already completed
    if task.status == "completed":
        raise HTTPException(status_code=400, detail="Cannot start a completed task")

    # Check if user has any running task and auto-stop it before switching.
    running = db.query(TaskTimeLog).filter(
        TaskTimeLog.user_id == current_user.id,
        TaskTimeLog.end_time == None
    ).first()

    if running:
        if running.task_id == task_id:
            current_duration = int((now - running.start_time).total_seconds())
            return {
                "message": "Task already running",
                "task_id": task_id,
                "task_title": task.title,
                "status": task.status,
                "duration_seconds": current_duration
            }
        running.end_time = now

    # Create time log
    log = TaskTimeLog(
        task_id=task_id,
        user_id=current_user.id,
        start_time=now
    )

    # Update task status to in_progress if it was pending
    if task.status == "pending":
        task.status = "in_progress"

    db.add(log)
    db.commit()

    return {
        "message": "Task started successfully",
        "task_id": task_id,
        "task_title": task.title,
        "status": task.status
    }


# =====================================
# STOP TASK
# =====================================
@router.post("/{task_id}/stop")
def stop_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Find running log for this task
    log = db.query(TaskTimeLog).filter(
        TaskTimeLog.task_id == task_id,
        TaskTimeLog.user_id == current_user.id,
        TaskTimeLog.end_time == None
    ).first()

    if not log:
        raise HTTPException(status_code=400, detail="No running timer found for this task")

    # Stop the timer
    log.end_time = datetime.now(timezone.utc)
    
    # Calculate duration and update if needed (optional)
    duration = (log.end_time - log.start_time).total_seconds()
    
    db.commit()

    return {
        "message": "Task stopped successfully",
        "task_id": task_id,
        "duration_seconds": int(duration),
        "duration_hours": round(duration / 3600, 2)
    }


# =====================================
# COMPLETE TASK
# =====================================
@router.post("/{task_id}/complete")
def complete_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Get task
    task = db.query(Task).filter(
        Task.id == task_id,
        Task.assigned_to == current_user.id
    ).first()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.status == "completed":
        raise HTTPException(status_code=400, detail="Task is already completed")

    # Stop any running timer for this task
    running_log = db.query(TaskTimeLog).filter(
        TaskTimeLog.task_id == task_id,
        TaskTimeLog.user_id == current_user.id,
        TaskTimeLog.end_time == None
    ).first()

    if running_log:
        running_log.end_time = datetime.now(timezone.utc)

    # Update task status
    task.status = "completed"
    task.completed_at = datetime.now(timezone.utc)
    task.completed_by = current_user.id

    db.commit()
    db.refresh(task)

    return {
        "message": "Task marked as completed",
        "task_id": task_id,
        "task_title": task.title,
        "completed_at": task.completed_at
    }


# =====================================
# GET ACTIVE TASK
# =====================================
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
    if not task:
        return None

    now = datetime.now(timezone.utc)
    completed_seconds = db.query(
        func.coalesce(
            func.sum(
                func.extract("epoch", TaskTimeLog.end_time - TaskTimeLog.start_time)
            ),
            0
        )
    ).filter(
        TaskTimeLog.user_id == current_user.id,
        TaskTimeLog.task_id == log.task_id,
        TaskTimeLog.end_time != None
    ).scalar() or 0

    running_seconds = int((now - log.start_time).total_seconds())

    return {
        "id": task.id,
        "title": task.title,
        "start_time": log.start_time,
        "status": task.status,
        "total_seconds": int(completed_seconds) + running_seconds
    }


