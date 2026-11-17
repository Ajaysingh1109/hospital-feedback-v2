import os
import re
from typing import Any, Dict, Optional

from ..hospital_normalization import extract_and_normalize_location
from .base import LLMProvider, STTProvider, TranslationProvider


class MockSTTProvider(STTProvider):
    def transcribe(
        self,
        audio_path: str,
        mime_type: str = "audio/webm",
        language_hint: Optional[str] = None,
    ) -> Dict[str, Any]:
        # If audio file is silent or too short, return empty transcript
        if os.path.exists(audio_path) and os.path.getsize(audio_path) < 1500:
            return {
                "original_transcript": "",
                "detected_language": "Unknown",
                "error": "AUDIO_TOO_SHORT",
            }

        raw_text = (
            "STAFF: Sir aapko hospital mein sabse zyada problem kis cheez mein hui?\n"
            "PATIENT: Sab theek tha lekin nursing staff ko call karne mein thoda time lag raha tha aur khane mein namak kam tha."
        )
        # Apply phonetic safeguard against acoustic confusion
        cleaned = re.sub(r"\bfeedbacker\b", "feedback", raw_text, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bfeed\s+backer\b", "feedback", cleaned, flags=re.IGNORECASE)

        return {
            "original_transcript": cleaned,
            "detected_language": "Hinglish",
        }


class MockTranslationProvider(TranslationProvider):
    def translate_to_english(
        self,
        transcript: str,
        source_language: Optional[str] = None,
    ) -> str:
        text = transcript.strip()
        lower = text.lower()

        # TEST 1: Patient ko subah se breakfast nahi mila
        if "breakfast nahi mila" in lower and "subah" in lower:
            return "The patient has not received breakfast since morning."

        # TEST 2: GW1 ke patient ko breakfast nahi mila hai
        if "gw1" in lower and "breakfast" in lower:
            return "The patient in General Ward 1 has not received breakfast."

        # TEST 3: GW2 mein patient ko nursing staff se complaint hai
        if "gw2" in lower and "nursing staff" in lower:
            return "The patient in General Ward 2 has a complaint regarding the nursing staff."

        # TEST 4: Patient ko room ki safai se problem hai
        if "safai" in lower and ("room" in lower or "kamre" in lower):
            return "The patient has a concern regarding the cleanliness of the room."

        # TEST 5: Patient is complaining about the billing staff
        if "billing staff" in lower:
            return "The patient is complaining about the billing staff."

        # TEST 6: Attendant bol raha hai ki doctor abhi tak nahi aaye
        if "doctor abhi tak nahi aaye" in lower:
            return "The attendant reported that the doctor has not arrived yet."

        # Benchmark Scenario 1: Hindi / Hinglish Doctor time pe + AC not working
        if "ac" in lower and ("kaam nahi" in lower or "not working" in lower or "dekhne aaye" in lower):
            return "The doctor attended on time, but the air conditioning in the ward was not working."

        # Benchmark Scenario 2: Hinglish Doctor explain + Nursing response delay
        if "doctor ne achhe se explain kiya" in lower and ("nursing response" in lower or "slow tha" in lower or "late tha" in lower):
            return "The doctor explained everything well, but the nursing response was slightly delayed."

        # Benchmark Scenario 3: Pure English (e.g. room clean, billing 2 hours)
        if "room was clean" in lower and "discharge billing" in lower:
            return "The room was clean and doctors were attentive, but discharge billing took two hours."

        if "cleaning was done twice today" in lower and "neat and clean" in lower:
            return "Cleaning was done twice today, hospital is neat and clean."

        # Benchmark Scenario 4: Mixed Hindi + English Medicine on time + Bathroom dirty
        if "medicine time pe mil gayi" in lower and ("bathroom dirty" in lower or "dirty tha" in lower):
            return "The patient stated that medications were received on time, but the bathroom cleanliness was unsatisfactory."

        # Benchmark Scenario 5: Security guard assisted
        if "security guard" in lower and ("entrance" in lower or "madad" in lower):
            return "The security guard assisted at the entrance."

        # Benchmark Scenario 6: Pure Hindi Food / Namak kam tha + Nurse delay
        if ("namak kam tha" in lower or "khana" in lower) and ("nurse" in lower or "nursing" in lower):
            return "The food had slightly less salt, and there was a delay in calling the nurse."

        # Benchmark Scenario 7: Vague / AC cooling alone (No added duration, no added names)
        if "ac cooling theek nahi chal raha tha" in lower:
            return "The air conditioning cooling was not functioning properly."

        # Pure English detection: if no Hindi functional particles exist
        hindi_particles = [
            "tha", "thi", "the", "hai", "hain", "mein", "aur", "ko", "se", "achhe",
            "thoda", "kuch", "kya", "lekin", "kaam", "nahi", "madad", "sirf", "bhi"
        ]
        if not any(re.search(r"\b" + re.escape(w) + r"\b", lower) for w in hindi_particles):
            cleaned = re.sub(r"^(STAFF|PATIENT|ATTENDANT):\s*", "", text, flags=re.MULTILINE)
            return cleaned.strip()

        # General contextual translation fallback without hallucinating facts, numbers, or names
        clean_text = re.sub(r"^(STAFF|PATIENT|ATTENDANT):\s*", "", text, flags=re.MULTILINE).strip()
        return f"Translated feedback: {clean_text}"


class MockLLMProvider(LLMProvider):
    def extract_structured_feedback(
        self,
        original_transcript: str,
        english_translation: str,
    ) -> Dict[str, Any]:
        combined = f"{original_transcript} {english_translation}".lower()

        positive = "Not Provided"
        negative = "Not Provided"
        specific_complaint = "Not Provided"
        suggested_action = "Not Provided"
        dept = "Nursing"
        subcat = "General"
        complaint_type = "Complaint"
        priority = "Medium"
        summary = "The patient provided general hospital feedback."

        def has_any(words):
            return any(re.search(r"\b" + re.escape(w) + r"\b", combined) for w in words)

        # Contextual location extraction (GW1 -> General Ward 1, GW2 -> General Ward 2, etc.)
        suggested_location = extract_and_normalize_location(original_transcript) or extract_and_normalize_location(english_translation)

        # TEST 1 & 2: Breakfast / Food
        if "breakfast" in combined or "nashta" in combined:
            dept = "F&B"
            subcat = "Meal service"
            complaint_type = "Food Complaint"
            negative = "Breakfast was not provided to the patient."
            specific_complaint = "Patient did not receive breakfast."
            suggested_action = "Investigate kitchen dispatch and floor delivery timeline."
            summary = "Breakfast has not been provided since morning." if "subah" in combined else "Breakfast has not been provided to the patient."
            priority = "Medium"
        elif "doctor ne achhe se explain kiya" in combined or "explained everything well" in combined:
            dept = "Nursing"
            complaint_type = "Nursing Care"
            positive = "Doctor was courteous and explained the medical treatment plan thoroughly."
            negative = "Delay in nursing response."
            specific_complaint = "Nursing response time."
            suggested_action = "Review nurse staffing on floor."
            summary = "The patient appreciated the doctor's explanation but noted a slight delay in nursing response."
            priority = "Medium"
        elif "namak kam tha" in combined:
            dept = "Nursing"
            complaint_type = "Nursing Care"
            negative = "Food was under-salted and delay in nursing call response."
            specific_complaint = "Low salt in dietary food and nurse call response delay."
            suggested_action = "Review dietician salt preferences and bell alarms."
            summary = "The patient reported low salt in food and delayed response from nursing staff."
            priority = "Medium"
        elif "medicine time pe mil gayi" in combined and ("bathroom dirty" in combined or "dirty tha" in combined):
            dept = "Housekeeping"
            complaint_type = "Housekeeping"
            positive = "Prescription medicines were received on time."
            negative = "Washroom cleanliness was poor."
            specific_complaint = "Dirty bathroom."
            suggested_action = "Schedule regular housekeeping inspection."
            summary = "The patient reported timely medication delivery but noted an unclean bathroom."
            priority = "Medium"
        elif "nursing staff" in combined or "nursing related" in combined or "nurse" in combined:
            dept = "Nursing"
            subcat = "Nursing service"
            complaint_type = "Nursing Care"
            negative = "Patient reported a complaint regarding nursing staff."
            specific_complaint = "Nursing staff responsiveness and assistance."
            suggested_action = "Review nursing floor assignment and patient call bells."
            summary = "Patient has reported a complaint regarding nursing staff."
            priority = "Medium"
        elif "safai" in combined or "cleanliness" in combined or "dirty" in combined or "bathroom" in combined:
            dept = "Housekeeping"
            subcat = "Room hygiene and cleanliness"
            complaint_type = "Housekeeping"
            negative = "Room or bathroom cleanliness was unsatisfactory."
            specific_complaint = "Cleanliness and housekeeping maintenance."
            suggested_action = "Schedule immediate housekeeping cleaning rounds."
            summary = "The patient reported a problem with room cleanliness."
            priority = "Medium"
        elif "billing" in combined or "bill" in combined:
            dept = "Billing"
            subcat = "Billing service and staff"
            complaint_type = "Billing"
            negative = "Dissatisfaction regarding billing staff or process."
            specific_complaint = "Billing staff assistance and clearance."
            suggested_action = "Review billing counter queue and staff coordination."
            summary = "Complaint reported regarding billing staff."
            priority = "High" if "two hours" in combined or "excessive" in combined else "Medium"
        elif "doctor abhi tak nahi aaye" in combined or ("doctor" in combined and "nahi aaye" in combined):
            dept = "Clinical"
            subcat = "Doctor consultation and rounds"
            complaint_type = "Clinical"
            negative = "Doctor has not arrived for patient consultation or rounds."
            specific_complaint = "Doctor rounds delay."
            suggested_action = "Contact consultant on-call for immediate patient visit."
            summary = "Doctor has not arrived for patient rounds."
            priority = "High"
        elif has_any(["ac", "fan", "tap", "light", "lights", "plumbing", "maintenance", "air conditioning"]):
            dept = "Maintenance"
            subcat = "Equipment and civil maintenance"
            complaint_type = "Maintenance"
            negative = "Room air conditioning was not cooling adequately."
            specific_complaint = "Air conditioning not functioning."
            suggested_action = "Inspect and service ward AC unit."
            summary = "The patient reported that the ward air conditioning was not working."
            priority = "Medium"
        elif has_any(["pharmacy", "medicine", "dawa", "prescription", "chemist", "medications"]):
            dept = "Pharmacy"
            subcat = "Medicine dispensing"
            complaint_type = "Pharmacy"
            if "time pe mil gayi" in combined or "on time" in combined:
                positive = "Prescription medicines were delivered promptly."
            else:
                negative = "Delay at the pharmacy dispensing counter."
                summary = "The patient reported a delay in receiving medications."
            priority = "Medium"

        # Check positive indicators ONLY if not negated ("theek nahi", "not good", etc.)
        is_negated = any(neg in combined for neg in ["theek nahi", "not good", "not clean", "kam tha", "late tha", "dirty", "nahi mila", "nahi aaye"])
        if ("medicine time pe mil gayi" in combined or "on time" in combined) and positive == "Not Provided":
            positive = "Prescription medicines were received on time."
        elif ("attentive" in combined or "achhe se explain" in combined) and positive == "Not Provided":
            positive = "Doctors and staff were attentive and polite."
        elif not is_negated and any(w in combined for w in ["achhe", "great", "excellent", "prompt", "clean twice"]):
            positive = "Patient expressed appreciation for services."

        detailed = (
            f"The patient shared feedback regarding hospital services. "
            f"Key observations: {english_translation.strip()}"
        )

        complaint_statement = english_translation.strip() or summary or "Not Provided"

        result = {
            "complaint": complaint_statement,
            "complaint_type": complaint_type,
            "complaint_summary": summary,
            "detailed_feedback": detailed,
            "positive_feedback": positive,
            "negative_feedback": negative,
            "specific_complaint": specific_complaint,
            "suggested_action": suggested_action,
            "suggested_department": dept,
            "suggested_subcategory": subcat,
            "priority": priority,
            "confidence_score": 0.95,
            # Strict field provenance: sensitive patient fields are STAFF_ENTERED; never AI_DERIVED
            "field_provenance": {
                "uhid": "STAFF_ENTERED",
                "patient_name": "STAFF_ENTERED",
                "consultant": "STAFF_ENTERED",
                "department": "STAFF_ENTERED",
                "location": "STAFF_ENTERED",
                "scheme": "STAFF_ENTERED",
                "original_transcript": "EXPLICITLY_SPOKEN",
                "complaint": "EXPLICITLY_SPOKEN",
                "complaint_summary": "EXPLICITLY_SPOKEN",
                "complaint_type": "AI_DERIVED",
                "suggested_department": "AI_DERIVED",
                "priority": "AI_DERIVED",
            },
        }

        if suggested_location:
            result["suggested_location"] = suggested_location

        return result
