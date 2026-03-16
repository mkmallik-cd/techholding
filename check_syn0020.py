#!/usr/bin/env python3
"""Validation script for SYN_0020 gap answers and gold standard."""
import json, sys

PATIENT = "SYN_0020"
BASE = f"output/{PATIENT}"

gap = json.load(open(f"{BASE}/tap_tap_gap_answers.json"))
gold = json.load(open(f"{BASE}/oasis_gold_standard.json"))

PASS = 0
FAIL = 0

def check(label, condition, detail=""):
    global PASS, FAIL
    if condition:
        print(f"  PASS  {label}" + (f"  [{detail}]" if detail else ""))
        PASS += 1
    else:
        print(f"  FAIL  {label}" + (f"  [{detail}]" if detail else ""))
        FAIL += 1

# --- Collect all gap field_codes ---
gap_codes = {}
for section in gap.get("sections", []):
    for q in section.get("questions", []):
        for fc in q.get("field_codes", []):
            gap_codes[fc] = q.get("answer", "")

print(f"\n=== SYN_0020 VALIDATION  (gap codes: {len(gap_codes)}) ===\n")

# ---- 1. No underscore codes in gap ----
print("-- GAP: code hygiene --")
bad_underscore = [c for c in gap_codes if "_" in c]
check("No underscore codes in gap", not bad_underscore, str(bad_underscore) if bad_underscore else "")

bad_roots = [c for c in gap_codes if c in ("GG0100", "GG0110", "GG0130", "GG0170", "N0415")]
check("No bare root GG/N0415 codes in gap", not bad_roots, str(bad_roots) if bad_roots else "")

phq_bad = [c for c in gap_codes if "PHQ_MOOD" in c or "MOOD_INTERVIEW" in c]
check("No PHQ_MOOD_INTERVIEW in gap", not phq_bad, str(phq_bad) if phq_bad else "")

# ---- 2. GG sub-code presence in gap ----
print("\n-- GAP: GG sub-code presence --")
gg0100 = sorted([c for c in gap_codes if c.startswith("GG0100")])
gg0110 = sorted([c for c in gap_codes if c.startswith("GG0110")])
gg0130 = sorted([c for c in gap_codes if c.startswith("GG0130")])
gg0170 = sorted([c for c in gap_codes if c.startswith("GG0170")])
n0415  = sorted([c for c in gap_codes if c.startswith("N0415")])

check("GG0100 sub-codes present in gap", len(gg0100) >= 4, f"found: {gg0100}")
check("GG0110 sub-codes present in gap", len(gg0110) >= 6, f"found: {gg0110}")
check("GG0130 sub-codes present in gap", len(gg0130) >= 14, f"found ({len(gg0130)}): {gg0130}")
check("GG0170 sub-codes present in gap", len(gg0170) >= 20, f"found ({len(gg0170)}): {gg0170}")
check("N0415 sub-codes present in gap",  len(n0415)  >= 9,  f"found: {n0415}")

# ---- 3. Gold standard: GG sub-code presence ----
print("\n-- GOLD: GG sub-code presence --")
gg0130_gold = sorted([k for k in gold if k.startswith("GG0130")])
gg0170_gold = sorted([k for k in gold if k.startswith("GG0170")])
check("GG0130 sub-codes in gold", len(gg0130_gold) >= 14, f"found ({len(gg0130_gold)}): {gg0130_gold}")
check("GG0170 sub-codes in gold", len(gg0170_gold) >= 20, f"found ({len(gg0170_gold)}): {gg0170_gold}")

# ---- 4. B1300 and M2040 verbatim consistency (only if present in gap) ----
print("\n-- GOLD vs GAP: Verbatim fields (only when item is a gap item) --")
gap_b1300  = gap_codes.get("B1300")
gold_b1300 = gold.get("B1300")
if gap_b1300 is not None:
    check("B1300 verbatim: gap == gold", gap_b1300 == gold_b1300,
          f"gap={gap_b1300!r} gold={gold_b1300!r}")
else:
    print(f"  SKIP  B1300 not a gap item → gold independently assigns it (gold={gold_b1300!r})")

gap_m2040  = gap_codes.get("M2040")
gold_m2040 = gold.get("M2040")
if gap_m2040 is not None:
    check("M2040 verbatim: gap == gold", gap_m2040 == gold_m2040,
          f"gap={gap_m2040!r} gold={gold_m2040!r}")
else:
    print(f"  SKIP  M2040 not a gap item → gold independently assigns it (gold={gold_m2040!r})")

# ---- 5. GG gap vs gold value consistency (excluding skip-logic expected overrides) ----
print("\n-- GOLD vs GAP: GG sub-code value consistency --")
all_gg = sorted(set(gg0130 + gg0170))
# Skip-logic legitimately overrides these codes in gold: GG_STAIR_HIERARCHY sets O1/N1 to 88
# when M1='88'; GG_WALK_HIERARCHY sets J/K/L to 88 when I1 unable.
# RR1 has no gap-copy path (only LLM) so value disagreement is expected.
skip_logic_expected = {"GG0170N1", "GG0170O1"}  # stair hierarchy
gg_mismatches = []
for code in all_gg:
    gv  = gap_codes.get(code)
    gdv = gold.get(code)
    if gv != gdv:
        if code in skip_logic_expected:
            print(f"  SKIP  {code}: gap={gv!r} gold={gdv!r}  [skip-logic expected]")
        elif code == "GG0170RR1":
            print(f"  SKIP  {code}: gap={gv!r} gold={gdv!r}  [RR1 from LLM — value disagreement OK]")
        else:
            gg_mismatches.append(f"{code}: gap={gv!r} gold={gdv!r}")
check("All GG sub-codes (excluding skip-logic) match gap and gold", not gg_mismatches,
      str(gg_mismatches) if gg_mismatches else "")

# ---- 5b. GG0170H specifically present in gold ----
check("GG0170H1 present and non-null in gold", gold.get("GG0170H1") is not None,
      f"gold.GG0170H1={gold.get('GG0170H1')!r}")
check("GG0170H2 present and non-null in gold", gold.get("GG0170H2") is not None,
      f"gold.GG0170H2={gold.get('GG0170H2')!r}")

# ---- 6. BIMS arithmetic in gold ----
# OASIS-E1: C0200=word repetition (0-3, single score — no A/B/C sub-items)
#            C0300A/B/C + C0400A/B/C = orientation + recall sub-scores
#            C0500 = C0200 + C0300 + C0400  (0-15)
print("\n-- GOLD: BIMS arithmetic --")
try:
    c0100 = gold.get("C0100", "0")
    if str(c0100) == "0":  # BIMS was conducted
        needed = ["C0200", "C0300A", "C0300B", "C0300C", "C0400A", "C0400B", "C0400C", "C0500"]
        missing = [k for k in needed if gold.get(k) is None]
        if missing:
            check("BIMS sub-scores all present in gold", False, f"null keys: {missing}")
        else:
            c0300_sum = int(gold["C0300A"]) + int(gold["C0300B"]) + int(gold["C0300C"])
            c0400_sum = int(gold["C0400A"]) + int(gold["C0400B"]) + int(gold["C0400C"])
            expected_total = int(gold["C0200"]) + c0300_sum + c0400_sum
            actual_c0500 = int(gold["C0500"])
            check("BIMS C0500 = C0200+C0300+C0400", actual_c0500 == expected_total,
                  f"C0500={actual_c0500} expected={expected_total}")
    else:
        print(f"  SKIP  BIMS arithmetic (C0100={c0100!r} — not conducted)")
except Exception as e:
    print(f"  ERROR BIMS arithmetic: {e}")

# ---- 7. PHQ-2 gate ----
print("\n-- GOLD: PHQ-2 gate --")
try:
    a = int(gold.get("D0150A2", "0"))
    b = int(gold.get("D0150B2", "0"))
    screen = a + b
    if screen < 3:
        d0200a2 = gold.get("D0200A2")
        check("PHQ-2 gate: screen<3 → D0200A2 is dash/99/absent",
              d0200a2 in ["-", "99", None, ""],
              f"D0150A2={a} D0150B2={b} screen={screen} D0200A2={d0200a2!r}")
    else:
        print(f"  SKIP  PHQ-2 gate (screen={screen}>=3 → full PHQ-9 required)")
except Exception as e:
    print(f"  ERROR PHQ-2 gate: {e}")

# ---- 8. BIMS sub-score detail ----
print("\n-- GOLD: BIMS detail --")
bims_keys = ["C0100","C0200","C0300","C0300A","C0300B","C0300C","C0400","C0400A","C0400B","C0400C","C0500"]
for k in bims_keys:
    print(f"  {k} = {gold.get(k)!r}")

# ---- 9. GG0170 H / O / RR detail ----
print("\n-- GG0170 H / O / RR gap vs gold detail --")
for k in ["GG0170H1","GG0170H2","GG0170O1","GG0170O2","GG0170RR1"]:
    print(f"  {k}: gap={gap_codes.get(k)!r}  gold={gold.get(k)!r}")

# ---- 10. B1300 / M2040 context ----
print("\n-- B1300 / M2040 context (is it even a gap item?) --")
print(f"  B1300 in gap: {'B1300' in gap_codes}  gap={gap_codes.get('B1300')!r}  gold={gold.get('B1300')!r}")
print(f"  M2040 in gap: {'M2040' in gap_codes}  gap={gap_codes.get('M2040')!r}  gold={gold.get('M2040')!r}")
print("  NOTE: if not in gap, gold independently assigns them from source docs — no verbatim check needed")

# ---- Summary ----
total = PASS + FAIL
print(f"\n=== RESULT: {PASS}/{total} PASSED  |  {FAIL} FAILED ===\n")
sys.exit(0 if FAIL == 0 else 1)
