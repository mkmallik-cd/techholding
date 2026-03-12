"""
app.config.settings — Application settings loaded from environment / .env file.

All runtime-configurable parameters live here.  Business-logic constants
(clinical archetypes, OASIS field maps, LLM prompt tuning flags) live in
``app.config.constants``, ``app.config.oasis_field_map``, and
``app.config.llm_config`` respectively.

Usage:
    from app.config.settings import get_settings
    settings = get_settings()          # returns a cached singleton
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Pydantic BaseSettings for the patient-dataset-generation service.

    All fields can be overridden via environment variables or a ``.env``
    file placed in the working directory.  Unknown env-vars are silently
    ignored (``extra="ignore"``).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Service identity ──────────────────────────────────────────────────────
    app_name: str = "patient-dataset-generation"
    app_env: str = "local"
    app_host: str = "0.0.0.0"
    app_port: int = 8081

    # ── Database ──────────────────────────────────────────────────────────────
    # Full SQLAlchemy connection string (postgres+psycopg2)
    database_url: str = (
        "postgresql+psycopg2://postgres:postgres@postgres:5432/patient_generation"
    )

    # ── Celery / RabbitMQ ─────────────────────────────────────────────────────
    # Broker URL — AMQP connection to RabbitMQ
    celery_broker_url: str = "amqp://guest:guest@rabbitmq:5672//"
    # Result backend — "rpc://" stores results in-memory via RabbitMQ reply-queue
    celery_result_backend: str = "rpc://"
    # Name of the Step 1 queue (first queue in the pipeline chain)
    celery_queue_name: str = "patient_generation.step1"
    # Per-task soft time limit (seconds) — worker raises SoftTimeLimitExceeded
    celery_task_soft_time_limit_seconds: int = 240
    # Per-task hard time limit (seconds) — worker is killed if exceeded
    celery_task_time_limit_seconds: int = 300

    # ── AWS / Bedrock ─────────────────────────────────────────────────────────
    aws_region: str = "us-east-1"
    # Default Claude model used when no model_id is supplied in the API request
    default_bedrock_model_id: str = "us.anthropic.claude-3-5-sonnet-20241022-v2:0"
    # Model used exclusively for the Step 8 LLM cross-document consistency audit.
    # Set LLM_AUDIT_MODEL_ID in .env to override (must be enabled in your Bedrock account).
    llm_audit_model_id: str = "us.anthropic.claude-opus-4-6-v1"

    # ── Artifact storage ──────────────────────────────────────────────────────
    # Root directory where per-patient output folders are written
    output_base_dir: str = "/app/output"

    # ── Langfuse observability ────────────────────────────────────────────────
    # Set langfuse_enabled=true and supply keys to enable LLM tracing.
    # Self-hosted: add the langfuse service in docker-compose.yml and create a
    # project at http://localhost:3000 to obtain the public/secret keys.
    langfuse_enabled: bool = False
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "http://localhost:3000"


@lru_cache
def get_settings() -> Settings:
    """
    Return a cached singleton of the application Settings.

    The ``@lru_cache`` decorator ensures Settings is instantiated only once
    per process, avoiding repeated .env parsing on every Celery task execution.
    """
    return Settings()
