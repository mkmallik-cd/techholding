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
  "has_clinical_note"   — boolean — take false for all records
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
   Generate a synthetic patient:
   - Realistic first name + last name
   - DOB (consistent with age {age_hint})
   - Gender {gender_full}
   - Ethnicity (e.g., Hispanic/Latino, Not Hispanic/Latino)
   - Race (e.g., White, Black, Asian, American Indian)
   - Preferred Language (e.g., English, Spanish)
   - Synthetic US-based residential address (Street, City, State, Zip)
   - Synthetic 11-character Medicare ID (MBI) (e.g., 1EG4-TE5-MK72)
   - Primary Insurer (e.g., Medicare, BCBS, UnitedHealthcare)
   - Synthetic 9-digit MRN.

2. REFERRAL DATES
   Generate: Hospital Admit Date, Hospital Discharge Date (2-7 days post-admit),
   Referral Date (same as or 1 day after discharge), Expected SOC Date (1-2 days after referral).
   All dates must be internally consistent. Use MM/DD/YYYY format.
   Use dates near 2026-03-09 (March 2026).

3. REFERRING PHYSICIAN
   Generate: Dr. [Firstname Lastname], MD. Use an ENTIRELY FICTIONAL name.
   Synthetic 10-digit NPI (starts with 1). Specialty.

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
    "id":           "unique identifier, e.g. MED-001",
    "name":         "generic name (capitalised)",
    "dose":         "e.g. 5 mg",
    "route":        "oral | subcutaneous | IV | topical | inhaled | other",
    "frequency":    "e.g. daily | twice daily | every 4-6 hours PRN",
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
with their correct id, dose, route, and frequency.

─────────────────────────────────────────────────────────────────
LAYER 3 — patient_reported_otc
─────────────────────────────────────────────────────────────────
Include 2-3 items the patient verbally reports taking.
Every OTC item must also have a unique "id" (e.g., MED-010).
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
Address: [copy residential address from referral]
Medicare ID: [copy Medicare MBI from referral]
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
- NEVER include PHQ mood codes (D0150A1 through D0150I2, D0160) —
  these require a live structured mood interview.
- NEVER include GG discharge goal codes (GG0100, GG0110, GG0130, GG0170, GG0170C) —
  these require clinical judgment about expected functional recovery.
- NEVER include a bare root GG0130 or GG0170 code — always use the full sub-item suffix
  (e.g. GG0130A1, GG0170D1). Root codes without a letter+digit suffix are invalid.
- Return ONLY real OASIS-E1 item codes. Non-clinical EHR narrative keys such as
  ALLERGIES, VITAL_SIGNS, CIRCULATORY_HISTORY, MENTAL_STATUS, SKIN, ACTIVITIES_PERMITTED,
  LAB_RESULTS, and similar non-coded descriptors must NEVER appear. If such a code is in
  the input list, omit it from the output entirely.
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
#   {referral_text}, {scribe_section}, {medication_json}, {fields_with_metadata_json}
GAP_ANSWER_PROMPT_TEMPLATE = """\
You are an expert OASIS-E1 clinical documentation specialist generating synthetic patient dataset answers.

⚠️  CRITICAL SCOPE RULE — READ BEFORE GENERATING ANY ANSWER:
The ONLY valid field codes in this task are real OASIS-E1 item codes (e.g. M1021, C0200, D0150A1,
GG0130A1, N0415A). The following keys are NOT OASIS-E1 codes and must be COMPLETELY SKIPPED
— do NOT generate an answer for them under any circumstances:
  ALLERGIES, VITAL_SIGNS, ACTIVITIES_PERMITTED, CIRCULATORY_HISTORY, MENTAL_STATUS, SKIN,
  LAB_RESULTS, WOUND_CARE, FALL_RISK_FACTORS, COGNITIVE_STATUS, FUNCTIONAL_LIMITATIONS,
  HOMEBOUND_STATUS, SAFETY_MEASURES, NUTRITIONAL_STATUS, CAREGIVER_STATUS,
  PHQ_MOOD_INTERVIEW, and any other free-text EHR narrative descriptor.
If any of the above appear in the field list, omit them entirely from the output JSON.

PATIENT CONTEXT:
- Archetype: {archetype}
- Primary Diagnosis Context: {diagnosis_context}
- Has Ambient Scribe Note: {has_ambient_scribe}

--- REFERRAL PACKET ---
{referral_text}

{scribe_section}

--- MEDICATION LIST (use this to derive N0415 flags per Rule 6 below) ---
{medication_json}

TASK:
Generate clinically realistic OASIS answers for ALL of the field codes listed below.
Every answer MUST be clinically consistent with the patient's presentation described above.

CRITICAL SCORING RULES — READ CAREFULLY:

1. BIMS (C section — MANDATORY):
   - C0100: Cognitive Assessment — 0=No, 1=Yes (whether BIMS was administered)
   - C0200: Words repeated correctly (0=none, 1=one, 2=two, 3=all three words "sock/blue/bed")
   - C0300: DERIVED sum — MUST EQUAL C0300A + C0300B + C0300C (range 0–6). Use 99 only if patient refused/unable.
   - C0300A: Year correct — 0=incorrect, 1=missed by >5y, 2=missed by 2-5y, 3=correct
   - C0300B: Month correct — 0=incorrect, 1=missed by >1mo, 2=correct
   - C0300C: Day of week correct — 0=incorrect, 1=correct
   - C0400: DERIVED sum — MUST EQUAL C0400A + C0400B + C0400C (range 0–6). Use 99 only if patient refused/unable.
   - C0400A: Recall "sock" — 0=could not recall, 1=yes with cue, 2=no cue needed
   - C0400B: Recall "blue" — 0=could not recall, 1=yes with cue, 2=no cue needed
   - C0400C: Recall "bed" — 0=could not recall, 1=yes with cue, 2=no cue needed
   - C0500: BIMS TOTAL — MUST EQUAL EXACTLY: C0200 + C0300 + C0400 (range 0-15).
     Compute sequentially: Step A: C0300 = C0300A+C0300B+C0300C (0–6);
                           Step B: C0400 = C0400A+C0400B+C0400C (0–6);
                           Step C: C0500 = C0200 + C0300 + C0400.
   - C1310: Brief Cognitive Interview for RCA — 0=No, 1=Yes
   - Use 99 for any code if patient was unable/refused to participate in BIMS

2. PHQ-9 (D section — MANDATORY — all 18 sub-codes + total):
   - D0150A1 through D0150I1: Symptom presence — Column 1 (0=symptom not present, 1=symptom present)
   - D0150A2 through D0150I2: Frequency — Column 2 (0=not at all, 1=several days, 2=more than half the days, 3=nearly every day)
   - D0160: PHQ TOTAL — MUST EQUAL EXACTLY the sum described below
   (PHQ_MOOD_INTERVIEW is not an OASIS-E1 code — omit it per the CRITICAL SCOPE RULE above)

   ⚠️  CRITICAL PHQ-2 SCREENING GATE (CMS mandatory rule — violations cause dataset rejection):
   Step 1 — Score the PHQ-2 screen: screen_score = D0150A1 + D0150B1
   Step 2 — If screen_score < 3 (negative screen):
     • D0150C1 through D0150I1 MUST ALL be null (NOT 0 — use null/None)
     • D0150C2 through D0150I2 MUST ALL be null
     • D0160 = (D0150A2 if D0150A1=1 else 0) + (D0150B2 if D0150B1=1 else 0) ONLY — items C through I excluded
     • Example (negative screen): A1=1, A2=2, B1=1, B2=1 → D0160 = 2+1 = 3 (NOT 4 — only sum frequencies where X1=1)
   Step 3 — If screen_score >= 3 (positive screen):
     • Administer all 9 items A through I normally
     • D0160 = sum of all D0150X2 values where the corresponding D0150X1 = 1

   Example (screen negative): A1=1, B1=1 → screen=2 < 3 → C1=null, D1=null … I1=null,
     C2=null … I2=null, D0160 = A2 + B2 (if those symptoms present)
   NEVER set D0150C-I items to any non-null value when screen_score < 3.

3. GG Self-Care / Mobility Sub-codes (MANDATORY — use full sub-item code, NEVER bare root GG0130 or GG0170):
   GG0130 Self-Care (X1 = SOC/ROC admission performance, X2 = expected discharge goal):
     GG0130A1/A2 = Eating
     GG0130B1/B2 = Oral Hygiene
     GG0130C1/C2 = Shower/Bathe Self
     GG0130D1/D2 = Upper Body Dressing ← FREQUENTLY MISSING — MUST emit both D1 and D2
     GG0130E1/E2 = Lower Body Dressing ← FREQUENTLY MISSING — MUST emit both E1 and E2
     GG0130F1/F2 = Toileting Hygiene
     GG0130G1/G2 = Oral Hygiene (denture/remove)
   GG0170 Mobility (X1 = admission, X2 = discharge goal):
     GG0170A1/A2 = Roll Left and Right in Bed
     GG0170B1/B2 = Sit to Lying
     GG0170C1/C2 = Lying to Sitting on Side of Bed
     GG0170D1/D2 = Sit to Stand ← MUST emit
     GG0170E1/E2 = Chair/Bed-to-Chair Transfer ← MUST emit
     GG0170F1/F2 = Toilet Transfer ← MUST emit
     GG0170G1/G2 = Car Transfer
     GG0170H1/H2 = Walk 10 Feet
     GG0170I1/I2  = Walk 50 Feet with Two Turns
     GG0170J1/J2 = Walk 150 Feet
     GG0170K1/K2 = Walking 10 Feet on Uneven Surfaces
     GG0170L1/L2 = 1 Step (Curb)
     GG0170M1/M2 = 4 Steps
     GG0170N1/N2 = 12 Steps
     GG0170O1/O2 = Picking Up Object
     GG0170P1/P2 = Wheel 50 Feet with Two Turns
     GG0170RR1   = Wheel 50 Feet on Rough/Uneven Surfaces (admission only)
   GG Scale: 01=Dependent, 02=Substantial/Maximal assist, 03=Partial/Moderate assist,
             04=Supervision/touching assist, 05=Setup/cleanup only, 06=Independent
   Exceptions: 07=Refused, 09=Not applicable, 10=Equipment unavailable, 88=Not attempted

4. OASIS M-codes — common value ranges:
   - M0100: 01=SOC, 03=ROC, 04=Recertification, 06=Transfer, 09=Discharge
   - M1021/M1023: Primary/Other diagnosis with ICD-10 code and symptom control rating 0-4
   - M1060: Height in inches, Weight in pounds (e.g., "66 inches, 172 lbs")
   - M1400: Dyspnea — 0=No dyspnea, 1=With exertion, 2=With ADLs, 3=At rest

5. GG0110 Prior Device Use (0=No, 1=Yes per device — device used before this illness/injury):
   GG0110A = Cane or Crutch, GG0110B = Walker, GG0110C = Wheelchair (manual or electric),
   GG0110D = Prosthetics/Orthotics, GG0110E = None of the above, GG0110F = Other

6. N0415 High-Risk Drug Classes — derive DETERMINISTICALLY from the MEDICATION LIST above:
   For each flag, set "1" if any active medication matches the drug class; "0" otherwise.
   N0415A = Antipsychotic    → haloperidol, quetiapine, risperidone, olanzapine, aripiprazole
   N0415B = Anticoagulant    → warfarin, apixaban, rivaroxaban, dabigatran, enoxaparin, heparin
   N0415C = Antibiotic       → any systemic antibiotic (amoxicillin, ciprofloxacin, vancomycin, etc.)
   N0415D = Antiplatelet     → aspirin ≥325mg, clopidogrel, ticagrelor, prasugrel
   N0415E = Hypoglycemic     → insulin, metformin, glipizide, sitagliptin, empagliflozin
   N0415F = Cardiovascular   → digoxin, amiodarone, flecainide, sotalol, dronedarone
   N0415G = Diuretic         → furosemide, torsemide, bumetanide, hydrochlorothiazide, chlorthalidone
   N0415H = Opioid           → oxycodone, morphine, hydromorphone, fentanyl, tramadol, codeine, buprenorphine
   N0415I = None of above    → set "1" ONLY if ALL of N0415A through N0415H are "0"

7. For ALL codes, generate archetype-appropriate answers:
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

Every OASIS-E1 field code in the list MUST have an entry in the output.
Non-OASIS codes (ALLERGIES, VITAL_SIGNS, PHQ_MOOD_INTERVIEW, etc.) must be omitted entirely — do NOT include them with null answers.
"""

# ─────────────────────────────────────────────────────────────────────────────
# Step 6 — OASIS Gold Standard
# ─────────────────────────────────────────────────────────────────────────────
# Placeholders: {archetype}, {diagnosis_context}, {has_scribe}, {section_name},
#   {referral_text}, {scribe_section}, {medication_json}, {gap_context},
#   {field_codes_json}

OASIS_GOLD_STANDARD_PROMPT = """\
You are an expert OASIS-E1 clinical documentation specialist generating a gold-standard \
synthetic patient assessment for AI training data.

⚠️  OUTPUT SCOPE RULE — MANDATORY:
Only generate values for real OASIS-E1 item codes. The following keys are NOT OASIS-E1 codes;
if they appear in the batch, skip them entirely — do NOT output a value for them:
  PHQ_MOOD_INTERVIEW, ALLERGIES, VITAL_SIGNS, CIRCULATORY_HISTORY, MENTAL_STATUS, SKIN,
  LAB_RESULTS, WOUND_CARE, FALL_RISK_FACTORS, COGNITIVE_STATUS, FUNCTIONAL_LIMITATIONS,
  HOMEBOUND_STATUS, SAFETY_MEASURES, NUTRITIONAL_STATUS, CAREGIVER_STATUS,
  ACTIVITIES_PERMITTED, and any other free-text EHR narrative descriptor.

PATIENT CONTEXT:
- Archetype: {archetype}
- Primary Diagnosis: {diagnosis_context}
- Has Ambient Scribe: {has_scribe}
- Assessment Section: {section_name}

SOURCE DOCUMENTS:
--- REFERRAL PACKET ---
{referral_text}

{scribe_section}

--- CURRENT MEDICATION LIST (Active Medications — use this to derive N0415 flags per Mandatory Rule 4) ---
{medication_json}

--- STEP 4 GAP ASSESSMENT (AUTHORITATIVE VALUES — READ CAREFULLY) ---
{gap_context}

⚠️  CRITICAL RULE — GG, ADL, AND AUTHORITATIVE PROPAGATION:
The STEP 4 GAP ASSESSMENT above is the authoritative source for ALL GG0130, GG0170, GG0100,
N0415, M1800–M1910, BIMS (C section), and PHQ (D section) values in this record.
For EVERY field present in gap_context:
  • Copy the value VERBATIM — do NOT re-derive, re-interpret, or override it.
  • Your rationale MUST state "Propagated verbatim from Step 4 gap assessment."
  • (Legacy support): If Step 4 uses grouped labels (e.g., GG0130 "Eating"), map it to the
    correct admission code (GG0130A1).
  • Discharge goal (X2 codes) = typically 1 level more independent than the admission (X1) value.

FREQUENTLY MISSING GG SUB-CODES — you MUST include ALL of the following in your output:
  GG0130D1 / GG0130D2 = Upper Body Dressing (admission performance / discharge goal)
  GG0130E1 / GG0130E2 = Lower Body Dressing (admission performance / discharge goal)
  GG0170A1 / GG0170A2 = Roll Left/Right in Bed
  GG0170B1 / GG0170B2 = Sit to Lying
  GG0170C1 / GG0170C2 = Lying to Sitting on Side of Bed
  GG0170D1 / GG0170D2 = Sit to Stand ← MUST emit
  GG0170E1 / GG0170E2 = Chair/Bed-to-Chair Transfer ← MUST emit
  GG0170F1 / GG0170F2 = Toilet Transfer ← MUST emit

A1010 SPECIAL RULE: A1010 is the Race/Ethnicity multi-select field (coded flags, not narrative).
Valid codes: 01=American Indian/Alaska Native, 02=Asian, 03=Black/African American,
04=Hispanic/Latino, 05=White, 06=Other, 99=Unknown.
NEVER fill A1010 with address text, patient name, or any non-code narrative.

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
5. ALL OASIS-E1 codes in the list must appear in the output; non-OASIS keys (e.g.
   PHQ_MOOD_INTERVIEW, ALLERGIES) must be omitted entirely — do NOT include them at all.
6. ⚠️  PHQ-2 GATE (CMS mandatory): If D0150A1 + D0150B1 < 3, then D0150C1–I1 and
   D0150C2–I2 MUST be null (not 0 — null). D0160 = only A2+B2 (if present). This rule
   overrides any other clinical reasoning. Do NOT set C–I items when the screen is negative.

MANDATORY RULE 2 — BIMS ARITHMETIC CROSS-VERIFY:
If BIMS codes appear in this batch or in gap_context, verify the arithmetic:
  C0300 MUST equal C0300A + C0300B + C0300C.
  C0400 MUST equal C0400A + C0400B + C0400C.
  C0500 MUST equal C0200 + C0300 + C0400.
If the propagated gap value is arithmetically incorrect, correct it and note the discrepancy
in the rationale (e.g. "Corrected: gap C0500=12 conflicts with sub-score sum=10; using 10").

MANDATORY RULE 3 — PHQ D0160 CROSS-VERIFY:
If PHQ codes appear in this batch or in gap_context, verify the PHQ-2 gate and D0160:
  screen_score = D0150A1 + D0150B1.
  If screen_score < 3: D0160 = (D0150A2 if D0150A1=1 else 0) + (D0150B2 if D0150B1=1 else 0).
  If screen_score >= 3: D0160 = sum of all D0150X2 values where the corresponding D0150X1=1.
If the propagated gap D0160 is inconsistent with this formula, correct it and note in rationale.

MANDATORY RULE 4 — N0415 FROM MEDICATION LIST:
Derive N0415A–I flags deterministically from the MEDICATION LIST above:
  N0415A = Antipsychotic    → haloperidol, quetiapine, risperidone, olanzapine, aripiprazole
  N0415B = Anticoagulant    → warfarin, apixaban, rivaroxaban, dabigatran, enoxaparin, heparin
  N0415C = Antibiotic       → any systemic antibiotic (amoxicillin, ciprofloxacin, vancomycin, etc.)
  N0415D = Antiplatelet     → aspirin ≥325mg, clopidogrel, ticagrelor, prasugrel
  N0415E = Hypoglycemic     → insulin, metformin, glipizide, sitagliptin, empagliflozin
  N0415F = Cardiovascular   → digoxin, amiodarone, flecainide, sotalol, dronedarone
  N0415G = Diuretic         → furosemide, torsemide, bumetanide, hydrochlorothiazide, chlorthalidone
  N0415H = Opioid           → oxycodone, morphine, hydromorphone, fentanyl, tramadol, codeine, buprenorphine
  N0415I = None of above    → set "1" ONLY if ALL of N0415A through N0415H are "0"
Set each flag to "1" if a matching medication is present, "0" otherwise.
If N0415 values were propagated from gap_context, cross-verify against the medication list
and correct if inconsistent — note the correction in rationale.

FIELD CODES FOR THIS BATCH:
{field_codes_json}

Return ONLY a flat JSON object. Every key must be a string OASIS item code. 
Every value must be a plain string — no nested objects, no arrays, no null.

Rules for multi-value items:
- Diagnosis lists: use underscore suffix  →  M1021, M1023_1, M1023_2, M1023_3
- Multi-select checkboxes: use item+subcode  →  M1030_1, M1030_2
- Nested assessment items: flatten with subcode  →  O0110A1, O0110A2, K0520Z1
- Height/weight: M1060A (height inches), M1060B (weight lbs)
- Omit skipped items entirely — do not include null or blank values
- Coded values only — never append descriptions: use "2" not "2 - Requires assistance"

{{
  "FIELD_CODE": "value",
  ...
}}
"""

# ─────────────────────────────────────────────────────────────────────────────
# Repair — GG Consistency (used by repair_tasks.py when gg_consistency errors remain)
# ─────────────────────────────────────────────────────────────────────────────
# Placeholders: {gg_errors_json}, {gold_standard_items_json}, {gap_answers_json}

GG_CONSISTENCY_REPAIR_PROMPT_TEMPLATE = """\
You are fixing GG consistency errors in an OASIS gold-standard document.

The gap_answers (Step 4 live assessment) contain AUTHORITATIVE GG0130 and GG0170 values.
The gold_standard has diverging values for the listed codes. Your task: produce a corrected
JSON object containing ONLY the affected GG codes with their values updated to match gap_answers.

ERRORS TO FIX (each shows the expected value from gap_answers and the incorrect actual value):
{gg_errors_json}

CURRENT GOLD STANDARD ITEMS (all GG codes for context):
{gold_standard_items_json}

GAP ANSWERS GG SECTION (authoritative source):
{gap_answers_json}

RULES:
- For each error, set the item value to the "expected" field from the error.
- Return ONLY a valid JSON object mapping each affected code to its updated value.
- No markdown, no explanatory text.

{{
  "FIELD_CODE": "value",
  ...
}}
"""

# ─────────────────────────────────────────────────────────────────────────────
# Step 8 — LLM Cross-Document Consistency Audit
# ─────────────────────────────────────────────────────────────────────────────
# Placeholders: {fields_batch_json}, {referral_text}, {ambient_scribe_text},
#               {medication_list_json}, {gap_answers_json}

LLM_AUDIT_PROMPT_TEMPLATE = """\
You are a clinical data auditor reviewing synthetic home-health patient records.
Your task is to perform a cross-document consistency audit for a batch of OASIS-E1 fields.

For EACH field in the batch:
1. Search ALL provided source documents for any mention of or evidence related to that field.
2. Identify what value each document supports (or note if it is silent about the field).
3. Flag a CONFLICT if two or more documents imply DIFFERENT values for the same field.
4. Write a concise explanation of why the recorded OASIS value is the correct clinical pick.

⚠️  CRITICAL OASIS CODEBOOK RULES — READ BEFORE AUDITING ANY FIELD:

1. D0150 vs N0415 — these are COMPLETELY DIFFERENT sections:
   - D0150A–I are PHQ-9 MOOD INTERVIEW items (symptoms of depression/anxiety):
       A = Little interest or pleasure in doing things
       B = Feeling down, depressed, or hopeless
       C = Trouble falling/staying asleep or sleeping too much
       D = Feeling tired or having little energy
       E = Poor appetite or overeating
       F = Feeling bad about yourself
       G = Trouble concentrating
       H = Moving/speaking slowly OR being fidgety/restless
       I = Thoughts of being better off dead, or hurting yourself
     Column 1 (X1) = symptom presence (0=not present, 1=present)
     Column 2 (X2) = frequency (0=not at all, 1=several days, 2=>half the days, 3=nearly every day)
   - N0415A–I are HIGH-RISK DRUG CLASS flags (completely unrelated to mood):
       A=Antipsychotic, B=Anticoagulant, C=Antibiotic, D=Antiplatelet,
       E=Hypoglycemic/Insulin, F=Cardiovascular, G=Diuretic, H=Opioid,
       I=None of the above drug classes received
   ❌ NEVER interpret D0150 fields using drug/medication terminology.
   ❌ NEVER compare D0150 values to the medication list.

2. PHQ-2 GATE — null on D0150 items C–I is CORRECT (not a data error):
   - If D0150A1 + D0150B1 < 3 (negative PHQ-2 screen), CMS requires items C–I to be null.
   - A null value on D0150C1 through D0150I2 when A1+B1 < 3 is the CORRECT per-protocol value.
   - Do NOT flag D0150C–I = null as a conflict or error when the PHQ-2 screen is negative.

3. BIMS AUTHORITY — gap_answers is the ONLY valid source for BIMS:
   - C0100–C1310 (BIMS section) values come from live cognitive testing documented in gap_answers.
   - The gold standard C-section values ARE the gap_answers values (copied verbatim).
   - If an ambient scribe note describes cognitive behaviour that implies a different BIMS score,
     that is NOT a conflict — the standardised BIMS test result (gap_answers) takes precedence.
   - C0300 and C0400 totals are DERIVED (C0300 = C0300A+B+C; C0400 = C0400A+B+C). If gap_answers
     shows an inconsistent group total it may be corrected by code — this is expected, not a conflict.

4. PHQ AUTHORITY — gap_answers is the ONLY valid source for D0150/D0160:
   - D0150 and D0160 values come from a structured mood interview in gap_answers.
   - Do NOT compare D0150 values to referral or ambient scribe documents.
   - If the mood interview was not administered, all D0150 values will be null (valid).

5. GG0130/GG0170 X1 admission codes — only gap_answers is authoritative:
   - GG0130X1 and GG0170X1 codes are admission-performance measurements from gap_answers.
   - Referral/scribe documents describing functional ability do NOT override gap_answers X1 values.

6. GG0130/GG0170 X2 discharge goal codes — these are LLM-generated clinical goals:
   - GG0130A2, GG0130B2, … GG0170P2 are EXPECTED DISCHARGE GOALS, NOT current performance.
   - gap_answers may contain a bare root code GG0130=09 (not attempted summary) — this is a
     DIFFERENT field from the individual sub-item X2 goal codes. Do NOT compare them.
   - Never flag GG0130X2 or GG0170X2 as conflicting with gap_answers GG0130=09/GG0170=09.

7. A1005 / A1010 / A1110 — field definitions (LLM frequently confuses these):
   - A1005 = Ethnicity: 1=Not Hispanic/Latino, 2=Hispanic/Latino
   - A1010 = Race (multi-select sub-flags, e.g. A1010_5=1 for White) — NOT ZIP code or state
   - A1110 = Preferred language code (e.g. "EN" for English, "SP" for Spanish) — NOT a date

Return ONLY a valid JSON array — no markdown fences, no commentary, no trailing text.
Each element must have EXACTLY these keys:
  "field_code"        — the OASIS field code (string, uppercase)
  "oasis_value"       — the value recorded in oasis_gold_standard (string or null)
  "sources_found"     — array of objects, one per document that has evidence for this field:
                          "document"       — one of: "referral_packet", "ambient_scribe",
                                             "medication_list", "gap_answers"
                          "excerpt"        — verbatim or paraphrased excerpt (max 120 chars)
                          "value_supported"— implied value from this document (string or null)
                          "consistent"     — true if value_supported matches oasis_value
  "conflict_detected" — true if ANY source_found entry has consistent=false
  "value_reasoning"   — 1-2 sentence explanation of why oasis_value is the correct pick

If a document has no relevant evidence for a field, omit it from sources_found entirely.
If no documents mention a field at all, set sources_found to [] and explain in value_reasoning.

OASIS FIELDS TO AUDIT (JSON object — field_code → oasis_value):
{fields_batch_json}

\u2500\u2500\u2500 SOURCE DOCUMENTS \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

REFERRAL PACKET (referral_packet.txt):
{referral_text}

\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

AMBIENT SCRIBE NOTE (ambient_scribe.txt \u2014 empty string if not generated for this patient):
{ambient_scribe_text}

\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

MEDICATION LIST (medication_list.json \u2014 condensed):
{medication_list_json}

\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

GAP ANSWERS / TAP-TAP FORM (tap_tap_gap_answers.json \u2014 condensed field_code \u2192 answer map):
{gap_answers_json}

\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

OUTPUT \u2014 return a JSON array only, example structure:
[
  {{
    "field_code": "M1700",
    "oasis_value": "0",
    "sources_found": [
      {{
        "document": "ambient_scribe",
        "excerpt": "Alert and oriented x3, follows commands appropriately",
        "value_supported": "0",
        "consistent": true
      }},
      {{
        "document": "gap_answers",
        "excerpt": "M1700 answer: 0",
        "value_supported": "0",
        "consistent": true
      }}
    ],
    "conflict_detected": false,
    "value_reasoning": "Ambient scribe documents A&Ox3 with no confusion episodes; M1700=0 (intact cognition) is fully consistent across all sources."
  }}
]
"""

# ─────────────────────────────────────────────────────────────────────────────
# Audit-Fix Prompts (used when LLM audit finds conflicts and a re-run is needed)
#
# Each prompt shows ALL currently generated documents + the audit report and
# asks the LLM to produce a REVISED version of the specific document that
# resolves the flagged inconsistencies.  These replace the normal generation
# prompt for the retry run — they are targeted revision prompts, not from-
# scratch generation prompts.
# ─────────────────────────────────────────────────────────────────────────────

# Step 2 fix — revise referral_packet.txt
# Placeholders: {current_referral_text}, {medication_list_json},
#   {ambient_scribe_text}, {gap_answers_json}, {oasis_gold_standard_json},
#   {audit_conflicts_text}
REFERRAL_PACKET_FIX_PROMPT = """\
You are a clinical documentation specialist reviewing previously generated synthetic home-health patient documents.
A cross-document LLM audit has identified inconsistencies. Your task is to produce a REVISED version of the
REFERRAL PACKET that resolves these inconsistencies and makes all documents internally consistent.

=== ALL CURRENTLY GENERATED DOCUMENTS ===

--- REFERRAL PACKET (current version — to be revised) ---
{current_referral_text}

--- MEDICATION LIST (current version — read-only reference) ---
{medication_list_json}

--- AMBIENT SCRIBE NOTE (current version — read-only reference) ---
{ambient_scribe_text}

--- TAP-TAP GAP ANSWERS (current version — read-only reference) ---
{gap_answers_json}

--- OASIS GOLD STANDARD (current version — read-only reference) ---
{oasis_gold_standard_json}

=== AUDIT FINDINGS — INCONSISTENCIES TO FIX ===
{audit_conflicts_text}

=== YOUR TASK ===
Produce a REVISED referral packet that resolves every inconsistency listed in the audit findings.

MANDATORY CONSTRAINTS — every constraint below must be satisfied in your revised output:

1. PRESERVE patient demographics EXACTLY — do not alter: patient name, DOB, MRN, Medicare ID (MBI),
   residential address, gender, ethnicity, or race. These must be identical to the current version.

2. PRESERVE all 11 required sections with correct content:
   1. PATIENT HEADER          7. DISCHARGE MEDICATION LIST
   2. REFERRAL DATES          8. ORDERED HOME HEALTH SERVICES
   3. REFERRING PHYSICIAN     9. HOMEBOUND STATUS (must include objective measures)
   4. PRIMARY DIAGNOSIS      10. PHYSICIAN ORDERS
   5. SECONDARY DIAGNOSES    11. FACE-TO-FACE (F2F) DOCUMENTATION
   6. HISTORY & PHYSICAL

3. ICD-10 codes must remain syntactically valid (pattern: letter + 2 digits + period + alphanumeric
   suffix, e.g. I50.9, E11.9, Z87.39). Do not invent new codes — only use codes already present or
   standard alternatives for the same clinical condition.

4. The F2F section must document clinical findings, the certifying physician, and homebound rationale —
   do not delete or abbreviate it.

5. Changes ONLY what is necessary to resolve the flagged inconsistencies — do not alter unrelated content.

6. Remains clinically realistic and consistent with all other documents (listed as read-only above).

Output ONLY the revised plain-text referral packet. No JSON, no markdown, no commentary before or after.
Generate the revised referral packet now:"""

# Step 3 fix — revise ambient_scribe.txt
# Placeholders: {referral_text}, {current_ambient_scribe_text}, {medication_list_json},
#   {gap_answers_json}, {oasis_gold_standard_json}, {audit_conflicts_text}
AMBIENT_SCRIBE_FIX_PROMPT = """\
You are a clinical documentation specialist reviewing previously generated synthetic home-health patient documents.
A cross-document LLM audit has identified inconsistencies. Your task is to produce a REVISED version of the
AMBIENT SCRIBE NOTE that resolves these inconsistencies and makes all documents internally consistent.

=== ALL CURRENTLY GENERATED DOCUMENTS ===

--- REFERRAL PACKET (current version — read-only reference) ---
{referral_text}

--- MEDICATION LIST (current version — read-only reference) ---
{medication_list_json}

--- AMBIENT SCRIBE NOTE (current version — to be revised) ---
{current_ambient_scribe_text}

--- TAP-TAP GAP ANSWERS (current version — read-only reference) ---
{gap_answers_json}

--- OASIS GOLD STANDARD (current version — read-only reference) ---
{oasis_gold_standard_json}

=== AUDIT FINDINGS — INCONSISTENCIES TO FIX ===
{audit_conflicts_text}

=== YOUR TASK ===
Produce a REVISED ambient scribe note that resolves every inconsistency listed in the audit findings.

MANDATORY FORMAT RULES — your output must satisfy ALL of the following:

1. VOICE: Nurse voice, first person throughout ("I arrived...", "I assessed...", "I observed...").

2. DOCUMENT HEADER (keep identical to the current version — do NOT alter any of these fields):
   AMBIENT NURSING ASSESSMENT — START OF CARE

   Patient: [same as current], DOB: [same as current], MRN: [same as current]
   Address: [same as current]
   Medicare ID: [same as current]
   Visit Date: [same as current]   Time: 09:30
   Clinician: [same RN name], RN
   Supervising Physician: [same as current]

3. TIMESTAMPS: Use HH:MM 24-hour format. Start at 09:30; each section ~5-15 minutes apart.

4. REQUIRED SECTIONS — all 7 must appear in EXACTLY this order with EXACTLY this header text:

   VITAL SIGNS — [timestamp]
   → State vitals: BP, HR (with rhythm), RR, O2 saturation, Temperature, Weight, Pain score.
   → 1-2 sentences interpreting the vitals.

   PHYSICAL ASSESSMENT — [timestamp]
   → 2-4 sentences prose: relevant abnormal findings, measurements, laterality.

   ADL OBSERVATIONS — [timestamp]
   → 2-3 sentences. Use ONLY these exact assistance-level terms:
     "Independent" | "Independent with setup/cleanup" | "Minimal assistance" |
     "Moderate assistance" | "Substantial/Maximal assistance" | "Dependent"

   HOME SAFETY OBSERVATION — [timestamp]
   → 2-3 sentences: specific named hazards, fall risk factors, modifications recommended.

   PATIENT GOALS — [timestamp]
   → Format exactly as:
     Patient stated: "[Direct quote — patient's own words]"
     Clinical goal: [SMART goal — measurable metric and timeframe]

   PAIN ASSESSMENT — [timestamp]
   → 2-3 sentences: location, numeric rating, quality descriptor, aggravating/relieving factors.

   PLAN & FOLLOW-UP — [timestamp]
   → 2-3 sentences: next visit, physician orders to confirm, education given with patient
     verbalization of understanding. Use "SN Xw#" visit frequency format.

5. LENGTH: 600-900 words total. Plain text — NO markdown, NO bullet points in the main body.

6. STRICT PROHIBITIONS — these terms must NEVER appear anywhere in your output:
   ❌ "BIMS score"
   ❌ "BIMS interview"
   ❌ "PHQ-2"
   ❌ "PHQ-9"
   ❌ "PHQ2"
   ❌ "PHQ9"
   → For cognition write: "alert and oriented x4 (person/place/time/event)" or "oriented x3", etc.
   → For mood write descriptively: "appeared anxious but cooperative", "tearful at times, engaged with teaching"
   → These standardised screening tools are documented in gap-answer sections ONLY.

7. Changes ONLY what is necessary to resolve the flagged inconsistencies — do not alter unrelated content.

Output ONLY the revised plain-text ambient scribe note. No JSON, no markdown, no commentary before or after.
Generate the revised ambient scribe note now:"""

# Step 4 fix — revise tap_tap_gap_answers.json
# Placeholders: {referral_text}, {ambient_scribe_text}, {medication_list_json},
#   {current_gap_answers_json}, {oasis_gold_standard_json}, {audit_conflicts_text}
GAP_ANSWERS_FIX_PROMPT = """\
You are a clinical documentation specialist reviewing previously generated synthetic home-health patient documents.
A cross-document LLM audit has identified inconsistencies. Your task is to produce a REVISED version of the
TAP-TAP GAP ANSWERS (tap_tap_gap_answers.json) that resolves these inconsistencies and makes all documents internally consistent.

=== ALL CURRENTLY GENERATED DOCUMENTS ===

--- REFERRAL PACKET (current version — read-only reference) ---
{referral_text}

--- MEDICATION LIST (current version — read-only reference) ---
{medication_list_json}

--- AMBIENT SCRIBE NOTE (current version — read-only reference) ---
{ambient_scribe_text}

--- TAP-TAP GAP ANSWERS (current version — to be revised) ---
{current_gap_answers_json}

--- OASIS GOLD STANDARD (current version — read-only reference) ---
{oasis_gold_standard_json}

=== AUDIT FINDINGS — INCONSISTENCIES TO FIX ===
{audit_conflicts_text}

=== YOUR TASK ===
Produce a REVISED tap_tap_gap_answers JSON that resolves every inconsistency listed in the audit findings.

MANDATORY CLINICAL RULES — violations will cause dataset rejection:

────────────────────────────────────────────────────────────
RULE 1 — BIMS ARITHMETIC (C section)
────────────────────────────────────────────────────────────
C0500 (BIMS Total) MUST EQUAL EXACTLY the sum:
  C0200 + C0300A + C0300B + C0300C + C0400A + C0400B + C0400C
  Valid range: 0–15.
Exception: if patient was unable/refused BIMS, all C-codes must be "99".
Do NOT change any BIMS codes unless a BIMS field is explicitly named in the audit findings above.

────────────────────────────────────────────────────────────
RULE 2 — PHQ-2 SCREENING GATE (CMS mandatory — D section)
────────────────────────────────────────────────────────────
Step 1 — Calculate screen score: screen_score = D0150A1 + D0150B1
Step 2 — If screen_score < 3 (negative screen):
  • D0150C1, D0150D1, D0150E1, D0150F1, D0150G1, D0150H1, D0150I1 MUST ALL be null (NOT 0)
  • D0150C2, D0150D2, D0150E2, D0150F2, D0150G2, D0150H2, D0150I2 MUST ALL be null
  • D0160 = D0150A2 (if A1=1) + D0150B2 (if B1=1) — items C through I excluded from total
Step 3 — If screen_score >= 3 (positive screen):
  • Administer all 9 items A through I normally
  • D0160 = sum of all D0150X2 values where the corresponding D0150X1 = 1
PHQ_MOOD_INTERVIEW: use "completed" if screen was administered normally, or "99 - Unable to complete"
Do NOT change any PHQ codes unless a PHQ/D-section field is explicitly named in the audit findings above.

────────────────────────────────────────────────────────────
RULE 3 — GG DISCHARGE GOAL SCALE (GG0170 items)
────────────────────────────────────────────────────────────
GG discharge goal codes represent EXPECTED status at discharge — not current ability.
Valid coded values: 01=Dependent, 02=Substantial/Maximal assist, 03=Partial/Moderate assist,
  04=Supervision/touching assist, 05=Setup/cleanup only, 06=Independent
Exceptions: 07=Refused, 09=Not applicable, 10=Equipment unavailable, 88=Not attempted
Use coded strings only (e.g. "04", not "04 - Supervision/touching assist").

────────────────────────────────────────────────────────────
RULE 4 — OUTPUT FORMAT
────────────────────────────────────────────────────────────
Preserve the EXACT top-level JSON structure of the current version:
  • _synthetic_label — keep verbatim
  • sections — keep all section objects; update only the specific field answers that changed
  • fields_auto_extracted — preserve or update consistently
Within each field entry, the output shape must remain:
  "FIELD_CODE": {{"question": "<verbatim question text>", "answer": "<coded or descriptive value>"}}
For enum fields, use ONLY valid option codes as the answer (e.g. "2", not "2 - Moderate").
ONLY alter the specific field answers called out in the audit findings — leave all other fields unchanged.

Output ONLY valid JSON with no markdown fences, no commentary before or after.
Generate the revised tap_tap_gap_answers.json now:"""

# Step 5 fix — revise oasis_gold_standard.json
# Placeholders: {referral_text}, {ambient_scribe_text}, {medication_list_json},
#   {gap_answers_json}, {current_oasis_gold_standard_json}, {audit_conflicts_text}
OASIS_GOLD_STANDARD_FIX_PROMPT = """\
You are a clinical documentation specialist reviewing previously generated synthetic home-health patient documents.
A cross-document LLM audit has identified inconsistencies. Your task is to produce a REVISED version of the
OASIS GOLD STANDARD (oasis_gold_standard.json) that resolves these inconsistencies and makes all documents internally consistent.

=== ALL CURRENTLY GENERATED DOCUMENTS ===

--- REFERRAL PACKET (current version — read-only reference) ---
{referral_text}

--- MEDICATION LIST (current version — read-only reference) ---
{medication_list_json}

--- AMBIENT SCRIBE NOTE (current version — read-only reference) ---
{ambient_scribe_text}

--- TAP-TAP GAP ANSWERS (current version — read-only reference) ---
{gap_answers_json}

--- OASIS GOLD STANDARD (current version — to be revised) ---
{current_oasis_gold_standard_json}

=== AUDIT FINDINGS — INCONSISTENCIES TO FIX ===
{audit_conflicts_text}

=== YOUR TASK ===
Produce a REVISED oasis_gold_standard.json that resolves every inconsistency listed in the audit findings.

MANDATORY CLINICAL RULES — violations will cause dataset rejection:

────────────────────────────────────────────────────────────
RULE 1 — GAP-ANSWERS CODES ARE AUTHORITATIVE
────────────────────────────────────────────────────────────
The following code groups MUST be copied verbatim from gap_answers — do NOT change them,
even if flagged in the audit findings, unless the field is EXPLICITLY listed as a conflict:
  • All C-section codes (BIMS): C0100, C0200, C0300, C0300A, C0300B, C0300C,
      C0400, C0400A, C0400B, C0400C, C0500, C1310
  • All D-section codes (PHQ-9): D0150A1–I1, D0150A2–I2, D0160, PHQ_MOOD_INTERVIEW
  • All GG0130 (self-care) and GG0170 (mobility) codes — these reflect live clinical assessment

────────────────────────────────────────────────────────────
RULE 2 — PHQ-2 GATE MUST BE PRESERVED
────────────────────────────────────────────────────────────
If gap_answers has D0150A1 + D0150B1 < 3 (negative screen), the gold standard must also have:
  D0150C1–I1 = null (omitted) and D0150C2–I2 = null (omitted).
Do not set these to "0" when the screen is negative.

────────────────────────────────────────────────────────────
RULE 3 — CODED VALUES ONLY
────────────────────────────────────────────────────────────
Use valid OASIS coded values as plain strings. Never append descriptions:
  ✓  "2"     ✗  "2 - Requires assistance"
  ✓  "06"    ✗  "06=Independent"
  ✓  "NA"    ✗  "Not applicable"
Valid GG discharge goal codes: "01" "02" "03" "04" "05" "06" "07" "09" "10" "88"
Skip items do NOT appear in the output at all — omit rather than setting null.

────────────────────────────────────────────────────────────
RULE 4 — MULTI-VALUE ITEM FLATTENING
────────────────────────────────────────────────────────────
Multi-value items must use the same flattened key format as the current version:
  Diagnosis list suffix:  M1021, M1023_1, M1023_2, M1023_3
  Multi-select checkbox:  M1030_1, M1030_2
  Nested assessment sub:  O0110A1, O0110A2, K0520Z1
  Height/weight:          M1060A (height inches), M1060B (weight lbs)
Do not combine these into a parent key.

────────────────────────────────────────────────────────────
RULE 5 — OUTPUT FORMAT
────────────────────────────────────────────────────────────
The output must be a flat JSON object. Every key is a string OASIS item code; every value
is a plain string. Preserve the "_synthetic_label" key from the current version.
  {{
    "_synthetic_label": "SYNTHETIC — NOT REAL PATIENT DATA",
    "M1021": "I50.9",
    "M1700": "0",
    ...
  }}

ONLY alter the specific field values called out in the audit findings — leave all other
fields at their current values.

Output ONLY valid JSON with no markdown fences, no commentary before or after.
Generate the revised oasis_gold_standard.json now:"""

