"""app.services.llm.langfuse_tracing — Langfuse LLM observability for patient generation.

Provides per-invocation LangChain callback handlers that automatically capture:
  - Input / output token counts
  - Estimated cost (based on model pricing tables in Langfuse)
  - Latency (wall-clock time for the Bedrock invoke)
  - Full prompt text and response text

How it works
------------
1. Each Celery task calls ``set_step_context()`` after loading the job from the DB.
   This stores (step_name, patient_external_id, model_id) in a ContextVar, which is
   isolated per Celery task invocation (thread-safe via contextvars semantics).

2. ``BedrockClient.invoke_json()`` calls ``get_langfuse_callback()`` before the retry
   loop. If tracing is enabled, it attaches the returned ``CallbackHandler`` as a
   LangChain config callback for that specific ``llm.invoke()`` call.

3. After a successful invoke, ``BedrockClient`` calls ``handler.flush()`` to ensure the
   batch HTTP request to Langfuse is sent synchronously before the task continues.

4. Each Celery task calls ``clear_step_context()`` in its ``finally`` block.

In Langfuse UI
--------------
  - All LLM calls for one patient are grouped under a single **Session** (session_id = job_id).
  - Each pipeline step appears as a separate **Trace** (trace_name = step_name).
  - Individual LLM calls (e.g. filter pass + answer batches in Step 4) are **Generations**
    nested inside their trace.

Enabling
--------
Set in .env:
    LANGFUSE_ENABLED=true
    LANGFUSE_PUBLIC_KEY=pk-lf-...
    LANGFUSE_SECRET_KEY=sk-lf-...
    LANGFUSE_HOST=http://localhost:3000    # or https://cloud.langfuse.com
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

# ---------------------------------------------------------------------------
# ContextVar — stores step-level metadata for the duration of a Celery task.
# Automatically isolated per task via contextvars semantics.
# ---------------------------------------------------------------------------
_step_context_var: ContextVar[dict[str, str]] = ContextVar(
    "step_context",
    default={"step_name": "unknown", "patient_id": "unknown", "model_id": ""},
)


def set_step_context(step_name: str, patient_id: str, model_id: str) -> None:
    """Set the step context for the current task execution (call after loading the job)."""
    _step_context_var.set(
        {"step_name": step_name, "patient_id": patient_id, "model_id": model_id}
    )


def clear_step_context() -> None:
    """Reset step context to defaults (call in task finally block)."""
    _step_context_var.set({"step_name": "unknown", "patient_id": "unknown", "model_id": ""})


def get_langfuse_callback() -> Any | None:
    """Build and return a LangfuseCallbackHandler for the current task context.

    Returns ``None`` when:
      - ``LANGFUSE_ENABLED`` is false (default)
      - ``LANGFUSE_PUBLIC_KEY`` / ``LANGFUSE_SECRET_KEY`` are not set
      - The ``langfuse`` package is not installed (import guard)

    The returned handler is configured with:
      - ``session_id``  = job_id  (groups all steps for one patient)
      - ``trace_name``  = step_name (e.g. "step1_metadata")
      - ``metadata``    = {"patient_id": ..., "model_id": ...}
    """
    from app.config.settings import get_settings

    settings = get_settings()
    if not settings.langfuse_enabled:
        return None
    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        return None

    try:
        from langfuse.callback import CallbackHandler
    except ImportError:
        return None

    from app.utils.logger import _tracking_id_var

    job_id = _tracking_id_var.get()
    step_ctx = _step_context_var.get()

    return CallbackHandler(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        host=settings.langfuse_host,
        session_id=job_id,
        trace_name=step_ctx["step_name"],
        metadata={
            "patient_id": step_ctx["patient_id"],
            "model_id": step_ctx["model_id"],
        },
    )
