"""Centralised LLM prompt templates for all pipeline steps.

Every prompt template is a plain Python string with ``{placeholder}`` variables
that are filled via ``.format(**kwargs)`` at call time.  Literal curly-braces
that should appear in the rendered output are written as ``{{`` / ``}}``.

Templates are grouped by pipeline step to make them easy to find and edit.
"""

# ─────────────────────────────────────────────────────────────────────────────
# Step 1 — Patient Metadata
# ─────────────────────────────────────────────────────────────────────────────
# Placeholders: {patient_id}, {today}, {seed}

PATIENT_METADATA_PROMPT_TEMPLATE = """\
You are generating metadata for a synthetic home-health patient record. \
Output ONLY a single JSON object — no markdown fences, no commentary.

STEP 1 — PRD 0D.1 metadata.json spec. The output JSON must contain EXACTLY these keys and no others:
  "patient_id"          — use the value provided below
  "source"              — always "PHASE_A"
  "archetype"           — MUST be one of the approved snake_case names listed below
  "pdgm_group"          — MUST match the archetype's PDGM group (see mapping below)
  "admission_source"    — "hospital" or "community"
  "episode_timing"      — "early" (days 0-29) or "late" (days 30+)
  "age_bracket"         — one of "18-64", "65-74", "75-84", "85+"
  "gender"              — "M" or "F"
  "comorbidity_count"   — integer >= 0
  "has_ambient_scribe"  — boolean — set true for ~70% of records
  "has_clinical_note"   — boolean — clinical summary present? set true for ~70%
  "f2f_status"          — "present_complete", "present_incomplete", or "missing"
                          (vary: 60% present_complete, 20% present_incomplete, 20% missing)
  "referral_format"     — "clean_emr", "messy_fax", or "minimal"
  "validation_status"   — always "pending"
  "generated_by"        — model short-name, e.g. "claude-sonnet"
  "generated_date"      — use the date provided below (ISO format)
  "clinician_validated" — always false

APPROVED ARCHETYPE → PDGM_GROUP mapping (use exact snake_case key):
  total_knee_replacement        → MS_REHAB
  chf_exacerbation              → MMTA_CARDIAC
  diabetic_foot_ulcer           → WOUNDS
  cva_stroke_rehab              → NEURO_STROKE
  hip_fracture                  → MS_REHAB
  copd_exacerbation             → MMTA_RESPIRATORY
  sepsis_cellulitis_recovery    → MMTA_INFECTIOUS
  patient_refuses_cannot_answer → EDGE_CASE

patient_id: {patient_id}
generated_date: {today}
seed (for variation): {seed}
"""

# ─────────────────────────────────────────────────────────────────────────────
# Step 2 — Referral Packet
# ─────────────────────────────────────────────────────────────────────────────
# Placeholders: {format_instruction}, {archetype}, {pdgm_group}, {age_hint},
#   {gender_full}, {admission_source}, {admission_source_desc}, {episode_timing},
#   {episode_timing_desc}, {comorbidity_count}, {primary_hint},
#   {secondary_hints_text}, {high_risk_section}, {services_hint},
#   {homebound_reason}, {f2f_instruction}

REFERRAL_PACKET_PROMPT_TEMPLATE = """\
You are generating a synthetic home-health patient referral document for a test dataset.
Output ONLY the plain-text referral — no JSON, no markdown, no commentary before or after the referral.

{format_instruction}

PATIENT ARCHETYPE CONTEXT (use this to drive all clinical content):
  archetype:         {archetype}
  pdgm_group:        {pdgm_group}
  age:               approximately {age_hint} years old
  gender:            {gender_full}
  admission_source:  {admission_source} (patient was discharged from {admission_source_desc})
  episode_timing:    {episode_timing} ({episode_timing_desc})
  comorbidity_count: {comorbidity_count}

ICD-10 GUIDANCE (use these exact codes — do NOT invent invalid codes):
  Primary diagnosis hint: {primary_hint}
  Secondary diagnoses to include ({comorbidity_count} comorbidities):
{secondary_hints_text}

{validated_codes_section}

HIGH-RISK MEDICATIONS to include in the discharge medication list:
{high_risk_section}

REQUIRED SECTIONS — include ALL of the following. Do not skip any.

1. PATIENT HEADER
   Generate a synthetic patient: realistic first name + last name, DOB (consistent with age {age_hint}),
   gender {gender_full}, synthetic 9-digit MRN.

2. REFERRAL DATES
   Generate: Hospital Admit Date, Hospital Discharge Date (2-7 days post-admit),
   Referral Date (same as or 1 day after discharge), Expected SOC Date (1-2 days after referral).
   All dates must be internally consistent. Use MM/DD/YYYY format.
   Use dates near 2026-03-09 (March 2026).

3. REFERRING PHYSICIAN
   Generate: Dr. [Firstname Lastname], MD, synthetic 10-digit NPI (starts with 1), specialty.

4. PRIMARY DIAGNOSIS
   Full ICD-10 code + description per guidance above.

5. SECONDARY DIAGNOSES
   {comorbidity_count} secondary diagnoses with ICD-10 codes per guidance above.

6. HISTORY & PHYSICAL (H&P)
   Clinical narrative matching the archetype. Must reference the same diagnoses listed above.
   Use realistic clinical abbreviations and objective findings.

7. DISCHARGE MEDICATION LIST  ← this is Layer 1 of medication_list.json
   Format: numbered list, one med per line.
   Each line: [Name] [dose] [route] [frequency] [⚠ HIGH RISK — reason if applicable]
   Example: "Warfarin 5 mg oral daily ⚠ HIGH RISK — anticoagulant"
   Include ALL high-risk medications listed above (do not omit any).
   Add 3-5 additional archetype-appropriate medications (name, dose, route, frequency).
   HIGH RISK flag is REQUIRED for: anticoagulants, insulin, opioids, digoxin.
   Total: at least 6 medications.

8. ORDERED HOME HEALTH SERVICES
   Use this guidance: {services_hint}

9. HOMEBOUND STATUS
   Must include objective measures.
   Use this homebound rationale: {homebound_reason}

10. PHYSICIAN ORDERS
    Brief physician order section (2-4 orders matching the clinical scenario).

11. FACE-TO-FACE (F2F) DOCUMENTATION
    {f2f_instruction}

Generate the referral now:"""

# ─────────────────────────────────────────────────────────────────────────────
# Step 3a — Medication List
# ─────────────────────────────────────────────────────────────────────────────
# Placeholders: {referral_text}, {archetype}

MEDICATION_LIST_PROMPT_TEMPLATE = """\
You are building a structured medication reconciliation record for a synthetic home-health patient dataset.

REFERRAL DOCUMENT (extract the hospital discharge medication list from this):
---
{referral_text}
---

Your task: produce a JSON object with exactly these three top-level keys:
  "hospital_discharge_list"
  "patient_pill_bottles"
  "patient_reported_otc"
  "reconciliation_issues"

─────────────────────────────────────────────────────────────────
LAYER 1 — hospital_discharge_list
─────────────────────────────────────────────────────────────────
Extract every medication from the DISCHARGE MEDICATION LIST section of the referral above.
For each medication use this object shape:
  {{
    "name":        "generic name (capitalised)",
    "dose":        "e.g. 5 mg",
    "route":       "oral | subcutaneous | IV | topical | inhaled | other",
    "frequency":   "e.g. daily | twice daily | every 4-6 hours PRN",
    "is_high_risk": true   ← set true for: anticoagulants (warfarin, enoxaparin, heparin, apixaban,
                                           rivaroxaban, dabigatran), insulin, opioids (oxycodone,
                                           morphine, hydromorphone, fentanyl, tramadol), digoxin
  }}

─────────────────────────────────────────────────────────────────
LAYER 2 — patient_pill_bottles
─────────────────────────────────────────────────────────────────
Represent what was physically found at the patient's home. Start from the hospital_discharge_list
and apply EXACTLY these four required discrepancies (the dataset needs all four to test the
OASIS reconciliation pipeline):

  DISCREPANCY 1 — missing_at_home:
    Omit ONE high-risk medication from Layer 1 entirely from patient_pill_bottles.
    (Preferred candidate: Warfarin, or the first anticoagulant if Warfarin not present.)

  DISCREPANCY 2 — wrong_dose_bottle:
    Include ONE medication but set its dose to a DIFFERENT value than Layer 1.
    (e.g. discharge says Metoprolol 50 mg; bottle found at home says 25 mg)
    Add a "note" field: "bottle dose differs from discharge prescription of [Layer1 dose]"

All remaining Layer 1 medications (minus discrepancy 1) appear in patient_pill_bottles
with their correct dose, route, and frequency.

─────────────────────────────────────────────────────────────────
LAYER 3 — patient_reported_otc
─────────────────────────────────────────────────────────────────
Include 2-3 items the patient verbally reports taking.
Apply EXACTLY these two discrepancies:

  DISCREPANCY 3 — otc_not_on_list:
    At least one supplement not mentioned anywhere in the referral.
    (e.g. Fish Oil 1000 mg oral daily, Vitamin D3 2000 IU oral daily, CoQ10 100 mg oral daily)
    Add "note": "not on any official list"

  DISCREPANCY 4 — dose_discrepancy_layers:
    One item from patient_pill_bottles where the patient says they take a DIFFERENT dose
    than what is on the bottle.
    (e.g. bottle says Lisinopril 10 mg; patient reports taking 20 mg)
    Add "note": "patient reports taking [patient-stated dose]; bottle label reads [bottle dose]"

─────────────────────────────────────────────────────────────────
reconciliation_issues array
─────────────────────────────────────────────────────────────────
List all four discrepancies as separate objects:
  {{
    "discrepancy_type": "missing_at_home | wrong_dose_bottle | otc_not_on_list | dose_discrepancy_layers",
    "medication": "name of the affected medication",
    "description": "one sentence describing the issue"
  }}

─────────────────────────────────────────────────────────────────
STRICT JSON OUTPUT RULES
─────────────────────────────────────────────────────────────────
• Output ONLY a single JSON object — no markdown fences, no commentary.
• Do not add any keys other than the four listed above.
• Every list item must be a valid JSON object.
• reconciliation_issues must contain exactly 4 items (one per discrepancy type).
• Archetype context for clinical plausibility: {archetype}

Generate the medication_list.json now:"""

# ─────────────────────────────────────────────────────────────────────────────
# Step 3b — Ambient Scribe
# ─────────────────────────────────────────────────────────────────────────────
# Placeholders: {referral_text}, {archetype}, {age_bracket}, {gender_full},
#   {comorbidity_count}, {vitals_context}, {physical_focus}, {adl_picture},
#   {home_safety}, {typical_goal}, {cognition_mood}

AMBIENT_SCRIBE_PROMPT_TEMPLATE = """\
You are generating a synthetic home-health ambient nursing assessment note for a test dataset.

Output ONLY the plain-text nursing note — no JSON, no markdown, no commentary before or after.

========== REFERRAL DOCUMENT (your primary source) ==========
{referral_text}
========== END REFERRAL DOCUMENT ==========

TASK: Write the Start of Care nursing visit note that would follow this referral.
This note MUST be consistent with the referral above — same patient name/DOB/MRN, same diagnoses,
same medications, same visit dates (use the Expected SOC Date from the referral as the visit date).

FORMAT RULES:
- Nurse voice, first person throughout ("I arrived...", "I assessed...", "I observed...")
- Timestamps in HH:MM 24-hour format. Start at 09:30. Each section ~5-15 minutes apart.
  Example: 09:30 arrival paragraph, VITAL SIGNS — 09:35, PHYSICAL ASSESSMENT — 09:45, etc.
- Plain text — NO markdown, NO bullet points in the main body (prose paragraphs only)
- Functional findings must be CONSISTENT with the referral but MORE DETAILED and specific
  (add exact measurements, laterality, objective scores, specific patient quotes)
- Clinician name: generate a realistic RN name (do not reuse the referring physician name)
- Length: 600-900 words

CLINICAL CONTEXT FOR THIS ARCHETYPE ({archetype}):
  Age bracket: {age_bracket}  |  Gender: {gender_full}  |  Comorbidities: {comorbidity_count}
  
  Vital signs guidance:
  {vitals_context}
  
  Physical assessment focus:
  {physical_focus}
  
  ADL picture:
  {adl_picture}
  
  Home safety focus:
  {home_safety}
  
  Typical SMART goal for this archetype:
  {typical_goal}
  
  Cognition and mood approach:
  {cognition_mood}

REQUIRED DOCUMENT HEADER (use EXACT format):
AMBIENT NURSING ASSESSMENT — START OF CARE

Patient: [copy name from referral], DOB: [copy DOB from referral], MRN: [copy MRN from referral]
Visit Date: [SOC date from referral]   Time: 09:30
Clinician: [Generated RN name], RN
Supervising Physician: [copy physician name from referral]

[09:30 arrival paragraph — first person, 2-3 sentences introducing yourself, confirming patient identity and reason for visit]

REQUIRED SECTIONS — include ALL 7 in this EXACT order with EXACT header text:

VITAL SIGNS — [timestamp e.g. 09:35]
[State vitals in this exact format, each on its own line:]
BP: [value] ([position, e.g. sitting], [arm, e.g. right arm])
HR: [value], [rhythm, e.g. regular]
RR: [value], [effort descriptor, e.g. unlabored]
O2 saturation: [value]% on [O2 source, e.g. room air or 2 L/min via nasal cannula]
Temperature: [value]°F
Weight: [value] lbs[add comparison if clinically relevant, e.g. "(up 3 lbs from discharge weight of X lbs)"]
Pain: [X]/10, [location], [brief quality descriptor]
[1-2 sentences in first person interpreting the vitals — e.g. "I noted the blood pressure remained elevated..."]

PHYSICAL ASSESSMENT — [timestamp]
[2-4 sentences first-person prose covering archetype-relevant body systems with specific objective findings.
 Include: relevant abnormal findings, measurements with units, laterality, comparison to referral.
 Use clinical abbreviations (crackles, JVD, 2+ pitting edema, etc.) but spell out on first use.]

ADL OBSERVATIONS — [timestamp]
[2-3 sentences first-person prose. Use EXACT assistance level terminology:]
  Exact levels: "Independent", "Independent with setup/cleanup", "Minimal assistance",
  "Moderate assistance", "Substantial/Maximal assistance", "Dependent"
[Include: what patient attempted, what level of assist was needed, specific ADLs observed,
 patient response/fatigue level, any adaptive equipment in use.]

HOME SAFETY OBSERVATION — [timestamp]
[2-3 sentences first-person prose. Specific hazards observed (name them — not generic).
 Environmental barriers. Fall risk factors. Modifications recommended. Caregiver availability.]

PATIENT GOALS — [timestamp]
[Format exactly as:]
Patient stated: "[Direct quote in patient's own words — 1 sentence expressing their main goal]"
Clinical goal: [SMART goal — one sentence with specific measurable metric and timeframe, aligned to archetype]

PAIN ASSESSMENT — [timestamp]
[2-3 sentences: location, X/10 rating, quality descriptor (sharp/dull/aching/burning/pressure), 
 aggravating factors, relieving factors, functional impact on ADLs.]

PLAN & FOLLOW-UP — [timestamp]
[2-3 sentences first-person prose: next visit date and focus, any physician orders to confirm or clarify,
 one key education topic provided this visit with patient verbalization of understanding documented.
 Use "SN Xw#" format for visit frequency (e.g. "SN 3w4 per POC").]

STRICT PROHIBITIONS — these terms must NEVER appear anywhere in your output:
❌ "BIMS score"
❌ "BIMS interview"
❌ "PHQ-2"
❌ "PHQ-9"
❌ "PHQ2"
❌ "PHQ9"
→ For cognition: write "alert and oriented x4 (person/place/time/event)" or "oriented x3" etc.
→ For mood: write descriptively ("appeared anxious but cooperative", "tearful at times, engaged with teaching")
→ These standardised screening tools are documented in gap-answer sections only, NOT in the ambient note.
"""

# ─────────────────────────────────────────────────────────────────────────────
# Step 4 — Gap Answers (two-phase: filter then answer)
# ─────────────────────────────────────────────────────────────────────────────

# Phase 2: filter — identify which OASIS codes are answerable from documents.
# Placeholders: {referral_text}, {scribe_section}, {field_codes_json}
GAP_FILTER_PROMPT_TEMPLATE = """\
You are an OASIS clinical documentation assistant analyzing a home health patient record.

Given the patient documents below, identify which OASIS field codes from the provided list
can already be answered (fully or substantially) from the available clinical documentation.

RULES:
- Return ONLY the field codes that are CLEARLY AND COMPLETELY ANSWERABLE from the documentation.
- If a code is ambiguous, missing, or only partially answerable, do NOT include it.
- NEVER include BIMS codes (C0100, C0200, C0300, C0300A, C0300B, C0300C, C0400, C0400A,
  C0400B, C0400C, C0500, C1310) — these require live cognitive testing.
- NEVER include PHQ mood codes (D0150A1 through D0150I2, D0160, PHQ_MOOD_INTERVIEW) —
  these require a live structured mood interview.
- NEVER include GG discharge goal codes (GG0100, GG0110, GG0130, GG0170, GG0170C) —
  these require clinical judgment about expected functional recovery.
- Return a JSON object with a single key "answerable_codes" containing an array of strings.

PATIENT DOCUMENTATION:
--- REFERRAL PACKET ---
{referral_text}

{scribe_section}

FIELD CODE LIST TO EVALUATE:
{field_codes_json}

Respond with ONLY valid JSON:
{{"answerable_codes": ["CODE1", "CODE2", ...]}}
"""

# Phase 3: answer — generate OASIS answers for all mandatory + answerable codes.
# Placeholders: {archetype}, {diagnosis_context}, {has_ambient_scribe},
#   {referral_text}, {scribe_section}, {fields_with_metadata_json}
GAP_ANSWER_PROMPT_TEMPLATE = """\
You are an expert OASIS-E1 clinical documentation specialist generating synthetic patient dataset answers.

PATIENT CONTEXT:
- Archetype: {archetype}
- Primary Diagnosis Context: {diagnosis_context}
- Has Ambient Scribe Note: {has_ambient_scribe}

--- REFERRAL PACKET ---
{referral_text}

{scribe_section}

TASK:
Generate clinically realistic OASIS answers for ALL of the field codes listed below.
Every answer MUST be clinically consistent with the patient's presentation described above.

CRITICAL SCORING RULES — READ CAREFULLY:

1. BIMS (C section — MANDATORY):
   - C0100: Cognitive Assessment — 0=No, 1=Yes (whether BIMS was administered)
   - C0200: Words repeated correctly (0=none, 1=one, 2=two, 3=all three words "sock/blue/bed")
   - C0300: Temporal orientation grouping code (use 99 if unable)
   - C0300A: Year correct — 0=incorrect, 1=missed by >5y, 2=missed by 2-5y, 3=correct
   - C0300B: Month correct — 0=incorrect, 1=missed by >1mo, 2=correct
   - C0300C: Day of week correct — 0=incorrect, 1=correct
   - C0400: Recall grouping code (use 99 if unable)
   - C0400A: Recall "sock" — 0=could not recall, 1=yes with cue, 2=no cue needed
   - C0400B: Recall "blue" — 0=could not recall, 1=yes with cue, 2=no cue needed
   - C0400C: Recall "bed" — 0=could not recall, 1=yes with cue, 2=no cue needed
   - C0500: BIMS TOTAL — MUST EQUAL EXACTLY: C0200 + C0300A + C0300B + C0300C + C0400A + C0400B + C0400C (range 0-15)
   - C1310: Brief Cognitive Interview for RCA — 0=No, 1=Yes
   - Use 99 for any code if patient was unable/refused to participate in BIMS

2. PHQ-9 (D section — MANDATORY — all 18 sub-codes + total):
   - D0150A1 through D0150I1: Symptom presence — Column 1 (0=symptom not present, 1=symptom present)
   - D0150A2 through D0150I2: Frequency — Column 2 (0=not at all, 1=several days, 2=more than half the days, 3=nearly every day)
   - D0160: PHQ TOTAL — MUST EQUAL EXACTLY the sum described below
   - PHQ_MOOD_INTERVIEW: "PHQ-9 Mood Interview" — use "completed" or "99 - Unable to complete"

   ⚠️  CRITICAL PHQ-2 SCREENING GATE (CMS mandatory rule — violations cause dataset rejection):
   Step 1 — Score the PHQ-2 screen: screen_score = D0150A1 + D0150B1
   Step 2 — If screen_score < 3 (negative screen):
     • D0150C1 through D0150I1 MUST ALL be null (NOT 0 — use null/None)
     • D0150C2 through D0150I2 MUST ALL be null
     • D0160 = D0150A2 (if A1=1) + D0150B2 (if B1=1) ONLY — items C through I excluded
   Step 3 — If screen_score >= 3 (positive screen):
     • Administer all 9 items A through I normally
     • D0160 = sum of all D0150X2 values where the corresponding D0150X1 = 1

   Example (screen negative): A1=1, B1=1 → screen=2 < 3 → C1=null, D1=null … I1=null,
     C2=null … I2=null, D0160 = A2 + B2 (if those symptoms present)
   NEVER set D0150C-I items to any non-null value when screen_score < 3.

3. GG Discharge Goals (GG0170 items — MANDATORY — set EXPECTED DISCHARGE status, not current):
   Scale: 01=Dependent, 02=Substantial/Maximal assist, 03=Partial/Moderate assist,
          04=Supervision/touching assist, 05=Setup/cleanup only, 06=Independent
   Exceptions: 07=Refused, 09=Not applicable, 10=Equipment unavailable, 88=Not attempted

4. OASIS M-codes — common value ranges:
   - M0100: 01=SOC, 03=ROC, 04=Recertification, 06=Transfer, 09=Discharge
   - M1021/M1023: Primary/Other diagnosis with ICD-10 code and symptom control rating 0-4
   - M1060: Height in inches, Weight in pounds (e.g., "66 inches, 172 lbs")
   - M1400: Dyspnea — 0=No dyspnea, 1=With exertion, 2=With ADLs, 3=At rest

5. Non-OASIS narrative codes (ALLERGIES, VITAL_SIGNS, ACTIVITIES_PERMITTED, etc.):
   Use descriptive string answers consistent with the patient's archetype.

6. For ALL codes, generate archetype-appropriate answers:
   - CHF patient: activity intolerance, lower extremity edema, dyspnea on exertion
   - TKR patient: post-surgical, weight-bearing restrictions, knee incision, pain 5-7/10
   - Diabetic foot ulcer: wound present, glucose management, peripheral neuropathy
   - CVA/Stroke: hemiparesis, speech deficits, ADL maximal assistance
   - COPD: severe dyspnea, O2 therapy, pursed-lip breathing
   - Sepsis/cellulitis: wound/infection site, IV antibiotics, wound care

FIELD DEFINITIONS — generate an answer for EVERY field listed below.
- The "question" in your output MUST be taken verbatim from the "question" in each field definition.
- For enum fields with "options", use ONLY a valid option code as the answer.
- For non-enum fields (object, array, string), use a clinically appropriate descriptive answer.
{fields_with_metadata_json}

Return ONLY a valid JSON object (no markdown, no backticks, no explanatory text):
{{
  "FIELD_CODE": {{"question": "<verbatim from field definition above>", "answer": "<coded or descriptive value>"}},
  ...
}}

Every field code in the list MUST have an entry in the output.
"""

# ─────────────────────────────────────────────────────────────────────────────
# Step 6 — OASIS Gold Standard
# ─────────────────────────────────────────────────────────────────────────────
# Placeholders: {archetype}, {diagnosis_context}, {has_scribe}, {section_name},
#   {referral_text}, {scribe_section}, {medication_summary}, {gap_context},
#   {field_codes_json}

OASIS_GOLD_STANDARD_PROMPT = """\
You are an expert OASIS-E1 clinical documentation specialist generating a gold-standard \
synthetic patient assessment for AI training data.

PATIENT CONTEXT:
- Archetype: {archetype}
- Primary Diagnosis: {diagnosis_context}
- Has Ambient Scribe: {has_scribe}
- Assessment Section: {section_name}

SOURCE DOCUMENTS:
--- REFERRAL PACKET ---
{referral_text}

{scribe_section}

--- CURRENT MEDICATION LIST (Active Medications) ---
{medication_summary}

--- STEP 4 GAP ASSESSMENT (AUTHORITATIVE VALUES — READ CAREFULLY) ---
{gap_context}

⚠️  CRITICAL RULE — GG AND ADL CONSISTENCY:
The STEP 4 GAP ASSESSMENT above was generated by a live clinical assessment of
this patient.  Its GG0130, GG0170, GG0100, and M-ADL values are AUTHORITATIVE.
When generating GG0130A1/A2/B1/B2/..., GG0170A1/A2/..., GG0100A/B/C/D,
M1800–M1910 codes in this batch:
  • Use the Step 4 values DIRECTLY as the basis — do NOT re-derive from documents.
  • The grouped Step 4 format maps to individual sub-codes:
      GG0130 "Eating"         → GG0130A1 (admission), GG0130A2 (discharge goal)
      GG0130 "Oral Hygiene"   → GG0130B1 / GG0130B2
      GG0130 "Shower/Bathe"   → GG0130C1 / GG0130C2
      GG0130 "Upper Body Dressing" → GG0130D1 / GG0130D2
      GG0130 "Lower Body Dressing" → GG0130E1 / GG0130E2
      GG0130 "Toileting Hygiene"   → GG0130F1 / GG0130F2
      GG0170 "A"→GG0170A1/A2, "B"→B1/B2, "C"→C1/C2, "D"→D1/D2, "E"→E1/E2,
              "F"→F1/F2, "I"→I1/I2, "J"→J1/J2, "K"→K1/K2
      Admission value (X1) = grouped value; Discharge goal (X2) = 1 level better.
  • M1800–M1910 ADL values in the Step 4 section above are the correct answers
    — use them verbatim; your rationale should state "Consistent with Step 4 gap assessment."
  • PRD RULE: GG discharge goals ALWAYS require clinical judgment; they are NEVER
    extractable from referral or scribe documents — they are set in Step 4 and
    must propagate unchanged into the gold standard.

═══════════════════════════════════════════════════════════
OASIS-E1 SCORING REFERENCE (for this batch):
═══════════════════════════════════════════════════════════

GG Self-Care / Mobility ADMISSION performance (X1 codes):
  01=Dependent (helper does all), 02=Substantial/maximal assist (>50%),
  03=Partial/moderate assist (<50%), 04=Supervision/touching assist (no physical assist),
  05=Setup/cleanup only (patient independent), 06=Independent (no helper, no device),
  07=Refused, 09=Not applicable, 10=Not attempted-environmental, 88=Not attempted-safety

GG DISCHARGE GOAL (X2 codes): same scale; goal = realistic expected status at end of care,
  typically 1-2 levels MORE independent than admission.

GG0100 Prior Functioning (before current illness):
  3=Independent, 2=Needed some help, 1=Dependent, 8=Unknown

GG0110 Devices/Aids used prior to illness: 0=No, 1=Yes (per device)

M ADL scale (M1800-M1910):
  M1800 Grooming: 0=Indep, 1=Supplies laid out, 2=Reminding, 3=Partial help, 4=Unable
  M1810/M1820 Dressing upper/lower: 0=Indep, 1=Clothes laid out, 2=Intermittent help, 3=Continuous help, 4=Unable
  M1830 Bathing: 0=Indep, 1=Reminding/supervis, 2=Intermittent help, 3=Continuous help, 4=Unable
  M1840 Toileting: 0=Indep, 1=Supervis, 2=Intermittent help, 3=Continuous help, 4=Unable/ostomy
  M1845 Incont care: 0=No ostomy/catheter, 1=Patient/carer manages, 2=HHA required
  M1850 Transferring: 0=Indep, 1=Minimal help/device, 2=Needs human help, 3=Unable, 4=Bedfast
  M1860 Ambulation: 0=Indep, 1=One-handed device, 2=Non-weight device, 3=Walker/crutches, 4=Human help, 5=Non-amby can wheel, 6=Non-amby cannot wheel
  M1870 Eating: 0=Indep, 1=Setup only, 2=Minimal help, 3=Needs human help, 4=Tube fed
  M1880 Oral meds: 0=Indep, 1=Reminding, 2=Partial help, 3=Full help, 4=No oral meds
  M1890 Phone: 0=Indep, 1=Answers easily, 2=Special phone, 3=Directed to phone, 4=Cannot use
  M1900 Therapy need: 0=None, 1=PT, 2=OT, 3=ST, 4=PT+OT, 5=PT+ST, 6=OT+ST, 7=PT+OT+ST
  M1910 Falls risk: 0=No, 1=Yes-1 fall in 12mo, 2=Yes-multiple falls in 12mo

Behavioral / Cognitive:
  M1700: 0=Alert/oriented/focused, 1=Difficulty focusing, 2=Disoriented, 3=Comatose
  M1710: 0=Not confused, 1=Confused ≤50% time, 2=>50% time, 3=Consistently confused
  M1720: 0=Not anxious, 1=Anxious ≤50% time, 2=>50% time, 3=Consistently anxious
  M1740: multi-select — 1=Memory deficit, 2=Impaired decision, 3=Verbal disruption,
         4=Physical aggression, 5=Disruptive/inapprop, 6=Delusional/hallucinat, 7=None of above
  M1745: 0=No behaviors, 1=Behaviors ≤weekly, 2=Behaviors 1-3×/day, 3=Behaviors 3+/day

Sensory:
  B0200: 0=Adequate, 1=Minimal difficulty, 2=Moderate-must speak distinctly, 3=Highly impaired
  B1000: 0=Adequate, 1=LG print only, 2=Headlines only, 3=Highly impaired, 4=Severely impaired
  B1300: 0=Never needs help, 1=Rarely, 2=Sometimes, 3=Often, 4=Always needs help

Pain:
  J0510: 0=No pain present, 1=Yes pain present
  J0520: 0=No effect on sleep, 1=Sleep <6h, 2=Cannot sleep
  J0530: 0=No effect, 1=Limited some activities, 2=Couldn't do some, 3=Can't do most things
  J0600: 0-10 numeric pain intensity rating (e.g. "4")

Clinical:
  M1000: NA=Not discharged inpatient; 01=NF, 02=SNF/TCU, 03=Acute hosp, 04=LTCH, 05=IRF, 06=Psych
  M1033: multi-select risk flags — 1=Falls hx, 2=Wt loss, 3=Multiple hosp, 4=Multiple ED,
         5=Mental decline, 6=Compliance difficulty, 7=5+ meds, 8=Wound/skin, 9=Procedure in 30d,
         10=Hosp in 12mo, 11=High-risk dx, NA=None
  M1100: 01=Alone-no help, 02=Alone-night help, 03=Alone-day help, 04=Alone-frequent, 05=Alone-continuous,
         06=With others-no help, 07=With others-regular, 08=With others-frequent, 09=With others-continuous
  M1400: 0=Not dyspneic, 1=With exertion, 2=With ADLs/moderate, 3=At rest, 4=With oxygen
  M1500: 0=No CHF symptom, 1=Dyspnea/edema with exertion, 2=With ADLs, 3=At rest
  M1306: 0=No pressure ulcer Stage 2+, 1=Yes
  M1330: 0=No stasis ulcer, 1=Yes observable, 2=Yes not observable
  M1340: 0=No surgical wound, 1=Yes observable, 2=Yes not observable
  M1610: 0=No incontinence/catheter, 1=Continent with catheter/ostomy, 2=Incontinent ≤50%, 3=>50%, 4=Total/catheter
  M1620: 0=Continent, 1=Rare ≤1/wk, 2=Occasional 2-3/wk, 3=Frequent >3/wk
  M2001: 0=No high-risk meds, 1=Yes-managed well, 2=Yes-managed with difficulty
  M2020: 0=No oral meds, 1=Able to take correctly, 2=Unable to take correctly
  M2030: 0=No injectable, 1=Patient manages, 2=Caregiver manages, 3=Both, 4=Cannot manage
  M2040: 0=No IV meds, 1=Patient/carer manages entirely, 2=HHA manages, 3=Both

TASK:
Generate a clinically realistic OASIS-E1 gold-standard answer for EVERY field listed below.
All answers MUST be clinically consistent with the patient archetype, diagnosis, and source documents.

RULES:
1. Use valid OASIS coded values as strings (e.g. "01", "06", "1", "0", "NA", "88")
2. For object/array/free-text fields, use a clinically appropriate descriptive string
3. Rationale: 1-2 sentences citing specific evidence from the source documents above
4. Confidence: "high" if clearly supported, "medium" if inferred, "low" if limited evidence
5. ALL codes in the list must appear in the output array
6. ⚠️  PHQ-2 GATE (CMS mandatory): If D0150A1 + D0150B1 < 3, then D0150C1–I1 and
   D0150C2–I2 MUST be null (not 0 — null). D0160 = only A2+B2 (if present). This rule
   overrides any other clinical reasoning. Do NOT set C–I items when the screen is negative.

FIELD CODES FOR THIS BATCH:
{field_codes_json}

Return ONLY a valid JSON ARRAY (no markdown, no code fences, no explanatory text):
[
  {{"item_code": "...", "value": "...", "rationale": "...", "confidence": "high|medium|low"}},
  ...
]
"""

# ─────────────────────────────────────────────────────────────────────────────
# Repair — GG Consistency (used by repair_tasks.py when gg_consistency errors remain)
# ─────────────────────────────────────────────────────────────────────────────
# Placeholders: {gg_errors_json}, {gold_standard_items_json}, {gap_answers_json}

GG_CONSISTENCY_REPAIR_PROMPT_TEMPLATE = """\
You are fixing GG consistency errors in an OASIS gold-standard document.

The gap_answers (Step 4 live assessment) contain AUTHORITATIVE GG0130 and GG0170 values.
The gold_standard has diverging values for the listed codes. Your task: produce a corrected
JSON array containing ONLY the affected GG codes with their values updated to match gap_answers.

ERRORS TO FIX (each shows the expected value from gap_answers and the incorrect actual value):
{gg_errors_json}

CURRENT GOLD STANDARD ITEMS (all GG codes for context):
{gold_standard_items_json}

GAP ANSWERS GG SECTION (authoritative source):
{gap_answers_json}

RULES:
- For each error, set the item value to the "expected" field from the error.
- Preserve item_code, rationale (update to reference gap_answers), confidence="high".
- Return ONLY the corrected items as a JSON array — no markdown, no other text.

[
  {{"item_code": "...", "value": "...", "rationale": "Repaired: aligned to gap_answers value.", "confidence": "high"}},
  ...
]
"""

