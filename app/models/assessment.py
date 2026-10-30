"""
Assessment + AssessmentResult — map to assessments and assessment_results.
assessment_type is stored as String (maps to PostgreSQL USER-DEFINED enum).
AssessmentResult has denormalized roll_number and student_name columns.
"""

import enum
from sqlalchemy import Column, BigInteger, Integer, String, Numeric, ForeignKey, DateTime, Date, Boolean
from sqlalchemy.orm import relationship

from app.db.session import Base


class AssessmentType(str, enum.Enum):
    quiz       = "quiz"
    test       = "test"
    exam       = "exam"
    assignment = "assignment"


class Assessment(Base):
    __tablename__ = "assessments"

    assessment_id   = Column(BigInteger, primary_key=True)
    teacher_id      = Column(BigInteger, ForeignKey("teacher_master.teacher_id", ondelete="CASCADE"), nullable=False, index=True)
    title           = Column(String(300), nullable=False)
    assessment_type = Column(String(50),  nullable=False, default="test")
    subject         = Column(String(150), nullable=True)
    chapter_id      = Column(BigInteger,  nullable=True)
    chapter         = Column(String(255), nullable=True)
    assessment_date = Column(Date,        nullable=True)
    max_marks       = Column(Numeric,     nullable=False, default=100.0)
    # class_name is the original free-text column and is kept filled for the
    # rows and readers that predate class_id. class_id is the one to filter on.
    class_name      = Column(String(50),  nullable=True)
    class_id        = Column(BigInteger,  nullable=True, index=True)
    # Points at exam_master for a scheduled exam (PT-1..PT-4). NULL for a
    # weekly class test, which is not a school-scheduled exam.
    exam_id         = Column(BigInteger,  nullable=True, index=True)
    section         = Column(String(50),  nullable=True)
    total_students  = Column(Integer,     nullable=False, default=0)
    submitted       = Column(Integer,     nullable=False, default=0)
    class_average   = Column(Numeric,     nullable=True)
    created_at      = Column(DateTime,    nullable=True)
    updated_at      = Column(DateTime,    nullable=True)
    record_status   = Column(String(50),  nullable=True)
    version_no      = Column(Integer,     nullable=True)

    teacher = relationship("TeacherMaster", back_populates="assessments")
    results = relationship("AssessmentResult", back_populates="assessment", cascade="all, delete-orphan")


class AssessmentResult(Base):
    __tablename__ = "assessment_results"

    result_id      = Column(BigInteger, primary_key=True)
    assessment_id  = Column(BigInteger, ForeignKey("assessments.assessment_id", ondelete="CASCADE"), nullable=False, index=True)
    student_id     = Column(BigInteger, ForeignKey("student_master.student_id", ondelete="CASCADE"), nullable=False, index=True)
    roll_number    = Column(String(50),  nullable=False)
    student_name   = Column(String(255), nullable=False)
    marks_obtained = Column(Numeric,     nullable=True)
    percentage     = Column(Numeric,     nullable=True)
    is_absent      = Column(Boolean,     nullable=False, default=False)
    created_at     = Column(DateTime,    nullable=True)
    updated_at     = Column(DateTime,    nullable=True)
    record_status  = Column(String(50),  nullable=True)
    version_no     = Column(Integer,     nullable=True)

    assessment = relationship("Assessment",    back_populates="results")
    student    = relationship("StudentMaster", back_populates="results")
