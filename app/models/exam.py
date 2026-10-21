"""
ExamMaster — the school's scheduled examinations. Maps to exam_master.

PT-1 to PT-4 and the summative exams live here, each with its own window. An
assessment points at one of these through assessments.exam_id, which is
what lets the headmaster report "PT-2 for Class 9" rather than guessing from a
free-text title.

A weekly class test has no row here — it is not a scheduled school exam. Those
assessments carry exam_id = NULL and are grouped by month and subject instead.
"""

from sqlalchemy import BigInteger, Column, Date, DateTime, Integer, String

from app.db.session import Base


class ExamMaster(Base):
    __tablename__ = "exam_master"

    exam_id          = Column(BigInteger, primary_key=True)
    exam_name        = Column(String(150), nullable=True)
    academic_year    = Column(String(20),  nullable=True)
    exam_type        = Column(String(50),  nullable=True)
    start_date       = Column(Date,        nullable=True)
    end_date         = Column(Date,        nullable=True)
    created_datetime = Column(DateTime,    nullable=True)
    record_status    = Column(String(50),  nullable=True)
    version_no       = Column(Integer,     nullable=True)
