
from fastapi import FastAPI
from app.database.session import engine
from app.database.base import Base
from app.models.user import User
from app.models.user_session import UserSession
from app.models.chat import ChatConversation, ChatConversationMember, ChatMessage
from app.routes import admin
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime
from fastapi.middleware.cors import CORSMiddleware
from app.routes import auth, admin, notices ,tasks
from app.routes import projects
from app.routes import employee_projects
from app.routes import attendance
from app.routes import leaves,profile
from fastapi.staticfiles import StaticFiles
from app.models.holiday import Holiday  
from app.models.attendance_edit_log import AttendanceEditLog
from app.models.research import ResearchColumn, ResearchRow, ResearchCell, ResearchColumnPermission, ResearchDocument, ResearchDocumentPermission
from app.schemas.research import ResearchFileCreate, ResearchFileOut, CellUpdate
from app.routes import research,holiday
from app.routes import chat

app = FastAPI()

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500",
        "http://localhost:5500",
        "http://127.0.0.1:8000",
        "http://localhost:8000",
    ],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def create_tables():
    Base.metadata.create_all(bind=engine)


app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(notices.router)
app.include_router(projects.router)
app.include_router(employee_projects.router)
app.include_router(tasks.router)
app.include_router(leaves.router)
app.include_router(attendance.router, prefix="/attendance", tags=["Attendance"])
app.include_router(profile.router)
app.include_router(research.router)
app.include_router(holiday.router)
app.include_router(chat.router)
app.include_router(chat.ws_router)






