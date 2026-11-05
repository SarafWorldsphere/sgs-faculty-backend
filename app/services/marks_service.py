"""
Entering and correcting marks.

Until now the platform could display assessment results but had no way to
create them — the two tables were read-only from the application's point of
view and every mark on them was loaded by hand. This is the write path.

Two rules shape everything here:

  A mark only exists for a student on the teacher's own roll. The student ids
  in the request are checked against the class roll before anything is written,
  so a teacher cannot record a mark against a child in another class.

  A test and its marks are saved together. A test row with no results is
  useless to every screen that reads it, so both tables are written in one
  transaction or neither is.
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.assessment import Assessment, AssessmentResult
from app.models.class_master import ClassMaster
from app.models.exam import ExamMaster
from app.models.student import StudentMaster
from app.models.teacher import TeacherMaster
from app.services import student_service

ACTIVE = "Active"


class RollError(ValueError):
    """A mark was submitted for a student who is not on this class's roll."""


def _roll(db: Session, class_id) -> dict[int, StudentMaster]:
    """The students a mark may be recorded against, keyed by id."""
    return {s.student_id: s for s in student_service.roll_query(db, class_id).all()}


def _percentage(marks, max_marks: float):
    if marks is None or not max_marks:
        return None
    return round(float(marks) / float(max_marks) * 100, 2)


def _class_label(db: Session, class_id) -> str | None:
    """The human-readable class name, kept in the legacy class_name column.

    Still filled because reports and the headmaster dashboard read it; class_id
    beside it is what anything new should filter on.
    """
    if not class_id:
        return None
    cls = db.query(ClassMaster).filter(ClassMaster.class_id == class_id).first()
    return (cls.class_name if cls and cls.class_name else str(class_id))[:50]


def create_assessment_with_marks(
    db: Session, teacher: TeacherMaster, class_id, payload
) -> Assessment:
    """Record a test and every student's mark on it, in one transaction."""
    roll = _roll(db, class_id)

    strangers = [m.student_id for m in payload.marks if m.student_id not in roll]
    if strangers:
        raise RollError(f"Students not on this class's roll: {strangers}")

    now = datetime.utcnow()
    scored = [m for m in payload.marks if not m.is_absent and m.marks_obtained is not None]
    average = (
        round(sum(float(m.marks_obtained) for m in scored) / len(scored), 2)
        if scored else None
    )

    assessment = Assessment(
        teacher_id=teacher.teacher_id,
        title=payload.title,
        assessment_type=payload.assessment_type.value,
        subject=payload.subject,
        assessment_date=payload.assessment_date,
        max_marks=Decimal(str(payload.max_marks)),
        class_id=class_id,
        class_name=_class_label(db, class_id),
        section=teacher.section_1,
        exam_id=payload.exam_id,
        total_students=len(payload.marks),
        submitted=len(scored),
        class_average=Decimal(str(average)) if average is not None else None,
        created_at=now,
        updated_at=now,
        record_status=ACTIVE,
        version_no=1,
    )
    db.add(assessment)
    db.flush()  # need assessment_id for the result rows, same transaction

    # roll_number and student_name are denormalised onto the result so a report
    # reads without joining, and so a later name change does not silently
    # rewrite what was recorded on the day.
    db.add_all([
        AssessmentResult(
            assessment_id=assessment.assessment_id,
            student_id=m.student_id,
            roll_number=roll[m.student_id].roll_no or "",
            student_name=roll[m.student_id].full_name or "",
            marks_obtained=Decimal(str(m.marks_obtained)) if m.marks_obtained is not None else None,
            percentage=(
                Decimal(str(_percentage(m.marks_obtained, payload.max_marks)))
                if not m.is_absent and m.marks_obtained is not None else None
            ),
            is_absent=m.is_absent,
            created_at=now,
            updated_at=now,
            record_status=ACTIVE,
            version_no=1,
        )
        for m in payload.marks
    ])

    db.commit()
    db.refresh(assessment)
    return assessment


def update_marks(db: Session, assessment: Assessment, payload) -> Assessment:
    """Correct the marks on a test that is already saved.

    Only the students named in the request are touched — a teacher fixing one
    child's mark should not have to resend the whole class.
    """
    existing = {r.student_id: r for r in assessment.results}

    strangers = [m.student_id for m in payload.marks if m.student_id not in existing]
    if strangers:
        raise RollError(f"These students have no result on this test: {strangers}")

    now = datetime.utcnow()
    max_marks = float(assessment.max_marks)

    for m in payload.marks:
        if m.marks_obtained is not None and (m.marks_obtained < 0 or m.marks_obtained > max_marks):
            raise ValueError(
                f"Marks for student {m.student_id} must be between 0 and {max_marks}"
            )
        row = existing[m.student_id]
        row.marks_obtained = Decimal(str(m.marks_obtained)) if m.marks_obtained is not None else None
        row.percentage = (
            Decimal(str(_percentage(m.marks_obtained, max_marks)))
            if not m.is_absent and m.marks_obtained is not None else None
        )
        row.is_absent = m.is_absent
        row.updated_at = now

    scored = [r for r in existing.values() if not r.is_absent and r.marks_obtained is not None]
    assessment.submitted = len(scored)
    assessment.class_average = (
        Decimal(str(round(sum(float(r.marks_obtained) for r in scored) / len(scored), 2)))
        if scored else None
    )
    assessment.updated_at = now

    db.commit()
    db.refresh(assessment)
    return assessment


def add_marks(db: Session, assessment: Assessment, marks: list) -> Assessment:
    """Add students to a test that already exists.

    Marks entry writes a whole class at once, but auto-correct marks one paper
    at a time — the teacher scans one student, then the next. Each of those
    belongs on the same assessment rather than creating a row per child, so
    this appends to one.

    A student already on the test is updated rather than duplicated. Marking a
    paper twice is a correction, not a second result, and two rows for one
    child would break every report that counts them.
    """
    roll = _roll(db, assessment.class_id)

    strangers = [m.student_id for m in marks if m.student_id not in roll]
    if strangers:
        raise RollError(f"Students not on this class's roll: {strangers}")

    now = datetime.utcnow()
    max_marks = float(assessment.max_marks)
    existing = {r.student_id: r for r in assessment.results}

    for m in marks:
        if m.marks_obtained is not None and (m.marks_obtained < 0 or m.marks_obtained > max_marks):
            raise ValueError(
                f"Marks for student {m.student_id} must be between 0 and {max_marks}"
            )

        value = Decimal(str(m.marks_obtained)) if m.marks_obtained is not None else None
        pct = (
            Decimal(str(_percentage(m.marks_obtained, max_marks)))
            if not m.is_absent and m.marks_obtained is not None else None
        )

        row = existing.get(m.student_id)
        if row:
            row.marks_obtained = value
            row.percentage = pct
            row.is_absent = m.is_absent
            row.updated_at = now
        else:
            db.add(AssessmentResult(
                assessment_id=assessment.assessment_id,
                student_id=m.student_id,
                roll_number=roll[m.student_id].roll_no or "",
                student_name=roll[m.student_id].full_name or "",
                marks_obtained=value,
                percentage=pct,
                is_absent=m.is_absent,
                created_at=now,
                updated_at=now,
                record_status=ACTIVE,
                version_no=1,
            ))

    db.flush()
    db.refresh(assessment)

    scored = [r for r in assessment.results if not r.is_absent and r.marks_obtained is not None]
    assessment.total_students = len(assessment.results)
    assessment.submitted = len(scored)
    assessment.class_average = (
        Decimal(str(round(sum(float(r.marks_obtained) for r in scored) / len(scored), 2)))
        if scored else None
    )
    assessment.updated_at = now

    db.commit()
    db.refresh(assessment)
    return assessment


def exams_for_year(db: Session, academic_year: str | None = None) -> list[ExamMaster]:
    """The scheduled exams a teacher can record marks against."""
    q = db.query(ExamMaster).filter(
        (ExamMaster.record_status.is_(None)) | (ExamMaster.record_status == ACTIVE)
    )
    if academic_year:
        q = q.filter(ExamMaster.academic_year == academic_year)
    return q.order_by(ExamMaster.start_date.asc().nullslast(), ExamMaster.exam_id).all()


# ── Monthly view ─────────────────────────────────────────────────────────────
# "All the tests conducted for a subject during the month, with student-wise
# marks." The per-test drawer already answers "how did the class do on Friday's
# test"; this answers "how is this child doing in Maths this month", which is
# the question a parent meeting or a report card starts from.

def _month_bounds(month: str) -> tuple[date, date]:
    """'2026-11' -> the first of that month and the first of the next."""
    try:
        year, mon = (int(part) for part in month.split("-", 1))
        start = date(year, mon, 1)
    except (ValueError, TypeError) as exc:
        raise ValueError("month must be YYYY-MM") from exc
    end = date(year + 1, 1, 1) if mon == 12 else date(year, mon + 1, 1)
    return start, end


def monthly_marks(
    db: Session,
    teacher: TeacherMaster,
    month: str,
    subject: str | None = None,
    class_id=None,
) -> tuple[list[Assessment], list[dict]]:
    """
    Every test this teacher ran in `month` (optionally for one subject), and
    each student's marks across them.

    Returns the assessments and a per-student list; the endpoint shapes them.
    """
    start, end = _month_bounds(month)

    q = db.query(Assessment).filter(
        Assessment.teacher_id == teacher.teacher_id,
        Assessment.assessment_date >= start,
        Assessment.assessment_date < end,
    )
    if subject:
        q = q.filter(Assessment.subject.ilike(subject))
    if class_id is not None:
        # Same rule as the list endpoint: rows predating class_id have none and
        # would otherwise vanish from every class.
        q = q.filter((Assessment.class_id == class_id) | (Assessment.class_id.is_(None)))

    assessments = q.order_by(Assessment.assessment_date, Assessment.assessment_id).all()
    if not assessments:
        return [], []

    by_id = {a.assessment_id: a for a in assessments}

    results = (
        db.query(AssessmentResult)
        .filter(AssessmentResult.assessment_id.in_(list(by_id)))
        .all()
    )

    # roll_number and student_name are denormalised onto the result row, so the
    # student list comes from the results themselves — no extra query, and a
    # student who has since left still appears against the marks they earned.
    students: dict[int, dict] = {}
    for r in results:
        s = students.setdefault(
            r.student_id,
            {
                "student_id":  r.student_id,
                "name":        r.student_name,
                "roll_number": r.roll_number,
                "marks":       [],
                "attempted":   0,
                "scored":      0.0,
                "max_total":   0.0,
            },
        )
        assessment = by_id[r.assessment_id]
        marks = float(r.marks_obtained) if r.marks_obtained is not None else None
        s["marks"].append(
            {
                "assessment_id":  r.assessment_id,
                "marks_obtained": marks,
                "percentage":     float(r.percentage) if r.percentage is not None else None,
                "is_absent":      bool(r.is_absent),
            }
        )
        # Absences and unentered marks are excluded from the total rather than
        # counted as zero — see the schema note on why.
        if not r.is_absent and marks is not None:
            s["attempted"] += 1
            s["scored"] += marks
            s["max_total"] += float(assessment.max_marks)

    rows = []
    for s in sorted(students.values(), key=lambda x: (x["roll_number"] or "", x["name"] or "")):
        total = s["scored"] if s["attempted"] else None
        pct = round(s["scored"] / s["max_total"] * 100, 2) if s["max_total"] else None
        rows.append(
            {
                "student_id":  s["student_id"],
                "name":        s["name"],
                "roll_number": s["roll_number"],
                "marks":       s["marks"],
                "attempted":   s["attempted"],
                "total":       total,
                "max_total":   s["max_total"],
                "percentage":  pct,
            }
        )

    return assessments, rows
