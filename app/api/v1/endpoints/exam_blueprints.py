"""
The exam types and competitive patterns the Auto Test screen offers.

One call returns everything the Configure step needs, because it needs all of
it before it can draw anything and three round trips would only show the
teacher a half-built form.

The response is deliberately shaped like the constants it replaces
(Swais-faculty/src/lib/testBlueprints.js), so the screen can read it with no
change to how it uses the data — `blueprint` is still a map of
questionType -> [count, marksEach].
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_teacher
from app.db.session import get_db
from app.models.exam_blueprint import ExamBlueprint, ExamBlueprintRow, ExamPattern
from app.models.teacher import TeacherMaster

router = APIRouter(prefix="/exam-blueprints", tags=["exam-blueprints"])

_LIVE_STATUS = ("Active", None)


def _num(value):
    """Numeric(6,2) comes back as Decimal; JSON wants a plain number.

    12.50 is returned as 12.5 and 10.00 as 10, because the screen prints
    these straight into labels and "10.00 marks" reads wrong.
    """
    if value is None:
        return None
    f = float(value)
    return int(f) if f.is_integer() else f


@router.get("")
def list_blueprints(
    teacher: TeacherMaster = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    """Every test type and competitive pattern configured for this school."""
    blueprints = (
        db.query(ExamBlueprint)
        .filter(
            ExamBlueprint.is_active.is_(True),
            ExamBlueprint.record_status.in_(_LIVE_STATUS),
        )
        .order_by(ExamBlueprint.display_seq, ExamBlueprint.code)
        .all()
    )

    # One query for every row rather than one per blueprint.
    rows_by_blueprint: dict[int, list[ExamBlueprintRow]] = {}
    if blueprints:
        ids = [b.blueprint_id for b in blueprints]
        for row in (
            db.query(ExamBlueprintRow)
            .filter(ExamBlueprintRow.blueprint_id.in_(ids))
            .order_by(ExamBlueprintRow.display_seq, ExamBlueprintRow.row_id)
            .all()
        ):
            rows_by_blueprint.setdefault(row.blueprint_id, []).append(row)

    test_types = [
        {
            "id":          b.code,
            "label":       b.label,
            "shortLabel":  b.short_label,
            "note":        b.note,
            "totalMarks":  _num(b.total_marks),
            "minutes":     b.minutes,
            "group":       b.group_name,
            "examType":    b.exam_type,
            "numbered":    b.numbered,
            # questionType -> [count, marksEach], the shape the screen reads.
            "blueprint": {
                r.question_type: [r.question_count, _num(r.marks_each)]
                for r in rows_by_blueprint.get(b.blueprint_id, [])
            },
        }
        for b in blueprints
    ]

    patterns = (
        db.query(ExamPattern)
        .filter(
            ExamPattern.is_active.is_(True),
            ExamPattern.record_status.in_(_LIVE_STATUS),
        )
        .order_by(ExamPattern.display_seq, ExamPattern.code)
        .all()
    )

    exam_patterns = [
        {
            "id":        p.code,
            "label":     p.label,
            "target":    p.target,
            "questions": p.question_count,
            "marks":     _num(p.marks_each),
            "minutes":   p.minutes,
        }
        for p in patterns
    ]

    return {
        "testTypes": test_types,
        "examPatterns": exam_patterns,
        # Says plainly that this school has nothing configured, so the screen
        # can fall back to its built-in defaults rather than drawing an empty
        # Configure step that a teacher cannot get past.
        "configured": bool(test_types),
    }
