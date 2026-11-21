"""
A teacher's own timetable.

Reads sgs_timetable for one teacher and joins the school's period structure
from sgs_period_master so each slot can be shown at its real time.

Two things the schema does not settle, and this module takes a position on:

  schedule_type   sgs_period_master has 'full' and 'half', but sgs_timetable
                  rows do not say which they belong to. Which weekdays are half
                  days is a school rule that is not recorded anywhere, so it is
                  a parameter here, defaulting to 'full'. When the school tells
                  us (it is usually Saturday), this becomes a lookup.

  academic_year   defaults to whatever the timetable rows actually use rather
                  than a constant, so the endpoint keeps working into the next
                  year without a code change.
"""

from collections import defaultdict
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.class_master import ClassMaster
from app.models.teacher import TeacherMaster
from app.models.timetable import PeriodMaster, Timetable
from app.schemas.timetable import PeriodOut, SlotOut, TimetableResponse
from app.services.teacher_class_service import class_display_name

ACTIVE = "Active"

DAY_NAMES = {1: "Monday", 2: "Tuesday", 3: "Wednesday",
             4: "Thursday", 5: "Friday", 6: "Saturday"}


def _live(column):
    """record_status is nullable and defaults to 'Active', so null counts."""
    return (column.is_(None)) | (column == ACTIVE)


def current_academic_year(db: Session, teacher_key: str) -> Optional[str]:
    """
    The year this teacher actually has a timetable in, latest first.

    Reading it from the data rather than hardcoding '2026-27' means the endpoint
    does not need editing when the school rolls over.
    """
    row = (
        db.query(Timetable.academic_year)
        .filter(Timetable.teacher_id == teacher_key, _live(Timetable.record_status))
        .order_by(Timetable.academic_year.desc())
        .first()
    )
    return row[0] if row else None


def periods_for(db: Session, academic_year: str, schedule_type: str) -> List[PeriodMaster]:
    return (
        db.query(PeriodMaster)
        .filter(
            PeriodMaster.academic_year == academic_year,
            PeriodMaster.schedule_type == schedule_type,
            _live(PeriodMaster.record_status),
        )
        .order_by(PeriodMaster.period_no)
        .all()
    )


def teacher_week(
    db: Session,
    teacher: TeacherMaster,
    academic_year: Optional[str] = None,
    schedule_type: str = "full",
) -> TimetableResponse:
    """This teacher's slots for the week, with the period structure to lay them on."""

    # teacher_id is a varchar in both tables and holds numeric ids as well as
    # staff codes, so it is compared as text. Passing the int would ask Postgres
    # for an operator between varchar and bigint, which does not exist.
    teacher_key = str(teacher.teacher_id)

    year = academic_year or current_academic_year(db, teacher_key)
    if not year:
        # No timetable rows for this teacher at all. An empty week is the honest
        # answer — the screen says "no timetable yet" rather than erroring.
        return TimetableResponse(
            academic_year="",
            schedule_type=schedule_type,
            periods=[],
            slots=[],
        )

    rows = (
        db.query(Timetable)
        .filter(
            Timetable.teacher_id == teacher_key,
            Timetable.academic_year == year,
            _live(Timetable.record_status),
        )
        .order_by(Timetable.day_of_week, Timetable.period_no)
        .all()
    )

    # One query for the class names rather than one per slot.
    class_ids = {r.class_id for r in rows if r.class_id is not None}
    names = {}
    if class_ids:
        names = {
            c.class_id: c.class_name
            for c in db.query(ClassMaster).filter(ClassMaster.class_id.in_(class_ids)).all()
            if c.class_name
        }

    slots = [
        SlotOut(
            day_of_week=r.day_of_week,
            period_no=r.period_no,
            class_id=r.class_id,
            class_name=names.get(r.class_id) or class_display_name(r.class_id),
            section=r.section,
            subject_name=r.subject_name,
        )
        for r in rows
    ]

    # The unique constraint on sgs_timetable is per class, so nothing stops the
    # same teacher being booked for two classes in one period. Report it.
    seen = defaultdict(list)
    for s in slots:
        seen[(s.day_of_week, s.period_no)].append(s)
    clashes = [
        "%s period %d: %s" % (
            DAY_NAMES.get(day, "Day %d" % day),
            period,
            " and ".join("%s-%s" % (s.class_name, s.section) for s in group),
        )
        for (day, period), group in sorted(seen.items())
        if len(group) > 1
    ]

    return TimetableResponse(
        academic_year=year,
        schedule_type=schedule_type,
        periods=[PeriodOut.model_validate(p) for p in periods_for(db, year, schedule_type)],
        slots=slots,
        clashes=clashes,
    )
