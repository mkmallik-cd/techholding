"""Quick smoke test for the repair algorithmic_fixes module."""
import sys
sys.path.insert(0, '/Users/dhrimilmendapara/Documents/project/copper-digital/patient-dataset-generation')

from app.services.repair.algorithmic_fixes import fix_gap_answers, fix_gold_standard

# Test fix_gap_answers with PHQ-2 gate scenario (screen=2 < 3)
ga = {
    'unanswered_response': {
        'D0150A1': {'question': 'A1', 'answer': '1'},
        'D0150A2': {'question': 'A2', 'answer': '2'},
        'D0150B1': {'question': 'B1', 'answer': '1'},
        'D0150B2': {'question': 'B2', 'answer': '1'},
        'D0150C1': {'question': 'C1', 'answer': '1'},
        'D0150C2': {'question': 'C2', 'answer': '2'},
        'D0150D1': {'question': 'D1', 'answer': '1'},
        'D0150D2': {'question': 'D2', 'answer': '2'},
        'D0150I1': {'question': 'I1', 'answer': '0'},
        'D0150I2': {'question': 'I2', 'answer': '0'},
        'D0160': {'question': 'total', 'answer': '10'},
    },
    'status': 'draft'
}

fixed, fixes = fix_gap_answers(ga)
ur = fixed['unanswered_response']
assert ur['D0150C1']['answer'] is None, f"Expected None, got {ur['D0150C1']['answer']}"
assert ur['D0150D1']['answer'] is None, f"Expected None, got {ur['D0150D1']['answer']}"
assert ur['D0160']['answer'] == '3', f"Expected '3', got {ur['D0160']['answer']}"  # A2=2+B2=1
print("gap_answers PHQ-2 gate fix: OK")
print(f"  C1={ur['D0150C1']['answer']} D1={ur['D0150D1']['answer']} D0160={ur['D0160']['answer']}")
print(f"  fixes: {fixes}")

# Test fix_gold_standard with phq2_gate errors
errors = [
    {'check': 'phq2_gate', 'code': 'D0150C1', 'expected': 'null', 'actual': '1'},
    {'check': 'phq2_gate', 'code': 'D0150C2', 'expected': 'null', 'actual': '2'},
    {'check': 'phq2_gate', 'code': 'D0150D1', 'expected': 'null', 'actual': '1'},
    {'check': 'phq2_gate', 'code': 'D0150D2', 'expected': 'null', 'actual': '2'},
]
gs = {
    'items': [
        {'item_code': 'D0150A1', 'value': '1', 'rationale': '', 'confidence': 'high'},
        {'item_code': 'D0150A2', 'value': '2', 'rationale': '', 'confidence': 'high'},
        {'item_code': 'D0150B1', 'value': '1', 'rationale': '', 'confidence': 'high'},
        {'item_code': 'D0150B2', 'value': '1', 'rationale': '', 'confidence': 'high'},
        {'item_code': 'D0150C1', 'value': '1', 'rationale': '', 'confidence': 'high'},
        {'item_code': 'D0150C2', 'value': '2', 'rationale': '', 'confidence': 'high'},
        {'item_code': 'D0150D1', 'value': '1', 'rationale': '', 'confidence': 'high'},
        {'item_code': 'D0150D2', 'value': '2', 'rationale': '', 'confidence': 'high'},
        {'item_code': 'D0160', 'value': '10', 'rationale': '', 'confidence': 'high'},
    ]
}
fixed_gs, fixes_gs = fix_gold_standard(gs, errors)
item_map = {e['item_code']: e['value'] for e in fixed_gs['items']}
assert item_map['D0150C1'] is None, f"Expected None, got {item_map['D0150C1']}"
assert item_map['D0150C2'] is None, f"Expected None, got {item_map['D0150C2']}"
# D0160 should be A2+B2=3 (C-D are nulled, so not counted)
assert item_map['D0160'] == '3', f"Expected '3', got {item_map['D0160']}"
print("gold_standard PHQ-2 gate fix: OK")
print(f"  C1={item_map['D0150C1']} C2={item_map['D0150C2']} D0160={item_map['D0160']}")
print(f"  fixes: {fixes_gs}")

# Test BIMS arithmetic
errors_bims = [
    {'check': 'bims_arithmetic', 'code': 'C0500', 'expected': '10', 'actual': '15'},
]
gs_bims = {
    'items': [
        {'item_code': 'C0200', 'value': '3', 'rationale': '', 'confidence': 'high'},
        {'item_code': 'C0300A', 'value': '3', 'rationale': '', 'confidence': 'high'},
        {'item_code': 'C0300B', 'value': '2', 'rationale': '', 'confidence': 'high'},
        {'item_code': 'C0300C', 'value': '1', 'rationale': '', 'confidence': 'high'},
        {'item_code': 'C0400A', 'value': '0', 'rationale': '', 'confidence': 'high'},
        {'item_code': 'C0400B', 'value': '1', 'rationale': '', 'confidence': 'high'},
        {'item_code': 'C0400C', 'value': '0', 'rationale': '', 'confidence': 'high'},
        {'item_code': 'C0500', 'value': '15', 'rationale': '', 'confidence': 'high'},
    ]
}
fixed_bims, fixes_bims = fix_gold_standard(gs_bims, errors_bims)
bims_map = {e['item_code']: e['value'] for e in fixed_bims['items']}
assert bims_map['C0500'] == '10', f"Expected '10', got {bims_map['C0500']}"
print("gold_standard BIMS arithmetic fix: OK")
print(f"  C0500={bims_map['C0500']} (was 15, should be 3+3+2+1+0+1+0=10)")

print("\nAll repair logic smoke tests PASSED")
