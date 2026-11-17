import re
from typing import Any, Dict, Optional

from .base import LLMProvider, STTProvider, TranslationProvider


class MockSTTProvider(STTProvider):
    def transcribe(
        self,
        audio_path: str,
        mime_type: str = "audio/webm",
        language_hint: Optional[str] = None,
    ) -> Dict[str, Any]:
        # For mock / test environments, returns realistic conversation
        return {
            "original_transcript": "STAFF: Sir aapko hospital mein sabse zyada problem kis cheez mein hui?\nPATIENT: Sab theek tha lekin nursing staff ko call karne mein thoda time lag raha tha aur khane mein namak kam tha.",
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

        # Benchmark Scenario 1: Hindi / Hinglish Doctor time pe + AC not working
        if "ac" in lower and ("kaam nahi" in lower or "not working" in lower or "dekhne aaye" in lower):
            return "The doctor attended the patient on time, but the air conditioning in the ward was not functioning."

        # Benchmark Scenario 2: Hinglish Doctor explain + Nursing response delay
        if "doctor ne achhe se explain kiya" in lower and ("nursing response" in lower or "slow tha" in lower):
            return "The doctor explained everything well, but the nursing response was slightly delayed."

        # Benchmark Scenario 3: Pure English
        if "cleaning was done twice today" in lower and "neat and clean" in lower:
            return "Cleaning was done twice today, hospital is neat and clean."

        # Benchmark Scenario 4: Mixed Hindi + English Medicine on time + Bathroom dirty
        if "medicine time pe mil gayi" in lower and ("bathroom dirty" in lower or "dirty tha" in lower):
            return "The patient stated that medications were received on time, but the bathroom cleanliness was unsatisfactory."

        # Benchmark Scenario 5: Security guard assisted
        if "security guard" in lower and ("entrance" in lower or "madad" in lower):
            return "The security guard assisted at the entrance."

        # Benchmark Scenario 6: Food / Namak kam tha + Nurse
        if "namak kam tha" in lower and "nurse" in lower:
            return (
                "The patient reported that the food was slightly low in salt "
                "and that there was a delay in calling the nursing staff."
            )

        # Pure English detection
        if not any(
            w in lower
            for w in [
                "tha",
                "thi",
                "hai",
                "mein",
                "aur",
                "ko",
                "se",
                "achhe",
                "thoda",
                "kuch",
                "kya",
                "lekin",
                "kaam",
                "nahi",
                "madad",
            ]
        ):
            # Already English: clean up staff/patient tags if present
            cleaned = re.sub(r"^(STAFF|PATIENT):\s*", "", text, flags=re.MULTILINE)
            return cleaned.strip()

        # General contextual translation fallback
        return f"Translated summary: {text}"


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
        dept = "Nursing"  # default sensible candidate
        subcat = "General"
        complaint_type = "Complaint"
        priority = "Medium"

        # Helper word-boundary check to prevent substring collisions (e.g. 'light' inside 'slightly')
        def has_any(words):
            return any(re.search(r"\b" + re.escape(w) + r"\b", combined) for w in words)

        # Check specific complaint cues first (Complaints take priority over praise for department mapping)
        if has_any(["bill", "billing", "discharge billing", "tpa", "insurance"]):
            dept = "Billing"
            subcat = "Discharge billing delay"
            negative = "Discharge billing took excessive time."
            specific_complaint = "Delay in final bill clearance and discharge summary."
            suggested_action = "Streamline TPA pre-authorization settlement workflow."
            priority = "High"
        elif has_any(["bathroom", "clean", "toilet", "saaf", "dirty", "housekeeping", "washroom"]):
            dept = "Housekeeping"
            subcat = "Washroom cleanliness"
            negative = "Washroom cleanliness was poor."
            specific_complaint = "Dirty bathroom upon admission."
            suggested_action = "Schedule regular housekeeping inspection rounds every 2 hours."
            priority = "Medium"
        elif has_any(["ac", "fan", "tap", "light", "lights", "plumbing", "maintenance", "air conditioning"]):
            dept = "Maintenance"
            subcat = "Equipment and civil maintenance"
            negative = "Room air conditioning was not cooling adequately."
            priority = "Medium"
        elif has_any(["nurse", "nursing", "sister", "bell", "call button"]):
            dept = "Nursing"
            subcat = "Delay in response"
            negative = "Delay in nursing response to patient call bells."
            specific_complaint = "Response time of nurses on floor after calling."
            suggested_action = "Review nurse-to-patient staffing ratio and bell response alarms."
            priority = "Medium"
        elif has_any(["food", "diet", "namak", "salt", "khana", "lunch", "dinner"]):
            dept = "F&B"
            subcat = "Food quality and seasoning"
            negative = "Food was under-salted and mildly cold."
            specific_complaint = "Salt levels in dietary meals."
            suggested_action = "Coordinate with clinical dietician for patient seasoning preferences."
            priority = "Low"
        elif has_any(["pharmacy", "medicine", "dawa", "prescription", "chemist", "medications"]):
            dept = "Pharmacy"
            subcat = "Medicine dispensing"
            if "time pe mil gayi" in combined or "on time" in combined:
                positive = "Prescription medicines were delivered promptly."
            else:
                negative = "Delay at the pharmacy dispensing counter."
            priority = "Medium"
        elif has_any(["doctor", "consultant", "physician", "round", "diagnosis"]):
            dept = "Clinical"
            subcat = "Doctor rounds and explanation"
            if "achhe se explain" in combined or "explained everything well" in combined or "attentive" in combined:
                positive = "Doctor was courteous and explained the medical treatment plan thoroughly."
            priority = "Low"
        elif any(w in combined for w in ["wifi", "system", "portal", "computer", "it"]):
            dept = "IT"
            subcat = "Digital services"
            negative = "Patient portal login issues."
            priority = "Low"

        # Check positive indicators ONLY if not negated ("theek nahi", "not good", etc.)
        is_negated = any(neg in combined for neg in ["theek nahi", "not good", "not clean", "kam tha", "late tha", "dirty"])
        if ("medicine time pe mil gayi" in combined or "on time" in combined) and positive == "Not Provided":
            positive = "Prescription medicines were received on time."
        elif ("attentive" in combined or "achhe se explain" in combined) and positive == "Not Provided":
            positive = "Doctors and staff were attentive and polite."
        elif not is_negated and any(w in combined for w in ["achhe", "great", "excellent", "prompt"]):
            positive = "Patient expressed appreciation for services."

        # Concise Hospital Complaint Type determination:
        # Clinical, Nursing Care, Pharmacy, Food Complaint, Housekeeping, Infrastructure,
        # Billing, Staff Behaviour, Service Complaint, Maintenance, General Feedback, Appreciation
        if negative != "Not Provided" or ("lekin" in combined and "ac" in combined):
            if dept == "Maintenance":
                complaint_type = "Maintenance"
            elif dept == "Housekeeping":
                complaint_type = "Housekeeping"
            elif dept == "Nursing":
                complaint_type = "Nursing Care"
            elif dept == "F&B":
                complaint_type = "Food Complaint"
            elif dept == "Billing":
                complaint_type = "Billing"
            elif dept == "Pharmacy":
                complaint_type = "Pharmacy"
            elif dept == "Clinical":
                complaint_type = "Clinical"
            else:
                complaint_type = "Service Complaint"
            summary = negative if negative != "Not Provided" else "Hospital service complaint"
        elif positive != "Not Provided":
            complaint_type = "Appreciation"
            summary = positive
            priority = "Low"
        else:
            complaint_type = "General Feedback"
            summary = "Patient provided general feedback regarding stay."
            priority = "Not Specified"

        detailed = (
            f"The patient shared feedback regarding hospital services. "
            f"Key observations: {english_translation.strip()}"
        )

        # Dedicated complaint field containing ONLY final professional English complaint statement
        complaint_statement = english_translation.strip() or summary or "Not Provided"

        return {
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
        }
