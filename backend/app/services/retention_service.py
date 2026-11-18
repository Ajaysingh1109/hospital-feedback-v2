import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from ..core.config import get_settings
from ..models import AuditLog, Feedback, FeedbackAudio, User
from .audit_service import log_audit
from .audio_service import delete_from_supabase_storage, ensure_audio_dir

logger = logging.getLogger(__name__)
settings = get_settings()

RETENTION_HOURS = 12


def calculate_retention_expiry(created_at: datetime) -> datetime:
    """Returns exact timestamp when feedback must be purged (created_at + 12 hours)."""
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return created_at + timedelta(hours=RETENTION_HOURS)


def purge_single_feedback(
    target: Union[str, Feedback],
    db: Session,
    actor: Optional[User] = None,
    reason: str = "MANUAL_DELETE",
) -> bool:
    """
    Permanently purges a feedback record and all associated data:
    1. Removes audio recording file(s) from local or cloud storage.
    2. Removes any temporary processing data/files.
    3. Sanitizes historical audit logs for this record (removing UHID, patient name, complaints).
    4. Records clean audit event (FEEDBACK_DELETED or AUTO_PURGED) without retaining sensitive data.
    5. Cascades delete across database tables (Transcript, AIAnalysis, Audio, Corrections, Feedback).
    """
    if isinstance(target, str):
        fb = db.scalar(
            select(Feedback)
            .where(or_(Feedback.id == target, Feedback.feedback_id == target, Feedback.client_uuid == target))
            .options(
                selectinload(Feedback.transcript),
                selectinload(Feedback.audio),
                selectinload(Feedback.ai_analysis),
                selectinload(Feedback.corrections),
            )
        )
    else:
        fb = target

    if not fb:
        return False

    fb_id = fb.feedback_id
    db_id = fb.id
    client_uuid = fb.client_uuid

    # 1. Permanently delete associated audio recording files (local / container / cloud storage)
    audio_paths_to_delete: List[str] = []
    if fb.audio and fb.audio.file_path:
        audio_paths_to_delete.append(fb.audio.file_path)

    # Check potential standard storage paths for this feedback session
    audio_dir = ensure_audio_dir()
    candidate_paths = [
        audio_dir / f"{client_uuid}.webm",
        audio_dir / f"{fb_id}.webm",
        Path(f"/tmp/audio/{client_uuid}.webm"),
        Path(f"/tmp/audio/{fb_id}.webm"),
    ]
    if fb.audio:
        candidate_paths.append(audio_dir / f"{fb.audio.id}.webm")

    for p in candidate_paths:
        if p.exists():
            audio_paths_to_delete.append(str(p))

    for path_str in set(audio_paths_to_delete):
        try:
            p = Path(path_str)
            if p.exists() and p.is_file():
                p.unlink()
                logger.info(f"[Retention] Successfully deleted audio file: {path_str}")
        except Exception as e:
            logger.warning(f"[Retention] Could not delete audio file {path_str}: {e}")

    # Also purge from private Supabase Storage if backed up
    try:
        delete_from_supabase_storage(f"{client_uuid}.webm")
        delete_from_supabase_storage(f"{fb_id}.webm")
        if fb.audio and fb.audio.file_path:
            delete_from_supabase_storage(Path(fb.audio.file_path).name)
    except Exception as e:
        logger.warning(f"[Retention] Notice deleting from private cloud storage: {e}")

    # 2. Sanitize any historical audit logs matching this feedback so patient details are NOT retained
    try:
        historical_logs = db.scalars(
            select(AuditLog).where(
                AuditLog.entity_id.in_([fb_id, db_id, client_uuid])
            )
        ).all()
        for log_entry in historical_logs:
            log_entry.details_json = json.dumps({
                "purged": True,
                "notice": f"Patient content permanently purged per {RETENTION_HOURS}-hour retention policy.",
            })
    except Exception as e:
        logger.warning(f"[Retention] Error sanitizing historical audit logs for {fb_id}: {e}")

    # 3. Write clean deletion audit event without patient identifiers or complaint text
    action_type = "FEEDBACK_DELETED" if "MANUAL" in reason or "BULK" in reason else "AUTO_PURGED"
    actor_username = actor.username if actor else "SYSTEM"
    actor_id = actor.id if actor else "SYSTEM"

    audit_entry = AuditLog(
        actor_id=actor_id,
        actor_username=actor_username,
        action=action_type,
        entity_type="Feedback",
        entity_id=fb_id,
        details_json=json.dumps({
            "status": "PERMANENTLY_PURGED",
            "retention_rule": f"{RETENTION_HOURS}_HOURS",
            "reason": reason,
        }),
    )
    db.add(audit_entry)

    # 4. Permanently delete Feedback core (cascades to transcripts, ai_analysis, audio, corrections)
    db.delete(fb)
    db.commit()
    logger.info(f"[Retention] Permanently purged feedback record {fb_id} ({reason}).")
    return True


def purge_bulk_feedbacks(
    feedback_ids: List[str],
    db: Session,
    actor: Optional[User] = None,
) -> int:
    """Permanently purges multiple selected feedback records."""
    count = 0
    for fid in feedback_ids:
        if not fid or not str(fid).strip():
            continue
        try:
            if purge_single_feedback(str(fid).strip(), db=db, actor=actor, reason="BULK_DELETE"):
                count += 1
        except Exception as e:
            logger.error(f"[Retention] Failed to purge {fid} during bulk delete: {e}")
            db.rollback()
    return count


ADVISORY_LOCK_ID = 84729103  # Fixed 32-bit identifier for hospital retention lock


def acquire_advisory_lock(db: Session) -> bool:
    """Attempts to acquire non-blocking PostgreSQL advisory lock to prevent duplicate concurrent purges."""
    try:
        bind = db.get_bind()
        if bind and bind.dialect.name == "postgresql":
            from sqlalchemy import text
            res = db.execute(text("SELECT pg_try_advisory_lock(:lock_id)"), {"lock_id": ADVISORY_LOCK_ID}).scalar()
            return bool(res)
    except Exception as e:
        logger.warning(f"[Retention Lock] Notice while acquiring advisory lock: {e}")
    return True


def release_advisory_lock(db: Session):
    """Releases PostgreSQL advisory lock."""
    try:
        bind = db.get_bind()
        if bind and bind.dialect.name == "postgresql":
            from sqlalchemy import text
            db.execute(text("SELECT pg_advisory_unlock(:lock_id)"), {"lock_id": ADVISORY_LOCK_ID})
    except Exception as e:
        logger.warning(f"[Retention Lock] Notice while releasing advisory lock: {e}")


def run_automatic_retention_purge(
    db: Session,
    retention_hours: int = RETENTION_HOURS,
) -> Dict[str, Any]:
    """
    Automated scheduled cleanup mechanism:
    Finds and permanently deletes all feedback records >= 48 hours old.
    Ensures safe error isolation per record, idempotency, and multi-instance concurrency safety.
    """
    if not acquire_advisory_lock(db):
        logger.info("[Retention] Another retention worker instance is currently running. Skipping duplicate run.")
        return {
            "status": "SKIPPED",
            "message": "Another worker instance is executing retention purge. Advisory lock busy.",
            "retention_hours": retention_hours,
            "purged_count": 0,
            "total_eligible": 0,
            "failed_count": 0,
        }

    try:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=retention_hours)

        # Query records older than or equal to cutoff
        eligible_feedbacks = db.scalars(
            select(Feedback)
            .where(Feedback.created_at <= cutoff)
            .options(
                selectinload(Feedback.transcript),
                selectinload(Feedback.audio),
                selectinload(Feedback.ai_analysis),
                selectinload(Feedback.corrections),
            )
        ).all()

        total_eligible = len(eligible_feedbacks)
        purged_count = 0
        failed_count = 0

        for fb in eligible_feedbacks:
            fb_id = fb.feedback_id
            try:
                if purge_single_feedback(fb, db=db, actor=None, reason="AUTO_PURGED"):
                    purged_count += 1
            except Exception as e:
                logger.error(f"[Retention] Error auto-purging feedback {fb_id}: {e}")
                db.rollback()
                failed_count += 1

        if purged_count > 0:
            logger.info(
                f"[Retention] Automatic Purge Job completed: {purged_count}/{total_eligible} "
                f"expired records purged (cutoff: {cutoff.isoformat()})."
            )

        return {
            "status": "SUCCESS",
            "retention_hours": retention_hours,
            "cutoff_timestamp": cutoff.isoformat(),
            "total_eligible": total_eligible,
            "purged_count": purged_count,
            "failed_count": failed_count,
        }
    finally:
        release_advisory_lock(db)
