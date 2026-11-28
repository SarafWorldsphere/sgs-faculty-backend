from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_active_class_id, get_current_teacher
from app.db.session import get_db
from app.models.teacher import TeacherMaster
from app.services import assignment_service
from app.services.ai_service import get_assignment_reminders, get_completion_alerts

router = APIRouter(prefix="/alerts", tags=["alerts"])


def _assignment_facts(db: Session, class_id) -> dict:
    """
    What the AI service needs to write an alert that is actually true.

    Until now both of these endpoints forwarded nothing but the teacher's
    name, so the "alert" was composed with no idea which work had been set or
    who had handed it in. These are the same figures the Assignments screen
    shows, so the alert and the screen cannot disagree.
    """
    items = assignment_service.get_assignments(db, class_id)
    today = date.today()

    rows = []
    for a in items:
        outstanding = max((a.total_students or 0) - (a.submitted_count or 0), 0)
        rows.append({
            "title": a.title,
            "subject": a.subject,
            "chapter": a.chapter_name,
            "due_date": a.due_date.isoformat() if a.due_date else None,
            "overdue": bool(a.due_date and a.due_date < today),
            "assigned_to": a.total_students or 0,
            "submitted": a.submitted_count or 0,
            "not_submitted": outstanding,
        })

    return {
        "assignment_count": len(rows),
        "overdue_count": sum(1 for r in rows if r["overdue"]),
        "total_not_submitted": sum(r["not_submitted"] for r in rows),
        "assignments": rows,
    }


@router.post("/due-date")
async def due_date_alerts(
    teacher: TeacherMaster = Depends(get_current_teacher),
    class_id: Optional[int] = Depends(get_active_class_id),
    db: Session = Depends(get_db),
):
    """A reminder about work that is due."""
    return await get_assignment_reminders(teacher, _assignment_facts(db, class_id))


@router.post("/completion")
async def completion_alerts(
    teacher: TeacherMaster = Depends(get_current_teacher),
    class_id: Optional[int] = Depends(get_active_class_id),
    db: Session = Depends(get_db),
):
    """A note about work that was set but not handed in."""
    return await get_completion_alerts(teacher, _assignment_facts(db, class_id))
