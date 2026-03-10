"""create patient generation jobs table

Revision ID: 20260309_0001
Revises:
Create Date: 2026-03-09
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260309_0001"
down_revision = None
branch_labels = None
depends_on = None


job_status = sa.Enum("queued", "processing", "completed", "failed", name="job_status")


def upgrade() -> None:
    op.create_table(
        "patient_generation_jobs",
        sa.Column("job_id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("patient_external_id", sa.String(length=100), nullable=False),
        sa.Column("phase", sa.String(length=30), nullable=False, server_default="step1_metadata"),
        sa.Column("status", job_status, nullable=False, server_default="queued"),
        sa.Column("selected_model", sa.String(length=255), nullable=False),
        sa.Column("request_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("result_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("artifact_path", sa.String(length=500), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_patient_generation_jobs_patient_external_id", "patient_generation_jobs", ["patient_external_id"])


def downgrade() -> None:
    op.drop_index("ix_patient_generation_jobs_patient_external_id", table_name="patient_generation_jobs")
    op.drop_table("patient_generation_jobs")
