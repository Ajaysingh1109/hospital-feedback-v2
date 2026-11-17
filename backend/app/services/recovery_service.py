import logging
import os
import threading
from typing import Dict, Set
from sqlalchemy.orm import Session

from ..models import Feedback

logger = logging.getLogger("hospital_feedback.recovery")

# Concurrency guard: track currently active recovering client_uuids
_active_recovery_uuids: Set[str] = set()
_recovery_lock = threading.Lock()


def recover_orphaned_feedback_jobs(db: Session, engine_bind=None) -> Dict[str, int]:
    """
    Startup recovery for in-flight jobs interrupted by container restarts, deploys, or crashes.
    Inspects records in in-flight states: QUEUED, PROCESSING, TRANSCRIBING, TRANSLATING, ANALYZING, VALIDATING.
    Safely re-queues recoverable jobs; transitions unrecoverable records to NEEDS_REVIEW.
    Idempotent, zero duplicate records, zero patient details logged.
    """
    from ..api.v1.feedback import process_feedback_background_job

    in_flight_statuses = [
        "QUEUED",
        "PROCESSING",
        "TRANSCRIBING",
        "TRANSLATING",
        "ANALYZING",
        "VALIDATING",
    ]

    orphaned = (
        db.query(Feedback)
        .filter(Feedback.status.in_(in_flight_statuses), Feedback.is_deleted == False)
        .all()
    )

    requeued_count = 0
    needs_review_count = 0
    skipped_count = 0

    for fb in orphaned:
        with _recovery_lock:
            if fb.client_uuid in _active_recovery_uuids:
                skipped_count += 1
                continue
            _active_recovery_uuids.add(fb.client_uuid)

        audio_path = fb.audio.file_path if fb.audio else None
        audio_exists = bool(audio_path and os.path.exists(audio_path))
        has_manual = bool(
            fb.complaint
            and fb.complaint != "Audio captured — processing in background..."
            and fb.complaint.strip()
        )

        if audio_exists or has_manual:
            # Re-queue for background processing
            fb.status = "QUEUED"
            fb.processing_error = None
            db.commit()

            def run_job(
                f_id=fb.id,
                c_uuid=fb.client_uuid,
                a_path=audio_path,
                m_comp=fb.complaint if has_manual else None,
                bind=engine_bind,
            ):
                try:
                    process_feedback_background_job(
                        feedback_db_id=f_id,
                        client_uuid=c_uuid,
                        audio_file_path=a_path,
                        manual_complaint=m_comp,
                        engine_bind=bind,
                    )
                except Exception as e:
                    logger.error(f"[Startup Recovery] Failed processing recovered job {c_uuid}: {e}")
                finally:
                    with _recovery_lock:
                        _active_recovery_uuids.discard(c_uuid)

            thread = threading.Thread(target=run_job, daemon=True)
            thread.start()
            requeued_count += 1
        else:
            # Unrecoverable because audio is missing and no manual complaint exists
            fb.status = "NEEDS_REVIEW"
            fb.processing_error = "Server restart interrupted in-flight job; audio recording was missing or unrecoverable."
            db.commit()
            with _recovery_lock:
                _active_recovery_uuids.discard(fb.client_uuid)
            needs_review_count += 1

    total_orphaned = len(orphaned)
    if total_orphaned > 0:
        logger.info(
            f"[Startup Recovery] Processed {total_orphaned} interrupted jobs: "
            f"{requeued_count} re-queued, {needs_review_count} marked NEEDS_REVIEW, {skipped_count} skipped."
        )

    return {
        "total_orphaned": total_orphaned,
        "requeued": requeued_count,
        "needs_review": needs_review_count,
        "skipped": skipped_count,
    }
