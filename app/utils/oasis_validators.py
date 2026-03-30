"""
app.utils.oasis_validators — Deterministic Python validators for OASIS field rules.

Used by both the Gap (Step 4) and Gold Standard (Step 6) generators as the
VALIDATE step in the Generate → Validate → Fix loop.

Each validator returns a list of human-readable violation strings.  An empty
list means the section passed all checks.  Violations are forwarded to the
LLM fix prompt when present.
"""

from __future__ import annotations

from app.utils.logger import get_logger

logger = get_logger(__name__)

# Non-OASIS EHR narrative keys that must never appear in generated output.
FORBIDDEN_KEYS: frozenset[str] = frozenset({
    "PHQ_MOOD_INTERVIEW", "ALLERGIES", "VITAL_SIGNS", "CIRCULATORY_HISTORY",
    "MENTAL_STATUS", "SKIN", "LAB_RESULTS", "WOUND_CARE", "FALL_RISK_FACTORS",
    "COGNITIVE_STATUS", "FUNCTIONAL_LIMITATIONS", "HOMEBOUND_STATUS",
    "SAFETY_MEASURES", "NUTRITIONAL_STATUS", "CAREGIVER_STATUS",
    "ACTIVITIES_PERMITTED", "DIABETIC_FOOT", "COMMUNITY_SCREENING",
    "CORRECTIVE_ACTION_PLAN",
})

# GG sub-codes that MUST be present whenever GG self-care/mobility data is generated.
_GG_SELF_CARE_REQUIRED: list[str] = [
    "GG0130D1", "GG0130E1",  # Upper/Lower Body Dressing admission — frequently missing
]
_GG_MOBILITY_REQUIRED: list[str] = [
    "GG0170A1", "GG0170B1", "GG0170C1",
    "GG0170D1", "GG0170E1", "GG0170F1",  # Sit-Stand, Chair Tx, Toilet Tx — frequently missing
]


# ── Individual validators ──────────────────────────────────────────────────────

def validate_forbidden_keys(items: dict[str, object]) -> list[str]:
    """Return violations for any non-OASIS EHR narrative keys found in *items*."""
    bad = [k for k in items if k in FORBIDDEN_KEYS]
    return [f"Forbidden non-OASIS key present: {k}" for k in bad]


def validate_bims_arithmetic(items: dict[str, object]) -> list[str]:
    """Check two-level BIMS arithmetic.

    Rules:
      C0300 = C0300A + C0300B + C0300C  (range 0–6)
      C0400 = C0400A + C0400B + C0400C  (range 0–6)
      C0500 = C0200  + C0300  + C0400   (range 0–15)
    """
    violations: list[str] = []

    def _int(code: str) -> int | None:
        val = items.get(code)
        if val is None:
            return None
        try:
            return int(str(val).strip().split()[0])
        except (ValueError, TypeError):
            return None

    c0300a, c0300b, c0300c = _int("C0300A"), _int("C0300B"), _int("C0300C")
    if None not in (c0300a, c0300b, c0300c):
        expected = c0300a + c0300b + c0300c  # type: ignore[operator]
        actual = _int("C0300")
        if actual is not None and actual != expected:
            violations.append(
                f"BIMS C0300={actual} but C0300A+C0300B+C0300C={expected}; "
                f"set C0300={expected}"
            )

    c0400a, c0400b, c0400c = _int("C0400A"), _int("C0400B"), _int("C0400C")
    if None not in (c0400a, c0400b, c0400c):
        expected = c0400a + c0400b + c0400c  # type: ignore[operator]
        actual = _int("C0400")
        if actual is not None and actual != expected:
            violations.append(
                f"BIMS C0400={actual} but C0400A+C0400B+C0400C={expected}; "
                f"set C0400={expected}"
            )

    c0200 = _int("C0200")
    c0300 = _int("C0300")
    c0400 = _int("C0400")
    if None not in (c0200, c0300, c0400):
        expected = c0200 + c0300 + c0400  # type: ignore[operator]
        actual = _int("C0500")
        if actual is not None and actual != expected:
            violations.append(
                f"BIMS C0500={actual} but C0200+C0300+C0400={expected}; "
                f"set C0500={expected}"
            )

    return violations


def validate_phq2_gate(items: dict[str, object]) -> list[str]:
    """Check CMS PHQ-2 gate rules.

    If D0150A1 + D0150B1 < 3 (negative screen):
      - D0150C1–I1 and D0150C2–I2 must be null/absent
      - D0160 = (A2 if A1==1 else 0) + (B2 if B1==1 else 0)

    If screen >= 3 (positive):
      - D0160 = sum of D0150X2 where D0150X1 == 1
    """
    violations: list[str] = []

    def _int(code: str) -> int | None:
        val = items.get(code)
        if val is None:
            return None
        try:
            return int(str(val).strip().split()[0])
        except (ValueError, TypeError):
            return None

    a1, b1 = _int("D0150A1"), _int("D0150B1")
    if a1 is None or b1 is None:
        return violations  # can't evaluate without screen items

    screen = a1 + b1

    if screen < 3:
        # Negative screen — C–I must be null
        for letter in "CDEFGHI":
            for col in ("1", "2"):
                code = f"D0150{letter}{col}"
                val = items.get(code)
                if val is not None and str(val).strip() not in ("", "null", "None"):
                    violations.append(
                        f"PHQ-2 gate violation: {code}={val!r} must be null "
                        f"(screen score {screen} < 3)"
                    )
        # Check D0160
        a2 = _int("D0150A2") if a1 == 1 else 0
        b2 = _int("D0150B2") if b1 == 1 else 0
        if a2 is None:
            a2 = 0
        if b2 is None:
            b2 = 0
        expected_d0160 = a2 + b2
        actual_d0160 = _int("D0160")
        if actual_d0160 is not None and actual_d0160 != expected_d0160:
            violations.append(
                f"PHQ-2 D0160={actual_d0160} but negative screen formula "
                f"(A2 if A1=1 else 0)+(B2 if B1=1 else 0)={expected_d0160}; "
                f"set D0160={expected_d0160}"
            )
    else:
        # Positive screen — D0160 = sum of frequencies for present items
        freq_sum = 0
        for letter in "ABCDEFGHI":
            symptom = _int(f"D0150{letter}1")
            freq = _int(f"D0150{letter}2")
            if symptom == 1 and freq is not None:
                freq_sum += freq
        actual_d0160 = _int("D0160")
        if actual_d0160 is not None and actual_d0160 != freq_sum:
            violations.append(
                f"PHQ D0160={actual_d0160} but sum of present-item frequencies={freq_sum}; "
                f"set D0160={freq_sum}"
            )

    return violations


def validate_n0415_completeness(items: dict[str, object]) -> list[str]:
    """All nine N0415 sub-flags (A–I) must be present and be '0' or '1'."""
    violations: list[str] = []
    for sub in "ABCDEFGHI":
        code = f"N0415{sub}"
        val = items.get(code)
        if val is None:
            violations.append(f"N0415{sub} missing entirely from output")
        elif str(val).strip() not in ("0", "1"):
            violations.append(
                f"N0415{sub}={val!r} is not a valid binary flag ('0' or '1')"
            )
    # N0415I must be '1' only when all A–H are '0'
    flags = [str(items.get(f"N0415{s}", "0")).strip() for s in "ABCDEFGH"]
    n0415i = str(items.get("N0415I", "")).strip()
    if n0415i == "1" and any(f == "1" for f in flags):
        violations.append(
            "N0415I='1' (None of above) but at least one of N0415A–H is also '1'"
        )
    if n0415i == "0" and all(f == "0" for f in flags):
        violations.append(
            "N0415I='0' but all of N0415A–H are '0' — N0415I should be '1' (None of above)"
        )
    return violations


def validate_gg_completeness(items: dict[str, object], section: str) -> list[str]:
    """Check that frequently-missing GG sub-codes are present for the given section."""
    violations: list[str] = []
    required = (
        _GG_SELF_CARE_REQUIRED if section == "gg_self_care" else _GG_MOBILITY_REQUIRED
    )
    for code in required:
        if items.get(code) is None:
            violations.append(f"{code} is missing from output (frequently omitted — MUST emit)")
    return violations


# ── Orchestrator ───────────────────────────────────────────────────────────────

def validate_batch(
    items: dict[str, object],
    section_name: str,
) -> list[str]:
    """Run all applicable validators for *section_name* and return all violations.

    Args:
        items:        Flat dict of {OASIS_code: value_string}.
        section_name: One of 'bims', 'phq', 'gg_self_care', 'gg_mobility',
                      'n0415', 'm_codes', or a gold-standard batch name like
                      'A_admin_diagnosis', 'B_sensory_behavioral_living', etc.

    Returns:
        List of human-readable violation strings; empty list = all checks pass.
    """
    violations: list[str] = []

    # Forbidden keys apply to every section
    violations.extend(validate_forbidden_keys(items))

    if section_name == "bims":
        violations.extend(validate_bims_arithmetic(items))

    elif section_name == "phq":
        violations.extend(validate_phq2_gate(items))

    elif section_name == "gg_self_care":
        violations.extend(validate_gg_completeness(items, "gg_self_care"))

    elif section_name == "gg_mobility":
        violations.extend(validate_gg_completeness(items, "gg_mobility"))

    elif section_name == "n0415":
        violations.extend(validate_n0415_completeness(items))

    # Gold-standard batches — apply relevant checks to codes that may be present
    elif section_name in (
        "C_gg_self_care", "D_gg_mobility_adl",
        "A_admin_diagnosis", "B_sensory_behavioral_living",
        "E_wound_respiratory_medication",
    ):
        # GG codes can appear in gold batches C and D
        if section_name == "C_gg_self_care":
            violations.extend(validate_gg_completeness(items, "gg_self_care"))
        if section_name == "D_gg_mobility_adl":
            violations.extend(validate_gg_completeness(items, "gg_mobility"))
        # N0415 may appear in any gold batch (usually E)
        n0415_present = any(k.startswith("N0415") for k in items)
        if n0415_present:
            violations.extend(validate_n0415_completeness(items))
        # BIMS/PHQ in any gold batch
        if any(k.startswith("C0") for k in items):
            violations.extend(validate_bims_arithmetic(items))
        if any(k.startswith("D015") for k in items):
            violations.extend(validate_phq2_gate(items))

    if violations:
        logger.warning(
            "oasis_validators: section=%s — %d violation(s): %s",
            section_name,
            len(violations),
            "; ".join(violations),
        )

    return violations
