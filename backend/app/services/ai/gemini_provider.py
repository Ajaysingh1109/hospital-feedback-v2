import json
import logging
import os
from typing import Any, Dict, Optional

from .base import LLMProvider, STTProvider, TranslationProvider
from .mock_provider import MockLLMProvider, MockSTTProvider, MockTranslationProvider

logger = logging.getLogger(__name__)


class GeminiAIProvider(STTProvider, TranslationProvider, LLMProvider):
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self.model_name = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")
        self._fallback_stt = MockSTTProvider()
        self._fallback_trans = MockTranslationProvider()
        self._fallback_llm = MockLLMProvider()

        self.client = None
        if self.api_key:
            try:
                from google import genai
                self.client = genai.Client(api_key=self.api_key)
            except Exception as e:
                logger.warning(f"Failed to initialize Gemini client: {e}. Using fallback.")

    def transcribe(
        self,
        audio_path: str,
        mime_type: str = "audio/webm",
        language_hint: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not self.client or not os.path.exists(audio_path):
            return self._fallback_stt.transcribe(audio_path, mime_type, language_hint)

        try:
            from google.genai import types

            # Read audio file
            with open(audio_path, "rb") as f:
                audio_bytes = f.read()

            if len(audio_bytes) < 1000:
                return self._fallback_stt.transcribe(audio_path, mime_type, language_hint)

            prompt = (
                "You are an expert bilingual medical transcriptionist. Listen to this hospital feedback recording.\n"
                "The conversation may contain Hindi, Hinglish, English, or mixed language.\n"
                "1. Transcribe the exact words spoken by staff and patient.\n"
                "2. Identify speakers if discernible (STAFF: ... / PATIENT: ...). Do NOT invent speakers if unclear.\n"
                "3. Preserve the exact Hindi / Hinglish phrasing.\n"
                "Return JSON with keys:\n"
                "{\n"
                '  "original_transcript": "string",\n'
                '  "detected_language": "Hindi | Hinglish | English | Mixed"\n'
                "}"
            )

            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[
                    types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
                    prompt,
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.2,
                ),
            )

            res_text = response.text
            data = json.loads(res_text)
            return {
                "original_transcript": data.get("original_transcript", "").strip(),
                "detected_language": data.get("detected_language", "Mixed").strip(),
            }
        except Exception as e:
            logger.error(f"Gemini transcription failed: {e}. Falling back.")
            return self._fallback_stt.transcribe(audio_path, mime_type, language_hint)

    def translate_to_english(
        self,
        transcript: str,
        source_language: Optional[str] = None,
    ) -> str:
        if not self.client or not transcript.strip():
            return self._fallback_trans.translate_to_english(transcript, source_language)

        try:
            prompt = (
                "You are a professional healthcare translation expert.\n"
                "Translate the following hospital conversation into clear, accurate, professional English.\n"
                "Rules:\n"
                "- Do NOT translate mechanically word-for-word.\n"
                "- Preserve the clinical and experiential nuance.\n"
                "- DO NOT add information that was not spoken.\n"
                "- DO NOT omit any patient complaints, praises, or concerns.\n"
                "- DO NOT hallucinate.\n\n"
                f"Conversation:\n{transcript}\n\n"
                "Return only the clear English translation without conversational intro/outro."
            )

            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config={"temperature": 0.2},
            )
            return response.text.strip()
        except Exception as e:
            logger.error(f"Gemini translation failed: {e}. Falling back.")
            return self._fallback_trans.translate_to_english(transcript, source_language)

    def extract_structured_feedback(
        self,
        original_transcript: str,
        english_translation: str,
    ) -> Dict[str, Any]:
        if not self.client or not (original_transcript.strip() or english_translation.strip()):
            return self._fallback_llm.extract_structured_feedback(original_transcript, english_translation)

        try:
            prompt = (
                "You are an AI Hospital Patient Feedback structuring engine.\n"
                "STRICT RULES:\n"
                "1. NEVER invent patient names, UHID, doctor names, medications, departments, or diagnoses.\n"
                "2. If information is not mentioned in the conversation, use 'Not Provided'.\n"
                "3. Clinical safety: Do NOT provide medical diagnoses or treatment recommendations.\n"
                "4. Suggest ONE primary department from: Clinical, Nursing, Pharmacy, Maintenance, F&B, Housekeeping, Operations, Billing, IT, Security, Other.\n"
                "5. Complaint Type must be one of: Clinical, Nursing Care, Pharmacy, Food Complaint, Housekeeping, Infrastructure, Billing, Staff Behaviour, Service Complaint, Maintenance, General Feedback, Appreciation.\n"
                "6. Priority must be: Low, Medium, High, Critical, or Not Specified.\n\n"
                f"Original Transcript:\n{original_transcript}\n\n"
                f"English Translation:\n{english_translation}\n\n"
                "Return strict JSON matching this structure:\n"
                "{\n"
                '  "complaint": "Dedicated statement of the patient complaint or feedback in clear professional English",\n'
                '  "complaint_summary": "Short 1-sentence summary",\n'
                '  "detailed_feedback": "Detailed paragraph of what occurred",\n'
                '  "positive_feedback": "Positive observations or Not Provided",\n'
                '  "negative_feedback": "Negative observations or Not Provided",\n'
                '  "specific_complaint": "Concrete specific issue or Not Provided",\n'
                '  "suggested_action": "Operational improvement recommendation or Not Provided",\n'
                '  "complaint_type": "Clinical | Nursing Care | Pharmacy | Food Complaint | Housekeeping | Infrastructure | Billing | Staff Behaviour | Service Complaint | Maintenance | General Feedback | Appreciation",\n'
                '  "suggested_department": "Clinical | Nursing | Pharmacy | Maintenance | F&B | Housekeeping | Operations | Billing | IT | Security | Other",\n'
                '  "suggested_subcategory": "Short category description",\n'
                '  "priority": "Low | Medium | High | Critical | Not Specified",\n'
                '  "confidence_score": 0.95\n'
                "}"
            )

            from google.genai import types

            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1,
                ),
            )
            data = json.loads(response.text)
            return data
        except Exception as e:
            logger.error(f"Gemini structured extraction failed: {e}. Falling back.")
            return self._fallback_llm.extract_structured_feedback(original_transcript, english_translation)
