from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class EnqueuePatientGenerationRequest(BaseModel):
    patient_external_id: str = Field(default="PATIENT-0001", min_length=3, max_length=100)
    model_id: str | None = Field(default=None, description="Optional Bedrock model id override")
    hardcoded_seed: str = Field(default="default-step1-seed", min_length=3, max_length=100)


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
