"""Create sgs_teacher_class_map — a teacher's full class/section/subject list

Revision ID: 0007
Revises: 0004
Create Date: 2026-09-30

Numbered 0007 to stay in step with sql/: 0005 and 0006 are SQL-only changes
with no alembic counterpart, so 0004 is still the alembic head.

The shared RDS instances are not migrated by this app (the app user has no DDL
rights there); this file documents the schema and applies it to local
databases. For staging/production, run sql/0007_teacher_class_map.sql through
the DB-access process.

Purely additive. Nothing on sgs_teacher_master changes, and a teacher with no
rows here behaves exactly as before.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sgs_teacher_class_map",
        sa.Column("map_id", sa.BigInteger, primary_key=True, autoincrement=True),
        # varchar: matches sgs_teacher_master.teacher_id ('T02') and every
        # sibling table. No FK — the production tables are owned by a different
        # role, and data entry writes the map before every teacher row exists.
        sa.Column("teacher_id", sa.String(50), nullable=False),
        sa.Column("class_id", sa.BigInteger, nullable=False),
        sa.Column("section", sa.String(10), nullable=False),
        sa.Column("subject_name", sa.String(150), nullable=True),
        sa.Column("is_class_teacher", sa.Boolean, server_default=sa.false(), nullable=True),
        sa.Column("record_status", sa.String(20), server_default="Active", nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=True),
        sa.UniqueConstraint("teacher_id", "class_id", "section", "subject_name",
                            name="uq_teacher_class_map_assignment"),
    )
    op.create_index("ix_sgs_teacher_class_map_teacher_id",
                    "sgs_teacher_class_map", ["teacher_id"])
    op.create_index("ix_sgs_teacher_class_map_class_id",
                    "sgs_teacher_class_map", ["class_id"])


def downgrade() -> None:
    op.drop_index("ix_sgs_teacher_class_map_class_id", table_name="sgs_teacher_class_map")
    op.drop_index("ix_sgs_teacher_class_map_teacher_id", table_name="sgs_teacher_class_map")
    op.drop_table("sgs_teacher_class_map")
