import os

# Clearly fake test-only credentials (Never real production credentials)
TEST_MASTER_USERNAME = "test_master@local"
TEST_MASTER_PASSWORD = "TestMasterPassword!123"
TEST_FEEDBACK_USERNAME = "test_staff@local"
TEST_FEEDBACK_PASSWORD = "TestStaffPassword!123"

os.environ["MASTER_USERNAME"] = TEST_MASTER_USERNAME
os.environ["MASTER_PASSWORD"] = TEST_MASTER_PASSWORD
os.environ["FEEDBACK_USER_USERNAME"] = TEST_FEEDBACK_USERNAME
os.environ["FEEDBACK_USER_PASSWORD"] = TEST_FEEDBACK_PASSWORD
os.environ["SECRET_KEY"] = "test-secret-key-32-chars-long-for-pytest-only"
os.environ["CRON_SECRET"] = "test-cron-secret-for-pytest"
os.environ["AI_PROVIDER"] = "mock"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.core.security import create_access_token
from app.db.database import Base, get_db
from app.main import app
from app.models import RoleEnum, User
from app.seed import seed_database

# Use in-memory SQLite for isolated test runs
TEST_DATABASE_URL = "sqlite:///:memory:"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    Base.metadata.create_all(bind=test_engine)
    db = TestingSessionLocal()
    seed_database(db=db)
    yield
    db.close()
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def db_session():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.rollback()
        db.close()


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def admin_headers(db_session):
    admin = db_session.query(User).filter(User.role.in_([RoleEnum.ADMIN, RoleEnum.MASTER])).first()
    token = create_access_token(
        subject=admin.id,
        role=admin.role.value,
        extra_claims={"username": admin.username, "display_name": admin.display_name},
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def staff_headers(db_session):
    staff = db_session.query(User).filter(User.role == RoleEnum.STAFF).first()
    if not staff:
        from app.core.security import hash_password
        staff = User(
            username="nurse_fixture",
            display_name="Fixture Staff Nurse",
            password_hash=hash_password("StaffNurse@2026"),
            role=RoleEnum.STAFF,
            is_active=True,
        )
        db_session.add(staff)
        db_session.commit()
        db_session.refresh(staff)

    token = create_access_token(
        subject=staff.id,
        role=staff.role.value,
        extra_claims={"username": staff.username, "display_name": staff.display_name},
    )
    return {"Authorization": f"Bearer {token}"}
