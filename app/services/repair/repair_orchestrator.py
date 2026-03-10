"""Repair orchestration: load artifacts from disk, apply fixes, write back."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from app.services.repair.algorithmic_fixes import fix_gap_answers, fix_gold_standard

logger = logging.getLogger(__name__)


def repair_gap_answers_artifact(gap_answers_path: str) -> list[str]:
    """Load tap_tap_gap_answers.json, apply fixes, overwrite in place.

    Returns the list of fix descriptions that were applied.
    """
    path = Path(gap_answers_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    data, fixes = fix_gap_answers(data)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    logger.info(
        "gap_answers repaired (%d fix(es)): %s",
        len(fixes),
        fixes,
    )
    return fixes


def repair_gold_standard_artifact(
    gold_standard_path: str,
    validation_errors: list[dict],
) -> list[str]:
    """Load oasis_gold_standard.json, apply algorithmic fixes, overwrite in place.

    Returns the list of fix descriptions that were applied.
    """
    path = Path(gold_standard_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    data, fixes = fix_gold_standard(data, validation_errors)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    logger.info(
        "gold_standard repaired (%d fix(es)): %s",
        len(fixes),
        fixes,
    )
    return fixes
