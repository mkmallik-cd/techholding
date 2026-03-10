"""Repair Celery tasks: repair_gap_answers (Step 4 queue) and repair_gold_standard (Step 5 queue).

These tasks are triggered when consistency validation returns INVALID and repair_attempt < 3.
They apply deterministic fixes to the artifacts and re-queue the consistency validation.

Task chain:
  consistency_validation (INVALID + attempt < 3)
      → repair_gap_answers       [STEP4_QUEUE]
      → repair_gold_standard     [STEP5_QUEUE]
      → validate_consistency     [STEP6_QUEUE]
"""
from __future__ import annotations

import logging
from uuid import UUID

from app.db.session import SessionLocal
from app.repositories.patient_generation_repository import PatientGenerationRepository
from app.services.repair.repair_orchestrator import (
    repair_gap_answers_artifact,
    repair_gold_standard_artifact,
)
from app.workers.celery_app import _STEP4_QUEUE, _STEP5_QUEUE, _STEP6_QUEUE, celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="workers.patient_generation.repair_gap_answers",
    autoretry_for=(OSError, IOError),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 1},
    time_limit=120,
    soft_time_limit=100,
)
def repair_gap_answers(self, *, job_id: str) -> None:
    """Apply algorithmic fixes to tap_tap_gap_answers.json (PHQ-2 gate, BIMS/PHQ arithmetic).

    Passes control to repair_gold_standard when done.
    """
    db = SessionLocal()
    try:
        repo = PatientGenerationRepository(db)
        job = repo.get_job(UUID(job_id))
        if job is None:
            logger.error("repair_gap_answers: job not found: %s", job_id)
            return

        repo.mark_processing(job)

        metadata = job.result_payload or {}
        gap_answers_path = metadata.get("gap_answers_path")
        if not gap_answers_path:
            raise ValueError(
                "gap_answers_path missing from result_payload for job %s" % job_id
            )

        fixes = repair_gap_answers_artifact(gap_answers_path)
        logger.info(
            "repair_gap_answers: job_id=%s applied %d fix(es): %s",
            job_id,
            len(fixes),
            fixes,
        )

        repo.advance_to_next_step(
            job,
            next_phase="repair_gold_standard",
            step_result_payload=metadata,
            step_artifact_path=metadata.get("artifact_path", gap_answers_path.rsplit("/", 1)[0]),
        )
        logger.info(
            "repair_gap_answers: complete, dispatching repair_gold_standard — job_id=%s",
            job_id,
        )

        repair_gold_standard.apply_async(
            kwargs={"job_id": job_id},
            queue=_STEP5_QUEUE,
            routing_key=_STEP5_QUEUE,
        )

    except Exception as exc:
        logger.error(
            "repair_gap_answers task failed: job_id=%s error=%s", job_id, exc, exc_info=True
        )
        try:
            repo = PatientGenerationRepository(db)
            failed_job = repo.get_job(UUID(job_id))
            if failed_job:
                repo.mark_failed(failed_job, error_message=str(exc))
        except Exception:
            logger.error(
                "Failed to persist repair_gap_answers failure for job_id=%s",
                job_id,
                exc_info=True,
            )
        raise
    finally:
        db.close()


@celery_app.task(
    bind=True,
    name="workers.patient_generation.repair_gold_standard",
    autoretry_for=(OSError, IOError),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 1},
    time_limit=120,
    soft_time_limit=100,
)
def repair_gold_standard(self, *, job_id: str) -> None:
    """Apply algorithmic fixes to oasis_gold_standard.json using the stored validation errors.

    Passes control back to validate_consistency when done.
    """
    db = SessionLocal()
    try:
        repo = PatientGenerationRepository(db)
        job = repo.get_job(UUID(job_id))
        if job is None:
            logger.error("repair_gold_standard: job not found: %s", job_id)
            return

        repo.mark_processing(job)

        metadata = job.result_payload or {}
        gold_standard_path = metadata.get("oasis_gold_standard_path")
        if not gold_standard_path:
            raise ValueError(
                "oasis_gold_standard_path missing from result_payload for job %s" % job_id
            )

        validation_errors: list[dict] = metadata.get("validation_errors") or []
        if not validation_errors:
            logger.warning(
                "repair_gold_standard: no validation_errors in result_payload for job_id=%s"
                " — proceeding with empty error list (will re-validate)",
                job_id,
            )

        fixes = repair_gold_standard_artifact(gold_standard_path, validation_errors)
        logger.info(
            "repair_gold_standard: job_id=%s applied %d fix(es): %s",
            job_id,
            len(fixes),
            fixes,
        )

        repo.advance_to_next_step(
            job,
            next_phase="step6_consistency_validation",
            step_result_payload=metadata,
            step_artifact_path=metadata.get(
                "artifact_path", gold_standard_path.rsplit("/", 1)[0]
            ),
        )
        logger.info(
            "repair_gold_standard: complete, dispatching validate_consistency — job_id=%s",
            job_id,
        )

        from app.workers.tasks.consistency_validation_tasks import validate_consistency
        validate_consistency.apply_async(
            kwargs={"job_id": job_id},
            queue=_STEP6_QUEUE,
            routing_key=_STEP6_QUEUE,
        )

    except Exception as exc:
        logger.error(
            "repair_gold_standard task failed: job_id=%s error=%s", job_id, exc, exc_info=True
        )
        try:
            repo = PatientGenerationRepository(db)
            failed_job = repo.get_job(UUID(job_id))
            if failed_job:
                repo.mark_failed(failed_job, error_message=str(exc))
        except Exception:
            logger.error(
                "Failed to persist repair_gold_standard failure for job_id=%s",
                job_id,
                exc_info=True,
            )
        raise
    finally:
        db.close()
