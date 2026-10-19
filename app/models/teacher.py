"""
TeacherMaster — teacher profile data.
Maps to teacher_master table.
Linked to users_masters via email_id (no FK constraint).
"""

from sqlalchemy import Column, BigInteger, String, Boolean, DateTime
from sqlalchemy.orm import relationship

from app.db.session import Base


class TeacherMaster(Base):
    __tablename__ = "teacher_master"

    teacher_id   = Column(BigInteger, primary_key=True)
    full_name    = Column(String(255), nullable=False)
    subject_name = Column(String(255), nullable=True)
    class_id     = Column(BigInteger, nullable=True)
    section_1    = Column(String(50), nullable=True)
    role         = Column(String(50), nullable=True)
    email_id     = Column(String(255), nullable=False, unique=True, index=True)
    section_2    = Column(String(50), nullable=True)
    phone        = Column(BigInteger, nullable=True)
    is_active    = Column(Boolean, nullable=True)
    created_at   = Column(DateTime, nullable=True)

    notes       = relationship("TeacherNote",  back_populates="teacher", cascade="all, delete-orphan")
    assessments = relationship("Assessment",   back_populates="teacher", cascade="all, delete-orphan")
