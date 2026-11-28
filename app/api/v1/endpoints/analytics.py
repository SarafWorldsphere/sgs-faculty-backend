from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_active_class_id, get_current_teacher
from app.db.session import get_db
from app.models.teacher import TeacherMaster
from app.services import performance_service
from app.services.ai_service import assess_performance

router = APIRouter(prefix="/analytics", tags=["analytics"])


class StudentAnalyticsRequest(BaseModel):
    studentName: str
    subject: str


class ClassAnalyticsRequest(BaseModel):
    subject: str


@router.post("/student")
async def student(
    body: StudentAnalyticsRequest,
    teacher: TeacherMaster = Depends(get_current_teacher),
    class_id: Optional[int] = Depends(get_active_class_id),
    db: Session = Depends(get_db),
):
    """
    Read one child's marks and ask the AI service what they say.

    The marks are gathered here and sent. Until now this forwarded only the
    child's name to an endpoint that has no access to this database, so
    whatever came back was written from the name alone.
    """
    scope, data = performance_service.student_performance(
        db, teacher, class_id, body.studentName, body.subject
    )
    return await assess_performance(scope, data, teacher)


@router.post("/class")
async def class_report(
    body: ClassAnalyticsRequest,
    teacher: TeacherMaster = Depends(get_current_teacher),
    class_id: Optional[int] = Depends(get_active_class_id),
    db: Session = Depends(get_db),
):
    """The same for a whole class: every student's average, then the reading."""
    scope, data = performance_service.class_performance(
        db, teacher, class_id, body.subject
    )
    return await assess_performance(scope, data, teacher)
