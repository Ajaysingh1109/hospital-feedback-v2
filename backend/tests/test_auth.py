from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy import func, select
from app.models import User, RoleEnum
from app.core.config import get_settings

settings = get_settings()


def test_master_login_works(client: TestClient):
    """
    Test Master account authentication with canonical credentials:
    Username: Apollo@123
    Password: 2321@Apollo
    """
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "Apollo@123", "password": "2321@Apollo"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["role"] in ["ADMIN", "MASTER"]
    assert data["username"].lower() == "apollo@123"
    # First login requires password change
    assert data["must_change_password"] is True


def test_invalid_master_password_rejected(client: TestClient):
    """
    Invalid password for master account must be rejected with 401.
    """
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "Apollo@123", "password": "WrongMasterPassword@123"},
    )
    assert response.status_code == 401
    assert "Invalid username or password" in response.json()["detail"]


def test_no_default_demo_accounts_exist_after_fresh_initialization(client: TestClient, admin_headers: dict):
    """
    Ensure legacy demo accounts (admin, staff1, staff2, staff3) do NOT exist.
    Only Master/Admin created accounts exist.
    """
    response = client.get("/api/v1/admin/users", headers=admin_headers)
    assert response.status_code == 200
    users = response.json()
    usernames = [u["username"].lower() for u in users]

    assert "admin" not in usernames
    assert "staff1" not in usernames
    assert "staff2" not in usernames
    assert "staff3" not in usernames
    assert "apollo@123" in usernames


def test_master_can_create_staff_and_new_staff_can_login(client: TestClient, admin_headers: dict):
    """
    Master creates a new staff user with username, password, display_name, role.
    Then newly created staff successfully logs in.
    """
    staff_username = "nurse_anita"
    staff_password = "AnitaPassword@2026"
    staff_name = "Anita Deshmukh (Senior Nurse)"

    # 1. Master creates staff account
    create_resp = client.post(
        "/api/v1/admin/users",
        headers=admin_headers,
        json={
            "username": staff_username,
            "password": staff_password,
            "display_name": staff_name,
            "role": "STAFF",
        },
    )
    assert create_resp.status_code == 201
    created_user = create_resp.json()
    assert created_user["username"] == staff_username
    assert created_user["display_name"] == staff_name
    assert created_user["role"] == "STAFF"
    assert created_user["is_active"] is True
    staff_id = created_user["id"]

    # 2. Newly created staff can login
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"username": staff_username, "password": staff_password},
    )
    assert login_resp.status_code == 200
    login_data = login_resp.json()
    assert login_data["role"] == "STAFF"
    assert login_data["username"] == staff_username
    staff_token = login_data["access_token"]
    staff_auth_headers = {"Authorization": f"Bearer {staff_token}"}

    # 3. Staff cannot access master/admin-only APIs
    user_mgmt_resp = client.get("/api/v1/admin/users", headers=staff_auth_headers)
    assert user_mgmt_resp.status_code == 403

    export_resp = client.get("/api/v1/admin/export-excel", headers=staff_auth_headers)
    assert export_resp.status_code == 403

    # 4. Master deactivates staff account
    deactivate_resp = client.patch(
        f"/api/v1/admin/users/{staff_id}",
        headers=admin_headers,
        json={"is_active": False},
    )
    assert deactivate_resp.status_code == 200
    assert deactivate_resp.json()["is_active"] is False

    # 5. Deactivated staff cannot login
    deactivated_login = client.post(
        "/api/v1/auth/login",
        json={"username": staff_username, "password": staff_password},
    )
    assert deactivated_login.status_code == 403
    assert "deactivated" in deactivated_login.json()["detail"].lower()


def test_password_change_works(client: TestClient, admin_headers: dict):
    """
    Test user password change flow via /api/v1/auth/change-password.
    Old password rejected, new password authenticated, must_change_password cleared.
    """
    # Create test user
    create_resp = client.post(
        "/api/v1/admin/users",
        headers=admin_headers,
        json={
            "username": "pwdteststaff",
            "password": "InitialStaffPass@2026",
            "display_name": "Password Test Staff",
            "role": "STAFF",
        },
    )
    assert create_resp.status_code == 201

    # Login to obtain user token
    login_init = client.post(
        "/api/v1/auth/login",
        json={"username": "pwdteststaff", "password": "InitialStaffPass@2026"},
    )
    assert login_init.status_code == 200
    user_token = login_init.json()["access_token"]
    user_headers = {"Authorization": f"Bearer {user_token}"}

    # Change password
    change_resp = client.post(
        "/api/v1/auth/change-password",
        headers=user_headers,
        json={
            "old_password": "InitialStaffPass@2026",
            "new_password": "NewUpdatedPass@2027!",
        },
    )
    assert change_resp.status_code == 200
    assert "message" in change_resp.json()

    # Old password no longer works
    login_old = client.post(
        "/api/v1/auth/login",
        json={"username": "pwdteststaff", "password": "InitialStaffPass@2026"},
    )
    assert login_old.status_code == 401

    # New password succeeds and must_change_password is False
    login_new = client.post(
        "/api/v1/auth/login",
        json={"username": "pwdteststaff", "password": "NewUpdatedPass@2027!"},
    )
    assert login_new.status_code == 200
    assert login_new.json()["must_change_password"] is False


def test_staff_isolation_and_master_oversight(client: TestClient, admin_headers: dict):
    """
    Case 8 & 9:
    Staff isolation: Staff can only see their own feedback submissions via /api/v1/feedback/my.
    Master oversight: Master sees full hospital feedback submissions via /api/v1/admin/feedback.
    """
    import uuid

    # 1. Create Staff 1
    client.post(
        "/api/v1/admin/users",
        headers=admin_headers,
        json={"username": "staff_alpha", "password": "PassAlpha@123", "display_name": "Staff Alpha", "role": "STAFF"},
    )
    t1 = client.post("/api/v1/auth/login", json={"username": "staff_alpha", "password": "PassAlpha@123"}).json()["access_token"]
    h1 = {"Authorization": f"Bearer {t1}"}

    # 2. Create Staff 2
    client.post(
        "/api/v1/admin/users",
        headers=admin_headers,
        json={"username": "staff_beta", "password": "PassBeta@123", "display_name": "Staff Beta", "role": "STAFF"},
    )
    t2 = client.post("/api/v1/auth/login", json={"username": "staff_beta", "password": "PassBeta@123"}).json()["access_token"]
    h2 = {"Authorization": f"Bearer {t2}"}

    # 3. Staff 1 submits Feedback A
    res_a = client.post(
        "/api/v1/feedback",
        headers=h1,
        json={
            "client_uuid": str(uuid.uuid4()),
            "uhid": "00111111",
            "patient_name": "Patient Alpha",
            "department": "Nursing",
            "complaint": "Call bell delay",
        },
    )
    assert res_a.status_code == 201
    fb_a_id = res_a.json()["feedback_id"]

    # 4. Staff 2 submits Feedback B
    res_b = client.post(
        "/api/v1/feedback",
        headers=h2,
        json={
            "client_uuid": str(uuid.uuid4()),
            "uhid": "00222222",
            "patient_name": "Patient Beta",
            "department": "Pharmacy",
            "complaint": "Dispensing delay",
        },
    )
    assert res_b.status_code == 201
    fb_b_id = res_b.json()["feedback_id"]

    # 5. Staff 1 checks /my submissions: must contain A, MUST NOT contain B
    my_a = client.get("/api/v1/feedback/my", headers=h1).json()
    my_a_ids = [x["feedback_id"] for x in my_a]
    assert fb_a_id in my_a_ids
    assert fb_b_id not in my_a_ids

    # 6. Staff 2 checks /my submissions: must contain B, MUST NOT contain A
    my_b = client.get("/api/v1/feedback/my", headers=h2).json()
    my_b_ids = [x["feedback_id"] for x in my_b]
    assert fb_b_id in my_b_ids
    assert fb_a_id not in my_b_ids

    # 7. Master checks /admin/feedback: must contain BOTH A and B
    admin_feedbacks = client.get("/api/v1/admin/feedback", headers=admin_headers).json()["items"]
    admin_ids = [x["feedback_id"] for x in admin_feedbacks]
    assert fb_a_id in admin_ids
    assert fb_b_id in admin_ids
