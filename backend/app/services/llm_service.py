"""Seleciona o provedor LLM configurado sem alterar o pipeline de OCR."""

from __future__ import annotations

from app.core.config import get_settings
from app.models.schemas import LLMAnalysis, Questionario


def analyze_with_llm(
    paginated_ocr_text: str,
    questionnaire: Questionario,
    prompt_version: str,
    processo_id: str | None = None,
) -> LLMAnalysis:
    """Encaminha a análise ao provedor escolhido em ``LLM_PROVIDER``."""
    provider = get_settings().llm_provider.strip().lower()
    if provider == "openai":
        from app.services.openai_service import analyze_with_openai

        return analyze_with_openai(
            paginated_ocr_text, questionnaire, prompt_version, processo_id
        )
    if provider == "gemini":
        from app.services.gemini_service import analyze_with_gemini

        return analyze_with_gemini(
            paginated_ocr_text, questionnaire, prompt_version, processo_id
        )
    raise ValueError("LLM_PROVIDER inválido. Valores aceitos: openai ou gemini.")
