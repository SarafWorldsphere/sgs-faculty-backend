from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_teacher
from app.db.session import get_db
from app.models.teacher import TeacherMaster
from app.schemas.timetable import TimetableResponse
from app.services import timetable_service

router = APIRouter(prefix="/timetable", tags=["timetable"])


@router.get("/me", response_model=TimetableResponse)
def my_timetable(
    academic_year: Optional[str] = Query(
        None, description="Defaults to the latest year this teacher has a timetable in"
    ),
    schedule_type: str = Query(
        "full",
        pattern="^(full|half)$",
        description="Which period structure to lay the week on",
    ),
    teacher: TeacherMaster = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    """
    The signed-in teacher's own timetable.

    Scoped to the teacher from the token, with no teacher_id parameter — a
    teacher viewing another teacher's week is the Admin module's job
    (Admin: Teacher-wise Timetable View), not this endpoint's.
    """
    return timetable_service.teacher_week(
        db, teacher, academic_year=academic_year, schedule_type=schedule_type
    )
