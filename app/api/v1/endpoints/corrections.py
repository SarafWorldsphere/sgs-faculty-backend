from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_teacher, get_active_class_id
from app.db.session import get_db
from app.models.assessment import Assessment, AssessmentType
from app.models.teacher import TeacherMaster
from app.schemas.assessment import MarksEntryRequest, StudentMarkIn
from app.services import marks_service
from app.services.ai_service import correct_answer, scan_answer_sheets

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


# Guards the upload before it reaches the AI service: a scan is slow and
# billed, so a wrong file type should fail here rather than after the wait.
_SCAN_TYPES = {"application/pdf", "image/jpeg", "image/png", "image/webp", "image/heic"}
_SCAN_MAX_BYTES = 25 * 1024 * 1024
_SCAN_MAX_SHEETS = 40


@router.post("/scan")
async def scan(
    answer_sheets: list[UploadFile] = File(...),
    mode: str = Form("direct_grade"),
    question_paper_json: Optional[str] = Form(None),
    rubric_or_answer_key: Optional[str] = Form(None),
    subject: Optional[str] = Form(None),
    class_level: Optional[str] = Form(None),
    max_marks: Optional[int] = Form(None),
    student_name: Optional[str] = Form(None),
    roll_number: Optional[str] = Form(None),
    teacher: TeacherMaster = Depends(get_current_teacher),
):
    """
    Read scanned answer sheets and return the marks the scanner worked out.

    The browser never reaches the AI service directly — there is no route to
    it from outside — so the sheets come here and this forwards them.
    """
    if not answer_sheets:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No answer sheets were uploaded.")
    if len(answer_sheets) > _SCAN_MAX_SHEETS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Too many sheets in one scan — {len(answer_sheets)} sent, "
            f"{_SCAN_MAX_SHEETS} is the most per request.",
        )

    sheets: list[tuple[str, bytes, str]] = []
    for upload in answer_sheets:
        content_type = upload.content_type or "application/octet-stream"
        if content_type not in _SCAN_TYPES:
            raise HTTPException(
                status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                f"{upload.filename or 'A file'} is a {content_type}. "
                "Upload the answer sheets as PDF or as images.",
            )
        blob = await upload.read()
        if not blob:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"{upload.filename or 'A file'} is empty.",
            )
        if len(blob) > _SCAN_MAX_BYTES:
            raise HTTPException(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                f"{upload.filename or 'A file'} is larger than "
                f"{_SCAN_MAX_BYTES // (1024 * 1024)}MB.",
            )
        sheets.append((upload.filename or "answer-sheet", blob, content_type))

    return await scan_answer_sheets(
        answer_sheets=sheets,
        teacher=teacher,
        mode=mode,
        question_paper_json=question_paper_json,
        rubric_or_answer_key=rubric_or_answer_key,
        subject=subject,
        class_level=class_level,
        max_marks=max_marks,
        student_name=student_name,
        roll_number=roll_number,
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
