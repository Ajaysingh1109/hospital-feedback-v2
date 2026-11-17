import io
import uuid
import openpyxl
from fastapi.testclient import TestClient


def test_scenario_17_and_18_excel_export_structure_and_leading_zeros(
    client: TestClient, staff_headers: dict, admin_headers: dict
):
    """
    Scenario 17: Admin exports Excel. Exactly one row per feedback.
    Scenario 18: UHID contains leading zeros. Excel preserves them without scientific notation.
    """
    # Create 3 feedbacks with leading zeros in UHID
    uhids = ["000123456", "000078901", "012345678"]
    for i, uhid in enumerate(uhids):
        payload = {
            "client_uuid": str(uuid.uuid4()),
            "uhid": uhid,  # CRITICAL: leading zeros!
            "patient_name": f"Patient Number {i}",
            "department": "Pharmacy" if i == 0 else "Nursing",
            "complaint_summary": f"Test complaint summary {i}",
        }
        res = client.post("/api/v1/feedback", json=payload, headers=staff_headers)
        assert res.status_code == 201

    # Admin requests Excel Export
    export_res = client.get("/api/v1/admin/export-excel", headers=admin_headers)
    assert export_res.status_code == 200
    assert "application/vnd.openxmlformats" in export_res.headers["content-type"]

    # Read the returned Excel in memory
    wb = openpyxl.load_workbook(io.BytesIO(export_res.content))
    ws = wb.active
    assert ws.title == "Patient Feedback"

    # Check Header Row (English headers, row 1)
    header_cells = [cell.value for cell in ws[1]]
    expected_headers = [
        "Date",
        "Time",
        "UHID",
        "Patient Name",
        "Location",
        "Consultant",
        "Scheme",
        "Department",
        "HOD",
        "Complaint Type",
        "Complaint",
    ]
    assert header_cells == expected_headers, f"Headers mismatch: {header_cells} vs {expected_headers}"
    assert len(header_cells) == 11

    # Strictly NO original transcript, NO internal IDs, NO technical metadata
    assert "Feedback ID" not in header_cells
    assert "Original Transcript" not in header_cells
    assert "Recording Duration" not in header_cells
    assert "Submission Status" not in header_cells
    assert "Created At" not in header_cells
    assert "Staff Name" not in header_cells

    uhid_col_idx = header_cells.index("UHID") + 1

    # Find the rows corresponding to our inserted UHIDs
    found_uhids = []
    # Count non-header data rows
    data_rows = 0
    for row in range(2, ws.max_row + 1):
        cell_val = str(ws.cell(row=row, column=uhid_col_idx).value or "")
        if cell_val:
            data_rows += 1
            if cell_val in uhids:
                found_uhids.append(cell_val)
                # Ensure leading zero was NOT stripped (i.e. not "123456", but "000123456")
                assert cell_val.startswith("0")
                assert len(cell_val) == 9

    # Assert exactly one row per feedback
    assert len(found_uhids) == len(uhids)
    # Check freeze panes
    assert ws.freeze_panes == "A2"


def test_excel_export_admin_only_and_filters(client: TestClient, staff_headers: dict, admin_headers: dict):
    """
    Section 11: Verify that Excel export is ADMIN-only and department/date filters work.
    """
    # 1. Staff access MUST be blocked (403)
    staff_res = client.get("/api/v1/admin/export-excel", headers=staff_headers)
    assert staff_res.status_code == 403

    # 2. Filter by Pharmacy
    dept_res = client.get("/api/v1/admin/export-excel?department=Pharmacy", headers=admin_headers)
    assert dept_res.status_code == 200
    wb = openpyxl.load_workbook(io.BytesIO(dept_res.content))
    ws = wb.active
    header = [cell.value for cell in ws[1]]
    dept_idx = header.index("Department") + 1

    # Verify all exported rows belong to Pharmacy
    for row in range(2, ws.max_row + 1):
        cell_val = str(ws.cell(row=row, column=dept_idx).value or "")
        if cell_val:
            assert cell_val.lower() == "pharmacy"

