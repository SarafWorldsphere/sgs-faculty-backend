"""Create sgs_period_master and sgs_timetable

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-11

Three features need a timetable — the teacher's own week, the student's class
timetable, and the same shown to a parent — and none could be built because no
timetable existed anywhere.

Two tables: period timings are the same for every class and change twice a
year, so they are not repeated on every slot. The academic calendar switches to
half-day timings on 15 March 2027, which schedule_type carries.

For staging/production, run sql/0009_timetable.sql through the DB-access
process — it also seeds the period timings from the Government calendar.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sgs_period_master",
        sa.Column("period_id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("academic_year", sa.String(9), nullable=False),
        sa.Column("schedule_type", sa.String(10), nullable=False, server_default="full"),
        sa.Column("period_no", sa.Integer, nullable=False),
        sa.Column("period_label", sa.String(50), nullable=False),
        sa.Column("start_time", sa.Time, nullable=False),
        sa.Column("end_time", sa.Time, nullable=False),
        sa.Column("is_teaching", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("record_status", sa.String(20), server_default="Active"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.UniqueConstraint("academic_year", "schedule_type", "period_no",
                            name="uq_period_master"),
    )

    op.create_table(
        "sgs_timetable",
        sa.Column("timetable_id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("academic_year", sa.String(9), nullable=False),
        sa.Column("class_id", sa.BigInteger, nullable=False),
        sa.Column("section", sa.String(10), nullable=False),
        sa.Column("day_of_week", sa.Integer, nullable=False),
        sa.Column("period_no", sa.Integer, nullable=False),
        sa.Column("subject_name", sa.String(150), nullable=False),
        # varchar to match sgs_teacher_master.teacher_id ('T02')
        sa.Column("teacher_id", sa.String(50), nullable=False),
        sa.Column("record_status", sa.String(20), server_default="Active"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=True),
        sa.UniqueConstraint("academic_year", "class_id", "section",
                            "day_of_week", "period_no", name="uq_timetable_slot"),
        sa.CheckConstraint("day_of_week BETWEEN 1 AND 6", name="ck_timetable_day"),
        sa.CheckConstraint("period_no >= 0", name="ck_timetable_period"),
    )
    op.create_index("ix_sgs_timetable_class", "sgs_timetable",
                    ["academic_year", "class_id", "section"])
    op.create_index("ix_sgs_timetable_teacher", "sgs_timetable",
                    ["academic_year", "teacher_id"])

    # No unique constraint on (teacher_id, day_of_week, period_no) on purpose —
    # two teachers sharing a lab period is legitimate. The Admin screen checks
    # for the double-booking instead. See sql/0009_timetable.sql.


def downgrade() -> None:
    op.drop_index("ix_sgs_timetable_teacher", table_name="sgs_timetable")
    op.drop_index("ix_sgs_timetable_class", table_name="sgs_timetable")
    op.drop_table("sgs_timetable")
    op.drop_table("sgs_period_master")
