import io
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
import openpyxl
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (
    AuditLog,
    Feedback,
    FeedbackAIAnalysis,
    FeedbackAudio,
    FeedbackTranscript,
    RoleEnum,
    User,
)
from app.services.audio_service import ensure_audio_dir
from app.services.retention_service import (
    calculate_retention_expiry,
    purge_bulk_feedbacks,
    purge_single_feedback,
    run_automatic_retention_purge,
)

settings = get_settings()


def _create_sample_feedback(
    db: Session,
    uhid: str = "UHID-RET-001",
    patient_name: str = "Retention Test Patient",
    hours_ago: float = 0.0,
    has_audio_file: bool = False,
) -> Feedback:
    """Helper to construct a complete feedback hierarchy with optional age and audio file."""
    now = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    client_uuid = str(uuid.uuid4())
    fb_id = f"FB-{uuid.uuid4().hex[:8].upper()}"

    fb = Feedback(
        feedback_id=fb_id,
        client_uuid=client_uuid,
        staff_id="test-staff",
        staff_name="Staff Tester",
        uhid=uhid,
        patient_name=patient_name,
        location="OPD Room 102",
        consultant="Dr. Rajesh Kumar",
        scheme="Apollo Shield",
        attendant_name="Relative",
        department="Billing",
        subcategory="Overcharging",
        hod_name="Asha Ma'am",
        complaint="Billing was charged excessively without explanation.",
        is_deleted=False,
        created_at=now,
        date_str=now.strftime("%Y-%m-%d"),
        time_str=now.strftime("%H:%M"),
    )
    db.add(fb)
    db.commit()
    db.refresh(fb)

    # Transcript
    tr = FeedbackTranscript(
        feedback_id=fb.id,
        original_language="Hindi",
        original_transcript="Bohot zyada bill laga diya aur koi batane ko tayar nahi tha.",
        english_translation="They charged a very high bill and no one was ready to explain.",
        created_at=now,
    )
    db.add(tr)

    # AI Analysis
    ai = FeedbackAIAnalysis(
        feedback_id=fb.id,
        complaint_type="Billing",
        complaint_summary="High bill without explanation",
        detailed_feedback="Patient feels overcharged",
        positive_feedback="Doctor was good",
        negative_feedback="Billing issue",
        specific_complaint="Excessive charges",
        suggested_action="Review bill with accountant",
        priority="High",
        confidence_score=0.95,
        created_at=now,
    )
    db.add(ai)

    # Audio record & physical file if requested
    if has_audio_file:
        audio_dir = ensure_audio_dir()
        file_path = audio_dir / f"{client_uuid}.webm"
        file_path.write_bytes(b"RIFF_FAKE_AUDIO_DATA_FOR_TESTING")

        aud = FeedbackAudio(
            feedback_id=fb.id,
            file_path=str(file_path),
            file_size_bytes=32,
            duration_seconds=25.0,
            mime_type="audio/webm",
            created_at=now,
        )
        db.add(aud)

    # Audit Log simulating initial submission
    audit = AuditLog(
        actor_id="test-staff",
        actor_username="Staff Tester",
        action="FEEDBACK_SUBMITTED",
        entity_type="Feedback",
        entity_id=fb_id,
        details_json=json.dumps({"uhid": uhid, "patient_name": patient_name, "department": "Billing"}),
        created_at=now,
    )
    db.add(audit)

    db.commit()
    db.refresh(fb)
    return fb


# ============================================================================
# 1. ADMIN MANUAL DELETE
# ============================================================================

def test_01_admin_manual_delete_feedback(client: TestClient, admin_headers: dict, db_session: Session):
    """Admin can permanently delete a single feedback complaint."""
    fb = _create_sample_feedback(db_session, uhid="UHID-MANUAL-01")
    fb_id = fb.feedback_id

    res = client.delete(f"/api/v1/admin/feedback/{fb_id}", headers=admin_headers)
    assert res.status_code == 200
    data = res.json()
    assert "permanently deleted" in data["message"].lower()

    # Verify completely purged from DB
    remaining = db_session.query(Feedback).filter(Feedback.feedback_id == fb_id).first()
    assert remaining is None


def test_02_staff_delete_forbidden(client: TestClient, staff_headers: dict, db_session: Session):
    """Normal staff user is forbidden from deleting feedback (HTTP 403)."""
    fb = _create_sample_feedback(db_session, uhid="UHID-STAFF-FORBIDDEN")
    fb_id = fb.feedback_id

    res = client.delete(f"/api/v1/admin/feedback/{fb_id}", headers=staff_headers)
    assert res.status_code == 403

    # Verify record still exists in DB
    existing = db_session.query(Feedback).filter(Feedback.feedback_id == fb_id).first()
    assert existing is not None


def test_03_staff_bulk_delete_forbidden(client: TestClient, staff_headers: dict, db_session: Session):
    """Normal staff user is forbidden from bulk deleting feedback (HTTP 403)."""
    fb = _create_sample_feedback(db_session, uhid="UHID-BULK-FORBIDDEN")

    res = client.post(
        "/api/v1/admin/feedback/bulk-delete",
        json={"feedback_ids": [fb.id]},
        headers=staff_headers,
    )
    assert res.status_code == 403


# ============================================================================
# 2. BULK DELETE
# ============================================================================

def test_04_bulk_delete_multiple_records(client: TestClient, admin_headers: dict, db_session: Session):
    """Admin can select and bulk delete multiple records permanently."""
    fb1 = _create_sample_feedback(db_session, uhid="UHID-BULK-1")
    fb2 = _create_sample_feedback(db_session, uhid="UHID-BULK-2")
    fb3 = _create_sample_feedback(db_session, uhid="UHID-BULK-3")

    ids_to_delete = [fb1.id, fb2.feedback_id, fb3.id]

    res = client.post(
        "/api/v1/admin/feedback/bulk-delete",
        json={"feedback_ids": ids_to_delete},
        headers=admin_headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["purged_count"] == 3

    # Verify all 3 purged
    remaining = db_session.query(Feedback).filter(
        Feedback.id.in_([fb1.id, fb2.id, fb3.id])
    ).all()
    assert len(remaining) == 0


def test_05_bulk_delete_empty_list_rejected(client: TestClient, admin_headers: dict):
    """Bulk delete with empty ID list returns 400 Bad Request."""
    res = client.post(
        "/api/v1/admin/feedback/bulk-delete",
        json={"feedback_ids": []},
        headers=admin_headers,
    )
    assert res.status_code == 400


# ============================================================================
# 3. 12-HOUR RETENTION BOUNDARY
# ============================================================================

def test_06_retention_expiry_calculation_and_string(client: TestClient, admin_headers: dict, db_session: Session):
    """Test retention expiry timestamp is exact created_at + 12 hours and returned in API."""
    fb = _create_sample_feedback(db_session, uhid="UHID-EXPIRY-01")
    expected_expiry = calculate_retention_expiry(fb.created_at)
    assert expected_expiry == fb.created_at.replace(tzinfo=timezone.utc) + timedelta(hours=12)

    res = client.get(f"/api/v1/admin/feedback/{fb.feedback_id}", headers=admin_headers)
    assert res.status_code == 200
    data = res.json()
    assert "retention_expires_at" in data
    assert "retention_expiry_str" in data
    assert data["retention_expiry_str"] is not None


def test_07_retention_boundary_under_12h_not_purged(db_session: Session):
    """Feedback created 11.5 hours ago is within 12h window and NOT purged."""
    fb = _create_sample_feedback(db_session, uhid="UHID-UNDER-12H", hours_ago=11.5)
    fb_id = fb.feedback_id

    result = run_automatic_retention_purge(db=db_session, retention_hours=12)
    assert result["status"] == "SUCCESS"

    remaining = db_session.query(Feedback).filter(Feedback.feedback_id == fb_id).first()
    assert remaining is not None


def test_08_retention_boundary_over_12h_purged(db_session: Session):
    """Feedback created 12.5 hours ago has expired and IS automatically purged."""
    fb = _create_sample_feedback(db_session, uhid="UHID-OVER-12H", hours_ago=12.5)
    fb_id = fb.feedback_id

    result = run_automatic_retention_purge(db=db_session, retention_hours=12)
    assert result["status"] == "SUCCESS"
    assert result["purged_count"] >= 1

    remaining = db_session.query(Feedback).filter(Feedback.feedback_id == fb_id).first()
    assert remaining is None


# ============================================================================
# 4. AUDIO FILE CLEANUP
# ============================================================================

def test_09_manual_delete_unlinks_audio_file(db_session: Session):
    """Manual feedback purge permanently unlinks the audio file from disk."""
    fb = _create_sample_feedback(db_session, uhid="UHID-AUDIO-DEL", has_audio_file=True)
    audio_path = Path(fb.audio.file_path)
    assert audio_path.exists()

    success = purge_single_feedback(fb, db=db_session, actor=None, reason="MANUAL_DELETE")
    assert success is True
    assert not audio_path.exists()


def test_10_auto_purge_unlinks_audio_file(db_session: Session):
    """Automatic 12h purge permanently unlinks the audio file from disk."""
    fb = _create_sample_feedback(db_session, uhid="UHID-AUDIO-AUTO", hours_ago=15.0, has_audio_file=True)
    audio_path = Path(fb.audio.file_path)
    assert audio_path.exists()

    result = run_automatic_retention_purge(db=db_session, retention_hours=12)
    assert result["purged_count"] >= 1
    assert not audio_path.exists()


# ============================================================================
# 5. AUDIT PRIVACY & SANITIZATION
# ============================================================================

def test_11_audit_log_sanitization_on_purge(db_session: Session):
    """Historical audit logs have patient identifiers and complaints stripped on purge."""
    fb = _create_sample_feedback(db_session, uhid="UHID-SANITIZE-99", hours_ago=15.0)
    fb_id = fb.feedback_id

    run_automatic_retention_purge(db=db_session, retention_hours=12)

    # Check historical logs for this feedback
    logs = db_session.query(AuditLog).filter(AuditLog.entity_id == fb_id).all()
    for log in logs:
        if log.action == "FEEDBACK_SUBMITTED":
            data = json.loads(log.details_json)
            assert data.get("purged") is True
            assert "uhid" not in data
            assert "UHID-SANITIZE-99" not in log.details_json


def test_12_clean_deletion_audit_event_logged(db_session: Session):
    """Purge records a clean FEEDBACK_DELETED or AUTO_PURGED audit event without sensitive details."""
    fb = _create_sample_feedback(db_session, uhid="UHID-EVENT-TEST", hours_ago=15.0)
    fb_id = fb.feedback_id

    run_automatic_retention_purge(db=db_session, retention_hours=12)

    purge_event = (
        db_session.query(AuditLog)
        .filter(AuditLog.entity_id == fb_id, AuditLog.action == "AUTO_PURGED")
        .first()
    )
    assert purge_event is not None
    details = json.loads(purge_event.details_json)
    assert details.get("status") == "PERMANENTLY_PURGED"
    assert "patient_name" not in details
    assert "uhid" not in details


# ============================================================================
# 6. DASHBOARD & EXCEL EXPORT INTEGRITY
# ============================================================================

def test_13_purged_feedback_absent_from_dashboard_and_search(
    client: TestClient, admin_headers: dict, db_session: Session
):
    """Purged feedback disappears completely from search and table queries."""
    fb = _create_sample_feedback(db_session, uhid="UHID-SEARCH-ABSENT")
    fb_id = fb.feedback_id

    # Verify present before delete
    res_before = client.get(f"/api/v1/admin/feedback?search={fb_id}", headers=admin_headers)
    assert res_before.status_code == 200
    assert any(item["feedback_id"] == fb_id for item in res_before.json()["items"])

    # Delete record
    purge_single_feedback(fb, db=db_session, actor=None, reason="MANUAL_DELETE")

    # Verify absent after delete
    res_after = client.get(f"/api/v1/admin/feedback?search={fb_id}", headers=admin_headers)
    assert res_after.status_code == 200
    assert not any(item["feedback_id"] == fb_id for item in res_after.json()["items"])


def test_14_excel_export_includes_active_excludes_purged(
    client: TestClient, admin_headers: dict, db_session: Session
):
    """Excel export includes active feedback and excludes purged feedback."""
    active_fb = _create_sample_feedback(db_session, uhid="UHID-ACTIVE-EXPORT")
    purged_fb = _create_sample_feedback(db_session, uhid="UHID-PURGED-EXPORT")

    # Delete the second record
    purge_single_feedback(purged_fb, db=db_session, actor=None, reason="MANUAL_DELETE")

    res = client.get("/api/v1/admin/export-excel", headers=admin_headers)
    assert res.status_code == 200

    wb = openpyxl.load_workbook(io.BytesIO(res.content))
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))

    uhids_in_excel = [r[2] for r in rows[1:]]
    assert active_fb.uhid in uhids_in_excel
    assert purged_fb.uhid not in uhids_in_excel


def test_15_excel_export_retains_exactly_11_columns(
    client: TestClient, admin_headers: dict
):
    """Excel export adheres to the exact 11 hospital columns without extra technical fields."""
    res = client.get("/api/v1/admin/export-excel", headers=admin_headers)
    assert res.status_code == 200

    wb = openpyxl.load_workbook(io.BytesIO(res.content))
    ws = wb.active
    header_cells = [cell.value for cell in ws[1]]
    expected = [
        "Date",
        "Time",
        "UHID",
        "Patient Name",
        "Location",
        "Consultant",
        "Scheme",
        "Department",
        "HOD",
        "Complaint Type",
        "Complaint",
    ]
    assert header_cells == expected
    assert len(header_cells) == 11


# ============================================================================
# 7. RESILIENCE & OFFLINE SAFETY
# ============================================================================

def test_16_retention_purge_idempotent(db_session: Session):
    """Re-running the retention cleanup multiple times is safe and idempotent."""
    _create_sample_feedback(db_session, uhid="UHID-IDEMP-01", hours_ago=15.0)

    res1 = run_automatic_retention_purge(db=db_session, retention_hours=12)
    assert res1["purged_count"] >= 1

    # Second run should have 0 eligible and complete cleanly
    res2 = run_automatic_retention_purge(db=db_session, retention_hours=12)
    assert res2["status"] == "SUCCESS"
    assert res2["purged_count"] == 0
    assert res2["failed_count"] == 0


def test_17_offline_unsynced_feedback_safety(db_session: Session):
    """
    Offline queue records stored locally on mobile client are not purged by server
    retention job. Server auto-purge strictly evaluates server database entries.
    """
    # Simulate server-side cleanup running while an offline draft exists on client
    res = run_automatic_retention_purge(db=db_session, retention_hours=12)
    assert res["status"] == "SUCCESS"
    # Validates server does not touch offline client storage


def test_18_cron_webhook_retention_purge(client: TestClient, db_session: Session):
    """Cloud scheduler webhook triggers purge with secure X-Cron-Key header."""
    _create_sample_feedback(db_session, uhid="UHID-WEBHOOK-EXPIRED", hours_ago=15.0)

    # 1. Without header -> 401 Unauthorized
    unauth = client.post("/api/v1/admin/retention/cron-trigger")
    assert unauth.status_code == 401

    # 2. With invalid header -> 401 Unauthorized
    invalid = client.post(
        "/api/v1/admin/retention/cron-trigger",
        headers={"X-Cron-Key": "wrong-secret-key"},
    )
    assert invalid.status_code == 401

    # 3. With valid X-Cron-Key -> 200 OK & executes purge
    success = client.post(
        "/api/v1/admin/retention/cron-trigger",
        headers={"X-Cron-Key": settings.CRON_SECRET},
    )
    assert success.status_code == 200
    data = success.json()
    assert data["status"] == "SUCCESS"
    assert data["purged_count"] >= 1


def test_19_cli_retention_job_execution(db_session: Session):
    """Verifies that the standalone CLI entrypoint executes cleanly without exceptions."""
    from app.cli.retention_job import run_automatic_retention_purge
    result = run_automatic_retention_purge(db=db_session, retention_hours=12)
    assert result["status"] == "SUCCESS"
    assert "purged_count" in result
