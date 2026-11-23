import io
import re
from datetime import datetime
from typing import List, Optional
import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from ..models import Feedback
from .hospital_normalization import (
    expand_hospital_shorthands_in_english,
    normalize_explicit_location,
)


def clean_patient_verbatim_statement(raw_text: str) -> str:
    """
    Ensures Excel contains ONLY what the patient/attendant stated verbatim without high-level summary.
    - Strips out any interviewer/staff questions or dialogue prefixes.
    - Expands hospital shorthands: 'pvt' / 'pvt room' -> 'Private Room', 'GW1' -> 'General Ward 1', etc.
    - Formats the statement starting with 'Patient / Attendant stated that ...' accurately reflecting spoken feedback.
    """
    if not raw_text or not raw_text.strip():
        return "Not Provided"

    text = raw_text.strip()
    if text == "Not Provided":
        return "Not Provided"

    # 1. If explicit dialogue tags like 'Patient:' or 'Attendant:' exist, extract patient parts
    patient_segments = re.findall(
        r'(?:patient|attendant|attender|marij|mariz)\s*[:\-]\s*(.*?)(?=(?:staff|doctor|nurse|interviewer|feedbacker|\bpatient\b|\battendant\b|\battender\b\s*[:\-]|$))',
        text,
        flags=re.IGNORECASE | re.DOTALL
    )
    if patient_segments:
        extracted = " ".join(s.strip() for s in patient_segments if s.strip())
        if extracted:
            text = extracted

    # 2. Strip leading staff/interviewer dialogue or questions
    staff_patterns = [
        r'^(?:staff|interviewer|doctor|nurse|feedbacker)\s*[:\-].*?(?=(?:patient|attendant|attender)\s*[:\-]|\n|$)',
        r'^(?:namaste|hello|hi)[,\s]+(?:feedback|patient|sir|ma\'?am).*?[.?!]\s*',
        r'^(?:aapko\s+)?koi\s+(?:pareshani|problem|dikkat|issue|shikayat)\s+(?:hai|to\s+nahi|hui).*?[.?!\n]\s*',
        r'^(?:did\s+you\s+face|how\s+was|how\s+is)\s+(?:any\s+problem|your\s+stay|the\s+service|the\s+food).*?[.?!\n]\s*',
    ]
    for pattern in staff_patterns:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE | re.DOTALL).strip()

    # 3. Clean up leading/trailing leftover dialogue tags
    text = re.sub(r'^(?:patient|attendant|attender)\s*[:\-]\s*', '', text, flags=re.IGNORECASE).strip()

    # 4. Expand hospital ward and room shorthands (pvt -> Private Room, GW1 -> General Ward 1)
    text = expand_hospital_shorthands_in_english(text)

    # 5. Clean mock or technical prefixes
    text = re.sub(r'^Translated feedback:\s*', '', text, flags=re.IGNORECASE).strip()

    if not text or text == "Not Provided":
        return "Not Provided"

    # 6. Check if attribution prefix is already present
    attribution_pattern = (
        r'^(?:the\s+)?(?:patient\s*(?:/|\band\b)?\s*attend(?:ant|er)|patient|attend(?:ant|er))\s+'
        r'(?:stated|reported|mentioned|complained|shared|said)\s+(?:that\s+)?'
    )
    match = re.match(attribution_pattern, text, flags=re.IGNORECASE)
    if match:
        body = text[match.end():].strip()
        if body:
            first_word = body.split()[0]
            if body[0].isupper() and len(body) > 1 and body[1].islower():
                if first_word not in ["I", "Dr.", "Dr", "GW1", "GW2", "GW3", "Private", "ICU", "OPD", "IPD"]:
                    body = body[0].lower() + body[1:]
            return f"Patient / Attendant stated that {body}"
        return text

    # Apply attribution prefix
    first_word = text.split()[0]
    if text[0].isupper() and len(text) > 1 and text[1].islower():
        if first_word not in ["I", "Dr.", "Dr", "GW1", "GW2", "GW3", "Private", "ICU", "OPD", "IPD"]:
            text = text[0].lower() + text[1:]

    return f"Patient / Attendant stated that {text}"


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

        complaint_type = (ai_obj.complaint_type if ai_obj and ai_obj.complaint_type else None) or "Complaint"
        # Exact verbatim statement from patient: strictly no summary, staff questions filtered out
        raw_complaint = (
            getattr(fb, "complaint", None)
            or eng_trans
            or (transcript_obj.original_transcript if transcript_obj else "")
            or "Not Provided"
        )
        complaint_text = clean_patient_verbatim_statement(raw_complaint)

        norm_loc = normalize_explicit_location(fb.location) if fb.location else "Not Provided"

        # EXACTLY 11 COLUMNS IN REQUIRED ORDER:
        # Date | Time | UHID | Patient Name | Location | Consultant | Scheme | Department | HOD | Complaint Type | Complaint
        row_data = [
            (str(fb.date_str or ""), center_align, "YYYY-MM-DD"),
            (str(fb.time_str or ""), center_align, "HH:MM:SS"),
            (str(fb.uhid), left_align, "@"),  # CRITICAL UHID TEXT FORMATTING (preserves leading zeros)
            (str(fb.patient_name), left_align, "@"),
            (str(norm_loc), left_align, "@"),
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
