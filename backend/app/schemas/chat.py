from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ChatUserOut(BaseModel):
    id: int
    name: str
    role: str
    department: Optional[str] = None
    designation: Optional[str] = None
    profile_image: Optional[str] = None
    is_online: bool = False

    model_config = {"from_attributes": True}


class ChatMessageCreate(BaseModel):
    conversation_id: int
    message: str = Field(min_length=1, max_length=2000)


class ChatMessageOut(BaseModel):
    id: int
    conversation_id: int
    sender_id: int
    message: str
    timestamp: datetime


class ChatConversationCreatePrivate(BaseModel):
    user_id: int


class ChatConversationCreateGroup(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    member_ids: list[int] = Field(default_factory=list)


class ChatConversationOut(BaseModel):
    id: int
    name: str
    is_group: bool
    unread_count: int = 0
    last_message: str = ""
    last_message_timestamp: Optional[datetime] = None
    members: list[ChatUserOut] = Field(default_factory=list)


class ChatUnreadConversationCount(BaseModel):
    conversation_id: int
    unread_count: int = 0


class ChatUnreadSummaryOut(BaseModel):
    total_unread: int = 0
    conversations: list[ChatUnreadConversationCount] = Field(default_factory=list)

