"""
TeacherNote — maps to teacher_notes table.
Rich note data (title, content, chapter, content_type, tags) is stored
as a JSON string in the `notes` column since the sgs table has no separate fields.
"""

import enum
from sqlalchemy import Column, BigInteger, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship

from app.db.session import Base


class ContentType(str, enum.Enum):
    typed       = "typed"
    voice       = "voice"
    handwritten = "handwritten"


class TeacherNote(Base):
    __tablename__ = "teacher_notes"

    notes_id   = Column(BigInteger, primary_key=True)
    teacher_id = Column(
        BigInteger,
        ForeignKey("teacher_master.teacher_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    class_id   = Column(BigInteger, nullable=True)
    section_1  = Column(String(50), nullable=True)
    notes      = Column(String, nullable=True)   # stores JSON: {title, content, chapter, ...}
    created_at = Column(DateTime, nullable=True)

    # Soft delete. Deleting sets this to "Deleted" instead of removing the row,
    # so a note can be restored until the year-end purge. NULL and "Active"
    # both mean live — rows created before the audit columns existed are NULL.
    record_status = Column(String, nullable=True)
    updated_at    = Column(DateTime, nullable=True)  # stamped by trg_audit_stamp (fn_stamp_updated_at)

    teacher = relationship("TeacherMaster", back_populates="notes")
