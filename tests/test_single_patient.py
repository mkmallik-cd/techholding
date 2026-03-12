#!/usr/bin/env python3
"""
End-to-end test: generate one dummy patient and verify all pipeline steps.

Usage:  python3 tests/test_single_patient.py
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = "http://localhost:8081/api/v1/patient-generation"
PATIENT_ID = "SYN_0001"
MAX_WAIT = 900  # 15 minutes — allow for up to 3 repair cycles


def enqueue(patient_id: str) -> str:
    payload = json.dumps({
        "patient_external_id": patient_id,
        "model_id": "us.anthropic.claude-3-5-sonnet-20241022-v2:0",
    }).encode()
    req = urllib.request.Request(
        f"{BASE}/enqueue",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    resp = json.loads(urllib.request.urlopen(req).read())
    return resp["job_id"]


def poll(job_id: str) -> dict:
    deadline = time.time() + MAX_WAIT
    last_phase = None
    while time.time() < deadline:
        try:
            resp = json.loads(urllib.request.urlopen(f"{BASE}/{job_id}").read())
        except urllib.error.URLError as e:
            print(f"  [poll error] {e}")
            time.sleep(5)
            continue

        status = resp.get("status")
        phase = resp.get("phase")
        if phase != last_phase:
            elapsed = int(MAX_WAIT - (deadline - time.time()))
            repair_info = f"  repair={resp.get('repair_attempt', 0)}" if resp.get('repair_attempt') else ""
            print(f"  [{elapsed:>3}s]  phase={phase:<35}  status={status}{repair_info}")
            last_phase = phase

        if status in ("completed", "failed", "invalid", "invalid_permanent"):
            return resp
        time.sleep(5)

    raise TimeoutError(f"Job {job_id} did not complete within {MAX_WAIT}s")


def check_artifacts(patient_id: str) -> list[str]:
    folder = f"output/{patient_id}"
    if not os.path.isdir(folder):
        return []
    return sorted(os.listdir(folder))


def main() -> int:
    print("=" * 60)
    print(f"  E2E Test — generating {PATIENT_ID}")
    print("=" * 60)

    # Remove old output if it exists so we get a fresh run
    import shutil
    outdir = f"output/{PATIENT_ID}"
    if os.path.isdir(outdir):
        shutil.rmtree(outdir)
        print(f"  Removed existing output at {outdir}")

    # Step 0 — verify API is up
    try:
        health = json.loads(urllib.request.urlopen("http://localhost:8081/health").read())
        assert health.get("status") == "ok", f"Unexpected health: {health}"
        print("  ✅ API health check passed")
    except Exception as e:
        print(f"  ❌ API not reachable: {e}")
        return 1

    # Step 1 — enqueue
    print(f"\n  Enqueueing {PATIENT_ID}...")
    try:
        job_id = enqueue(PATIENT_ID)
        print(f"  ✅ Enqueued — job_id={job_id}")
    except Exception as e:
        print(f"  ❌ Enqueue failed: {e}")
        return 1

    # Step 2 — poll to completion
    print(f"\n  Polling for completion (up to {MAX_WAIT}s)...")
    try:
        result = poll(job_id)
    except TimeoutError as e:
        print(f"  ❌ {e}")
        return 1

    status = result.get("status")
    phase  = result.get("phase")
    error  = result.get("error_message")
    repair = result.get("repair_attempt", 0)

    print(f"\n  Final status     : {status}")
    print(f"  Final phase      : {phase}")
    print(f"  Repair attempts  : {repair}")
    if error:
        print(f"  Error            : {error[:200]}")

    if status == "failed":
        print("\n  ❌ PIPELINE FAILED")
        return 1

    if status == "invalid_permanent":
        print(f"  ⚠️  Permanently INVALID after {repair} repair attempt(s) — check validation_report.json")

    if status == "invalid":
        print("  ⚠️  Consistency validator found issues in generated data")

    # Step 3 — inspect output artifacts
    files = check_artifacts(PATIENT_ID)
    print(f"\n  Output folder: output/{PATIENT_ID}/")

    # Expected artifacts
    expected = {
        "metadata.json",
        "referral_packet.txt",
        "medication_list.json",
        "tap_tap_gap_answers.json",
        "oasis_gold_standard.json",
        "validation_report.json",
    }

    # Resolve docs/ sub-folder files too
    docs_folder = f"output/{PATIENT_ID}/docs"
    all_files: set[str] = set()
    for fn in files:
        all_files.add(fn)

    if os.path.isdir(docs_folder):
        for root, dirs, fns in os.walk(docs_folder):
            for fn in fns:
                rel = os.path.relpath(os.path.join(root, fn), f"output/{PATIENT_ID}")
                all_files.add(rel)

    print(f"\n  Files found:")
    for fn in sorted(all_files):
        tag = "✅" if fn in expected or any(fn.endswith(e.split(".")[-1]) for e in expected) else "  "
        print(f"    {tag} {fn}")

    # Check metadata content
    meta_path = f"output/{PATIENT_ID}/metadata.json"
    if os.path.exists(meta_path):
        meta = json.load(open(meta_path))
        print(f"\n  Metadata snapshot:")
        for k in ("archetype", "pdgm_group", "age_bracket", "gender",
                  "has_ambient_scribe", "f2f_status", "referral_format"):
            print(f"    {k:<22} = {meta.get(k)}")
    else:
        print("  ⚠️  metadata.json not found")

    # Quick content checks
    failures = []
    checks = [
        ("metadata.json",          lambda p: json.load(open(p)).get("archetype")),
        ("referral_packet.txt",    lambda p: len(open(p).read()) > 200),
        ("medication_list.json",   lambda p: "hospital_discharge_list" in json.load(open(p))),
        ("tap_tap_gap_answers.json",  lambda p: "unanswered_response" in json.load(open(p))),
        ("oasis_gold_standard.json",  lambda p: "items" in json.load(open(p))),
        ("validation_report.json",    lambda p: "status" in json.load(open(p))),
    ]

    # Ambient scribe is optional (depends on has_ambient_scribe flag)
    meta_data = json.load(open(meta_path)) if os.path.exists(meta_path) else {}
    if meta_data.get("has_ambient_scribe"):
        checks.append(("ambient_scribe.txt", lambda p: len(open(p).read()) > 200))

    print(f"\n  Content checks:")
    for filename, check_fn in checks:
        filepath = f"output/{PATIENT_ID}/{filename}"
        if not os.path.exists(filepath):
            print(f"    ❌ {filename} — FILE MISSING")
            failures.append(filename)
            continue
        try:
            ok = check_fn(filepath)
            if ok:
                print(f"    ✅ {filename}")
            else:
                print(f"    ❌ {filename} — content check failed")
                failures.append(filename)
        except Exception as e:
            print(f"    ❌ {filename} — error: {e}")
            failures.append(filename)

    print("\n" + "=" * 60)
    if failures:
        print(f"  ❌ TEST FAILED — {len(failures)} artifact(s) missing or invalid: {failures}")
        return 1
    else:
        print(f"  ✅ ALL CHECKS PASSED — {PATIENT_ID} generated successfully")
        return 0


if __name__ == "__main__":
    sys.exit(main())
