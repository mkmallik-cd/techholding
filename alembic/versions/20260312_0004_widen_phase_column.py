"""widen phase column to VARCHAR(40) for step7_llm_audit phase name

Revision ID: 20260312_0004
Revises: 20260310_0003
Create Date: 2026-03-12 00:00:00.000000

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260312_0004"
down_revision = "20260310_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Widen the phase column from VARCHAR(30) to VARCHAR(40) to accommodate the
    # new "step7_llm_audit" phase name and provide headroom for future phases.
    op.alter_column(
        "patient_generation_jobs",
        "phase",
        existing_type=sa.String(30),
        type_=sa.String(40),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "patient_generation_jobs",
        "phase",
        existing_type=sa.String(40),
        type_=sa.String(30),
        existing_nullable=False,
    )
