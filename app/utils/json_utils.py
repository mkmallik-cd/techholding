"""
app.utils.json_utils — Shared JSON extraction and repair helpers.

Consolidates the three independent ``_extract_json_object`` implementations
that previously lived inside each generator service.  All callers should import
from here to avoid drift between individual copies.

Public API:
    extract_json_object(text)        — Extract first JSON object/array from LLM output.
    extract_json_array(text)         — Extract first JSON array (or object fallback) from LLM output.
    repair_truncated_json(text)      — Best-effort repair of a truncated JSON object.
    repair_truncated_array(text)     — Best-effort repair of a truncated JSON array.
"""

from __future__ import annotations

import json
import re


def extract_json_object(text: str) -> str:
    """Extract the first complete JSON object or array from LLM output text.

    Strips markdown fences (```json … ```), then attempts to parse the whole
    text.  On failure, uses a regex to find the outermost ``{…}`` or ``[…]``
    block.

    Args:
        text: Raw string returned by the LLM.

    Returns:
        A JSON-parseable string containing the first object or array found.

    Raises:
        ValueError: If no JSON structure can be located in *text*.
    """
    text = text.strip()
    # Remove opening and closing markdown code fences
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()

    # Fast path: the full text is already valid JSON
    try:
        json.loads(text)
        return text
    except Exception:
        pass

    # Locate outermost object OR array
    match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", text)
    if match:
        return match.group(1)

    raise ValueError(f"No JSON found in LLM response: {text[:500]!r}")


def extract_json_array(text: str) -> str:
    """Extract the first JSON array (or object fallback) from LLM output text.

    Strips markdown fences, then attempts to find a ``[…]`` block.
    Falls back to ``{…}`` when the LLM wrapped the array inside an object.

    Args:
        text: Raw string returned by the LLM.

    Returns:
        A JSON-parseable string containing the first array or object found.

    Raises:
        ValueError: If no JSON structure can be located in *text*.
    """
    text = text.strip()
    # Remove opening and closing markdown code fences
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()

    # Fast path: the full text is already valid JSON
    try:
        json.loads(text)
        return text
    except Exception:
        pass

    # Primary: look for an array
    match = re.search(r"(\[[\s\S]*\])", text)
    if match:
        return match.group(1)

    # Fallback: LLM sometimes wraps the array in an outer object
    match_obj = re.search(r"(\{[\s\S]*\})", text)
    if match_obj:
        return match_obj.group(1)

    raise ValueError(f"No JSON array found in LLM response: {text[:500]!r}")


def repair_truncated_json(text: str) -> dict:
    """Best-effort repair for a truncated JSON object.

    Strips fences, finds the last complete ``"KEY": {…}`` entry, and closes
    the outer ``{}`` so the result is parseable.  Returns an empty dict when
    repair fails.

    Args:
        text: Potentially truncated JSON string (object form).

    Returns:
        Parsed dict, partially-repaired dict, or ``{}`` on total failure.
    """
    text = text.strip()
    # Remove markdown code fences
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    # Keep everything up to and including the last complete "}: or "}"
    last_complete = text.rfind("},")
    if last_complete == -1:
        last_complete = text.rfind("}")
    if last_complete == -1:
        return {}

    # Close the outer object after the last complete inner entry
    truncated = text[: last_complete + 1] + "\n}"
    try:
        return json.loads(truncated)
    except Exception:
        return {}


def repair_truncated_array(text: str) -> list:
    """Best-effort repair for a truncated JSON array.

    Strips fences, finds the last complete ``{…}`` element, and wraps
    the salvaged elements in ``[…]``.  Returns an empty list on failure.

    Args:
        text: Potentially truncated JSON string (array form).

    Returns:
        Parsed list, partially-repaired list, or ``[]`` on total failure.
    """
    text = text.strip()
    # Remove markdown code fences
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    # Find the last complete object in the array
    last_complete = text.rfind("},")
    if last_complete == -1:
        last_complete = text.rfind("}")
    if last_complete == -1:
        return []

    # Locate the opening of the first array element
    start = text.find("{")
    if start == -1:
        return []

    # Re-wrap salvaged elements as a valid array
    repaired = "[" + text[start : last_complete + 1] + "]"
    try:
        return json.loads(repaired)
    except Exception:
        return []
