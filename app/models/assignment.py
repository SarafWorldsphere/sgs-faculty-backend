"""
Assignment models — map to sgs_assignment_master and sgs_assignment_results.
Assignments are scoped to a class; submissions live in the results table.
"""

from sqlalchemy import Column, BigInteger, Integer, Numeric, String, Text, Date, DateTime

from app.db.session import Base


class AssignmentMaster(Base):
    __tablename__ = "sgs_assignment_master"

    assignment_id    = Column(BigInteger, primary_key=True)
    chapter_id       = Column(BigInteger, nullable=True)
    assignment_title = Column(String(200), nullable=True)
    assignment_text  = Column(Text, nullable=True)
    due_date         = Column(Date, nullable=True)
    assigned_by      = Column(BigInteger, nullable=True)
    class_id         = Column(BigInteger, nullable=True)
    subject_id       = Column(BigInteger, nullable=True)
    created_datetime = Column(DateTime, nullable=True)
    record_status    = Column(String(20), nullable=True)
    version_no       = Column(Integer, nullable=True)


class AssignmentResult(Base):
    """One row per (assignment, student): written at assignment time with
    status "assigned", updated when the student submits. The title/subject/
    due-date columns are copies of the master row so student-side apps can
    list without a join."""
    __tablename__ = "sgs_assignment_results"

    assignment_result_id = Column(BigInteger, primary_key=True)
    assignment_id        = Column(BigInteger, nullable=True)
    student_id           = Column(BigInteger, nullable=False)
    subject_id           = Column(BigInteger, nullable=True)
    assignment_title     = Column(String(200), nullable=True)
    due_date             = Column(Date, nullable=True)
    status               = Column(String(50), nullable=True)
    submitted_at         = Column(DateTime, nullable=True)
    # What the student actually turned in. file_content is a bytea blob and is
    # deliberately not mapped — listing submissions must never load it.
    submission_text      = Column(Text, nullable=True)
    submission_link      = Column(String, nullable=True)
    submitted_file_name  = Column(String, nullable=True)
    submitted_file_type  = Column(String, nullable=True)
    submitted_file_size  = Column(BigInteger, nullable=True)
    marks_obtained       = Column(Numeric, nullable=True)
    total_marks          = Column(Numeric, nullable=True)
    created_datetime     = Column(DateTime, nullable=True)
    record_status        = Column(String(20), nullable=True)
    version_no           = Column(Integer, nullable=True)
