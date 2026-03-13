from pathlib import Path
from uuid import UUID

from app.services.llm.langfuse_tracing import clear_step_context, set_step_context
from app.utils.logger import clear_tracking_id, get_logger, set_tracking_id

from app.db.session import SessionLocal
from app.repositories.patient_generation_repository import PatientGenerationRepository
from app.services.artifact_writer import ArtifactWriter
from app.services.generators.gap_answers_generator import GapAnswersGenerator
from app.workers.celery_app import celery_app
from app.workers.tasks.llm_audit_tasks import _extract_audit_context, _format_audit_conflicts

logger = get_logger(__name__)


@celery_app.task(
    bind=True,
    name="workers.patient_generation.generate_gap_answers",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
    # Step 4 runs two LLM calls (filter + answer-generation batches) — needs more time than other steps
    time_limit=900,
    soft_time_limit=780,
)
def generate_gap_answers(self, *, job_id: str, is_audit_fix: bool = False) -> None:
    set_tracking_id(job_id)
    db = SessionLocal()
    try:
        repo = PatientGenerationRepository(db)
        job = repo.get_job(UUID(job_id))
        if job is None:
            logger.error("Step 4 job not found: %s", job_id)
            return

        repo.mark_processing(job)
        set_step_context("step4_gap_answers", job.patient_external_id, job.selected_model)

        # result_payload contains Step 1+2+3 metadata and artifact paths
        metadata = job.result_payload or {}
        if not metadata:
            raise ValueError(
                "result_payload is empty — upstream payload not found for job %s" % job_id
            )

        # Read referral packet (always required)
        referral_packet_path = metadata.get("referral_packet_path")
        if not referral_packet_path:
            raise ValueError(
                "referral_packet_path missing from result_payload for job %s" % job_id
            )
        referral_text = Path(referral_packet_path).read_text(encoding="utf-8")
        logger.info("Step 4: loaded referral_packet.txt from %s", referral_packet_path)

        # Read ambient scribe if present (not available when has_ambient_scribe=false)
        scribe_text: str | None = None
        ambient_scribe_path = metadata.get("ambient_scribe_path")
        if ambient_scribe_path:
            try:
                scribe_text = Path(ambient_scribe_path).read_text(encoding="utf-8")
                logger.info("Step 4: loaded ambient_scribe.txt from %s", ambient_scribe_path)
            except FileNotFoundError:
                logger.warning(
                    "Step 4: ambient_scribe_path set but file not found: %s — proceeding without scribe",
                    ambient_scribe_path,
                )

        audit_context = (
            _extract_audit_context(metadata["llm_audit_report_path"])
            if metadata.get("llm_audit_report_path")
            else None
        )

        gap_gen = GapAnswersGenerator()
        if is_audit_fix and metadata.get("llm_audit_report_path") and metadata.get("gap_answers_path"):
            # Fix mode: load all existing documents and use the targeted revision prompt.
            import json as _json
            from pathlib import Path as _Path
            existing_gap_answers = _Path(metadata["gap_answers_path"]).read_text(encoding="utf-8")
            medication_list_json = _json.dumps(
                _json.loads(_Path(metadata["medication_list_path"]).read_text(encoding="utf-8"))
                if metadata.get("medication_list_path") else {}, indent=2
            )
            ambient_scribe_text = (
                _Path(metadata["ambient_scribe_path"]).read_text(encoding="utf-8")
                if metadata.get("ambient_scribe_path") else "(no ambient scribe generated)"
            )
            oasis_gold_standard_json = _json.dumps(
                _json.loads(_Path(metadata["oasis_gold_standard_path"]).read_text(encoding="utf-8"))
                if metadata.get("oasis_gold_standard_path") else {}, indent=2
            )
            audit_conflicts_text = _format_audit_conflicts(metadata["llm_audit_report_path"])
            gap_answers = gap_gen.generate_fix(
                referral_text=referral_text,
                ambient_scribe_text=ambient_scribe_text,
                medication_list_json=medication_list_json,
                current_gap_answers_json=existing_gap_answers,
                oasis_gold_standard_json=oasis_gold_standard_json,
                audit_conflicts_text=audit_conflicts_text,
                model_id=job.selected_model,
            )
        else:
            import json as _json
            from pathlib import Path as _Path
            _medication_list = (
                _json.loads(_Path(metadata["medication_list_path"]).read_text(encoding="utf-8"))
                if metadata.get("medication_list_path") else {}
            )
            gap_answers = gap_gen.generate(
                referral_text=referral_text,
                metadata=metadata,
                scribe_text=scribe_text,
                medication_list=_medication_list,
                model_id=job.selected_model,
                audit_context=audit_context,
            )
        logger.info("Step 4: tap_tap_gap_answers.json generated for job_id=%s", job_id)

        from app.config.settings import get_settings
        settings = get_settings()
        writer = ArtifactWriter(settings.output_base_dir)
        artifact_path = writer.write_step4_artifacts(
            patient_external_id=job.patient_external_id,
            gap_answers=gap_answers,
        )

        step4_payload = {
            **metadata,
            "gap_answers_path": artifact_path + "/tap_tap_gap_answers.json",
        }

        # Advance to Step 6 — OASIS gold-standard generation
        repo.advance_to_next_step(
            job,
            next_phase="step5_oasis_gold_standard",
            step_result_payload=step4_payload,
            step_artifact_path=artifact_path,
        )
        from app.workers.celery_app import _STEP5_QUEUE
        from app.workers.tasks.oasis_gold_standard_tasks import generate_oasis_gold_standard
        generate_oasis_gold_standard.apply_async(
            kwargs={"job_id": job_id, "is_audit_fix": is_audit_fix},
            queue=_STEP5_QUEUE,
            routing_key=_STEP5_QUEUE,
        )
        logger.info(
            "Step 4 → dispatched Step 6 (oasis gold standard): job_id=%s patient=%s",
            job_id,
            job.patient_external_id,
        )

    except Exception as exc:
        logger.error("Step 4 task failed: job_id=%s error=%s", job_id, exc, exc_info=True)
        try:
            repo = PatientGenerationRepository(db)
            failed_job = repo.get_job(UUID(job_id))
            if failed_job:
                repo.mark_failed(failed_job, error_message=str(exc))
        except Exception:
            logger.error(
                "Failed to persist Step 4 failure for job_id=%s", job_id, exc_info=True
            )
        raise
    finally:
        db.close()
        clear_step_context()
        clear_tracking_id()
