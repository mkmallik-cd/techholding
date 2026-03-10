"""Tests for Step 7 — ConsistencyValidator

Covers all 6 checks: GG consistency, BIMS arithmetic, PHQ arithmetic,
PHQ-2 gate, date ordering, and skip-logic cross-check.
"""
from __future__ import annotations

import pytest

from app.services.generators.consistency_validator import ConsistencyValidator


def _items(*pairs) -> list[dict]:
    """Helper: build a gold-standard items list from (code, value) pairs."""
    return [{"code": code, "value": value} for code, value in pairs]


def _gold(*pairs) -> dict:
    return {"items": _items(*pairs)}


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def validator():
    return ConsistencyValidator()


# ── Check 1: GG Consistency ───────────────────────────────────────────────────

class TestGGConsistency:
    def test_gg0130_matches_gap_answers(self, validator):
        gap = {"GG0130": {"Eating": "04", "Oral Hygiene": "03"}}
        gold = _gold(("GG0130A1", "04"), ("GG0130B1", "03"))
        result = validator.validate(gap_answers=gap, gold_standard=gold)
        assert result.is_valid
        assert result.errors == []

    def test_gg0130_mismatch_is_flagged(self, validator):
        gap = {"GG0130": {"Eating": "04"}}
        gold = _gold(("GG0130A1", "02"))  # should be 04
        result = validator.validate(gap_answers=gap, gold_standard=gold)
        assert not result.is_valid
        assert any(e["code"] == "GG0130A1" for e in result.errors)

    def test_gg0170_matches_gap_answers(self, validator):
        gap = {"GG0170": {"A": "04", "B": "03"}}
        gold = _gold(("GG0170A1", "04"), ("GG0170B1", "03"))
        result = validator.validate(gap_answers=gap, gold_standard=gold)
        assert result.is_valid

    def test_gg0170_snake_case_keys(self, validator):
        gap = {"GG0170": {"roll_left": "03", "sit_to_lying": "04"}}
        gold = _gold(("GG0170A1", "03"), ("GG0170B1", "04"))
        result = validator.validate(gap_answers=gap, gold_standard=gold)
        assert result.is_valid

    def test_unknown_gg_key_is_ignored(self, validator):
        gap = {"GG0130": {"UnknownActivity": "04"}}
        gold = _gold()
        result = validator.validate(gap_answers=gap, gold_standard=gold)
        assert result.is_valid  # Unknown key — no error

    def test_combined_dressing_key_maps_to_both_d_and_e(self, validator):
        gap = {"GG0130": {"Dressing": "03"}}
        gold = _gold(("GG0130D1", "03"), ("GG0130E1", "03"))
        result = validator.validate(gap_answers=gap, gold_standard=gold)
        assert result.is_valid

    def test_combined_dressing_key_mismatch(self, validator):
        gap = {"GG0130": {"Dressing": "03"}}
        gold = _gold(("GG0130D1", "03"), ("GG0130E1", "05"))  # E is wrong
        result = validator.validate(gap_answers=gap, gold_standard=gold)
        assert not result.is_valid
        assert any(e["code"] == "GG0130E1" for e in result.errors)


# ── Check 2: BIMS Arithmetic ──────────────────────────────────────────────────

class TestBIMSArithmetic:
    def _bims_gold(self, c0200, c0300a, c0300b, c0300c, c0400a, c0400b, c0400c, c0500):
        return _gold(
            ("C0200", str(c0200)),
            ("C0300A", str(c0300a)),
            ("C0300B", str(c0300b)),
            ("C0300C", str(c0300c)),
            ("C0400A", str(c0400a)),
            ("C0400B", str(c0400b)),
            ("C0400C", str(c0400c)),
            ("C0500", str(c0500)),
        )

    def test_correct_bims_sum(self, validator):
        gold = self._bims_gold(2, 2, 1, 1, 2, 2, 2, 12)
        result = validator.validate(gap_answers={}, gold_standard=gold)
        assert result.is_valid

    def test_incorrect_bims_sum(self, validator):
        gold = self._bims_gold(2, 2, 1, 1, 2, 2, 2, 15)  # sum is 12 not 15
        result = validator.validate(gap_answers={}, gold_standard=gold)
        assert not result.is_valid
        assert any(e["code"] == "C0500" for e in result.errors)

    def test_missing_c0500_skips_check(self, validator):
        gold = _gold(("C0200", "2"))  # No C0500
        result = validator.validate(gap_answers={}, gold_standard=gold)
        assert result.is_valid  # Check skipped — no error

    def test_maximum_bims_score(self, validator):
        gold = self._bims_gold(3, 3, 3, 3, 2, 2, 2, 18)
        result = validator.validate(gap_answers={}, gold_standard=gold)
        assert result.is_valid


# ── Check 3: PHQ Arithmetic ───────────────────────────────────────────────────

class TestPHQArithmetic:
    def _phq_gold(self, symptom_flags: dict, freq_values: dict, d0160: int) -> dict:
        """symptom_flags: {letter: "0"|"1"}, freq_values: {letter: int}"""
        pairs = []
        for letter in ["A", "B", "C", "D", "E", "F", "G", "H", "I"]:
            if letter in symptom_flags:
                pairs.append((f"D0150{letter}1", symptom_flags[letter]))
            if letter in freq_values:
                pairs.append((f"D0150{letter}2", str(freq_values[letter])))
        pairs.append(("D0160", str(d0160)))
        return _gold(*pairs)

    def test_correct_phq_sum(self, validator):
        gold = self._phq_gold(
            symptom_flags={"A": "1", "B": "1", "C": "0"},
            freq_values={"A": 2, "B": 3},
            d0160=5,
        )
        result = validator.validate(gap_answers={}, gold_standard=gold)
        assert result.is_valid

    def test_absent_symptoms_excluded_from_sum(self, validator):
        gold = self._phq_gold(
            symptom_flags={"A": "1", "B": "0"},
            freq_values={"A": 2, "B": 3},  # B freq should not count since B symptom=0
            d0160=2,
        )
        result = validator.validate(gap_answers={}, gold_standard=gold)
        assert result.is_valid

    def test_incorrect_phq_sum(self, validator):
        gold = self._phq_gold(
            symptom_flags={"A": "1", "B": "1"},
            freq_values={"A": 2, "B": 3},
            d0160=10,  # should be 5
        )
        result = validator.validate(gap_answers={}, gold_standard=gold)
        assert not result.is_valid
        assert any(e["code"] == "D0160" for e in result.errors)


# ── Check 4: PHQ-2 Gate ───────────────────────────────────────────────────────

class TestPHQ2Gate:
    def test_screen_score_lt_3_all_downstream_null(self, validator):
        gold = _gold(("D0150A1", "1"), ("D0150B1", "1"))  # sum=2 < 3; no downstream
        result = validator.validate(gap_answers={}, gold_standard=gold)
        assert result.is_valid

    def test_screen_score_lt_3_downstream_populated_is_invalid(self, validator):
        gold = _gold(
            ("D0150A1", "1"), ("D0150B1", "1"),  # sum=2 < 3
            ("D0150C1", "1"),  # should be null
        )
        result = validator.validate(gap_answers={}, gold_standard=gold)
        assert not result.is_valid
        assert any(e["code"] == "D0150C1" for e in result.errors)

    def test_screen_score_gte_3_allows_downstream(self, validator):
        gold = _gold(
            ("D0150A1", "2"), ("D0150B1", "2"),  # sum=4 >= 3
            ("D0150C1", "1"),
        )
        result = validator.validate(gap_answers={}, gold_standard=gold)
        assert result.is_valid


# ── Check 5: Date Ordering ────────────────────────────────────────────────────

class TestDateOrdering:
    def test_valid_date_chain(self, validator):
        gold = _gold(
            ("M1005", "01/01/2026"),  # hospital admit
            ("M0104", "01/10/2026"),  # discharge
            ("M0110", "01/11/2026"),  # referral
            ("M0080", "01/15/2026"),  # SOC
        )
        result = validator.validate(gap_answers={}, gold_standard=gold)
        assert result.is_valid

    def test_discharge_before_admit_is_invalid(self, validator):
        gold = _gold(
            ("M1005", "01/15/2026"),
            ("M0104", "01/10/2026"),  # before M1005
        )
        result = validator.validate(gap_answers={}, gold_standard=gold)
        assert not result.is_valid
        assert any("M1005" in e["code"] for e in result.errors)

    def test_soc_before_referral_is_invalid(self, validator):
        gold = _gold(
            ("M0110", "01/20/2026"),  # referral
            ("M0080", "01/15/2026"),  # SOC before referral
        )
        result = validator.validate(gap_answers={}, gold_standard=gold)
        assert not result.is_valid

    def test_equal_dates_are_valid(self, validator):
        gold = _gold(
            ("M0110", "01/15/2026"),
            ("M0080", "01/15/2026"),  # same day — valid
        )
        result = validator.validate(gap_answers={}, gold_standard=gold)
        assert result.is_valid

    def test_missing_dates_skipped(self, validator):
        gold = _gold(("M1005", "01/01/2026"))  # only one date
        result = validator.validate(gap_answers={}, gold_standard=gold)
        assert result.is_valid  # pair incomplete — skip


# ── Check 6: Skip-Logic ───────────────────────────────────────────────────────

class TestSkipLogic:
    def test_m1306_zero_no_dependents_is_valid(self, validator):
        gold = _gold(("M1306", "0"))
        result = validator.validate(gap_answers={}, gold_standard=gold)
        assert result.is_valid

    def test_m1306_zero_with_dependent_flagged(self, validator):
        gold = _gold(("M1306", "0"), ("M1311", "3"))
        result = validator.validate(gap_answers={}, gold_standard=gold)
        assert not result.is_valid
        assert any(e["code"] == "M1311" for e in result.errors)

    def test_m1306_nonzero_allows_dependents(self, validator):
        gold = _gold(("M1306", "1"), ("M1311", "3"))
        result = validator.validate(gap_answers={}, gold_standard=gold)
        assert result.is_valid

    def test_m1740_none_alone_is_valid(self, validator):
        gold = _gold(("M1740", "07"))
        result = validator.validate(gap_answers={}, gold_standard=gold)
        assert result.is_valid

    def test_m1740_none_plus_other_flag_is_invalid(self, validator):
        gold = _gold(("M1740", "01,07"))  # "none" combined with another flag
        result = validator.validate(gap_answers={}, gold_standard=gold)
        assert not result.is_valid
        assert any(e["code"] == "M1740" for e in result.errors)


# ── Aggregate behaviour ───────────────────────────────────────────────────────

class TestAggregation:
    def test_checks_run_count(self, validator):
        result = validator.validate(gap_answers={}, gold_standard={"items": []})
        assert result.checks_run == 6

    def test_all_checks_pass_empty_gold_standard(self, validator):
        result = validator.validate(gap_answers={}, gold_standard={"items": []})
        assert result.is_valid
        assert result.checks_passed == 6

    def test_multiple_failures_accumulate(self, validator):
        # BIMS wrong + date ordering wrong
        gold = _gold(
            ("C0200", "2"), ("C0300A", "2"), ("C0300B", "1"), ("C0300C", "1"),
            ("C0400A", "2"), ("C0400B", "2"), ("C0400C", "2"),
            ("C0500", "99"),  # wrong sum
            ("M1005", "01/20/2026"),
            ("M0104", "01/10/2026"),  # before M1005
        )
        result = validator.validate(gap_answers={}, gold_standard=gold)
        assert not result.is_valid
        assert len(result.errors) >= 2
