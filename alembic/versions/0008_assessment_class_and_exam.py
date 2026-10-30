"""Give an assessment a class_id and an exam_id

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-09

sgs_assessments had class_name as free text and no link to sgs_exam_master, so
an assessment could not be scoped to a class or told apart from another PT.
Both columns are additive; existing rows and readers are unaffected.

The assessment_type enum is deliberately left alone — it holds
quiz/test/exam/assignment, which does not match this school's PT/CT/Weekly
scheme, and Postgres cannot remove an enum value once added. exam_id carries
the real identity instead.

For staging/production, run sql/0008_assessment_class_and_exam.sql through the
DB-access process.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sgs_assessments", sa.Column("class_id", sa.BigInteger, nullable=True))
    op.add_column("sgs_assessments", sa.Column("exam_id", sa.BigInteger, nullable=True))
    op.create_index("ix_sgs_assessments_class_id", "sgs_assessments", ["class_id"])
    op.create_index("ix_sgs_assessments_exam_id", "sgs_assessments", ["exam_id"])


def downgrade() -> None:
    op.drop_index("ix_sgs_assessments_exam_id", table_name="sgs_assessments")
    op.drop_index("ix_sgs_assessments_class_id", table_name="sgs_assessments")
    op.drop_column("sgs_assessments", "exam_id")
    op.drop_column("sgs_assessments", "class_id")
