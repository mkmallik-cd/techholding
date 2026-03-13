from celery import Celery
from celery.signals import after_setup_logger, after_setup_task_logger
from kombu import Exchange, Queue

from app.config.settings import get_settings
from app.utils.logger import StructuredJSONFormatter


def _apply_json_formatter(logger, **_kwargs) -> None:
    """Replace Celery's default formatter with StructuredJSONFormatter on all handlers."""
    formatter = StructuredJSONFormatter()
    for handler in logger.handlers:
        handler.setFormatter(formatter)


after_setup_logger.connect(_apply_json_formatter)
after_setup_task_logger.connect(_apply_json_formatter)
from app.config.llm_config import (
    STEP2_QUEUE,
    STEP3_QUEUE,
    STEP4_QUEUE,
    STEP5_QUEUE,
    STEP6_QUEUE,
    STEP7_QUEUE,
)

settings = get_settings()

# Step queue names imported from app.config.llm_config
_STEP2_QUEUE = STEP2_QUEUE
_STEP3_QUEUE = STEP3_QUEUE
_STEP4_QUEUE = STEP4_QUEUE
_STEP5_QUEUE = STEP5_QUEUE
_STEP6_QUEUE = STEP6_QUEUE
_STEP7_QUEUE = STEP7_QUEUE

celery_app = Celery(
    "patient_dataset_generation",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.workers.tasks.patient_generation_tasks",
        "app.workers.tasks.referral_packet_tasks",
        "app.workers.tasks.ambient_scribe_tasks",
        "app.workers.tasks.gap_answers_tasks",
        "app.workers.tasks.oasis_gold_standard_tasks",
        "app.workers.tasks.consistency_validation_tasks",
        "app.workers.tasks.llm_audit_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    broker_connection_retry_on_startup=True,
    task_default_exchange="patient_generation",
    task_default_exchange_type="direct",
    task_default_routing_key=settings.celery_queue_name,
    task_queues=[
        Queue(
            settings.celery_queue_name,
            Exchange("patient_generation", type="direct"),
            routing_key=settings.celery_queue_name,
        ),
        Queue(
            _STEP2_QUEUE,
            Exchange("patient_generation", type="direct"),
            routing_key=_STEP2_QUEUE,
        ),
        Queue(
            _STEP3_QUEUE,
            Exchange("patient_generation", type="direct"),
            routing_key=_STEP3_QUEUE,
        ),
        Queue(
            _STEP4_QUEUE,
            Exchange("patient_generation", type="direct"),
            routing_key=_STEP4_QUEUE,
        ),
        Queue(
            _STEP5_QUEUE,
            Exchange("patient_generation", type="direct"),
            routing_key=_STEP5_QUEUE,
        ),
        Queue(
            _STEP6_QUEUE,
            Exchange("patient_generation", type="direct"),
            routing_key=_STEP6_QUEUE,
        ),
        Queue(
            _STEP7_QUEUE,
            Exchange("patient_generation", type="direct"),
            routing_key=_STEP7_QUEUE,
        ),
    ],
    task_routes={
        "workers.patient_generation.generate_metadata": {
            "queue": settings.celery_queue_name,
            "routing_key": settings.celery_queue_name,
        },
        "workers.patient_generation.generate_referral_packet": {
            "queue": _STEP2_QUEUE,
            "routing_key": _STEP2_QUEUE,
        },
        "workers.patient_generation.generate_ambient_scribe": {
            "queue": _STEP3_QUEUE,
            "routing_key": _STEP3_QUEUE,
        },
        "workers.patient_generation.generate_gap_answers": {
            "queue": _STEP4_QUEUE,
            "routing_key": _STEP4_QUEUE,
        },
        "workers.patient_generation.generate_oasis_gold_standard": {
            "queue": _STEP5_QUEUE,
            "routing_key": _STEP5_QUEUE,
        },
        "workers.patient_generation.validate_consistency": {
            "queue": _STEP6_QUEUE,
            "routing_key": _STEP6_QUEUE,
        },
        "workers.patient_generation.run_llm_audit": {
            "queue": _STEP7_QUEUE,
            "routing_key": _STEP7_QUEUE,
        },
    },
    task_soft_time_limit=settings.celery_task_soft_time_limit_seconds,
    task_time_limit=settings.celery_task_time_limit_seconds,
)
