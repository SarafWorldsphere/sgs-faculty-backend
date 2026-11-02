from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_teacher
from app.db.session import get_db
from app.models.teacher import TeacherMaster
from app.schemas.conversation import (
    ConversationDetail,
    ConversationListResponse,
    ConversationMessageOut,
    ReplyRequest,
)
from app.services import conversation_service

router = APIRouter(prefix="/conversations", tags=["conversations"])

NOT_YOURS = "Conversation not found"


@router.get("", response_model=ConversationListResponse)
def list_conversations(
    teacher: TeacherMaster = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    """
    Conversations parents have addressed to this teacher, newest activity first.

    Not scoped by class on purpose: a parent writes to a teacher, and that
    teacher should see the thread whichever class the child is in.
    """
    return conversation_service.list_for_teacher(db, teacher)


@router.get("/{conv_id}", response_model=ConversationDetail)
def get_conversation(
    conv_id: int,
    teacher: TeacherMaster = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    """The full thread. Opening it marks the parent's messages as read."""
    conv = conversation_service.get_for_teacher(db, teacher, conv_id)
    if not conv:
        # 404 rather than 403: a teacher should not be able to learn that a
        # conversation exists by asking for one that is not theirs.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NOT_YOURS)
    return conversation_service.thread(db, teacher, conv)


@router.post("/{conv_id}/messages", response_model=ConversationMessageOut,
             status_code=status.HTTP_201_CREATED)
def reply_to_conversation(
    conv_id: int,
    body: ReplyRequest,
    teacher: TeacherMaster = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    """
    Reply as the teacher.

    sender_type is set here rather than taken from the request: it identifies
    who is speaking, and a client should not be able to post a message as the
    parent.
    """
    conv = conversation_service.get_for_teacher(db, teacher, conv_id)
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NOT_YOURS)
    return conversation_service.reply(db, teacher, conv, body.message)
