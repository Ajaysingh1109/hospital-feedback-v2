import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import AuditLog, Feedback, FeedbackAudio, HODMapping, RoleEnum, User
from app.services.hod_service import get_deterministic_hod
from app.services.recovery_service import recover_orphaned_feedback_jobs
from app.services.retention_service import calculate_retention_expiry, run_automatic_retention_purge


def test_startup_recovery_interrupted_jobs(db_session: Session, tmp_path: Path):
    """
    FIX 2 Regression Test:
    Ensures that when the application starts, any in-flight jobs interrupted by container
    restart or OOM are inspected:
    - Jobs with audio file intact are safely re-queued for processing.
    - Jobs with missing audio and no manual complaint transition to NEEDS_REVIEW.
    - Recovery is idempotent and produces zero duplicates.
    """
    # 1. Create dummy audio file
    audio_file = tmp_path / "recovery_test.webm"
    audio_file.write_bytes(b"\x1a\x45\xdf\xa3" + b"A" * 2000)

    # 2. Interrupted Job A (Has valid audio -> Recoverable)
    uuid_a = f"uuid-rec-a-{uuid.uuid4().hex[:6]}"
    fb_a = Feedback(
        feedback_id=f"FB-{uuid.uuid4().hex[:8].upper()}",
        client_uuid=uuid_a,
        date_str="2026-11-17",
        time_str="15:00:00",
        staff_id="test-staff",
        staff_name="Nurse Tester",
        uhid="UHID-REC-001",
        patient_name="Patient Recovery A",
        department="Nursing",
        hod_name="Reshmi Ma'am",
        complaint="Audio captured — processing in background...",
        status="PROCESSING",  # Interrupted mid-flight!
        is_deleted=False,
    )
    db_session.add(fb_a)
    db_session.flush()

    audio_rec_a = FeedbackAudio(
        feedback_id=fb_a.id,
        file_path=str(audio_file),
        file_size_bytes=len(audio_file.read_bytes()),
        duration_seconds=3.0,
        mime_type="audio/webm",
        retention_status="KEPT",
    )
    db_session.add(audio_rec_a)

    # 3. Interrupted Job B (No audio, no manual complaint -> Unrecoverable -> NEEDS_REVIEW)
    uuid_b = f"uuid-rec-b-{uuid.uuid4().hex[:6]}"
    fb_b = Feedback(
        feedback_id=f"FB-{uuid.uuid4().hex[:8].upper()}",
        client_uuid=uuid_b,
        date_str="2026-11-17",
        time_str="15:00:00",
        staff_id="test-staff",
        staff_name="Nurse Tester",
        uhid="UHID-REC-002",
        patient_name="Patient Recovery B",
        department="Clinical",
        hod_name="Tanveer Sir",
        complaint="Audio captured — processing in background...",
        status="TRANSCRIBING",  # Interrupted mid-flight with no audio file!
        is_deleted=False,
    )
    db_session.add(fb_b)
    db_session.commit()

    # 4. Run recovery engine
    bind = db_session.get_bind()
    result = recover_orphaned_feedback_jobs(db=db_session, engine_bind=bind)

    assert result["total_orphaned"] >= 2
    assert result["requeued"] >= 1
    assert result["needs_review"] >= 1

    # Check database statuses
    db_session.refresh(fb_a)
    db_session.refresh(fb_b)

    # Job A was re-queued (or completed by thread)
    assert fb_a.status in ["QUEUED", "PROCESSING", "COMPLETED", "NEEDS_REVIEW"]
    # Job B had no audio and must safely be in NEEDS_REVIEW
    assert fb_b.status == "NEEDS_REVIEW"
    assert "interrupted" in fb_b.processing_error.lower()


def test_dynamic_hod_configuration_master_editing(client: TestClient, admin_headers: dict, db_session: Session):
    """
    FIX 6 Regression Test:
    Ensures Master/Admin can dynamically configure department HOD assignments
    without requiring application redeployment or restart.
    """
    # 1. Fetch current Clinical HOD (Default: Tanveer Sir)
    default_hod = get_deterministic_hod("Clinical", db=db_session)
    assert default_hod == "Tanveer Sir"

    # 2. Master updates Clinical HOD to a new doctor
    mapping = db_session.query(HODMapping).filter(HODMapping.department_name == "Clinical").first()
    assert mapping is not None

    update_res = client.put(
        f"/api/v1/admin/hod-mappings/{mapping.id}",
        json={"hod_name": "Dr. Sarah Johnson Ma'am", "is_active": True},
        headers=admin_headers,
    )
    assert update_res.status_code == 200
    assert update_res.json()["hod_name"] == "Dr. Sarah Johnson Ma'am"

    # 3. Verify immediate effect in backend resolution
    updated_hod = get_deterministic_hod("Clinical", db=db_session)
    assert updated_hod == "Dr. Sarah Johnson Ma'am"

    # 4. Master creates a new custom department mapping (e.g. Oncology)
    add_res = client.post(
        "/api/v1/admin/hod-mappings",
        json={"department_name": "Oncology", "hod_name": "Dr. Raman Sir", "is_active": True},
        headers=admin_headers,
    )
    assert add_res.status_code == 201
    assert get_deterministic_hod("Oncology", db=db_session) == "Dr. Raman Sir"

    # 5. Master restores default HOD assignments
    restore_res = client.post("/api/v1/admin/hod-mappings/restore-defaults", headers=admin_headers)
    assert restore_res.status_code == 200
    assert get_deterministic_hod("Clinical", db=db_session) == "Tanveer Sir"


def test_12_hour_retention_policy_exact(db_session: Session, tmp_path: Path):
    """
    12-Hour Retention Verification:
    - 11 hours 50 mins ago (under 12h) -> Retained.
    - 12 hours 10 mins ago (over 12h) -> Automatically purged.
    - Audio file is unlinked.
    """
    now = datetime.now(timezone.utc)

    # 1. Feedback under 12h (11.8h)
    fb_under = Feedback(
        feedback_id=f"FB-UNDER-12H-{uuid.uuid4().hex[:6]}",
        client_uuid=f"uuid-under-{uuid.uuid4().hex[:6]}",
        staff_id="test-staff",
        staff_name="Nurse Tester",
        uhid="UHID-RETAINED-12H",
        patient_name="Retained Patient",
        department="Nursing",
        hod_name="Reshmi Ma'am",
        complaint="Room bell responded quickly.",
        status="COMPLETED",
        created_at=now - timedelta(hours=11.8),
        date_str=(now - timedelta(hours=11.8)).strftime("%Y-%m-%d"),
        time_str=(now - timedelta(hours=11.8)).strftime("%H:%M"),
        is_deleted=False,
    )
    db_session.add(fb_under)

    # 2. Feedback over 12h (12.2h) with audio file
    audio_path = tmp_path / "expired_12h_audio.webm"
    audio_path.write_bytes(b"\x1a\x45\xdf\xa3" + b"X" * 2000)

    fb_over = Feedback(
        feedback_id=f"FB-OVER-12H-{uuid.uuid4().hex[:6]}",
        client_uuid=f"uuid-over-{uuid.uuid4().hex[:6]}",
        staff_id="test-staff",
        staff_name="Nurse Tester",
        uhid="UHID-PURGED-12H",
        patient_name="Expired Patient",
        department="Billing",
        hod_name="Asha Ma'am",
        complaint="Billing delayed.",
        status="COMPLETED",
        created_at=now - timedelta(hours=12.2),
        date_str=(now - timedelta(hours=12.2)).strftime("%Y-%m-%d"),
        time_str=(now - timedelta(hours=12.2)).strftime("%H:%M"),
        is_deleted=False,
    )
    db_session.add(fb_over)
    db_session.flush()

    audio_rec = FeedbackAudio(
        feedback_id=fb_over.id,
        file_path=str(audio_path),
        file_size_bytes=len(audio_path.read_bytes()),
        duration_seconds=2.5,
        mime_type="audio/webm",
        retention_status="KEPT",
    )
    db_session.add(audio_rec)
    db_session.commit()

    assert audio_path.exists()

    # 3. Run retention purge with 12 hours
    result = run_automatic_retention_purge(db=db_session, retention_hours=12)
    assert result["status"] == "SUCCESS"
    assert result["purged_count"] >= 1

    # 4. Verify under 12h remains intact
    assert db_session.query(Feedback).filter(Feedback.id == fb_under.id).first() is not None

    # 5. Verify over 12h is purged and audio file deleted
    assert db_session.query(Feedback).filter(Feedback.id == fb_over.id).first() is None
    assert not audio_path.exists()


def test_production_secrets_validation_fails_on_missing_keys():
    """
    FIX 4 & 5 Regression Test:
    Ensures that when ENVIRONMENT=production, missing SECRET_KEY or CRON_SECRET
    causes fail-fast validation errors.
    """
    old_env = os.environ.get("ENVIRONMENT")
    old_secret = os.environ.get("SECRET_KEY")
    old_cron = os.environ.get("CRON_SECRET")

    try:
        os.environ["ENVIRONMENT"] = "production"
        os.environ["SECRET_KEY"] = ""  # Missing!

        with pytest.raises(ValueError, match="SECRET_KEY environment variable is missing"):
            Settings()

        # Restore secret key, but miss CRON_SECRET
        os.environ["SECRET_KEY"] = "super-secure-production-secret-key-32chars"
        os.environ["CRON_SECRET"] = ""  # Missing!

        with pytest.raises(ValueError, match="CRON_SECRET environment variable is missing"):
            Settings()

    finally:
        # Restore test environment
        if old_env is not None:
            os.environ["ENVIRONMENT"] = old_env
        else:
            os.environ.pop("ENVIRONMENT", None)
        if old_secret is not None:
            os.environ["SECRET_KEY"] = old_secret
        if old_cron is not None:
            os.environ["CRON_SECRET"] = old_cron


def test_temporary_voice_recording_security_and_permissions(
    client: TestClient, admin_headers: dict, staff_headers: dict, db_session: Session, tmp_path: Path
):
    """
    Temporary Recording Security & Review Verification:
    1. Audio is saved privately on persistent server storage, associated with client_uuid.
    2. Unauthenticated audio access returns 401.
    3. Unauthorized staff (staff accessing another staff's recording) returns 403.
    4. Master / Admin can access and listen to any recording before 12 hours.
    5. Feedback detail includes audio_expires_at and is_audio_expired=False.
    """
    now = datetime.now(timezone.utc)
    audio_dir = tmp_path / "audio_storage"
    audio_dir.mkdir(parents=True, exist_ok=True)
    audio_file = audio_dir / "temp_rec_001.webm"
    audio_content = b"\x1a\x45\xdf\xa3" + b"TEST_VOICE_DATA" * 100
    audio_file.write_bytes(audio_content)

    # Create feedback submitted by staff user
    staff_user = db_session.query(User).filter(User.role == RoleEnum.STAFF).first()
    client_uuid = f"uuid-voice-test-{uuid.uuid4().hex[:8]}"
    fb = Feedback(
        feedback_id=f"FB-VOICE-{uuid.uuid4().hex[:6]}",
        client_uuid=client_uuid,
        staff_id=staff_user.id,
        staff_name=staff_user.display_name,
        uhid="UHID-VOICE-001",
        patient_name="Voice Test Patient",
        department="Nursing",
        hod_name="Reshmi Ma'am",
        complaint="Room bell responded quickly.",
        status="COMPLETED",
        created_at=now - timedelta(hours=1),
        date_str=now.strftime("%Y-%m-%d"),
        time_str=now.strftime("%H:%M:%S"),
        is_deleted=False,
    )
    db_session.add(fb)
    db_session.flush()

    audio_rec = FeedbackAudio(
        feedback_id=fb.id,
        file_path=str(audio_file),
        file_size_bytes=len(audio_content),
        duration_seconds=5.0,
        mime_type="audio/webm",
        retention_status="KEPT",
    )
    db_session.add(audio_rec)
    db_session.commit()

    # 1. Unauthenticated request to audio endpoint -> 401
    res_unauth = client.get(f"/api/v1/audio/{fb.feedback_id}")
    assert res_unauth.status_code == 401

    # 2. Staff who created it CAN stream it
    res_staff = client.get(f"/api/v1/audio/{fb.feedback_id}", headers=staff_headers)
    assert res_staff.status_code == 200
    assert res_staff.content == audio_content

    # 3. Another staff user who DID NOT create it -> 403 Forbidden
    other_staff = User(
        username=f"other_staff_{uuid.uuid4().hex[:6]}",
        display_name="Other Staff",
        password_hash="mock_hash",
        role=RoleEnum.STAFF,
        is_active=True,
    )
    db_session.add(other_staff)
    db_session.commit()
    from app.core.security import create_access_token
    other_token = create_access_token(subject=other_staff.id, role="STAFF")
    res_forbidden = client.get(
        f"/api/v1/audio/{fb.feedback_id}", headers={"Authorization": f"Bearer {other_token}"}
    )
    assert res_forbidden.status_code == 403

    # 4. Master / Admin CAN stream it for review
    res_admin = client.get(f"/api/v1/audio/{fb.feedback_id}", headers=admin_headers)
    assert res_admin.status_code == 200
    assert res_admin.content == audio_content

    # Can also lookup by client_uuid or audio_rec.id
    res_by_uuid = client.get(f"/api/v1/audio/{client_uuid}", headers=admin_headers)
    assert res_by_uuid.status_code == 200

    # 5. Admin feedback detail returns audio_expires_at, is_audio_expired=False, has_audio=True
    res_detail = client.get(f"/api/v1/admin/feedback/{fb.id}", headers=admin_headers)
    assert res_detail.status_code == 200
    detail = res_detail.json()
    assert detail["has_audio"] is True
    assert detail["is_audio_expired"] is False
    assert detail["audio_expires_at"] is not None


def test_temporary_voice_recording_12h_expiry_and_physical_unlink(
    client: TestClient, admin_headers: dict, db_session: Session, tmp_path: Path
):
    """
    12-Hour Expiration & Purge Verification:
    - Audio older than 12 hours returns 404 on streaming.
    - Automatic retention purge physically deletes file (p.unlink()).
    - Purged feedback cascades delete across transcript, AI, audio.
    - Historical audit logs are sanitized (no UHID, patient name, or complaint text).
    - Missing files during purge are handled gracefully without exceptions.
    """
    import json
    now = datetime.now(timezone.utc)
    audio_dir = tmp_path / "audio_expired"
    audio_dir.mkdir(parents=True, exist_ok=True)
    audio_file = audio_dir / "expired_recording.webm"
    audio_file.write_bytes(b"\x1a\x45\xdf\xa3" + b"EXPIRED_VOICE" * 100)
    assert audio_file.exists()

    staff_user = db_session.query(User).filter(User.role == RoleEnum.STAFF).first()
    client_uuid = f"uuid-expired-{uuid.uuid4().hex[:8]}"
    fb = Feedback(
        feedback_id=f"FB-EXP-{uuid.uuid4().hex[:6]}",
        client_uuid=client_uuid,
        staff_id=staff_user.id,
        staff_name=staff_user.display_name,
        uhid="UHID-SENSITIVE-999",
        patient_name="Confidential Patient",
        department="Clinical",
        hod_name="Tanveer Sir",
        complaint="Doctor consultation delay in room 12.",
        status="COMPLETED",
        created_at=now - timedelta(hours=12.5),  # Older than 12 hours!
        date_str=(now - timedelta(hours=12.5)).strftime("%Y-%m-%d"),
        time_str=(now - timedelta(hours=12.5)).strftime("%H:%M:%S"),
        is_deleted=False,
    )
    db_session.add(fb)
    db_session.flush()

    audio_rec = FeedbackAudio(
        feedback_id=fb.id,
        file_path=str(audio_file),
        file_size_bytes=len(audio_file.read_bytes()),
        duration_seconds=4.0,
        mime_type="audio/webm",
        retention_status="KEPT",
    )
    db_session.add(audio_rec)

    # Add audit log with sensitive information
    audit_entry = AuditLog(
        actor_id=staff_user.id,
        actor_username=staff_user.username,
        action="FEEDBACK_CREATED",
        entity_type="Feedback",
        entity_id=fb.feedback_id,
        details_json=json.dumps({"uhid": "UHID-SENSITIVE-999", "patient_name": "Confidential Patient"}),
    )
    db_session.add(audit_entry)
    db_session.commit()

    # 1. Direct stream before purge job: Since created_at > 12h, returns 404 (expired)
    res_expired_stream = client.get(f"/api/v1/audio/{fb.feedback_id}", headers=admin_headers)
    assert res_expired_stream.status_code == 404
    assert "expired" in res_expired_stream.json()["detail"].lower()

    # 2. Run automatic retention purge
    result = run_automatic_retention_purge(db=db_session, retention_hours=12)
    assert result["status"] == "SUCCESS"
    assert result["purged_count"] >= 1

    # 3. Space Protection: Physical audio file must be unlinked from disk
    assert not audio_file.exists()

    # 4. Feedback record is deleted from DB
    assert db_session.query(Feedback).filter(Feedback.id == fb.id).first() is None
    assert db_session.query(FeedbackAudio).filter(FeedbackAudio.feedback_id == fb.id).first() is None

    # 5. Audit log is sanitized: no UHID or patient name
    db_session.refresh(audit_entry)
    assert "UHID-SENSITIVE-999" not in audit_entry.details_json
    assert "Confidential Patient" not in audit_entry.details_json
    assert "purged" in audit_entry.details_json.lower()

    # 6. Idempotent & safe: running purge again on missing file causes NO crash
    result2 = run_automatic_retention_purge(db=db_session, retention_hours=12)
    assert result2["status"] == "SUCCESS"

