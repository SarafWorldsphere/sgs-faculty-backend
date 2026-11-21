from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.api.deps import get_active_class_id, get_current_teacher
from app.models.teacher import TeacherMaster
from app.models.assessment import Assessment, AssessmentResult
from app.models.exam import ExamMaster
from app.schemas.assessment import (
    AssessmentListResponse, AssessmentOut, AssessmentDetailOut, ResultOut,
    ExamListResponse, ExamOut, MarksEntryRequest, MarksUpdateRequest,
    MonthlyMarksResponse, StudentMarksRow,
)
from app.services import marks_service

router = APIRouter(prefix="/assessments", tags=["assessments"])


def _build_out(a: Assessment, exam_name: Optional[str] = None) -> AssessmentOut:
    results_with_marks = [r for r in a.results if not r.is_absent and r.marks_obtained is not None]
    avg = (
        round(sum(float(r.marks_obtained) for r in results_with_marks) / len(results_with_marks), 1)
        if results_with_marks else None
    )
    return AssessmentOut(
        assessment_id=a.assessment_id,
        title=a.title,
        subject=a.subject,
        chapter=a.chapter,
        assessment_type=a.assessment_type,
        max_marks=float(a.max_marks),
        assessment_date=a.assessment_date,
        total_students=len(a.results),
        submitted=len(results_with_marks),
        class_average=avg,
        class_id=a.class_id,
        exam_id=a.exam_id,
        exam_name=exam_name,
        absent_count=sum(1 for r in a.results if r.is_absent),
    )


def _build_result(r: AssessmentResult, max_marks: float) -> ResultOut:
    pct = (
        round(float(r.marks_obtained) / max_marks * 100, 1)
        if r.marks_obtained is not None and not r.is_absent else None
    )
    return ResultOut(
        result_id=r.result_id,
        student_id=r.student_id,
        student_name=r.student_name,
        roll_number=r.roll_number,
        marks_obtained=float(r.marks_obtained) if r.marks_obtained is not None else None,
        max_marks=max_marks,
        percentage=pct,
        is_absent=bool(r.is_absent),
    )


@router.get("", response_model=AssessmentListResponse)
def list_assessments(
    teacher: TeacherMaster = Depends(get_current_teacher),
    class_id: Optional[int] = Depends(get_active_class_id),
    db: Session = Depends(get_db),
):
    """This teacher's tests, newest first.

    Scoped to the selected class where the assessment records one. Rows created
    before class_id existed have none, so they are still returned — otherwise
    every assessment loaded by hand would disappear from the list.
    """
    q = db.query(Assessment).filter(Assessment.teacher_id == teacher.teacher_id)
    if class_id is not None:
        q = q.filter(
            (Assessment.class_id == class_id) | (Assessment.class_id.is_(None))
        )
    assessments = q.order_by(Assessment.assessment_date.desc()).all()

    names = _exam_names(db, assessments)
    return AssessmentListResponse(
        assessments=[_build_out(a, names.get(a.exam_id)) for a in assessments],
        total=len(assessments),
    )


def _exam_names(db: Session, assessments: list[Assessment]) -> dict:
    ids = {a.exam_id for a in assessments if a.exam_id}
    if not ids:
        return {}
    return {
        e.exam_id: e.exam_name
        for e in db.query(ExamMaster).filter(ExamMaster.exam_id.in_(ids)).all()
    }


@router.get("/exams", response_model=ExamListResponse)
def list_exams(
    academic_year: Optional[str] = None,
    teacher: TeacherMaster = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    """The scheduled exams marks can be recorded against — PT-1..PT-4 and the
    summatives. A weekly class test is not here; it is saved without an exam."""
    return ExamListResponse(
        exams=[ExamOut.model_validate(e) for e in marks_service.exams_for_year(db, academic_year)]
    )


@router.get("/monthly", response_model=MonthlyMarksResponse)
def monthly_marks(
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$", description="YYYY-MM"),
    subject: Optional[str] = Query(None, description="Omit for every subject"),
    teacher: TeacherMaster = Depends(get_current_teacher),
    class_id: Optional[int] = Depends(get_active_class_id),
    db: Session = Depends(get_db),
):
    """
    Every test this teacher ran in a month, with each student's marks across
    them.

    Declared before /{assessment_id} on purpose: FastAPI matches in order, and
    a path parameter would otherwise swallow "monthly" and try to read it as an
    id.
    """
    try:
        assessments, students = marks_service.monthly_marks(
            db, teacher, month=month, subject=subject, class_id=class_id
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

    names = _exam_names(db, assessments)
    return MonthlyMarksResponse(
        subject=subject,
        month=month,
        assessments=[_build_out(a, names.get(a.exam_id)) for a in assessments],
        students=[StudentMarksRow(**row) for row in students],
    )


@router.post("", response_model=AssessmentDetailOut, status_code=status.HTTP_201_CREATED)
def enter_marks(
    payload: MarksEntryRequest,
    teacher: TeacherMaster = Depends(get_current_teacher),
    class_id: Optional[int] = Depends(get_active_class_id),
    db: Session = Depends(get_db),
):
    """Record a test and every student's mark on it.

    The test and its results are written together — a test row with no results
    is useless to every screen that reads it.
    """
    if class_id is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "No class selected, and this teacher has no class assigned",
        )
    try:
        assessment = marks_service.create_assessment_with_marks(db, teacher, class_id, payload)
    except marks_service.RollError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

    return _detail(db, assessment)


@router.put("/{assessment_id}/marks", response_model=AssessmentDetailOut)
def correct_marks(
    assessment_id: int,
    payload: MarksUpdateRequest,
    teacher: TeacherMaster = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    """Correct marks on a saved test. Only the students sent are changed."""
    assessment = db.query(Assessment).filter(
        Assessment.assessment_id == assessment_id,
        Assessment.teacher_id == teacher.teacher_id,
    ).first()
    if not assessment:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Assessment not found")

    try:
        assessment = marks_service.update_marks(db, assessment, payload)
    except marks_service.RollError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

    return _detail(db, assessment)


def _detail(db: Session, a: Assessment) -> AssessmentDetailOut:
    """
    The whole class, not only the students already marked.

    This used to return a.results, which is one row per mark entered. A
    teacher who saved five of forty saw five students and no way to tell
    whether the other thirty-five were absent, pending, or simply lost. The
    roll is the list; the marks are what is filled in against it.

    Students with no row come back with result_id and marks_obtained null, so
    the screen can show them as pending and the teacher can finish later
    without the saved marks being disturbed.
    """
    exam_name = _exam_names(db, [a]).get(a.exam_id)
    max_marks = float(a.max_marks)
    out = _build_out(a, exam_name)

    results = [_build_result(r, max_marks) for r in a.results]
    marked = {r.student_id for r in results}

    # Only when the assessment knows its class. An older row without class_id
    # has no roll to show, and listing the wrong class would be worse than
    # listing none.
    if a.class_id:
        for student_id, s in marks_service.roll_for(db, a.class_id).items():
            if student_id in marked:
                continue
            results.append(
                ResultOut(
                    result_id=None,
                    student_id=student_id,
                    student_name=s.full_name or "",
                    roll_number=str(s.roll_no or ""),
                    marks_obtained=None,
                    max_marks=max_marks,
                    percentage=None,
                    is_absent=False,
                )
            )

    results.sort(key=lambda x: (x.roll_number or "", x.student_name or ""))
    return AssessmentDetailOut(**out.model_dump(), results=results)


@router.get("/{assessment_id}", response_model=AssessmentDetailOut)
def get_assessment(
    assessment_id: int,
    teacher: TeacherMaster = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    a = db.query(Assessment).filter(
        Assessment.assessment_id == assessment_id,
        Assessment.teacher_id == teacher.teacher_id,
    ).first()
    if not a:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")

    return _detail(db, a)
