from uuid import UUID

from app.utils.logger import clear_tracking_id, get_logger, set_tracking_id

from app.config.settings import get_settings
from app.db.session import SessionLocal
from app.repositories.patient_generation_repository import PatientGenerationRepository
from app.services.artifact_writer import ArtifactWriter
from app.services.generators.patient_metadata_generator import PatientMetadataGenerator
from app.workers.celery_app import _STEP2_QUEUE, celery_app

logger = get_logger(__name__)


@celery_app.task(
    bind=True,
    name="workers.patient_generation.generate_metadata",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def generate_patient_metadata(self, *, job_id: str) -> None:
    set_tracking_id(job_id)
    settings = get_settings()
    db = SessionLocal()
    try:
        repo = PatientGenerationRepository(db)
        job = repo.get_job(UUID(job_id))
        if job is None:
            logger.error("Job not found: %s", job_id)
            return

        repo.mark_processing(job)

        generator = PatientMetadataGenerator()
        generated = generator.generate(
            patient_external_id=job.patient_external_id,
            model_id=job.selected_model,
            hardcoded_seed=job.request_payload.get("hardcoded_seed", "default-step1-seed"),
        )

        writer = ArtifactWriter(settings.output_base_dir)
        artifact_path = writer.write_step1_artifacts(
            patient_external_id=job.patient_external_id,
            metadata=generated.model_dump(),
        )

        # Persist Step 1 result and transition to Step 2
        repo.advance_to_next_step(
            job,
            next_phase="step2_referral_packet",
            step_result_payload=generated.model_dump(),
            step_artifact_path=artifact_path,
        )

        # Dispatch Step 2 task to its dedicated queue
        from app.workers.tasks.referral_packet_tasks import generate_referral_packet
        generate_referral_packet.apply_async(
            kwargs={"job_id": job_id},
            queue=_STEP2_QUEUE,
            routing_key=_STEP2_QUEUE,
        )
        logger.info("Step 1 done — dispatched Step 2: job_id=%s", job_id)

    except Exception as exc:
        logger.error("Step 1 task failed: job_id=%s error=%s", job_id, exc, exc_info=True)
        try:
            repo = PatientGenerationRepository(db)
            failed_job = repo.get_job(UUID(job_id))
            if failed_job:
                repo.mark_failed(failed_job, error_message=str(exc))
        except Exception:
            logger.error("Failed to persist task failure for job_id=%s", job_id, exc_info=True)
        raise
    finally:
        db.close()
        clear_tracking_id()
