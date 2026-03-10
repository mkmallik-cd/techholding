"""add repair_attempt column and invalid_permanent enum value

Revision ID: 20260310_0003
Revises: 20260309_0002
Create Date: 2026-03-10 00:00:00.000000

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260310_0003"
down_revision = "20260309_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE job_status ADD VALUE IF NOT EXISTS 'invalid_permanent'")
    op.add_column(
        "patient_generation_jobs",
        sa.Column(
            "repair_attempt",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    # PostgreSQL does not support removing enum values; only drop the column.
    op.drop_column("patient_generation_jobs", "repair_attempt")
