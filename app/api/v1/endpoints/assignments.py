from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.api.deps import get_active_class_id, get_current_teacher
from app.models.teacher import TeacherMaster
from app.schemas.assignment import (
    AssignmentListResponse, AssignmentCreate, AssignmentOut, AssignmentStudentsResponse,
)
from app.services import assignment_service

router = APIRouter(prefix="/assignments", tags=["assignments"])


@router.get("", response_model=AssignmentListResponse)
def list_assignments(
    class_id: Optional[int] = Depends(get_active_class_id),
    db: Session = Depends(get_db),
):
    """Assignments for the selected class, with target and submission counts.

    `class_id` defaults to the teacher's primary class and is refused if they
    are not assigned to it.
    """
    items = assignment_service.get_assignments(db, class_id)
    return AssignmentListResponse(assignments=items, total=len(items))


@router.post("", response_model=AssignmentOut, status_code=status.HTTP_201_CREATED)
def create_assignment(
    payload: AssignmentCreate,
    teacher: TeacherMaster = Depends(get_current_teacher),
    class_id: Optional[int] = Depends(get_active_class_id),
    db: Session = Depends(get_db),
):
    """
    Create an assignment (Assign-work modal). `student_ids` picks the
    recipients; leave it out to assign to the whole class. The work is created
    against the selected class.
    """
    try:
        return assignment_service.create_assignment(db, teacher, class_id, payload)
    except assignment_service.TargetError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.get("/{assignment_id}/students", response_model=AssignmentStudentsResponse)
def assignment_students(
    assignment_id: int,
    class_id: Optional[int] = Depends(get_active_class_id),
    db: Session = Depends(get_db),
):
    """Who the assignment went to, with each student's status."""
    result = assignment_service.get_assignment_students(db, class_id, assignment_id)
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Assignment not found")
    return result
