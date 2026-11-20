from typing import Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import HODMapping

# STRICT CANONICAL BUSINESS RULES (Section 1 & 6)
# Asha Ma'am: ONLY Maintenance, F&B, Housekeeping, Operations, Billing
# Tanveer Sir: Clinical
# Reshmi Ma'am: Nursing
# Vijay Sir: Pharmacy
# Valay Sir: IT
DEFAULT_HOD_MAPPING = {
    # Tanveer Sir
    "clinical": "Tanveer Sir",
    "doctor": "Tanveer Sir",
    "consultant": "Tanveer Sir",

    # Reshmi Ma'am
    "nursing": "Reshmi Ma'am",

    # Vijay Sir
    "pharmacy": "Vijay Sir",

    # Valay Sir
    "it": "Valay Sir",

    # Asha Ma'am (ONLY these 5 departments!)
    "maintenance": "Asha Ma'am",
    "f&b": "Asha Ma'am",
    "f & b": "Asha Ma'am",
    "food & beverage": "Asha Ma'am",
    "housekeeping": "Asha Ma'am",
    "operations": "Asha Ma'am",
    "billing": "Asha Ma'am",
}

# Standard display names
STANDARD_HOD_BY_DEPT = {
    "Clinical": "Tanveer Sir",
    "Nursing": "Reshmi Ma'am",
    "Pharmacy": "Vijay Sir",
    "IT": "Valay Sir",
    "Maintenance": "Asha Ma'am",
    "F&B": "Asha Ma'am",
    "Housekeeping": "Asha Ma'am",
    "Operations": "Asha Ma'am",
    "Billing": "Asha Ma'am",
    # Security and Other are NOT automatically mapped.
    # If not configured in Admin Master Data, they return "HOD Not Configured".
    "Security": "HOD Not Configured",
    "Other": "HOD Not Configured",
}


def get_deterministic_hod(department_name: str, db: Optional[Session] = None) -> str:
    """
    CRITICAL BUSINESS RULE (Sections 1, 6 & 23, 24):
    Determines HOD strictly based on deterministic backend mapping.
    The AI does NOT decide HOD.
    If a department has no configured HOD: returns "HOD Not Configured".
    Never guesses.
    Supports single or multiple comma-separated departments (up to 4).
    """
    if not department_name or not department_name.strip():
        return "HOD Not Configured"

    # Support multiple departments separated by comma
    depts = [d.strip() for d in department_name.split(",") if d.strip()]
    if not depts:
        return "HOD Not Configured"

    def _resolve_single_hod(dept_clean: str) -> str:
        dept_key = dept_clean.lower()
        if db is not None:
            try:
                mapping = db.scalar(
                    select(HODMapping).where(
                        HODMapping.department_name.ilike(dept_clean),
                        HODMapping.is_active == True,
                    )
                )
                if mapping and mapping.hod_name and mapping.hod_name.strip():
                    val = mapping.hod_name.strip()
                    if val:
                        return val
            except Exception:
                pass

        if dept_key in DEFAULT_HOD_MAPPING:
            return DEFAULT_HOD_MAPPING[dept_key]

        for key, hod in DEFAULT_HOD_MAPPING.items():
            if key in dept_key:
                return hod

        return "HOD Not Configured"

    mapped_hods = []
    for d in depts:
        h = _resolve_single_hod(d)
        if h not in mapped_hods:
            mapped_hods.append(h)

    return ", ".join(mapped_hods) if mapped_hods else "HOD Not Configured"
