"""
app.config.llm_config — LLM inference hyper-parameters.

Centralises all Bedrock / LangChain tuning knobs so they can be adjusted
without touching service or task code.
"""

# ── Temperature ───────────────────────────────────────────────────────────────
# temperature=0.2 gives mostly-deterministic but slightly varied outputs.
# Lower values → more consistent JSON structure; higher → more narrative variety.
LLM_TEMPERATURE: float = 0.2

# ── Max-token budgets (per LLM call) ─────────────────────────────────────────
# Short responses: metadata JSON, filter decisions, BIMS/PHQ-only batches
DEFAULT_MAX_TOKENS: int = 1200

# Medium responses: referral packets, ambient scribe, medication lists
MEDIUM_MAX_TOKENS: int = 3000

# Long responses: full referral packet, gap-answer batches, OASIS batches
LARGE_MAX_TOKENS: int = 4096

# ── Retry policy ─────────────────────────────────────────────────────────────
# Maximum number of Bedrock API call attempts before raising the last exception.
# Uses exponential back-off: wait = 2^(attempt+1) seconds between retries.
MAX_LLM_RETRIES: int = 4

# ── Celery queue names ────────────────────────────────────────────────────────
# Defined here alongside other pipeline constants so all step-to-queue
# mappings are visible in one place.
STEP1_QUEUE: str = "patient_generation.step1"
STEP2_QUEUE: str = "patient_generation.step2"
STEP3_QUEUE: str = "patient_generation.step3"
STEP4_QUEUE: str = "patient_generation.step4"
STEP5_QUEUE: str = "patient_generation.step5"
STEP6_QUEUE: str = "patient_generation.step6"
