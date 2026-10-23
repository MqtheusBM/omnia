"""Serviço de análise de processos usando a API direta da OpenAI."""

from __future__ import annotations

import time

from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI, RateLimitError

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.schemas import LLMAnalysis, Questionario
from app.services.gemini_service import (
    GeminiJSONParseError,
    _build_full_prompt,
    _build_response_schema_block,
    _parse_llm_response,
)

logger = get_logger("openai")
_MAX_ATTEMPTS = 3
_RETRYABLE_STATUS_CODES = {408, 409, 429, 500, 502, 503, 504}

_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "respostas": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "pergunta_id": {"type": "string"},
                    "resposta": {"type": "string", "enum": ["Sim", "Não", "Não se aplica"]},
                    "paginas": {"type": "array", "items": {"type": "integer"}},
                    "evidencia": {"type": "string"},
                    "confianca": {"type": "string", "enum": ["alta", "média", "baixa"]},
                    "observacao": {"type": ["string", "null"]},
                },
                "required": [
                    "pergunta_id",
                    "resposta",
                    "paginas",
                    "evidencia",
                    "confianca",
                    "observacao",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["respostas"],
    "additionalProperties": False,
}


class OpenAIServiceError(Exception):
    """Falha na chamada à API da OpenAI ou no parsing de sua resposta."""


def _is_retryable(error: Exception) -> bool:
    status = getattr(error, "status_code", None)
    if status in _RETRYABLE_STATUS_CODES:
        return True
    if isinstance(error, (APIConnectionError, APITimeoutError, RateLimitError)):
        return True
    if isinstance(error, APIStatusError):
        return error.status_code in _RETRYABLE_STATUS_CODES
    return isinstance(error, TimeoutError)


def _create_response(client: OpenAI, *, model: str, input_text: str):
    """Faz a chamada Responses com retentativas limitadas para erros transitórios."""
    for attempt in range(_MAX_ATTEMPTS):
        try:
            return client.responses.create(
                model=model,
                input=input_text,
                reasoning={"effort": "low"},
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "triagem_processual",
                        "strict": True,
                        "schema": _RESPONSE_SCHEMA,
                    }
                },
            )
        except Exception as error:
            if attempt == _MAX_ATTEMPTS - 1 or not _is_retryable(error):
                raise
            delay = 2**attempt
            logger.warning(
                "Falha transitória na OpenAI; repetindo chamada",
                extra={"attempt": attempt + 1, "retry_in_seconds": delay},
            )
            time.sleep(delay)


def analyze_with_openai(
    paginated_ocr_text: str,
    questionnaire: Questionario,
    prompt_version: str,
    processo_id: str | None = None,
) -> LLMAnalysis:
    """Analisa o OCR e retorna as respostas no formato esperado pelo pipeline."""
    settings = get_settings()
    if not settings.openai_api_key:
        raise OpenAIServiceError(
            "OPENAI_API_KEY não configurada. Adicione uma chave de API da OpenAI ao arquivo .env."
        )

    prompt = (
        f"{_build_response_schema_block()}\n\n"
        f"{_build_full_prompt(paginated_ocr_text, questionnaire, prompt_version)}"
    )
    client = OpenAI(
        api_key=settings.openai_api_key,
        timeout=settings.llm_timeout_seconds,
        max_retries=0,
    )

    logger.info("Chamando OpenAI", extra={"status": "llm_start", "job_id": processo_id})
    started_at = time.time()
    try:
        response = _create_response(client, model=settings.openai_model, input_text=prompt)
    except Exception as error:
        raise OpenAIServiceError(f"Erro na chamada à OpenAI: {error}") from error

    logger.info(
        "OpenAI respondeu",
        extra={"status": "llm_done", "duration_ms": int((time.time() - started_at) * 1000)},
    )
    raw_text = response.output_text or ""

    try:
        return _parse_llm_response(
            raw_text, questionnaire, settings.openai_model, prompt_version, processo_id
        )
    except GeminiJSONParseError:
        logger.warning("JSON inválido da OpenAI; tentando reparo estruturado")

    repair_prompt = (
        "Corrija a resposta abaixo para corresponder ao schema de saída solicitado. "
        "Use somente dados presentes na resposta anterior e retorne o JSON estruturado.\n\n"
        f"Resposta anterior:\n{raw_text}"
    )
    try:
        repaired = _create_response(
            client, model=settings.openai_model, input_text=repair_prompt
        )
        return _parse_llm_response(
            repaired.output_text or "",
            questionnaire,
            settings.openai_model,
            prompt_version,
            processo_id,
        )
    except Exception as error:
        message = f"Resposta inválida mesmo após tentativa de reparo: {error}"
        raise OpenAIServiceError(message) from error
