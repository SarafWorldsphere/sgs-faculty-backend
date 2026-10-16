from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_teacher, get_active_class_id
from app.db.session import get_db
from app.models.assessment import Assessment, AssessmentType
from app.models.teacher import TeacherMaster
from app.schemas.assessment import MarksEntryRequest, StudentMarkIn
from app.services import marks_service
from app.services.ai_service import correct_answer

router = APIRouter(prefix="/corrections", tags=["corrections"])


class CorrectionRequest(BaseModel):
    question: str
    studentAnswer: str
    maxMarks: int = 5
    rubric: str = ""


@router.post("/check")
async def check(
    body: CorrectionRequest,
    teacher: TeacherMaster = Depends(get_current_teacher),
):
    return await correct_answer(
        question=body.question,
        student_answer=body.studentAnswer,
        max_marks=body.maxMarks,
        rubric=body.rubric,
        teacher=teacher,
    )


class CorrectedPaper(BaseModel):
    """One student's marked paper, as the auto-correct screen finished it."""

    title: str
    subject: Optional[str] = None
    assessment_date: Optional[date] = None
    student_id: int
    marks_obtained: float
    max_marks: float
    # Present from the second student onward: the first save creates the
    # assessment, the rest attach to it.
    assessment_id: Optional[int] = None


class CorrectedPaperSaved(BaseModel):
    assessment_id: int
    student_id: int
    marks_obtained: float
    max_marks: float
    created: bool


@router.post("/save", response_model=CorrectedPaperSaved, status_code=status.HTTP_201_CREATED)
def save_corrected_paper(
    body: CorrectedPaper,
    db: Session = Depends(get_db),
    teacher: TeacherMaster = Depends(get_current_teacher),
    class_id=Depends(get_active_class_id),
):
    """
    Keep what the marking screen worked out.

    Until now /check returned a mark and the screen displayed it, and that was
    the end of it — the paper was marked and the result thrown away, so none of
    the reports built on `sgs_assessments` ever saw it.

    A marked paper is the same thing as a mark entered by hand, so it is
    written through the same service rather than a second path of its own. That
    keeps one definition of what a valid mark is: the roll is checked, the
    averages are maintained, and the student's name and roll number are
    denormalised onto the result exactly as they are for marks entry.

    Marking is one student at a time, but a class sits on one assessment. The
    first paper creates it and returns its id; every paper after that sends the
    id back and is added to the same row.
    """
    if body.marks_obtained < 0 or body.marks_obtained > body.max_marks:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Marks must be between 0 and {body.max_marks}",
        )

    mark = StudentMarkIn(
        student_id=body.student_id,
        marks_obtained=body.marks_obtained,
        is_absent=False,
    )

    if body.assessment_id is None:
        payload = MarksEntryRequest(
            title=body.title,
            subject=body.subject,
            assessment_date=body.assessment_date or date.today(),
            max_marks=body.max_marks,
            assessment_type=AssessmentType.test,
            marks=[mark],
        )
        try:
            assessment = marks_service.create_assessment_with_marks(
                db, teacher, class_id, payload
            )
        except marks_service.RollError as err:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(err))

        return CorrectedPaperSaved(
            assessment_id=assessment.assessment_id,
            student_id=body.student_id,
            marks_obtained=body.marks_obtained,
            max_marks=body.max_marks,
            created=True,
        )

    assessment = (
        db.query(Assessment)
        .filter(Assessment.assessment_id == body.assessment_id)
        .first()
    )
    if not assessment:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Assessment not found")

    # A teacher may only add to an assessment on a class they are assigned to.
    # Without this check an id from elsewhere would let marks be written into
    # another teacher's class.
    if assessment.class_id != class_id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="That assessment belongs to a different class",
        )

    try:
        marks_service.add_marks(db, assessment, [mark])
    except marks_service.RollError as err:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(err))

    return CorrectedPaperSaved(
        assessment_id=assessment.assessment_id,
        student_id=body.student_id,
        marks_obtained=body.marks_obtained,
        max_marks=body.max_marks,
        created=False,
    )
