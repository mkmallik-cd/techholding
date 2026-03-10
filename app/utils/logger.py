"""app.utils.logger — Structured JSON logging for patient-dataset-generation.

Every log line is emitted as a single JSON object:
    {
        "message":    "<log message string>",
        "trackingId": "<job_id or N/A>",
        "method":     "<function name that called the logger>",
        "timestamp":  "<ISO 8601 UTC>"
    }

Usage in modules
----------------
    from app.utils.logger import get_logger
    logger = get_logger(__name__)
    logger.info("Step 4: gap answers generated")

Usage in Celery tasks (set once per task invocation)
-----------------------------------------------------
    from app.utils.logger import set_tracking_id, clear_tracking_id
    ...
    def my_task(self, *, job_id: str) -> None:
        set_tracking_id(job_id)
        try:
            ...
        finally:
            clear_tracking_id()
"""
from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# ContextVar — stores the current job_id for the duration of a Celery task.
# Automatically isolated per async task / thread via contextvars semantics.
# ---------------------------------------------------------------------------
_tracking_id_var: ContextVar[str] = ContextVar("tracking_id", default="N/A")


def set_tracking_id(job_id: str) -> None:
    """Set the trackingId for the current execution context (call at task start)."""
    _tracking_id_var.set(job_id)


def clear_tracking_id() -> None:
    """Reset trackingId to the default 'N/A' (call in task finally block)."""
    _tracking_id_var.set("N/A")


# ---------------------------------------------------------------------------
# Formatter
# ---------------------------------------------------------------------------
class StructuredJSONFormatter(logging.Formatter):
    """Emit each log record as a single-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        # Merge any exception text into the message
        message = record.getMessage()
        if record.exc_info:
            if not record.exc_text:
                record.exc_text = self.formatException(record.exc_info)
        if record.exc_text:
            message = f"{message}\n{record.exc_text}"

        payload = {
            "message": message,
            "trackingId": _tracking_id_var.get(),
            "method": record.funcName,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        return json.dumps(payload, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
_logging_configured = False


def setup_logging(level: str = "INFO") -> None:
    """Attach StructuredJSONFormatter to the root logger.

    Idempotent — safe to call multiple times (only configures once).
    """
    global _logging_configured
    if _logging_configured:
        return

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove any existing handlers to avoid duplicate output
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredJSONFormatter())
    root.addHandler(handler)

    _logging_configured = True


# ---------------------------------------------------------------------------
# Public alias — drop-in for logging.getLogger
# ---------------------------------------------------------------------------
def get_logger(name: str) -> logging.Logger:
    """Return a standard Logger; identical to logging.getLogger(name)."""
    return logging.getLogger(name)
