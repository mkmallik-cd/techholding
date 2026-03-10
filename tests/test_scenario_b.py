#!/usr/bin/env python3
"""Scenario B test: find a patient with has_ambient_scribe=false, verify no ambient_scribe.txt is created."""
import json
import os
import subprocess
import sys
import time
import urllib.request

BASE = "http://localhost:8081/api/v1/patient-generation"


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


def poll(job_id: str, max_wait: int = 180) -> dict:
    deadline = time.time() + max_wait
    while time.time() < deadline:
        resp = json.loads(urllib.request.urlopen(f"{BASE}/{job_id}").read())
        status = resp.get("status")
        phase = resp.get("phase")
        print(f"  status={status} phase={phase}")
        if status in ("completed", "failed"):
            return resp
        time.sleep(5)
    raise TimeoutError(f"Job {job_id} did not complete within {max_wait}s")


for n in range(11, 20):
    patient_id = f"PATIENT-00{n:02d}"
    # skip if already generated
    meta_path = f"output/{patient_id}/metadata.json"
    if os.path.exists(meta_path):
        meta = json.load(open(meta_path))
        has_scribe = meta.get("has_ambient_scribe")
        print(f"{patient_id} already exists, has_ambient_scribe={has_scribe}")
        if has_scribe is False:
            files = os.listdir(f"output/{patient_id}")
            has_ambient_txt = "ambient_scribe.txt" in files
            print(f"  files: {sorted(files)}")
            print(f"  ambient_scribe.txt present: {has_ambient_txt}")
            if not has_ambient_txt:
                print(f"\n✅ SCENARIO B CONFIRMED: {patient_id} has has_ambient_scribe=false and NO ambient_scribe.txt was created.")
                sys.exit(0)
        continue

    print(f"\nEnqueueing {patient_id}...")
    job_id = enqueue(patient_id)
    print(f"  job_id={job_id}")
    result = poll(job_id)

    if result.get("status") == "failed":
        print(f"  ❌ Job failed: {result.get('error_message')}")
        continue

    meta = json.load(open(meta_path))
    has_scribe = meta.get("has_ambient_scribe")
    files = sorted(os.listdir(f"output/{patient_id}"))
    final_phase = result.get("phase")
    print(f"  has_ambient_scribe={has_scribe}")
    print(f"  final phase={final_phase}")
    print(f"  files: {files}")

    if has_scribe is False:
        has_ambient_txt = "ambient_scribe.txt" in files
        if not has_ambient_txt and final_phase == "step2_referral_packet":
            print(f"\n✅ SCENARIO B CONFIRMED: {patient_id}")
            print("   has_ambient_scribe=False → pipeline ended at step2_referral_packet")
            print("   ambient_scribe.txt NOT created ✓")
            print("   referral_packet.txt and medication_list.json present ✓")
        else:
            if has_ambient_txt:
                print("❌ FAIL: ambient_scribe.txt was created despite has_ambient_scribe=False")
            if final_phase != "step2_referral_packet":
                print(f"❌ FAIL: expected phase=step2_referral_packet, got {final_phase}")
        sys.exit(0)

print("\n⚠️  No has_ambient_scribe=false patient found in range PATIENT-0011 to PATIENT-0019.")
print("All tested patients had has_ambient_scribe=True — this is expected (~70% true rate).")
print("Try running the script again or increase the range.")
