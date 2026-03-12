"""Step 8 — LLM Cross-Document Consistency Audit Celery Task.

Runs only when the enqueue request included ``perform_llm_audit=true`` AND
Step 7 (consistency validation) passed.  Uses Claude claude-opus-4-5 to audit
every OASIS field across all 5 generated documents and writes
``llm_audit_report.json`` to the patient output directory.
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from app.services.llm.langfuse_tracing import clear_step_context, set_step_context
from app.utils.logger import clear_tracking_id, get_logger, set_tracking_id

from app.db.session import SessionLocal
from app.repositories.patient_generation_repository import PatientGenerationRepository
from app.services.artifact_writer import ArtifactWriter
from app.services.generators.llm_audit_generator import LlmAuditGenerator
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task(
    bind=True,
    name="workers.patient_generation.run_llm_audit",
    # LLM audit makes multiple Bedrock calls; allow up to 16 minutes.
    time_limit=960,
    soft_time_limit=900,
    # Retry only on transient infrastructure failures (DB/disk/network), not LLM errors.
    autoretry_for=(OSError, IOError),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 1},
)
def run_llm_audit(self, *, job_id: str) -> None:
    set_tracking_id(job_id)
    db = SessionLocal()
    try:
        repo = PatientGenerationRepository(db)
        job = repo.get_job(UUID(job_id))
        if job is None:
            logger.error("Step 8 job not found: %s", job_id)
            return

        repo.mark_processing(job)
        set_step_context("step8_llm_audit", job.patient_external_id, job.selected_model)

        metadata = job.result_payload or {}
        if not metadata:
            raise ValueError(
                "result_payload is empty — upstream payload not found for job %s" % job_id
            )

        # ── Load referral packet (always required) ────────────────────────────
        referral_packet_path = metadata.get("referral_packet_path")
        if not referral_packet_path:
            raise ValueError(
                "referral_packet_path missing from result_payload for job %s" % job_id
            )
        referral_text = Path(referral_packet_path).read_text(encoding="utf-8")
        logger.info("Step 8: loaded referral_packet.txt from %s", referral_packet_path)

        # ── Load ambient scribe (optional) ────────────────────────────────────
        ambient_scribe_text = ""
        ambient_scribe_path = metadata.get("ambient_scribe_path")
        if ambient_scribe_path:
            try:
                ambient_scribe_text = Path(ambient_scribe_path).read_text(encoding="utf-8")
                logger.info("Step 8: loaded ambient_scribe.txt from %s", ambient_scribe_path)
            except FileNotFoundError:
                logger.warning(
                    "Step 8: ambient_scribe_path set but file not found: %s — proceeding without scribe",
                    ambient_scribe_path,
                )

        # ── Load medication list ───────────────────────────────────────────────
        medication_list_path = metadata.get("medication_list_path")
        if not medication_list_path:
            raise ValueError(
                "medication_list_path missing from result_payload for job %s" % job_id
            )
        medication_list = json.loads(Path(medication_list_path).read_text(encoding="utf-8"))
        logger.info("Step 8: loaded medication_list.json from %s", medication_list_path)

        # ── Load gap answers ───────────────────────────────────────────────────
        gap_answers_path = metadata.get("gap_answers_path")
        if not gap_answers_path:
            raise ValueError(
                "gap_answers_path missing from result_payload for job %s" % job_id
            )
        gap_answers = json.loads(Path(gap_answers_path).read_text(encoding="utf-8"))
        logger.info("Step 8: loaded tap_tap_gap_answers.json from %s", gap_answers_path)

        # ── Load OASIS gold standard ───────────────────────────────────────────
        oasis_path = metadata.get("oasis_gold_standard_path")
        if not oasis_path:
            raise ValueError(
                "oasis_gold_standard_path missing from result_payload for job %s" % job_id
            )
        gold_standard = json.loads(Path(oasis_path).read_text(encoding="utf-8"))
        logger.info(
            "Step 8: loaded oasis_gold_standard.json (%d fields) from %s",
            len([k for k in gold_standard if not k.startswith("_")]),
            oasis_path,
        )

        # ── Run the audit ──────────────────────────────────────────────────────
        generator = LlmAuditGenerator()
        audit_report = generator.generate(
            referral_text=referral_text,
            ambient_scribe_text=ambient_scribe_text,
            medication_list=medication_list,
            gap_answers=gap_answers,
            gold_standard=gold_standard,
        )

        logger.info(
            "Step 8: audit complete for job_id=%s — fields_audited=%d conflicts=%d",
            job_id,
            audit_report.get("fields_audited", 0),
            audit_report.get("fields_with_conflicts", 0),
        )

        # ── Write artifact ────────────────────────────────────────────────────
        from app.config.settings import get_settings
        settings = get_settings()
        writer = ArtifactWriter(settings.output_base_dir)
        artifact_path = writer.write_llm_audit_artifacts(
            patient_external_id=job.patient_external_id,
            audit_report=audit_report,
        )

        # ── Mark job completed ────────────────────────────────────────────────
        repo.mark_completed(
            job,
            artifact_path=artifact_path,
            result_payload={
                **metadata,
                "llm_audit_report_path": artifact_path + "/llm_audit_report.json",
            },
        )
        logger.info(
            "Step 8 completed: job_id=%s patient=%s audit_status=%s",
            job_id,
            job.patient_external_id,
            audit_report.get("audit_status"),
        )

    except Exception as exc:
        logger.error("Step 8 task failed: job_id=%s error=%s", job_id, exc, exc_info=True)
        try:
            repo = PatientGenerationRepository(db)
            failed_job = repo.get_job(UUID(job_id))
            if failed_job:
                repo.mark_failed(failed_job, error_message=str(exc))
        except Exception:
            logger.error(
                "Failed to persist Step 8 failure for job_id=%s", job_id, exc_info=True
            )
        raise
    finally:
        db.close()
        clear_step_context()
        clear_tracking_id()
