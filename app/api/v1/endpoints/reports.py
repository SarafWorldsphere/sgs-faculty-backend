from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.api.deps import get_active_class_id, get_current_teacher
from app.models.teacher    import TeacherMaster
from app.models.student    import StudentMaster
from app.models.assessment import Assessment, AssessmentResult
from app.schemas.report    import ReportResponse, StudentReportRow
from app.services import student_service, teacher_class_service

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("", response_model=ReportResponse)
def get_report(
    teacher: TeacherMaster = Depends(get_current_teacher),
    class_id: Optional[int] = Depends(get_active_class_id),
    db: Session = Depends(get_db),
):
    tid = teacher.teacher_id
    # Same roll as the Dashboard headcount and the Students tab — see
    # student_service. This used to filter on class_id alone, so inactive and
    # deleted students were counted here but nowhere else.
    students = (
        student_service.roll_query(db, class_id)
        .order_by(StudentMaster.roll_no)
        .all()
    )
    # Teacher-wide, not per class: sgs_assessments has no class_id, only a free
    # text class_name, so there is nothing reliable to scope on. For a teacher
    # with several classes this count therefore covers all of them. The per
    # student rows below are correct — they come from the selected class's roll.
    assessments = db.query(Assessment).filter(Assessment.teacher_id == tid).all()
    total_assessments = len(assessments)

    rows: list[StudentReportRow] = []
    for student in students:
        marks_list = [
            float(r.marks_obtained)
            for r in student.results
            if not r.is_absent and r.marks_obtained is not None
            and r.assessment.teacher_id == tid
        ]
        pct_list = [
            float(r.marks_obtained) / float(r.assessment.max_marks) * 100
            for r in student.results
            if not r.is_absent and r.marks_obtained is not None
            and r.assessment.teacher_id == tid
        ]

        avg_pct = round(sum(pct_list) / len(pct_list), 1) if pct_list else None
        avg_raw = round(sum(marks_list) / len(marks_list), 1) if marks_list else None

        rows.append(StudentReportRow(
            student_id=student.student_id,
            name=student.full_name or "",
            roll_number=student.roll_no or "",
            total_assessed=len(marks_list),
            average_marks=avg_raw,
            average_percent=avg_pct,
            highest_marks=max(marks_list) if marks_list else None,
            lowest_marks=min(marks_list) if marks_list else None,
            rank=0,
        ))

    rows.sort(key=lambda r: (-(r.average_percent or 0), r.roll_number))
    for i, row in enumerate(rows, start=1):
        row.rank = i

    # The header follows the class being reported on, not the teacher's primary
    # one. class_name stays the raw id, as it always was — the frontend renders
    # it as "Class {class_name}".
    option = next(
        (o for o in teacher_class_service.class_options(db, teacher) if o.class_id == class_id),
        None,
    )
    sections = ", ".join(option.sections) if option and option.sections else None

    return ReportResponse(
        teacher_id=tid,
        class_name=str(class_id) if class_id else "8",
        section=sections or teacher.section_1 or "A",
        total_students=len(students),
        total_assessments=total_assessments,
        students=rows,
    )
