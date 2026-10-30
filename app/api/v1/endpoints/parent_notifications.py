"""
Teacher → parent notifications.

  POST /parent-notifications        send (and record) a message to a student's parents
  GET  /parent-notifications        what this teacher has sent, newest first

The Faculty UI previously showed "Notification Sent!" without calling
anything — nothing was stored and no parent was told. These endpoints make
the record real.

Delivery is a separate question: `sent_via` is 'manual', meaning the row
exists but nothing leaves the building yet. The Parent dashboard builds its
notification list from the Communication Center (ticket messages), so it
will not surface these until it also reads sgs_parent_notifications.
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.deps import get_active_class_id, get_current_teacher
from app.db.session import get_db
from app.models.parent_notification import (
    ParentNotification, ALLOWED_TYPES, CHANNEL_MANUAL, TYPE_GENERAL,
)
from app.models.student import StudentMaster
from app.models.teacher import TeacherMaster
from app.services import student_service

router = APIRouter(prefix="/parent-notifications", tags=["parent-notifications"])

DELETED = "Deleted"
_LIVE = or_(ParentNotification.record_status.is_(None),
            ParentNotification.record_status != DELETED)


class NotificationCreate(BaseModel):
    student_id: int
    notification_type: str = TYPE_GENERAL
    message: str

    @field_validator("message")
    @classmethod
    def _message(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("Message cannot be empty")
        return v

    @field_validator("notification_type")
    @classmethod
    def _type(cls, v: str) -> str:
        v = (v or TYPE_GENERAL).strip().lower()
        if v not in ALLOWED_TYPES:
            # The column is an enum — an unknown value fails at insert with a
            # database error, so reject it here with something readable.
            raise ValueError(f"Unknown notification type: {v}")
        return v


class NotificationOut(BaseModel):
    notification_id: int
    student_id: int
    student_name: Optional[str] = None
    notification_type: str
    message_text: str
    sent_via: str
    sent_at: Optional[datetime] = None


class NotificationListResponse(BaseModel):
    notifications: list[NotificationOut]
    total: int


def _out(n: ParentNotification, student_name: Optional[str] = None) -> NotificationOut:
    return NotificationOut(
        notification_id=n.notification_id, student_id=n.student_id,
        student_name=student_name, notification_type=n.notification_type,
        message_text=n.message_text, sent_via=n.sent_via, sent_at=n.sent_at,
    )


@router.post("", response_model=NotificationOut, status_code=status.HTTP_201_CREATED)
def send_notification(
    body: NotificationCreate,
    teacher: TeacherMaster = Depends(get_current_teacher),
    class_id: Optional[int] = Depends(get_active_class_id),
    db: Session = Depends(get_db),
):
    """Record a message to a student's parents. The student must be on this
    teacher's roll — otherwise a teacher could message any child in the school.

    `class_id` picks which of the teacher's classes the child is in; it is
    checked against their assignments before we get here."""
    student = (
        student_service.roll_query(db, class_id)
        .filter(StudentMaster.student_id == body.student_id)
        .first()
    )
    if not student:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Student not in your class")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    row = ParentNotification(
        teacher_id=teacher.teacher_id,
        student_id=body.student_id,
        notification_type=body.notification_type,
        message_text=body.message,
        sent_via=CHANNEL_MANUAL,
        sent_at=now,
        created_at=now,
        record_status="Active",
        version_no=1,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _out(row, student.full_name)


@router.get("", response_model=NotificationListResponse)
def list_notifications(
    student_id: Optional[int] = None,
    teacher: TeacherMaster = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    """What this teacher has sent, newest first. `student_id` filters to one child."""
    q = (
        db.query(ParentNotification, StudentMaster.full_name)
        .outerjoin(StudentMaster, StudentMaster.student_id == ParentNotification.student_id)
        .filter(ParentNotification.teacher_id == teacher.teacher_id, _LIVE)
    )
    if student_id is not None:
        q = q.filter(ParentNotification.student_id == student_id)
    rows = q.order_by(ParentNotification.sent_at.desc().nullslast()).all()
    return NotificationListResponse(
        notifications=[_out(n, name) for n, name in rows],
        total=len(rows),
    )
