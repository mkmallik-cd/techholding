from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.patient_generation_job import JobStatus, PatientGenerationJob


class PatientGenerationRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_job(
        self,
        *,
        patient_external_id: str,
        selected_model: str,
        request_payload: dict,
    ) -> PatientGenerationJob:
        job = PatientGenerationJob(
            patient_external_id=patient_external_id,
            phase="step1_metadata",
            status=JobStatus.QUEUED,
            selected_model=selected_model,
            request_payload=request_payload,
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def get_job(self, job_id: UUID) -> PatientGenerationJob | None:
        return self.db.query(PatientGenerationJob).filter(PatientGenerationJob.job_id == job_id).first()

    def mark_processing(self, job: PatientGenerationJob) -> PatientGenerationJob:
        job.status = JobStatus.PROCESSING
        job.started_at = datetime.now(timezone.utc)
        job.error_message = None
        self.db.commit()
        self.db.refresh(job)
        return job

    def mark_completed(self, job: PatientGenerationJob, *, artifact_path: str, result_payload: dict) -> PatientGenerationJob:
        job.status = JobStatus.COMPLETED
        job.artifact_path = artifact_path
        job.result_payload = result_payload
        job.completed_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(job)
        return job

    def mark_failed(self, job: PatientGenerationJob, *, error_message: str) -> PatientGenerationJob:
        job.status = JobStatus.FAILED
        job.error_message = error_message[:2000]
        job.completed_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(job)
        return job

    def mark_invalid(self, job: PatientGenerationJob, *, validation_errors: list[dict]) -> PatientGenerationJob:
        """Mark the job as clinically invalid (deterministic validation failure, not a crash)."""
        import json as _json
        job.status = JobStatus.INVALID
        job.error_message = _json.dumps(validation_errors)[:2000]
        job.completed_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(job)
        return job

    def increment_repair_attempt(self, job: PatientGenerationJob) -> PatientGenerationJob:
        """Increment the repair counter; call before re-queuing a repair chain."""
        job.repair_attempt = (job.repair_attempt or 0) + 1
        self.db.commit()
        self.db.refresh(job)
        return job

    def mark_invalid_permanent(self, job: PatientGenerationJob, *, validation_errors: list[dict]) -> PatientGenerationJob:
        """Mark the job permanently invalid after all repair attempts are exhausted."""
        import json as _json
        job.status = JobStatus.INVALID_PERMANENT
        job.error_message = _json.dumps(validation_errors)[:2000]
        job.completed_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(job)
        return job

    def advance_to_next_step(
        self,
        job: PatientGenerationJob,
        *,
        next_phase: str,
        step_result_payload: dict,
        step_artifact_path: str,
    ) -> PatientGenerationJob:
        """Persist the current step's output and transition job to the next step (queued)."""
        job.phase = next_phase
        job.status = JobStatus.QUEUED
        job.result_payload = step_result_payload
        job.artifact_path = step_artifact_path
        job.started_at = None
        job.completed_at = None
        job.error_message = None
        self.db.commit()
        self.db.refresh(job)
        return job
