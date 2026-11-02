from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, field_validator


class ConversationSummary(BaseModel):
    """One thread in the teacher's inbox."""

    conv_id:       int
    subject:       Optional[str] = None
    category:      Optional[str] = None
    status:        str = "OPEN"
    student_id:    Optional[int] = None
    student_name:  Optional[str] = None
    student_class: Optional[str] = None
    parent_name:   Optional[str] = None
    last_message:  Optional[str] = None
    last_sender:   Optional[str] = None
    last_at:       Optional[datetime] = None
    unread:        int = 0


class ConversationMessageOut(BaseModel):
    message_id:  int
    conv_id:     int
    sender_type: str
    sender_name: Optional[str] = None
    message:     Optional[str] = None
    created_at:  Optional[datetime] = None
    is_read:     bool = False


class ConversationListResponse(BaseModel):
    conversations: List[ConversationSummary]
    total:         int
    unread_total:  int = 0


class ConversationDetail(ConversationSummary):
    messages: List[ConversationMessageOut] = []


class ReplyRequest(BaseModel):
    message: str

    @field_validator("message")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        text = (v or "").strip()
        if not text:
            raise ValueError("A reply cannot be empty")
        return text
