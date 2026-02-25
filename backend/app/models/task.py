from sqlalchemy import (
    Column, Integer, String, Text, Date, DateTime, 
    ForeignKey, Float, Enum
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import enum

from app.database.base import Base


class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class TaskPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(50), default=TaskStatus.PENDING.value, nullable=False)
    due_date = Column(Date, nullable=True)
    estimated_hours = Column(Float, nullable=True)
    
    # Relations
    project_id = Column(
        Integer,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False
    )
    priority = Column(String(20), default=TaskPriority.MEDIUM.value)
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
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    completed_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    project = relationship("Project", back_populates="tasks")
    assigned_user = relationship("User", foreign_keys=[assigned_to])
    created_user = relationship("User", foreign_keys=[created_by])
    completed_user = relationship("User", foreign_keys=[completed_by])
    time_logs = relationship("TaskTimeLog", back_populates="task", cascade="all, delete-orphan")

    @property
    def project_name(self):
        return self.project.name if self.project else None

    @property
    def assignee_name(self):
        return self.assigned_user.name if self.assigned_user else None

    @property
    def assignee_profile_image(self):
        return self.assigned_user.profile_image if self.assigned_user else None

    @property
    def created_by_name(self):
        return self.created_user.name if self.created_user else None

    @property
    def created_by_profile_image(self):
        return self.created_user.profile_image if self.created_user else None
