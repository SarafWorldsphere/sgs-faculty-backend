"""
Which subjects a teacher is allowed to see.

Chapters, notes and study material are scoped through this, so a teacher sees
their own subject rather than every subject in the school.

The awkward part is that the same person has two identities:

    sgs_users_masters.user_id      3       (bigint)
    sgs_teacher_master.teacher_id  'T02'   (varchar)

and sgs_subject_master.teacher_id is a foreign key to *user_id*, not to the
teacher table. Email is the only thing linking the two rows, so that is what
we bridge on.

Resolution order:
  1. sgs_subject_master.teacher_id == the teacher's user_id  (the real
     assignment; requires a matching row in sgs_users_masters)
  2. the subjects named on the teacher's sgs_teacher_class_map rows — unioned
     with 1, not a fallback to it
  3. sgs_subject_master.subject_name matched against the teacher's
     subject_name — a fallback for schools that never fill in either

Sources 1 and 2 are unioned because a teacher's *other* subjects exist only in
the class map. Treating 1 as sufficient meant a teacher with one
sgs_subject_master row and three mapped subjects resolved to one subject, and
chapters, notes and study material for the other two came back empty — "only
the primary subject works".
"""

from typing import List, Optional

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models.subject import SubjectMaster
from app.models.teacher import TeacherMaster
from app.models.teacher_class_map import DELETED, TeacherClassMap
from app.models.user import UserMaster

# Same definition of a live row as teacher_class_service uses: record_status is
# nullable and defaults to 'Active', so a row is live unless it says 'Deleted'.
_LIVE = or_(TeacherClassMap.record_status.is_(None),
            TeacherClassMap.record_status != DELETED)


def user_id_for(db: Session, teacher: TeacherMaster) -> Optional[int]:
    """The teacher's id in sgs_users_masters, matched on email."""
    email = (teacher.email_id or "").strip()
    if not email:
        return None
    row = (
        db.query(UserMaster.user_id)
        .filter(UserMaster.email_id.ilike(email))
        .first()
    )
    return row[0] if row else None


def mapped_subject_ids(db: Session, teacher: TeacherMaster) -> List[int]:
    """
    Subject ids named on this teacher's live sgs_teacher_class_map rows.

    The map records a subject by *name* against a class, so each row is matched
    back to sgs_subject_master on that name within that class. A subject row
    with no class_id is matched on name alone — some schools leave it blank,
    and excluding those rows would reintroduce the missing-subject bug for them.
    """
    rows = (
        db.query(TeacherClassMap.class_id, TeacherClassMap.subject_name)
        .filter(TeacherClassMap.teacher_id == teacher.teacher_id, _LIVE)
        .all()
    )

    clauses = [
        and_(
            SubjectMaster.subject_name.ilike(name.strip()),
            or_(SubjectMaster.class_id == class_id, SubjectMaster.class_id.is_(None)),
        )
        for class_id, name in rows
        if name and name.strip()
    ]
    if not clauses:
        return []

    found = db.query(SubjectMaster.subject_id).filter(or_(*clauses)).all()
    return [row[0] for row in found]


def subject_ids_for(db: Session, teacher: TeacherMaster) -> List[int]:
    """Subject ids this teacher teaches. Empty means nothing is assigned."""
    ids: set[int] = set()

    user_id = user_id_for(db, teacher)
    if user_id is not None:
        assigned = (
            db.query(SubjectMaster.subject_id)
            .filter(SubjectMaster.teacher_id == user_id)
            .all()
        )
        ids.update(row[0] for row in assigned)

    ids.update(mapped_subject_ids(db, teacher))

    if ids:
        return sorted(ids)

    # Neither source resolved anything. Fall back to the subject named on the
    # teacher record.
    name = (teacher.subject_name or "").strip()
    if not name:
        return []

    by_name = (
        db.query(SubjectMaster.subject_id)
        .filter(SubjectMaster.subject_name.ilike(name))
        .all()
    )
    return [row[0] for row in by_name]
