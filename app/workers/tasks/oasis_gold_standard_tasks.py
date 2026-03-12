import json
from pathlib import Path
from uuid import UUID

from app.utils.logger import clear_tracking_id, get_logger, set_tracking_id

from app.db.session import SessionLocal
from app.repositories.patient_generation_repository import PatientGenerationRepository
from app.services.artifact_writer import ArtifactWriter
from app.services.generators.oasis_gold_standard_generator import OasisGoldStandardGenerator
from app.workers.celery_app import celery_app, _STEP6_QUEUE

logger = get_logger(__name__)


@celery_app.task(
    bind=True,
    name="workers.patient_generation.generate_oasis_gold_standard",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
    # 5 LLM section batches + BIMS/PHQ copy — allow up to 15 min
    time_limit=900,
    soft_time_limit=780,
)
def generate_oasis_gold_standard(self, *, job_id: str) -> None:
    set_tracking_id(job_id)
    db = SessionLocal()
    try:
        repo = PatientGenerationRepository(db)
        job = repo.get_job(UUID(job_id))
        if job is None:
            logger.error("Step 6 job not found: %s", job_id)
            return

        repo.mark_processing(job)

        # result_payload contains all upstream artifact paths from Steps 1-4
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
        logger.info("Step 6: loaded referral_packet.txt from %s", referral_packet_path)

        # Read medication list (required — active med context for LLM)
        medication_list_path = metadata.get("medication_list_path")
        if not medication_list_path:
            raise ValueError(
                "medication_list_path missing from result_payload for job %s" % job_id
            )
        medication_list = json.loads(Path(medication_list_path).read_text(encoding="utf-8"))
        logger.info("Step 6: loaded medication_list.json from %s", medication_list_path)

        # Read gap answers (required — source of all BIMS + PHQ values)
        gap_answers_path = metadata.get("gap_answers_path")
        if not gap_answers_path:
            raise ValueError(
                "gap_answers_path missing from result_payload for job %s" % job_id
            )
        gap_answers = json.loads(Path(gap_answers_path).read_text(encoding="utf-8"))
        logger.info("Step 6: loaded tap_tap_gap_answers.json from %s", gap_answers_path)

        # Read ambient scribe (optional)
        scribe_text: str | None = None
        ambient_scribe_path = metadata.get("ambient_scribe_path")
        if ambient_scribe_path:
            try:
                scribe_text = Path(ambient_scribe_path).read_text(encoding="utf-8")
                logger.info("Step 6: loaded ambient_scribe.txt from %s", ambient_scribe_path)
            except FileNotFoundError:
                logger.warning(
                    "Step 6: ambient_scribe_path set but file not found: %s — proceeding without scribe",
                    ambient_scribe_path,
                )

        generator = OasisGoldStandardGenerator()
        oasis_gold_standard = generator.generate(
            referral_text=referral_text,
            medication_list=medication_list,
            scribe_text=scribe_text,
            gap_answers=gap_answers,
            metadata=metadata,
            model_id=job.selected_model,
        )
        logger.info(
            "Step 6: oasis_gold_standard.json generated for job_id=%s (%d items)",
            job_id,
            len([k for k in oasis_gold_standard.keys() if not k.startswith("_")]),
        )

        from app.config.settings import get_settings
        settings = get_settings()
        writer = ArtifactWriter(settings.output_base_dir)
        artifact_path = writer.write_step5_artifacts(
            patient_external_id=job.patient_external_id,
            oasis_gold_standard=oasis_gold_standard,
        )

        repo.advance_to_next_step(
            job,
            next_phase="step6_consistency_validation",
            step_result_payload={
                **metadata,
                "oasis_gold_standard_path": artifact_path + "/oasis_gold_standard.json",
            },
            step_artifact_path=artifact_path,
        )
        logger.info(
            "Step 6 completed, dispatching Step 7: job_id=%s patient=%s",
            job_id,
            job.patient_external_id,
        )

        from app.workers.tasks.consistency_validation_tasks import validate_consistency
        validate_consistency.apply_async(
            kwargs={"job_id": job_id},
            queue=_STEP6_QUEUE,
            routing_key=_STEP6_QUEUE,
        )

    except Exception as exc:
        logger.error("Step 6 task failed: job_id=%s error=%s", job_id, exc, exc_info=True)
        try:
            repo = PatientGenerationRepository(db)
            failed_job = repo.get_job(UUID(job_id))
            if failed_job:
                repo.mark_failed(failed_job, error_message=str(exc))
        except Exception:
            logger.error(
                "Failed to persist Step 6 failure for job_id=%s", job_id, exc_info=True
            )
        raise
    finally:
        db.close()
        clear_tracking_id()
