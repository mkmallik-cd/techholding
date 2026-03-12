from uuid import UUID

from app.services.llm.langfuse_tracing import clear_step_context, set_step_context
from app.utils.logger import clear_tracking_id, get_logger, set_tracking_id

from app.db.session import SessionLocal
from app.repositories.patient_generation_repository import PatientGenerationRepository
from app.services.artifact_writer import ArtifactWriter
from app.services.generators.medication_list_generator import MedicationListGenerator
from app.services.generators.referral_packet_generator import ReferralPacketGenerator
from app.workers.celery_app import celery_app, _STEP3_QUEUE, _STEP4_QUEUE

logger = get_logger(__name__)


@celery_app.task(
    bind=True,
    name="workers.patient_generation.generate_referral_packet",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def generate_referral_packet(self, *, job_id: str) -> None:
    set_tracking_id(job_id)
    db = SessionLocal()
    try:
        repo = PatientGenerationRepository(db)
        job = repo.get_job(UUID(job_id))
        if job is None:
            logger.error("Step 2 job not found: %s", job_id)
            return

        repo.mark_processing(job)
        set_step_context("step2_referral_packet", job.patient_external_id, job.selected_model)

        # Step 1 metadata is persisted in result_payload by advance_to_next_step
        metadata = job.result_payload or {}
        if not metadata:
            raise ValueError("result_payload is empty — Step 1 metadata not found for job %s" % job_id)

        referral_gen = ReferralPacketGenerator()
        referral_text = referral_gen.generate(
            metadata=metadata,
            model_id=job.selected_model,
        )
        logger.info("Step 2: referral_packet.txt generated for job_id=%s", job_id)

        med_gen = MedicationListGenerator()
        medication_list = med_gen.generate(
            referral_text=referral_text,
            metadata=metadata,
            model_id=job.selected_model,
        )
        logger.info("Step 2: medication_list.json generated for job_id=%s", job_id)

        from app.config.settings import get_settings
        settings = get_settings()
        writer = ArtifactWriter(settings.output_base_dir)
        artifact_path = writer.write_step2_artifacts(
            patient_external_id=job.patient_external_id,
            referral_text=referral_text,
            medication_list=medication_list,
        )

        step2_payload = {
            **metadata,
            "referral_packet_path": artifact_path + "/referral_packet.txt",
            "medication_list_path": artifact_path + "/medication_list.json",
        }

        if metadata.get("has_ambient_scribe"):
            # Advance to Step 3 — ambient scribe generation
            from app.repositories.patient_generation_repository import PatientGenerationRepository as _Repo
            repo.advance_to_next_step(
                job,
                next_phase="step3_ambient_scribe",
                step_result_payload=step2_payload,
                step_artifact_path=artifact_path,
            )
            from app.workers.tasks.ambient_scribe_tasks import generate_ambient_scribe
            generate_ambient_scribe.apply_async(
                kwargs={"job_id": job_id},
                queue=_STEP3_QUEUE,
                routing_key=_STEP3_QUEUE,
            )
            logger.info(
                "Step 2 → dispatched Step 3 (has_ambient_scribe=true): job_id=%s patient=%s",
                job_id,
                job.patient_external_id,
            )
        else:
            # has_ambient_scribe=false — skip Step 3, advance directly to Step 4
            repo.advance_to_next_step(
                job,
                next_phase="step4_gap_answers",
                step_result_payload=step2_payload,
                step_artifact_path=artifact_path,
            )
            from app.workers.tasks.gap_answers_tasks import generate_gap_answers
            generate_gap_answers.apply_async(
                kwargs={"job_id": job_id},
                queue=_STEP4_QUEUE,
                routing_key=_STEP4_QUEUE,
            )
            logger.info(
                "Step 2 → dispatched Step 4 (has_ambient_scribe=false, skipping Step 3): job_id=%s patient=%s",
                job_id,
                job.patient_external_id,
            )

    except Exception as exc:
        logger.error("Step 2 task failed: job_id=%s error=%s", job_id, exc, exc_info=True)
        try:
            repo = PatientGenerationRepository(db)
            failed_job = repo.get_job(UUID(job_id))
            if failed_job:
                repo.mark_failed(failed_job, error_message=str(exc))
        except Exception:
            logger.error("Failed to persist Step 2 failure for job_id=%s", job_id, exc_info=True)
        raise
    finally:
        db.close()
        clear_step_context()
        clear_tracking_id()
