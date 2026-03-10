"""
app.services.generators.referral_packet_generator — Step 2 referral document generator.

PRD reference: Step 2

Generates a plain-text ``referral_packet.txt`` driven by Step 1 metadata.

The prompt is heavily grounded with per-archetype ICD-10 hints and high-risk
medication lists imported from ``app.config.constants``.  Three distinct output
formats (clean_emr / messy_fax / minimal) are controlled by the
``REFERRAL_FORMAT_INSTRUCTIONS`` constant.
"""

from __future__ import annotations

import re

from app.config.constants import ARCHETYPE_CLINICAL_HINTS, REFERRAL_FORMAT_INSTRUCTIONS
from app.config.pdgm_icd_loader import format_validated_codes_block
from app.config.prompts import REFERRAL_PACKET_PROMPT_TEMPLATE
from app.services.llm.bedrock_client import BedrockClient


class ReferralPacketGenerator:
    """Generates Step 2 referral packet text via Bedrock."""

    def __init__(self) -> None:
        # Shared Bedrock client with per-model caching
        self.bedrock = BedrockClient()

    def generate(self, *, metadata: dict, model_id: str) -> str:
        """Generate a plain-text referral_packet.txt from Step 1 metadata.

        Args:
            metadata: Serialised :class:`GeneratedPatientMetadata` dict (Step 1 output).
            model_id: Bedrock model ARN / short-name to use.

        Returns:
            The raw referral text string (written to disk by artifact_writer).

        Raises:
            ValueError: If the generated referral is missing ICD-10 codes or is too short.
        """
        archetype = metadata.get("archetype", "chf_exacerbation")
        # Retrieve archetype-specific ICD-10 / medication / service hints
        hints = ARCHETYPE_CLINICAL_HINTS.get(archetype, ARCHETYPE_CLINICAL_HINTS["chf_exacerbation"])
        referral_format = metadata.get("referral_format", "clean_emr")
        # Format instruction string injected at the top of the prompt
        format_instruction = REFERRAL_FORMAT_INSTRUCTIONS.get(
            referral_format, REFERRAL_FORMAT_INSTRUCTIONS["clean_emr"]
        )
        f2f_status       = metadata.get("f2f_status", "present_complete")
        age_bracket      = metadata.get("age_bracket", "75-84")
        gender           = metadata.get("gender", "F")
        episode_timing   = metadata.get("episode_timing", "early")
        admission_source = metadata.get("admission_source", "hospital")
        comorbidity_count = metadata.get("comorbidity_count", 2)

        f2f_instruction = self._f2f_instruction(f2f_status)
        age_hint = self._age_from_bracket(age_bracket)
        gender_full = "Female" if gender == "F" else "Male"
        # Format high-risk med list as a plain block of text
        high_risk_section = (
            "\n".join(hints["high_risk_meds"]) if hints["high_risk_meds"] else "(none specific)"
        )

        admission_source_desc = (
            "a hospital" if admission_source == "hospital" else "the community / home setting"
        )
        episode_timing_desc = (
            "days 0-29 — Start of Care episode"
            if episode_timing == "early"
            else "days 30+ — recertification episode"
        )
        secondary_hints_text = "\n".join(
            f"    - {h}" for h in hints["secondary_hints"][:max(comorbidity_count, 2)]
        )

        # Build CMS-verified primary DX code block from the PDGM ICD-10 reference CSV.
        # This constrains the LLM to real, valid codes and catches coding-rule violations
        # (e.g. CHF I50.xx codes require CODE_FIRST — loader surfaces safe alternatives).
        validated_codes_section = format_validated_codes_block(archetype)

        prompt = REFERRAL_PACKET_PROMPT_TEMPLATE.format(
            format_instruction=format_instruction,
            archetype=archetype,
            pdgm_group=metadata.get("pdgm_group", ""),
            age_hint=age_hint,
            gender_full=gender_full,
            admission_source=admission_source,
            admission_source_desc=admission_source_desc,
            episode_timing=episode_timing,
            episode_timing_desc=episode_timing_desc,
            comorbidity_count=comorbidity_count,
            primary_hint=hints["primary_hint"],
            secondary_hints_text=secondary_hints_text,
            validated_codes_section=validated_codes_section,
            high_risk_section=high_risk_section,
            services_hint=hints["services"],
            homebound_reason=hints["homebound_reason"],
            f2f_instruction=f2f_instruction,
        )

        response = self.bedrock.invoke_json(
            prompt=prompt,
            model_id=model_id,
            max_tokens=4096,  # referral packets can be long
        )
        text = response["text"].strip()
        self._validate(text)
        return text

    @staticmethod
    def _f2f_instruction(f2f_status: str) -> str:
        """Build the F2F section instruction based on the metadata f2f_status field."""
        if f2f_status == "present_complete":
            return (
                "Include a complete Face-to-Face Encounter section. "
                "Content: physician name, date of encounter (before SOC date), "
                "clinical statement confirming homebound status and skilled care need, "
                "physician signature. Must be clearly dated and signed."
            )
        elif f2f_status == "present_incomplete":
            return (
                "Include a Face-to-Face Encounter section but make it INCOMPLETE. "
                "For example: physician name and date present but the clinical narrative is "
                "missing or the signature line is blank. Do NOT include a complete statement."
            )
        else:  # missing — tests system handling of absent F2F for Medicare compliance
            return (
                "Do NOT include a Face-to-Face Encounter section at all. "
                "The referral should have no F2F documentation — this tests the system's "
                "handling of missing F2F for Medicare compliance."
            )

    @staticmethod
    def _age_from_bracket(age_bracket: str) -> int:
        """Convert an age bracket string to an approximate midpoint integer."""
        m = re.match(r"^(\d+)[-–](\d+)$", age_bracket)
        if m:
            return (int(m.group(1)) + int(m.group(2))) // 2
        if "85" in age_bracket:
            return 88
        return 75

    @staticmethod
    def _validate(text: str) -> None:
        """Light validation — referral must contain an ICD-10-like code and be non-trivially short."""
        if not re.search(r"[A-Z]\d{2}\.\w+", text):
            raise ValueError("Generated referral contains no valid ICD-10 code pattern")
        if len(text) < 200:
            raise ValueError(f"Generated referral is too short ({len(text)} chars) — likely incomplete")
