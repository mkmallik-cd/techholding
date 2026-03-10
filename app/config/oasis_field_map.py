"""
app.config.oasis_field_map — Authoritative OASIS field definitions.

This module is intentionally isolated so the field map can be imported without
pulling in any LLM / service dependencies.

Keys   = OASIS fieldCode string (e.g. "M0069", "GG0130").
Values = {
    "question" : str               — human-readable question label
    "dataType" : str               — "string" | "date" | "enum" | "oasis_enum"
                                     | "object" | "array" | "integer" | "boolean"
                                     | "state_code"
    "options"  : list[str] | None  — option strings in "code=label" or plain-label
                                     format; None for free-form fields
}

Inlined here so the worker has zero runtime file-system dependency on the
original OASIS_MASTER_GENERIC_TEMPLATE.json artefact.

Renamed from TEMPLATE_FIELD_MAP (gap_answers_generator.py) to OASIS_FIELD_MAP
to clarify scope and avoid the generic "template" label.
"""

from __future__ import annotations

# ── OASIS field map (130+ fields) ─────────────────────────────────────────────
OASIS_FIELD_MAP: dict[str, dict] = {
    # ── Patient Tracking / Administrative ─────────────────────────────────────
    "M0010": {"question": "CMS Certification Number", "dataType": "string", "options": None},
    "M0014": {"question": "Branch State", "dataType": "string", "options": None},
    "M0018": {"question": "NPI for attending physician", "dataType": "string", "options": None},
    "M0020": {"question": "Patient ID Number", "dataType": "string", "options": None},
    "M0030": {"question": "Start of Care Date", "dataType": "date", "options": None},
    "M0040": {"question": "Patient Name", "dataType": "string", "options": None},
    "M0050": {"question": "Patient State of Residence", "dataType": "state_code", "options": None},
    "M0060": {"question": "Patient Zip Code", "dataType": "string", "options": None},
    "M0066": {"question": "Birth Date", "dataType": "date", "options": None},
    "M0069": {
        "question": "Gender",
        "dataType": "enum",
        "options": ["M=Male", "F=Female"],
    },
    "M0080": {
        "question": "Discipline of person completing assessment",
        "dataType": "oasis_enum",
        "options": ["1=RN", "2=PT", "3=SLP/ST", "4=OT"],
    },
    "M0090": {"question": "Date Assessment Completed", "dataType": "date", "options": None},
    "M0100": {
        "question": "Reason assessment is being completed",
        "dataType": "oasis_enum",
        "options": [
            "1=Start of Care - further visits planned",
            "3=Resumption of care (after inpatient stay)",
            "4=Recertification (follow-up) reassessment",
            "5=Other follow-up",
            "6=Transferred to inpatient - not discharged",
            "7=Transferred to inpatient - discharged",
            "8=Death at home",
            "9=Discharge from agency",
        ],
    },
    "M0150": {
        "question": "Current Payment Sources for Home Care",
        "dataType": "oasis_enum",
        "options": [
            "1=Medicare (traditional fee-for-service)",
            "2=Medicare (HMO/managed care)",
            "3=Medicaid (traditional fee-for-service)",
            "4=Medicaid (HMO/managed care)",
            "5=Worker's Compensation",
            "6=VA",
            "7=Private insurance",
            "8=Private pay",
            "9=Other",
        ],
    },
    # ── Patient History & Diagnosis ───────────────────────────────────────────
    "M1000": {
        "question": "Inpatient facility discharge in last 14 days",
        "dataType": "oasis_enum",
        "options": [
            "NA=Patient was not discharged from inpatient facility",
            "1=Long-term nursing facility (NF)",
            "2=Skilled nursing facility (SNF/TCU)",
            "3=Short-stay acute hospital (IPPS)",
            "4=Long-term care hospital (LTCH)",
            "5=Inpatient rehabilitation hospital or unit (IRF)",
            "6=Psychiatric hospital or unit",
        ],
    },
    "M1005": {"question": "Inpatient Discharge Date (most recent)", "dataType": "date", "options": None},
    "M1021": {"question": "Primary Diagnosis", "dataType": "object", "options": None},
    "M1023": {"question": "Other Diagnoses", "dataType": "array", "options": None},
    "M1028": {"question": "Active Diagnoses - Comorbidities", "dataType": "object", "options": None},
    "M1060": {"question": "Height and Weight", "dataType": "object", "options": None},
    "K0520": {
        "question": "Nutritional Approaches",
        "dataType": "array",
        "options": [
            "Parenteral/IV feeding",
            "Feeding tube",
            "Mechanically altered diet",
            "Therapeutic diet",
            "Fluid restriction",
        ],
    },
    "O0110": {"question": "Special Treatments, Procedures, and Programs", "dataType": "object", "options": None},
    "ALLERGIES": {"question": "Allergies", "dataType": "object", "options": None},
    # ── Living Arrangements ───────────────────────────────────────────────────
    "M1100": {
        "question": "Patient Living Situation",
        "dataType": "oasis_enum",
        "options": [
            "01=Lives alone - no assistance",
            "02=Lives alone - regular nighttime assistance",
            "03=Lives alone - regular daytime assistance",
            "04=Lives alone - frequent assistance",
            "05=Lives alone - continuous assistance",
            "06=Lives with other persons - no assistance",
            "07=Lives with other persons - regular assistance",
            "08=Lives with other persons - frequent assistance",
            "09=Lives with other persons - continuous assistance",
        ],
    },
    "HOUSEHOLD_SUPPORT": {"question": "Support Person", "dataType": "object", "options": None},
    "HOME_SAFETY_EVAL": {"question": "Home Safety Evaluation Completed", "dataType": "boolean", "options": None},
    "HOME_SAFETY_PROBLEMS": {"question": "Home Safety Problems Identified", "dataType": "array", "options": None},
    # ── Sensory ───────────────────────────────────────────────────────────────
    "B0200": {
        "question": "Hearing Ability",
        "dataType": "oasis_enum",
        "options": [
            "0=Adequate - no difficulty",
            "1=Minimal difficulty",
            "2=Moderate difficulty - must speak distinctly",
            "3=Highly impaired",
        ],
    },
    "B1000": {
        "question": "Vision Ability",
        "dataType": "oasis_enum",
        "options": [
            "0=Adequate - sees fine detail",
            "1=Impaired - sees large print only",
            "2=Moderately impaired - headlines only",
            "3=Highly impaired - no detail",
            "4=Severely impaired - no vision",
        ],
    },
    "B1300": {
        "question": "Health Literacy",
        "dataType": "oasis_enum",
        "options": [
            "0=Never needs help",
            "1=Rarely needs help",
            "2=Sometimes needs help",
            "3=Often needs help",
            "4=Always needs help",
        ],
    },
    # ── Integumentary ─────────────────────────────────────────────────────────
    "M1306": {
        "question": "Unhealed pressure ulcer/injury at Stage 2 or higher?",
        "dataType": "oasis_enum",
        "options": ["0=No", "1=Yes"],
    },
    "M1311": {"question": "Current Number of Unhealed Pressure Ulcers at Each Stage", "dataType": "object", "options": None},
    "M1322": {"question": "Current Number of Stage 1 Pressure Injuries", "dataType": "integer", "options": None},
    "M1330": {
        "question": "Does patient have a Stasis Ulcer?",
        "dataType": "oasis_enum",
        "options": ["0=No", "1=Yes"],
    },
    # ── Respiratory ───────────────────────────────────────────────────────────
    "M1400": {
        "question": "When is patient dyspneic or short of breath?",
        "dataType": "oasis_enum",
        "options": [
            "0=Patient is not short of breath",
            "1=Short of breath only with exertion",
            "2=Short of breath with minimal exertion",
            "3=Short of breath at rest",
            "4=Requires oxygen",
        ],
    },
    "OXYGEN_SATURATION": {"question": "Oxygen Saturation", "dataType": "object", "options": None},
    "RESPIRATORY_RATE": {"question": "Respiratory Rate", "dataType": "object", "options": None},
    # ── Cardiac ───────────────────────────────────────────────────────────────
    "BLOOD_PRESSURE": {"question": "Blood Pressure", "dataType": "object", "options": None},
    "HEART_RATE": {"question": "Heart Rate / Pulse", "dataType": "object", "options": None},
    # ── Neuro / Emotional / Behavioral ────────────────────────────────────────
    "M1700": {
        "question": "Cognitive Functioning",
        "dataType": "oasis_enum",
        "options": [
            "0=Alert/oriented, can focus and shift attention",
            "1=Difficulty focusing or shifting attention",
            "2=Disoriented, cannot focus",
            "3=Comatose or no observable response",
        ],
    },
    "M1710": {
        "question": "When Confused (past 14 days)",
        "dataType": "oasis_enum",
        "options": [
            "0=Patient not confused",
            "1=Confused 50% or less of time",
            "2=Confused more than 50% of time",
            "3=Consistently confused",
        ],
    },
    "M1720": {
        "question": "When Anxious (past 14 days)",
        "dataType": "oasis_enum",
        "options": [
            "0=Patient not anxious",
            "1=Anxious 50% or less of time",
            "2=Anxious more than 50% of time",
            "3=Consistently anxious",
        ],
    },
    "M1740": {
        "question": "Psychiatric or Behavioral Symptoms (1 or more times per week)",
        "dataType": "array",
        "options": [
            "Memory deficit",
            "Impaired decision making",
            "Verbal disruption",
            "Physical aggression",
            "Disruptive/inappropriate",
            "Delusional/hallucinatory",
            "None",
        ],
    },
    # ── Elimination ───────────────────────────────────────────────────────────
    "M1610": {
        "question": "Urinary Incontinence or Urinary Catheter Presence",
        "dataType": "oasis_enum",
        "options": [
            "0=No incontinence or catheter",
            "1=Continent with catheter/ostomy",
            "2=Incontinence 50% or less of time",
            "3=Incontinence more than 50% of time",
            "4=Totally incontinent or indwelling catheter",
        ],
    },
    "M1620": {
        "question": "Bowel Incontinence Frequency",
        "dataType": "oasis_enum",
        "options": [
            "0=Continent or no incontinence",
            "1=Rare incontinence (1 per week or less)",
            "2=Occasional (2-3 times per week)",
            "3=Frequent (more than 3 times per week)",
        ],
    },
    # ── Nutritional Status ────────────────────────────────────────────────────
    "K0510": {
        "question": "Nutritional Status",
        "dataType": "oasis_enum",
        "options": [
            "0=Adequate",
            "1=Predicted inadequate",
            "2=Altered - less than requirements",
            "3=Altered - more than requirements",
        ],
    },
    # ── Medications ───────────────────────────────────────────────────────────
    "N0415": {"question": "High-Risk Drug Classes: Use and Indication", "dataType": "array", "options": None},
    "IV_ACCESS": {"question": "Intravenous Access", "dataType": "object", "options": None},
    # ── Functional Abilities and Goals (GG) ──────────────────────────────────
    "GG0100": {"question": "Prior Functioning: Everyday Activities (BASELINE)", "dataType": "object", "options": None},
    "GG0130": {"question": "Self-Care: Admission Performance", "dataType": "object", "options": None},
    "GG0170": {"question": "Mobility: Admission Performance and Discharge Goals", "dataType": "object", "options": None},
    # ── Activities of Daily Living (ADLs) ─────────────────────────────────────
    "M1800": {
        "question": "Grooming",
        "dataType": "oasis_enum",
        "options": [
            "0=Able independently",
            "1=Grooming utensils/clothing laid out",
            "2=Needs reminding",
            "3=Needs partial assistance",
            "4=Unable",
        ],
    },
    "M1830": {
        "question": "Bathing",
        "dataType": "oasis_enum",
        "options": [
            "0=Able independently",
            "1=Reminding/supervision only",
            "2=Intermittent assistance",
            "3=Continuous assistance",
            "4=Unable",
        ],
    },
    "M1850": {
        "question": "Transferring",
        "dataType": "oasis_enum",
        "options": [
            "0=Able independently",
            "1=Minimal assistance/device",
            "2=Needs human assistance",
            "3=Unable",
            "4=Bedfast",
        ],
    },
    "M1860": {
        "question": "Ambulation/Locomotion",
        "dataType": "oasis_enum",
        "options": [
            "0=Able independently",
            "1=With one-handed device",
            "2=With two-handed device",
            "3=With walker/crutches/cane",
            "4=With human assistance",
            "5=Non-ambulatory, can wheel self",
            "6=Non-ambulatory, cannot wheel self",
        ],
    },
    "M1870": {
        "question": "Feeding or Eating",
        "dataType": "oasis_enum",
        "options": [
            "0=Able independently",
            "1=Reminding/setup only",
            "2=Minimal assistance",
            "3=Needs human assistance",
            "4=Unable - tube feeding",
        ],
    },
    # ── Care Management ───────────────────────────────────────────────────────
    "M2102": {
        "question": "Types and Sources of Assistance",
        "dataType": "object",
        "options": [
            "0=No assistance needed",
            "1=Assistance needed but not provided",
            "2=Assistance provided",
            "3=Intensive assistance provided",
        ],
    },
    "ADVANCE_DIRECTIVES": {"question": "Advance Directives on File", "dataType": "object", "options": None},
}
