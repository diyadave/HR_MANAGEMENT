from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class NoticeCreate(BaseModel):
    title: str
    description: str
    category: Optional[str] = None
    expires_at: Optional[datetime] = None

class NoticeResponse(BaseModel):
    id: int
    title: str
    description: str
    category: Optional[str]
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True
