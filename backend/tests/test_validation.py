import uuid
from fastapi.testclient import TestClient


def test_scenario_5_uhid_missing_blocks_submission(client: TestClient, staff_headers: dict):
    """
    Scenario 5: UHID missing -> Submission MUST be blocked.
    """
    payload = {
        "client_uuid": str(uuid.uuid4()),
        "uhid": "",  # Missing UHID
        "patient_name": "Ramesh Kumar",
        "department": "Nursing",
    }
    response = client.post("/api/v1/feedback", json=payload, headers=staff_headers)
    assert response.status_code == 422
    err_detail = str(response.json())
    assert "UHID is required" in err_detail


def test_scenario_6_patient_name_missing_blocks_submission(client: TestClient, staff_headers: dict):
    """
    Scenario 6: Patient name missing -> Submission MUST be blocked.
    """
    payload = {
        "client_uuid": str(uuid.uuid4()),
        "uhid": "000123456",
        "patient_name": "   ",  # Blank Patient Name
        "department": "Clinical",
    }
    response = client.post("/api/v1/feedback", json=payload, headers=staff_headers)
    assert response.status_code == 422
    err_detail = str(response.json())
    assert "Patient Name is required" in err_detail


def test_scenario_7_department_missing_blocks_submission(client: TestClient, staff_headers: dict):
    """
    Scenario 7: Department missing -> Submission MUST be blocked.
    """
    payload = {
        "client_uuid": str(uuid.uuid4()),
        "uhid": "000123456",
        "patient_name": "Ramesh Kumar",
        "department": "",  # Missing Department
    }
    response = client.post("/api/v1/feedback", json=payload, headers=staff_headers)
    assert response.status_code == 422
    err_detail = str(response.json())
    assert "Department is required" in err_detail


def test_valid_submission_succeeds(client: TestClient, staff_headers: dict):
    payload = {
        "client_uuid": str(uuid.uuid4()),
        "uhid": "000987654",
        "patient_name": "Anita Verma",
        "department": "Nursing",
        "location": "Ward 4A, Bed 12",
        "consultant": "Dr. Sandeep Sharma",
        "scheme": "Ayushman Bharat (PM-JAY)",
    }
    response = client.post("/api/v1/feedback", json=payload, headers=staff_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["uhid"] == "000987654"
    assert data["patient_name"] == "Anita Verma"
    assert data["department"] == "Nursing"
    assert data["hod_name"] == "Reshmi Ma'am"
    assert data["feedback_id"].startswith("FB-")
