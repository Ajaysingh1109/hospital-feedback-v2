import re
from typing import Dict, Optional

# Configurable hospital location abbreviations dictionary
# Allows hospital administrators or engineers to register new shorthands without prompt changes
HOSPITAL_LOCATION_ABBREVIATIONS: Dict[str, str] = {
    "GW1": "General Ward 1",
    "GW2": "General Ward 2",
    "GW3": "General Ward 3",
}


def extract_and_normalize_location(text: str) -> Optional[str]:
    """
    Extracts and normalizes hospital location from spoken transcript or text when context
    indicates it is a location/ward (e.g., 'GW1 ke patient', 'GW2 mein', 'Location: GW1').
    The original transcript remains untouched; this returns a normalized candidate for the Location field.
    """
    if not text:
        return None

    # Contextual regex: abbreviation followed or preceded by location cues (ke patient, mein, par, ward, bed, room, location)
    for abbr, full_name in HOSPITAL_LOCATION_ABBREVIATIONS.items():
        # Match e.g. "GW1 ke patient", "GW1 mein", "GW2 par", "Location: GW1", "ward GW1", etc.
        pattern = (
            rf"(?:\b(?:location|ward|bed|room)\s*[:=-]?\s*{re.escape(abbr)}\b)|"
            rf"(?:\b{re.escape(abbr)}\b\s*(?:ke\s+(?:patient|mariz|admission)|mein|me|par|ward|floor|bed)?)"
        )
        if re.search(pattern, text, flags=re.IGNORECASE):
            return full_name

    return None


def normalize_explicit_location(location_str: Optional[str]) -> Optional[str]:
    """
    Normalizes an explicit staff-entered location string (e.g. 'GW1' -> 'General Ward 1').
    Leaves unmapped locations intact.
    """
    if not location_str:
        return None
    loc = location_str.strip()
    upper = loc.upper()
    return HOSPITAL_LOCATION_ABBREVIATIONS.get(upper, loc)


def expand_hospital_shorthands_in_english(text: str) -> str:
    """
    Safely expands hospital ward abbreviations in translated English complaints
    (e.g., 'GW1' -> 'General Ward 1', 'Ward GW1' -> 'General Ward 1').
    """
    if not text:
        return ""
    expanded = text
    for abbr, full_name in HOSPITAL_LOCATION_ABBREVIATIONS.items():
        # Match 'Ward GW1' or 'GW1'
        expanded = re.sub(rf"\b(?:ward\s+)?{re.escape(abbr)}\b", full_name, expanded, flags=re.IGNORECASE)
    return expanded

