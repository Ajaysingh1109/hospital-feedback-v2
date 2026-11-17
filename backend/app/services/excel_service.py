import io
from datetime import datetime
from typing import List, Optional
import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from ..models import Feedback


EXCEL_COLUMNS = [
    ("Date", 14),
    ("Time", 12),
    ("UHID", 18),  # CRITICAL: TEXT format, preserving leading zeros!
    ("Patient Name", 24),
    ("Location", 18),
    ("Consultant", 22),
    ("Scheme", 18),
    ("Department", 18),
    ("HOD", 20),  # DETERMINISTIC MAPPING
    ("Complaint Type", 20),
    ("Complaint", 55),  # ONLY FINAL PROFESSIONAL ENGLISH COMPLAINT
]


def generate_feedback_excel(feedbacks: List[Feedback]) -> bytes:
    """
    Generates production-grade Excel (.xlsx) file.
    Rules:
    - Exactly ONE row per feedback (no merged cells, no duplicates)
    - UHID preserved strictly as text (@) preventing leading zero loss or scientific notation
    - Frozen header row (Row 1)
    - Auto-filter enabled on header row
    - Wrap text enabled on long descriptive fields
    - Hospital blue header styling
    - Sensible column widths
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Patient Feedback"

    # Styling definitions
    header_fill = PatternFill(start_color="1A365D", end_color="1A365D", fill_type="solid")  # Hospital Navy Blue
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    data_font = Font(name="Calibri", size=10)
    center_align = Alignment(horizontal="center", vertical="top")
    left_align = Alignment(horizontal="left", vertical="top")
    wrap_align = Alignment(horizontal="left", vertical="top", wrap_text=True)

    thin_border = Border(
        left=Side(style="thin", color="E2E8F0"),
        right=Side(style="thin", color="E2E8F0"),
        top=Side(style="thin", color="E2E8F0"),
        bottom=Side(style="thin", color="E2E8F0"),
    )

    # 1. Write Header Row
    for col_idx, (col_name, _) in enumerate(EXCEL_COLUMNS, start=1):
        cell = ws.cell(row=1, column=col_idx, value=col_name)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = thin_border
    ws.row_dimensions[1].height = 28

    # 2. Write Data Rows
    for row_idx, fb in enumerate(feedbacks, start=2):
        ws.row_dimensions[row_idx].height = 35

        # Get sub-tables
        transcript_obj = fb.transcript
        ai_obj = fb.ai_analysis

        eng_trans = transcript_obj.english_translation if transcript_obj else ""

        complaint_type = ai_obj.complaint_type if ai_obj else fb.department
        complaint_text = (
            getattr(fb, "complaint", None)
            or (ai_obj.complaint_summary if ai_obj and ai_obj.complaint_summary != "Not Provided" else None)
            or eng_trans
            or "Not Provided"
        )

        # EXACTLY 11 COLUMNS IN REQUIRED ORDER:
        # Date | Time | UHID | Patient Name | Location | Consultant | Scheme | Department | HOD | Complaint Type | Complaint
        row_data = [
            (str(fb.date_str or ""), center_align, "YYYY-MM-DD"),
            (str(fb.time_str or ""), center_align, "HH:MM:SS"),
            (str(fb.uhid), left_align, "@"),  # CRITICAL UHID TEXT FORMATTING (preserves leading zeros)
            (str(fb.patient_name), left_align, "@"),
            (str(fb.location or "Not Provided"), left_align, "@"),
            (str(fb.consultant or "Not Provided"), left_align, "@"),
            (str(fb.scheme or "Not Provided"), left_align, "@"),
            (str(fb.department), left_align, "@"),
            (str(fb.hod_name), left_align, "@"),  # DETERMINISTIC HOD MAPPING
            (str(complaint_type), center_align, "@"),
            (str(complaint_text), wrap_align, "@"),  # DEDICATED ENGLISH COMPLAINT ONLY
        ]

        for col_idx, (val, alignment, num_format) in enumerate(row_data, start=1):
            cell = ws.cell(row=row_idx, column=col_idx, value=val)
            cell.font = data_font
            cell.alignment = alignment
            cell.number_format = num_format
            cell.border = thin_border

    # 3. Freeze Header Row
    ws.freeze_panes = "A2"

    # 4. Enable Filters
    max_col_letter = get_column_letter(len(EXCEL_COLUMNS))
    max_row = max(len(feedbacks) + 1, 1)
    ws.auto_filter.ref = f"A1:{max_col_letter}{max_row}"

    # 5. Set sensible column widths
    for col_idx, (_, width) in enumerate(EXCEL_COLUMNS, start=1):
        col_letter = get_column_letter(col_idx)
        ws.column_dimensions[col_letter].width = width

    # Save to buffer
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output.getvalue()
