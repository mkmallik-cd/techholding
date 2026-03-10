#!/usr/bin/env python3
"""Diagnose M-ADL and GG0130 entries in gap_answers vs gold standard."""
import json, sys

patient = sys.argv[1] if len(sys.argv) > 1 else "PATIENT-0052"
gap  = json.load(open(f"output/{patient}/tap_tap_gap_answers.json"))
gold = json.load(open(f"output/{patient}/oasis_gold_standard.json"))
u = gap["unanswered_response"]
item_map = {i["item_code"]: i for i in gold["items"]}

print(f"\n=== M-ADL detail ({patient}) ===")
for code in ["M1800","M1810","M1820","M1830","M1840","M1845","M1850","M1860","M1870"]:
    gap_entry = u.get(code)
    gold_item = item_map.get(code)
    gap_answer = gap_entry.get("answer") if gap_entry else "NOT_IN_GAP"
    gold_val = gold_item.get("value") if gold_item else "NOT_IN_GOLD"
    gold_src = gold_item.get("source") if gold_item else "NOT_IN_GOLD"
    print(f"  {code}: gap_answer={gap_answer!r:10} gold_val={gold_val!r:10} gold_src={gold_src!r}")

print(f"\n=== GG0130 detail ({patient}) ===")
gg0130_entry = u.get("GG0130")
print(f"  GG0130 grouped entry: {gg0130_entry}")
for code in ["GG0130A1","GG0130B1","GG0130C1","GG0130D1","GG0130E1","GG0130F1"]:
    gold_item = item_map.get(code)
    gold_val = gold_item.get("value") if gold_item else "NOT_IN_GOLD"
    gold_src = gold_item.get("source") if gold_item else "NOT_IN_GOLD"
    print(f"  {code}: gold_val={gold_val!r:6} gold_src={gold_src!r}")
