from datetime import datetime, timedelta, timezone
import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_admin, get_current_user
from app.core.security import decode_token
from app.database.session import get_db
from app.models.chat import ChatConversation, ChatConversationMember, ChatMessage
from app.models.user import User
from app.models.user_session import UserSession
from app.schemas.chat import (
    ChatConversationCreateGroup,
    ChatConversationCreatePrivate,
    ChatConversationOut,
    ChatMessageCreate,
    ChatMessageOut,
    ChatUnreadConversationCount,
    ChatUnreadSummaryOut,
    ChatUserOut,
)

router = APIRouter(prefix="/chat", tags=["Chat"])
ws_router = APIRouter(tags=["Chat"])


class ConnectionManager:
    def __init__(self) -> None:
        self.connections: dict[int, set[WebSocket]] = {}

    async def connect(self, user_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        self.connections.setdefault(user_id, set()).add(websocket)

    def disconnect(self, user_id: int, websocket: WebSocket) -> None:
        sockets = self.connections.get(user_id)
        if not sockets:
            return
        sockets.discard(websocket)
        if not sockets:
            self.connections.pop(user_id, None)

    async def send_to_user(self, user_id: int, payload: dict) -> None:
        sockets = list(self.connections.get(user_id, []))
        if not sockets:
            return
        await asyncio.gather(*(socket.send_json(payload) for socket in sockets), return_exceptions=True)

    async def broadcast_to_users(self, user_ids: list[int], payload: dict) -> None:
        await asyncio.gather(*(self.send_to_user(user_id, payload) for user_id in user_ids), return_exceptions=True)


manager = ConnectionManager()


def _active_online_user_ids(db: Session) -> set[int]:
    now = datetime.now(timezone.utc)
    online_since = now - timedelta(minutes=10)
    rows = db.query(UserSession.user_id).filter(
        UserSession.revoked_at == None,  # noqa: E711
        UserSession.expires_at > now,
        UserSession.last_seen_at >= online_since,
    ).all()
    return {row[0] for row in rows}


def _ensure_membership(db: Session, conversation_id: int, user_id: int) -> ChatConversation:
    conversation = db.query(ChatConversation).filter(ChatConversation.id == conversation_id).first()
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    is_member = db.query(ChatConversationMember.id).filter(
        ChatConversationMember.conversation_id == conversation_id,
        ChatConversationMember.user_id == user_id,
    ).first()
    if not is_member:
        raise HTTPException(status_code=403, detail="Not allowed for this conversation")
    return conversation


def _upsert_private_conversation(db: Session, current_user_id: int, target_user_id: int) -> ChatConversation:
    user_ids = sorted([current_user_id, target_user_id])
    private_key = f"{user_ids[0]}:{user_ids[1]}"
    existing = db.query(ChatConversation).filter(
        ChatConversation.is_group == False,  # noqa: E712
        ChatConversation.private_key == private_key,
    ).first()
    if existing:
        return existing

    conversation = ChatConversation(
        name=None,
        is_group=False,
        private_key=private_key,
        created_by=current_user_id,
    )
    db.add(conversation)
    db.flush()

    db.add(ChatConversationMember(conversation_id=conversation.id, user_id=current_user_id))
    db.add(ChatConversationMember(conversation_id=conversation.id, user_id=target_user_id))
    db.commit()
    db.refresh(conversation)
    return conversation


def _serialize_message(message: ChatMessage) -> dict:
    return {
        "id": message.id,
        "sender_id": message.sender_id,
        "conversation_id": message.conversation_id,
        "message": message.message,
        "timestamp": message.created_at.isoformat() if message.created_at else datetime.now(timezone.utc).isoformat(),
    }


def _conversation_unread_count(db: Session, conversation_id: int, user_id: int) -> int:
    membership = db.query(ChatConversationMember).filter(
        ChatConversationMember.conversation_id == conversation_id,
        ChatConversationMember.user_id == user_id,
    ).first()
    if not membership:
        return 0

    unread_count = db.query(func.count(ChatMessage.id)).filter(
        ChatMessage.conversation_id == conversation_id,
        ChatMessage.sender_id != user_id,
        ChatMessage.created_at > (membership.last_read_at or datetime(1970, 1, 1, tzinfo=timezone.utc)),
    ).scalar() or 0
    return int(unread_count)


def _conversation_payload(
    db: Session,
    conversation: ChatConversation,
    current_user: User,
    online_ids: set[int],
) -> ChatConversationOut:
    members = db.query(User).join(
        ChatConversationMember, ChatConversationMember.user_id == User.id
    ).filter(
        ChatConversationMember.conversation_id == conversation.id
    ).all()

    member_payload = [
        ChatUserOut(
            id=m.id,
            name=m.name,
            role=m.role,
            department=m.department,
            designation=m.designation,
            profile_image=m.profile_image,
            is_online=m.id in online_ids,
        )
        for m in members
    ]

    display_name = conversation.name or "Conversation"
    if not conversation.is_group:
        other = next((m for m in members if m.id != current_user.id), None)
        if other:
            display_name = other.name

    last_message = db.query(ChatMessage).filter(
        ChatMessage.conversation_id == conversation.id
    ).order_by(desc(ChatMessage.created_at)).first()

    unread_count = _conversation_unread_count(db, conversation.id, current_user.id)

    return ChatConversationOut(
        id=conversation.id,
        name=display_name,
        is_group=conversation.is_group,
        unread_count=int(unread_count),
        last_message=(last_message.message if last_message else ""),
        last_message_timestamp=(last_message.created_at if last_message else None),
        members=member_payload,
    )


@router.get("/users", response_model=list[ChatUserOut])
def list_chat_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    online_ids = _active_online_user_ids(db)
    users = db.query(User).filter(
        User.is_active == True,  # noqa: E712
        User.id != current_user.id,
    ).order_by(User.name.asc()).all()

    return [
        ChatUserOut(
            id=user.id,
            name=user.name,
            role=user.role,
            department=user.department,
            designation=user.designation,
            profile_image=user.profile_image,
            is_online=user.id in online_ids,
        )
        for user in users
    ]


@router.post("/conversations/private", response_model=ChatConversationOut)
def create_or_get_private_conversation(
    payload: ChatConversationCreatePrivate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if payload.user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot create self conversation")

    target = db.query(User).filter(
        User.id == payload.user_id,
        User.is_active == True,  # noqa: E712
    ).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    conversation = _upsert_private_conversation(db, current_user.id, target.id)
    online_ids = _active_online_user_ids(db)
    return _conversation_payload(db, conversation, current_user, online_ids)


@router.post("/conversations/group", response_model=ChatConversationOut)
def create_group_conversation(
    payload: ChatConversationCreateGroup,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
):
    requested_ids = sorted({user_id for user_id in payload.member_ids if user_id > 0})
    if current_admin.id not in requested_ids:
        requested_ids.append(current_admin.id)

    users = db.query(User).filter(
        User.id.in_(requested_ids),
        User.is_active == True,  # noqa: E712
    ).all()
    if len(users) != len(requested_ids):
        raise HTTPException(status_code=400, detail="One or more members are invalid or inactive")

    conversation = ChatConversation(
        name=payload.name.strip(),
        is_group=True,
        private_key=None,
        created_by=current_admin.id,
    )
    db.add(conversation)
    db.flush()

    for user in users:
        db.add(ChatConversationMember(conversation_id=conversation.id, user_id=user.id))

    db.commit()
    db.refresh(conversation)
    online_ids = _active_online_user_ids(db)
    return _conversation_payload(db, conversation, current_admin, online_ids)


@router.get("/conversations", response_model=list[ChatConversationOut])
def list_conversations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    memberships = db.query(ChatConversationMember.conversation_id).filter(
        ChatConversationMember.user_id == current_user.id
    ).all()
    conversation_ids = [row[0] for row in memberships]
    if not conversation_ids:
        return []

    conversations = db.query(ChatConversation).filter(
        ChatConversation.id.in_(conversation_ids)
    ).order_by(desc(ChatConversation.updated_at)).all()

    online_ids = _active_online_user_ids(db)
    return [_conversation_payload(db, conv, current_user, online_ids) for conv in conversations]


@router.get("/unread-count", response_model=ChatUnreadSummaryOut)
def get_unread_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conversation_ids = [
        row[0]
        for row in db.query(ChatConversationMember.conversation_id).filter(
            ChatConversationMember.user_id == current_user.id
        ).all()
    ]
    if not conversation_ids:
        return ChatUnreadSummaryOut(total_unread=0, conversations=[])

    per_conversation: list[ChatUnreadConversationCount] = []
    total = 0
    for conversation_id in conversation_ids:
        unread = _conversation_unread_count(db, conversation_id, current_user.id)
        total += unread
        per_conversation.append(
            ChatUnreadConversationCount(
                conversation_id=conversation_id,
                unread_count=unread,
            )
        )

    return ChatUnreadSummaryOut(total_unread=total, conversations=per_conversation)


@router.get("/conversations/{conversation_id}/messages", response_model=list[ChatMessageOut])
def get_messages(
    conversation_id: int,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_membership(db, conversation_id, current_user.id)

    messages = db.query(ChatMessage).filter(
        ChatMessage.conversation_id == conversation_id
    ).order_by(desc(ChatMessage.created_at)).limit(limit).all()
    messages = list(reversed(messages))

    member = db.query(ChatConversationMember).filter(
        ChatConversationMember.conversation_id == conversation_id,
        ChatConversationMember.user_id == current_user.id,
    ).first()
    if member:
        member.last_read_at = datetime.now(timezone.utc)
        db.commit()

    return [
        ChatMessageOut(
            id=m.id,
            conversation_id=m.conversation_id,
            sender_id=m.sender_id,
            message=m.message,
            timestamp=m.created_at,
        )
        for m in messages
    ]


@router.post("/messages", response_model=ChatMessageOut)
async def send_message(
    payload: ChatMessageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conversation = _ensure_membership(db, payload.conversation_id, current_user.id)
    text = payload.message.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    message = ChatMessage(
        conversation_id=payload.conversation_id,
        sender_id=current_user.id,
        message=text,
    )
    conversation.updated_at = datetime.now(timezone.utc)
    db.add(message)
    db.commit()
    db.refresh(message)

    member_ids = db.query(ChatConversationMember.user_id).filter(
        ChatConversationMember.conversation_id == payload.conversation_id
    ).all()
    broadcast_user_ids = [row[0] for row in member_ids]
    await manager.broadcast_to_users(broadcast_user_ids, _serialize_message(message))

    return ChatMessageOut(
        id=message.id,
        conversation_id=message.conversation_id,
        sender_id=message.sender_id,
        message=message.message,
        timestamp=message.created_at,
    )


@router.put("/conversations/{conversation_id}/read", status_code=status.HTTP_204_NO_CONTENT)
def mark_conversation_read(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_membership(db, conversation_id, current_user.id)
    member = db.query(ChatConversationMember).filter(
        ChatConversationMember.conversation_id == conversation_id,
        ChatConversationMember.user_id == current_user.id,
    ).first()
    if member:
        member.last_read_at = datetime.now(timezone.utc)
        db.commit()


@ws_router.websocket("/ws/chat/{user_id}")
async def chat_socket(
    websocket: WebSocket,
    user_id: int,
    token: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    if not token:
        await websocket.close(code=1008)
        return

    payload = decode_token(token)
    if payload is None or payload.get("token_type") != "access":
        await websocket.close(code=1008)
        return

    try:
        token_user_id = int(payload.get("sub"))
    except (TypeError, ValueError):
        await websocket.close(code=1008)
        return

    if token_user_id != user_id:
        await websocket.close(code=1008)
        return

    session_id = payload.get("sid")
    now = datetime.now(timezone.utc)
    session = db.query(UserSession).filter(
        UserSession.session_id == session_id,
        UserSession.user_id == user_id,
        UserSession.revoked_at == None,  # noqa: E711
    ).first()
    if not session or session.expires_at < now:
        await websocket.close(code=1008)
        return

    user = db.query(User).filter(
        User.id == user_id,
        User.is_active == True,  # noqa: E712
    ).first()
    if not user:
        await websocket.close(code=1008)
        return

    await manager.connect(user_id, websocket)

    try:
        while True:
            data = await websocket.receive_json()
            conversation_id = int(data.get("conversation_id", 0))
            text = str(data.get("message", "")).strip()
            if not conversation_id or not text:
                continue

            _ensure_membership(db, conversation_id, user_id)

            message = ChatMessage(
                conversation_id=conversation_id,
                sender_id=user_id,
                message=text[:2000],
            )
            conversation = db.query(ChatConversation).filter(ChatConversation.id == conversation_id).first()
            if conversation:
                conversation.updated_at = datetime.now(timezone.utc)

            db.add(message)
            db.commit()
            db.refresh(message)

            member_ids = db.query(ChatConversationMember.user_id).filter(
                ChatConversationMember.conversation_id == conversation_id
            ).all()
            await manager.broadcast_to_users([row[0] for row in member_ids], _serialize_message(message))
    except WebSocketDisconnect:
        manager.disconnect(user_id, websocket)
    except Exception:
        manager.disconnect(user_id, websocket)
        await websocket.close(code=1011)
