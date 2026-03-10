"""add invalid value to job_status enum

Revision ID: 20260309_0002
Revises: 20260309_0001
Create Date: 2026-03-09
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260309_0002"
down_revision = "20260309_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL supports ADD VALUE (idempotent with IF NOT EXISTS).
    op.execute("ALTER TYPE job_status ADD VALUE IF NOT EXISTS 'invalid'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values — intentionally a no-op.
    pass
