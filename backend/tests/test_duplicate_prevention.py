import uuid
from fastapi.testclient import TestClient


def test_scenario_10_submit_tapped_twice_creates_only_one(client: TestClient, staff_headers: dict):
    """
    Scenario 10: Submit button tapped twice. Only one feedback created.
    """
    same_client_uuid = str(uuid.uuid4())
    payload = {
        "client_uuid": same_client_uuid,
        "uhid": "000555123",
        "patient_name": "Suresh Patel",
        "department": "F&B",
        "location": "Room 204",
    }

    # First tap
    res1 = client.post("/api/v1/feedback", json=payload, headers=staff_headers)
    assert res1.status_code == 201
    data1 = res1.json()
    first_id = data1["id"]
    first_fb_id = data1["feedback_id"]

    # Second tap (e.g. double-tap or offline retry with same client_uuid)
    res2 = client.post("/api/v1/feedback", json=payload, headers=staff_headers)
    assert res2.status_code in [200, 201]
    data2 = res2.json()
    second_id = data2["id"]
    second_fb_id = data2["feedback_id"]

    # Assert that identical record is returned, no duplicate created
    assert first_id == second_id
    assert first_fb_id == second_fb_id
