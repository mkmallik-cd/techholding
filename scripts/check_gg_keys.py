#!/usr/bin/env python3
"""Check full GG0170 grouped entry for a patient."""
import json, sys
patient = sys.argv[1] if len(sys.argv) > 1 else "PATIENT-0053"
gap = json.load(open(f"output/{patient}/tap_tap_gap_answers.json"))
u = gap["unanswered_response"]
gg0170 = u.get("GG0170")
print(f"GG0170 entry: {gg0170}")
gg0130 = u.get("GG0130")
print(f"GG0130 entry: {gg0130}")
