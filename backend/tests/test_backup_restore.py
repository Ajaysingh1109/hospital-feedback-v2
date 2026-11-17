import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

# Add scripts directory to path to test backup_restore
scripts_dir = Path(__file__).parent.parent.parent / "scripts"
sys.path.insert(0, str(scripts_dir))

from backup_restore import backup_database, restore_database


def test_backup_and_disaster_recovery_workflow():
    """
    Section 10: Automated test verifying that backup and restore procedures
    preserve 100% of hospital feedback data without corruption.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        db_path = tmp_path / "hospital_test.db"
        backup_dir = tmp_path / "backups"

        # 1. Create a test SQLite database with sample data
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE feedback (id TEXT PRIMARY KEY, uhid TEXT, patient_name TEXT);")
        cursor.execute("INSERT INTO feedback VALUES ('FB-001', '000123456', 'Patient Alpha');")
        cursor.execute("INSERT INTO feedback VALUES ('FB-002', '000789012', 'Patient Beta');")
        conn.commit()
        conn.close()

        # 2. Perform backup
        backup_database(str(db_path), str(backup_dir))

        # Check backup created
        backup_files = list(backup_dir.glob("hospital_feedback_backup_*.db"))
        assert len(backup_files) == 1, "Backup file was not created"
        backup_file = backup_files[0]
        assert backup_file.stat().st_size > 0

        # 3. Simulate disaster: overwrite or delete database
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("DELETE FROM feedback;")
        conn.commit()
        # Verify disaster: 0 rows
        count = cursor.execute("SELECT count(*) FROM feedback;").fetchone()[0]
        assert count == 0
        conn.close()

        # 4. Perform disaster recovery restore
        restore_database(str(backup_file), str(db_path), confirm=True)

        # 5. Verify restored data
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        rows = cursor.execute("SELECT id, uhid, patient_name FROM feedback ORDER BY id;").fetchall()
        conn.close()

        assert len(rows) == 2, "Disaster recovery failed to restore all rows"
        assert rows[0] == ("FB-001", "000123456", "Patient Alpha")
        assert rows[1] == ("FB-002", "000789012", "Patient Beta")
        print("Disaster recovery backup and restore verified successfully.")
