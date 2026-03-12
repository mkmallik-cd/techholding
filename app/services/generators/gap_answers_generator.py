"""
app.services.generators.gap_answers_generator — Step 4 gap answers generator.

PRD reference: Step 4

Generates ``tap_tap_gap_answers.json``: a record of OASIS field code answers grouped into
clinical sections per PRD Section 6.

INPUT:   referral_packet.txt + ambient_scribe.txt (optional) + Step 1 archetype metadata
OUTPUT:
  {
    "_synthetic_label": "SYNTHETIC — NOT REAL PATIENT DATA",
    "sections": [
      {
        "section": "<Section Name>",
        "questions": [
          {
            "id": "<field_code_lower>",
            "title": "<question text>",
            "type": "radio|checkbox|text",
            "field_codes": ["<CODE>"],
            "answer": <value>,
            "why_gap": "Requires in-person nurse observation"
          },
          ...
        ]
      },
      ...
    ],
    "fields_auto_extracted": {
      "from_referral": [],
      "from_scribe": [],
      "from_medications": []
    }
  }

Flow:
    Phase 2 (Filter): Start from 130+ gap field codes; filter to codes NOT answerable from
                      referral + scribe.  Add union with MANDATORY codes (BIMS, PHQ-9, GG).
    Phase 3 (Answer): Generate clinically consistent answers for remaining codes in batches.
    Post-validation:  Verify BIMS arithmetic (C0500 = sum of sub-scores).
                      Verify PHQ-9 total (D0160 = sum of Column 2 frequency scores).

PRD rules:
    - BIMS (C0200–C0500) always included — requires live cognitive testing
    - PHQ-2/9 (D0150–D0160) always included — requires live mood interview
    - All GG discharge goals always included — require clinical judgment
    - Wound codes included for wound-bearing archetypes only
"""

from __future__ import annotations

import json

from app.config.constants import (
    ALL_GAP_FIELD_CODES,
    BIMS_MANDATORY,
    BIMS_SUB_CODES,
    BIMS_TOTAL_CODE,
    GG_MANDATORY,
    PHASE3_BATCH_SIZE,
    PHQ_FREQUENCY_CODES,
    PHQ_MANDATORY,
    WOUND_ARCHETYPES,
    WOUND_CODES,
)
from app.config.oasis_field_map import OASIS_FIELD_MAP
from app.services.llm.bedrock_client import BedrockClient
from app.config.prompts import GAP_ANSWER_PROMPT_TEMPLATE, GAP_FILTER_PROMPT_TEMPLATE
from app.utils.json_utils import extract_json_object, repair_truncated_json
from app.utils.logger import get_logger

logger = get_logger(__name__)

# ── Section grouping rules ─────────────────────────────────────────────────────

_SECTION_ORDER = [
    "Cognitive",
    "Mood",
    "Functional - Self Care",
    "Functional - Mobility",
    "ADL",
    "Medications",
    "Clinical",
]


def _code_to_section(code: str) -> str:
    """Map an OASIS field code to its clinical section label."""
    if code.startswith("C"):
        return "Cognitive"
    if code.startswith("D"):
        return "Mood"
    if code == "GG0130":
        return "Functional - Self Care"
    if code == "GG0170" or code.startswith("GG0170") or code.startswith("GG0100") or code.startswith("GG0110"):
        return "Functional - Mobility"
    if code.startswith("GG"):
        return "Functional - Self Care"
    if code.startswith("M18") or code.startswith("M19"):
        return "ADL"
    if code.startswith("N"):
        return "Medications"
    return "Clinical"


def _derive_answer_type(code: str) -> str:
    """Derive the answer widget type for a given OASIS code."""
    meta = OASIS_FIELD_MAP.get(code)
    if meta is None:
        return "text"
    data_type = meta.get("dataType", "text")
    if data_type == "enum":
        return "radio"
    if data_type == "array":
        return "checkbox"
    return "text"


def _build_sections(unanswered: dict) -> list[dict]:
    """Convert a flat unanswered_response dict into the PRD sections array format.

    Args:
        unanswered: Flat dict keyed {CODE: {question, answer}}.

    Returns:
        List of section dicts, each with 'section' and 'questions' keys.
        Sections are ordered per _SECTION_ORDER; within each section codes
        preserve their original iteration order.
    """
    from app.config.constants import (
        GG0130_LABEL_TO_LETTER,
        GG0170_KEY_TO_LETTER,
    )

    buckets: dict[str, list[dict]] = {s: [] for s in _SECTION_ORDER}

    for code, entry in unanswered.items():
        if not isinstance(entry, dict):
            continue
        
        section_name = _code_to_section(code)
        meta = OASIS_FIELD_MAP.get(code)
        base_title = (
            meta["question"]
            if meta and meta.get("question")
            else entry.get("question", code)
        )
        answer = entry.get("answer")

        # PRD 2.2 Formatting Fix:
        # If the LLM returned a dictionary for grouped codes like GG0130, GG0170, or GG0100, 
        # we must flatten it into individual questions with specific field codes and string answers.
        # This occurs because these codes are grouped during generation to save prompt space.
        if isinstance(answer, dict) and code.startswith("GG"):
            for sub_key, sub_val in answer.items():
                if not isinstance(sub_val, str):
                    sub_val = str(sub_val)

                sub_code = code
                if code == "GG0130":
                    letter_hint = GG0130_LABEL_TO_LETTER.get(sub_key, GG0130_LABEL_TO_LETTER.get(sub_key.title()))
                    if letter_hint:
                        if isinstance(letter_hint, list):
                            # e.g., "Dressing" -> both D and E. Add D now, E manually below or loop
                            for l in letter_hint:
                                specific_code = f"GG0130{l}1" # 1 = Admission Performance for 0130 grouped
                                q_entry = {
                                    "id": specific_code.lower(),
                                    "title": f"{base_title} - {sub_key}",
                                    "type": _derive_answer_type(specific_code),
                                    "field_codes": [specific_code],
                                    "answer": sub_val,
                                    "why_gap": "Requires in-person nurse observation",
                                }
                                buckets[section_name].append(q_entry)
                            continue
                        else:
                            sub_code = f"GG0130{letter_hint}1"
                elif code == "GG0170":
                    letter_hint = GG0170_KEY_TO_LETTER.get(sub_key, GG0170_KEY_TO_LETTER.get(sub_key.title()))
                    if letter_hint:
                        # For GG0170 grouped, we assume 1 (Admission Performance) unless the answer has 2 elements?
                        # Since gap primarily documents admission, we default to 1 for structured answers unless specified.
                        # Typically the LLM returns individual specific goals too (like GG0170C2), so this grouped one is admission.
                        sub_code = f"GG0170{letter_hint}1"
                elif code == "GG0100":
                    mapping = {"self care": "A", "indoor mobility": "B", "stairs": "C", "functional cognition": "D"}
                    letter = mapping.get(str(sub_key).lower().strip())
                    if letter:
                        sub_code = f"GG0100{letter}"

                q_entry = {
                    "id": sub_code.lower(),
                    "title": f"{base_title} - {sub_key}",
                    "type": _derive_answer_type(sub_code),
                    "field_codes": [sub_code],
                    "answer": sub_val,
                    "why_gap": "Requires in-person nurse observation",
                }
                buckets[section_name].append(q_entry)
            continue # Skip adding the grouped object itself

        # Default behaviour for non-grouped or non-dict answers
        # IMPROVEMENT: If the code is generic (GG0130/GG0170/GG0100), try to resolve the specific sub-code from the title
        resolved_code = code
        if code in ["GG0130", "GG0170", "GG0100"]:
            # Helper for word-set matching
            def _words_match(label, title):
                # Skip single-letter keys or numeric keys which are ambiguous in titles
                if len(label.strip()) <= 2:
                    return False
                label_words = {w.lower() for w in label.split() if len(w) > 2}
                if not label_words: return False # Still skip if no significant words
                title_words = {w.lower() for w in title.replace("-", " ").replace("_", " ").split()}
                return label_words.issubset(title_words)

            if code == "GG0130":
                for label, letter in GG0130_LABEL_TO_LETTER.items():
                    if _words_match(label, base_title):
                        if isinstance(letter, str):
                            resolved_code = f"GG0130{letter}1"
                            break
                        elif isinstance(letter, list):
                            # Disambiguate Dressing
                            if "upper" in base_title.lower():
                                resolved_code = "GG0130D1"
                            elif "lower" in base_title.lower():
                                resolved_code = "GG0130E1"
                            else:
                                resolved_code = f"GG0130{letter[0]}1"
                            break
            elif code == "GG0170":
                for label, letter in GG0170_KEY_TO_LETTER.items():
                    # Check descriptive label first
                    if _words_match(label.replace("_", " "), base_title):
                        resolved_code = f"GG0170{letter}1"
                        break
            elif code == "GG0100":
                mapping = {"self care": "A", "indoor mobility": "B", "stairs": "C", "functional cognition": "D"}
                for label, letter in mapping.items():
                    if label.lower() in base_title.lower():
                        resolved_code = f"GG0100{letter}"
                        break

        question_entry = {
            "id": resolved_code.lower(),
            "title": base_title,
            "type": _derive_answer_type(resolved_code),
            "field_codes": [resolved_code],
            "answer": answer,
            "why_gap": "Requires in-person nurse observation",
        }
        buckets[section_name].append(question_entry)

    return [
        {"section": section_name, "questions": questions}
        for section_name in _SECTION_ORDER
        if (questions := buckets[section_name])
    ]


def _get_mandatory_codes(archetype: str) -> set[str]:
    """Return the set of OASIS codes that must always appear in gap_answers regardless of docs."""
    codes: set[str] = set(BIMS_MANDATORY) | set(PHQ_MANDATORY) | set(GG_MANDATORY)
    # Wound-specific codes only for wound-bearing archetypes
    if archetype in WOUND_ARCHETYPES:
        codes |= set(WOUND_CODES)
    return codes


class GapAnswersGenerator:
    """Generates Step 4 OASIS gap answers via a two-phase Bedrock pipeline."""

    def __init__(self) -> None:
        # Shared Bedrock client with per-model caching
        self.bedrock = BedrockClient()

    def generate(
        self,
        *,
        referral_text: str,
        metadata: dict,
        scribe_text: str | None = None,
        model_id: str,
    ) -> dict:
        """Run Step 4 end-to-end: filter → answer → validate.

        Args:
            referral_text: Plain-text referral packet.
            metadata:      Serialised Step 1 metadata dict.
            scribe_text:   Optional ambient scribe note text.
            model_id:      Bedrock model ARN / short-name to use.

        Returns:
            ``{"unanswered_response": {code: {question, answer}, ...}, "status": "draft"}``
        """
        archetype = metadata.get("archetype", "chf_exacerbation")

        # Phase 2: determine which codes are answerable from existing documents
        remaining_codes = self._filter_answerable_codes(
            referral_text=referral_text,
            scribe_text=scribe_text,
            archetype=archetype,
            model_id=model_id,
        )
        logger.info(
            "Step 4 Phase 2 complete: %d gap codes remaining (from %d total), archetype=%s",
            len(remaining_codes),
            len(ALL_GAP_FIELD_CODES),
            archetype,
        )

        # Phase 3: generate clinically consistent answers for remaining codes
        unanswered_response = self._generate_answers(
            remaining_codes=remaining_codes,
            referral_text=referral_text,
            scribe_text=scribe_text,
            metadata=metadata,
            model_id=model_id,
        )
        logger.info(
            "Step 4 Phase 3 complete: %d answers generated, archetype=%s",
            len(unanswered_response),
            archetype,
        )

        # Post-validate and fix BIMS arithmetic (C0500 = sum of sub-scores)
        unanswered_response = self._validate_and_fix_bims(unanswered_response)
        # Post-validate and fix PHQ-9 total (D0160 = sum of Column 2 frequencies)
        unanswered_response = self._validate_and_fix_phq(unanswered_response)

        return {
            "_synthetic_label": "SYNTHETIC — NOT REAL PATIENT DATA",
            "sections": _build_sections(unanswered_response),
            "fields_auto_extracted": {
                "from_referral": [],
                "from_scribe": [],
                "from_medications": [],
            },
        }

    def _filter_answerable_codes(
        self,
        *,
        referral_text: str,
        scribe_text: str | None,
        archetype: str,
        model_id: str,
    ) -> list[str]:
        """Phase 2: identify gap codes that are NOT answerable from existing documents.

        Returns a list of codes that require live clinician assessment (the "gap").
        """
        mandatory_codes = _get_mandatory_codes(archetype)

        scribe_section = (
            f"--- AMBIENT SCRIBE (Nurse Visit Note) ---\n{scribe_text}"
            if scribe_text
            else "(No ambient scribe available for this patient)"
        )

        filter_prompt = GAP_FILTER_PROMPT_TEMPLATE.format(
            referral_text=referral_text,
            scribe_section=scribe_section,
            field_codes_json=json.dumps(ALL_GAP_FIELD_CODES, indent=2),
        )

        try:
            filter_response = self.bedrock.invoke_json(
                prompt=filter_prompt,
                model_id=model_id,
                max_tokens=2048,
            )
            raw = json.loads(extract_json_object(filter_response["text"]))
            answerable: set[str] = set(raw.get("answerable_codes") or [])
        except Exception as exc:
            # If the filter fails, proceed conservatively with all gap codes
            logger.warning(
                "Step 4 Phase 2 filter LLM failed (%s) — proceeding with all gap codes", exc
            )
            answerable = set()

        # Mandatory codes can never be "answered" from documents alone
        answerable -= mandatory_codes

        # Build remaining list preserving original order; append mandatory extras
        remaining: list[str] = [c for c in ALL_GAP_FIELD_CODES if c not in answerable]
        seen = set(remaining)
        for code in sorted(mandatory_codes):
            if code not in seen:
                remaining.append(code)
                seen.add(code)

        return remaining

    def _generate_answers(
        self,
        *,
        remaining_codes: list[str],
        referral_text: str,
        scribe_text: str | None,
        metadata: dict,
        model_id: str,
    ) -> dict:
        """Phase 3: generate answers for all remaining codes in parallel batches.

        Returns a flat dict keyed ``{code: {question, answer}}``.
        """
        archetype = metadata.get("archetype", "chf_exacerbation")
        diagnosis_context = metadata.get(
            "primary_diagnosis", archetype.replace("_", " ").title()
        )

        scribe_section = (
            f"--- AMBIENT SCRIBE (Nurse Visit Note) ---\n{scribe_text}"
            if scribe_text
            else "(No ambient scribe — use referral packet for all clinical context)"
        )

        # Split codes into batches to stay within LLM output size limits (~50 per call)
        batches = [
            remaining_codes[i : i + PHASE3_BATCH_SIZE]
            for i in range(0, len(remaining_codes), PHASE3_BATCH_SIZE)
        ]
        logger.info(
            "Step 4 Phase 3: processing %d codes in %d batch(es), archetype=%s",
            len(remaining_codes),
            len(batches),
            archetype,
        )

        result: dict = {}
        for batch_idx, batch in enumerate(batches):
            logger.info(
                "Step 4 Phase 3: batch %d/%d (%d codes)",
                batch_idx + 1,
                len(batches),
                len(batch),
            )
            batch_result = self._generate_answers_batch(
                batch=batch,
                archetype=archetype,
                diagnosis_context=diagnosis_context,
                scribe_section=scribe_section,
                referral_text=referral_text,
                model_id=model_id,
            )
            result.update(batch_result)

        # Insert empty entries for any codes the LLM failed to return
        for code in remaining_codes:
            if code not in result:
                logger.warning(
                    "Step 4: no answer produced for code=%s — inserting empty placeholder", code
                )
                result[code] = {"question": code, "answer": ""}

        return result

    def _generate_answers_batch(
        self,
        *,
        batch: list[str],
        archetype: str,
        diagnosis_context: str,
        scribe_section: str,
        referral_text: str,
        model_id: str,
    ) -> dict:
        """Run one Phase 3 LLM call for a single batch of field codes."""
        # Build per-code metadata from the canonical OASIS field map
        fields_with_metadata = []
        for code in batch:
            meta = OASIS_FIELD_MAP.get(code)
            entry: dict = {"code": code}
            if meta:
                entry["question"] = meta["question"]
                entry["dataType"] = meta["dataType"]
                if meta["options"]:
                    entry["options"] = meta["options"]
            else:
                entry["question"] = code  # no template entry — LLM infers question text
            fields_with_metadata.append(entry)

        answer_prompt = GAP_ANSWER_PROMPT_TEMPLATE.format(
            archetype=archetype,
            diagnosis_context=diagnosis_context,
            has_ambient_scribe="Yes" if "AMBIENT SCRIBE" in scribe_section else "No",
            referral_text=referral_text,
            scribe_section=scribe_section,
            fields_with_metadata_json=json.dumps(fields_with_metadata, indent=2),
        )

        response = self.bedrock.invoke_json(
            prompt=answer_prompt,
            model_id=model_id,
            max_tokens=4096,
        )
        text = response["text"].strip()

        try:
            raw = json.loads(extract_json_object(text))
        except Exception as exc:
            # If clean extraction fails, attempt best-effort truncation repair
            logger.error(
                "Step 4 Phase 3 batch JSON parse failed (%s). Attempting truncation repair.", exc
            )
            raw = repair_truncated_json(text)

        # Normalise: retain only requested codes and attach canonical question text
        requested_set = set(batch)
        batch_result: dict = {}
        for code, value in raw.items():
            if not isinstance(value, dict):
                continue
            code_upper = code.strip().upper()
            if code_upper not in requested_set:
                continue
            template_meta = OASIS_FIELD_MAP.get(code_upper)
            question = (
                template_meta["question"]
                if template_meta
                else str(value.get("question") or code_upper)
            )
            batch_result[code_upper] = {
                "question": question,
                "answer": value.get("answer"),
            }

        return batch_result

    # ── Post-validation helpers ────────────────────────────────────────────────

    @staticmethod
    def _validate_and_fix_bims(unanswered_response: dict) -> dict:
        """Recalculate C0500 from sub-scores to guarantee BIMS arithmetic correctness.

        CMS rule: C0500 = C0200 + C0300A + C0300B + C0300C + C0400A + C0400B + C0400C (0–15).
        """
        sub_scores: dict[str, int] = {}
        all_present = True

        for code in BIMS_SUB_CODES:
            entry = unanswered_response.get(code)
            if not entry:
                all_present = False
                break
            try:
                # Answer may be "3 - all three words" or just "3" — take first token
                raw_val = str(entry.get("answer", "")).strip().split()[0]
                sub_scores[code] = int(raw_val)
            except (ValueError, TypeError, IndexError):
                all_present = False
                break

        if all_present and BIMS_TOTAL_CODE in unanswered_response:
            total = sum(sub_scores.values())
            existing = unanswered_response[BIMS_TOTAL_CODE]
            unanswered_response[BIMS_TOTAL_CODE] = {
                "question": existing.get("question", "BIMS Summary Score"),
                "answer": str(total),
            }
            logger.info("Step 4 BIMS validation: C0500 recalculated to %d", total)

        return unanswered_response

    @staticmethod
    def _validate_and_fix_phq(unanswered_response: dict) -> dict:
        """Recalculate D0160 from Column 2 frequency sub-scores.

        CMS rule: D0160 = sum(D0150A2 … D0150I2) — range 0–27.
        """
        freq_scores: dict[str, int] = {}
        all_present = True

        for code in PHQ_FREQUENCY_CODES:
            entry = unanswered_response.get(code)
            if not entry:
                all_present = False
                break
            try:
                raw_val = str(entry.get("answer", "")).strip().split()[0]
                freq_scores[code] = int(raw_val)
            except (ValueError, TypeError, IndexError):
                all_present = False
                break

        if all_present and "D0160" in unanswered_response:
            total = sum(freq_scores.values())
            existing = unanswered_response["D0160"]
            unanswered_response["D0160"] = {
                "question": existing.get("question", "PHQ-9 Total Severity Score"),
                "answer": str(total),
            }
            logger.info("Step 4 PHQ validation: D0160 recalculated to %d", total)

        return unanswered_response
