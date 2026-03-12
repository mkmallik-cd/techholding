"""
Standalone script to run Step 8 LLM audit for an existing patient.

Usage:
    python scripts/run_llm_audit_standalone.py [PATIENT_ID]

Example:
    python scripts/run_llm_audit_standalone.py SYN_0001

All 5 source documents must already exist in output/<PATIENT_ID>/.
The script writes llm_audit_report.json to the same directory.
"""

import json
import os
import sys
from pathlib import Path

# ── Bootstrap: add project root to path and load .env ────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load .env before importing app code so settings picks up env vars.
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from app.config.settings import get_settings
from app.services.generators.llm_audit_generator import LlmAuditGenerator


def main() -> None:
    patient_id = sys.argv[1] if len(sys.argv) > 1 else "SYN_0001"
    settings = get_settings()
    output_dir = Path(settings.output_base_dir) / patient_id

    # When running locally the output dir is relative to project root.
    if not output_dir.exists():
        output_dir = PROJECT_ROOT / "output" / patient_id

    if not output_dir.exists():
        print(f"ERROR: output directory not found: {output_dir}")
        sys.exit(1)

    print(f"Running LLM audit for {patient_id}")
    print(f"Output dir : {output_dir}")
    print(f"Audit model: {settings.llm_audit_model_id}")
    print()

    # ── Load artifacts ────────────────────────────────────────────────────────
    referral_text = (output_dir / "referral_packet.txt").read_text(encoding="utf-8")
    print("Loaded referral_packet.txt")

    ambient_scribe_path = output_dir / "ambient_scribe.txt"
    ambient_scribe_text = (
        ambient_scribe_path.read_text(encoding="utf-8")
        if ambient_scribe_path.exists()
        else ""
    )
    print(f"Loaded ambient_scribe.txt  : {'yes' if ambient_scribe_text else 'not present'}")

    medication_list = json.loads((output_dir / "medication_list.json").read_text(encoding="utf-8"))
    print("Loaded medication_list.json")

    gap_answers = json.loads((output_dir / "tap_tap_gap_answers.json").read_text(encoding="utf-8"))
    print("Loaded tap_tap_gap_answers.json")

    gold_standard = json.loads((output_dir / "oasis_gold_standard.json").read_text(encoding="utf-8"))
    field_count = len([k for k in gold_standard if not k.startswith("_")])
    print(f"Loaded oasis_gold_standard.json ({field_count} fields)")
    print()

    # ── Run audit ─────────────────────────────────────────────────────────────
    generator = LlmAuditGenerator()
    audit_report = generator.generate(
        referral_text=referral_text,
        ambient_scribe_text=ambient_scribe_text,
        medication_list=medication_list,
        gap_answers=gap_answers,
        gold_standard=gold_standard,
    )

    # ── Write output ──────────────────────────────────────────────────────────
    _SYNTHETIC_LABEL = "SYNTHETIC — NOT REAL PATIENT DATA"
    report_with_label = {"_synthetic_label": _SYNTHETIC_LABEL, **audit_report}
    out_path = output_dir / "llm_audit_report.json"
    out_path.write_text(json.dumps(report_with_label, indent=2), encoding="utf-8")

    print(f"audit_status         : {audit_report['audit_status']}")
    print(f"fields_audited       : {audit_report['fields_audited']}")
    print(f"fields_consistent    : {audit_report['fields_consistent']}")
    print(f"fields_with_conflicts: {audit_report['fields_with_conflicts']}")
    print()
    print(f"Report written to: {out_path}")


if __name__ == "__main__":
    main()
