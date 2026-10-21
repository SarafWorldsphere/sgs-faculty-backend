"""
Which classes a teacher may work in.

Two sources, both authoritative:

  sgs_teacher_master.class_id     the primary assignment — one class, and what
                                  every endpoint used before this existed
  sgs_teacher_class_map           the full list, for teachers who take more
                                  than one class

The primary assignment is always allowed, mapped or not. A teacher with no map
rows therefore sees exactly what they saw before, which is what lets this ship
without a data migration.

allowed_class_ids() is the authorisation boundary. Class-scoped endpoints take
a class_id from the client, so without checking it against this set any teacher
could read any class's students, reports and submissions by changing one query
parameter.
"""

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.class_master import ClassMaster
from app.models.teacher import TeacherMaster
from app.models.teacher_class_map import DELETED, TeacherClassMap
from app.schemas.auth import ClassOption

_LIVE = or_(TeacherClassMap.record_status.is_(None),
            TeacherClassMap.record_status != DELETED)


def class_display_name(class_id) -> str:
    """Format a class number as an ordinal grade: 8 → '8th Grade'."""
    try:
        n = int(class_id)
        suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
        return f"{n}{suffix} Grade"
    except (ValueError, TypeError):
        return str(class_id)


def assigned_rows(db: Session, teacher: TeacherMaster) -> list[TeacherClassMap]:
    """This teacher's live map rows, ordered for display."""
    return (
        db.query(TeacherClassMap)
        .filter(TeacherClassMap.teacher_id == teacher.teacher_id, _LIVE)
        .order_by(TeacherClassMap.class_id, TeacherClassMap.section)
        .all()
    )


def allowed_class_ids(db: Session, teacher: TeacherMaster) -> set[int]:
    """
    Every class this teacher may read. The primary assignment counts even when
    it has no map row — that is the pre-existing behaviour and must not regress.
    """
    ids = {row.class_id for row in assigned_rows(db, teacher) if row.class_id}
    if teacher.class_id:
        ids.add(teacher.class_id)
    return ids


def class_options(db: Session, teacher: TeacherMaster) -> list[ClassOption]:
    """
    What the faculty class selector shows: one entry per class, carrying the
    sections and subjects the teacher takes in it.

    A teacher with a single class still gets one entry, so the frontend has no
    special case — it renders a selector of one, or hides it.
    """
    grouped: dict[int, dict] = {}

    for row in assigned_rows(db, teacher):
        if not row.class_id:
            continue
        entry = grouped.setdefault(row.class_id, {"sections": set(), "subjects": set()})
        if row.section:
            entry["sections"].add(row.section)
        if row.subject_name:
            entry["subjects"].add(row.subject_name)

    # The primary assignment, whether or not it is mapped. Its sections come
    # from section_1/section_2 so an unmapped teacher still shows their section.
    if teacher.class_id:
        entry = grouped.setdefault(teacher.class_id, {"sections": set(), "subjects": set()})
        for section in (teacher.section_1, teacher.section_2):
            if section:
                entry["sections"].add(section)
        if teacher.subject_name:
            entry["subjects"].add(teacher.subject_name)

    if not grouped:
        return []

    names = {
        c.class_id: c.class_name
        for c in db.query(ClassMaster).filter(ClassMaster.class_id.in_(grouped)).all()
        if c.class_name
    }

    options = [
        ClassOption(
            class_id=class_id,
            class_name=names.get(class_id) or class_display_name(class_id),
            sections=sorted(entry["sections"]),
            subjects=sorted(entry["subjects"]),
            is_primary=(class_id == teacher.class_id),
        )
        for class_id, entry in grouped.items()
    ]
    # Primary first, then by name — the selector opens on the teacher's own class.
    options.sort(key=lambda o: (not o.is_primary, o.class_name or ""))
    return options
