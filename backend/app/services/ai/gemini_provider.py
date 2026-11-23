import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional

from ..hospital_normalization import (
    expand_hospital_shorthands_in_english,
    extract_and_normalize_location,
)
from .base import LLMProvider, STTProvider, TranslationProvider
from .mock_provider import MockLLMProvider, MockSTTProvider, MockTranslationProvider

logger = logging.getLogger(__name__)


def post_process_transcript(transcript: str) -> str:
    """
    Safeguard against common acoustic misrecognitions and speech engine artifacts.
    Ensures hospital-specific vocabulary is disambiguated without altering spoken intent.
    """
    if not transcript:
        return ""
    text = transcript
    # Acoustic confusion: 'feedbacker' / 'feed backer' -> 'feedback'
    text = re.sub(r"\bfeedbacker\b", "feedback", text, flags=re.IGNORECASE)
    text = re.sub(r"\bfeed\s+backer\b", "feedback", text, flags=re.IGNORECASE)
    # Acoustic confusion: 'peshent' / 'paishant' -> 'patient'
    text = re.sub(r"\bpeshent\b", "patient", text, flags=re.IGNORECASE)
    text = re.sub(r"\bpaishant\b", "patient", text, flags=re.IGNORECASE)
    # Acoustic confusion: 'this charge' -> 'discharge' in billing/ward context
    text = re.sub(r"\bthis\s+charge\b", "discharge", text, flags=re.IGNORECASE)
    # Acoustic confusion: 'attender' -> 'attendant'
    text = re.sub(r"\battender\b", "attendant", text, flags=re.IGNORECASE)
    return text.strip()


HOSPITAL_DOMAIN_VOCABULARY_CONTEXT = """
HOSPITAL & CLINICAL DOMAIN VOCABULARY HINTS:
- Key terms: patient, feedback, attendant, doctor, consultant, physician, nurse, nursing staff, sister,
  ward, bed, room, ICU, OPD, IPD, emergency, reception, billing, TPA, insurance, discharge,
  admission, prescription, medicine, pharmacy, chemist, dose, injection, wheelchair, stretcher,
  housekeeping, safai, cleanliness, washroom, toilet, bathroom, linen, bedsheet, pillow,
  food, diet, meal, breakfast, lunch, dinner, khana, namak, salt, tea, water,
  air conditioning, AC, fan, cooling, light, tap, plumbing, lift, elevator, security guard,
  GW1, GW2, GW3 (General Ward 1, 2, 3), PVT, pvt room (Private Room).

PHONETIC DISAMBIGUATION RULES:
- 'peshent' or 'mariz' -> 'patient'
- 'pvt' / 'pvt room' / 'pvt.' -> 'Private Room'
- 'feedback' / 'feedbacker' / 'feed back' -> transcribe accurately as 'feedback' or 'feedback lene' as spoken; NEVER transcribe as 'feedbacker'.
- 'attender' -> 'attendant'
- 'this charge' in hospital context -> 'discharge'
- 'sister' -> 'sister' (referring to nursing staff)
"""


class GeminiAIProvider(STTProvider, TranslationProvider, LLMProvider):
    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self.model_name = model_name or os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
        self.fallback_models = ["gemini-3.1-flash-lite", "gemini-3.5-flash"]
        self._fallback_stt = MockSTTProvider()
        self._fallback_trans = MockTranslationProvider()
        self._fallback_llm = MockLLMProvider()

        self.client = None
        if self.api_key:
            try:
                from google import genai
                self.client = genai.Client(api_key=self.api_key)
            except Exception as e:
                logger.error(f"[Gemini Client] Failed to initialize client: {e}")

    def _generate_with_retry_and_fallback(self, contents: Any, config: Any) -> Any:
        if not self.client:
            raise RuntimeError("Gemini client is not initialized. Please configure GEMINI_API_KEY.")

        candidate_models = [self.model_name] + [m for m in self.fallback_models if m != self.model_name]
        last_error = None

        for model in candidate_models:
            for attempt in range(2):
                try:
                    return self.client.models.generate_content(
                        model=model,
                        contents=contents,
                        config=config,
                    )
                except Exception as e:
                    last_error = e
                    err_msg = str(e)
                    logger.warning(
                        f"[Gemini] Request to model {model} attempt {attempt+1} failed: {err_msg}"
                    )
                    # Handle transient load spike (503 / 429 / UNAVAILABLE)
                    if any(code in err_msg for code in ["503", "429", "UNAVAILABLE"]):
                        time.sleep(1.0)
                        continue
                    else:
                        # Non-retryable error on this model, break to next candidate model
                        break
        raise last_error

    def transcribe(
        self,
        audio_path: str,
        mime_type: str = "audio/webm",
        language_hint: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not self.client:
            logger.warning("[Gemini STT] Client not initialized. Returning empty transcript.")
            return {"original_transcript": "", "detected_language": "Unknown", "error": "CLIENT_NOT_INITIALIZED"}

        if not os.path.exists(audio_path):
            logger.warning(f"[Gemini STT] File not found: {audio_path}")
            return {"original_transcript": "", "detected_language": "Unknown", "error": "FILE_NOT_FOUND"}

        try:
            from google.genai import types

            with open(audio_path, "rb") as f:
                audio_bytes = f.read()

            if len(audio_bytes) < 1500:
                logger.warning(f"[Gemini STT] Audio file under 1500 bytes ({len(audio_bytes)}B). Flagged silent/empty.")
                return {"original_transcript": "", "detected_language": "Unknown", "error": "AUDIO_TOO_SHORT"}

            prompt = (
                "You are an expert bilingual medical speech-to-text transcription engine. Listen to this hospital feedback recording.\n"
                f"{HOSPITAL_DOMAIN_VOCABULARY_CONTEXT}\n"
                "STRICT VERBATIM TRANSCRIPTION RULES:\n"
                "1. Transcribe the EXACT words spoken verbatim. DO NOT translate into English.\n"
                "2. Preserve original Hindi, Hinglish, or English phrasing exactly as uttered.\n"
                "3. If Hindi/Hinglish is spoken (e.g., 'GW1 ke patient ko subah se breakfast nahi mila'), transcribe in the spoken phrasing exactly as uttered.\n"
                "4. DO NOT sanitize colloquial words, summarize, or extrapolate unmentioned facts.\n"
                "5. Common phrase: When staff says 'patient feedback lene aaye hain' or 'feedback lene', transcribe it accurately. NEVER output 'feedbacker'.\n"
                "6. If the audio contains only silence, background noise, or no discernible human speech, return an empty string.\n"
                "Return JSON with keys:\n"
                "{\n"
                '  "original_transcript": "verbatim spoken transcription",\n'
                '  "detected_language": "Hindi | Hinglish | English | Mixed"\n'
                "}"
            )

            response = self._generate_with_retry_and_fallback(
                contents=[
                    types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
                    prompt,
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.0,
                ),
            )

            res_text = (response.text or "").strip()
            if not res_text or res_text in ["00:00", "[00:00]", "{}", "[]"]:
                return {"original_transcript": "", "detected_language": "Unknown"}

            data = {}
            try:
                data = json.loads(res_text)
                if isinstance(data, list) and data:
                    data = data[0]
            except Exception:
                data = {"original_transcript": res_text, "detected_language": "Mixed"}

            raw_transcript = data.get("original_transcript", "").strip() if isinstance(data, dict) else str(res_text).strip()
            if raw_transcript in ["00:00", "0:00", "[00:00]"]:
                raw_transcript = ""

            cleaned_transcript = post_process_transcript(raw_transcript)

            return {
                "original_transcript": cleaned_transcript,
                "detected_language": data.get("detected_language", "Mixed").strip() if isinstance(data, dict) else "Mixed",
            }
        except Exception as e:
            logger.error(f"[Gemini STT] Transcription failed: {e}")
            return {"original_transcript": "", "detected_language": "Unknown", "error": str(e)}

    def translate_to_english(
        self,
        transcript: str,
        source_language: Optional[str] = None,
    ) -> str:
        if not transcript or not transcript.strip():
            return ""

        if not self.client:
            return self._fallback_trans.translate_to_english(transcript, source_language)

        try:
            from google.genai import types

            prompt = (
                "You are a professional healthcare translation expert.\n"
                "Translate the following hospital conversation into clear, accurate, professional English.\n\n"
                "CRITICAL FIDELITY & ANTI-HALLUCINATION RULES:\n"
                "1. STRICT FIDELITY: Translate ONLY what was explicitly said. DO NOT invent, assume, or extrapolate ANY details.\n"
                "2. PRESERVE TIME AND TEMPORAL NUANCE:\n"
                "   - 'subah se' -> 'since morning'\n"
                "   - 'abhi tak nahi mila' / 'abhi tak nahi aaya' -> 'has still not been provided / has still not arrived'\n"
                "   - 'bahut der ho gayi' -> 'has been delayed for a long time'\n"
                "3. HOSPITAL SHORTHANDS & ABBREVIATIONS:\n"
                "   - 'GW1', 'GW2', 'GW3' -> 'General Ward 1', 'General Ward 2', 'General Ward 3'\n"
                "   - 'pvt', 'pvt room', 'pvt.' -> 'Private Room'\n"
                "4. FULL VERBATIM PATIENT STATEMENT (STRICTLY NO SUMMARY):\n"
                "   - Translate EVERYTHING the patient or attendant said completely and accurately as it is.\n"
                "   - DO NOT summarize, condense, or omit any grievances, observations, or details.\n"
                "5. STATEMENT ATTRIBUTION:\n"
                "   - Begin the translated statement with: 'Patient / Attendant stated that ...' followed by the exact verbatim translation of what was said.\n"
                "6. EXCLUDE INTERVIEWER QUESTIONS:\n"
                "   - EXCLUDE staff/interviewer inquiry questions or greetings (such as 'namaste', 'feedback lene aaye hain', 'aapko koi pareshani to nahi hui'). Translate ONLY what the patient or attendant stated as their feedback.\n"
                "7. ALREADY IN ENGLISH: If the spoken conversation is already in English, retain the full verbatim statement without changing any facts, prefixed by 'Patient / Attendant stated that ...'.\n"
                "8. PRESERVE SEVERITY & TONE: Keep the complaint objective and faithful. Do not amplify minor concerns or downplay serious issues.\n"
                "9. NO INVENTED NAMES OR DIAGNOSES: Do not invent patient names, consultant names, bed numbers, medical conditions, or drug names.\n"
                "10. OUTPUT: Return ONLY the clean English patient statement without any intro, outro, preamble, or quotation marks.\n\n"
                f"Conversation:\n{transcript}\n\n"
                "Professional English Translation:"
            )

            response = self._generate_with_retry_and_fallback(
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.0),
            )
            raw_eng = (response.text or "").strip()
            clean_eng = raw_eng.strip('"`\' \n')
            expanded_eng = expand_hospital_shorthands_in_english(clean_eng)
            return expanded_eng
        except Exception as e:
            logger.error(f"[Gemini Translation] Translation failed: {e}")
            raise RuntimeError(f"Translation service unavailable: {e}")

    def extract_structured_feedback(
        self,
        original_transcript: str,
        english_translation: str,
    ) -> Dict[str, Any]:
        if not (original_transcript.strip() or english_translation.strip()):
            return self._fallback_llm.extract_structured_feedback(original_transcript, english_translation)

        if not self.client:
            return self._fallback_llm.extract_structured_feedback(original_transcript, english_translation)

        try:
            from google.genai import types

            prompt = (
                "You are an AI Hospital Patient Feedback structuring engine.\n\n"
                "CRITICAL ANTI-HALLUCINATION & PROVENANCE RULES:\n"
                "1. SENSITIVE FIELDS FORBIDDEN: UHID, Patient Name, Consultant, Department, Location, and Scheme must NEVER be invented. AI cannot know them unless explicitly uttered. If not explicitly spoken in the audio, return 'Not Provided'.\n"
                "2. SHORT SUMMARY (complaint_summary): Must be exactly ONE concise, factual sentence summarizing ONLY the issues or compliments explicitly stated. Strictly forbid mentioning patient names, consultant names, durations, or medical diagnoses unless explicitly uttered. No emotional speculation (do NOT say 'deliberate negligence' or 'extremely dissatisfied').\n"
                "3. COMPLAINT STATEMENT (complaint): Full verbatim English complaint statement as stated by the patient/attendant without omitting details (begin with 'Patient / Attendant stated that ...'). Strictly NO summarizing or condensing.\n"
                "4. NO MEDICAL DIAGNOSES: Do NOT diagnose illnesses or recommend clinical treatments.\n"
                "5. SUGGESTED DEPARTMENT: Suggest ONE department based ONLY on the complaint: Clinical, Nursing, Pharmacy, Maintenance, F&B, Housekeeping, Operations, Billing, IT, Security, Other.\n"
                "6. COMPLAINT TYPE: Classify the statement strictly as one of: Complaint, Suggestion, Request, or Appreciation (default: Complaint).\n"
                "7. PRIORITY: Low | Medium | High | Critical | Not Specified (Assign based ONLY on explicit urgency words; default Medium for complaints, Low for appreciation).\n"
                "8. FIELD PROVENANCE: Every field must be categorized as 'STAFF_ENTERED', 'EXPLICITLY_SPOKEN', or 'AI_DERIVED'.\n\n"
                f"Original Transcript:\n{original_transcript}\n\n"
                f"English Translation:\n{english_translation}\n\n"
                "Return strict JSON matching this structure:\n"
                "{\n"
                '  "complaint": "Clear professional English complaint statement",\n'
                '  "complaint_summary": "1-sentence factual summary of spoken issue only",\n'
                '  "detailed_feedback": "Detailed paragraph of what occurred without invented facts",\n'
                '  "positive_feedback": "Explicit praise or Not Provided",\n'
                '  "negative_feedback": "Explicit issue or Not Provided",\n'
                '  "specific_complaint": "Concrete specific issue or Not Provided",\n'
                '  "suggested_action": "Operational improvement recommendation or Not Provided",\n'
                '  "complaint_type": "Complaint | Suggestion | Request | Appreciation",\n'
                '  "suggested_department": "Clinical | Nursing | Pharmacy | Maintenance | F&B | Housekeeping | Operations | Billing | IT | Security | Other",\n'
                '  "suggested_subcategory": "Short category description",\n'
                '  "priority": "Low | Medium | High | Critical | Not Specified",\n'
                '  "confidence_score": 0.95,\n'
                '  "field_provenance": {\n'
                '    "uhid": "STAFF_ENTERED",\n'
                '    "patient_name": "STAFF_ENTERED",\n'
                '    "consultant": "STAFF_ENTERED",\n'
                '    "department": "STAFF_ENTERED",\n'
                '    "location": "STAFF_ENTERED",\n'
                '    "scheme": "STAFF_ENTERED",\n'
                '    "original_transcript": "EXPLICITLY_SPOKEN",\n'
                '    "complaint": "EXPLICITLY_SPOKEN",\n'
                '    "complaint_summary": "EXPLICITLY_SPOKEN",\n'
                '    "complaint_type": "AI_DERIVED",\n'
                '    "suggested_department": "AI_DERIVED",\n'
                '    "priority": "AI_DERIVED"\n'
                '  }\n'
                "}"
            )

            response = self._generate_with_retry_and_fallback(
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.0,
                ),
            )
            data = json.loads(response.text)

            # Check for contextual location normalization (GW1 -> General Ward 1)
            suggested_loc = (
                extract_and_normalize_location(original_transcript)
                or extract_and_normalize_location(english_translation)
            )
            if suggested_loc:
                data["suggested_location"] = suggested_loc

            # Ensure provenance dictionary exists
            if "field_provenance" not in data or not isinstance(data["field_provenance"], dict):
                data["field_provenance"] = {
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
                }

            return data
        except Exception as e:
            logger.error(f"[Gemini Extraction] Structured extraction failed: {e}")
            raise RuntimeError(f"AI analysis unavailable: {e}")
