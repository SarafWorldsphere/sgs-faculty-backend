from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_teacher
from app.db.session import get_db
from app.models.class_master import ClassMaster
from app.models.subject import SubjectMaster
from app.models.teacher import TeacherMaster
from app.services import teacher_class_service

router = APIRouter(prefix="/classes", tags=["classes"])


@router.get("")
def list_classes(
    teacher: TeacherMaster = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    """
    The classes this teacher is assigned to.

    This used to return every class in the school. A teacher picking a class
    from Chapters, Auto Test or the Lesson Planner was therefore offered all
    of them, including years and subjects they do not teach — they could
    upload material against another teacher's class, and the dropdown was long
    enough to make finding their own tedious.

    The allowed set is teacher_class_service.allowed_class_ids, the same
    boundary the class-scoped endpoints already authorise against, so the
    selector now offers exactly what the rest of the API would accept. A
    teacher's primary assignment counts whether or not it is mapped, so
    nobody loses access they had before.

    Only classes that actually have a subject are returned: a class with no
    subjects is a dead end (you could pick it but never reach a chapter), so
    listing it just produces empty dropdowns. As soon as a subject is added to
    a class it appears here automatically.
    """
    subject_classes = db.query(SubjectMaster.class_id).filter(SubjectMaster.class_id.isnot(None))

    query = db.query(ClassMaster).filter(
        ClassMaster.class_name.isnot(None),
        ClassMaster.class_name != "",
        ClassMaster.class_id.in_(subject_classes),
    )

    # Narrow to the teacher's own classes — but only when that leaves them
    # something to pick.
    #
    # Half the teachers on one of the two schools have neither a class_id on
    # their record nor a row in teacher_class_subject_map. Returning nothing
    # for them would make Chapters, Auto Test and the Lesson Planner unusable
    # where today they work, and an unassigned teacher is a data problem to
    # fix in the admin screens, not something to punish them for at login.
    #
    # So an unassigned teacher keeps the wide list they already had, and
    # everyone who is assigned gets only their own. Same compromise as
    # subject_service.get_subjects.
    allowed = teacher_class_service.allowed_class_ids(db, teacher)
    if allowed:
        narrowed = query.filter(ClassMaster.class_id.in_(allowed))
        if narrowed.first() is not None:
            query = narrowed

    rows = query.order_by(ClassMaster.class_name).all()

    classes = [
        {
            "class_id":   row.class_id,
            "class_name": row.class_name,
            "section":    row.section_name,
            "label":      f"{row.class_name}{' - ' + row.section_name if row.section_name else ''}",
        }
        for row in rows
    ]
    return {"classes": classes}
