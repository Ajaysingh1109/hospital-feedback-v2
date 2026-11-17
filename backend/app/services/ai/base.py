from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class STTProvider(ABC):
    """Speech-to-Text provider abstraction"""

    @abstractmethod
    def transcribe(
        self,
        audio_path: str,
        mime_type: str = "audio/webm",
        language_hint: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Transcribes audio into original transcript and detected language.
        Returns:
            {
                "original_transcript": str,
                "detected_language": str  # 'Hindi', 'Hinglish', 'English', 'Mixed'
            }
        """
        pass


class TranslationProvider(ABC):
    """Translation provider abstraction"""

    @abstractmethod
    def translate_to_english(
        self,
        transcript: str,
        source_language: Optional[str] = None,
    ) -> str:
        """
        Translates Hindi/Hinglish/mixed speech into professional English
        preserving context and nuance without mechanical word-by-word distortion.
        """
        pass


class LLMProvider(ABC):
    """Structured extraction LLM abstraction"""

    @abstractmethod
    def extract_structured_feedback(
        self,
        original_transcript: str,
        english_translation: str,
    ) -> Dict[str, Any]:
        """
        Extracts structured feedback from transcripts.
        Strict rule: MUST NOT invent data. If not present in conversation, returns 'Not Provided'.
        Returns dictionary with:
            complaint_type,
            complaint_summary,
            detailed_feedback,
            positive_feedback,
            negative_feedback,
            specific_complaint,
            suggested_action,
            suggested_department,
            suggested_subcategory,
            priority,
            confidence_score
        """
        pass
