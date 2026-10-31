"""
Assignment service — list, create, and who each assignment went to.

An assignment row in sgs_assignment_master says which *class* it belongs to.
Which *students* actually received it lives in sgs_assignment_results: one row
per target, written at creation with status "assigned" and filled in as they
submit. Every assignment gets those rows — a class-wide one simply targets the
whole roll — so consumers (student and parent dashboards) can read a student's
assignments by joining results on student_id rather than guessing from class_id.
"""

from datetime import datetime
from typing import List
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.assignment import AssignmentMaster, AssignmentResult
from app.models.chapter_master import ChapterMaster
from app.models.subject import SubjectMaster
from app.models.student import StudentMaster
from app.models.teacher import TeacherMaster
from app.models.user import UserMaster
from app.schemas.assignment import (
    AssignmentOut, AssignmentCreate, AssignmentStudentRow, AssignmentStudentsResponse,
)
from app.services import student_service

STATUS_ASSIGNED = "assigned"


class TargetError(ValueError):
    """A requested student is not on the teacher's roll."""


def _subject_name(db: Session, subject_id) -> str | None:
    if not subject_id:
        return None
    s = db.query(SubjectMaster).filter(SubjectMaster.subject_id == subject_id).first()
    return s.subject_name if s else None


def _chapter_name(db: Session, chapter_id) -> str | None:
    if not chapter_id:
        return None
    c = db.query(ChapterMaster).filter(ChapterMaster.chapter_id == chapter_id).first()
    return c.chapter_name if c else None


def _target_count(db: Session, assignment_id) -> int:
    return (
        db.query(AssignmentResult)
        .filter(AssignmentResult.assignment_id == assignment_id)
        .count()
    )


def _to_out(db: Session, a: AssignmentMaster) -> AssignmentOut:
    submitted = (
        db.query(AssignmentResult)
        .filter(
            AssignmentResult.assignment_id == a.assignment_id,
            AssignmentResult.submitted_at.isnot(None),
        )
        .count()
    )
    return AssignmentOut(
        assignment_id=a.assignment_id,
        title=a.assignment_title,
        subject=_subject_name(db, a.subject_id),
        chapter_id=a.chapter_id,
        chapter_name=_chapter_name(db, a.chapter_id),
        due_date=a.due_date,
        submitted_count=submitted,
        total_students=_target_count(db, a.assignment_id),
    )


def get_assignments(db: Session, class_id) -> List[AssignmentOut]:
    """All assignments for one class, with per-assignment counts.

    The caller resolves class_id through get_active_class_id, so it is always a
    class the teacher is assigned to.
    """
    if not class_id:
        return []
    rows = (
        db.query(AssignmentMaster)
        .filter(AssignmentMaster.class_id == class_id)
        .order_by(AssignmentMaster.due_date.asc().nullslast())
        .all()
    )
    return [_to_out(db, a) for a in rows]


def _resolve_user_id(db: Session, teacher: TeacherMaster):
    """
    assigned_by has a FK to sgs_users_masters(user_id) — a different id space
    from teacher_id, so writing the teacher_id straight in violates the
    constraint. Match the teacher to their user row by email and fall back to
    NULL (the column is nullable) rather than failing the whole insert.
    """
    if not teacher.email_id:
        return None
    user = (
        db.query(UserMaster)
        .filter(func.lower(UserMaster.email_id) == teacher.email_id.lower())
        .first()
    )
    if not user:
        user = (
            db.query(UserMaster)
            .filter(func.lower(UserMaster.login_id) == teacher.email_id.lower())
            .first()
        )
    return user.user_id if user else None


def _resolve_targets(db: Session, class_id, requested: list[int] | None) -> list[int]:
    """
    The student ids this assignment goes to. Empty request = the whole roll of
    the class being assigned. Any requested id not on that roll is rejected
    outright — a teacher can only assign work to a class they are assigned to,
    and only to children in it.
    """
    roll = {sid for (sid,) in student_service.roll_query(db, class_id)
                                            .with_entities(StudentMaster.student_id).all()}
    if not requested:
        return sorted(roll)
    strangers = [sid for sid in requested if sid not in roll]
    if strangers:
        raise TargetError(f"Students not in your class: {strangers}")
    return list(requested)


def create_assignment(
    db: Session, teacher: TeacherMaster, class_id, payload: AssignmentCreate
) -> AssignmentOut:
    """Create an assignment and record who it went to (Assign-work modal)."""
    targets = _resolve_targets(db, class_id, payload.student_ids)
    assigned_by = _resolve_user_id(db, teacher)
    now = datetime.utcnow()

    a = AssignmentMaster(
        assignment_title=payload.title,
        assignment_text=payload.text,
        subject_id=payload.subject_id,
        chapter_id=payload.chapter_id,
        due_date=payload.due_date,
        class_id=class_id,
        assigned_by=assigned_by,
        created_datetime=now,
        record_status="Active",
        version_no=1,
    )
    db.add(a)
    db.flush()   # need assignment_id for the result rows, same transaction

    # The results table denormalises title/subject/due date so the student
    # apps can list without joining back; keep those in step with the master.
    db.add_all([
        AssignmentResult(
            assignment_id=a.assignment_id,
            student_id=sid,
            subject_id=payload.subject_id,
            assignment_title=payload.title,
            due_date=payload.due_date,
            status=STATUS_ASSIGNED,
            created_datetime=now,
            record_status="Active",
            version_no=1,
        )
        for sid in targets
    ])
    db.commit()
    db.refresh(a)
    return _to_out(db, a)


def get_assignment_students(db: Session, class_id, assignment_id: int) -> AssignmentStudentsResponse | None:
    """Who an assignment went to and where each of them stands.

    Scoped to the class being viewed, so an assignment belonging to another
    class is not found rather than exposed.
    """
    a = (
        db.query(AssignmentMaster)
        .filter(AssignmentMaster.assignment_id == assignment_id,
                AssignmentMaster.class_id == class_id)
        .first()
    )
    if not a:
        return None
    rows = (
        db.query(AssignmentResult, StudentMaster)
        .join(StudentMaster, StudentMaster.student_id == AssignmentResult.student_id)
        .filter(AssignmentResult.assignment_id == assignment_id)
        .order_by(StudentMaster.roll_no)
        .all()
    )
    students = [
        AssignmentStudentRow(
            student_id=s.student_id, full_name=s.full_name, roll_no=s.roll_no,
            status=r.status, submitted_at=r.submitted_at,
            submission_text=r.submission_text,
            submission_link=r.submission_link,
            submitted_file_name=r.submitted_file_name,
            submitted_file_size=r.submitted_file_size,
            marks_obtained=float(r.marks_obtained) if r.marks_obtained is not None else None,
            total_marks=float(r.total_marks) if r.total_marks is not None else None,
        )
        for r, s in rows
    ]
    return AssignmentStudentsResponse(
        assignment_id=assignment_id,
        title=a.assignment_title,
        students=students,
        total=len(students),
        submitted_count=sum(1 for x in students if x.submitted_at is not None),
    )
