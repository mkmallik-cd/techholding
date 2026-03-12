"""Step 7 — Consistency Validation Celery Task

Reads the oasis_gold_standard.json and tap_tap_gap_answers.json artifacts
produced by Steps 5 and 4, runs all 6 deterministic consistency checks, then:
  - valid:   marks the job COMPLETED and writes validation_report.json with status="passed"
  - invalid: marks the job INVALID  and writes validation_report.json
  - crash:   marks the job FAILED   (technical error ≠ clinical invalidity)
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from app.services.llm.langfuse_tracing import clear_step_context, set_step_context
from app.utils.logger import clear_tracking_id, get_logger, set_tracking_id

from app.db.session import SessionLocal
from app.repositories.patient_generation_repository import PatientGenerationRepository
from app.services.artifact_writer import ArtifactWriter
from app.services.generators.consistency_validator import ConsistencyValidator
from app.workers.celery_app import _STEP4_QUEUE, _STEP6_QUEUE, celery_app

logger = get_logger(__name__)


@celery_app.task(
    bind=True,
    name="workers.patient_generation.validate_consistency",
    # Deterministic — only retry on transient infrastructure failures (DB/disk).
    autoretry_for=(OSError, IOError),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 1},
    # Checks are fast; 5 minutes is generous.
    time_limit=300,
    soft_time_limit=270,
)
def validate_consistency(self, *, job_id: str) -> None:
    set_tracking_id(job_id)
    db = SessionLocal()
    try:
        repo = PatientGenerationRepository(db)
        job = repo.get_job(UUID(job_id))
        if job is None:
            logger.error("Step 7 job not found: %s", job_id)
            return

        repo.mark_processing(job)
        set_step_context("step6_consistency_validation", job.patient_external_id, job.selected_model)

        metadata = job.result_payload or {}
        if not metadata:
            raise ValueError(
                "result_payload is empty — upstream payload not found for job %s" % job_id
            )

        # ── Load required artifacts ────────────────────────────────────────────
        oasis_path = metadata.get("oasis_gold_standard_path")
        gap_answers_path = metadata.get("gap_answers_path")

        if not oasis_path:
            raise ValueError("oasis_gold_standard_path missing from result_payload for job %s" % job_id)
        if not gap_answers_path:
            raise ValueError("gap_answers_path missing from result_payload for job %s" % job_id)

        gold_standard = json.loads(Path(oasis_path).read_text(encoding="utf-8"))
        gap_answers = json.loads(Path(gap_answers_path).read_text(encoding="utf-8"))
        logger.info(
            "Step 7: loaded gold_standard (%d items) and gap_answers for job_id=%s",
            len([k for k in gold_standard.keys() if not k.startswith("_")]),
            job_id,
        )

        # ── Run all 6 consistency checks ───────────────────────────────────────
        validator = ConsistencyValidator()
        result = validator.validate(
            gap_answers=gap_answers,
            gold_standard=gold_standard,
            metadata=metadata,
        )

        logger.info(
            "Step 7: job_id=%s checks_run=%d checks_passed=%d valid=%s",
            job_id,
            result.checks_run,
            result.checks_passed,
            result.is_valid,
        )

        # ── Write validation_report.json ───────────────────────────────────────
        validation_report = {
            "status": "passed" if result.is_valid else "invalid",
            "checks_run": result.checks_run,
            "checks_passed": result.checks_passed,
            "errors": result.errors,
            "validated_at": datetime.now(timezone.utc).isoformat(),
        }

        from app.config.settings import get_settings
        settings = get_settings()
        writer = ArtifactWriter(settings.output_base_dir)
        artifact_path = writer.write_step6_artifacts(
            patient_external_id=job.patient_external_id,
            validation_report=validation_report,
        )

        # ── Persist final status ───────────────────────────────────────────────
        if result.is_valid:
            updated_payload = {
                **metadata,
                "validation_report_path": artifact_path + "/validation_report.json",
            }
            perform_llm_audit = (job.request_payload or {}).get("perform_llm_audit", False)
            if perform_llm_audit:
                # Step 7 passed and the caller requested the LLM audit — advance to Step 8.
                from app.workers.celery_app import _STEP7_QUEUE
                from app.workers.tasks.llm_audit_tasks import run_llm_audit

                repo.advance_to_next_step(
                    job,
                    next_phase="step7_llm_audit",
                    step_result_payload=updated_payload,
                    step_artifact_path=artifact_path,
                )
                logger.info(
                    "Step 7 VALID — dispatching Step 8 LLM audit: job_id=%s patient=%s",
                    job_id,
                    job.patient_external_id,
                )
                run_llm_audit.apply_async(
                    kwargs={"job_id": job_id},
                    queue=_STEP7_QUEUE,
                    routing_key=_STEP7_QUEUE,
                )
            else:
                repo.mark_completed(
                    job,
                    artifact_path=artifact_path,
                    result_payload=updated_payload,
                )
                logger.info(
                    "Step 7 completed (VALID): job_id=%s patient=%s",
                    job_id,
                    job.patient_external_id,
                )
        else:
            _MAX_REPAIR_ATTEMPTS = 3
            if (job.repair_attempt or 0) < _MAX_REPAIR_ATTEMPTS:
                repo.increment_repair_attempt(job)
                repair_attempt_num = job.repair_attempt
                repo.advance_to_next_step(
                    job,
                    next_phase="repair_gap_answers",
                    step_result_payload={
                        **metadata,
                        "validation_errors": result.errors,
                        "validation_report_path": artifact_path + "/validation_report.json",
                    },
                    step_artifact_path=artifact_path,
                )
                logger.warning(
                    "Step 7 INVALID (attempt %d/%d): job_id=%s patient=%s errors=%d"
                    " — queuing repair chain",
                    repair_attempt_num,
                    _MAX_REPAIR_ATTEMPTS,
                    job_id,
                    job.patient_external_id,
                    len(result.errors),
                )
                from app.workers.tasks.repair_tasks import repair_gap_answers
                repair_gap_answers.apply_async(
                    kwargs={"job_id": job_id},
                    queue=_STEP4_QUEUE,
                    routing_key=_STEP4_QUEUE,
                )
            else:
                repo.mark_invalid_permanent(job, validation_errors=result.errors)
                logger.error(
                    "Step 7 permanently INVALID (all %d repair attempts exhausted):"
                    " job_id=%s patient=%s errors=%d",
                    _MAX_REPAIR_ATTEMPTS,
                    job_id,
                    job.patient_external_id,
                    len(result.errors),
                )

    except Exception as exc:
        logger.error("Step 7 task failed: job_id=%s error=%s", job_id, exc, exc_info=True)
        try:
            repo = PatientGenerationRepository(db)
            failed_job = repo.get_job(UUID(job_id))
            if failed_job:
                repo.mark_failed(failed_job, error_message=str(exc))
        except Exception:
            logger.error(
                "Failed to persist Step 7 failure for job_id=%s", job_id, exc_info=True
            )
        raise
    finally:
        db.close()
        clear_step_context()
        clear_tracking_id()
