from pydantic import BaseModel
from typing import Optional, List


# ===============================
# CREATE FILE
# ===============================

class ResearchFileCreate(BaseModel):
    name: str
    type: str  # excel | document

    # Excel fields
    rows: Optional[int] = None
    columns: Optional[int] = None

    # Document fields
    title: Optional[str] = None
    content: Optional[str] = None
    visibility: Optional[str] = "admin"
    user_ids: Optional[List[int]] = None


class ResearchFileOut(BaseModel):
    id: int
    name: str
    type: str

    class Config:
        from_attributes = True



class CellUpdate(BaseModel):
    value: str
