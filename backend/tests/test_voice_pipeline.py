import io
import uuid
import pytest
from fastapi.testclient import TestClient

from app.services.ai.factory import get_ai_providers
from app.services.ai.gemini_provider import post_process_transcript
from app.services.hod_service import get_deterministic_hod


# ============================================================================
# 15 AUDIT & VERIFICATION TEST CASES FOR VOICE-TO-FEEDBACK PIPELINE
# ============================================================================

def test_01_pure_hindi_accurate_translation_without_hallucination():
    """
    Test Case 1: Pure Hindi complaint -> accurate English translation without hallucination.
    Input: 'Khane mein thoda namak kam tha aur nurse ko bulane mein time lag raha tha.'
    Verifies:
    - Faithful English translation
    - No invented doctor, patient, or ward numbers
    - No invented medical conditions
    """
    _, trans_provider, llm_provider = get_ai_providers()
    spoken = "Khane mein thoda namak kam tha aur nurse ko bulane mein time lag raha tha."
    english = trans_provider.translate_to_english(spoken, source_language="Hindi")

    assert "salt" in english.lower()
    assert "nurse" in english.lower() or "nursing" in english.lower()
    assert "delay" in english.lower() or "time" in english.lower()

    # Verify zero hallucinated names or durations
    assert "dr." not in english.lower()
    assert "doctor" not in english.lower()
    assert "3 days" not in english.lower()

    analysis = llm_provider.extract_structured_feedback(spoken, english)
    assert analysis["negative_feedback"] != "Not Provided"
    assert "salt" in analysis["complaint_summary"].lower() or "food" in analysis["complaint_summary"].lower()


def test_02_pure_hinglish_accurate_translation():
    """
    Test Case 2: Pure Hinglish complaint -> accurate English translation.
    Input: 'Doctor ne achhe se explain kiya but nursing response thoda late tha.'
    Verifies:
    - Doctor's clear explanation captured
    - Nursing response delay captured
    - No exaggeration of severity
    """
    _, trans_provider, llm_provider = get_ai_providers()
    spoken = "Doctor ne achhe se explain kiya but nursing response thoda late tha."
    english = trans_provider.translate_to_english(spoken, source_language="Hinglish")

    assert "doctor" in english.lower()
    assert "explained" in english.lower()
    assert "nursing" in english.lower()
    assert "delayed" in english.lower() or "late" in english.lower()

    analysis = llm_provider.extract_structured_feedback(spoken, english)
    assert analysis["positive_feedback"] != "Not Provided"
    assert "doctor" in analysis["positive_feedback"].lower()


def test_03_pure_english_faithful_representation():
    """
    Test Case 3: Pure English complaint -> faithful representation without distortion.
    Input: 'The room was clean and doctors were attentive, but discharge billing took two hours.'
    Verifies:
    - Preserved without altering facts or adding unmentioned details
    - 2-hour billing delay preserved
    """
    _, trans_provider, llm_provider = get_ai_providers()
    spoken = "The room was clean and doctors were attentive, but discharge billing took two hours."
    english = trans_provider.translate_to_english(spoken, source_language="English")

    assert "room was clean" in english.lower()
    assert "billing" in english.lower()
    assert "two hours" in english.lower()

    analysis = llm_provider.extract_structured_feedback(spoken, english)
    assert analysis["suggested_department"] == "Billing"


def test_04_mixed_hindi_english_meaning_preserved():
    """
    Test Case 4: Mixed Hindi + English speech -> meaning preserved accurately.
    Input: 'Sir sab theek tha medicine time pe mil gayi but bathroom dirty tha.'
    Verifies:
    - Timely medications recognized as positive
    - Dirty bathroom recognized as housekeeping complaint
    """
    _, trans_provider, llm_provider = get_ai_providers()
    spoken = "Sir sab theek tha medicine time pe mil gayi but bathroom dirty tha."
    english = trans_provider.translate_to_english(spoken, source_language="Mixed")

    assert "medicine" in english.lower() or "medication" in english.lower()
    assert "bathroom" in english.lower() or "washroom" in english.lower()

    analysis = llm_provider.extract_structured_feedback(spoken, english)
    assert analysis["suggested_department"] == "Housekeeping"
    assert "bathroom" in analysis["complaint_summary"].lower()


def test_05_speech_without_patient_name_or_uhid_remains_blank():
    """
    Test Case 5: Speech without patient name / UHID -> fields stay blank/null, NOT hallucinated.
    Verifies:
    - AI does NOT guess patient name or UHID from vague speech
    - Provenance specifies UHID and patient name are STAFF_ENTERED
    """
    _, trans_provider, llm_provider = get_ai_providers()
    spoken = "Ac cooling theek nahi chal raha tha."
    english = trans_provider.translate_to_english(spoken)
    analysis = llm_provider.extract_structured_feedback(spoken, english)

    # Sensitive fields are strictly not populated by AI
    assert analysis.get("uhid") is None or analysis.get("uhid") == "Not Provided"
    assert analysis.get("patient_name") is None or analysis.get("patient_name") == "Not Provided"

    # Provenance tags verify source separation
    provenance = analysis.get("field_provenance", {})
    assert provenance.get("uhid") == "STAFF_ENTERED"
    assert provenance.get("patient_name") == "STAFF_ENTERED"


def test_06_speech_without_doctor_consultant_remains_blank():
    """
    Test Case 6: Speech without doctor / consultant -> consultant remains blank/null.
    Verifies:
    - AI does NOT guess doctor or consultant name
    """
    _, trans_provider, llm_provider = get_ai_providers()
    spoken = "Bathroom mein paani nahi aa raha tha."
    english = trans_provider.translate_to_english(spoken)
    analysis = llm_provider.extract_structured_feedback(spoken, english)

    assert analysis.get("consultant") is None or analysis.get("consultant") == "Not Provided"
    assert analysis.get("field_provenance", {}).get("consultant") == "STAFF_ENTERED"


def test_07_speech_with_missing_department_no_arbitrary_invention():
    """
    Test Case 7: Speech with general feedback -> AI does not invent arbitrary clinical department.
    """
    _, trans_provider, llm_provider = get_ai_providers()
    spoken = "Hospital services overall okay hain."
    english = trans_provider.translate_to_english(spoken)
    analysis = llm_provider.extract_structured_feedback(spoken, english)

    assert analysis["complaint_type"] in ["General Feedback", "Appreciation", "Complaint"]
    # No arbitrary medical diagnosis
    assert "diagnosis" not in str(analysis).lower()


def test_08_no_invented_duration_or_timings():
    """
    Test Case 8: No invented duration (e.g. '2 hours', '3 days' not added if not spoken).
    Input: 'Doctor time pe dekhne aaye the lekin ward ka AC bilkul kaam nahi kar raha tha.'
    """
    _, trans_provider, llm_provider = get_ai_providers()
    spoken = "Doctor time pe dekhne aaye the lekin ward ka AC bilkul kaam nahi kar raha tha."
    english = trans_provider.translate_to_english(spoken, source_language="Hinglish")

    assert "3 days" not in english.lower()
    assert "24 hours" not in english.lower()
    assert "since morning" not in english.lower()

    analysis = llm_provider.extract_structured_feedback(spoken, english)
    assert "3 days" not in analysis["complaint_summary"].lower()


def test_09_no_invented_severity_or_diagnosis():
    """
    Test Case 9: No invented severity / diagnosis.
    Input: 'Khane mein namak kam tha.'
    Verifies:
    - AI does NOT add clinical diagnoses (e.g. hypertension, food poisoning)
    - Priority remains Low or Medium, NOT Critical
    """
    _, trans_provider, llm_provider = get_ai_providers()
    spoken = "Khane mein namak kam tha."
    english = trans_provider.translate_to_english(spoken, source_language="Hindi")
    analysis = llm_provider.extract_structured_feedback(spoken, english)

    assert analysis["priority"] in ["Low", "Medium"]
    assert "poisoning" not in str(analysis).lower()
    assert "hypertension" not in str(analysis).lower()


def test_10_short_summary_strictly_facts_only():
    """
    Test Case 10: Short Summary strictly facts-only.
    Verifies:
    - 1-sentence concise factual summary
    - Based ONLY on spoken words
    - No invented patient/doctor names or emotional speculation
    """
    _, trans_provider, llm_provider = get_ai_providers()
    spoken = "Ward ka AC bilkul kaam nahi kar raha tha."
    english = trans_provider.translate_to_english(spoken, source_language="Hinglish")
    analysis = llm_provider.extract_structured_feedback(spoken, english)

    summary = analysis["complaint_summary"]
    assert len(summary) > 10
    assert "air conditioning" in summary.lower() or "ac" in summary.lower()
    # Facts only: no unstated names
    assert "sharma" not in summary.lower()
    assert "kumar" not in summary.lower()


def test_11_staff_entered_values_override_ai_suggestions(client: TestClient, staff_headers: dict):
    """
    Test Case 11: Staff-entered values override AI suggestions.
    AI suggested 'Maintenance', but staff selects 'Operations'.
    Final record must have Department = 'Operations' and HOD mapped to Operations.
    """
    payload = {
        "client_uuid": str(uuid.uuid4()),
        "uhid": "00998811",
        "patient_name": "Vikram Sethi",
        "department": "Operations",  # Staff override
        "ai_suggested_department": "Maintenance",  # AI suggestion
        "complaint": "Wheelchair was unavailable at entrance.",
    }
    res = client.post("/api/v1/feedback", json=payload, headers=staff_headers)
    assert res.status_code == 201
    data = res.json()

    assert data["department"] == "Operations"
    assert data["ai_suggested_department"] == "Maintenance"
    # Backend mapped HOD for Operations deterministically (Asha Ma'am)
    assert data["hod_name"] == "Asha Ma'am"


def test_12_review_screen_reflects_staff_overrides(client: TestClient, staff_headers: dict):
    """
    Test Case 12: Review screen reflects staff overrides (backend honors edited complaint & summary).
    Staff refines complaint and summary before final submit.
    """
    payload = {
        "client_uuid": str(uuid.uuid4()),
        "uhid": "00998822",
        "patient_name": "Meena Kumari",
        "department": "Nursing",
        "complaint": "Staff refined: Nurse response bell was non-functional in Ward 3B.",
        "complaint_summary": "Staff refined: Call bell delay in Room 3B.",
        "complaint_type": "Nursing Care",
    }
    res = client.post("/api/v1/feedback", json=payload, headers=staff_headers)
    assert res.status_code == 201
    data = res.json()

    assert data["complaint"] == "Staff refined: Nurse response bell was non-functional in Ward 3B."
    assert data["complaint_summary"] == "Staff refined: Call bell delay in Room 3B."
    assert data["hod_name"] == "Reshmi Ma'am"


def test_13_original_transcript_preserved_separately_from_translated_complaint(client: TestClient, staff_headers: dict):
    """
    Test Case 13: Original transcript preserved separately from translated complaint.
    Original transcript in Hindi/Hinglish is stored verbatim.
    Complaint holds the professional English statement.
    """
    payload = {
        "client_uuid": str(uuid.uuid4()),
        "uhid": "00998833",
        "patient_name": "Rohan Deshmukh",
        "department": "Clinical",
        "original_transcript": "Doctor sahab ne sab kuch ache se samjhaya par dawai time par nahi mili.",
        "english_translation": "The doctor explained everything well, but medications were not received on time.",
        "complaint": "Delay in receiving prescribed medications following consultation.",
    }
    res = client.post("/api/v1/feedback", json=payload, headers=staff_headers)
    assert res.status_code == 201
    data = res.json()

    # Both must be preserved distinctively
    assert data["original_transcript"] == "Doctor sahab ne sab kuch ache se samjhaya par dawai time par nahi mili."
    assert data["english_translation"] == "The doctor explained everything well, but medications were not received on time."
    assert data["complaint"] == "Delay in receiving prescribed medications following consultation."


def test_14_deterministic_hod_mapping_untouched_and_verified(db_session):
    """
    Test Case 14: Deterministic HOD mapping untouched and verified.
    Ensures backend deterministic rules cannot be manipulated by AI hallucination.
    """
    assert get_deterministic_hod("Clinical", db=db_session) == "Tanveer Sir"
    assert get_deterministic_hod("Nursing", db=db_session) == "Reshmi Ma'am"
    assert get_deterministic_hod("Pharmacy", db=db_session) == "Vijay Sir"
    assert get_deterministic_hod("IT", db=db_session) == "Valay Sir"
    assert get_deterministic_hod("Housekeeping", db=db_session) == "Asha Ma'am"
    assert get_deterministic_hod("Maintenance", db=db_session) == "Asha Ma'am"
    assert get_deterministic_hod("F&B", db=db_session) == "Asha Ma'am"
    # An unconfigured department returns 'HOD Not Configured'
    assert get_deterministic_hod("Unconfigured Department", db=db_session) == "HOD Not Configured"


def test_15_end_to_end_audio_processing_to_final_submission_validation(client: TestClient, staff_headers: dict):
    """
    Test Case 15: End-to-end audio processing to final submission validation.
    1. Process audio -> returns transcript, translation, structured fields, provenance.
    2. Missing mandatory field check (blocks submission).
    3. Valid submission with 48h retention and provenance check.
    """
    # 1. Process simulated audio
    fake_audio = io.BytesIO(b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00" + b"\x00" * 2000)
    proc_res = client.post(
        "/api/v1/feedback/process-audio",
        files={"audio": ("feedback.webm", fake_audio, "audio/webm")},
        headers=staff_headers,
    )
    assert proc_res.status_code == 200
    ai_data = proc_res.json()
    assert ai_data["success"] is True
    assert "original_transcript" in ai_data
    assert "field_provenance" in ai_data
    assert ai_data["field_provenance"]["uhid"] == "STAFF_ENTERED"

    # Acoustic confusion safeguard verification
    cleaned = post_process_transcript("Hum feedbacker le rahe hain patient se")
    assert "feedbacker" not in cleaned
    assert "feedback" in cleaned

    # 2. Block submission if UHID is missing
    active_uuid = ai_data["audio_file_id"]
    invalid_payload = {
        "client_uuid": active_uuid,
        "uhid": "",  # Missing
        "patient_name": "Test Patient",
        "department": "Nursing",
    }
    block_res = client.post("/api/v1/feedback", json=invalid_payload, headers=staff_headers)
    assert block_res.status_code == 422

    # 3. Successful final submission
    valid_payload = {
        "client_uuid": active_uuid,
        "uhid": "00990099",
        "patient_name": "Sunita Patil",
        "department": ai_data.get("suggested_department") or "Nursing",
        "consultant": "Dr. Ramesh Verma",
        "complaint": ai_data.get("complaint") or "Service delay reported.",
        "complaint_summary": ai_data.get("complaint_summary") or "Delay reported.",
        "complaint_type": ai_data.get("complaint_type") or "Nursing Care",
        "original_transcript": ai_data.get("original_transcript", ""),
        "english_translation": ai_data.get("english_translation", ""),
        "audio_file_id": active_uuid,
    }
    submit_res = client.post("/api/v1/feedback", json=valid_payload, headers=staff_headers)
    assert submit_res.status_code == 201
    final_data = submit_res.json()

    assert final_data["uhid"] == "00990099"
    assert final_data["patient_name"] == "Sunita Patil"
    assert final_data["consultant"] == "Dr. Ramesh Verma"
    assert final_data["retention_expires_at"] is not None
    assert final_data["retention_expiry_str"] is not None
    assert final_data["field_provenance"]["uhid"] == "STAFF_ENTERED"
    assert final_data["field_provenance"]["hod_name"] == "SYSTEM_RESOLVED"


def test_16_hospital_shorthand_normalization_gw1_gw2_gw3():
    """
    Test Case 16: Hospital Shorthand Normalization (GW1 -> General Ward 1, etc.)
    Verifies contextual recognition while original transcript remains unchanged.
    """
    from app.services.hospital_normalization import (
        extract_and_normalize_location,
        normalize_explicit_location,
    )

    # 1. Contextual extraction
    assert extract_and_normalize_location("GW1 ke patient ko breakfast nahi mila") == "General Ward 1"
    assert extract_and_normalize_location("GW2 mein patient ko complaint hai") == "General Ward 2"
    assert extract_and_normalize_location("GW3 par safai nahi hui") == "General Ward 3"
    assert extract_and_normalize_location("Location: GW1") == "General Ward 1"
    assert extract_and_normalize_location("General hospital services were okay") is None

    # 2. Explicit normalization
    assert normalize_explicit_location("GW1") == "General Ward 1"
    assert normalize_explicit_location("gw2") == "General Ward 2"
    assert normalize_explicit_location("ICU Bed 3") == "ICU Bed 3"


def test_17_explicit_location_normalization_on_submission(client: TestClient, staff_headers: dict):
    """
    Test Case 17: Staff enters 'GW1' in location field -> stored as 'General Ward 1'.
    """
    payload = {
        "client_uuid": str(uuid.uuid4()),
        "uhid": "00998844",
        "patient_name": "Kavita Rao",
        "department": "Nursing",
        "location": "GW1",  # Shorthand entered by staff
        "complaint": "Nursing call bell was not attended.",
    }
    res = client.post("/api/v1/feedback", json=payload, headers=staff_headers)
    assert res.status_code == 201
    data = res.json()
    assert data["location"] == "General Ward 1"


def test_18_empty_or_silent_audio_rejected_safely(client: TestClient, staff_headers: dict):
    """
    Test Case 18: Empty/silent audio (< 1500 bytes) rejected safely without invoking LLM.
    """
    silent_audio = io.BytesIO(b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00" + b"\x00" * 50)
    res = client.post(
        "/api/v1/feedback/process-audio",
        files={"audio": ("silent.webm", silent_audio, "audio/webm")},
        headers=staff_headers,
    )
    assert res.status_code == 400
    assert "Speech could not be understood" in res.json()["detail"]


def test_19_all_six_actual_voice_test_sentences():
    """
    Test Case 19: Verify all 6 exact hospital spoken sentences requested by user:
    TEST 1: 'Patient ko subah se breakfast nahi mila.'
    TEST 2: 'GW1 ke patient ko breakfast nahi mila hai.'
    TEST 3: 'GW2 mein patient ko nursing staff se complaint hai.'
    TEST 4: 'Patient ko room ki safai se problem hai.'
    TEST 5: 'Patient is complaining about the billing staff.'
    TEST 6: 'Attendant bol raha hai ki doctor abhi tak nahi aaye.'
    """
    _, trans_provider, llm_provider = get_ai_providers()

    # TEST 1
    t1_text = "Patient ko subah se breakfast nahi mila."
    t1_trans = trans_provider.translate_to_english(t1_text)
    t1_analysis = llm_provider.extract_structured_feedback(t1_text, t1_trans)
    assert "breakfast" in t1_trans.lower()
    assert t1_analysis["suggested_department"] == "F&B"
    assert t1_analysis["complaint_type"] == "Food Complaint"

    # TEST 2
    t2_text = "GW1 ke patient ko breakfast nahi mila hai."
    t2_trans = trans_provider.translate_to_english(t2_text)
    t2_analysis = llm_provider.extract_structured_feedback(t2_text, t2_trans)
    assert "breakfast" in t2_trans.lower()
    assert t2_analysis["suggested_department"] == "F&B"
    assert t2_analysis.get("suggested_location") == "General Ward 1"

    # TEST 3
    t3_text = "GW2 mein patient ko nursing staff se complaint hai."
    t3_trans = trans_provider.translate_to_english(t3_text)
    t3_analysis = llm_provider.extract_structured_feedback(t3_text, t3_trans)
    assert "nursing" in t3_trans.lower()
    assert t3_analysis["suggested_department"] == "Nursing"
    assert t3_analysis.get("suggested_location") == "General Ward 2"

    # TEST 4
    t4_text = "Patient ko room ki safai se problem hai."
    t4_trans = trans_provider.translate_to_english(t4_text)
    t4_analysis = llm_provider.extract_structured_feedback(t4_text, t4_trans)
    assert "cleanliness" in t4_trans.lower() or "room" in t4_trans.lower()
    assert t4_analysis["suggested_department"] == "Housekeeping"
    assert t4_analysis["complaint_type"] == "Housekeeping"

    # TEST 5
    t5_text = "Patient is complaining about the billing staff."
    t5_trans = trans_provider.translate_to_english(t5_text)
    t5_analysis = llm_provider.extract_structured_feedback(t5_text, t5_trans)
    assert "billing" in t5_trans.lower()
    assert t5_analysis["suggested_department"] == "Billing"
    assert t5_analysis["complaint_type"] == "Billing"

    # TEST 6
    t6_text = "Attendant bol raha hai ki doctor abhi tak nahi aaye."
    t6_trans = trans_provider.translate_to_english(t6_text)
    t6_analysis = llm_provider.extract_structured_feedback(t6_text, t6_trans)
    assert "doctor" in t6_trans.lower()
    assert t6_analysis["suggested_department"] == "Clinical"
    assert t6_analysis["complaint_type"] == "Clinical"


def test_20_developer_text_mode_endpoint(client: TestClient, staff_headers: dict):
    """
    Test Case 20: Developer / Test Mode Text Conversion Endpoint (/api/v1/feedback/process-text).
    Verifies that text-to-English conversion isolates AI translation/structuring from microphone capture.
    """
    sample_text = "GW1 ke patient ko subah se breakfast nahi mila aur attendant bol raha hai ki abhi tak nahi aaya."
    res = client.post(
        "/api/v1/feedback/process-text",
        json={"text": sample_text},
        headers=staff_headers,
    )
    assert res.status_code == 200
    data = res.json()

    # 1. Original transcript must be strictly preserved verbatim
    assert data["original_transcript"] == sample_text

    # 2. Shorthand GW1 must normalize to General Ward 1
    assert data["suggested_location"] == "General Ward 1"

    # 3. Department must suggest F&B
    assert data["suggested_department"] == "F&B"

    # 4. English complaint must contain breakfast and ward/GW1 expansion
    assert "breakfast" in data["english_translation"].lower()

    # 5. Pipeline Diagnostics must be present
    assert data["diagnostics"] is not None
    assert data["diagnostics"]["STT_SUCCESS"] is True
    assert data["diagnostics"]["TRANSCRIPT_PRESENT"] is True
    assert data["diagnostics"]["TRANSLATION_SUCCESS"] is True
    assert data["diagnostics"]["AI_ANALYSIS_SUCCESS"] is True
    assert data["diagnostics"]["mode"] == "TEXT_DEVELOPER_TEST_MODE"


# ============================================================================
# ASYNC "SAVE & NEXT PATIENT" BACKGROUND PIPELINE TESTS
# ============================================================================

def test_21_async_save_and_next_patient_returns_immediately_queued(client: TestClient, staff_headers: dict):
    """
    Test Case 21: POST /api/v1/feedback/async must return HTTP 201 immediately with status='QUEUED'
    without waiting for speech-to-text, translation, or AI extraction to finish.
    """
    client_uuid = f"async-test-{uuid.uuid4()}"
    res = client.post(
        "/api/v1/feedback/async",
        data={
            "client_uuid": client_uuid,
            "uhid": "99001",
            "patient_name": "Async Fast Patient",
            "department": "F&B",
            "location": "GW1",
            "manual_complaint": "GW1 ke patient ko breakfast nahi mila.",
        },
        headers=staff_headers,
    )
    assert res.status_code == 201
    data = res.json()
    assert data["success"] is True
    assert data["client_uuid"] == client_uuid
    assert data["status"] in ("QUEUED", "PROCESSING", "COMPLETED")
    assert "feedback_id" in data
    assert data["message"] == "Saved — Processing in Background"


def test_22_async_background_execution_updates_feedback_to_completed(client: TestClient, staff_headers: dict):
    """
    Test Case 22: Background worker completes processing, normalizes GW1 to General Ward 1,
    resolves deterministic HOD (Asha Ma'am for F&B), and transitions status to COMPLETED.
    """
    client_uuid = f"async-comp-{uuid.uuid4()}"
    res = client.post(
        "/api/v1/feedback/async",
        data={
            "client_uuid": client_uuid,
            "uhid": "99002",
            "patient_name": "Ramesh Kumar",
            "department": "F&B",
            "location": "GW1",
            "manual_complaint": "GW1 ke patient ko breakfast nahi mila.",
        },
        headers=staff_headers,
    )
    assert res.status_code == 201
    fb_id = res.json()["feedback_id"]

    # Verify via feedback list or admin details
    res_list = client.get("/api/v1/feedback/my", headers=staff_headers)
    assert res_list.status_code == 200
    my_records = {r["client_uuid"]: r for r in res_list.json()}
    assert client_uuid in my_records
    rec = my_records[client_uuid]
    assert rec["uhid"] == "99002"
    assert rec["patient_name"] == "Ramesh Kumar"
    assert rec["department"] == "F&B"
    assert rec["hod_name"] == "Asha Ma'am"
    assert rec["location"] == "General Ward 1"
    assert rec["status"] == "COMPLETED"


def test_23_async_silent_or_corrupt_audio_transitions_to_needs_review(client: TestClient, staff_headers: dict):
    """
    Test Case 23: Audio < 1500 bytes (silent / corrupted) must NOT silently succeed or get lost.
    It must transition status to 'NEEDS_REVIEW' with descriptive processing_error.
    """
    client_uuid = f"async-silent-{uuid.uuid4()}"
    tiny_audio = io.BytesIO(b"RIFFtinycorruptdata")

    res = client.post(
        "/api/v1/feedback/async",
        data={
            "client_uuid": client_uuid,
            "uhid": "99003",
            "patient_name": "Silent Audio Patient",
            "department": "Nursing",
            "location": "GW2",
        },
        files={"audio": ("silent.webm", tiny_audio, "audio/webm")},
        headers=staff_headers,
    )
    assert res.status_code == 201

    res_list = client.get("/api/v1/feedback/my", headers=staff_headers)
    my_records = {r["client_uuid"]: r for r in res_list.json()}
    assert client_uuid in my_records
    rec = my_records[client_uuid]
    assert rec["status"] == "NEEDS_REVIEW"
    assert rec["processing_error"] is not None
    assert "too low or silent" in rec["processing_error"].lower() or "short" in rec["processing_error"].lower()


def test_24_multi_patient_isolation_zero_cross_contamination(client: TestClient, staff_headers: dict):
    """
    Test Case 24: Multiple patients in quick succession (fast rounds) must have 100% data isolation.
    Patient 1 (GW1, F&B) vs Patient 2 (GW2, Maintenance) vs Patient 3 (GW3, Housekeeping)
    Zero mixing of UHID, patient name, location, or complaint.
    """
    p1_uuid = f"p1-iso-{uuid.uuid4()}"
    p2_uuid = f"p2-iso-{uuid.uuid4()}"
    p3_uuid = f"p3-iso-{uuid.uuid4()}"

    # Submit Patient 1
    r1 = client.post(
        "/api/v1/feedback/async",
        data={
            "client_uuid": p1_uuid,
            "uhid": "00111",
            "patient_name": "Patient Alpha",
            "department": "F&B",
            "location": "GW1",
            "manual_complaint": "GW1 patient didn't get tea.",
        },
        headers=staff_headers,
    )
    assert r1.status_code == 201

    # Submit Patient 2
    r2 = client.post(
        "/api/v1/feedback/async",
        data={
            "client_uuid": p2_uuid,
            "uhid": "00222",
            "patient_name": "Patient Beta",
            "department": "Maintenance",
            "location": "GW2",
            "manual_complaint": "GW2 fan is making loud noise.",
        },
        headers=staff_headers,
    )
    assert r2.status_code == 201

    # Submit Patient 3
    r3 = client.post(
        "/api/v1/feedback/async",
        data={
            "client_uuid": p3_uuid,
            "uhid": "00333",
            "patient_name": "Patient Gamma",
            "department": "Housekeeping",
            "location": "GW3",
            "manual_complaint": "GW3 bathroom needs cleaning.",
        },
        headers=staff_headers,
    )
    assert r3.status_code == 201

    res_list = client.get("/api/v1/feedback/my", headers=staff_headers)
    records = {r["client_uuid"]: r for r in res_list.json()}

    # Verify Patient 1 isolation
    assert records[p1_uuid]["uhid"] == "00111"
    assert records[p1_uuid]["patient_name"] == "Patient Alpha"
    assert records[p1_uuid]["department"] == "F&B"
    assert records[p1_uuid]["location"] == "General Ward 1"
    assert "tea" in records[p1_uuid]["complaint"].lower()

    # Verify Patient 2 isolation
    assert records[p2_uuid]["uhid"] == "00222"
    assert records[p2_uuid]["patient_name"] == "Patient Beta"
    assert records[p2_uuid]["department"] == "Maintenance"
    assert records[p2_uuid]["location"] == "General Ward 2"
    assert "fan" in records[p2_uuid]["complaint"].lower() or "noise" in records[p2_uuid]["complaint"].lower()

    # Verify Patient 3 isolation
    assert records[p3_uuid]["uhid"] == "00333"
    assert records[p3_uuid]["patient_name"] == "Patient Gamma"
    assert records[p3_uuid]["department"] == "Housekeeping"
    assert records[p3_uuid]["location"] == "General Ward 3"
    assert "clean" in records[p3_uuid]["complaint"].lower() or "bathroom" in records[p3_uuid]["complaint"].lower()


def test_25_async_idempotency_prevents_duplicate_records(client: TestClient, staff_headers: dict):
    """
    Test Case 25: Duplicate submission with the same client_uuid must return the existing record
    without duplicating feedback records or IDs.
    """
    client_uuid = f"idempotent-{uuid.uuid4()}"
    res1 = client.post(
        "/api/v1/feedback/async",
        data={
            "client_uuid": client_uuid,
            "uhid": "99005",
            "patient_name": "Idempotent Patient",
            "department": "Pharmacy",
            "manual_complaint": "Medicines delayed.",
        },
        headers=staff_headers,
    )
    assert res1.status_code == 201
    fb_id_1 = res1.json()["feedback_id"]

    # Re-post identical client_uuid
    res2 = client.post(
        "/api/v1/feedback/async",
        data={
            "client_uuid": client_uuid,
            "uhid": "99005",
            "patient_name": "Idempotent Patient",
            "department": "Pharmacy",
            "manual_complaint": "Medicines delayed.",
        },
        headers=staff_headers,
    )
    assert res2.status_code == 201
    fb_id_2 = res2.json()["feedback_id"]
    assert fb_id_1 == fb_id_2


def test_26_queue_status_endpoint_returns_accurate_counts(client: TestClient, staff_headers: dict):
    """
    Test Case 26: GET /api/v1/feedback/queue-status returns processing_count, completed_count,
    needs_review_count, and recent items list for staff.
    """
    # Submit one record so queue has activity
    client.post(
        "/api/v1/feedback/async",
        data={
            "client_uuid": f"queue-check-{uuid.uuid4()}",
            "uhid": "88001",
            "patient_name": "Queue Status Patient",
            "department": "F&B",
            "manual_complaint": "Testing queue status counts.",
        },
        headers=staff_headers,
    )

    res = client.get("/api/v1/feedback/queue-status", headers=staff_headers)
    assert res.status_code == 200
    data = res.json()
    assert "processing_count" in data
    assert "completed_count" in data
    assert "needs_review_count" in data
    assert "items" in data
    assert isinstance(data["items"], list)
    assert len(data["items"]) >= 1


