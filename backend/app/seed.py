import logging
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .core.config import get_settings
from .core.security import hash_password
from .db.database import Base, SessionLocal, engine
from .models import (
    Consultant,
    Department,
    DepartmentSubcategory,
    Feedback,
    FeedbackCorrection,
    HODMapping,
    RoleEnum,
    Scheme,
    SystemSetting,
    User,
)
from .services.hod_service import STANDARD_HOD_BY_DEPT

logger = logging.getLogger(__name__)
settings = get_settings()


INITIAL_DEPARTMENTS = {
    "Clinical": [
        "Doctor rounds",
        "Treatment concern",
        "Diagnosis explanation",
        "Consultant availability",
        "Procedure delay",
    ],
    "Nursing": [
        "Delay in response",
        "Call bell response",
        "Staff behavior",
        "Medication timing",
        "IV / Infusion care",
    ],
    "Pharmacy": [
        "Medicine availability",
        "Dispensing delay",
        "Billing at pharmacy",
        "Prescription clarification",
    ],
    "Maintenance": [
        "Air conditioning / AC",
        "Plumbing & water supply",
        "Electrical / Lights",
        "Bed controls",
    ],
    "F&B": [
        "Food temperature",
        "Salt & seasoning",
        "Dietary requirement",
        "Delivery delay",
        "Hygiene",
    ],
    "Housekeeping": [
        "Room cleanliness",
        "Bathroom hygiene",
        "Linen & bedsheet change",
        "Waste disposal",
    ],
    "Operations": [
        "Admission delay",
        "Discharge clearance delay",
        "Porter & wheelchair service",
        "Room transfer",
    ],
    "Billing": [
        "TPA / Insurance approval delay",
        "Final bill settlement",
        "Payment receipt",
        "Billing transparency",
    ],
    "IT": [
        "Patient portal & app",
        "Hospital Wi-Fi",
        "Digital registration",
        "Room TV & entertainment",
    ],
    "Security": [
        "Visitor pass control",
        "Parking management",
        "Staff behavior",
        "Campus safety",
    ],
    "Other": [
        "General feedback",
        "Unclassified",
    ],
}

INITIAL_SCHEMES = [
    "Ayushman Bharat (PM-JAY)",
    "CGHS",
    "ECHS",
    "TPA / Private Insurance",
    "Corporate Cashless",
    "Direct Cash / Self Pay",
]

INITIAL_CONSULTANTS = [
    ("Dr. Sandeep Sharma", "Clinical"),
    ("Dr. Ananya Ray", "Clinical"),
    ("Dr. Vikram Malhotra", "Clinical"),
    ("Dr. Sunita Deshmukh", "Clinical"),
    ("Dr. Arvind Menon", "Clinical"),
]


def cleanup_legacy_users(db: Session, master_id: str):
    """
    Safely removes legacy seeded users ('admin', 'staff1', 'staff2', 'staff3')
    while preserving all feedback records, corrections, and audit logs.
    """
    legacy_usernames = ["admin", "staff1", "staff2", "staff3"]
    legacy_users = db.scalars(
        select(User).where(func.lower(User.username).in_(legacy_usernames))
    ).all()

    if not legacy_users:
        return

    legacy_ids = [u.id for u in legacy_users]

    # Re-link existing feedback attribution to master_id to preserve relational integrity
    # without deleting historical records or altering staff_name text attribution
    db.query(Feedback).filter(Feedback.staff_id.in_(legacy_ids)).update(
        {Feedback.staff_id: master_id}, synchronize_session=False
    )
    db.query(FeedbackCorrection).filter(FeedbackCorrection.corrected_by_id.in_(legacy_ids)).update(
        {FeedbackCorrection.corrected_by_id: master_id}, synchronize_session=False
    )

    for user in legacy_users:
        logger.info(f"Safely removing legacy seeded user: {user.username}")
        db.delete(user)
    db.commit()


def init_master_account(db: Session) -> User:
    """
    Ensures a single initial MASTER account exists.
    Created with forced password change required on first login.
    NO staff users are seeded automatically.
    """
    clean_master_username = settings.MASTER_USERNAME.strip()

    master_user = db.scalar(
        select(User).where(func.lower(User.username) == clean_master_username.lower())
    )

    if not master_user:
        # Check if an admin or master account already exists
        existing_admin = db.scalar(
            select(User).where(User.role.in_([RoleEnum.ADMIN, RoleEnum.MASTER]))
        )
        if not existing_admin:
            master_user = User(
                username=clean_master_username,
                display_name=settings.MASTER_DISPLAY_NAME,
                password_hash=hash_password(settings.MASTER_PASSWORD),
                role=RoleEnum.ADMIN,
                is_active=True,
                must_change_password=True,
            )
            db.add(master_user)
            db.commit()
            db.refresh(master_user)
            logger.info("Master Administrator account initialized.")
        else:
            master_user = existing_admin

    return master_user


def seed_database(db: Session = None):
    close_at_end = False
    if db is None:
        Base.metadata.create_all(bind=engine)
        db = SessionLocal()
        close_at_end = True

    try:
        # 1. Initialize Master Account (First-run server-side configuration)
        master_user = init_master_account(db)

        # 2. Safely remove legacy demo/test accounts while preserving feedback and audit data
        cleanup_legacy_users(db, master_id=master_user.id)

        # 3. Seed Departments & Subcategories
        for dept_name, subcats in INITIAL_DEPARTMENTS.items():
            dept = db.scalar(select(Department).where(Department.name == dept_name))
            if not dept:
                dept = Department(name=dept_name, is_active=True)
                db.add(dept)
                db.flush()

            for sc_name in subcats:
                sc = db.scalar(
                    select(DepartmentSubcategory).where(
                        DepartmentSubcategory.department_id == dept.id,
                        DepartmentSubcategory.name == sc_name,
                    )
                )
                if not sc:
                    sc = DepartmentSubcategory(
                        department_id=dept.id,
                        name=sc_name,
                        is_active=True,
                    )
                    db.add(sc)

        # 4. Seed Canonical HOD Mappings
        for dept_name, hod_name in STANDARD_HOD_BY_DEPT.items():
            mapping = db.scalar(select(HODMapping).where(HODMapping.department_name == dept_name))
            if not mapping:
                mapping = HODMapping(
                    department_name=dept_name,
                    hod_name=hod_name,
                    is_active=True,
                )
                db.add(mapping)

        # 5. Seed Schemes
        for s_name in INITIAL_SCHEMES:
            scheme = db.scalar(select(Scheme).where(Scheme.name == s_name))
            if not scheme:
                db.add(Scheme(name=s_name, is_active=True))

        # 6. Seed Consultants
        for c_name, c_dept in INITIAL_CONSULTANTS:
            consultant = db.scalar(select(Consultant).where(Consultant.name == c_name))
            if not consultant:
                db.add(Consultant(name=c_name, department=c_dept, is_active=True))

        # 7. Seed System Settings
        default_settings = [
            ("consent_notice_text", settings.CONSENT_NOTICE_TEXT, "Patient Recording Consent Notice"),
            ("audio_retention_policy", settings.AUDIO_RETENTION_POLICY, "Audio retention policy (keep/delete_after_processing)"),
            ("ai_provider", settings.AI_PROVIDER, "Active AI Provider (gemini/openai/mock)"),
        ]
        for key, val, desc in default_settings:
            setting = db.scalar(select(SystemSetting).where(SystemSetting.key == key))
            if not setting:
                db.add(SystemSetting(key=key, value=val, description=desc))

        db.commit()
        logger.info("Database seeding completed successfully.")
    except Exception as e:
        db.rollback()
        logger.error(f"Error seeding database: {e}")
        raise
    finally:
        if close_at_end:
            db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    seed_database()
