"""
The teacher's side of the parent-teacher Communication Centre.

A parent starts a conversation about their child and addresses it to one
teacher. This module lets that teacher read the thread and reply into it, using
the same two tables the parent module writes.

Scoping is on recipient_user_id, which is a users_masters.user_id. A teacher's
own id lives in teacher_master, and the two number different things, so every
request bridges through teacher_subjects.user_id_for() — the same email bridge
the chapters scoping already uses.

A teacher with no resolvable user id sees an empty inbox rather than everyone's
conversations. That is deliberate: these are messages about a named child, and
showing them to the wrong teacher is worse than showing them to nobody.
"""

from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.conversation import Conversation, ConversationMessage
from app.models.student import StudentMaster
from app.models.teacher import TeacherMaster
from app.schemas.conversation import (
    ConversationDetail,
    ConversationListResponse,
    ConversationMessageOut,
    ConversationSummary,
)
from app.services.teacher_class_service import class_display_name
from app.services.teacher_subjects import user_id_for

PARENT = "PARENT"
TEACHER = "TEACHER"


def _message_out(m: ConversationMessage) -> ConversationMessageOut:
    return ConversationMessageOut(
        message_id=m.message_id,
        conv_id=m.ticket_id,
        sender_type=m.sender_type or "",
        sender_name=m.sender_name,
        message=m.message,
        created_at=m.created_at,
        is_read=bool(m.is_read),
    )


def _student_labels(db: Session, student_ids) -> dict:
    """student_id -> (name, class label). One query, not one per conversation."""
    ids = {i for i in student_ids if i is not None}
    if not ids:
        return {}
    rows = db.query(StudentMaster).filter(StudentMaster.student_id.in_(ids)).all()
    out = {}
    for s in rows:
        label = class_display_name(s.class_id) if s.class_id is not None else None
        if label and s.section:
            label = f"{label} - {s.section}"
        out[s.student_id] = (s.full_name, label)
    return out


def _for_teacher(db: Session, teacher: TeacherMaster):
    """Base query: conversations addressed to this teacher. None if unresolvable."""
    user_id = user_id_for(db, teacher)
    if user_id is None:
        return None
    return db.query(Conversation).filter(Conversation.recipient_user_id == user_id)


def list_for_teacher(db: Session, teacher: TeacherMaster) -> ConversationListResponse:
    q = _for_teacher(db, teacher)
    if q is None:
        return ConversationListResponse(conversations=[], total=0, unread_total=0)

    rows = q.order_by(Conversation.updated_at.desc().nullslast(),
                      Conversation.ticket_id.desc()).all()
    if not rows:
        return ConversationListResponse(conversations=[], total=0, unread_total=0)

    ids = [r.ticket_id for r in rows]

    # Latest message per conversation, and unread counts, in two queries rather
    # than two per conversation.
    messages = (
        db.query(ConversationMessage)
        .filter(ConversationMessage.ticket_id.in_(ids))
        .order_by(ConversationMessage.ticket_id, ConversationMessage.created_at)
        .all()
    )
    latest: dict = {}
    unread: dict = {}
    for m in messages:
        latest[m.ticket_id] = m          # ordered ascending, so the last wins
        if m.sender_type == PARENT and not m.is_read:
            unread[m.ticket_id] = unread.get(m.ticket_id, 0) + 1

    labels = _student_labels(db, (r.student_id for r in rows))

    summaries: List[ConversationSummary] = []
    for r in rows:
        name, klass = labels.get(r.student_id, (None, None))
        last = latest.get(r.ticket_id)
        summaries.append(
            ConversationSummary(
                conv_id=r.ticket_id,
                subject=r.subject,
                category=r.category,
                status=r.status or "OPEN",
                student_id=r.student_id,
                student_name=name,
                student_class=klass,
                last_message=last.message if last else None,
                last_sender=last.sender_type if last else None,
                last_at=last.created_at if last else r.updated_at,
                unread=unread.get(r.ticket_id, 0),
            )
        )

    return ConversationListResponse(
        conversations=summaries,
        total=len(summaries),
        unread_total=sum(unread.values()),
    )


def get_for_teacher(db: Session, teacher: TeacherMaster, conv_id: int) -> Optional[Conversation]:
    """The conversation, only if it is addressed to this teacher."""
    q = _for_teacher(db, teacher)
    if q is None:
        return None
    return q.filter(Conversation.ticket_id == conv_id).first()


def thread(db: Session, teacher: TeacherMaster, conv: Conversation) -> ConversationDetail:
    """The full thread. Opening it marks the parent's messages as read."""
    rows = (
        db.query(ConversationMessage)
        .filter(ConversationMessage.ticket_id == conv.ticket_id)
        .order_by(ConversationMessage.created_at, ConversationMessage.message_id)
        .all()
    )

    # The parent side marks TEACHER messages read when a parent opens a thread;
    # this is the mirror of that. Done before serialising so the response does
    # not still show them unread.
    changed = False
    for m in rows:
        if m.sender_type == PARENT and not m.is_read:
            m.is_read = True
            changed = True
    if changed:
        db.commit()

    name, klass = _student_labels(db, [conv.student_id]).get(conv.student_id, (None, None))
    last = rows[-1] if rows else None

    return ConversationDetail(
        conv_id=conv.ticket_id,
        subject=conv.subject,
        category=conv.category,
        status=conv.status or "OPEN",
        student_id=conv.student_id,
        student_name=name,
        student_class=klass,
        last_message=last.message if last else None,
        last_sender=last.sender_type if last else None,
        last_at=last.created_at if last else conv.updated_at,
        unread=0,
        messages=[_message_out(m) for m in rows],
    )


def reply(db: Session, teacher: TeacherMaster, conv: Conversation, message: str) -> ConversationMessageOut:
    """Add a teacher message to the thread and reopen it."""
    now = datetime.utcnow()
    msg = ConversationMessage(
        ticket_id=conv.ticket_id,
        sender_type=TEACHER,
        sender_name=teacher.full_name or "Teacher",
        message=message,
        created_at=now,
        is_read=False,
    )
    db.add(msg)

    # Matches what the parent side does when it sends: a reply reopens a closed
    # conversation, and updated_at is what both inboxes sort on.
    conv.status = "OPEN"
    conv.updated_at = now

    db.commit()
    db.refresh(msg)
    return _message_out(msg)
