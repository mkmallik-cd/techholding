"""
app.services.llm.bedrock_client — AWS Bedrock LLM client wrapper.

Provides a thin, retry-aware wrapper around ``langchain_aws.ChatBedrockConverse``
so every generator shares a single, consistent invocation path.

Key behaviours:
  - Per-(model_id, max_tokens) instance caching to avoid redundant client construction.
  - Exponential-backoff retry loop (up to ``MAX_LLM_RETRIES`` attempts).
  - Returns a uniform ``{"text": str, "raw": dict}`` response envelope.
"""

from __future__ import annotations

import datetime
import time
from typing import Any

from langchain_aws import ChatBedrockConverse
from langchain_core.messages import HumanMessage

from app.config.llm_config import LLM_TEMPERATURE, MAX_LLM_RETRIES
from app.config.settings import get_settings
from app.services.llm.langfuse_tracing import record_generation
from app.utils.logger import get_logger

logger = get_logger(__name__)


class BedrockClient:
    """Wrapper around ChatBedrockConverse with per-model client caching and retry logic."""

    def __init__(self) -> None:
        # Load runtime settings (AWS region, default model ID, etc.)
        self.settings = get_settings()
        # Cache["{model_id}:{max_tokens}"] → ChatBedrockConverse instance
        self._clients: dict[str, ChatBedrockConverse] = {}

    def _get_client(self, model_id: str, max_tokens: int = 1200) -> ChatBedrockConverse:
        """Return a cached ChatBedrockConverse instance for the given model/token budget.

        Args:
            model_id:   Bedrock model identifier (e.g. ``"anthropic.claude-3-5-sonnet-20241022-v2:0"``).
            max_tokens: Maximum tokens the model is allowed to generate in one call.

        Returns:
            A ready-to-use ``ChatBedrockConverse`` instance.
        """
        cache_key = f"{model_id}:{max_tokens}"
        client = self._clients.get(cache_key)
        if client is not None:
            return client  # Reuse existing client to avoid redundant construction

        # Build a new client and cache it for subsequent calls with the same params
        client = ChatBedrockConverse(
            model=model_id,
            region_name=self.settings.aws_region,
            temperature=LLM_TEMPERATURE,   # shared constant — 0.2 for all generators
            max_tokens=max_tokens,
        )
        self._clients[cache_key] = client
        return client

    def invoke_json(
        self,
        *,
        prompt: str,
        model_id: str,
        retries: int = MAX_LLM_RETRIES,
        max_tokens: int = 1200,
    ) -> dict[str, Any]:
        """Send a prompt to Bedrock and return the raw text response.

        Retries the call with exponential back-off on any exception.

        Args:
            prompt:     The full instruction/user-turn string to send.
            model_id:   Bedrock model identifier.
            retries:    Maximum number of attempts (default: ``MAX_LLM_RETRIES``).
            max_tokens: Maximum tokens for this specific call.

        Returns:
            ``{"text": <model_output_str>, "raw": <response_metadata_dict>}``

        Raises:
            The last exception from Bedrock if all retry attempts are exhausted.
        """
        for attempt in range(retries):
            try:
                # Capture start time for Langfuse latency tracking
                start_time = datetime.datetime.now(datetime.timezone.utc)
                # Invoke the language model with a single human-turn message
                response = self._get_client(model_id, max_tokens).invoke(
                    [HumanMessage(content=prompt)],
                )
                content = response.content

                # Normalise the response content to a plain string
                if isinstance(content, str):
                    text = content
                else:
                    # Content may be a list of typed blocks (text/tool_use etc.)
                    blocks = [b.get("text", "") for b in content if isinstance(b, dict)]
                    text = "".join(blocks)

                record_generation(
                    prompt=prompt,
                    model_id=model_id,
                    output=text,
                    usage_metadata=response.usage_metadata,
                    max_tokens=max_tokens,
                    start_time=start_time,
                )
                # 1-second courtesy pause between consecutive LLM calls to avoid
                # hitting Bedrock rate limits when multiple calls are made in quick
                # succession within a single pipeline step.
                time.sleep(1)
                return {"text": text, "raw": response.response_metadata}

            except Exception as exc:
                is_last = attempt == retries - 1
                if is_last:
                    logger.error("Bedrock invoke failed after %d retries", retries, exc_info=True)
                    raise
                # Exponential back-off: 2s, 4s, 8s, …
                wait = 2 ** (attempt + 1)
                logger.warning(
                    "Bedrock invoke retry attempt=%d/%d wait=%ds error=%s",
                    attempt + 1,
                    retries,
                    wait,
                    exc,
                )
                time.sleep(wait)

        # This line is unreachable — the last iteration always raises or returns.
        raise RuntimeError("Bedrock invocation failed unexpectedly")
