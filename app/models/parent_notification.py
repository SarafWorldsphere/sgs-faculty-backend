"""
ParentNotification — maps to the kit's `parent_notifications`.

The record of a message a teacher sent to a student's parents.

In the old SGS database `notification_type` and `sent_via` were Postgres
enums; in the kit they are plain text, so the "operator does not exist" trap
on LIKE/ILIKE no longer applies. ALLOWED_TYPES below is now the only thing
constraining the value, which means it is enforced in the application rather
than the database — worth a CHECK constraint in the kit if that matters.

The SGS migration has to cast the existing enum columns to text.

`sent_via` is 'manual' until a real delivery channel (sms / whatsapp /
email) is wired up; the row is the record, not proof of delivery.

tenant_id is deliberately not declared — the kit's stamp trigger fills it on
insert and the row-level security policy filters it on read.
"""

from sqlalchemy import Column, BigInteger, Integer, String, Text, DateTime

from app.db.session import Base

# notification_type enum, after migration 0006 adds the three the UI offers.
TYPE_PERFORMANCE = "performance"
TYPE_HOMEWORK    = "homework"
TYPE_ATTENDANCE  = "attendance"
TYPE_GENERAL     = "general"
ALLOWED_TYPES = {
    TYPE_PERFORMANCE, TYPE_HOMEWORK, TYPE_ATTENDANCE, TYPE_GENERAL,
    # pre-existing values, kept so older rows still validate
    "let_drop", "peer_help", "good_manners", "table_manners",
}

# notification_channel enum
CHANNEL_MANUAL = "manual"


class ParentNotification(Base):
    __tablename__ = "parent_notifications"

    notification_id   = Column(BigInteger, primary_key=True, autoincrement=True)
    # bigint, matching teacher_master.teacher_id. The visible staff code
    # ('T02') lives in teacher_master.teacher_code, not here.
    teacher_id        = Column(BigInteger, nullable=False, index=True)
    student_id        = Column(BigInteger, nullable=False, index=True)
    notification_type = Column(String, nullable=False)   # enum notification_type
    message_text      = Column(Text, nullable=False)
    sent_via          = Column(String, nullable=False)   # enum notification_channel
    sent_at           = Column(DateTime, nullable=True)  # defaults to now() in the DB
    created_at        = Column(DateTime, nullable=True)

    record_status     = Column(String, nullable=True)
    version_no        = Column(Integer, nullable=True)
    updated_at        = Column(DateTime, nullable=True)  # stamped by trg_audit_stamp
