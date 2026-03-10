from app.services.artifact_writer import ArtifactWriter


def test_artifact_writer_creates_expected_files(tmp_path):
    writer = ArtifactWriter(str(tmp_path))
    patient_id = "PATIENT-TEST-001"
    metadata = {
        "patient_id": patient_id,
        "source": "PHASE_A",
        "archetype": "copd_with_fall_risk",
        "pdgm_group": "MMTA_RESPIRATORY",
        "admission_source": "hospital",
        "episode_timing": "early",
        "age_bracket": "75-84",
        "gender": "F",
        "comorbidity_count": 3,
        "has_ambient_scribe": True,
        "has_clinical_note": False,
        "f2f_status": "present_complete",
        "referral_format": "clean_emr",
        "validation_status": "pending",
        "generated_by": "claude-sonnet",
        "generated_date": "2026-03-09",
        "clinician_validated": False,
    }

    output_path = writer.write_step1_artifacts(patient_external_id=patient_id, metadata=metadata)

    assert (tmp_path / patient_id / "metadata.json").exists()
    assert (tmp_path / patient_id / "docs" / "placeholders" / "referral_summary.txt").exists()
    assert output_path.endswith(patient_id)
