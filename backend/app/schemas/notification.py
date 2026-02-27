from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class NotificationOut(BaseModel):
    id: int
    user_id: int
    title: str
    message: str
    event_type: Optional[str] = None
    reference_type: Optional[str] = None
    reference_id: Optional[int] = None
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True

