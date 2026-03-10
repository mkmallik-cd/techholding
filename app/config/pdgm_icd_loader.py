"""app.config.pdgm_icd_loader — CY2025 PDGM ICD-10 reference data.

Loads ``pdgm_icd10_cy2025.csv`` (74 718 codes) once at import time and exposes
helper functions used by the referral-packet and OASIS generators to inject
CMS-verified, clinically accurate ICD-10 codes into LLM prompts.

CSV columns (relevant subset)
------------------------------
DIAGNOSIS           ICD-10 code string (no dot — e.g. "M1711")
DESCRIPTION         Human-readable description
CLINICAL_GROUP      CMS PDGM clinical function letter (A-L or NA)
COMORBIDITY_GROUP   Comorbidity tier string (e.g. "Endocrine_3", "No_group")
MANIFESTATION_FLAG  "1" → manifestation code (cannot be listed first)
CODE_FIRST          "0" = no constraint; any other value = etiology must precede
UNACCEPTABLE_PDX    "1" → code is not acceptable as a primary diagnosis

Key insight: a code is ``primary_safe`` iff
    UNACCEPTABLE_PDX == "0" AND CODE_FIRST == "0" AND MANIFESTATION_FLAG == "0"

CMS PDGM clinical group letter → project PDGM group name mapping
-----------------------------------------------------------------
  A  Musculoskeletal Rehabilitation  }
  E  Surgical Aftercare              }  → MS_REHAB
  B  Neuro / Stroke Rehabilitation   → NEURO_STROKE
  C  Wounds                          → WOUNDS
  H  MMTA – Cardiac / Circulatory    → MMTA_CARDIAC
  L  MMTA – Pulmonary                → MMTA_RESPIRATORY
  K  MMTA – Infectious Disease       → MMTA_INFECTIOUS
"""
from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple

# ── Path to CSV (co-located with this module in app/config/) ──────────────────
_CSV_PATH = Path(__file__).parent / "pdgm_icd10_cy2025.csv"

# ── CMS letter(s) that map to each project PDGM group name ───────────────────
PDGM_GROUP_LETTERS: dict[str, list[str]] = {
    "MS_REHAB":          ["A", "E"],
    "NEURO_STROKE":      ["B"],
    "WOUNDS":            ["C"],
    "MMTA_CARDIAC":      ["H"],
    "MMTA_RESPIRATORY":  ["L"],
    "MMTA_INFECTIOUS":   ["K"],
    "EDGE_CASE":         [],
}

# ── Per-archetype ICD-10 code prefixes (used to select clinically relevant hits) ──
# Ordered from most-specific to least-specific; the loader stops after ``limit``
# safe-primary codes matching any prefix in order.
ARCHETYPE_ICD_PREFIXES: dict[str, list[str]] = {
    "total_knee_replacement":        ["M171", "M172", "Z9665", "Z9664", "Z47", "S72", "M79"],
    "chf_exacerbation":              ["I110", "I130", "I132", "I501", "I502",
                                      "I503", "I509", "I420"],
    "diabetic_foot_ulcer":           ["E1162", "E1152", "E1165", "E116", "E115", "L97", "E11"],
    "cva_stroke_rehab":              ["I63", "I69", "G811", "G812", "G813", "G814", "I64"],
    "hip_fracture":                  ["S72", "S79", "M800", "M801", "M802", "M804", "M845"],
    "copd_exacerbation":             ["J441", "J449", "J431", "J432", "J438", "J960", "J961"],
    "sepsis_cellulitis_recovery":    ["L0311", "L0312", "L0321", "L0331", "A403", "A408",
                                      "A409", "A4801", "A481"],
    "patient_refuses_cannot_answer": [],
}


# ── Data class for a single ICD row ──────────────────────────────────────────
class IcdEntry(NamedTuple):
    code: str          # e.g. "M1711"
    description: str   # e.g. "Unilateral primary osteoarthritis, right knee"
    clinical_group: str
    comorbidity_group: str
    primary_safe: bool  # True iff usable as standalone primary diagnosis


# ── Loader (runs once at import time) ────────────────────────────────────────
def _load_csv() -> dict[str, IcdEntry]:
    """Read CSV and return a dict keyed by DIAGNOSIS code string."""
    index: dict[str, IcdEntry] = {}
    with _CSV_PATH.open(encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            code = row["DIAGNOSIS"].strip()
            safe = (
                row["UNACCEPTABLE_PDX"] == "0"
                and row["CODE_FIRST"] == "0"
                and row["MANIFESTATION_FLAG"] == "0"
            )
            index[code] = IcdEntry(
                code=code,
                description=row["DESCRIPTION"].strip(),
                clinical_group=row["CLINICAL_GROUP"].strip(),
                comorbidity_group=row["COMORBIDITY_GROUP"].strip(),
                primary_safe=safe,
            )
    return index


# Module-level singleton — loaded once on first import, shared across all workers
_ICD_INDEX: dict[str, IcdEntry] = _load_csv()


# ── Public helpers ────────────────────────────────────────────────────────────

def is_valid_icd_code(code: str) -> bool:
    """True if the code (without dot) exists in the CY2025 PDGM table."""
    return code.replace(".", "").upper() in _ICD_INDEX


def get_code_info(code: str) -> IcdEntry | None:
    """Return the full IcdEntry for a code, or None if not found."""
    return _ICD_INDEX.get(code.replace(".", "").upper())


def is_valid_primary_dx(code: str, pdgm_group: str) -> bool:
    """True if:
      - code exists in the CSV
      - its CMS clinical_group matches the expected PDGM group letters
      - it is primary_safe (no CODE_FIRST / MANIFESTATION / UNACCEPTABLE_PDX flags)
    """
    entry = _ICD_INDEX.get(code.replace(".", "").upper())
    if entry is None:
        return False
    expected_letters = PDGM_GROUP_LETTERS.get(pdgm_group, [])
    return entry.primary_safe and entry.clinical_group in expected_letters


@lru_cache(maxsize=32)
def get_archetype_primary_codes(archetype: str, limit: int = 8) -> list[IcdEntry]:
    """Return up to ``limit`` CSV-verified, primary-safe ICD-10 codes for the archetype.

    Codes are filtered by  ``ARCHETYPE_ICD_PREFIXES[archetype]`` and ordered
    from most-specific prefix match to least-specific.  This gives the LLM a
    small, clinically focused list to choose from instead of thousands of codes.
    """
    prefixes = ARCHETYPE_ICD_PREFIXES.get(archetype, [])
    if not prefixes:
        return []

    pdgm_group = _archetype_to_pdgm_group(archetype)
    allowed_letters = PDGM_GROUP_LETTERS.get(pdgm_group, [])

    seen: set[str] = set()
    results: list[IcdEntry] = []

    for prefix in prefixes:
        if len(results) >= limit:
            break
        for code, entry in _ICD_INDEX.items():
            if code.startswith(prefix) and entry.primary_safe:
                # Include codes from the expected PDGM letters OR the broader group
                # (allows some clinically relevant cross-group codes, e.g. I11.0 for CHF)
                if entry.clinical_group in allowed_letters or entry.clinical_group in ["H", "K", "C", "B", "L", "E", "A"]:
                    if code not in seen:
                        seen.add(code)
                        results.append(entry)
                        if len(results) >= limit:
                            break

    return results[:limit]


def format_validated_codes_block(archetype: str, limit: int = 8) -> str:
    """Format a prompt-ready block listing CSV-verified primary DX codes.

    Returns an empty string for ``patient_refuses_cannot_answer`` (no validated
    primary codes needed) or if no matching codes are found.

    Example output::

        CMS CY2025-VERIFIED PRIMARY DIAGNOSIS OPTIONS (pick the most clinically
        appropriate for this patient — do NOT invent codes outside this list):
          M17.11  Unilateral primary osteoarthritis, right knee  [MS_REHAB ✓]
          M17.12  Unilateral primary osteoarthritis, left knee   [MS_REHAB ✓]
          Z47.1   Aftercare following joint replacement surgery  [MS_REHAB ✓]
          ...
    """
    codes = get_archetype_primary_codes(archetype, limit=limit)
    if not codes:
        return ""

    pdgm_group = _archetype_to_pdgm_group(archetype)
    lines = [
        "CMS CY2025-VERIFIED PRIMARY DIAGNOSIS OPTIONS"
        " (choose the most clinically appropriate — do NOT use codes outside this list"
        " or invent non-existent ICD-10 codes):",
    ]
    for entry in codes:
        # Format code with dot (e.g. M1711 -> M17.11)
        formatted = _format_icd_dot(entry.code)
        group_label = f"{pdgm_group} ✓" if entry.clinical_group in PDGM_GROUP_LETTERS.get(pdgm_group, []) else entry.clinical_group
        lines.append(f"  {formatted:<12}  {entry.description}  [{group_label}]")

    return "\n".join(lines)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _archetype_to_pdgm_group(archetype: str) -> str:
    """Return the PDGM group for an archetype (mirrors APPROVED_ARCHETYPES in constants.py)."""
    _map = {
        "total_knee_replacement":        "MS_REHAB",
        "chf_exacerbation":              "MMTA_CARDIAC",
        "diabetic_foot_ulcer":           "WOUNDS",
        "cva_stroke_rehab":              "NEURO_STROKE",
        "hip_fracture":                  "MS_REHAB",
        "copd_exacerbation":             "MMTA_RESPIRATORY",
        "sepsis_cellulitis_recovery":    "MMTA_INFECTIOUS",
        "patient_refuses_cannot_answer": "EDGE_CASE",
    }
    return _map.get(archetype, "EDGE_CASE")


def _format_icd_dot(code: str) -> str:
    """Insert a dot after position 3 to match standard ICD-10 display format.

    E.g. "M1711" → "M17.11", "I639" → "I63.9", "S72001D" → "S72.001D"
    """
    if len(code) <= 3:
        return code
    return f"{code[:3]}.{code[3:]}"
