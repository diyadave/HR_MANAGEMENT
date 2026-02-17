from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Date,
    DateTime,
    ForeignKey,
    Table
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database.base import Base


# ===============================
# Association table (Project ↔ Team Members)
# ===============================
project_team_members = Table(
    "project_team_members",
    Base.metadata,
    Column("project_id", Integer, ForeignKey("projects.id", ondelete="CASCADE")),
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE")),
)

class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(Text)

    start_date = Column(Date)
    end_date = Column(Date)

    status = Column(String, default="active")

    # admin who created project
    created_by = Column(Integer, ForeignKey("users.id"))

    # project owner (employee)
    owner_id = Column(Integer, ForeignKey("users.id"))

    created_at = Column(DateTime, server_default=func.now())


    # ===============================
    # Relationships
    # ===============================

    # admin creator
    creator = relationship(
        "User",
        foreign_keys=[created_by]
    )

    # project owner (employee)
    owner = relationship(
        "User",
        foreign_keys=[owner_id]
    )

    # team members (employees)
    team_members = relationship(
        "User",
        secondary=project_team_members,
        lazy="selectin"
    )

    # tasks under this project
    tasks = relationship(
        "Task",
        back_populates="project",
        cascade="all, delete-orphan"
    )
