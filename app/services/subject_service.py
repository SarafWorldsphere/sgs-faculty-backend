"""Subject service — subjects scoped to a teacher's class."""

from typing import List
from sqlalchemy.orm import Session

from app.models.subject import SubjectMaster
from app.models.teacher import TeacherMaster
from app.schemas.subject import SubjectOut
from app.services.teacher_subjects import subject_ids_for


def get_subjects(db: Session, teacher: TeacherMaster, class_id=None) -> List[SubjectOut]:
    """
    The subjects this teacher teaches, optionally narrowed to one class.

    This used to return every subject in the school. On Chapters, Auto Test
    and the Lesson Planner that meant a maths teacher was offered Telugu and
    Biology as well, and could generate or upload against them.

    subject_ids_for is the same resolution the chapters endpoint already
    uses — the subject_master.teacher_id link, then the class/subject map,
    then the subject named on the teacher record. Narrowing is only applied
    when it resolves something: a teacher with no subject assignment keeps
    the previous wide list rather than being shown an empty screen, which
    would read as a broken page rather than a missing assignment.
    """
    query = db.query(SubjectMaster).filter(
        SubjectMaster.subject_name.isnot(None),
        SubjectMaster.subject_name != "",
    )
    if class_id is not None:
        query = query.filter(SubjectMaster.class_id == class_id)

    mine = subject_ids_for(db, teacher)
    if mine:
        narrowed = query.filter(SubjectMaster.subject_id.in_(mine))
        # Only keep the narrowed list if it leaves something. A teacher who
        # holds no subject in the class being viewed is better served the
        # class's subjects than a blank dropdown — the same compromise the
        # chapters endpoint makes.
        if narrowed.first() is not None:
            query = narrowed

    rows = query.order_by(SubjectMaster.subject_name).all()
    return [
        SubjectOut(
            subject_id=r.subject_id,
            subject_name=r.subject_name,
            subject_code=r.subject_code,
        )
        for r in rows
    ]
