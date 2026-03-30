"""app.services.llm.langfuse_tracing — Langfuse LLM observability for patient generation.

Uses the native Langfuse SDK (no LangChain dependency) to capture:
  - Input / output token counts
  - Prompt text and response text per LLM call
  - Model & parameters for each generation
  - Full session grouping across pipeline steps

How it works
------------
1. Each Celery task calls ``set_step_context()`` after loading the job from the DB.
   This creates a Langfuse Trace for the step and stores it in a ContextVar, which is
   isolated per task invocation (thread-safe via contextvars semantics).

2. ``BedrockClient.invoke_json()`` calls ``record_generation()`` after a successful
   llm.invoke(). This adds a Generation observation to the active trace with the
   full prompt, response text, and token counts from ``response.usage_metadata``.

3. Each Celery task calls ``clear_step_context()`` in its ``finally`` block, which
   flushes all pending events to Langfuse and resets the trace ContextVar.

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

import datetime
from contextvars import ContextVar
from typing import Any, Optional

# ---------------------------------------------------------------------------
# AWS Bedrock pricing table — (input_per_1M_tokens, output_per_1M_tokens) USD.
# Matched by substring against the Bedrock model ID string.
# ---------------------------------------------------------------------------
_BEDROCK_PRICING: list[tuple[str, float, float]] = [
    ("claude-opus-4",                  15.0,  75.0),
    ("claude-3-opus",                  15.0,  75.0),
    ("claude-sonnet-4-5",               3.0,  15.0),
    ("claude-sonnet-4",                 3.0,  15.0),
    ("claude-3-5-sonnet",               3.0,  15.0),
    ("claude-3-5-haiku",                0.8,   4.0),
    ("claude-3-sonnet",                 3.0,  15.0),
    ("claude-3-haiku",                  0.25,  1.25),
]


def _compute_cost(model_id: str, input_tokens: int, output_tokens: int) -> Optional[dict[str, float]]:
    """Return cost_details dict (USD) for a Bedrock model call, or None if model unknown."""
    model_lower = model_id.lower()
    for key, in_price, out_price in _BEDROCK_PRICING:
        if key in model_lower:
            input_cost  = input_tokens  * in_price  / 1_000_000
            output_cost = output_tokens * out_price / 1_000_000
            return {
                "input":  round(input_cost,  8),
                "output": round(output_cost, 8),
                "total":  round(input_cost + output_cost, 8),
            }
    return None


# ---------------------------------------------------------------------------
# Module-level Langfuse client singleton (created once per worker process).
# ---------------------------------------------------------------------------
_langfuse_client: Optional[Any] = None
_langfuse_initialized: bool = False


def _get_client() -> Optional[Any]:
    """Return the cached Langfuse client, creating it on first call if enabled."""
    global _langfuse_client, _langfuse_initialized
    if _langfuse_initialized:
        return _langfuse_client
    _langfuse_initialized = True

    from app.config.settings import get_settings

    settings = get_settings()
    if not settings.langfuse_enabled:
        return None
    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        return None

    try:
        from langfuse import Langfuse

        _langfuse_client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
        return _langfuse_client
    except ImportError:
        return None


# ---------------------------------------------------------------------------
# ContextVar — stores the active Langfuse Trace for the current Celery task.
# ---------------------------------------------------------------------------
_trace_var: ContextVar[Optional[Any]] = ContextVar("langfuse_trace", default=None)


def set_step_context(step_name: str, patient_id: str, model_id: str) -> None:
    """Create a Langfuse Trace for the current pipeline step and store it in context.

    Call this after loading the job from the DB at the start of each Celery task.
    The session_id is read automatically from the logging ContextVar (= job_id).
    """
    client = _get_client()
    if client is None:
        return

    from app.utils.logger import _tracking_id_var

    job_id = _tracking_id_var.get()
    trace = client.trace(
        name=step_name,
        session_id=job_id,
        input={"patient_id": patient_id, "model_id": model_id},
        metadata={"patient_id": patient_id, "model_id": model_id},
    )
    _trace_var.set(trace)


def clear_step_context() -> None:
    """Flush pending Langfuse events and reset the trace ContextVar.

    Call this in the Celery task's finally block alongside ``clear_tracking_id()``.
    """
    client = _get_client()
    if client is not None:
        client.flush()
    _trace_var.set(None)


def record_generation(
    *,
    prompt: str,
    model_id: str,
    output: str,
    usage_metadata: Optional[dict],
    max_tokens: int,
    start_time: Optional[datetime.datetime] = None,
) -> None:
    """Record a single LLM generation on the active step's Langfuse Trace.

    Called by ``BedrockClient.invoke_json()`` after each successful llm.invoke().

    Args:
        prompt:         The full prompt string sent to Bedrock.
        model_id:       Bedrock model identifier (e.g. ``"anthropic.claude-3-5-sonnet-..."``)
        output:         The plain-text response from the model.
        usage_metadata: ``response.usage_metadata`` dict with keys
                        ``input_tokens``, ``output_tokens``, ``total_tokens``.
        max_tokens:     The max_tokens parameter used for the call.
    """
    trace = _trace_var.get()
    if trace is None:
        return

    input_tokens  = usage_metadata.get("input_tokens",  0) if usage_metadata else 0
    output_tokens = usage_metadata.get("output_tokens", 0) if usage_metadata else 0
    total_tokens  = usage_metadata.get("total_tokens",  input_tokens + output_tokens) if usage_metadata else 0

    usage: dict[str, int] = {
        "input":  input_tokens,
        "output": output_tokens,
        "total":  total_tokens,
    }

    cost_details = _compute_cost(model_id, input_tokens, output_tokens)

    from app.config.llm_config import LLM_TEMPERATURE

    end_time = datetime.datetime.now(datetime.timezone.utc)
    trace.generation(
        name="bedrock_invoke",
        model=model_id,
        model_parameters={"max_tokens": max_tokens, "temperature": str(LLM_TEMPERATURE)},
        input=[{"role": "user", "content": prompt}],
        output=output,
        usage=usage,
        cost_details=cost_details,
        start_time=start_time,
        end_time=end_time,
    )
