from pydantic import BaseModel
from datetime import date, datetime
from typing import Optional, List
from app.schemas.user import UserOut
from app.schemas.task import TaskOut


# ---------- CREATE ----------
from typing import List, Optional

class ProjectCreate(BaseModel):
    name: str
    description: str
    start_date: date
    end_date: date
    owner_id: int
    team_members: Optional[List[int]] = []
                 

# ---------- UPDATE ----------
class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    status: Optional[str] = None


# ---------- RESPONSE ----------
class ProjectOut(BaseModel):
    id: int
    name: str
    description: Optional[str]
    start_date: Optional[date]
    end_date: Optional[date]
    status: str

    created_by: int                  # admin
    owner_id: int                    # employee owner
    created_at: datetime

    # relations (READ ONLY)
    owner: Optional[UserOut] = None
    team_members: Optional[List[UserOut]] = []
    tasks: Optional[List[TaskOut]] = []
    task_count: int = 0
    project_progress: int = 0
    total_hours: float = 0.0

    class Config:
        from_attributes = True
