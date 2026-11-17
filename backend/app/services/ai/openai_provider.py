import json
import logging
import os
from typing import Any, Dict, Optional

from .base import LLMProvider, STTProvider, TranslationProvider
from .mock_provider import MockLLMProvider, MockSTTProvider, MockTranslationProvider

logger = logging.getLogger(__name__)


class OpenAIProvider(STTProvider, TranslationProvider, LLMProvider):
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self._fallback_stt = MockSTTProvider()
        self._fallback_trans = MockTranslationProvider()
        self._fallback_llm = MockLLMProvider()

        self.client = None
        if self.api_key:
            try:
                from openai import OpenAI
                self.client = OpenAI(api_key=self.api_key)
            except Exception as e:
                logger.warning(f"Failed to initialize OpenAI client: {e}. Using fallback.")

    def transcribe(
        self,
        audio_path: str,
        mime_type: str = "audio/webm",
        language_hint: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not self.client or not os.path.exists(audio_path):
            return self._fallback_stt.transcribe(audio_path, mime_type, language_hint)

        try:
            with open(audio_path, "rb") as f:
                transcript = self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=f,
                    response_format="verbose_json",
                )
            detected_lang = getattr(transcript, "language", "Hindi")
            text = getattr(transcript, "text", "")
            return {
                "original_transcript": text.strip(),
                "detected_language": detected_lang.capitalize() if detected_lang else "Mixed",
            }
        except Exception as e:
            logger.error(f"OpenAI transcription failed: {e}. Falling back.")
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
                "You are an expert bilingual healthcare translation specialist.\n"
                "Translate the following Hindi, Hinglish, or mixed speech into clear, professional English.\n"
                "Do NOT translate mechanically word-for-word. Preserve the conversational context accurately.\n"
                "DO NOT hallucinate or add any facts.\n\n"
                f"Transcript:\n{transcript}"
            )
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"OpenAI translation failed: {e}. Falling back.")
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
                "You are a structured hospital feedback extractor.\n"
                "STRICT RULES:\n"
                "1. NEVER invent patient names, UHID, consultant names, departments, or diagnoses.\n"
                "2. If information is missing, output 'Not Provided'.\n"
                "3. Clinical safety: Do NOT provide medical diagnosis or treatment advice.\n"
                "4. Suggest ONE department from: Clinical, Nursing, Pharmacy, Maintenance, F&B, Housekeeping, Operations, Billing, IT, Security, Other.\n\n"
                f"Original: {original_transcript}\n"
                f"English: {english_translation}\n\n"
                "Return strict JSON with keys: complaint_summary, detailed_feedback, positive_feedback, "
                "negative_feedback, specific_complaint, suggested_action, complaint_type, suggested_department, "
                "suggested_subcategory, priority, confidence_score."
            )
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                response_format={"type": "json_object"},
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            logger.error(f"OpenAI extraction failed: {e}. Falling back.")
            return self._fallback_llm.extract_structured_feedback(original_transcript, english_translation)
