from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.db.session import get_db
from app.models.patient_generation_job import JobStatus
from app.repositories.patient_generation_repository import PatientGenerationRepository
from app.schemas.patient_generation import (
    EnqueuePatientGenerationRequest,
    EnqueuePatientGenerationResponse,
    JobStatusResponse,
)
from app.workers.tasks.patient_generation_tasks import generate_patient_metadata

router = APIRouter(prefix="/api/v1/patient-generation", tags=["patient-generation"])


@router.post("/enqueue", response_model=EnqueuePatientGenerationResponse)
def enqueue_step1_job(payload: EnqueuePatientGenerationRequest, db: Session = Depends(get_db)):
    settings = get_settings()
    selected_model = payload.model_id or settings.default_bedrock_model_id

    repo = PatientGenerationRepository(db)
    job = repo.create_job(
        patient_external_id=payload.patient_external_id,
        selected_model=selected_model,
        request_payload=payload.model_dump(),
    )

    generate_patient_metadata.delay(job_id=str(job.job_id))

    return EnqueuePatientGenerationResponse(
        job_id=job.job_id,
        patient_external_id=job.patient_external_id,
        status=job.status.value,
    )


@router.get("/{job_id}", response_model=JobStatusResponse)
def get_step1_job_status(job_id: UUID, db: Session = Depends(get_db)):
    repo = PatientGenerationRepository(db)
    job = repo.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")

    return JobStatusResponse(
        job_id=job.job_id,
        patient_external_id=job.patient_external_id,
        phase=job.phase,
        status=job.status.value,
        selected_model=job.selected_model,
        repair_attempt=job.repair_attempt,
        artifact_path=job.artifact_path,
        error_message=job.error_message,
        request_payload=job.request_payload,
        result_payload=job.result_payload,
        created_at=job.created_at,
        updated_at=job.updated_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
    )


@router.post("/{job_id}/repair", response_model=JobStatusResponse)
def trigger_manual_repair(job_id: UUID, db: Session = Depends(get_db)):
    """Manually trigger the repair chain for a job that is in INVALID status.

    Only valid for jobs with status=INVALID (not INVALID_PERMANENT).
    Increments repair_attempt and queues the repair_gap_answers task.
    """
    from app.workers.celery_app import _STEP4_QUEUE
    from app.workers.tasks.repair_tasks import repair_gap_answers

    repo = PatientGenerationRepository(db)
    job = repo.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    if job.status != JobStatus.INVALID:
        raise HTTPException(
            status_code=409,
            detail=(
                f"job status is '{job.status.value}'; repair is only available for status='invalid'"
            ),
        )

    repo.increment_repair_attempt(job)
    repo.advance_to_next_step(
        job,
        next_phase="repair_gap_answers",
        step_result_payload=job.result_payload or {},
        step_artifact_path=job.artifact_path or "",
    )
    repair_gap_answers.apply_async(
        kwargs={"job_id": str(job_id)},
        queue=_STEP4_QUEUE,
        routing_key=_STEP4_QUEUE,
    )

    return JobStatusResponse(
        job_id=job.job_id,
        patient_external_id=job.patient_external_id,
        phase=job.phase,
        status=job.status.value,
        selected_model=job.selected_model,
        repair_attempt=job.repair_attempt,
        artifact_path=job.artifact_path,
        error_message=job.error_message,
        request_payload=job.request_payload,
        result_payload=job.result_payload,
        created_at=job.created_at,
        updated_at=job.updated_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
    )
