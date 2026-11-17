"""
Portable 12-Hour Retention Cleanup Job (CLI & Cron Entrypoint)

Usage:
    python -m app.cli.retention_job
    python -m app.cli.retention_job --hours 12

Can be executed by:
- Linux Crontab (e.g. `0 * * * * cd /app && python -m app.cli.retention_job`)
- Kubernetes CronJob
- AWS ECS Scheduled Task / EventBridge
- GCP Cloud Run Job
- Render / Heroku Cron Scheduler
"""
import argparse
import logging
import sys
from datetime import datetime, timezone

from ..core.config import get_settings
from ..db.database import SessionLocal
from ..services.retention_service import run_automatic_retention_purge

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("retention_job")
settings = get_settings()


def main():
    parser = argparse.ArgumentParser(description="Hospital Feedback 12-Hour Data Retention & Purge Job")
    parser.add_argument(
        "--hours",
        type=int,
        default=12,
        help="Retention period in hours (default: 12)",
    )
    args = parser.parse_args()

    start_time = datetime.now(timezone.utc)
    logger.info(f"Starting Hospital Feedback retention purge job (Retention window: {args.hours} hours)...")

    try:
        with SessionLocal() as db:
            result = run_automatic_retention_purge(db=db, retention_hours=args.hours)

        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        logger.info(
            f"Retention purge job completed in {duration:.2f}s: "
            f"Status={result.get('status')}, "
            f"Purged={result.get('purged_count')}/{result.get('total_eligible')}, "
            f"Failed={result.get('failed_count')}"
        )
        if result.get("failed_count", 0) > 0:
            sys.exit(1)
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error during retention purge job: {e}", exc_info=True)
        sys.exit(2)


if __name__ == "__main__":
    main()
