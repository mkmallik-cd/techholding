#!/usr/bin/env python3
"""
Step 6 end-to-end validation: oasis_gold_standard.json

Enqueues a fresh patient, waits for the full 6-step pipeline to complete, then
validates the generated oasis_gold_standard.json against the following checks:

    ✅ A1  items array has ≥150 entries
    ✅ A2  BIMS items (C0500) have source="gap_answers"
    ✅ A3  PHQ items (D0160) have source="gap_answers"
    ✅ A4  C0500 value matches tap_tap_gap_answers.json
    ✅ A5  D0160 value matches tap_tap_gap_answers.json
    ✅ A6  validation.bims_verified = true
    ✅ A7  validation.phq_verified  = true  (or score 0-27)
    ✅ A8  validation.hip_valid = true AND hip_score in [5, 30]  (if applicable)
    ✅ A9  validation.skip_logic_applied is a list (may be empty)
    ✅ A10 generated_at is present (ISO 8601)
    ✅ A11 source_documents list contains "tap_tap_gap_answers.json"
    ✅ A12 all LLM-sourced items have item_code, value, rationale, confidence fields
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error

BASE = "http://localhost:8081/api/v1/patient-generation"

# Use a high patient ID to avoid colliding with existing output
PATIENT_ID = "PATIENT-0050"
# Full pipeline: Step1 (~30s) + Step2 (~70s) + Step3 (~50s) + Step4 (~130s) + Step6 (~200s) = ~8 min
MAX_WAIT_SECONDS = 600


# ── helpers ──────────────────────────────────────────────────────────────────

def enqueue(patient_id: str) -> str:
    data = json.dumps({
        "patient_external_id": patient_id,
        "model_id": "us.anthropic.claude-3-5-sonnet-20241022-v2:0",
    }).encode()
    req = urllib.request.Request(
        f"{BASE}/enqueue",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    resp = json.loads(urllib.request.urlopen(req).read())
    return resp["job_id"]


def poll(job_id: str, max_wait: int = MAX_WAIT_SECONDS) -> dict:
    deadline = time.time() + max_wait
    last_phase = None
    while time.time() < deadline:
        resp = json.loads(urllib.request.urlopen(f"{BASE}/{job_id}").read())
        status = resp.get("status")
        phase = resp.get("phase")
        if phase != last_phase:
            elapsed = max_wait - (deadline - time.time())
            print(f"  [{int(elapsed):3d}s] status={status}  phase={phase}")
            last_phase = phase
        if status in ("completed", "failed"):
            return resp
        time.sleep(6)
    raise TimeoutError(f"Job {job_id} did not complete within {max_wait}s")


def check(condition: bool, name: str, detail: str = "") -> bool:
    if condition:
        print(f"  ✅ {name}")
    else:
        print(f"  ❌ {name}" + (f": {detail}" if detail else ""))
    return condition


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    output_dir = f"output/{PATIENT_ID}"

    # Skip enqueue if the gold standard already exists (for re-run)
    gold_path = f"{output_dir}/oasis_gold_standard.json"
    if os.path.exists(gold_path):
        print(f"\n{PATIENT_ID} output already exists — skipping enqueue, validating existing files.")
    else:
        # Clean slate: remove output dir if it exists but is incomplete
        if os.path.exists(output_dir):
            print(f"\n{PATIENT_ID} output dir exists but no oasis_gold_standard.json — removing and re-enqueueing.")
            import shutil
            shutil.rmtree(output_dir)

        print(f"\nEnqueueing {PATIENT_ID} ...")
        try:
            job_id = enqueue(PATIENT_ID)
        except urllib.error.URLError as exc:
            print(f"❌ Cannot reach API at {BASE}: {exc}")
            print("   Make sure the stack is running: docker compose up -d")
            return 1
        print(f"  job_id={job_id}")

        print(f"\nPolling (max {MAX_WAIT_SECONDS}s) — pipeline: Step1 → Step2 → Step3 → Step4 → Step6 ...")
        result = poll(job_id)

        final_status = result.get("status")
        final_phase  = result.get("phase")
        print(f"\n  Final: status={final_status}  phase={final_phase}")

        if final_status == "failed":
            print(f"\n❌ Pipeline FAILED: {result.get('error_message', '(no message)')}")
            return 1

        if final_phase != "step5_oasis_gold_standard":
            print(f"\n❌ Wrong final phase: expected step5_oasis_gold_standard, got {final_phase}")
            return 1

    # ── Load artifacts ────────────────────────────────────────────────────────
    if not os.path.exists(gold_path):
        print(f"\n❌ oasis_gold_standard.json not found at {gold_path}")
        return 1

    gold = json.load(open(gold_path))
    items: list[dict] = gold.get("items", [])
    validation: dict  = gold.get("validation", {})

    # Load tap_tap_gap_answers for cross-check
    gap_path = f"{output_dir}/tap_tap_gap_answers.json"
    gap = json.load(open(gap_path)) if os.path.exists(gap_path) else {}
    unanswered = gap.get("unanswered_response", {})

    item_map = {i["item_code"]: i for i in items}

    # ── Run assertions ────────────────────────────────────────────────────────
    print(f"\n─── Validating {PATIENT_ID}/oasis_gold_standard.json ───")

    passes: list[bool] = []

    # A1: items count
    passes.append(check(len(items) >= 150, "A1 items count ≥ 150", f"got {len(items)}"))

    # A2: C0500 source = gap_answers
    c0500_item = item_map.get("C0500")
    passes.append(check(
        c0500_item is not None and c0500_item.get("source") == "gap_answers",
        "A2 C0500 source='gap_answers'",
        f"got {c0500_item}",
    ))

    # A3: D0160 source = gap_answers
    d0160_item = item_map.get("D0160")
    passes.append(check(
        d0160_item is not None and d0160_item.get("source") == "gap_answers",
        "A3 D0160 source='gap_answers'",
        f"got {d0160_item}",
    ))

    # A4: C0500 value matches gap_answers
    gap_c0500 = str(unanswered.get("C0500", {}).get("answer", "")).strip()
    gold_c0500 = str(c0500_item.get("value", "")).strip() if c0500_item else ""
    passes.append(check(
        gap_c0500 == gold_c0500 and gap_c0500 != "",
        f"A4 C0500 value matches gap_answers ({gap_c0500})",
        f"gold={gold_c0500!r} gap={gap_c0500!r}",
    ))

    # A5: D0160 value matches gap_answers
    gap_d0160 = str(unanswered.get("D0160", {}).get("answer", "")).strip()
    gold_d0160 = str(d0160_item.get("value", "")).strip() if d0160_item else ""
    passes.append(check(
        gap_d0160 == gold_d0160 and gap_d0160 != "",
        f"A5 D0160 value matches gap_answers ({gap_d0160})",
        f"gold={gold_d0160!r} gap={gap_d0160!r}",
    ))

    # A6: bims_verified
    passes.append(check(
        validation.get("bims_verified") is True,
        f"A6 validation.bims_verified=true (bims_score={validation.get('bims_score')})",
    ))

    # A7: phq_score in valid range 0-27
    phq_score = validation.get("phq_score")
    passes.append(check(
        phq_score is not None and 0 <= phq_score <= 27,
        f"A7 phq_score in [0,27] (phq_score={phq_score}, phq_verified={validation.get('phq_verified')})",
    ))

    # A8: hip_valid=true and hip_score in [5,30]  (skip if hip returned None — not applicable)
    hip_score = validation.get("hip_score")
    hip_valid = validation.get("hip_valid")
    if hip_score is None:
        passes.append(check(True, "A8 hip_score=None (GG0130A1–E1 not applicable for this patient — acceptable)"))
    else:
        passes.append(check(
            hip_valid is True and 5 <= hip_score <= 30,
            f"A8 hip_valid=true AND hip_score in [5,30] (got hip_score={hip_score}, hip_valid={hip_valid})",
        ))

    # A9: skip_logic_applied is a list
    sla = validation.get("skip_logic_applied")
    passes.append(check(
        isinstance(sla, list),
        f"A9 skip_logic_applied is list (got {type(sla).__name__}: {sla})",
    ))
    if isinstance(sla, list) and len(sla) > 0:
        print(f"     rules applied: {sla}")

    # A10: generated_at present
    passes.append(check(
        bool(gold.get("generated_at")),
        f"A10 generated_at present ({gold.get('generated_at', 'MISSING')})",
    ))

    # A11: source_documents contains tap_tap_gap_answers.json
    src_docs = gold.get("source_documents", [])
    passes.append(check(
        "tap_tap_gap_answers.json" in src_docs,
        f"A11 source_documents includes tap_tap_gap_answers.json (got {src_docs})",
    ))

    # A12: all LLM-sourced items have required fields
    llm_items = [i for i in items if i.get("source") == "llm"]
    required_fields = {"item_code", "value", "rationale", "confidence"}
    bad_items = [i["item_code"] for i in llm_items if not required_fields.issubset(i.keys())]
    passes.append(check(
        len(bad_items) == 0,
        f"A12 all {len(llm_items)} LLM items have required fields",
        f"missing fields in: {bad_items[:5]}",
    ))

    # ── Summary ───────────────────────────────────────────────────────────────
    total  = len(passes)
    passed = sum(passes)
    failed = total - passed

    print(f"\n{'─' * 50}")
    print(f"  {PATIENT_ID}  —  {passed}/{total} checks passed")

    # Extra stats
    print(f"\n  📊 Stats:")
    print(f"     Total items            : {len(items)}")
    print(f"     LLM-sourced items      : {len(llm_items)}")
    ga_items = [i for i in items if i.get("source") == "gap_answers"]
    det_items = [i for i in items if i.get("source") == "deterministic"]
    print(f"     gap_answers items      : {len(ga_items)}")
    print(f"     deterministic items    : {len(det_items)}")
    print(f"     BIMS score (C0500)     : {validation.get('bims_score')}")
    print(f"     PHQ score  (D0160)     : {validation.get('phq_score')}")
    print(f"     HIP score  (GG0130)    : {validation.get('hip_score')} (valid={validation.get('hip_valid')})")
    print(f"     Skip logic rules       : {sla}")
    print(f"     source_documents       : {src_docs}")
    print()

    if failed == 0:
        print("  🎉 ALL CHECKS PASSED — Step 6 implementation validated!\n")
        return 0
    else:
        print(f"  ⚠️  {failed} check(s) FAILED — review output above\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
