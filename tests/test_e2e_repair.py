"""End-to-end repair smoke test using real PATIENT-E2E-001 artifacts."""
import json
import importlib.util
import sys
import types

BASE_PATH = '/Users/dhrimilmendapara/Documents/project/copper-digital/patient-dataset-generation'
sys.path.insert(0, BASE_PATH)

from app.services.repair.algorithmic_fixes import fix_gap_answers, fix_gold_standard

# Load GG constants directly from constants.py without triggering app.config.__init__
_constants_spec = importlib.util.spec_from_file_location(
    "app.config.constants",
    f"{BASE_PATH}/app/config/constants.py",
)
_constants_mod = importlib.util.module_from_spec(_constants_spec)
sys.modules["app.config.constants"] = _constants_mod
_constants_spec.loader.exec_module(_constants_mod)

# Now import ConsistencyValidator directly
_cv_spec = importlib.util.spec_from_file_location(
    "app.services.generators.consistency_validator",
    f"{BASE_PATH}/app/services/generators/consistency_validator.py",
)
_cv_mod = importlib.util.module_from_spec(_cv_spec)
sys.modules["app.services.generators.consistency_validator"] = _cv_mod
_cv_spec.loader.exec_module(_cv_mod)
ConsistencyValidator = _cv_mod.ConsistencyValidator

BASE = '/Users/dhrimilmendapara/Documents/project/copper-digital/patient-dataset-generation/output/PATIENT-E2E-001'

ga = json.load(open(f'{BASE}/tap_tap_gap_answers.json'))
gs = json.load(open(f'{BASE}/oasis_gold_standard.json'))
vr = json.load(open(f'{BASE}/validation_report.json'))

errors = vr['errors']
print(f'Loaded {len(errors)} validation errors: checks = {set(e["check"] for e in errors)}')

# Fix gap_answers in-place
_, ga_fixes = fix_gap_answers(ga)
print(f'gap_answers: {len(ga_fixes)} fix(es) applied')

# Fix gold_standard in-place
_, gs_fixes = fix_gold_standard(gs, errors)
print(f'gold_standard: {len(gs_fixes)} fix(es) applied')

# Re-run validator on the repaired data
validator = ConsistencyValidator()
result = validator.validate(gap_answers=ga, gold_standard=gs, metadata={})
print(f'Post-repair validation: valid={result.is_valid}, errors={len(result.errors)}')
if result.errors:
    for e in result.errors:
        print(f'  REMAINING: {e["check"]} {e["code"]} actual={e["actual"]}')
    sys.exit(1)
else:
    print('ALL ERRORS RESOLVED — repair logic verified on real data!')


BASE = '/Users/dhrimilmendapara/Documents/project/copper-digital/patient-dataset-generation/output/PATIENT-E2E-001'

ga = json.load(open(f'{BASE}/tap_tap_gap_answers.json'))
gs = json.load(open(f'{BASE}/oasis_gold_standard.json'))
vr = json.load(open(f'{BASE}/validation_report.json'))

errors = vr['errors']
print(f'Loaded {len(errors)} validation errors: checks = {set(e["check"] for e in errors)}')

# Fix gap_answers in-place
_, ga_fixes = fix_gap_answers(ga)
print(f'gap_answers: {len(ga_fixes)} fix(es) applied')

# Fix gold_standard in-place
_, gs_fixes = fix_gold_standard(gs, errors)
print(f'gold_standard: {len(gs_fixes)} fix(es) applied')

# Re-run validator on the repaired data
validator = ConsistencyValidator()
result = validator.validate(gap_answers=ga, gold_standard=gs, metadata={})
print(f'Post-repair validation: valid={result.is_valid}, errors={len(result.errors)}')
if result.errors:
    for e in result.errors:
        print(f'  REMAINING: {e["check"]} {e["code"]} actual={e["actual"]}')
    sys.exit(1)
else:
    print('ALL ERRORS RESOLVED — repair logic verified on real data!')
