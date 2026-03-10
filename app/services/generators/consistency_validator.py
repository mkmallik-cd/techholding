"""Step 7 — Consistency Validator

Cross-checks the five generated documents for clinical contradictions.
All checks are deterministic; no LLM calls are made.

Checks performed:
  1. GG consistency      — GG0130/GG0170 X1 (admission) codes match gap_answers
  2. BIMS arithmetic     — C0500 == sum(C0200 + C0300A-C + C0400A-C)
  3. PHQ arithmetic      — D0160 == sum of D0150X2 where D0150X1 != "0"
  4. PHQ-2 gate          — if D0150A1 + D0150B1 < 3, downstream items must be null
  5. Date ordering       — M1005 <= M0104 <= M0110 <= M0080
  6. Skip-logic          — M1306=0 => M1311-M1314 null; M1740=7 => no other flags set
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.config.constants import GG0130_LABEL_TO_LETTER, GG0170_KEY_TO_LETTER
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
            gold_standard: Step 6 gold standard dict (contains "items" list).
            metadata: Optional patient metadata dict (currently unused).

        Returns:
            ValidationResult with is_valid, errors, checks_run, checks_passed.
        """
        # Flatten gold standard items into a {code: value} dict for easy O(1) lookups.
        items: dict[str, str | None] = {
            item.get("item_code") or item.get("code"): item.get("value")
            for item in gold_standard.get("items", [])
            if item.get("item_code") or item.get("code")
        }

        all_errors: list[dict] = []

        checks = [
            self._check_gg_consistency,
            self._check_bims_arithmetic,
            self._check_phq_arithmetic,
            self._check_phq2_gate,
            self._check_date_ordering,
            self._check_skip_logic,
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
        # Count distinct checks that produced no errors
        failed_check_names = {e["check"] for e in all_errors}
        checks_passed = sum(
            1 for fn in checks if fn.__name__ not in failed_check_names
        )

        return ValidationResult(
            is_valid=len(all_errors) == 0,
            errors=all_errors,
            checks_run=checks_run,
            checks_passed=checks_passed,
        )

    # ── Check 1: GG Consistency ────────────────────────────────────────────────

    def _check_gg_consistency(self, *, gap_answers: dict, items: dict) -> list[dict]:
        """GG0130 and GG0170 admission (X1) codes in gold standard must match gap_answers."""
        errors: list[dict] = []

        gg0130_raw = gap_answers.get("GG0130") or gap_answers.get("gg0130")
        if isinstance(gg0130_raw, dict):
            for label, expected_value in gg0130_raw.items():
                letter_or_letters = GG0130_LABEL_TO_LETTER.get(label)
                if letter_or_letters is None:
                    continue
                letters = (
                    [letter_or_letters]
                    if isinstance(letter_or_letters, str)
                    else letter_or_letters
                )
                for letter in letters:
                    code = f"GG0130{letter}1"
                    actual = items.get(code)
                    if actual is not None and str(actual) != str(expected_value):
                        errors.append({
                            "check": "gg_consistency",
                            "code": code,
                            "expected": str(expected_value),
                            "actual": str(actual),
                            "message": (
                                f"{code}: gold standard has '{actual}' but "
                                f"gap_answers GG0130['{label}'] = '{expected_value}'"
                            ),
                        })

        gg0170_raw = gap_answers.get("GG0170") or gap_answers.get("gg0170")
        if isinstance(gg0170_raw, dict):
            for key, expected_value in gg0170_raw.items():
                letter = GG0170_KEY_TO_LETTER.get(key)
                if letter is None:
                    continue
                code = f"GG0170{letter}1"
                actual = items.get(code)
                if actual is not None and str(actual) != str(expected_value):
                    errors.append({
                        "check": "gg_consistency",
                        "code": code,
                        "expected": str(expected_value),
                        "actual": str(actual),
                        "message": (
                            f"{code}: gold standard has '{actual}' but "
                            f"gap_answers GG0170['{key}'] = '{expected_value}'"
                        ),
                    })

        return errors

    # ── Check 2: BIMS Arithmetic ───────────────────────────────────────────────

    def _check_bims_arithmetic(self, *, gap_answers: dict, items: dict) -> list[dict]:
        """C0500 (BIMS Summary) must equal sum of C0200 + C0300A/B/C + C0400A/B/C."""
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

    # ── Check 3: PHQ Arithmetic ────────────────────────────────────────────────

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

    # ── Check 4: PHQ-2 Gate ────────────────────────────────────────────────────

    def _check_phq2_gate(self, *, gap_answers: dict, items: dict) -> list[dict]:
        """If PHQ-2 screen (D0150A1 + D0150B1) < 3, downstream items C-I must be null."""
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

    # ── Check 5: Date Ordering ─────────────────────────────────────────────────

    def _check_date_ordering(self, *, gap_answers: dict, items: dict) -> list[dict]:
        """M1005 <= M0104 <= M0110 <= M0080 (hospital admit -> dc -> referral -> SOC)."""
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

    # ── Check 6: Skip-Logic ────────────────────────────────────────────────────

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
