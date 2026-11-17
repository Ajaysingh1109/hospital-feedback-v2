import argparse
import os
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path


def backup_database(db_path: str, backup_dir: str):
    p = Path(db_path).resolve()
    if not p.exists():
        print(f"Error: Database file '{db_path}' does not exist.")
        sys.exit(1)

    b_dir = Path(backup_dir).resolve()
    b_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = b_dir / f"hospital_feedback_backup_{timestamp}.db"

    # Use SQLite online backup API to ensure ACID consistency without locks
    src_conn = sqlite3.connect(str(p))
    dst_conn = sqlite3.connect(str(backup_file))
    with dst_conn:
        src_conn.backup(dst_conn)
    dst_conn.close()
    src_conn.close()

    print(f"Backup created successfully: {backup_file}")
    print(f"Backup size: {backup_file.stat().st_size} bytes")


def restore_database(backup_file: str, target_db_path: str, confirm: bool = False):
    b_path = Path(backup_file).resolve()
    if not b_path.exists():
        print(f"Error: Backup file '{backup_file}' does not exist.")
        sys.exit(1)

    t_path = Path(target_db_path).resolve()

    if not confirm:
        res = input(f"Are you sure you want to restore {b_path.name} to {t_path}? This will overwrite existing data! (y/N): ")
        if res.strip().lower() != "y":
            print("Restore cancelled.")
            sys.exit(0)

    # Make pre-restore safety copy if target exists
    if t_path.exists():
        safety_copy = t_path.parent / f"{t_path.name}.pre_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        shutil.copy2(t_path, safety_copy)
        print(f"Created safety pre-restore backup at: {safety_copy}")

    shutil.copy2(b_path, t_path)
    print(f"Database successfully restored from: {b_path}")


def main():
    parser = argparse.ArgumentParser(description="Hospital Feedback System Database Backup & Restore Tool")
    subparsers = parser.add_subparsers(dest="action", required=True)

    backup_parser = subparsers.add_parser("backup", help="Create database backup")
    backup_parser.add_argument("--db", default="./hospital-feedback/backend/data/hospital_feedback.db", help="Path to database")
    backup_parser.add_argument("--out", default="./hospital-feedback/backend/data/backups", help="Backup output directory")

    restore_parser = subparsers.add_parser("restore", help="Restore database from backup")
    restore_parser.add_argument("--file", required=True, help="Path to backup file")
    restore_parser.add_argument("--target", default="./hospital-feedback/backend/data/hospital_feedback.db", help="Target database path")
    restore_parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt")

    args = parser.parse_args()

    if args.action == "backup":
        backup_database(args.db, args.out)
    elif args.action == "restore":
        restore_database(args.file, args.target, args.yes)


if __name__ == "__main__":
    main()
