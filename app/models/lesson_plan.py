from sqlalchemy import Column, BigInteger, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from app.db.session import Base


class TeacherLessonPlan(Base):
    __tablename__ = "teacher_lesson_plans"

    lesson_plan_id = Column(BigInteger, primary_key=True, autoincrement=True)
    teacher_id     = Column(
        BigInteger,
        ForeignKey("teacher_master.teacher_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title          = Column(Text, nullable=False)
    chapter_text   = Column(Text, nullable=True)
    duration_minutes = Column(BigInteger, nullable=True)
    plan_data      = Column(Text, nullable=False)   # full plan JSON stored as string
    created_at     = Column(DateTime, nullable=True)

    teacher = relationship("TeacherMaster")
