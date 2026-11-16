from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_active_class_id, get_current_teacher
from app.db.session import get_db
from app.models.teacher import TeacherMaster
from app.models.chapter import SgsChapterContent
from app.models.chapter_master import ChapterMaster
from app.models.class_master import ClassMaster
from app.models.subject import SubjectMaster
from app.services.teacher_subjects import subject_ids_for

router = APIRouter(prefix="/chapters", tags=["chapters"])


def _serialise(master: ChapterMaster, has_content: bool, where: dict | None = None) -> dict:
    where = where or {}
    return {
        "chapter_id":    master.chapter_id,
        "chapter_name":  master.chapter_name,
        "content_title": master.chapter_name,
        # The list comes from chapter_master, which includes chapters with no
        # content row yet. Saying so up front is better than a 404 when the
        # teacher opens one.
        "has_content":   has_content,
        # Which class and subject this chapter belongs to. A teacher taking
        # several classes was shown one flat list with nothing to tell
        # "Chapter 3" for class 8 Science from "Chapter 3" for class 10
        # Social. The names travel with the row so the screen can group and
        # label without a lookup per chapter.
        "subject_id":    master.subject_id,
        "subject_name":  where.get("subject_name"),
        "class_id":      where.get("class_id"),
        "class_name":    where.get("class_name"),
    }


@router.get("")
def get_chapters(
    subject_id: Optional[int] = Query(None, description="Filter chapters by subject"),
    active_class_id: Optional[int] = Depends(get_active_class_id),
    teacher: TeacherMaster = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    """
    Chapters for the subjects this teacher teaches, in the class they are
    working in.

    Scoping happens here rather than in the caller: the endpoint previously
    returned every chapter in the school whenever the client omitted
    subject_id, which meant any teacher could see any subject's material.

    class_id narrows it further. Without it a teacher taking four classes got
    every chapter of all four in one list, which is correct and unusable —
    switching class in the header changed nothing. get_active_class_id does
    the authorisation, so a class the teacher does not hold is refused there
    rather than filtered here.
    """
    allowed = subject_ids_for(db, teacher)

    if allowed and active_class_id is not None:
        in_class = {
            row[0] for row in
            db.query(SubjectMaster.subject_id)
            .filter(
                SubjectMaster.subject_id.in_(allowed),
                SubjectMaster.class_id == active_class_id,
            )
            .all()
        }
        # Only narrow when the class actually has subjects of theirs. A class
        # with none would otherwise empty the screen, and a teacher with no
        # mapped subject in that class is better served the old wide list
        # than a blank page.
        if in_class:
            allowed = sorted(in_class)

    if not allowed:
        # No subject assignment we can resolve. Returning everything is how the
        # original leak happened, so return nothing and say why — the UI can
        # tell the teacher to have their subject assigned.
        return {"chapters": [], "reason": "no_subject_assigned"}

    if subject_id is not None and subject_id not in allowed:
        return {"chapters": [], "reason": "subject_not_assigned_to_teacher"}

    wanted = [subject_id] if subject_id is not None else allowed

    masters = (
        db.query(ChapterMaster)
        .filter(
            ChapterMaster.subject_id.in_(wanted),
            (ChapterMaster.record_status == "Active") | (ChapterMaster.record_status.is_(None)),
        )
        .order_by(ChapterMaster.chapter_no, ChapterMaster.chapter_id)
        .all()
    )

    # One query for which of these actually have readable content, so the list
    # can flag it without N round trips.
    ids = [m.chapter_id for m in masters]
    with_content = set()
    if ids:
        rows = (
            db.query(SgsChapterContent.chapter_id)
            .filter(
                SgsChapterContent.chapter_id.in_(ids),
                SgsChapterContent.is_active == True,
                SgsChapterContent.record_status == "Active",
            )
            .all()
        )
        with_content = {r[0] for r in rows}

    # Subject and class names for the chapters in hand — two queries, not one
    # per row. Without these the frontend has ids and nothing a teacher can
    # read.
    subject_ids = {m.subject_id for m in masters if m.subject_id}
    where: dict[int, dict] = {}
    if subject_ids:
        subjects = (
            db.query(SubjectMaster)
            .filter(SubjectMaster.subject_id.in_(subject_ids))
            .all()
        )
        class_ids = {s.class_id for s in subjects if s.class_id}
        class_names = {}
        if class_ids:
            class_names = {
                c.class_id: " ".join(filter(None, [c.class_name, c.section_name]))
                for c in db.query(ClassMaster).filter(ClassMaster.class_id.in_(class_ids)).all()
            }
        where = {
            s.subject_id: {
                "subject_name": s.subject_name,
                "class_id": s.class_id,
                "class_name": class_names.get(s.class_id),
            }
            for s in subjects
        }

    return {
        "chapters": [
            _serialise(m, m.chapter_id in with_content, where.get(m.subject_id))
            for m in masters
        ]
    }


@router.get("/{chapter_id}")
def get_chapter(
    chapter_id: int,
    teacher: TeacherMaster = Depends(get_current_teacher),
    db: Session = Depends(get_db),
):
    """Return a single chapter's full text content for the reading view."""
    master = db.query(ChapterMaster).filter(ChapterMaster.chapter_id == chapter_id).first()
    if not master:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chapter not found")

    # A chapter belonging to someone else's subject is not this teacher's to read.
    allowed = subject_ids_for(db, teacher)
    if master.subject_id not in allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your subject")

    row = (
        db.query(SgsChapterContent)
        .filter(
            SgsChapterContent.chapter_id == chapter_id,
            SgsChapterContent.is_active == True,
            SgsChapterContent.record_status == "Active",
        )
        .first()
    )

    # The chapter exists but nobody has uploaded its text yet. That is a
    # content gap, not a missing chapter — 404 here made the UI look broken.
    if not row:
        return {
            "chapter_id":    master.chapter_id,
            "chapter_name":  master.chapter_name,
            "content_title": master.chapter_name,
            "content":       "",
            "has_content":   False,
        }

    return {
        "chapter_id":    row.chapter_id,
        "chapter_name":  row.chapter_name,
        "content_title": row.content_title,
        "content":       row.full_text_content or "",
        "has_content":   bool(row.full_text_content),
    }
