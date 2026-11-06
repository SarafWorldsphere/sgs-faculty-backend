"""
StudentMaster — maps to student_master table.
Students are linked to a teacher via class_id (teacher.class_id == student.class_id).
"""

from sqlalchemy import Column, BigInteger, Integer, String, Boolean, DateTime
from sqlalchemy.orm import relationship

from app.db.session import Base


class StudentMaster(Base):
    __tablename__ = "student_master"

    student_id      = Column(BigInteger, primary_key=True)
    admission_no    = Column(String(50),  nullable=True)
    full_name       = Column(String(255), nullable=True)
    class_id        = Column(BigInteger,  nullable=True)
    section         = Column(String(50),  nullable=True)
    roll_no         = Column(String(50),  nullable=True)
    student_phone   = Column(String(50),  nullable=True)
    student_email   = Column(String(255), nullable=True)
    guardian_name   = Column(String(255), nullable=True)
    guardian_phone  = Column(String(50),  nullable=True)
    guardian_email  = Column(String(255), nullable=True)
    is_active       = Column(Boolean,     nullable=True)
    created_datetime  = Column(DateTime,  nullable=True)
    modified_datetime = Column(DateTime,  nullable=True)
    record_status   = Column(String(50),  nullable=True)
    version_no      = Column(Integer,     nullable=True)

    results = relationship("AssessmentResult", back_populates="student", cascade="all, delete-orphan")
