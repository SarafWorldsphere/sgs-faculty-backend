"""
Marks, shaped for the AI service's /api/faculty/assess endpoint.

Why this exists
---------------
The old /api/v1/ai/teacher/student-analytics and /class-analytics endpoints
were handed a student name and a subject and nothing else. Whatever analysis
came back was therefore written from the name alone — the AI service has no
access to this database and never did.

The replacement, /api/faculty/assess, is honest about that: it asks for
`performance_data` outright. So the marks have to be gathered here and sent.
That is the whole of the work — it is not a repoint.

Relationship to reports.py
--------------------------
endpoints/reports.py computes very similar per-student aggregates for the
Reports table. It is deliberately left alone: it is a working screen, and
folding both onto one helper mid-release risks changing numbers teachers are
already reading. Both read the same roll through student_service.roll_query,
so the two agree on who is in the class. If they are ever unified, this is the
one to keep — it filters by subject, which reports does not.
"""

from __future__ import annotations

from app.models.student import StudentMaster
from app.services import student_service


def _pct(obtained, maximum) -> float | None:
    try:
        maximum = float(maximum)
        if maximum <= 0:
            return None
        return round(float(obtained) / maximum * 100, 1)
    except (TypeError, ValueError):
        return None


def _marks_for(student, teacher_id: int, subject: str | None) -> list[dict]:
    """One row per assessment this student actually sat."""
    out: list[dict] = []
    for r in student.results:
        assessment = r.assessment
        if assessment is None or assessment.teacher_id != teacher_id:
            continue
        # Absent is not zero. Averaging a blank as 0 drags a child's mean down
        # for a day they were ill, which is how "weak student" conclusions get
        # manufactured out of attendance.
        if r.is_absent or r.marks_obtained is None:
            continue
        if subject and (assessment.subject or "").strip().lower() != subject.strip().lower():
            continue
        out.append({
            "assessment": assessment.title,
            "type": assessment.assessment_type,
            "date": assessment.assessment_date.isoformat() if assessment.assessment_date else None,
            "marks_obtained": float(r.marks_obtained),
            "max_marks": float(assessment.max_marks),
            "percent": _pct(r.marks_obtained, assessment.max_marks),
        })
    out.sort(key=lambda m: (m["date"] or ""))
    return out


def _summarise(marks: list[dict]) -> dict:
    pcts = [m["percent"] for m in marks if m["percent"] is not None]
    if not pcts:
        return {"assessments_taken": 0, "average_percent": None,
                "highest_percent": None, "lowest_percent": None}
    return {
        "assessments_taken": len(pcts),
        "average_percent": round(sum(pcts) / len(pcts), 1),
        "highest_percent": max(pcts),
        "lowest_percent": min(pcts),
    }


def student_performance(db, teacher, class_id, student_name: str,
                        subject: str | None) -> tuple[str, dict]:
    """
    (scope_description, performance_data) for one child.

    The child is found by name because that is all the Reports screen sends.
    Name is not unique, so the roll is searched case-insensitively and the
    first match on this teacher's roll is used — which is at least always a
    child the teacher actually teaches, rather than anyone in the school.
    """
    wanted = (student_name or "").strip().lower()
    student = next(
        (s for s in student_service.roll_query(db, class_id)
            .order_by(StudentMaster.roll_no).all()
         if (s.full_name or "").strip().lower() == wanted),
        None,
    )

    if student is None:
        scope = f"{student_name or 'A student'}"
        if subject:
            scope += f", {subject}"
        return scope, {"error": "That student is not on this class roll.",
                       "student_name": student_name}

    marks = _marks_for(student, teacher.teacher_id, subject)
    scope = f"{student.full_name}"
    if subject:
        scope += f", {subject}"
    scope += ". Their marks across the assessments this teacher has set."

    return scope, {
        "student_name": student.full_name,
        "roll_number": student.roll_no,
        "subject": subject,
        "summary": _summarise(marks),
        "assessments": marks,
    }


def class_performance(db, teacher, class_id, subject: str | None) -> tuple[str, dict]:
    """(scope_description, performance_data) for a whole class."""
    students = (
        student_service.roll_query(db, class_id)
        .order_by(StudentMaster.roll_no)
        .all()
    )

    rows: list[dict] = []
    for s in students:
        marks = _marks_for(s, teacher.teacher_id, subject)
        summary = _summarise(marks)
        rows.append({
            "student_name": s.full_name,
            "roll_number": s.roll_no,
            **summary,
        })

    averaged = [r["average_percent"] for r in rows if r["average_percent"] is not None]
    scope = f"A class of {len(students)} students"
    if subject:
        scope += f", {subject}"
    scope += ". Each student's average across the assessments this teacher has set."

    return scope, {
        "subject": subject,
        "student_count": len(students),
        "students_with_marks": len(averaged),
        "class_average_percent": round(sum(averaged) / len(averaged), 1) if averaged else None,
        "students": rows,
    }
