#!/usr/bin/env python3
"""Compare GG/ADL values between Step 4 and Step 6 for a given patient.

A "real mismatch" is when Step 4 HAS a value but the gold standard has a
different value.  Cases where Step 4 has no value (absent) and gold has a
value (LLM fallback) are acceptable and reported as INFO only.
"""
import json
import sys

# GG mapping constants imported from the shared config — no local copies needed
from app.config.constants import GG0130_LABEL_TO_LETTER, GG0170_KEY_TO_LETTER

patient = sys.argv[1] if len(sys.argv) > 1 else "PATIENT-0051"

gap = json.load(open(f"output/{patient}/tap_tap_gap_answers.json"))
gold = json.load(open(f"output/{patient}/oasis_gold_standard.json"))
unanswered = gap["unanswered_response"]
item_map = {i["item_code"]: i for i in gold["items"]}

real_mismatches = 0
no_step4_data = 0

# ---- GG0130 ---------------------------------------------------------------
print(f"\n=== GG0130 Self-Care comparison ({patient}) ===")
gg0130 = unanswered.get("GG0130", {}).get("answer", {})
if gg0130:
    seen_letters: set = set()
    for label, letter_or_letters in GG0130_LABEL_TO_LETTER.items():
        val = gg0130.get(label)
        if val is None:
            continue
        letters = letter_or_letters if isinstance(letter_or_letters, list) else [letter_or_letters]
        for letter in letters:
            if letter in seen_letters:
                continue
            seen_letters.add(letter)
            code1 = f"GG0130{letter}1"
            code2 = f"GG0130{letter}2"
            gold_v1 = item_map.get(code1, {}).get("value", "MISSING")
            gold_v2 = item_map.get(code2, {}).get("value", "MISSING")
            disp = label if not isinstance(letter_or_letters, list) else f"{label}->{letter}"
            if str(val) == str(gold_v1):
                print(f"  [OK]      {disp:30s}  step4={val}  {code1}={gold_v1}  {code2}={gold_v2}")
            else:
                real_mismatches += 1
                print(f"  [MISMATCH]{disp:30s}  step4={val}  {code1}={gold_v1}  {code2}={gold_v2}")
else:
    print("  [INFO] No GG0130 data in Step 4 for this patient -- LLM values used")

# ---- GG0170 ---------------------------------------------------------------
print(f"\n=== GG0170 Mobility comparison ({patient}) ===")
gg0170 = unanswered.get("GG0170", {}).get("answer", {})
if gg0170:
    seen_letters = set()
    for key, val in gg0170.items():
        letter = GG0170_KEY_TO_LETTER.get(key)
        if letter is None:
            print(f"  [WARN] unknown GG0170 key {key!r}")
            continue
        if letter in seen_letters:
            continue
        seen_letters.add(letter)
        code1 = f"GG0170{letter}1"
        code2 = f"GG0170{letter}2"
        gold_v1 = item_map.get(code1, {}).get("value", "MISSING")
        gold_v2 = item_map.get(code2, {}).get("value", "MISSING")
        if str(val) == str(gold_v1):
            print(f"  [OK]      GG0170{letter} ({key:20s})  step4={val}  {code1}={gold_v1}  {code2}={gold_v2}")
        else:
            real_mismatches += 1
            print(f"  [MISMATCH]GG0170{letter} ({key:20s})  step4={val}  {code1}={gold_v1}  {code2}={gold_v2}")
else:
    print("  [INFO] No GG0170 data in Step 4 for this patient -- LLM values used")

# ---- ADL M-codes ----------------------------------------------------------
print(f"\n=== ADL M-codes comparison ({patient}) ===")
for code in ["M1800","M1810","M1820","M1830","M1840","M1845",
             "M1850","M1860","M1870","M1880","M1890","M1900","M1910"]:
    step4_entry = unanswered.get(code)
    gold_item = item_map.get(code)
    step4_val = step4_entry.get("answer") if step4_entry else None
    gold_val = gold_item.get("value") if gold_item else "MISSING"
    gold_src = gold_item.get("source") if gold_item else "MISSING"
    if step4_val is None:
        no_step4_data += 1
        print(f"  [INFO]    {code}  step4=absent  gold={gold_val!r} ({gold_src})")
    elif str(step4_val) == str(gold_val):
        print(f"  [OK]      {code}  step4={step4_val!r}  gold={gold_val!r} ({gold_src})")
    else:
        real_mismatches += 1
        print(f"  [MISMATCH]{code}  step4={step4_val!r}  gold={gold_val!r} ({gold_src})")

summary = "ALL CONSISTENT" if real_mismatches == 0 else f"{real_mismatches} REAL MISMATCHES"
print(f"\n{summary}  ({no_step4_data} codes absent from Step 4 -- LLM fallback used)")
sys.exit(0 if real_mismatches == 0 else 1)
