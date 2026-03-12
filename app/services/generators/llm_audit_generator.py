"""
app.services.generators.llm_audit_generator — Step 8 LLM cross-document consistency audit.

For every OASIS field in oasis_gold_standard.json this generator asks Claude claude-opus-4-6 to:
  1. Find each field's value across all 5 generated documents (referral, scribe, meds,
     gap-answers, gold-standard).
  2. Detect conflicts where different documents imply different values.
  3. Explain the clinical reasoning behind the recorded OASIS value.

Fields are processed in batches of AUDIT_BATCH_SIZE to stay well within the context window
while minimising the total number of API calls.
"""

from __future__ import annotations

import json
import time

from app.config.llm_config import AUDIT_BATCH_SIZE, AUDIT_MAX_TOKENS
from app.config.prompts import LLM_AUDIT_PROMPT_TEMPLATE
from app.config.settings import get_settings
from app.services.llm.bedrock_client import BedrockClient
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Keys injected into every artifact — not OASIS fields.
_SKIP_KEYS = frozenset({"_synthetic_label", "_hip_score"})


def _condense_medication_list(medication_list: dict) -> str:
    """Extract a compact text summary of the medication list for the prompt."""
    try:
        # Layer 1 is the home medication list — most relevant for clinical context.
        layer1 = medication_list.get("layer1_home_medications", {})
        meds = layer1.get("medications", [])
        if not meds:
            # Fallback: try to get any list from the dict.
            for val in medication_list.values():
                if isinstance(val, list) and val:
                    meds = val
                    break
        lines = []
        for m in meds[:25]:  # cap at 25 to limit prompt size
            if isinstance(m, dict):
                name = m.get("name") or m.get("medication_name") or str(m)
                dose = m.get("dose") or m.get("dosage") or ""
                lines.append(f"- {name} {dose}".strip())
            else:
                lines.append(f"- {m}")
        return "\n".join(lines) if lines else json.dumps(medication_list, indent=2)[:2000]
    except Exception:
        return json.dumps(medication_list, indent=2)[:2000]


def _condense_gap_answers(gap_answers: dict) -> str:
    """Flatten gap_answers sections into a compact field_code → answer map."""
    flat: dict[str, object] = {}
    try:
        sections = gap_answers.get("sections", [])
        for section in sections:
            for q in section.get("questions", []):
                codes = q.get("field_codes", [])
                answer = q.get("answer")
                if answer is None:
                    continue
                for code in codes:
                    flat[code.upper()] = answer
    except Exception:
        pass
    if not flat:
        # Legacy flat format
        for k, v in gap_answers.items():
            if k.startswith("_"):
                continue
            flat[k.upper()] = v
    return json.dumps(flat, indent=2)[:4000]


class LlmAuditGenerator:
    """Generates Step 8 LLM cross-document consistency audit report via Bedrock (Claude claude-opus-4-6)."""

    def __init__(self) -> None:
        self.bedrock = BedrockClient()
        self._audit_model_id = get_settings().llm_audit_model_id

    def generate(
        self,
        *,
        referral_text: str,
        ambient_scribe_text: str,
        medication_list: dict,
        gap_answers: dict,
        gold_standard: dict,
    ) -> dict:
        """Run the cross-document consistency audit for all OASIS fields.

        Args:
            referral_text:       Contents of referral_packet.txt.
            ambient_scribe_text: Contents of ambient_scribe.txt (empty string if not generated).
            medication_list:     Parsed medication_list.json.
            gap_answers:         Parsed tap_tap_gap_answers.json.
            gold_standard:       Parsed oasis_gold_standard.json.

        Returns:
            Audit report dict ready to be serialised as llm_audit_report.json.
        """
        # ── Extract auditable OASIS fields ────────────────────────────────────
        oasis_fields = {
            k: v
            for k, v in gold_standard.items()
            if k not in _SKIP_KEYS and not k.startswith("_")
        }

        # ── Pre-compute condensed doc summaries (shared across all batches) ───
        condensed_meds = _condense_medication_list(medication_list)
        condensed_gaps = _condense_gap_answers(gap_answers)

        # ── Batch the fields ──────────────────────────────────────────────────
        field_items = list(oasis_fields.items())
        batches = [
            dict(field_items[i : i + AUDIT_BATCH_SIZE])
            for i in range(0, len(field_items), AUDIT_BATCH_SIZE)
        ]

        logger.info(
            "LLM audit: auditing %d fields in %d batches (model=%s)",
            len(oasis_fields),
            len(batches),
            self._audit_model_id,
        )

        all_findings: list[dict] = []
        for batch_idx, batch in enumerate(batches):
            logger.info(
                "LLM audit batch %d/%d: %d fields",
                batch_idx + 1,
                len(batches),
                len(batch),
            )
            prompt = LLM_AUDIT_PROMPT_TEMPLATE.format(
                fields_batch_json=json.dumps(batch, indent=2),
                referral_text=referral_text[:6000],
                ambient_scribe_text=ambient_scribe_text[:4000] if ambient_scribe_text else "",
                medication_list_json=condensed_meds,
                gap_answers_json=condensed_gaps,
            )
            response = self.bedrock.invoke_json(
                prompt=prompt,
                model_id=self._audit_model_id,
                max_tokens=AUDIT_MAX_TOKENS,
            )
            batch_findings = self._parse_batch_response(response["text"], batch)
            all_findings.extend(batch_findings)
            if batch_idx < len(batches) - 1:
                time.sleep(1)

        # ── Assemble final report ─────────────────────────────────────────────
        fields_with_conflicts = [f for f in all_findings if f.get("conflict_detected")]
        fields_consistent = [f for f in all_findings if not f.get("conflict_detected")]

        return {
            "audit_status": "conflicts_found" if fields_with_conflicts else "all_consistent",
            "fields_audited": len(all_findings),
            "fields_consistent": len(fields_consistent),
            "fields_with_conflicts": len(fields_with_conflicts),
            "audit_findings": all_findings,
        }

    # ── Private helpers ───────────────────────────────────────────────────────

    def _parse_batch_response(self, raw_text: str, batch: dict) -> list[dict]:
        """Parse the LLM JSON array response for one batch.

        Falls back to skeleton entries (no LLM data) for any fields whose
        findings cannot be parsed, so a single malformed batch response does
        not abort the whole audit.
        """
        # Strip any accidental markdown fences.
        text = raw_text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(
                line for line in lines if not line.startswith("```")
            ).strip()

        try:
            findings = json.loads(text)
            if not isinstance(findings, list):
                raise ValueError("Expected JSON array, got %s" % type(findings).__name__)
            # Normalise field_code to uppercase.
            for f in findings:
                if isinstance(f, dict) and "field_code" in f:
                    f["field_code"] = str(f["field_code"]).upper()
            return findings
        except Exception as exc:
            logger.warning(
                "LLM audit: failed to parse batch response (%s); using skeleton fallback for %d fields",
                exc,
                len(batch),
            )
            # Return skeleton entries so no fields are silently dropped.
            return [
                {
                    "field_code": code.upper(),
                    "oasis_value": str(value) if value is not None else None,
                    "sources_found": [],
                    "conflict_detected": False,
                    "value_reasoning": "Audit parse error — LLM response could not be decoded for this batch.",
                }
                for code, value in batch.items()
            ]
