from datetime import time
from typing import List, Optional

from pydantic import BaseModel


class PeriodOut(BaseModel):
    """One row of the grid — a period, or a break that sits between periods."""

    period_no:    int
    period_label: str
    start_time:   time
    end_time:     time
    is_teaching:  bool

    model_config = {"from_attributes": True}


class SlotOut(BaseModel):
    """One class this teacher takes, at one period on one day."""

    day_of_week:  int
    period_no:    int
    class_id:     int
    class_name:   Optional[str] = None
    section:      str
    subject_name: str


class TimetableResponse(BaseModel):
    """
    The teacher's week.

    periods and slots are returned separately rather than as a nested grid: the
    periods are the same for every day, and sending them once per day would
    repeat them six times. The client places each slot at
    (day_of_week, period_no).

    `clashes` lists the (day, period) pairs where this teacher is down for more
    than one class at once. The table's unique constraint is per class, so it
    cannot prevent this — it is a timetabling mistake, and the teacher should
    see it rather than have one of the two silently win.
    """

    academic_year: str
    schedule_type: str
    periods:       List[PeriodOut]
    slots:         List[SlotOut]
    clashes:       List[str] = []
