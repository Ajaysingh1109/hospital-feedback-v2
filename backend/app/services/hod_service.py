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
    """
    if not department_name or not department_name.strip():
        return "HOD Not Configured"

    dept_clean = department_name.strip()
    dept_key = dept_clean.lower()

    # 1. Check dynamic HODMapping database table first (configured by Admin)
    if db is not None:
        try:
            mapping = db.scalar(
                select(HODMapping).where(
                    HODMapping.department_name.ilike(dept_clean),
                    HODMapping.is_active == True,
                )
            )
            if mapping and mapping.hod_name and mapping.hod_name.strip():
                # If explicitly set in DB (e.g. Admin assigned an HOD to Security), use it
                val = mapping.hod_name.strip()
                if val:
                    return val
        except Exception:
            pass

    # 2. Check canonical dictionary for fixed rules
    if dept_key in DEFAULT_HOD_MAPPING:
        return DEFAULT_HOD_MAPPING[dept_key]

    # Check substring match only for fixed departments (e.g. "F&B / Dietary")
    for key, hod in DEFAULT_HOD_MAPPING.items():
        if key in dept_key:
            return hod

    # If unmapped, DO NOT GUESS.
    return "HOD Not Configured"
