"""
app.config.constants — Domain constants shared across all generator services.

Organises clinical knowledge that was previously scattered inside individual
service files.  Importing from here instead of cross-importing between service
modules avoids circular dependencies and makes every constant's scope explicit.

Sections:
    PATIENT METADATA      — approved archetypes, age brackets
    REFERRAL PACKET       — archetype clinical hints, referral format instructions
    AMBIENT SCRIBE        — prohibited keywords, required sections, nursing context
    OASIS GOLD STANDARD   — BIMS/PHQ copy codes, GG mapping tables, ADL copy codes,
                            section batch lists, HIP score codes
"""

from __future__ import annotations

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  PATIENT METADATA CONSTANTS (used by patient_metadata_generator.py)         ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

# PRD 0A.3 — approved archetype names (snake_case) mapped to PDGM groups.
# These eight archetypes cover the Phase 1 dataset requirements; EDGE_CASE is
# the wildcard for refusal/unable-to-answer scenarios.
APPROVED_ARCHETYPES: dict[str, str] = {
    "total_knee_replacement": "MS_REHAB",
    "chf_exacerbation": "MMTA_CARDIAC",
    "diabetic_foot_ulcer": "WOUNDS",
    "cva_stroke_rehab": "NEURO_STROKE",
    "hip_fracture": "MS_REHAB",
    "copd_exacerbation": "MMTA_RESPIRATORY",
    "sepsis_cellulitis_recovery": "MMTA_INFECTIOUS",
    "patient_refuses_cannot_answer": "EDGE_CASE",
}

# CMS PDGM grouper-compliant age bracket strings.
# These are the only accepted values for the ``age_bracket`` metadata field.
VALID_AGE_BRACKETS: list[str] = ["18-64", "65-74", "75-84", "85+"]


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  REFERRAL PACKET CONSTANTS (used by referral_packet_generator.py)           ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

# Per-archetype ICD-10 guidance, high-risk medications, services, and homebound
# rationale.  Used to ground the LLM referral prompt in clinically valid codes.
ARCHETYPE_CLINICAL_HINTS: dict[str, dict] = {
    "total_knee_replacement": {
        "primary_hint": (
            "M17.11 or M17.12 — primary osteoarthritis of knee (right/left). "
            "Use Z96.641/Z96.651 if post-surgical encounter for the prosthesis."
        ),
        "secondary_hints": [
            "M81.0 — Age-related osteoporosis",
            "I10 — Essential hypertension",
            "E11.9 — Type 2 diabetes mellitus without complications",
            "Z79.899 — Long-term use of other medications",
        ],
        "services": "PT (3x/week x 8 weeks), OT (2x/week x 4 weeks), SN (2x/week x 4 weeks)",
        "homebound_reason": (
            "non-weight-bearing or partial weight-bearing per orthopedic surgeon, "
            "pain with ambulation, unable to safely leave home without assistance"
        ),
        "high_risk_meds": [
            "Enoxaparin 40 mg subcutaneous daily ⚠ HIGH RISK — anticoagulant",
            "Oxycodone/acetaminophen 5/325 mg oral every 4-6 hrs PRN pain ⚠ HIGH RISK — opioid",
        ],
    },
    "chf_exacerbation": {
        "primary_hint": (
            "I50.22 — Chronic systolic (congestive) heart failure, or I50.32, I50.9. "
            "Do NOT use I50.9 if a more specific code is clinically appropriate."
        ),
        "secondary_hints": [
            "I48.91 — Unspecified atrial fibrillation",
            "I10 — Essential hypertension",
            "E11.9 — Type 2 diabetes mellitus without complications",
            "N18.3 — Chronic kidney disease, stage 3",
        ],
        "services": "SN (3x/week x 4 weeks, then reassess), PT (2x/week x 6 weeks)",
        "homebound_reason": (
            "severe dyspnea on exertion, 2+ bilateral lower extremity edema, "
            "extreme fatigue after fewer than 10 feet of ambulation"
        ),
        "high_risk_meds": [
            "Furosemide 40 mg oral daily",
            "Digoxin 0.125 mg oral daily ⚠ HIGH RISK — narrow therapeutic index",
            "Warfarin 5 mg oral daily ⚠ HIGH RISK — anticoagulant (target INR 2-3)",
            "Metoprolol succinate 50 mg oral daily",
            "Lisinopril 10 mg oral daily",
        ],
    },
    "diabetic_foot_ulcer": {
        "primary_hint": (
            "E11.621 — Type 2 diabetes mellitus with foot ulcer (right foot). "
            "Secondary wound code: L97.519 — Non-pressure chronic ulcer of other part of foot."
        ),
        "secondary_hints": [
            "L97.519 — Non-pressure chronic ulcer of other part of right foot, unspecified severity",
            "I10 — Essential hypertension",
            "N18.3 — Chronic kidney disease, stage 3",
            "E11.65 — Type 2 diabetes mellitus with hyperglycemia",
        ],
        "services": "SN (5x/week x 4 weeks for daily wound care), PT (2x/week x 6 weeks)",
        "homebound_reason": (
            "painful right foot wound prevents safe ambulation outside the home, "
            "requires daily skilled wound care and dressing changes"
        ),
        "high_risk_meds": [
            "Insulin glargine 20 units subcutaneous every evening ⚠ HIGH RISK — insulin",
            "Metformin 500 mg oral twice daily",
            "Lisinopril 10 mg oral daily",
            "Atorvastatin 40 mg oral nightly",
        ],
    },
    "cva_stroke_rehab": {
        "primary_hint": (
            "I63.9 — Cerebral infarction, unspecified; or I63.50, I63.49. "
            "Do NOT use R47.01 (aphasia) as primary — it is a manifestation code."
        ),
        "secondary_hints": [
            "I48.91 — Unspecified atrial fibrillation",
            "I10 — Essential hypertension",
            "G81.90 — Hemiplegia, unspecified, affecting unspecified side",
            "E11.9 — Type 2 diabetes mellitus without complications",
        ],
        "services": (
            "PT (5x/week x 8 weeks), OT (5x/week x 8 weeks), SLP (3x/week x 8 weeks), "
            "SN (3x/week x 4 weeks)"
        ),
        "homebound_reason": (
            "right/left hemiplegia and expressive aphasia prevent safe independent "
            "ambulation outside the home; requires maximal assistance for transfers"
        ),
        "high_risk_meds": [
            "Warfarin 5 mg oral daily ⚠ HIGH RISK — anticoagulant",
            "Aspirin 81 mg oral daily",
            "Clopidogrel 75 mg oral daily",
            "Lisinopril 10 mg oral daily",
        ],
    },
    "hip_fracture": {
        "primary_hint": (
            "S72.001D — Displaced femoral neck fracture, right, subsequent encounter "
            "(use 7th char D for subsequent home health encounter, NOT A)."
        ),
        "secondary_hints": [
            "M81.0 — Age-related osteoporosis without current pathological fracture",
            "I10 — Essential hypertension",
            "E11.9 — Type 2 diabetes mellitus without complications",
            "Z79.52 — Long-term use of systemic steroids",
        ],
        "services": "PT (5x/week x 8 weeks), OT (3x/week x 6 weeks), SN (3x/week x 4 weeks)",
        "homebound_reason": (
            "non-weight-bearing status per orthopedic surgeon, "
            "post-surgical pain, cannot safely exit home without skilled assistance"
        ),
        "high_risk_meds": [
            "Enoxaparin 40 mg subcutaneous daily ⚠ HIGH RISK — anticoagulant (DVT prophylaxis)",
            "Oxycodone 5 mg oral every 4-6 hrs PRN ⚠ HIGH RISK — opioid",
            "Alendronate 70 mg oral weekly",
            "Calcium carbonate 500 mg + vitamin D3 400 IU oral twice daily",
        ],
    },
    "copd_exacerbation": {
        "primary_hint": (
            "J44.1 — Chronic obstructive pulmonary disease with acute exacerbation. "
            "Do NOT use R06.02 (dyspnea) as a separate code — it is a manifestation of J44.1."
        ),
        "secondary_hints": [
            "I10 — Essential hypertension",
            "Z87.891 — Personal history of nicotine dependence",
            "J96.11 — Chronic respiratory failure with hypoxia",
            "E11.9 — Type 2 diabetes mellitus without complications",
        ],
        "services": "SN (3x/week x 4 weeks), PT (2x/week x 6 weeks)",
        "homebound_reason": (
            "severe dyspnea on exertion, on home O2 2 L/min, "
            "unable to walk from bedroom to kitchen without stopping to rest"
        ),
        "high_risk_meds": [
            "Prednisone 40 mg oral daily x 5 days tapering",
            "Azithromycin 500 mg oral daily x 5 days",
            "Tiotropium bromide 18 mcg inhaled daily",
            "Albuterol sulfate 2.5 mg nebulized every 4 hrs PRN",
        ],
    },
    "sepsis_cellulitis_recovery": {
        "primary_hint": (
            "A41.9 — Sepsis, unspecified organism. "
            "Or L03.115 — Cellulitis of right lower limb if cellulitis is primary driver."
        ),
        "secondary_hints": [
            "E11.9 — Type 2 diabetes mellitus without complications",
            "I10 — Essential hypertension",
            "N18.3 — Chronic kidney disease, stage 3",
            "D64.9 — Anemia, unspecified",
        ],
        "services": (
            "SN (daily x 2 weeks for IV antibiotic admin, then 3x/week x 2 weeks), "
            "PT (2x/week x 6 weeks)"
        ),
        "homebound_reason": (
            "profound weakness and fatigue from sepsis recovery, "
            "requires IV antibiotic therapy requiring skilled nursing oversight"
        ),
        "high_risk_meds": [
            "Vancomycin 1250 mg IV every 12 hours ⚠ HIGH RISK — IV antibiotic (renal monitoring required)",
            "Furosemide 20 mg oral daily",
            "Insulin regular sliding scale subcutaneous with meals ⚠ HIGH RISK — insulin",
            "Metronidazole 500 mg oral three times daily",
        ],
    },
    "patient_refuses_cannot_answer": {
        "primary_hint": (
            "Choose a clinically appropriate primary diagnosis code for the scenario. "
            "Example: I50.9 — Heart failure, unspecified; or E11.9 — T2DM."
        ),
        "secondary_hints": [
            "I10 — Essential hypertension",
            "E11.9 — Type 2 diabetes mellitus",
            "Z65.8 — Other specified problems related to psychosocial circumstances",
        ],
        "services": "SN (3x/week x 4 weeks)",
        "homebound_reason": (
            "overall debility and functional decline; patient requires supervision "
            "and considerable effort to leave home safely"
        ),
        "high_risk_meds": [],
    },
}

# Format-specific referral document style instructions injected into the LLM prompt.
# Keys map to the ``referral_format`` field generated in Step 1 metadata.
REFERRAL_FORMAT_INSTRUCTIONS: dict[str, str] = {
    "clean_emr": (
        "FORMAT: clean_emr — This is a well-formatted electronic medical record discharge referral. "
        "Use clear, labeled section headings in ALL CAPS. Write in complete professional clinical sentences. "
        "All fields must be fully populated. Medication list must include full name, dose, route, and frequency. "
        "Use standard clinical abbreviations sparingly (e.g. SOC, SN, PT, OT, SLP, PRN, BID, TID). "
        "H&P narrative should be 3-5 sentences with real clinical abbreviations (e.g. '78 y/o F w/ h/o CHF'). "
        "Overall length: 500-700 words."
    ),
    "messy_fax": (
        "FORMAT: messy_fax — This referral was received by fax and appears handwritten or scanned. "
        "Do NOT use structured headings — use short labels followed by colons (e.g. 'Pt:', 'Dx:', 'Meds:'). "
        "Use heavy clinical abbreviations throughout: pt, dx, hx, s/p, w/, c/o, y/o, F/M, med mgmt, SN, PT. "
        "Sentences may be truncated or run together. Some fields may be terse (1-2 words). "
        "Medication list may have missing routes or frequencies for 1-2 items. "
        "The H&P should be a single run-on sentence packed with abbreviations. "
        "Overall length: 200-350 words. Deliberately messy but still readable."
    ),
    "minimal": (
        "FORMAT: minimal — This is a bare-bones referral with only mandatory fields. "
        "Short labeled sections, no narrative prose beyond 1-2 sentences for H&P. "
        "Medication list: at most 4-5 items (no indications, just name/dose/frequency). "
        "Skip ordered services detail — one line only. "
        "Homebound status: one sentence. "
        "Overall length: 150-250 words. Sparse but all required sections present."
    ),
}


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  AMBIENT SCRIBE CONSTANTS (used by ambient_scribe_generator.py)             ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

# PRD hard rule: these exact strings must NEVER appear in the ambient nurse note.
# BIMS and PHQ wording is reserved for the gap-answer sections only; the nurse
# note must describe cognition and mood in plain narrative language.
PROHIBITED_AMBIENT_KEYWORDS: list[str] = [
    "BIMS score",
    "BIMS interview",
    "PHQ-2",
    "PHQ-9",
    "PHQ2",
    "PHQ9",
]

# All 7 section headers that every ambient scribe output must contain.
# Checked verbatim (upper-cased) against the generated text during validation.
REQUIRED_NURSING_SECTIONS: list[str] = [
    "VITAL SIGNS",
    "PHYSICAL ASSESSMENT",
    "ADL OBSERVATIONS",
    "HOME SAFETY OBSERVATION",
    "PATIENT GOALS",
    "PAIN ASSESSMENT",
    "PLAN & FOLLOW-UP",
]

# Per-archetype nursing context: typical vital ranges, physical assessment focus,
# ADL picture, home safety concerns, SMART goal, and cognition/mood narrative.
# Injected into the ambient scribe LLM prompt to ground clinical content.
ARCHETYPE_NURSING_CONTEXT: dict[str, dict] = {
    "total_knee_replacement": {
        "vitals_context": (
            "HR 70-85 regular, BP 130-150/80-90 sitting. O2 sat 95-98% on room air. "
            "Pain typically 5-7/10 at surgical site with movement."
        ),
        "physical_focus": (
            "Assess surgical knee incision (staples/sutures), wound drainage, "
            "surrounding erythema/warmth/edema. Neurovascular checks to bilateral lower extremities. "
            "CPM use if ordered. Ice/elevation of operative limb observed. "
            "Check calf for DVT signs (Homans sign, unilateral calf warmth/swelling)."
        ),
        "adl_picture": (
            "Requires minimal to moderate assistance for lower body dressing and bathing. "
            "Weight-bearing status per surgeon (NWB/PWB/TTWB) — confirm and document. "
            "Uses walker or crutches for ambulation. Transfer from bed/chair with minimal assistance."
        ),
        "home_safety": (
            "Raised toilet seat and grab bars critical. Assess for scatter rugs, "
            "thresholds, and stairs. Walker clearance through doorways. Adequate lighting."
        ),
        "typical_goal": (
            "Patient will ambulate 150 feet with walker independently and demonstrate "
            "safe stair negotiation with railing within 6 weeks of SOC."
        ),
        "cognition_mood": (
            "alert and oriented x4 (person/place/time/event). Appeared motivated and "
            "engaged, verbalized understanding of weight-bearing precautions."
        ),
    },
    "chf_exacerbation": {
        "vitals_context": (
            "HR irregularly irregular if AF. BP may be elevated 140-160/90-100. "
            "O2 sat 90-94% on room air — note O2 delivery and flow rate. "
            "Weight critical to document — compare to hospital discharge weight. "
            "Pain typically chest heaviness or dyspnea, not classic pain."
        ),
        "physical_focus": (
            "Auscultate breath sounds for crackles (bibasilar common). "
            "Assess JVD at 45°. Bilateral lower extremity pitting edema — grade and measure. "
            "Skin integrity of edematous areas (risk for weeping). "
            "Assess for orthopnea (number of pillows used to sleep)."
        ),
        "adl_picture": (
            "Significant activity intolerance. Patient becomes dyspneic with minimal ADLs. "
            "Requires assistance for bathing and lower body dressing due to dyspnea on exertion. "
            "Ambulation severely limited — stops within 10-20 feet for rest."
        ),
        "home_safety": (
            "Sodium and fluid restriction adherence. Access to daily weight scale. "
            "Medication storage and adherence. Fall risk from orthopnea, edema, weakness. "
            "Emergency action plan posted or reviewed."
        ),
        "typical_goal": (
            "Patient will identify and verbalize 3 warning signs of CHF exacerbation "
            "and demonstrate daily weight log compliance within 2 weeks. "
            "Weight will stabilize within ±2 lbs over 7 days within 4 weeks of SOC."
        ),
        "cognition_mood": (
            "alert and oriented x4 (person/place/time/event). Appeared anxious about "
            "hospital readmission but cooperative and engaged with teaching."
        ),
    },
    "diabetic_foot_ulcer": {
        "vitals_context": (
            "Blood glucose documented (finger-stick or patient-reported). "
            "BP 130-155/80-95. HR 72-88 regular. O2 sat 93-97% on room air. "
            "Pain at wound site 4-7/10 with dressing change."
        ),
        "physical_focus": (
            "Detailed wound assessment: location, dimensions (L x W x D in cm), "
            "wound bed (beefy red granulation vs. necrotic/slough %), drainage (mod serosanguineous), "
            "periwound skin (erythema, maceration, induration). Odor. "
            "Peripheral pulses bilateral. Sensation — monofilament tested."
        ),
        "adl_picture": (
            "Painful right foot wound significantly limits ambulation. "
            "Unable to bear full weight — uses walker or wheelchair. "
            "Requires moderate assistance for lower body dressing due to wound location. "
            "Independent with upper body ADLs if seated."
        ),
        "home_safety": (
            "Inspect footwear — no bare-foot ambulation. "
            "Caregiver ability to perform dressing changes between visits. "
            "Wound supplies available and stored appropriately. "
            "Blood glucose monitoring supplies and log reviewed."
        ),
        "typical_goal": (
            "Wound will demonstrate 30% reduction in dimension and progression of granulation "
            "tissue within 4 weeks. Patient/caregiver will verbalize wound care technique and "
            "infection signs within 2 weeks of SOC."
        ),
        "cognition_mood": (
            "alert and oriented x4 (person/place/time/event). Appeared motivated, "
            "caregiver present and engaged with wound care instruction."
        ),
    },
    "cva_stroke_rehab": {
        "vitals_context": (
            "BP carefully monitored — may be permissively elevated post-CVA "
            "(140-160/90-100 acceptable per physician parameters). "
            "HR 65-90. O2 sat 93-97% on room air. "
            "Document speech clarity and swallowing screen."
        ),
        "physical_focus": (
            "Neurological: cranial nerves intact/impaired (document which). "
            "Motor strength bilateral upper and lower extremities (0-5 scale). "
            "Facial droop present/absent. Speech — fluent/dysarthric/aphasic (expressive/receptive). "
            "Swallowing screen (not formal — just safe swallow observation). "
            "Gait: hemiparetic — ambulatory with device vs. non-ambulatory."
        ),
        "adl_picture": (
            "Maximal to total assistance for transfers and mobility. "
            "Moderate to maximal assistance for upper and lower body dressing. "
            "Grooming: minimal to moderate assistance. "
            "Cannot communicate needs reliably if expressive aphasia present."
        ),
        "home_safety": (
            "Transfer and fall risk extreme — caregiver training critical. "
            "Bed rails, grab bars, elevated toilet seat, wheelchair access. "
            "Swallowing precautions if applicable (consistency of liquids/solids). "
            "Wandering risk if cognitive impairment present."
        ),
        "typical_goal": (
            "Patient will ambulate 30 feet with hemiwalker and minimal assist within 6 weeks. "
            "Caregiver will demonstrate safe transfer technique by end of week 1."
        ),
        "cognition_mood": (
            "alert with fluctuating orientation, oriented x3 (person/place/time). "
            "Appeared frustrated by communication barriers but cooperative with gestures and yes/no responses."
        ),
    },
    "hip_fracture": {
        "vitals_context": (
            "HR 75-90, may be elevated from pain. BP 130-155/80-90. "
            "O2 sat 93-97% on room air post-operatively. "
            "Pain at surgical site 5-8/10 with movement."
        ),
        "physical_focus": (
            "Assess surgical hip incision — inspect staples/sutures, drainage, erythema. "
            "Hip precautions reviewed and practiced (no flexion >90°, no internal rotation, "
            "no adduction past midline — or anterior approach precautions as ordered). "
            "Bilateral lower extremity neurovascular check. "
            "Assess for signs of DVT. Compression device compliance."
        ),
        "adl_picture": (
            "Hip precautions strictly limit ADL independence. "
            "Moderate to maximal assistance for lower body dressing and bathing. "
            "NWB or PWB per surgeon — walker or crutches with assist. "
            "Raised toilet seat and long-handled adaptive equipment essential."
        ),
        "home_safety": (
            "Hip precaution equipment in place (raised toilet seat, reacher, sock aid, long-handled sponge). "
            "Stairs and thresholds — assess ability to negotiate safely. "
            "Caregiver present and educated on precautions. "
            "Bed height appropriate for safe transfers."
        ),
        "typical_goal": (
            "Patient will ambulate 100 feet with walker and minimal assist within 4 weeks "
            "while maintaining all hip precautions. "
            "Caregiver will verbalize all hip precautions by end of week 1."
        ),
        "cognition_mood": (
            "alert and oriented x4 (person/place/time/event). Appeared anxious about "
            "re-fracture risk but cooperative and motivated with therapy goals."
        ),
    },
    "copd_exacerbation": {
        "vitals_context": (
            "O2 sat critical — document at rest and with exertion. "
            "Target O2 sat 88-92% for COPD (not 95%+ — risk of hypercapnic drive suppression). "
            "RR elevated 18-24. HR 80-100. BP 130-155/80-90. "
            "Temp normal — fever may indicate infection/exacerbation."
        ),
        "physical_focus": (
            "Auscultate breath sounds bilateral — diffuse wheezing, prolonged expiratory phase, "
            "reduced air entry at bases. Use of accessory muscles (sternocleidomastoid, scalene). "
            "Pursed-lip breathing observed. Barrel chest configuration if chronic. "
            "Note O2 delivery system and flow rate, confirm O2 concentrator function."
        ),
        "adl_picture": (
            "Severe activity intolerance — dyspnea limits all ADLs. "
            "Requires breaks during bathing and dressing due to O2 desaturation. "
            "Ambulation limited to 20-30 feet before needing 3-5 minute rest. "
            "Pursed-lip breathing technique used during activity."
        ),
        "home_safety": (
            "Home O2 concentrator placement and function (keep away from open flame). "
            "Stair safety — handrail use and O2 tubing management. "
            "No smoking in home — active or passive smoke exposure. "
            "Rescue inhaler within reach at all times."
        ),
        "typical_goal": (
            "Patient will demonstrate correct pursed-lip breathing technique and use with "
            "activity, maintaining O2 sat ≥88% with ADLs within 4 weeks. "
            "Patient will verbalize COPD action plan and when to seek emergency care by end of week 2."
        ),
        "cognition_mood": (
            "alert and oriented x4 (person/place/time/event). Appeared fatigued but "
            "engaged and motivated to avoid rehospitalization."
        ),
    },
    "sepsis_cellulitis_recovery": {
        "vitals_context": (
            "Monitor temp — resolution from fever is progress indicator. "
            "BP 110-135/70-85 (sepsis recovery — may be hypotensive, watch for orthostatic changes). "
            "HR 80-100. O2 sat 93-97% on room air. "
            "Weight — document to track fluid status."
        ),
        "physical_focus": (
            "Cellulitis site assessment: erythema boundaries (mark and measure), "
            "warmth, induration, drainage from any open areas. "
            "IV access site if PICC present — dressing integrity, absence of phlebitis. "
            "Overall strength and endurance — profound weakness expected in early recovery. "
            "Assess for secondary infection signs."
        ),
        "adl_picture": (
            "Profound generalized weakness from sepsis episode limits all ADLs. "
            "Moderate to maximal assistance for transfers and ambulation. "
            "Minimal to moderate assistance for self-care depending on recovery phase. "
            "Activity tolerance very limited — 10-15 foot ambulation causes significant fatigue."
        ),
        "home_safety": (
            "IV line safety if PICC present — protect from water exposure, dressing changes. "
            "Medication administration: IV antibiotic schedule adherence. "
            "Fall risk extreme — orthostatic hypotension likely. "
            "Caregiver critical for medication schedule and IV management."
        ),
        "typical_goal": (
            "Patient will ambulate 50 feet with walker and minimal assist within 3 weeks. "
            "IV antibiotic course will complete without line complications. "
            "Patient/caregiver will demonstrate PICC care and flush technique by end of week 1."
        ),
        "cognition_mood": (
            "alert and oriented x4 (person/place/time/event). Appeared fatigued and "
            "somewhat withdrawn but cooperative with assessment."
        ),
    },
    "patient_refuses_cannot_answer": {
        "vitals_context": (
            "Document all obtainable vitals. Note patient cooperation level. "
            "HR, BP, O2 sat attempted — document if refused. Temperature obtained."
        ),
        "physical_focus": (
            "Conduct assessment to extent patient cooperates. "
            "Document specific refusals. Prioritise safety assessment. "
            "Observe affect, mobility, and skin integrity from available observation."
        ),
        "adl_picture": (
            "Formal ADL assessment limited by refusal. "
            "Document observed functional status. "
            "Note specific tasks patient declines to perform or discuss."
        ),
        "home_safety": (
            "Assess environment to extent possible. "
            "Note safety hazards observed. Document any caregiver present and their report. "
            "Social work referral may be appropriate."
        ),
        "typical_goal": (
            "Patient will allow full nursing assessment within 2 visits. "
            "Short-term safety assessment will be completed with available data."
        ),
        "cognition_mood": (
            "orientation unclear — patient declined formal questions. "
            "Appeared guarded but not agitated. Able to answer yes/no questions."
        ),
    },
}


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  OASIS GOLD STANDARD CONSTANTS (used by oasis_gold_standard_generator.py)   ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

# BIMS codes — copied verbatim from tap_tap_gap_answers (never regenerated by LLM).
# Matches _BIMS_MANDATORY in gap_answers_generator.py.
BIMS_COPY_CODES: list[str] = [
    "C0100",
    "C0200",
    "C0300", "C0300A", "C0300B", "C0300C",
    "C0400", "C0400A", "C0400B", "C0400C",
    "C0500",
    "C1310",
]

# PHQ-9 codes — copied verbatim from tap_tap_gap_answers (never regenerated by LLM).
# Matches _PHQ_MANDATORY in gap_answers_generator.py.
PHQ_COPY_CODES: list[str] = [
    "D0150A1", "D0150A2",
    "D0150B1", "D0150B2",
    "D0150C1", "D0150C2",
    "D0150D1", "D0150D2",
    "D0150E1", "D0150E2",
    "D0150F1", "D0150F2",
    "D0150G1", "D0150G2",
    "D0150H1", "D0150H2",
    "D0150I1", "D0150I2",
    "D0160",
    "PHQ_MOOD_INTERVIEW",
]

# Self-care admission performance codes used to calculate the HIP score.
# HIP = sum of GG0130A1 through GG0130E1 (range 5–30).
HIP_CODES: list[str] = [
    "GG0130A1", "GG0130B1", "GG0130C1", "GG0130D1", "GG0130E1",
]

# GG0130 Self-Care grouped label → OASIS sub-code letter mapping.
# Step 4 gap_answers may use Title Case OR snake_case keys.
# "Dressing" (combined key) maps to both D and E simultaneously.
GG0130_LABEL_TO_LETTER: dict[str, str | list[str]] = {
    # Title Case (PATIENT-0050/0051/0052 style)
    "Eating": "A",
    "Oral Hygiene": "B",
    "Shower/Bathe": "C",
    "Upper Body Dressing": "D",
    "Lower Body Dressing": "E",
    "Toileting Hygiene": "F",
    "Dressing": ["D", "E"],         # combined key → both D and E
    # snake_case (PATIENT-0053+ style)
    "eating": "A",
    "oral_hygiene": "B",
    "shower_bathe": "C",
    "dressing_upper": "D",
    "dressing_lower": "E",
    "toileting_hygiene": "F",
    "dressing": ["D", "E"],         # combined snake_case → both D and E
}

# GG0170 Mobility grouped key → OASIS sub-code letter mapping.
# Step 4 gap_answers may use single-letter keys ({"A": "04"}) OR
# descriptive snake_case keys ({"sit_to_stand": "04"}).
GG0170_KEY_TO_LETTER: dict[str, str] = {
    # Letter keys pass-through
    "A": "A", "B": "B", "C": "C", "D": "D", "E": "E", "F": "F",
    "G": "G", "I": "I", "J": "J", "K": "K",
    "L": "L", "M": "M", "N": "N", "O": "O", "P": "P",
    # Descriptive snake_case keys
    "roll_left": "A",
    "roll_right": "A",          # fallback if right-side variant is used
    "sit_to_lying": "B",
    "lying_to_sitting": "C",
    "sit_to_stand": "D",
    "chair_transfer": "E",
    "toilet_transfer": "F",
    "car_transfer": "G",
    "walk_10_feet": "I",
    "walk_50_feet": "J",
    "walk_150_feet": "K",
    "one_step": "L",
    "four_steps": "M",
    "twelve_steps": "N",
    "picking_up_object": "O",
    "wheelchair_50_feet": "P",
}

# Ordered list of all GG0170 sub-code letters used for fallback iteration
# when GG0170 is absent from gap_answers.
GG0170_LETTERS: list[str] = [
    "A", "B", "C", "D", "E", "F", "I", "J", "K", "L", "M", "N", "O", "P",
]

# ADL M-codes that are copied verbatim from Step 4 gap_answers.
# These are authoritative from the live clinical assessment and must not be
# overridden by the LLM.
ADL_COPY_CODES: list[str] = [
    "M1800", "M1810", "M1820", "M1830", "M1840",
    "M1845", "M1850", "M1860", "M1870", "M1880",
    "M1890", "M1900", "M1910",
]

# ── LLM section batch definitions ─────────────────────────────────────────────
# BIMS (C section) and PHQ (D section) codes are excluded from all batches
# because they are always copied directly from gap_answers.
# Each tuple: (batch_name, [field_codes])

# Batch A: Administrative, SOC, and Diagnosis codes
_BATCH_A_ADMIN_DIAGNOSIS: list[str] = [
    "M0069", "M0080", "M0090", "M0100", "M0102", "M0104", "M0110", "M0150",
    "A1005", "A1010", "A1110",
    "M1000", "M1005", "M1011", "M1017",
    "M1021", "M1023", "M1028", "M1030", "M1033", "M1060",
    "K0520", "O0110",
]

# Batch B: Sensory, Behavioral, Living Arrangements, and Pain codes
_BATCH_B_SENSORY_BEHAVIORAL: list[str] = [
    "B0200", "B1000", "B1300",
    "M1100",
    "M1200", "M1210", "M1220", "M1230", "M1240", "M1242",
    "M1700", "M1710", "M1720", "M1740", "M1745",
    "D0700",
    "J0510", "J0520", "J0530", "J0600",
]

# Batch C: GG0100 Prior Function, GG0110 Prior Devices, and GG0130 discharge goals (X2 only).
# NOTE: GG0130 X1 admission performance codes are derived from Step 4 gap_answers,
#       NOT generated by the LLM for this batch.
_BATCH_C_GG_SELF_CARE: list[str] = [
    "GG0100A", "GG0100B", "GG0100C", "GG0100D",
    "GG0110A", "GG0110B", "GG0110C", "GG0110D", "GG0110E", "GG0110F",
    "GG0130A2", "GG0130B2", "GG0130C2", "GG0130D2",
    "GG0130E2", "GG0130F2",
    "GG0130G1", "GG0130G2",
]

# Batch D: GG0170 Mobility discharge goals (X2 only) and M-ADL codes.
# NOTE: GG0170 X1 admission performance codes are derived from Step 4 gap_answers
#       and overwrite any LLM values for those codes.  M-ADL codes are also overwritten
#       by gap_answers values where present.
_BATCH_D_GG_MOBILITY_ADL: list[str] = [
    "GG0170A2", "GG0170B2", "GG0170C2", "GG0170D2", "GG0170E2", "GG0170F2",
    "GG0170G1", "GG0170G2",
    "GG0170I2", "GG0170J2", "GG0170K2", "GG0170L2",
    "GG0170M2", "GG0170N2", "GG0170O2", "GG0170P2",
    "GG0170RR1",
    "M1800", "M1810", "M1820", "M1830", "M1840", "M1845",
    "M1850", "M1860", "M1870", "M1880", "M1890", "M1900", "M1910",
]

# Batch E: Wound, Respiratory, Elimination, Medication, and Care Management codes
_BATCH_E_WOUND_RESPIRATORY: list[str] = [
    "M1300", "M1302", "M1306", "M1307", "M1308", "M1309",
    "M1310", "M1311", "M1312", "M1313", "M1314",
    "M1320", "M1322", "M1324",
    "M1330", "M1332", "M1334",
    "M1340", "M1342", "M1350",
    "M1400", "M1500", "M1501", "M1510", "M1511",
    "M1600", "M1610", "M1615", "M1620", "M1630",
    "M2001", "M2003", "M2005", "M2010", "M2016",
    "M2020", "M2030", "M2040",
    # N0415 is handled deterministically from gap_answers — not LLM-generated.
    # Sub-flags N0415E/H/I/F are injected by OasisGoldStandardGenerator._decompose_n0415_from_gap_answers().
    "M2100", "M2102", "M2110",
]

# Ordered list of all 5 LLM section batches.
# Each entry: (section_name_for_logging, list_of_field_codes)
OASIS_SECTION_BATCHES: list[tuple[str, list[str]]] = [
    ("A_admin_diagnosis", _BATCH_A_ADMIN_DIAGNOSIS),
    ("B_sensory_behavioral_living", _BATCH_B_SENSORY_BEHAVIORAL),
    ("C_gg_self_care", _BATCH_C_GG_SELF_CARE),
    ("D_gg_mobility_adl", _BATCH_D_GG_MOBILITY_ADL),
    ("E_wound_respiratory_medication", _BATCH_E_WOUND_RESPIRATORY),
]


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  GAP ANSWERS CONSTANTS (used by gap_answers_generator.py)                   ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

# BIMS individual sub-score field codes used to compute the total (C0500).
# sum(sub-scores) for C0200 + C0300A + C0300B + C0300C + C0400A + C0400B + C0400C
# must equal C0500.  0-15 scale.
BIMS_SUB_CODES: list[str] = [
    "C0200",
    "C0300A",
    "C0300B",
    "C0300C",
    "C0400A",
    "C0400B",
    "C0400C",
]

# Field code for the BIMS total score (sum of BIMS_SUB_CODES).
BIMS_TOTAL_CODE: str = "C0500"

# All BIMS-section codes that must always appear in gap_answers (live cogn. testing required).
BIMS_MANDATORY: list[str] = [
    "C0100",
    "C0200",
    "C0300",
    "C0300A", "C0300B", "C0300C",
    "C0400",
    "C0400A", "C0400B", "C0400C",
    "C0500",
    "C1310",
]

# All PHQ-9 codes that must always appear in gap_answers (live mood interview required).
PHQ_MANDATORY: list[str] = [
    "D0150A1", "D0150A2",
    "D0150B1", "D0150B2",
    "D0150C1", "D0150C2",
    "D0150D1", "D0150D2",
    "D0150E1", "D0150E2",
    "D0150F1", "D0150F2",
    "D0150G1", "D0150G2",
    "D0150H1", "D0150H2",
    "D0150I1", "D0150I2",
    "D0160",
    "PHQ_MOOD_INTERVIEW",
]

# PHQ Column 2 (frequency) codes used to validate the D0160 total score.
PHQ_FREQUENCY_CODES: list[str] = [
    "D0150A2", "D0150B2", "D0150C2", "D0150D2",
    "D0150E2", "D0150F2", "D0150G2", "D0150H2", "D0150I2",
]

# GG functional-goal codes that require clinical judgment — always mandatory.
GG_MANDATORY: list[str] = ["GG0100", "GG0110", "GG0130", "GG0170", "GG0170C"]

# Wound-care OASIS codes included only for wound-bearing archetypes.
WOUND_CODES: list[str] = [
    "M1300", "M1302", "M1306", "M1307",
    "M1310", "M1312", "M1313", "M1314",
    "M1320", "M1322", "M1324",
    "M1330", "M1332", "M1334",
    "M1340", "M1342", "M1350",
    "WOUND_CARE",
]

# Archetypes that always include wound-specific OASIS codes.
WOUND_ARCHETYPES: set[str] = {"diabetic_foot_ulcer", "sepsis_cellulitis_recovery"}

# All 130+ OASIS gap field codes evaluated in Phase 2 (filter).
# Sourced from the docread-consumer PROMPT master list.
ALL_GAP_FIELD_CODES: list[str] = [
    "A1250",
    "ACTIVITIES_PERMITTED",
    "ACUITY_LEVEL",
    "ADVANCE_DIRECTIVE",
    "ALLERGIES",
    "B0200",
    "B1000",
    "B1300",
    "C0100",
    "C0200",
    "C0300",
    "C0400",
    "C0500",
    "C1310",
    "CARDIOVASCULAR_PROBLEMS",
    "CIRCULATORY_HISTORY",
    "COMMUNITY_SCREENING",
    "CORRECTIVE_ACTION_PLAN",
    "D0160",
    "DIABETIC_FOOT",
    "DYSPNEA_HISTORY",
    "EARS",
    "ENDOCRINE_HEMATOLOGY",
    "ENTERAL_FEEDINGS",
    "ENVIRONMENTAL_RISKS",
    "EYES_VISION",
    "FIRE_EMERGENCY",
    "FUNCTIONAL_LIMITATIONS",
    "GAIT_EVALUATION",
    "GASTROINTESTINAL",
    "GENITALIA",
    "GENITOURINARY",
    "GG0100",
    "GG0110",
    "GG0130",
    "GG0170",
    "GG0170C",
    "GROOMING_TASKS",
    "HOMEBOUND_REASONS",
    "HOME_SAFETY_EVALUATION",
    "HOUSEHOLD_MEMBERS",
    "IMMUNIZATION",
    "INFECTION_CONTROL",
    "INFUSION_CARE",
    "INFUSION_THERAPY",
    "INSTRUCTIONS_PROVIDED",
    "J0510",
    "J0520",
    "J0530",
    "K0520",
    "LANGUAGE_INTERPRETER",
    "M0080",
    "M0090",
    "M0100",
    "M0102",
    "M0104",
    "M0110",
    "M1000",
    "M1005",
    "M1011",
    "M1017",
    "M1021",
    "M1023",
    "M1028",
    "M1033",
    "M1060",
    "M1100",
    "M1200",
    "M1210",
    "M1220",
    "M1230",
    "M1240",
    "M1242",
    "M1300",
    "M1302",
    "M1306",
    "M1307",
    "M1310",
    "M1312",
    "M1313",
    "M1314",
    "M1320",
    "M1322",
    "M1324",
    "M1330",
    "M1332",
    "M1334",
    "M1340",
    "M1342",
    "M1350",
    "M1400",
    "M1500",
    "M1501",
    "M1510",
    "M1511",
    "M1600",
    "M1610",
    "M1620",
    "M1630",
    "M1700",
    "M1710",
    "M1720",
    "M1740",
    "M1745",
    "M1800",
    "M1810",
    "M1820",
    "M1830",
    "M1840",
    "M1845",
    "M1850",
    "M1860",
    "M1870",
    "M1880",
    "M1890",
    "M1900",
    "M1910",
    "M2001",
    "M2003",
    "M2005",
    "M2010",
    "M2016",
    "M2020",
    "M2030",
    "M2040",
    "M2100",
    "M2102",
    "M2110",
    "MARITAL_STATUS",
    "MENTAL_STATUS",
    "MOUTH",
    "MUSCLE_ROM",
    "MUSCULOSKELETAL",
    "N0415",
    "NAILS",
    "NEURO_EMOTIONAL_PROBLEMS",
    "NOSE",
    "NUTRITIONAL_REQUIREMENTS",
    "NUTRITIONAL_STATUS",
    "O0110",
    "ORGANIZATIONS_ASSISTANCE",
    "OXYGEN_SAFETY",
    "PERTINENT_HISTORY",
    "PHQ_MOOD_INTERVIEW",
    "PROGNOSIS",
    "PSYCHOSOCIAL_PROBLEMS",
    "PT_INR",
    "PT_NUTRITIONAL_STATUS",
    "RESPIRATORY",
    "SAFETY_MEASURES",
    "SANITATION_HAZARDS",
    "SKIN",
    "SPECIAL_APPLIANCES",
    "STRUCTURAL_BARRIERS",
    "THROAT",
    "TIMINGS",
    "TRANSPORTATION_ASSISTANCE",
    "TUG_ASSESSMENT",
    "VITAL_SIGNS",
    "WOUND_CARE",
]

# Number of gap field codes sent to the LLM per Phase 3 batch request.
PHASE3_BATCH_SIZE: int = 50
