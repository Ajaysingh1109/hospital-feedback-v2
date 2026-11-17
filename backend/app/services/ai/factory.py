import logging
from functools import lru_cache
from typing import Tuple

from ...core.config import get_settings
from .base import LLMProvider, STTProvider, TranslationProvider
from .gemini_provider import GeminiAIProvider
from .mock_provider import MockLLMProvider, MockSTTProvider, MockTranslationProvider
from .openai_provider import OpenAIProvider

logger = logging.getLogger("hospital_feedback.ai_factory")


@lru_cache()
def get_ai_providers() -> Tuple[STTProvider, TranslationProvider, LLMProvider]:
    """
    Resolves the active AI pipeline (Section 4):
    - REAL AI MODE: Gemini or OpenAI using live cloud endpoints
    - MOCK/TEST MODE: High-fidelity deterministic provider for test suites and offline verification
    """
    settings = get_settings()
    provider_name = (settings.AI_PROVIDER or "").lower().strip()

    if provider_name == "gemini":
        if not settings.GEMINI_API_KEY:
            logger.error("[AI Factory] REQUIRED: Google Gemini API key is missing in configuration.")
            raise RuntimeError("REQUIRED: Google Gemini API key. GEMINI_API_KEY is not configured.")
        logger.info(f"[AI Factory] Operating in REAL AI MODE with Google Gemini ({settings.GEMINI_MODEL}).")
        gemini = GeminiAIProvider(
            api_key=settings.GEMINI_API_KEY,
            model_name=settings.GEMINI_MODEL,
        )
        return gemini, gemini, gemini

    if provider_name == "openai":
        if not settings.OPENAI_API_KEY:
            logger.error("[AI Factory] REQUIRED: OpenAI API key is missing in configuration.")
            raise RuntimeError("REQUIRED: OpenAI API key. OPENAI_API_KEY is not configured.")
        logger.info("[AI Factory] Operating in REAL AI MODE with OpenAI (Whisper + GPT).")
        openai_p = OpenAIProvider(api_key=settings.OPENAI_API_KEY)
        return openai_p, openai_p, openai_p

    logger.info("[AI Factory] Operating in MOCK/TEST MODE (Deterministic offline & QA verification).")
    mock_stt = MockSTTProvider()
    mock_trans = MockTranslationProvider()
    mock_llm = MockLLMProvider()
    return mock_stt, mock_trans, mock_llm


def get_active_ai_mode() -> str:
    settings = get_settings()
    p = (settings.AI_PROVIDER or "").lower().strip()
    if p == "gemini" and settings.GEMINI_API_KEY:
        return f"REAL AI MODE (Gemini - {settings.GEMINI_MODEL})"
    if p == "openai" and settings.OPENAI_API_KEY:
        return "REAL AI MODE (OpenAI)"
    return "MOCK/TEST MODE"
