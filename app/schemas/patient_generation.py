from datetime import datetime
from typing import Any
from uuid import UUID

import re

from pydantic import BaseModel, Field, field_validator


class EnqueuePatientGenerationRequest(BaseModel):
    patient_external_id: str = Field(default="SYN_0001", min_length=3, max_length=100)
    model_id: str | None = Field(default=None, description="Optional Bedrock model id override")
    hardcoded_seed: str = Field(default="default-step1-seed", min_length=3, max_length=100)
    perform_llm_audit: bool = Field(
        default=False,
        description=(
            "When true, run Step 8 LLM cross-document consistency audit after Step 7 "
            "validation passes. Uses Claude claude-opus-4-5. Adds ~2-4 min to total runtime."
        ),
    )

    @field_validator("patient_external_id")
    @classmethod
    def validate_patient_id_format(cls, v: str) -> str:
        """Enforce PRD Section 11: patient_external_id must match SYN_XXXX format."""
        if not re.match(r"^SYN_\d{4}$", v):
            raise ValueError(
                f"patient_external_id must match the format SYN_XXXX (e.g. SYN_0001). "
                f"Got: {v!r}"
            )
        return v


class EnqueuePatientGenerationResponse(BaseModel):
    job_id: UUID
    patient_external_id: str
    status: str


class JobStatusResponse(BaseModel):
    job_id: UUID
    patient_external_id: str
    phase: str
    status: str
    selected_model: str
    repair_attempt: int = 0
    artifact_path: str | None = None
    error_message: str | None = None
    request_payload: dict[str, Any]
    result_payload: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
