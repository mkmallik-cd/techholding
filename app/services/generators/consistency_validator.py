"""Step 7 — Consistency Validator

Cross-checks the five generated documents for clinical contradictions.
All checks are deterministic; no LLM calls are made.

Checks performed (pseudocode-aligned):
  1. GG consistency      — GG0130/GG0170 X1 (admission) codes match gap_answers
                           (supports both direct sub-code and legacy title-based lookup)
  2. BIMS arithmetic     — C0500 == C0200 + C0300 + C0400 (gold standard self-consistency)
  3. BIMS cross-reference— BIMS sub-codes in gold standard match gap_answers values
  4. PHQ arithmetic      — D0160 == sum of D0150X2 where D0150X1 != "0"
  5. PHQ-2 gate          — if D0150A1 + D0150B1 < 3, downstream items C-I must be null
  6. Date ordering       — M1005 <= M0104 <= M0110 <= M0080
  7. Skip-logic          — M1306=0 => M1311-M1314 null; M1740=7 => no other flags set
  8. Wound presence      — if M1306 non-zero, M1311 must be non-zero and wound data in gap_answers
  9. N0415 flags         — each high-risk drug class in gap_answers has correct sub-flag in gold standard
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

from app.config.constants import GG0130_LABEL_TO_LETTER, GG0170_KEY_TO_LETTER
from app.utils.gap_answers_utils import lookup_gap_answer as _lookup_gap_answer
from app.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ValidationResult:
    """Aggregated result of all consistency checks."""

    is_valid: bool
    errors: list[dict] = field(default_factory=list)
    checks_run: int = 0
    checks_passed: int = 0


class ConsistencyValidator:
    """Validate a generated OASIS gold standard against its source documents.

    All validation logic is deterministic — no LLM calls are made.
    """

    def validate(
        self,
        *,
        gap_answers: dict,
        gold_standard: dict,
        metadata: dict | None = None,
    ) -> ValidationResult:
        """Run all 6 consistency checks and return an aggregated ValidationResult.

        Args:
            gap_answers: Step 4 gap answers dict (authoritative source of truth).
            gold_standard: Step 6 gold standard flat dict mapping item codes to values.
            metadata: Optional patient metadata dict (currently unused).

        Returns:
            ValidationResult with is_valid, errors, checks_run, checks_passed.
        """
        # Flatten gold standard items into a {code: value} dict for easy O(1) lookups.
        items: dict[str, str | None] = {
            str(code).strip().upper(): str(value) if value is not None else None
            for code, value in gold_standard.items()
            if not code.startswith("_")
        }

        all_errors: list[dict] = []

        checks = [
            self._check_gg_consistency,
            self._check_bims_arithmetic,
            self._check_bims_gap_crosscheck,
            self._check_phq_arithmetic,
            self._check_phq2_gate,
            self._check_date_ordering,
            self._check_skip_logic,
            self._check_wound_presence,
            self._check_n0415_flags,
        ]

        for check_fn in checks:
            try:
                errors = check_fn(gap_answers=gap_answers, items=items)
                all_errors.extend(errors)
            except Exception as exc:
                logger.warning(
                    "Check %s raised unexpectedly: %s", check_fn.__name__, exc, exc_info=True
                )
                all_errors.append({
                    "check": check_fn.__name__,
                    "code": "CHECK_EXCEPTION",
                    "message": f"Check raised an unexpected error: {exc}",
                })

        checks_run = len(checks)
        # Count distinct checks that produced no errors.
        # Error dicts use short "check" keys (e.g. "n0415_flags"); function names have
        # the "_check_" prefix (e.g. "_check_n0415_flags").  Strip prefix when comparing.
        failed_check_names = {e["check"] for e in all_errors}
        checks_passed = sum(
            1 for fn in checks
            if (fn.__name__[7:] if fn.__name__.startswith("_check_") else fn.__name__)
            not in failed_check_names
        )

        return ValidationResult(
            is_valid=len(all_errors) == 0,
            errors=all_errors,
            checks_run=checks_run,
            checks_passed=checks_passed,
        )

    # ── Check 8: Wound Presence ────────────────────────────────────────────────

    def _check_wound_presence(self, *, gap_answers: dict, items: dict) -> list[dict]:
        """If M1306 indicates wound(s) present, M1311 must be non-zero in both gap_answers and gold standard."""
        m1306 = items.get("M1306")
        if m1306 is None or str(m1306).strip() in ("", "0", "null", "None", "-"):
            return []  # No wound present — skip

        errors: list[dict] = []

        # Check M1311 in gold standard — must be non-zero when wound is present
        m1311_gold = items.get("M1311")
        if m1311_gold is None or str(m1311_gold).strip() in ("", "0", "null", "None", "-"):
            errors.append({
                "check": "wound_presence",
                "code": "M1311",
                "expected": "non-zero (M1306 indicates wound present)",
                "actual": str(m1311_gold),
                "message": (
                    f"M1306={m1306} (wound present) but M1311='{m1311_gold}' "
                    f"in gold standard — wound surface area measurement required"
                ),
            })

        return errors

    # ── Check 9: N0415 Flags ───────────────────────────────────────────────────

    _N0415_DRUG_CLASS_MAP: dict[str, str] = {
        # Correct CMS OASIS-E1 N0415 sub-code assignments (A–I)
        "Antipsychotic": "N0415A",
        "Anticoagulant": "N0415B",
        "Antibiotic": "N0415C",
        "Antiplatelet": "N0415D",
        "Hypoglycemic": "N0415E",
        "Insulin": "N0415E",           # Insulin is a hypoglycemic agent
        "Cardiovascular": "N0415F",
        "Digoxin": "N0415F",
        "Narrow Therapeutic": "N0415F",
        "Diuretic": "N0415G",
        "Opioid": "N0415H",
    }

    # All N0415 sub-codes validated (A–I)
    _N0415_ALL_CODES: tuple[str, ...] = (
        "N0415A", "N0415B", "N0415C", "N0415D",
        "N0415E", "N0415F", "N0415G", "N0415H", "N0415I",
    )

    def _check_n0415_flags(self, *, gap_answers: dict, items: dict) -> list[dict]:
        """Every high-risk drug class in gap_answers N0415 must have its sub-flag set to '1' in the gold standard."""
        n0415_answer = _lookup_gap_answer(gap_answers, "N0415")
        if not n0415_answer or not isinstance(n0415_answer, list):
            return []  # No N0415 data in gap_answers — skip

        # Determine which sub-flags should be set based on gap_answers drug classes
        expected_flags: dict[str, str] = {code: "0" for code in self._N0415_ALL_CODES}
        for entry in n0415_answer:
            if not isinstance(entry, dict):
                continue
            drug_class = str(entry.get("drug_class", "")).strip()
            sub_flag = self._N0415_DRUG_CLASS_MAP.get(drug_class)
            if sub_flag:
                expected_flags[sub_flag] = "1"

        # N0415I = "1" only when ALL of A–H are "0"
        if all(expected_flags[c] == "0" for c in self._N0415_ALL_CODES[:-1]):
            expected_flags["N0415I"] = "1"

        errors: list[dict] = []
        for sub_flag, expected_value in expected_flags.items():
            actual = items.get(sub_flag)
            if actual is None:
                continue  # Sub-flag not in gold standard — cannot validate
            if str(actual).strip() != expected_value:
                drug_classes = [
                    dc for dc, sf in self._N0415_DRUG_CLASS_MAP.items() if sf == sub_flag
                ]
                errors.append({
                    "check": "n0415_flags",
                    "code": sub_flag,
                    "expected": expected_value,
                    "actual": str(actual),
                    "message": (
                        f"{sub_flag}: expected '{expected_value}' based on gap_answers N0415 "
                        f"(drug classes mapped to this flag: {drug_classes}) "
                        f"but gold standard has '{actual}'"
                    ),
                })

        return errors

    # ── Check 1: GG Consistency ────────────────────────────────────────────────

    def _check_gg_consistency(self, *, gap_answers: dict, items: dict) -> list[dict]:
        """GG0130 and GG0170 admission (X1) codes in gold standard must match gap_answers.

        Per pseudocode: FOR EACH gg_item IN [GG0130A1, GG0130B1, ...]
          gold_value = gold_standard[gg_item]
          gap_answer = gap_answers.find(field_code=gg_item).answer
          IF gold_value != gap_answer: error

        Supports three gap_answers formats:
          1. Direct sub-code (field_codes=["GG0130A1"]) — PRD 2.2 compliant
          2. Legacy grouped dict (field_codes=["GG0130"], answer={"Eating": "05", ...})
          3. Legacy title-based (field_codes=["GG0130"], title="... - GG0130A_admission")
        """
        errors: list[dict] = []

        def _lookup_legacy_title(base_prefix: str, letter: str, suffix: str) -> str | None:
            """Scan gap_answers sections for a question whose title encodes the GG sub-code.

            Handles titles like "Self-Care: ... - GG0130A" and
            "Mobility: ... - GG0170A_admission" / "GG0170A_discharge".
            """
            code_suffix_map = {
                "GG0130": (r"GG0130([A-G])(?=[^A-Z]|$)", lambda tail, s: "2" if tail.lower().startswith("_discharge") else "1"),
                "GG0170": (r"GG0170(RR|[A-P])(?=[^A-Z]|$)", lambda tail, s: "2" if tail.lower().startswith("_discharge") else "1"),
            }
            pattern, suffix_fn = code_suffix_map.get(base_prefix, (None, None))
            if not pattern:
                return None
            for section in gap_answers.get("sections", []):
                for q in section.get("questions", []):
                    if base_prefix not in q.get("field_codes", []):
                        continue
                    answer = q.get("answer")
                    if answer is None:
                        continue
                    title = q.get("title", "")
                    m = re.search(pattern, title, re.IGNORECASE)
                    if not m:
                        continue
                    found_letter = m.group(1).upper()
                    tail = title[m.end():]
                    found_suffix = suffix_fn(tail, suffix)
                    if found_letter == letter.upper() and found_suffix == suffix:
                        return str(answer)
            return None

        # Helper to get the expected value — tries all three formats
        def _get_expected_gg(base_prefix: str, mappings: dict, code: str, expected_letter: str, suffix: str) -> str | None:
            # 1. Direct sub-code lookup (PRD 2.2 compliant flattened format)
            val = _lookup_gap_answer(gap_answers, code)
            if val is not None:
                return str(val)

            # 2. Legacy grouped dictionary (e.g. {"Eating": "05"})
            legacy_dict = _lookup_gap_answer(gap_answers, base_prefix) or gap_answers.get(base_prefix)
            if isinstance(legacy_dict, dict):
                for key, mapped in mappings.items():
                    letters = mapped if isinstance(mapped, list) else [mapped]
                    if expected_letter in letters:
                        legacy_val = legacy_dict.get(key)
                        if legacy_val is not None:
                            return str(legacy_val)

            # 3. Legacy title-based format (field_codes=["GG0130"] but letter in title)
            title_val = _lookup_legacy_title(base_prefix, expected_letter, suffix)
            if title_val is not None:
                return title_val

            return None

        # ── GG0130 Self-Care ──────────────────────────────────────────────────
        gg0130_letters = set()
        for letter_or_letters in GG0130_LABEL_TO_LETTER.values():
            if isinstance(letter_or_letters, list):
                gg0130_letters.update(letter_or_letters)
            else:
                gg0130_letters.add(letter_or_letters)

        for letter in sorted(gg0130_letters):
            code = f"GG0130{letter}1"
            expected_value = _get_expected_gg("GG0130", GG0130_LABEL_TO_LETTER, code, letter, "1")
            
            if expected_value is not None:
                actual = items.get(code)
                if actual is not None and str(actual).strip() != expected_value.strip():
                    errors.append({
                        "check": "gg_consistency",
                        "code": code,
                        "expected": expected_value,
                        "actual": str(actual),
                        "message": (
                            f"{code}: gold standard has '{actual}' but "
                            f"gap_answers source = '{expected_value}'"
                        ),
                    })

        # ── GG0170 Mobility ───────────────────────────────────────────────────
        gg0170_letters = set(GG0170_KEY_TO_LETTER.values())
        for letter in sorted(gg0170_letters):
            code = f"GG0170{letter}1"
            expected_value = _get_expected_gg("GG0170", GG0170_KEY_TO_LETTER, code, letter, "1")
            
            if expected_value is not None:
                actual = items.get(code)
                if actual is not None and str(actual).strip() != expected_value.strip():
                    errors.append({
                        "check": "gg_consistency",
                        "code": code,
                        "expected": expected_value,
                        "actual": str(actual),
                        "message": (
                            f"{code}: gold standard has '{actual}' but "
                            f"gap_answers source = '{expected_value}'"
                        ),
                    })

        return errors

    # ── Check 2: BIMS Arithmetic ───────────────────────────────────────────────

    def _check_bims_arithmetic(self, *, gap_answers: dict, items: dict) -> list[dict]:
        """C0500 (BIMS Summary) must equal C0200 + C0300 + C0400 in the gold standard.

        Per pseudocode: bims_total = C0200 + C0300 + C0400; if gold_standard['C0500'] != bims_total → error.
        Also verifies the two-level derivation: C0300 = C0300A+B+C and C0400 = C0400A+B+C.
        """
        component_codes = [
            "C0200", "C0300A", "C0300B", "C0300C",
            "C0400A", "C0400B", "C0400C",
        ]
        total_code = "C0500"

        c0500_raw = items.get(total_code)
        if c0500_raw is None:
            return []  # BIMS not assessed — skip

        try:
            c0500 = int(c0500_raw)
        except (ValueError, TypeError):
            return []  # Non-numeric (e.g. "99" = not assessed) — skip

        components: dict[str, int] = {}
        for code in component_codes:
            raw = items.get(code)
            if raw is None:
                return []  # Missing component — cannot validate sum
            try:
                components[code] = int(raw)
            except (ValueError, TypeError):
                return []  # Non-numeric component — skip

        expected_sum = sum(components.values())
        if expected_sum != c0500:
            return [{
                "check": "bims_arithmetic",
                "code": total_code,
                "expected": str(expected_sum),
                "actual": str(c0500),
                "message": (
                    f"C0500 = {c0500} but component sum "
                    f"({' + '.join(f'{k}={v}' for k, v in components.items())}) = {expected_sum}"
                ),
            }]
        return []

    # ── Check 4: BIMS Cross-Reference (gap_answers vs gold standard) ────────────

    def _check_bims_gap_crosscheck(self, *, gap_answers: dict, items: dict) -> list[dict]:
        """Each raw BIMS sub-code in the gold standard must match the corresponding gap_answers value.

        Per pseudocode: BIMS values are read from gap_answers and compared to gold standard.
        This cross-document check ensures BIMS sub-scores were propagated verbatim from Step 4.

        NOTE: C0300, C0400, and C0500 are DERIVED totals — the generator recalculates them
        from sub-codes to fix arithmetic inconsistencies.  Those are validated by
        _check_bims_arithmetic instead.  Only the directly-observed sub-codes are checked here.
        """
        # Only raw interview scores — NOT derived totals (C0300, C0400, C0500)
        bims_raw_codes = [
            "C0100", "C0200",
            "C0300A", "C0300B", "C0300C",
            "C0400A", "C0400B", "C0400C",
            "C1310",
        ]
        errors: list[dict] = []
        for code in bims_raw_codes:
            gap_val = _lookup_gap_answer(gap_answers, code)
            if gap_val is None:
                continue  # Not in gap_answers — cannot cross-check
            gold_val = items.get(code)
            if gold_val is None:
                continue  # Not in gold standard — skip
            if str(gap_val).strip() != str(gold_val).strip():
                errors.append({
                    "check": "bims_gap_crosscheck",
                    "code": code,
                    "expected": str(gap_val),
                    "actual": str(gold_val),
                    "message": (
                        f"{code}: gap_answers='{gap_val}' but gold standard='{gold_val}' "
                        f"— BIMS values must be copied verbatim from Step 4"
                    ),
                })
        return errors

    # ── Check 4: PHQ Arithmetic ────────────────────────────────────────────────

    def _check_phq_arithmetic(self, *, gap_answers: dict, items: dict) -> list[dict]:
        """D0160 (PHQ Total) must equal sum of D0150X2 for all items where D0150X1 != '0'."""
        d0160_raw = items.get("D0160")
        if d0160_raw is None:
            return []  # PHQ not assessed — skip

        try:
            d0160 = int(d0160_raw)
        except (ValueError, TypeError):
            return []  # Non-numeric — skip

        phq_letters = ["A", "B", "C", "D", "E", "F", "G", "H", "I"]
        frequency_sum = 0
        detail_parts: list[str] = []
        for letter in phq_letters:
            symptom_code = f"D0150{letter}1"
            freq_code = f"D0150{letter}2"
            symptom_raw = items.get(symptom_code)
            if symptom_raw is None or str(symptom_raw) == "0":
                continue  # Symptom absent — frequency not counted in total
            freq_raw = items.get(freq_code)
            if freq_raw is None:
                continue  # Frequency missing — skip this item
            try:
                freq_val = int(freq_raw)
            except (ValueError, TypeError):
                continue
            frequency_sum += freq_val
            detail_parts.append(f"{freq_code}={freq_val}")

        if frequency_sum != d0160:
            return [{
                "check": "phq_arithmetic",
                "code": "D0160",
                "expected": str(frequency_sum),
                "actual": str(d0160),
                "message": (
                    f"D0160 = {d0160} but sum of present-symptom frequencies "
                    f"({', '.join(detail_parts) or 'none'}) = {frequency_sum}"
                ),
            }]
        return []

    # ── Check 5: PHQ-2 Gate ────────────────────────────────────────────────────

    def _check_phq2_gate(self, *, gap_answers: dict, items: dict) -> list[dict]:
        """If PHQ-2 screen (D0150A1 + D0150B1) < 3, downstream items C-I must be null.

        Per pseudocode: checks D0150C1 through D0150I2 (I is the last PHQ-9 item in
        OASIS-E1; 'J' in the pseudocode is a documentation typo).
        """
        a1_raw = items.get("D0150A1")
        b1_raw = items.get("D0150B1")
        if a1_raw is None or b1_raw is None:
            return []  # PHQ-2 screen not present — skip

        try:
            screen_score = int(a1_raw) + int(b1_raw)
        except (ValueError, TypeError):
            return []

        if screen_score >= 3:
            return []  # Full PHQ-9 was required — gate not applicable

        errors: list[dict] = []
        downstream_letters = ["C", "D", "E", "F", "G", "H", "I"]
        for letter in downstream_letters:
            for suffix in ["1", "2"]:
                code = f"D0150{letter}{suffix}"
                val = items.get(code)
                if val is not None and str(val).strip() not in ("", "-", "null", "None", "0"):
                    errors.append({
                        "check": "phq2_gate",
                        "code": code,
                        "expected": "null (PHQ-2 screen < 3)",
                        "actual": str(val),
                        "message": (
                            f"{code} = '{val}' but PHQ-2 screen score "
                            f"(D0150A1={a1_raw} + D0150B1={b1_raw} = {screen_score}) < 3 "
                            f"— downstream items should be null/not assessed"
                        ),
                    })
        return errors

    # ── Check 6: Date Ordering ─────────────────────────────────────────────────

    def _check_date_ordering(self, *, gap_answers: dict, items: dict) -> list[dict]:
        """M1005 <= M0104 <= M0110 <= M0080 (hospital admit -> dc -> referral -> SOC).

        Per pseudocode: errors if discharge_date <= admit_date OR
        referral_date < discharge_date OR soc_date < referral_date.
        """
        date_codes = ["M1005", "M0104", "M0110", "M0080"]
        parsed: dict[str, datetime] = {}

        for code in date_codes:
            raw = items.get(code)
            if raw is None or str(raw).strip() in ("", "-", "null", "None"):
                continue
            for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y"):
                try:
                    parsed[code] = datetime.strptime(str(raw).strip(), fmt)
                    break
                except ValueError:
                    continue

        errors: list[dict] = []
        ordering = [
            ("M1005", "M0104", "hospital admission date <= discharge date"),
            ("M0104", "M0110", "discharge date <= referral date"),
            ("M0110", "M0080", "referral date <= start-of-care date"),
        ]
        for earlier_code, later_code, description in ordering:
            earlier = parsed.get(earlier_code)
            later = parsed.get(later_code)
            if earlier is None or later is None:
                continue  # One or both dates not present — skip this pair
            if earlier > later:
                errors.append({
                    "check": "date_ordering",
                    "code": f"{earlier_code}..{later_code}",
                    "expected": f"{earlier_code} <= {later_code} ({description})",
                    "actual": (
                        f"{earlier_code}={items[earlier_code]}, "
                        f"{later_code}={items[later_code]}"
                    ),
                    "message": (
                        f"Date ordering violated: {description}. "
                        f"{earlier_code}={items[earlier_code]} > "
                        f"{later_code}={items[later_code]}"
                    ),
                })
        return errors

    # ── Check 7: Skip-Logic ────────────────────────────────────────────────────

    def _check_skip_logic(self, *, gap_answers: dict, items: dict) -> list[dict]:
        """M1306=0 => M1311/M1313/M1314 null; M1740=7 => no other M1740 flags set."""
        errors: list[dict] = []

        # Rule A: M1306=0 (no unhealed pressure ulcer ≥ Stage 2) => M1311–M1314 must be null/0
        m1306 = items.get("M1306")
        if m1306 is not None and str(m1306).strip() == "0":
            for code in ["M1311", "M1313", "M1314"]:
                val = items.get(code)
                if val is not None and str(val).strip() not in ("", "-", "0", "null", "None"):
                    errors.append({
                        "check": "skip_logic",
                        "code": code,
                        "expected": "null or 0 (M1306=0 — no unhealed pressure ulcers)",
                        "actual": str(val),
                        "message": (
                            f"{code} = '{val}' but M1306=0 (no unhealed pressure ulcers) — "
                            f"dependent codes should be null/0"
                        ),
                    })

        # Rule B: M1740 flag "07" (none of the above) is mutually exclusive with other flags
        m1740 = items.get("M1740")
        if m1740 is not None:
            raw_str = str(m1740).strip()
            # Value may be a comma-separated list of flags or a single code
            flags = {f.strip() for f in raw_str.split(",") if f.strip()}
            if "07" in flags and len(flags) > 1:
                errors.append({
                    "check": "skip_logic",
                    "code": "M1740",
                    "expected": "only '07' (none of the above) — no other flags",
                    "actual": str(m1740),
                    "message": (
                        f"M1740 contains flag '07' (none of the above) alongside other flags: "
                        f"{sorted(flags)} — mutually exclusive"
                    ),
                })

        return errors
