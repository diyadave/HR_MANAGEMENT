from pydantic import BaseModel
from datetime import date, datetime
from typing import Optional


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



from app.schemas.user import UserOut

class TaskOut(BaseModel):
    id: int
    title: str
    description: Optional[str]
    status: str
    due_date: Optional[date]
    priority: Optional[str]
    estimated_hours: Optional[float]
    assigned_user: UserOut | None
    created_user: UserOut | None
    created_at: datetime

    class Config:
        from_attributes = True

