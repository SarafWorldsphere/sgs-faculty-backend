"""
ParentNotification — maps to sgs_parent_notifications.

The record of a message a teacher sent to a student's parents.

Two columns are Postgres enums, not free text: `notification_type`
(notification_type) and `sent_via` (notification_channel). Writing a value
outside the enum fails at insert, and comparing them with LIKE/ILIKE raises
"operator does not exist" — the same trap that broke the AI analytics
queries. Always compare with ::text if you need a pattern match.

`sent_via` is 'manual' until a real delivery channel (sms / whatsapp /
email) is wired up; the row is the record, not proof of delivery.
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
    __tablename__ = "sgs_parent_notifications"

    notification_id   = Column(BigInteger, primary_key=True, autoincrement=True)
    # varchar, matching sgs_teacher_master.teacher_id and every sibling table
    teacher_id        = Column(String, nullable=False, index=True)
    student_id        = Column(BigInteger, nullable=False, index=True)
    notification_type = Column(String, nullable=False)   # enum notification_type
    message_text      = Column(Text, nullable=False)
    sent_via          = Column(String, nullable=False)   # enum notification_channel
    sent_at           = Column(DateTime, nullable=True)  # defaults to now() in the DB
    created_at        = Column(DateTime, nullable=True)

    record_status     = Column(String, nullable=True)
    version_no        = Column(Integer, nullable=True)
    updated_at        = Column(DateTime, nullable=True)  # stamped by trg_audit_stamp
