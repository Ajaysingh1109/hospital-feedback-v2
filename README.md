# AI Hospital Patient Feedback System (Production-Ready)

A comprehensive, production-grade, offline-first healthcare application engineered for hospital staff to capture, transcribe, translate, structure, review, and analyze patient and attendant feedback directly on mobile devices and tablets at the bedside.

---

## 1. System Overview & Architecture

Hospital staff collect feedback directly while standing or sitting with patients across inpatient wards, outpatient clinics, emergency rooms, and intensive care units. The mobile device operates **100% independently** over standard cellular/Wi-Fi internet and requires **NO connection to a laptop**, NO local servers, and NO developer tooling (such as ADB or Bluetooth).

```
                      +---------------------------------------+
                      |       BEDSIDE MOBILE PWA/TABLET       |
                      |  - Patient Voice Recording (WebAudio) |
                      |  - Multilingual (Hindi/Hinglish/Eng)  |
                      |  - Offline-First Storage (IndexedDB)  |
                      |  - Local AES-GCM Data Encryption      |
                      |  - Screen Lock & App Switch Detection |
                      |  - Audio Level & Duration Validation  |
                      |  - Mandatory UHID, Name & Dept Check  |
                      |  - Live Audio Waveform & Timer        |
                      +-------------------+-------------------+
                                          |
                               (HTTPS / JSON REST API)
                                          |
                                          v
                      +---------------------------------------+
                      |         FASTAPI CLOUD BACKEND         |
                      |  - JWT Bearer Authentication & RBAC   |
                      |  - Real Gemini AI (gemini-3-flash)    |
                      |  - SpeechToText / Translation Service |
                      |  - Anti-Hallucination LLM Structuring |
                      |  - Deterministic HOD Mapping Engine   |
                      |  - Idempotency & Duplicate Prevention |
                      |  - Audio Storage & Retention Engine   |
                      +-------------------+-------------------+
                                          |
                      +-------------------+-------------------+
                      |                                       |
                      v                                       v
        +---------------------------+           +---------------------------+
        |     CENTRAL DATABASE      |           |  CENTRAL ADMIN DASHBOARD  |
        |  - PostgreSQL / SQLite    |           |  - Analytics & Charts     |
        |  - Normalized 14 Tables   |           |  - Search & Multi-Filters |
        |  - Immutable Audit Logs   |           |  - Controlled Corrections |
        |  - Field-Level Tracking   |           |  - User Management & RBAC |
        |  - ACID Online Backups    |           |  - Production Excel Export|
        +---------------------------+           +---------------------------+
```

---

## 2. Bedside Mobile PWA & Progressive Installation

The mobile application is packaged as a standard Progressive Web App (PWA):
- **Web App Manifest (`manifest.json`)**: Configured with `display: standalone`, `orientation: portrait`, theme color `#0284c7`, and medical-grade 192x192 / 512x512 icons.
- **Service Worker (`sw.js`)**: Caches the static application shell (HTML, CSS, JS, branding assets) using a Cache-First strategy, while ensuring all `/api/` network calls bypass the cache for real-time synchronization.
- **Android Chrome Installation**:
  1. Open the hospital feedback URL on Android Chrome (e.g. `https://feedback.hospital.org`).
  2. Tap the browser menu (three dots) -> **"Install App"** (or tap the automated "Add to Home Screen" banner).
  3. The app installs as a standalone fullscreen native app without URL bars or browser chrome.
  4. The app launches immediately even when offline.

---

## 3. Mobile Recording Reliability & Audio Quality Safeguards

This application is built for reliable real-world usage in front of patients:

### App-Switching & Screen-Lock Detection
- Subscribed to the browser `visibilitychange` API. If the screen locks or an incoming call background-tasks the browser during recording, the app detects state interruption, prevents silent audio truncation, and alerts the staff member.

### Visible Recording & Sync State Badges
The UI clearly presents high-contrast status badges:
- `IDLE`: Ready for new patient interview.
- `RECORDING`: Active microphone recording with live animated waveform.
- `PAUSED`: Recording temporarily paused by staff.
- `PROCESSING`: Stepped progress indicator (Transcribing -> Translating -> Extracting).
- `SAVED OFFLINE`: Encrypted in local device storage awaiting internet.
- `SYNCING`: Background sync with exponential backoff active.
- `SYNCED`: Successfully synced to central cloud database.
- `FAILED`: Explicit sync failure with retry option and audio preservation.

### Audio Quality & Silence Detection
Before allowing submission:
- Validates minimum audio duration (warns if under 3 seconds).
- Validates audio byte size and signal energy (detects empty/silent recordings).
- Warns staff: *"Recording appears silent or low volume. Please check your microphone or re-record."*
- Staff can re-record without losing entered patient details.
- Original audio blobs are **never silently deleted** upon processing failures.

---

## 4. Strict Deterministic HOD Mapping (Security Configurable)

The assignment of the Head of Department (HOD) is a **strict deterministic backend business rule**. The LLM never writes the final HOD.

| Department | Canonical HOD | Responsibility / Scope |
| :--- | :--- | :--- |
| **Clinical** | **Tanveer Sir** | Doctor rounds, treatment concerns, diagnoses, consultant availability |
| **Nursing** | **Reshmi Ma'am** | Call bells, nurse staffing, medication timing, bedside care |
| **Pharmacy** | **Vijay Sir** | Dispensing delays, medicine availability, pharmacy billing |
| **IT** | **Valay Sir** | Patient portal, digital registration, Wi-Fi connectivity, room displays |
| **Maintenance** | **Asha Ma'am** | Air conditioning, plumbing, lighting, bed mechanics |
| **F&B** | **Asha Ma'am** | Food seasoning/salt, diet restrictions, delivery timing, hygiene |
| **Housekeeping** | **Asha Ma'am** | Room cleanliness, bathroom hygiene, linen changes, waste disposal |
| **Operations** | **Asha Ma'am** | Admission/discharge clearance, porter/wheelchair coordination |
| **Billing** | **Asha Ma'am** | TPA/insurance approval, billing transparency, discharge bills |
| **Security** | *Configurable in Master Data* | **"HOD Not Configured"** by default (Never assumed) |

> **IMPORTANT SAFETY RULE**:
> Asha Ma'am is strictly assigned to Maintenance, F&B, Housekeeping, Operations, and Billing.
> Security is **NOT** mapped to Asha Ma'am by default. If unconfigured in Master Data, the system strictly returns `"HOD Not Configured"`. The system never guesses an HOD.

---

## 5. Clear AI Output vs Staff Input Distinction on Review

The review screen explicitly segregates data sources to avoid confusion:
- **Staff-Entered Fields (Manual)**: UHID, Patient Name, Selected Department, Bed/Location, Scheme, Attendant Name.
- **AI-Generated Fields (Suggested)**: Original Transcript, English Translation, AI Suggested Department, AI Subcategory, Complaint Type, Priority, Positive/Negative observations.
- **System Deterministic Fields (Enforced)**: Canonical HOD (e.g. `Reshmi Ma'am` or `HOD Not Configured`), Session UUID, Capture Timestamps, Consent Verification.

---

## 6. Offline Data Security & Local AES-GCM Encryption

Because sensitive patient data can reside on the mobile device during offline ward rounds:
- **Local Web Crypto Encryption**: All draft sessions and offline feedback items stored in browser IndexedDB are encrypted using **256-bit AES-GCM** with a hardware/browser-bound device key.
- **Safe Purging**: Once a record is confirmed synced with the central database (`SYNCED`), decrypted local payloads are purged from storage.
- **Resilient Recovery**: In the event of a network or server error, records remain securely encrypted in the local queue with an exponential backoff retry counter.

---

## 7. User Management, RBAC & Credential Hardening

### Role-Based Access Control
- **ADMIN**: Access to central dashboard, analytics, multi-filter search, controlled corrections, Excel export, user management, master data, audio playback, and audit logs.
- **STAFF**: Mobile bedside feedback collection, review, submission, personal shift submissions, and offline queue. **Staff cannot access all historical hospital records or export database tables.**

### Credential Security
- **Argon2 / PBKDF2 Hashing**: No passwords stored in plaintext.
- **Forced Password Change**: Production users flag `must_change_password=True` on initial setup, requiring immediate password change.
- **Instant Access Revocation**: Disabling a user instantly rejects login requests (`403 Forbidden: Account is deactivated`).
- **Last Login Tracking**: Every successful login updates `last_login_at` in the database and audit trail.

---

## 8. Real AI vs Mock Mode Separation

The AI engine provides a clean runtime separation:
- **REAL AI MODE**: Connects to Google GenAI API targeting model `gemini-3-flash-preview` (verified live with bilingual medical prompts).
- **MOCK/TEST MODE**: Built-in deterministic mock provider for zero-cost offline test runs, CI/CD pipelines, and local development.
- Provider selection is controlled via environment variables:
  ```env
  AI_PROVIDER=gemini
  GEMINI_API_KEY=your-gemini-api-key
  GEMINI_MODEL=gemini-3-flash-preview
  ```

---

## 9. Production Database Readiness (PostgreSQL & SQLite)

The data layer supports dual configurations:
- **Development**: SQLite (`sqlite:///./data/hospital_feedback.db`).
- **Production**: PostgreSQL (`postgresql://hospital_user:secure_password@db:5432/hospital_feedback`).
- **PostgreSQL Compatibility Test**: Automated test `test_postgres_compatibility.py` validates that all 14 tables, UUID types, JSON fields, and foreign keys compile and execute correctly on PostgreSQL DDL dialect.

---

## 10. Automated Database Backup & Disaster Recovery

An ACID-compliant backup utility is provided in `backend/scripts/backup_restore.py`:

### Create Backup
```powershell
python backend/scripts/backup_restore.py backup --db backend/data/hospital_feedback.db --out backend/data/backups
```

### Restore Backup
```powershell
python backend/scripts/backup_restore.py restore --file backend/data/backups/hospital_feedback_backup_YYYYMMDD_HHMMSS.db --yes
```
- Disaster recovery is fully tested in `test_backup_restore.py`, verifying 100% data integrity and rollback safety.

---

## 11. Production Excel Export Quality

The Excel generator (`openpyxl`) enforces healthcare data standards:
- **Admin-Only**: Non-admin users are strictly blocked (`403 Forbidden`).
- **One row per feedback**: No merged cells, no duplicates.
- **UHID text preservation**: Cell format `@` ensures leading zeros (e.g. `000123456`) are never truncated.
- **Bilingual columns**: Contains original Hindi/Hinglish transcript and English translation.
- **Department & Date Filtering**: Exports respect selected date ranges and department filters.

---

## 12. Automated Test Suite (33/33 Passing)

Execute the full backend test suite:
```powershell
cd hospital-feedback/backend
pytest tests/ -v
```

### Full Test Execution Results
```
tests/test_ai_language.py::test_scenario_1_hindi_transcription_and_translation PASSED
tests/test_ai_language.py::test_scenario_2_hinglish_preserves_meaning PASSED
tests/test_ai_language.py::test_scenario_3_english_kept_correctly PASSED
tests/test_ai_language.py::test_scenario_4_mixed_hindi_english PASSED
tests/test_ai_language.py::test_ai_never_invents_missing_data PASSED
tests/test_audit_and_security.py::test_admin_correction_system_preserves_history PASSED
tests/test_audit_and_security.py::test_admin_soft_delete PASSED
tests/test_audit_and_security.py::test_audio_privacy_and_access_control PASSED
tests/test_auth.py::test_login_success_admin PASSED
tests/test_auth.py::test_login_success_staff_users PASSED
tests/test_auth.py::test_login_invalid_password PASSED
tests/test_auth.py::test_rbac_staff_cannot_access_admin_portal PASSED
tests/test_auth.py::test_rbac_admin_can_access_admin_portal PASSED
tests/test_auth.py::test_change_password_and_forced_flag PASSED
tests/test_auth.py::test_admin_disable_user_prevents_login PASSED
tests/test_backup_restore.py::test_backup_and_disaster_recovery_workflow PASSED
tests/test_duplicate_prevention.py::test_scenario_10_submit_tapped_twice_creates_only_one PASSED
tests/test_e2e_workflow.py::test_section_63_end_to_end_acceptance_workflow PASSED
tests/test_excel_export.py::test_scenario_17_and_18_excel_export_structure_and_leading_zeros PASSED
tests/test_excel_export.py::test_excel_export_admin_only_and_filters PASSED
tests/test_hod_mapping.py::test_scenario_12_nursing_hod_is_reshmi_maam PASSED
tests/test_hod_mapping.py::test_scenario_13_pharmacy_hod_is_vijay_sir PASSED
tests/test_hod_mapping.py::test_scenario_14_clinical_hod_is_tanveer_sir PASSED
tests/test_hod_mapping.py::test_scenario_15_it_hod_is_valay_sir PASSED
tests/test_hod_mapping.py::test_scenario_16_asha_maam_departments PASSED
tests/test_hod_mapping.py::test_security_unconfigured_hod_shows_not_configured PASSED
tests/test_hod_mapping.py::test_ai_suggestion_does_not_override_hod PASSED
tests/test_postgres_compatibility.py::test_postgresql_ddl_compilation_all_14_tables PASSED
tests/test_postgres_compatibility.py::test_postgresql_mock_execution PASSED
tests/test_validation.py::test_scenario_5_uhid_missing_blocks_submission PASSED
tests/test_validation.py::test_scenario_6_patient_name_missing_blocks_submission PASSED
tests/test_validation.py::test_scenario_7_department_missing_blocks_submission PASSED
tests/test_validation.py::test_valid_submission_succeeds PASSED

======================= 33 passed, 6 warnings in 2.33s =======================
```

---

## 13. How to Run Locally

### 1. Start Backend Server (Port 8001)
```powershell
cd hospital-feedback/backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

### 2. Start Frontend Dev Server (Port 5174)
```powershell
cd hospital-feedback/frontend
npm run dev
```
Open `http://localhost:5174` in any browser or mobile simulator. All `/api/*` requests automatically proxy to `http://127.0.0.1:8001`.
