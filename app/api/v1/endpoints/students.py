from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.api.deps import get_active_class_id
from app.models.student import StudentMaster
from app.schemas.student import StudentListResponse, StudentOut
from app.services import student_service

router = APIRouter(prefix="/students", tags=["students"])


@router.get("", response_model=StudentListResponse)
def list_students(
    class_id: Optional[int] = Depends(get_active_class_id),
    db: Session = Depends(get_db),
):
    # Students linked to a class via class_id (no direct teacher_id FK in sgs
    # schema). class_id comes from get_active_class_id, which defaults to the
    # teacher's primary class and refuses any class they are not assigned to.
    # Uses the same filter as the dashboard headcount — see student_service — so
    # the two numbers cannot disagree.
    students = (
        student_service.roll_query(db, class_id)
        .order_by(StudentMaster.roll_no)
        .all()
    )
    return StudentListResponse(
        students=[StudentOut.model_validate(s) for s in students],
        total=len(students),
    )
