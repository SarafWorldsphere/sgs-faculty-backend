"""
TeacherQuestionPaper — a generated test the teacher chose to keep.

The AI service returns papers in two shapes depending on its version: a plain
text paper (what it does today) or a structured list of questions. Both are
stored — `paper_text` for printing and assigning as-is, `questions` for the
structured UI once the AI returns it. Either may be NULL, never both.
"""

from sqlalchemy import Column, BigInteger, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.db.session import Base


class TeacherQuestionPaper(Base):
    __tablename__ = "question_papers"

    paper_id      = Column(BigInteger, primary_key=True, autoincrement=True)
    # String, not BigInteger: teacher_master.teacher_id is varchar in the
    # database. The older models declare BigInteger and get away with it because
    # the values are numeric strings; this one says what the column is.
    teacher_id    = Column(
        String,
        ForeignKey("teacher_master.teacher_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chapter_id    = Column(BigInteger, nullable=True)
    title         = Column(String(255), nullable=False)
    subject       = Column(String(150), nullable=True)
    difficulty    = Column(String(20), nullable=True)
    total_marks   = Column(Integer, nullable=True)
    question_type = Column(String(30), nullable=True)   # MCQ / True/False / Short Answer / NULL = mixed
    paper_text    = Column(Text, nullable=True)
    questions     = Column(JSONB, nullable=True)
    created_at    = Column(DateTime, nullable=True)

    # Audit columns, same set as every other sgs_ table. record_status drives
    # soft delete; updated_at is stamped by the audit trigger on every UPDATE.
    record_status = Column(String(20), nullable=True)
    updated_at    = Column(DateTime, nullable=True)   # stamped by trg_audit_stamp (fn_stamp_updated_at)

    teacher = relationship("TeacherMaster")
