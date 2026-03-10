"""
app.services.generators.patient_metadata_generator — Step 1 generator.

Generates ``metadata.json`` for each synthetic patient record.

PRD reference: Step 1 / PRD 0D.1 metadata.json schema.

INPUT:  patient_external_id + model_id + hardcoded_seed
OUTPUT: GeneratedPatientMetadata Pydantic model (serialised to metadata.json by artifact_writer)

Flow:
  1. Build a prompt containing the full archetype → PDGM mapping.
  2. Invoke Bedrock; extract and parse the JSON response.
  3. Normalise the parsed payload to enforce all PRD constraints (enum values,
     booleans, integer comorbidity count, etc.).
  4. Validate against the Pydantic schema and return.
"""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from app.config.constants import APPROVED_ARCHETYPES, VALID_AGE_BRACKETS
from app.config.prompts import PATIENT_METADATA_PROMPT_TEMPLATE
from app.services.llm.bedrock_client import BedrockClient
from app.utils.json_utils import extract_json_object


class GeneratedPatientMetadata(BaseModel):
    """Exactly matches PRD section 0D.1 metadata.json schema — no extra fields."""

    patient_id: str
    source: Literal["PHASE_A", "PHASE_B", "PHASE_C"] = "PHASE_A"
    archetype: Literal[
        "total_knee_replacement",
        "chf_exacerbation",
        "diabetic_foot_ulcer",
        "cva_stroke_rehab",
        "hip_fracture",
        "copd_exacerbation",
        "sepsis_cellulitis_recovery",
        "patient_refuses_cannot_answer",
    ]
    pdgm_group: Literal[
        "MS_REHAB",
        "MMTA_CARDIAC",
        "WOUNDS",
        "NEURO_STROKE",
        "MMTA_RESPIRATORY",
        "MMTA_INFECTIOUS",
        "EDGE_CASE",
    ]
    admission_source: Literal["hospital", "community"]
    episode_timing: Literal["early", "late"]
    age_bracket: Literal["18-64", "65-74", "75-84", "85+"]
    gender: Literal["M", "F"]
    comorbidity_count: int = Field(ge=0)
    has_ambient_scribe: bool
    has_clinical_note: bool
    f2f_status: Literal["present_complete", "present_incomplete", "missing"]
    referral_format: Literal["clean_emr", "messy_fax", "minimal"]
    validation_status: Literal["passed", "failed", "pending"] = "pending"
    generated_by: str
    generated_date: str
    clinician_validated: bool = False


class PatientMetadataGenerator:
    """Generates Step 1 patient metadata via Bedrock, then normalises the output."""

    def __init__(self) -> None:
        # Shared Bedrock client instance (caches per model/token combination)
        self.bedrock = BedrockClient()

    def generate(
        self,
        *,
        patient_external_id: str,
        model_id: str,
        hardcoded_seed: str,
    ) -> GeneratedPatientMetadata:
        """Run Step 1 end-to-end: prompt → parse → normalise → validate.

        Args:
            patient_external_id: UUID or slug used as the ``patient_id`` field.
            model_id:            Bedrock model ARN / short-name to use.
            hardcoded_seed:      Variation seed injected into the prompt.

        Returns:
            A fully-validated :class:`GeneratedPatientMetadata` instance.
        """
        today = date.today().isoformat()
        # Build a compact prompt that lists the archetype ↔ PDGM mapping inline
        prompt = PATIENT_METADATA_PROMPT_TEMPLATE.format(
            patient_id=patient_external_id,
            today=today,
            seed=hardcoded_seed,
        )

        # Call the LLM and extract the text response
        response = self.bedrock.invoke_json(prompt=prompt, model_id=model_id)
        text = response["text"].strip()
        # Parse JSON and normalise to PRD spec before validating with Pydantic
        parsed = json.loads(extract_json_object(text))
        parsed = self._normalize_payload(parsed=parsed, patient_id=patient_external_id, today=today)
        return GeneratedPatientMetadata.model_validate(parsed)

    @staticmethod
    def _normalize_payload(*, parsed: dict, patient_id: str, today: str) -> dict:
        """Enforce all PRD constraints on the raw LLM output.

        Locks in PRD-fixed fields, coerces enum values to their canonical forms,
        and strips any spurious keys the LLM may have invented.

        Args:
            parsed:     Raw dict decoded from the LLM JSON response.
            patient_id: External patient UUID — always wins over LLM-provided value.
            today:      ISO date string for ``generated_date``.

        Returns:
            A clean dict ready for :class:`GeneratedPatientMetadata` validation.
        """
        out = dict(parsed or {})

        # PRD-fixed fields — never trust LLM values for these
        out["patient_id"] = patient_id
        out["source"] = "PHASE_A"
        out["validation_status"] = "pending"
        out["clinician_validated"] = False
        out["generated_date"] = today

        # Normalise archetype: lower-case and space→underscore; fuzzy match if needed
        archetype_raw = str(out.get("archetype", "")).strip().lower().replace(" ", "_").replace("-", "_")
        if archetype_raw not in APPROVED_ARCHETYPES:
            # Attempt a partial-match fallback (handles minor LLM paraphrasing)
            for approved in APPROVED_ARCHETYPES:
                if approved in archetype_raw or archetype_raw in approved:
                    archetype_raw = approved
                    break
            else:
                archetype_raw = "chf_exacerbation"  # safe default
        out["archetype"] = archetype_raw

        # pdgm_group is derived deterministically from archetype — always consistent
        out["pdgm_group"] = APPROVED_ARCHETYPES[out["archetype"]]

        # Normalise gender to single-letter "M" / "F"
        gender_raw = str(out.get("gender", "")).strip().upper()
        out["gender"] = "F" if gender_raw == "F" else "M"

        # Normalise age_bracket — strip dash variants, then range-bucket if unknown
        bracket_raw = str(out.get("age_bracket", "")).strip()
        bracket_norm = (
            bracket_raw
            .replace("–", "-")   # en-dash → hyphen
            .replace("—", "-")   # em-dash → hyphen
            .replace(" ", "")
        )
        if bracket_norm not in VALID_AGE_BRACKETS:
            try:
                lo = int(re.match(r"^(\d+)", bracket_norm).group(1))
                if lo < 65:
                    bracket_norm = "18-64"
                elif lo < 75:
                    bracket_norm = "65-74"
                elif lo < 85:
                    bracket_norm = "75-84"
                else:
                    bracket_norm = "85+"
            except (AttributeError, ValueError):
                bracket_norm = "75-84"
        out["age_bracket"] = bracket_norm

        # Normalise referral_format enum
        fmt_raw = str(out.get("referral_format", "")).strip().lower()
        if fmt_raw not in {"clean_emr", "messy_fax", "minimal"}:
            if any(k in fmt_raw for k in ["fax", "messy", "handwritten", "scanned"]):
                fmt_raw = "messy_fax"
            elif any(k in fmt_raw for k in ["minimal", "brief", "sparse"]):
                fmt_raw = "minimal"
            else:
                fmt_raw = "clean_emr"
        out["referral_format"] = fmt_raw

        # Normalise f2f_status enum
        f2f_raw = str(out.get("f2f_status", "")).strip().lower().replace(" ", "_")
        if f2f_raw not in {"present_complete", "present_incomplete", "missing"}:
            f2f_raw = "present_complete"
        out["f2f_status"] = f2f_raw

        # Normalise admission_source and episode_timing enums
        src_raw = str(out.get("admission_source", "")).strip().lower()
        out["admission_source"] = "hospital" if src_raw == "hospital" else "community"
        timing_raw = str(out.get("episode_timing", "")).strip().lower()
        out["episode_timing"] = "early" if timing_raw == "early" else "late"

        # Coerce booleans (LLM may emit "true"/"false" strings)
        out["has_ambient_scribe"] = bool(out.get("has_ambient_scribe", False))
        out["has_clinical_note"] = bool(out.get("has_clinical_note", False))

        # Coerce comorbidity_count to int
        try:
            out["comorbidity_count"] = int(out.get("comorbidity_count", 0))
        except (TypeError, ValueError):
            out["comorbidity_count"] = 0

        # Strip any extra keys the LLM may have added (strict PRD 0D.1 schema)
        allowed = {
            "patient_id", "source", "archetype", "pdgm_group", "admission_source",
            "episode_timing", "age_bracket", "gender", "comorbidity_count",
            "has_ambient_scribe", "has_clinical_note", "f2f_status", "referral_format",
            "validation_status", "generated_by", "generated_date", "clinician_validated",
        }
        for key in list(out.keys()):
            if key not in allowed:
                del out[key]

        # Fallback for generated_by if the LLM omitted it
        if not out.get("generated_by"):
            out["generated_by"] = "claude-sonnet"

        return out
