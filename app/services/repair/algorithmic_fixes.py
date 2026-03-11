"""Deterministic (algorithmic) repair functions for gap_answers and gold_standard artifacts.

All functions operate on the deserialized Python dicts and return the modified dict
plus a list of human-readable fix descriptions for logging.
"""
from __future__ import annotations

from app.utils.logger import get_logger

logger = get_logger(__name__)

# ── Gap-answers helpers ────────────────────────────────────────────────────────


def _build_code_index(gap_answers: dict) -> dict[str, dict]:
    """Return a mutable index of {code: question_entry} from any gap_answers format.

    Supports both the new ``sections`` array format (PRD Section 6) and the
    legacy ``unanswered_response`` flat dict.  The returned dict values are
    references into the original structure — mutations propagate back.
    """
    index: dict[str, dict] = {}
    # New format: sections array
    for section in gap_answers.get("sections", []):
        for question in section.get("questions", []):
            for code in question.get("field_codes", []):
                index[code] = question
    # Legacy format: unanswered_response flat dict
    for code, entry in gap_answers.get("unanswered_response", {}).items():
        if isinstance(entry, dict) and code not in index:
            index[code] = entry
    return index


def _get_answer(index_or_unanswered: dict, code: str):
    """Return the raw answer value for ``code``, or None if absent."""
    entry = index_or_unanswered.get(code)
    return entry.get("answer") if isinstance(entry, dict) else None


def fix_gap_answers(gap_answers: dict) -> tuple[dict, list[str]]:
    """Apply PHQ-2 gate and arithmetic corrections to a gap_answers dict in-place.

    Handles:
    - PHQ-2 gate: if D0150A1 + D0150B1 < 3, null D0150C–I items and recalculate D0160.
    - BIMS arithmetic: recalculate C0500 = sum of sub-score codes.
    - PHQ arithmetic: recalculate D0160 = sum of D0150X2 where D0150X1 is present.

    Returns:
        (modified_gap_answers, list_of_fix_descriptions)
    """
    # Build a unified {code: entry} index that works for both schema versions.
    # Mutations to entry["answer"] propagate back to the original structure.
    unanswered: dict = _build_code_index(gap_answers)
    fixes: list[str] = []
    phq2_gate_fired = False

    # ── PHQ-2 gate ────────────────────────────────────────────────────────────
    a1 = _get_answer(unanswered, "D0150A1")
    b1 = _get_answer(unanswered, "D0150B1")
    if a1 is not None and b1 is not None:
        try:
            screen = int(a1) + int(b1)
        except (ValueError, TypeError):
            screen = 999
        if screen < 3:
            phq2_gate_fired = True
            for letter in ("C", "D", "E", "F", "G", "H", "I"):
                for suffix in ("1", "2"):
                    code = f"D0150{letter}{suffix}"
                    entry = unanswered.get(code)
                    if isinstance(entry, dict):
                        entry["answer"] = None
                        fixes.append(f"gap.{code}=null (phq2_gate screen={screen})")
            # Recalculate D0160 — only A+B frequency counts now
            freq_sum = 0
            for letter in ("A", "B"):
                s1 = _get_answer(unanswered, f"D0150{letter}1")
                s2 = _get_answer(unanswered, f"D0150{letter}2")
                if s1 is not None and str(s1).strip() not in ("0", "None", "null", "") \
                        and s2 is not None:
                    try:
                        freq_sum += int(s2)
                    except (ValueError, TypeError):
                        pass
            d0160_entry = unanswered.get("D0160")
            if isinstance(d0160_entry, dict):
                d0160_entry["answer"] = str(freq_sum)
                fixes.append(f"gap.D0160={freq_sum} (phq2_gate recalc)")

    # ── BIMS arithmetic ───────────────────────────────────────────────────────
    sub_codes = [
        "C0200", "C0300A", "C0300B", "C0300C",
        "C0400A", "C0400B", "C0400C",
    ]
    sub_vals: list[int] = []
    for c in sub_codes:
        raw = _get_answer(unanswered, c)
        if raw is None:
            sub_vals = []
            break
        try:
            sub_vals.append(int(raw))
        except (ValueError, TypeError):
            sub_vals = []
            break
    if sub_vals:
        expected_total = sum(sub_vals)
        c0500_entry = unanswered.get("C0500")
        if isinstance(c0500_entry, dict):
            current = _get_answer(unanswered, "C0500")
            try:
                if current is None or int(current) != expected_total:
                    c0500_entry["answer"] = str(expected_total)
                    fixes.append(f"gap.C0500={expected_total} (bims_arithmetic)")
            except (ValueError, TypeError):
                c0500_entry["answer"] = str(expected_total)
                fixes.append(f"gap.C0500={expected_total} (bims_arithmetic)")

    # ── PHQ arithmetic (only if PHQ-2 gate did NOT already fix D0160) ─────────
    if not phq2_gate_fired:
        freq_sum = 0
        for letter in "ABCDEFGHI":
            s1 = _get_answer(unanswered, f"D0150{letter}1")
            s2 = _get_answer(unanswered, f"D0150{letter}2")
            if s1 is not None \
                    and str(s1).strip() not in ("0", "None", "null", "") \
                    and s2 is not None:
                try:
                    freq_sum += int(s2)
                except (ValueError, TypeError):
                    pass
        d0160_entry = unanswered.get("D0160")
        if isinstance(d0160_entry, dict):
            current = _get_answer(unanswered, "D0160")
            try:
                if current is None or int(current) != freq_sum:
                    d0160_entry["answer"] = str(freq_sum)
                    fixes.append(f"gap.D0160={freq_sum} (phq_arithmetic)")
            except (ValueError, TypeError):
                d0160_entry["answer"] = str(freq_sum)
                fixes.append(f"gap.D0160={freq_sum} (phq_arithmetic)")

    return gap_answers, fixes


# ── Gold-standard helpers ──────────────────────────────────────────────────────

def fix_gold_standard(
    gold_standard: dict,
    validation_errors: list[dict],
) -> tuple[dict, list[str]]:
    """Apply all deterministic fixes to a gold_standard dict in-place, guided by validation_errors.

    Handles: phq2_gate, bims_arithmetic, phq_arithmetic, gg_consistency,
              skip_logic, date_ordering.

    Returns:
        (modified_gold_standard, list_of_fix_descriptions)
    """
    items_list: list[dict] = gold_standard.get("items", [])
    by_code: dict[str, dict] = {entry["item_code"]: entry for entry in items_list}
    fixes: list[str] = []

    # Group errors by check type
    errors_by_check: dict[str, list[dict]] = {}
    for err in validation_errors:
        check = err.get("check", "")
        errors_by_check.setdefault(check, []).append(err)

    if "phq2_gate" in errors_by_check:
        fixes.extend(_fix_phq2_gate_in_gold(by_code, errors_by_check["phq2_gate"]))

    if "gg_consistency" in errors_by_check:
        for err in errors_by_check["gg_consistency"]:
            code = err.get("code")
            expected = err.get("expected")
            if code and expected is not None and code in by_code:
                by_code[code]["value"] = str(expected)
                by_code[code]["rationale"] = (
                    f"Repaired: gg_consistency — value aligned to gap_answers source '{expected}'"
                )
                fixes.append(f"gold.{code}={expected} (gg_consistency)")

    if "bims_arithmetic" in errors_by_check:
        fixes.extend(_fix_bims_arithmetic_in_gold(by_code))

    if "phq_arithmetic" in errors_by_check:
        fixes.extend(_fix_phq_arithmetic_in_gold(by_code))

    if "skip_logic" in errors_by_check:
        for err in errors_by_check["skip_logic"]:
            code = err.get("code")
            if code and code in by_code:
                by_code[code]["value"] = None
                by_code[code]["rationale"] = "Repaired: skip_logic — dependent item nulled"
                fixes.append(f"gold.{code}=null (skip_logic)")

    if "date_ordering" in errors_by_check:
        fixes.extend(
            _fix_date_ordering_in_gold(by_code, errors_by_check["date_ordering"])
        )

    return gold_standard, fixes


def _fix_phq2_gate_in_gold(by_code: dict, errors: list[dict]) -> list[str]:
    fixes: list[str] = []
    nulled: set[str] = set()

    for err in errors:
        code = err.get("code")
        if code and code in by_code:
            by_code[code]["value"] = None
            by_code[code]["rationale"] = (
                "Repaired: phq2_gate — PHQ-2 screen score < 3; item nulled (not administered)"
            )
            nulled.add(code)
            fixes.append(f"gold.{code}=null (phq2_gate)")

    # Recalculate D0160 after nulling — only sum A+B frequencies for present symptoms
    freq_sum = 0
    for letter in "ABCDEFGHI":
        s1_item = by_code.get(f"D0150{letter}1")
        s2_item = by_code.get(f"D0150{letter}2")
        if s1_item is None or s2_item is None:
            continue
        s1 = s1_item.get("value")
        s2 = s2_item.get("value")
        if f"D0150{letter}2" in nulled:
            continue  # This was just nulled — don't count
        if s1 is not None \
                and str(s1).strip() not in ("0", "None", "null", "") \
                and s2 is not None:
            try:
                freq_sum += int(str(s2))
            except (ValueError, TypeError):
                pass

    d0160_item = by_code.get("D0160")
    if d0160_item is not None:
        d0160_item["value"] = str(freq_sum)
        d0160_item["rationale"] = (
            f"Repaired: phq2_gate — D0160 recalculated as {freq_sum} after downstream nulling"
        )
        fixes.append(f"gold.D0160={freq_sum} (phq2_gate D0160 recalc)")

    return fixes


def _fix_bims_arithmetic_in_gold(by_code: dict) -> list[str]:
    sub_codes = [
        "C0200", "C0300A", "C0300B", "C0300C",
        "C0400A", "C0400B", "C0400C",
    ]
    sub_vals: list[int] = []
    for c in sub_codes:
        item = by_code.get(c)
        if item is None:
            return []
        v = item.get("value")
        if v is None:
            return []
        try:
            sub_vals.append(int(str(v)))
        except (ValueError, TypeError):
            return []

    expected = sum(sub_vals)
    c0500_item = by_code.get("C0500")
    if c0500_item is not None:
        c0500_item["value"] = str(expected)
        c0500_item["rationale"] = (
            f"Repaired: bims_arithmetic — C0500 recalculated as {expected}"
        )
        return [f"gold.C0500={expected} (bims_arithmetic)"]
    return []


def _fix_phq_arithmetic_in_gold(by_code: dict) -> list[str]:
    freq_sum = 0
    for letter in "ABCDEFGHI":
        s1_item = by_code.get(f"D0150{letter}1")
        s2_item = by_code.get(f"D0150{letter}2")
        if s1_item is None or s2_item is None:
            continue
        s1 = s1_item.get("value")
        s2 = s2_item.get("value")
        if s1 is not None \
                and str(s1).strip() not in ("0", "None", "null", "") \
                and s2 is not None:
            try:
                freq_sum += int(str(s2))
            except (ValueError, TypeError):
                pass
    d0160_item = by_code.get("D0160")
    if d0160_item is not None:
        d0160_item["value"] = str(freq_sum)
        d0160_item["rationale"] = (
            f"Repaired: phq_arithmetic — D0160 recalculated as {freq_sum}"
        )
        return [f"gold.D0160={freq_sum} (phq_arithmetic)"]
    return []


def _fix_date_ordering_in_gold(by_code: dict, errors: list[dict]) -> list[str]:
    """For each out-of-order date pair, set the later date equal to the earlier one."""
    fixes: list[str] = []
    for err in errors:
        code_pair = err.get("code", "")
        if ".." not in code_pair:
            continue
        earlier_code, later_code = code_pair.split("..", 1)
        earlier_item = by_code.get(earlier_code)
        later_item = by_code.get(later_code)
        if earlier_item is None or later_item is None:
            continue
        earlier_val = earlier_item.get("value")
        later_item["value"] = earlier_val
        later_item["rationale"] = (
            f"Repaired: date_ordering — {later_code} adjusted to {earlier_val} "
            f"to satisfy {earlier_code} <= {later_code}"
        )
        fixes.append(f"gold.{later_code}={earlier_val} (date_ordering)")
    return fixes
