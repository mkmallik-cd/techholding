"""Shared helpers for reading values from a gap_answers dict.

Supports both the new ``sections`` array format (PRD Section 6) and the
legacy ``unanswered_response`` flat dict for backward compatibility.
"""
from __future__ import annotations


def lookup_gap_answer(gap_answers: dict, code: str):
    """Look up an answer value from a gap_answers dict — supports both schema versions.

    Searches the new ``sections`` array first; falls back to the legacy
    ``unanswered_response`` flat dict.

    Args:
        gap_answers: Full gap_answers dict from Step 4.
        code: OASIS field code (e.g. "C0500", "GG0130").

    Returns:
        The raw answer value (any type), or None if not found.
    """
    # New format: sections array
    for section in gap_answers.get("sections", []):
        for question in section.get("questions", []):
            if code in question.get("field_codes", []):
                return question.get("answer")
    # Legacy format: unanswered_response flat dict
    entry = gap_answers.get("unanswered_response", {}).get(code)
    if isinstance(entry, dict):
        return entry.get("answer")
    return None
