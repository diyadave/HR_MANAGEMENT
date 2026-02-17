from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Date,
    DateTime,
    ForeignKey,
    Float
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database.base import Base


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)

    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    status = Column(
        String(50),
        default="pending"
    )  # pending | in_progress | completed

    due_date = Column(Date, nullable=True)
    estimated_hours = Column(Float, nullable=True)
    
    # 🔗 relations
    project_id = Column(
        Integer,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False
    )
    priority = Column(
    String(20),
    default="medium"
    )  # low | medium | high
    assigned_to = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    created_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    # =====================
    # Relationships
    # =====================
    project = relationship(
        "Project",
        back_populates="tasks"
    )

    assigned_user = relationship("User", foreign_keys=[assigned_to])
    created_user = relationship("User", foreign_keys=[created_by])

