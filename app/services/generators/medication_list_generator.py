"""
app.services.generators.medication_list_generator — Step 2 (medication) generator.

PRD reference: PRD 0A.5

Generates ``medication_list.json`` containing three clinically realistic medication
layers with four mandatory reconciliation discrepancies.

Three layers:
    hospital_discharge_list — extracted from the referral packet's discharge med section (Layer 1)
    patient_pill_bottles    — what was physically found at the patient's home (Layer 2)
    patient_reported_otc    — supplements/OTCs the patient self-reports (Layer 3)

Four required discrepancies:
    1. missing_at_home          — one high-risk med absent from pill bottles
    2. wrong_dose_bottle        — one bottle dose differs from discharge prescription
    3. otc_not_on_list          — patient reports a supplement not on any official list
    4. dose_discrepancy_layers  — patient-reported dose differs from bottle label
"""

from __future__ import annotations

import json

from app.config.prompts import MEDICATION_LIST_PROMPT_TEMPLATE
from app.services.llm.bedrock_client import BedrockClient
from app.utils.json_utils import extract_json_object


class MedicationListGenerator:
    """Generates Step 2 medication_list.json via Bedrock."""

    def __init__(self) -> None:
        # Shared Bedrock client with per-model caching
        self.bedrock = BedrockClient()

    def generate(self, *, referral_text: str, metadata: dict, model_id: str) -> dict:
        """Generate a medication_list.json dict from the referral packet text.

        Args:
            referral_text: Plain-text referral packet produced by Step 2.
            metadata:      Serialised Step 1 metadata dict.
            model_id:      Bedrock model ARN / short-name to use.

        Returns:
            A validated dict ready for JSON serialisation (written by artifact_writer).

        Raises:
            ValueError: If required keys or discrepancy types are missing from the output.
        """
        archetype = metadata.get("archetype", "chf_exacerbation")
        prompt = self._build_prompt(referral_text=referral_text, archetype=archetype)

        response = self.bedrock.invoke_json(
            prompt=prompt,
            model_id=model_id,
            max_tokens=4096,  # medication lists can be verbose
        )
        text = response["text"].strip()
        # Extract and parse the JSON object from the LLM response
        raw = json.loads(extract_json_object(text))
        return self._validate_and_normalise(raw)

    @staticmethod
    def _build_prompt(*, referral_text: str, archetype: str) -> str:
        """Assemble the Bedrock prompt for medication list generation."""
        return MEDICATION_LIST_PROMPT_TEMPLATE.format(
            referral_text=referral_text,
            archetype=archetype,
        )

    @staticmethod
    def _validate_and_normalise(raw: dict) -> dict:
        """Verify that all required layers and discrepancy types are present.

        Args:
            raw: Parsed dict from the LLM JSON response.

        Returns:
            The same dict if validation passes.

        Raises:
            ValueError: On any structural validation failure.
        """
        required_keys = {
            "hospital_discharge_list",
            "patient_pill_bottles",
            "patient_reported_otc",
            "reconciliation_issues",
        }
        missing = required_keys - raw.keys()
        if missing:
            raise ValueError(f"medication_list.json missing required keys: {missing}")

        # Ensure each layer is a non-empty list
        for layer_key in ("hospital_discharge_list", "patient_pill_bottles", "patient_reported_otc"):
            if not isinstance(raw[layer_key], list):
                raise ValueError(f"Layer '{layer_key}' must be a list")
            if not raw[layer_key]:
                raise ValueError(f"Layer '{layer_key}' must not be empty")

        # Ensure the reconciliation_issues list has at least 4 entries
        if not isinstance(raw["reconciliation_issues"], list) or len(raw["reconciliation_issues"]) < 4:
            raise ValueError(
                f"reconciliation_issues must contain at least 4 discrepancies, "
                f"got {len(raw.get('reconciliation_issues', []))}"
            )

        # Verify all four mandatory discrepancy types are present
        required_discrepancy_types = {
            "missing_at_home",
            "wrong_dose_bottle",
            "otc_not_on_list",
            "dose_discrepancy_layers",
        }
        found_types = {issue.get("discrepancy_type") for issue in raw["reconciliation_issues"]}
        missing_types = required_discrepancy_types - found_types
        if missing_types:
            raise ValueError(
                f"reconciliation_issues missing required discrepancy types: {missing_types}"
            )

        return raw
