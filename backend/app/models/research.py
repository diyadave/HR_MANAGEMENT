from sqlalchemy import Column, Integer, String, ForeignKey, Text, Boolean, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database.base import Base


# ===============================
# COMMON FILE TABLE
# ===============================

class ResearchFile(Base):
    __tablename__ = "research_files"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    type = Column(String, nullable=False)  # excel | document
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    creator = relationship("User")


# ===============================
# EXCEL TABLES
# ===============================

class ResearchColumn(Base):
    __tablename__ = "research_columns"

    id = Column(Integer, primary_key=True)
    file_id = Column(Integer, ForeignKey("research_files.id", ondelete="CASCADE"))
    column_name = Column(String, nullable=False)
    column_order = Column(Integer)


class ResearchRow(Base):
    __tablename__ = "research_rows"

    id = Column(Integer, primary_key=True)
    file_id = Column(Integer, ForeignKey("research_files.id", ondelete="CASCADE"))
    row_number = Column(Integer)


class ResearchCell(Base):
    __tablename__ = "research_cells"

    id = Column(Integer, primary_key=True)
    row_id = Column(Integer, ForeignKey("research_rows.id", ondelete="CASCADE"))
    column_id = Column(Integer, ForeignKey("research_columns.id", ondelete="CASCADE"))
    value = Column(Text)
    updated_by = Column(Integer, ForeignKey("users.id"))
    updated_at = Column(DateTime(timezone=True), server_default=func.now())


class ResearchColumnPermission(Base):
    __tablename__ = "research_column_permissions"

    id = Column(Integer, primary_key=True)
    column_id = Column(Integer, ForeignKey("research_columns.id", ondelete="CASCADE"))
    user_id = Column(Integer, ForeignKey("users.id"))
    can_view = Column(Boolean, default=False)
    can_edit = Column(Boolean, default=False)


# ===============================
# DOCUMENT TABLES
# ===============================

class ResearchDocument(Base):
    __tablename__ = "research_documents"

    id = Column(Integer, primary_key=True)
    file_id = Column(Integer, ForeignKey("research_files.id", ondelete="CASCADE"))
    title = Column(String, nullable=False)
    content = Column(Text)
    visibility = Column(String, default="admin")  # admin | everyone | selected
    updated_at = Column(DateTime(timezone=True), server_default=func.now())


class ResearchDocumentPermission(Base):
    __tablename__ = "research_document_permissions"

    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("research_documents.id", ondelete="CASCADE"))
    user_id = Column(Integer, ForeignKey("users.id"))
