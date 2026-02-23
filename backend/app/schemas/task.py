from pydantic import BaseModel
from datetime import date, datetime
from typing import Optional, List
from enum import Enum
from app.schemas.user import UserOut
from pydantic import BaseModel
from datetime import date
from typing import Optional

class TaskStatusEnum(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class TaskPriorityEnum(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# ---------- CREATE ----------
class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    due_date: Optional[date] = None
    assigned_to: int
    project_id: int
    priority: Optional[str] = "medium"
    estimated_hours: Optional[float] = None


# ---------- UPDATE ----------
class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    due_date: Optional[date] = None
    assigned_to: Optional[int] = None
    priority: Optional[str] = None
    estimated_hours: Optional[float] = None


# ---------- TIME LOG SCHEMA ----------
class TaskTimeLogOut(BaseModel):
    id: int
    task_id: int
    user_id: int
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    
    class Config:
        from_attributes = True


# ---------- TASK HISTORY RESPONSE ----------
class TaskHistoryResponse(BaseModel):
    task_id: int
    task_title: str
    total_time_seconds: int
    total_time_hours: float
    logs: List[TaskTimeLogOut]
    completed_at: Optional[datetime] = None
    completed_by_name: Optional[str] = None


# ---------- OUT (with enhanced fields) ----------


class TaskOut(BaseModel):
    id: int
    title: str
    description: Optional[str]
    project_id: int
    project_name: Optional[str] = None
    assigned_to: Optional[int] = None
    assignee_name: Optional[str] = None
    assignee_profile_image: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    due_date: Optional[date]
    estimated_hours: Optional[float]
    total_time_spent: float = 0.0

    class Config:
        from_attributes = True
