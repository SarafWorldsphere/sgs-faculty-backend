"""
PeriodMaster + Timetable — map to sgs_period_master and sgs_timetable.

The school's day is described once in sgs_period_master: numbered periods with
their label and timings, including the non-teaching ones (assembly, breaks) so
a rendered timetable has the gaps in the right places. There are two schedule
types, 'full' and 'half', and the same period_no means different timings in
each.

sgs_timetable holds one row per filled slot: which class, section, day and
period, the subject, and the teacher taking it. A slot is unique per
(academic_year, class_id, section, day_of_week, period_no), so a class cannot
be double-booked — but a *teacher* can appear twice in one period, which is a
clash worth surfacing rather than hiding.

teacher_id is a varchar here, matching sgs_teacher_master.teacher_id, which is
also a varchar despite what the TeacherMaster model declares. Some ids are
numeric ('11'), some are staff codes ('T1002'); both are valid, so this must
always be compared as text.
"""

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Integer, String, Time

from app.db.session import Base


class PeriodMaster(Base):
    __tablename__ = "sgs_period_master"

    period_id     = Column(BigInteger, primary_key=True)
    academic_year = Column(String(9),   nullable=False)
    schedule_type = Column(String(10),  nullable=False, default="full")
    period_no     = Column(Integer,     nullable=False)
    period_label  = Column(String(50),  nullable=False)
    start_time    = Column(Time,        nullable=False)
    end_time      = Column(Time,        nullable=False)
    # False for assembly and breaks. They are still returned, so the grid shows
    # them in place instead of leaving a silent gap between periods.
    is_teaching   = Column(Boolean,     nullable=False, default=True)
    record_status = Column(String(20),  nullable=True, default="Active")
    created_at    = Column(DateTime,    nullable=True)


class Timetable(Base):
    __tablename__ = "sgs_timetable"

    timetable_id  = Column(BigInteger, primary_key=True)
    academic_year = Column(String(9),   nullable=False)
    class_id      = Column(BigInteger,  nullable=False)
    section       = Column(String(10),  nullable=False)
    # 1 = Monday .. 6 = Saturday. The table's own check constraint enforces it.
    day_of_week   = Column(Integer,     nullable=False)
    period_no     = Column(Integer,     nullable=False)
    subject_name  = Column(String(150), nullable=False)
    teacher_id    = Column(String(50),  nullable=False, index=True)
    record_status = Column(String(20),  nullable=True, default="Active")
    created_at    = Column(DateTime,    nullable=True)
    updated_at    = Column(DateTime,    nullable=True)
