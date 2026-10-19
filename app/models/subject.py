"""
SubjectMaster — maps to subject_master table.
Subjects are scoped to a class via class_id (and optionally a teacher).
"""

from sqlalchemy import Column, BigInteger, String

from app.db.session import Base


class SubjectMaster(Base):
    __tablename__ = "subject_master"

    subject_id    = Column(BigInteger, primary_key=True)
    class_id      = Column(BigInteger, nullable=True)
    subject_name  = Column(String(100), nullable=True)
    subject_code  = Column(String(50),  nullable=True)
    teacher_id    = Column(BigInteger, nullable=True)
    record_status = Column(String(20),  nullable=True)
