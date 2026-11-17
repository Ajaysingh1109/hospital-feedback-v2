import uuid
from fastapi.testclient import TestClient


def test_scenario_12_nursing_hod_is_reshmi_maam(client: TestClient, staff_headers: dict):
    """
    Scenario 12: Department = Nursing -> HOD MUST be Reshmi Ma'am.
    """
    payload = {
        "client_uuid": str(uuid.uuid4()),
        "uhid": "0001001",
        "patient_name": "Test Patient",
        "department": "Nursing",
    }
    response = client.post("/api/v1/feedback", json=payload, headers=staff_headers)
    assert response.status_code == 201
    assert response.json()["hod_name"] == "Reshmi Ma'am"


def test_scenario_13_pharmacy_hod_is_vijay_sir(client: TestClient, staff_headers: dict):
    """
    Scenario 13: Department = Pharmacy -> HOD MUST be Vijay Sir.
    """
    payload = {
        "client_uuid": str(uuid.uuid4()),
        "uhid": "0001002",
        "patient_name": "Test Patient",
        "department": "Pharmacy",
    }
    response = client.post("/api/v1/feedback", json=payload, headers=staff_headers)
    assert response.status_code == 201
    assert response.json()["hod_name"] == "Vijay Sir"


def test_scenario_14_clinical_hod_is_tanveer_sir(client: TestClient, staff_headers: dict):
    """
    Scenario 14: Department = Clinical -> HOD MUST be Tanveer Sir.
    """
    payload = {
        "client_uuid": str(uuid.uuid4()),
        "uhid": "0001003",
        "patient_name": "Test Patient",
        "department": "Clinical",
    }
    response = client.post("/api/v1/feedback", json=payload, headers=staff_headers)
    assert response.status_code == 201
    assert response.json()["hod_name"] == "Tanveer Sir"


def test_scenario_15_it_hod_is_valay_sir(client: TestClient, staff_headers: dict):
    """
    Scenario 15: Department = IT -> HOD MUST be Valay Sir.
    """
    payload = {
        "client_uuid": str(uuid.uuid4()),
        "uhid": "0001004",
        "patient_name": "Test Patient",
        "department": "IT",
    }
    response = client.post("/api/v1/feedback", json=payload, headers=staff_headers)
    assert response.status_code == 201
    assert response.json()["hod_name"] == "Valay Sir"


def test_scenario_16_asha_maam_departments(client: TestClient, staff_headers: dict):
    """
    Scenario 16: Department in Maintenance/F&B/Housekeeping/Operations/Billing -> HOD MUST be Asha Ma'am.
    """
    asha_departments = [
        "Maintenance",
        "F&B",
        "Housekeeping",
        "Operations",
        "Billing",
    ]
    for dept in asha_departments:
        payload = {
            "client_uuid": str(uuid.uuid4()),
            "uhid": f"000{dept[:3].upper()}",
            "patient_name": f"Patient for {dept}",
            "department": dept,
        }
        response = client.post("/api/v1/feedback", json=payload, headers=staff_headers)
        assert response.status_code == 201, f"Failed for department: {dept}"
        assert response.json()["hod_name"] == "Asha Ma'am", f"Expected Asha Ma'am for {dept}, got {response.json()['hod_name']}"


def test_security_unconfigured_hod_shows_not_configured(client: TestClient, staff_headers: dict, admin_headers: dict):
    """
    Point 1 & 6: Security must NOT be permanently assigned to Asha Ma'am.
    If unconfigured, it must show 'HOD Not Configured'.
    Admin must be able to configure it.
    """
    payload = {
        "client_uuid": str(uuid.uuid4()),
        "uhid": "000SEC01",
        "patient_name": "Security Test Patient",
        "department": "Security",
    }
    response = client.post("/api/v1/feedback", json=payload, headers=staff_headers)
    assert response.status_code == 201
    assert response.json()["hod_name"] == "HOD Not Configured"

    # Now Admin configures Security's HOD in Master Data
    mappings_res = client.get("/api/v1/admin/hod-mappings", headers=admin_headers)
    assert mappings_res.status_code == 200
    sec_mapping = next((m for m in mappings_res.json() if m["department_name"] == "Security"), None)

    if sec_mapping:
        update_res = client.put(
            f"/api/v1/admin/hod-mappings/{sec_mapping['id']}",
            json={"hod_name": "Col. Rathore", "is_active": True},
            headers=admin_headers,
        )
        assert update_res.status_code == 200

        # Next submission for Security should now resolve to Col. Rathore
        payload2 = {
            "client_uuid": str(uuid.uuid4()),
            "uhid": "000SEC02",
            "patient_name": "Security Test Patient 2",
            "department": "Security",
        }
        res2 = client.post("/api/v1/feedback", json=payload2, headers=staff_headers)
        assert res2.status_code == 201
        assert res2.json()["hod_name"] == "Col. Rathore"


def test_ai_suggestion_does_not_override_hod(client: TestClient, staff_headers: dict):
    """
    Even if AI suggests a different department or tries to provide HOD,
    the backend deterministic table determines final HOD.
    """
    payload = {
        "client_uuid": str(uuid.uuid4()),
        "uhid": "0009999",
        "patient_name": "Conflict Patient",
        "department": "Clinical",  # Staff selected Clinical
        "ai_suggested_department": "Nursing",  # AI suggested Nursing
    }
    response = client.post("/api/v1/feedback", json=payload, headers=staff_headers)
    assert response.status_code == 201
    # For Clinical, HOD MUST be Tanveer Sir
    assert response.json()["hod_name"] == "Tanveer Sir"
