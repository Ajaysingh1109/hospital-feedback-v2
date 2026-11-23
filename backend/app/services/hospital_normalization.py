import re
from typing import Dict, Optional

# Configurable hospital location abbreviations dictionary
# Allows hospital administrators or engineers to register new shorthands without prompt changes
HOSPITAL_LOCATION_ABBREVIATIONS: Dict[str, str] = {
    "GW1": "General Ward 1",
    "GW2": "General Ward 2",
    "GW3": "General Ward 3",
    "PVT": "Private Room",
    "PVT ROOM": "Private Room",
    "PVT.": "Private Room",
    "PVT. ROOM": "Private Room",
    "PVT WARD": "Private Room",
    "PRIVATE": "Private Room",
}


def extract_and_normalize_location(text: str) -> Optional[str]:
    """
    Extracts and normalizes hospital location from spoken transcript or text when context
    indicates it is a location/ward/room (e.g., 'GW1 ke patient', 'pvt room mein', 'Location: pvt 102').
    The original transcript remains untouched; this returns a normalized candidate for the Location field.
    """
    if not text:
        return None

    # 1. Contextual regex for Private Room: "pvt room", "pvt", "pvt 101"
    pvt_pattern = (
        r"(?:\b(?:location|ward|bed|room)\s*[:=-]?\s*pvt(?:\.?\s*room)?\b\s*(\d+)?)|"
        r"(?:\bpvt(?:\.?\s*room)?\b\s*(\d+)?\s*(?:ke\s+(?:patient|mariz|admission)|mein|me|par|ward|floor|bed)?)"
    )
    pvt_match = re.search(pvt_pattern, text, flags=re.IGNORECASE)
    if pvt_match:
        room_num = pvt_match.group(1) or pvt_match.group(2)
        if room_num:
            return f"Private Room {room_num}"
        # Only return Private Room if there was actual contextual location cue or pvt room
        matched_str = pvt_match.group(0).lower()
        if "room" in matched_str or any(cue in matched_str for cue in ["mein", "me", "par", "ward", "location", "patient"]):
            return "Private Room"

    # 2. Contextual regex: abbreviation followed or preceded by location cues (ke patient, mein, par, ward, bed, room, location)
    for abbr in ["GW1", "GW2", "GW3"]:
        full_name = HOSPITAL_LOCATION_ABBREVIATIONS[abbr]
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
    Normalizes an explicit staff-entered location string:
    - 'GW1' -> 'General Ward 1'
    - 'pvt' / 'pvt room' -> 'Private Room'
    - 'pvt 101' -> 'Private Room 101'
    Leaves unmapped locations intact.
    """
    if not location_str:
        return None
    loc = location_str.strip()
    upper = loc.upper()
    if upper in HOSPITAL_LOCATION_ABBREVIATIONS:
        return HOSPITAL_LOCATION_ABBREVIATIONS[upper]

    # Handle variations of pvt shorthand (e.g. "pvt 101" -> "Private Room 101", "pvt room 204" -> "Private Room 204")
    loc = re.sub(r"\bpvt(?:\.|\b)\s*room\b", "Private Room", loc, flags=re.IGNORECASE)
    loc = re.sub(r"\bpvt(?:\.|\b)\s*ward\b", "Private Room", loc, flags=re.IGNORECASE)
    loc = re.sub(r"\bpvt(?:\.|\b)", "Private Room", loc, flags=re.IGNORECASE)

    # Handle GW1, GW2, GW3 within multi-word string
    for abbr in ["GW1", "GW2", "GW3"]:
        loc = re.sub(rf"\b{re.escape(abbr)}\b", HOSPITAL_LOCATION_ABBREVIATIONS[abbr], loc, flags=re.IGNORECASE)

    loc = re.sub(r"\s+", " ", loc).strip()
    return loc


def expand_hospital_shorthands_in_english(text: str) -> str:
    """
    Safely expands hospital ward and room abbreviations in translated English complaints
    (e.g., 'GW1' -> 'General Ward 1', 'pvt' / 'pvt room' -> 'Private Room').
    """
    if not text:
        return ""
    expanded = text

    # Expand pvt / pvt room / pvt. to Private Room
    expanded = re.sub(r"\bpvt(?:\.|\b)\s*room\b", "Private Room", expanded, flags=re.IGNORECASE)
    expanded = re.sub(r"\bpvt(?:\.|\b)\s*ward\b", "Private Room", expanded, flags=re.IGNORECASE)
    expanded = re.sub(r"\bpvt(?:\.|\b)", "Private Room", expanded, flags=re.IGNORECASE)

    # Expand GW1, GW2, GW3
    for abbr in ["GW1", "GW2", "GW3"]:
        full_name = HOSPITAL_LOCATION_ABBREVIATIONS[abbr]
        expanded = re.sub(rf"\b(?:ward\s+)?{re.escape(abbr)}\b", full_name, expanded, flags=re.IGNORECASE)

    return expanded

