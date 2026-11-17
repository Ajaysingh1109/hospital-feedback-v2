import io
import uuid
import openpyxl
from fastapi.testclient import TestClient

TEST_MASTER_USERNAME = "test_master@local"
TEST_MASTER_PASSWORD = "TestMasterPassword!123"


def test_section_63_end_to_end_acceptance_workflow(client: TestClient):
    """
    Complete Section 63 End-to-End Acceptance Test:
    Master Login -> Master creates Staff Account -> Staff Login ->
    Process Audio (STT, Translation, AI Extraction) -> Mandatory Validation ->
    Deterministic HOD Mapping -> Final Submission -> Master Login -> Master Search & Filter ->
    Excel Export with Preserved Data.
    """
    # 0. Master logs in and creates staff account
    master_login_init = client.post(
        "/api/v1/auth/login",
        json={"username": TEST_MASTER_USERNAME, "password": TEST_MASTER_PASSWORD},
    )
    assert master_login_init.status_code == 200
    master_token = master_login_init.json()["access_token"]
    master_headers = {"Authorization": f"Bearer {master_token}"}

    create_staff_res = client.post(
        "/api/v1/admin/users",
        headers=master_headers,
        json={
            "username": "e2e_staff",
            "password": "E2EStaffPassword@2026",
            "display_name": "Priya Sharma (Staff Nurse)",
            "role": "STAFF",
        },
    )
    assert create_staff_res.status_code == 201

    # 1. Staff logs in
    login_res = client.post(
        "/api/v1/auth/login",
        json={"username": "e2e_staff", "password": "E2EStaffPassword@2026"},
    )
    assert login_res.status_code == 200
    staff_token = login_res.json()["access_token"]
    staff_headers = {"Authorization": f"Bearer {staff_token}"}

    # 2. Staff starts new feedback session, records conversation
    # We simulate sending audio bytes to /api/v1/feedback/process-audio
    mock_audio_bytes = b"RIFF____WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x80>\x00\x00\x00}\x00\x00\x02\x00\x10\x00data" + (b"\x00\x80" * 3000)
    session_uuid = str(uuid.uuid4())

    files = {"audio": ("recording.webm", io.BytesIO(mock_audio_bytes), "audio/webm")}
    data = {"client_uuid": session_uuid}

    process_res = client.post(
        "/api/v1/feedback/process-audio",
        files=files,
        data=data,
        headers=staff_headers,
    )
    assert process_res.status_code == 200
    proc_data = process_res.json()
    assert proc_data["success"] is True
    assert proc_data["original_transcript"] != ""
    assert proc_data["english_translation"] != ""
    assert proc_data["suggested_department"] is not None

    # 3. Validation: Verify that submitting without UHID or Patient Name is blocked
    incomplete_payload = {
        "client_uuid": session_uuid,
        "uhid": "",
        "patient_name": "",
        "department": "Nursing",
    }
    blocked_res = client.post("/api/v1/feedback", json=incomplete_payload, headers=staff_headers)
    assert blocked_res.status_code == 422

    # 4. Staff enters patient details (UHID with leading zeros) & reviews
    test_uhid = "000456789"
    patient_name = "Sunita Patil"
    selected_department = "Nursing"

    complete_payload = {
        "client_uuid": session_uuid,
        "uhid": test_uhid,
        "patient_name": patient_name,
        "department": selected_department,
        "location": "Ward 3, Bed 8",
        "consultant": "Dr. Ananya Ray",
        "scheme": "CGHS",
        "attendant_name": "Deepak Patil (Son)",
        "complaint_type": proc_data["complaint_type"],
        "complaint_summary": proc_data["complaint_summary"],
        "detailed_feedback": proc_data["detailed_feedback"],
        "positive_feedback": proc_data["positive_feedback"],
        "negative_feedback": proc_data["negative_feedback"],
        "specific_complaint": proc_data["specific_complaint"],
        "suggested_action": proc_data["suggested_action"],
        "priority": proc_data["priority"],
        "original_language": proc_data["original_language"],
        "original_transcript": proc_data["original_transcript"],
        "english_translation": proc_data["english_translation"],
        "duration_seconds": proc_data["duration_seconds"],
        "audio_file_id": proc_data["audio_file_id"],
        "ai_suggested_department": proc_data["suggested_department"],
    }

    # 5. Staff submits feedback
    submit_res = client.post("/api/v1/feedback", json=complete_payload, headers=staff_headers)
    assert submit_res.status_code == 201
    feedback_record = submit_res.json()
    feedback_id = feedback_record["feedback_id"]

    # 6. Verify deterministic HOD mapping was applied on backend:
    # Department = Nursing -> HOD MUST be Reshmi Ma'am
    assert feedback_record["hod_name"] == "Reshmi Ma'am"
    assert feedback_record["uhid"] == test_uhid

    # 7. Master Admin logs in
    admin_login_res = client.post(
        "/api/v1/auth/login",
        json={"username": TEST_MASTER_USERNAME, "password": TEST_MASTER_PASSWORD},
    )
    assert admin_login_res.status_code == 200
    admin_token = admin_login_res.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # 8. Admin sees record in dashboard
    admin_list_res = client.get(
        f"/api/v1/admin/feedback?search={test_uhid}",
        headers=admin_headers,
    )
    assert admin_list_res.status_code == 200
    items = admin_list_res.json()["items"]
    assert len(items) == 1
    assert items[0]["feedback_id"] == feedback_id
    assert items[0]["patient_name"] == patient_name
    assert items[0]["hod_name"] == "Reshmi Ma'am"

    # 9. Admin filters record by Department and HOD
    filter_res = client.get(
        "/api/v1/admin/feedback?department=Nursing&hod=Reshmi%20Ma'am",
        headers=admin_headers,
    )
    assert filter_res.status_code == 200
    assert any(it["feedback_id"] == feedback_id for it in filter_res.json()["items"])

    # 10. Admin exports Excel
    excel_res = client.get("/api/v1/admin/export-excel", headers=admin_headers)
    assert excel_res.status_code == 200
    assert "spreadsheetml" in excel_res.headers["content-type"]

    # 11. Verify Excel contents
    wb = openpyxl.load_workbook(io.BytesIO(excel_res.content))
    ws = wb.active
    header = [c.value for c in ws[1]]
    uhid_idx = header.index("UHID") + 1
    hod_idx = header.index("HOD") + 1

    matched_row = None
    for r in range(2, ws.max_row + 1):
        if str(ws.cell(row=r, column=uhid_idx).value) == test_uhid:
            matched_row = r
            break

    assert matched_row is not None, f"UHID {test_uhid} not found in Excel export"
    # Ensure HOD is Reshmi Ma'am
    assert ws.cell(row=matched_row, column=hod_idx).value == "Reshmi Ma'am"
    # Ensure UHID preserved leading zero
    uhid_val = str(ws.cell(row=matched_row, column=uhid_idx).value)
    assert uhid_val == "000456789"


def test_cloud_mobile_offline_and_laptop_independence_workflow(client: TestClient):
    """
    Simulates Section 13 Acceptance Flow:
    1. Mobile Staff logs in with independent staff credentials.
    2. Patient speaks Hindi/Hinglish bedside ("Doctor time pe dekhne aaye the lekin ward ka AC bilkul kaam nahi kar raha tha.").
    3. AI produces professional English Complaint.
    4. Free-text consultant ("Dr. Rajesh Kumar") manually entered by staff.
    5. Department = Maintenance -> HOD deterministically mapped to Asha Ma'am.
    6. Central record created with UUID.
    7. Offline sync retry simulation: same client_uuid sent again -> returns 200/201 without duplicate!
    8. Later, Laptop Master logs in, views central record, downloads 11-column Excel.
    9. Verifies exact 11 columns, no technical metadata, no original transcript, complaint contains ONLY English complaint.
    """
    # 1. Master creates mobile staff user
    m_login = client.post("/api/v1/auth/login", json={"username": TEST_MASTER_USERNAME, "password": TEST_MASTER_PASSWORD})
    assert m_login.status_code == 200
    m_headers = {"Authorization": f"Bearer {m_login.json()['access_token']}"}

    client.post(
        "/api/v1/admin/users",
        headers=m_headers,
        json={
            "username": "mobile_nurse_kavita",
            "password": "KavitaPass@2026",
            "display_name": "Kavita Nair (Ward Executive)",
            "role": "STAFF",
        },
    )

    # 2. Staff logs in on mobile device
    s_login = client.post("/api/v1/auth/login", json={"username": "mobile_nurse_kavita", "password": "KavitaPass@2026"})
    assert s_login.status_code == 200
    s_token = s_login.json()["access_token"]
    s_headers = {"Authorization": f"Bearer {s_token}"}

    # 3. Patient conversation audio processed
    session_uuid = str(uuid.uuid4())
    mock_audio = b"RIFF____WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x80>\x00\x00\x00}\x00\x00\x02\x00\x10\x00data" + (b"\x00\x7f" * 3000)
    proc_res = client.post(
        "/api/v1/feedback/process-audio",
        files={"audio": ("recording.webm", io.BytesIO(mock_audio), "audio/webm")},
        data={"client_uuid": session_uuid},
        headers=s_headers,
    )
    assert proc_res.status_code == 200
    ai_out = proc_res.json()

    # 4. Mobile staff submits feedback with free-text consultant
    test_uhid = "000889911"
    mobile_submission = {
        "client_uuid": session_uuid,
        "uhid": test_uhid,
        "patient_name": "Ramesh Chandra",
        "department": "Maintenance",
        "location": "Room 402, Bed A",
        "consultant": "Dr. Rajesh Kumar",  # FREE TEXT
        "scheme": "Ayushman Bharat (PM-JAY)",
        "complaint": "The doctor attended the patient on time, but the air conditioning in the ward was not functioning.",
        "complaint_type": "Maintenance",
        "original_transcript": "Doctor time pe dekhne aaye the lekin ward ka AC bilkul kaam nahi kar raha tha.",
        "english_translation": "The doctor attended the patient on time, but the air conditioning in the ward was not functioning.",
        "duration_seconds": ai_out.get("duration_seconds", 3.0),
        "audio_file_id": ai_out.get("audio_file_id"),
    }

    sub_res = client.post("/api/v1/feedback", json=mobile_submission, headers=s_headers)
    assert sub_res.status_code == 201
    created_record = sub_res.json()
    assert created_record["hod_name"] == "Asha Ma'am"
    assert created_record["consultant"] == "Dr. Rajesh Kumar"
    assert created_record["complaint"] == "The doctor attended the patient on time, but the air conditioning in the ward was not functioning."
    fb_id = created_record["feedback_id"]

    # 5. Idempotency test (Offline auto-sync retry with same client_uuid creates NO duplicate)
    retry_res = client.post("/api/v1/feedback", json=mobile_submission, headers=s_headers)
    assert retry_res.status_code in (200, 201)
    assert retry_res.json()["feedback_id"] == fb_id

    # 6. Laptop Master opens admin later and exports Excel
    m_admin_login = client.post("/api/v1/auth/login", json={"username": TEST_MASTER_USERNAME, "password": TEST_MASTER_PASSWORD})
    m_admin_headers = {"Authorization": f"Bearer {m_admin_login.json()['access_token']}"}

    excel_res = client.get("/api/v1/admin/export-excel", headers=m_admin_headers)
    assert excel_res.status_code == 200

    wb = openpyxl.load_workbook(io.BytesIO(excel_res.content))
    ws = wb.active

    # Check EXACT 11 headers
    headers = [cell.value for cell in ws[1]]
    expected_11 = [
        "Date", "Time", "UHID", "Patient Name", "Location", "Consultant",
        "Scheme", "Department", "HOD", "Complaint Type", "Complaint"
    ]
    assert headers == expected_11, f"Expected {expected_11}, got {headers}"
    assert len(headers) == 11

    # Verify data row
    uhid_col = headers.index("UHID") + 1
    consultant_col = headers.index("Consultant") + 1
    hod_col = headers.index("HOD") + 1
    complaint_col = headers.index("Complaint") + 1

    target_row = None
    for r in range(2, ws.max_row + 1):
        if str(ws.cell(row=r, column=uhid_col).value) == test_uhid:
            target_row = r
            break

    assert target_row is not None
    assert ws.cell(row=target_row, column=consultant_col).value == "Dr. Rajesh Kumar"
    assert ws.cell(row=target_row, column=hod_col).value == "Asha Ma'am"
    assert ws.cell(row=target_row, column=complaint_col).value == "The doctor attended the patient on time, but the air conditioning in the ward was not functioning."
    # Ensure UHID has preserved leading zero
    assert str(ws.cell(row=target_row, column=uhid_col).value) == "000889911"
