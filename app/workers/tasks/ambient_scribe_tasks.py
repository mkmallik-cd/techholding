from pathlib import Path
from uuid import UUID

from app.utils.logger import clear_tracking_id, get_logger, set_tracking_id

from app.db.session import SessionLocal
from app.repositories.patient_generation_repository import PatientGenerationRepository
from app.services.generators.ambient_scribe_generator import AmbientScribeGenerator
from app.services.artifact_writer import ArtifactWriter
from app.workers.celery_app import celery_app, _STEP4_QUEUE

logger = get_logger(__name__)


@celery_app.task(
    bind=True,
    name="workers.patient_generation.generate_ambient_scribe",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def generate_ambient_scribe(self, *, job_id: str) -> None:
    set_tracking_id(job_id)
    db = SessionLocal()
    try:
        repo = PatientGenerationRepository(db)
        job = repo.get_job(UUID(job_id))
        if job is None:
            logger.error("Step 3 job not found: %s", job_id)
            return

        repo.mark_processing(job)

        # result_payload contains Step 1+2 metadata and artifact paths
        metadata = job.result_payload or {}
        if not metadata:
            raise ValueError("result_payload is empty — Step 2 payload not found for job %s" % job_id)

        # Read the referral_packet.txt written by Step 2 — no re-generation
        referral_packet_path = metadata.get("referral_packet_path")
        if not referral_packet_path:
            raise ValueError("referral_packet_path missing from result_payload for job %s" % job_id)

        referral_text = Path(referral_packet_path).read_text(encoding="utf-8")
        logger.info("Step 3: loaded referral_packet.txt from %s", referral_packet_path)

        scribe_gen = AmbientScribeGenerator()
        scribe_text = scribe_gen.generate(
            referral_text=referral_text,
            metadata=metadata,
            model_id=job.selected_model,
        )
        logger.info("Step 3: ambient_scribe.txt generated for job_id=%s", job_id)

        from app.config.settings import get_settings
        settings = get_settings()
        writer = ArtifactWriter(settings.output_base_dir)
        artifact_path = writer.write_step3_artifacts(
            patient_external_id=job.patient_external_id,
            scribe_text=scribe_text,
        )

        step3_payload = {
            **metadata,
            "ambient_scribe_path": artifact_path + "/ambient_scribe.txt",
        }

        # Advance to Step 4 — gap answers generation
        repo.advance_to_next_step(
            job,
            next_phase="step4_gap_answers",
            step_result_payload=step3_payload,
            step_artifact_path=artifact_path,
        )
        from app.workers.tasks.gap_answers_tasks import generate_gap_answers
        generate_gap_answers.apply_async(
            kwargs={"job_id": job_id},
            queue=_STEP4_QUEUE,
            routing_key=_STEP4_QUEUE,
        )
        logger.info(
            "Step 3 → dispatched Step 4 (gap answers): job_id=%s patient=%s",
            job_id,
            job.patient_external_id,
        )

    except Exception as exc:
        logger.error("Step 3 task failed: job_id=%s error=%s", job_id, exc, exc_info=True)
        try:
            repo = PatientGenerationRepository(db)
            failed_job = repo.get_job(UUID(job_id))
            if failed_job:
                repo.mark_failed(failed_job, error_message=str(exc))
        except Exception:
            logger.error("Failed to persist Step 3 failure for job_id=%s", job_id, exc_info=True)
        raise
    finally:
        db.close()
        clear_tracking_id()
