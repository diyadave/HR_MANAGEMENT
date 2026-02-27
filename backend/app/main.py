
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from app.database.session import engine
from app.database.base import Base
from app.models.user import User
from app.models.user_session import UserSession
from app.models.notification import Notification
from app.models.chat import ChatConversation, ChatConversationMember, ChatMessage
from app.routes import admin
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime, timezone
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from app.routes import auth, admin, notices ,tasks
from app.routes import projects
from app.routes import employee_projects
from app.routes import attendance
from app.routes import leaves,profile
from app.routes import notifications
from fastapi.staticfiles import StaticFiles
from app.models.holiday import Holiday  
from app.models.attendance_edit_log import AttendanceEditLog
from app.models.research import ResearchColumn, ResearchRow, ResearchCell, ResearchColumnPermission, ResearchDocument, ResearchDocumentPermission
from app.schemas.research import ResearchFileCreate, ResearchFileOut, CellUpdate
from app.routes import research,holiday
from app.routes import chat
from app.core.security import decode_token
from app.core.attendance_ws_manager import attendance_ws_manager
from app.core.notification_ws_manager import notification_ws_manager
from app.database.session import SessionLocal

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


def _format_validation_messages(exc: RequestValidationError, request: Request) -> list[str]:
    messages: list[str] = []
    for err in exc.errors():
        loc = [str(v) for v in err.get("loc", []) if str(v) not in {"body", "query", "path"}]
        field = ".".join(loc) if loc else "field"
        err_type = str(err.get("type", ""))
        message = str(err.get("msg", "Invalid value"))

        if request.url.path == "/admin/tasks" and field == "assigned_to":
            messages.append("Please select at least one employee.")
            continue

        if err_type in {"missing", "value_error.missing"}:
            messages.append(f"{field} is required")
        elif "string_too_short" in err_type:
            messages.append(f"{field} cannot be empty")
        elif "none.not_allowed" in err_type:
            messages.append(f"{field} cannot be null")
        elif field:
            messages.append(f"{field}: {message}")
        else:
            messages.append(message)

    # Preserve order while de-duplicating.
    return list(dict.fromkeys(messages))


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    messages = _format_validation_messages(exc, request)
    detail = messages[0] if len(messages) == 1 else "Validation failed"
    return JSONResponse(
        status_code=422,
        content={
            "detail": detail,
            "errors": messages,
        },
    )


app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(notices.router)
app.include_router(projects.router)
app.include_router(employee_projects.router)
app.include_router(tasks.router)
app.include_router(leaves.router)
app.include_router(notifications.router)
app.include_router(attendance.router, prefix="/attendance", tags=["Attendance"])
app.include_router(profile.router)
app.include_router(research.router)
app.include_router(holiday.router)
app.include_router(chat.router)
app.include_router(chat.ws_router)


@app.websocket("/ws/attendance/stream")
async def attendance_stream_ws(websocket: WebSocket):
    await attendance_ws_manager.connect_stream(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        attendance_ws_manager.disconnect_stream(websocket)


@app.websocket("/ws/attendance/{user_id}")
async def attendance_ws(websocket: WebSocket, user_id: int):
    await attendance_ws_manager.connect(user_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        attendance_ws_manager.disconnect(user_id)


@app.websocket("/ws/notifications/{user_id}")
async def notifications_ws(websocket: WebSocket, user_id: int):
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4401, reason="Missing token")
        return

    payload = decode_token(token)
    if payload is None or payload.get("token_type") != "access":
        await websocket.close(code=4401, reason="Invalid token")
        return

    sub = payload.get("sub")
    sid = payload.get("sid")
    if not sub or not sid:
        await websocket.close(code=4401, reason="Invalid token payload")
        return

    try:
        token_user_id = int(sub)
    except Exception:
        await websocket.close(code=4401, reason="Invalid token subject")
        return

    if token_user_id != user_id:
        await websocket.close(code=4403, reason="Forbidden")
        return

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        session = db.query(UserSession).filter(
            UserSession.user_id == user_id,
            UserSession.session_id == sid,
            UserSession.revoked_at == None
        ).first()
        if not user or not session or session.expires_at < datetime.now(timezone.utc):
            await websocket.close(code=4401, reason="Session expired")
            return
    finally:
        db.close()

    await notification_ws_manager.connect(user_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        notification_ws_manager.disconnect(user_id)






