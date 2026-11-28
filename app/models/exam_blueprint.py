"""
What a paper is made of, per school.

The Auto Test screen's test types and competitive patterns used to be
constants in the frontend, so every school got the same marks totals and
question mixes and changing one meant a deploy. These tables hold them per
tenant instead — see sql/0012_exam_blueprints.sql.

tenant_id is deliberately not mapped on any of these. Row-level security
scopes reads to the request's school, and the stamp_tenant trigger fills it
on insert, exactly as notice_board works.
"""

from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, Integer, Numeric, String,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.db.session import Base


class ExamBlueprint(Base):
    """One test type: Weekly, CT, PT, Term, Competitive."""

    __tablename__ = "exam_blueprint"

    blueprint_id      = Column(BigInteger, primary_key=True)
    code              = Column(String, nullable=False)
    label             = Column(String, nullable=False)
    short_label       = Column(String, nullable=True)
    note              = Column(String, nullable=True)
    total_marks       = Column(Numeric, nullable=False)
    minutes           = Column(Integer, nullable=True)
    group_name        = Column(String, nullable=False, default="school")
    exam_type         = Column(String, nullable=True)
    # ["PT-1", "PT-2", …] for types that come numbered; null otherwise.
    numbered          = Column(JSONB, nullable=True)
    display_seq       = Column(Integer, nullable=False, default=0)
    is_active         = Column(Boolean, nullable=False, default=True)
    created_datetime  = Column(DateTime(timezone=True), nullable=True)
    modified_datetime = Column(DateTime(timezone=True), nullable=True)
    record_status     = Column(String, nullable=True)
    version_no        = Column(Integer, nullable=True)


class ExamBlueprintRow(Base):
    """How many questions of one type a blueprint asks for, and their marks."""

    __tablename__ = "exam_blueprint_row"

    row_id         = Column(BigInteger, primary_key=True)
    blueprint_id   = Column(BigInteger, nullable=False, index=True)
    question_type  = Column(String, nullable=False)
    question_count = Column(Integer, nullable=False)
    marks_each     = Column(Numeric, nullable=False)
    display_seq    = Column(Integer, nullable=False, default=0)


class ExamPattern(Base):
    """A competitive pattern — NTSE, NMMS, an olympiad. Prefills numbers only."""

    __tablename__ = "exam_pattern"

    pattern_id        = Column(BigInteger, primary_key=True)
    code              = Column(String, nullable=False)
    label             = Column(String, nullable=False)
    target            = Column(String, nullable=False)
    question_count    = Column(Integer, nullable=False)
    marks_each        = Column(Numeric, nullable=False, default=1)
    minutes           = Column(Integer, nullable=True)
    display_seq       = Column(Integer, nullable=False, default=0)
    is_active         = Column(Boolean, nullable=False, default=True)
    created_datetime  = Column(DateTime(timezone=True), nullable=True)
    modified_datetime = Column(DateTime(timezone=True), nullable=True)
    record_status     = Column(String, nullable=True)
    version_no        = Column(Integer, nullable=True)
