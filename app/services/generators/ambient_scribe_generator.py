"""
app.services.generators.ambient_scribe_generator — Step 3 ambient scribe generator.

PRD reference: Step 3

Generates a plain-text ``ambient_scribe.txt`` (SOC nursing assessment note) that is
consistent with the Step 2 referral packet.

Key rules (from PRD):
  - BIMS/PHQ keywords are PROHIBITED in the note — those assessments belong only in
    gap-answer sections.  The validator raises ValueError on any violation.
  - All 7 required section headers must appear in the output.
  - Output must be at least 400 characters long.
"""

from __future__ import annotations

from app.config.constants import (
    ARCHETYPE_CLINICAL_HINTS,
    ARCHETYPE_NURSING_CONTEXT,
    PROHIBITED_AMBIENT_KEYWORDS,
    REQUIRED_NURSING_SECTIONS,
)
from app.config.prompts import AMBIENT_SCRIBE_PROMPT_TEMPLATE
from app.services.llm.bedrock_client import BedrockClient


class AmbientScribeGenerator:
    """Generates Step 3 ambient scribe note via Bedrock."""

    def __init__(self) -> None:
        # Shared Bedrock client with per-model caching
        self.bedrock = BedrockClient()

    def generate(self, *, referral_text: str, metadata: dict, model_id: str, audit_context: str | None = None) -> str:
        """Generate ambient_scribe.txt from the referral packet and Step 1 metadata.

        Args:
            referral_text: Plain-text referral packet produced by Step 2.
            metadata:      Serialised Step 1 metadata dict.
            model_id:      Bedrock model ARN / short-name to use.
            audit_context: Optional conflict summary from a previous LLM audit run.

        Returns:
            Validated plain-text nursing assessment note string.

        Raises:
            ValueError: If the output contains prohibited keywords, is missing required
                        sections, or is unreasonably short.
        """
        archetype = metadata.get("archetype", "chf_exacerbation")
        # Load archetype-specific clinical and nursing context
        hints = ARCHETYPE_CLINICAL_HINTS.get(archetype, ARCHETYPE_CLINICAL_HINTS["chf_exacerbation"])
        nursing_ctx = ARCHETYPE_NURSING_CONTEXT.get(archetype, ARCHETYPE_NURSING_CONTEXT["chf_exacerbation"])

        prompt = self._build_prompt(referral_text, metadata, hints, nursing_ctx)
        if audit_context:
            prompt += f"\n\n{audit_context}"
        response = self.bedrock.invoke_json(
            prompt=prompt,
            model_id=model_id,
            max_tokens=3000,  # notes are ~600-900 words
        )
        scribe_text = response["text"].strip()
        return self._validate(scribe_text)

    def _build_prompt(
        self,
        referral_text: str,
        metadata: dict,
        hints: dict,
        nursing_ctx: dict,
    ) -> str:
        """Assemble the full Bedrock prompt for ambient scribe generation."""
        archetype = metadata.get("archetype", "chf_exacerbation")
        age_bracket = metadata.get("age_bracket", "75-84")
        gender = metadata.get("gender", "F")
        gender_full = "Female" if gender == "F" else "Male"
        comorbidity_count = metadata.get("comorbidity_count", 2)

        return AMBIENT_SCRIBE_PROMPT_TEMPLATE.format(
            referral_text=referral_text,
            archetype=archetype,
            age_bracket=age_bracket,
            gender_full=gender_full,
            comorbidity_count=comorbidity_count,
            vitals_context=nursing_ctx["vitals_context"],
            physical_focus=nursing_ctx["physical_focus"],
            adl_picture=nursing_ctx["adl_picture"],
            home_safety=nursing_ctx["home_safety"],
            typical_goal=nursing_ctx["typical_goal"],
            cognition_mood=nursing_ctx["cognition_mood"],
        )

    def _validate(self, scribe_text: str) -> str:
        """Validate the generated ambient scribe note.

        Raises:
            ValueError: If the text is too short, contains prohibited BIMS/PHQ keywords,
                        or is missing any of the 7 required section headers.
        """
        if len(scribe_text.strip()) < 400:
            raise ValueError(
                f"Ambient scribe output too short ({len(scribe_text)} chars) — "
                "likely a generation failure"
            )

        # Hard prohibition: BIMS and PHQ wording must never appear in the nurse note
        for keyword in PROHIBITED_AMBIENT_KEYWORDS:
            if keyword.lower() in scribe_text.lower():
                raise ValueError(
                    f"Ambient scribe contains prohibited keyword '{keyword}' — "
                    "BIMS/PHQ wording is reserved for gap-answer sections only. "
                    "Retrying generation."
                )

        # All 7 required section headers must be present (checked case-insensitively)
        missing = [sec for sec in REQUIRED_NURSING_SECTIONS if sec not in scribe_text.upper()]
        if missing:
            raise ValueError(
                f"Ambient scribe missing required sections: {missing}. "
                "All 7 sections must be present."
            )

        return scribe_text

    def generate_fix(
        self,
        *,
        referral_text: str,
        current_ambient_scribe_text: str,
        medication_list_json: str,
        gap_answers_json: str,
        oasis_gold_standard_json: str,
        audit_conflicts_text: str,
        model_id: str,
    ) -> str:
        """Produce a revised ambient_scribe.txt that resolves LLM audit conflicts.

        Uses the targeted AMBIENT_SCRIBE_FIX_PROMPT which shows all existing
        documents + the audit conflict summary and asks for a minimal revision.
        """
        from app.config.prompts import AMBIENT_SCRIBE_FIX_PROMPT
        prompt = AMBIENT_SCRIBE_FIX_PROMPT.format(
            referral_text=referral_text[:6000],
            current_ambient_scribe_text=current_ambient_scribe_text,
            medication_list_json=medication_list_json[:2000],
            gap_answers_json=gap_answers_json[:3000],
            oasis_gold_standard_json=oasis_gold_standard_json[:3000],
            audit_conflicts_text=audit_conflicts_text,
        )
        response = self.bedrock.invoke_json(
            prompt=prompt,
            model_id=model_id,
            max_tokens=3000,
        )
        scribe_text = response["text"].strip()
        return self._validate(scribe_text)
