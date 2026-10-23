"""Gera passos auditáveis para regras correicionais com o provedor LLM configurado."""

from __future__ import annotations

import json

from app.core.config import get_settings
from app.models.schemas import RegraDraftRequest, RegraDraftResponse


class RuleGenerationError(Exception):
    """Falha ao gerar uma regra usando o provedor de IA configurado."""


def _prompt(request: RegraDraftRequest) -> str:
    return f"""Você auxilia uma equipe de correição judicial a transformar critérios em etapas verificáveis.
Crie entre 3 e 8 passos curtos, objetivos, ordenados e auditáveis. Não invente requisitos legais;
use somente a instrução e os cenários fornecidos. Retorne exclusivamente JSON no formato
{{"passos": ["...", "..."]}}.

Instrução: {request.instrucao}
Cenário que atende: {request.atende}
Cenário que não atende: {request.nao_atende}
Cenário que não se encaixa: {request.nao_se_encaixa}
Orientações adicionais para revisar os passos: {request.ajustes or "Nenhuma orientação adicional."}
"""


def _parse_response(raw: str) -> RegraDraftResponse:
    try:
        data = json.loads(raw)
        parsed = RegraDraftResponse.model_validate(data)
        return parsed.model_copy(update={"passos": [step.strip() for step in parsed.passos]})
    except Exception as error:
        raise RuleGenerationError("A IA retornou passos fora do formato esperado. Tente novamente.") from error


def gerar_passos(request: RegraDraftRequest) -> RegraDraftResponse:
    settings = get_settings()
    provider = settings.llm_provider.strip().lower()
    prompt = _prompt(request)

    try:
        if provider == "openai":
            if not settings.openai_api_key:
                raise RuleGenerationError("OPENAI_API_KEY não está configurada no backend.")
            from openai import OpenAI

            response = OpenAI(api_key=settings.openai_api_key, timeout=settings.llm_timeout_seconds).responses.create(
                model=settings.openai_model,
                input=prompt,
                text={"format": {
                    "type": "json_schema",
                    "name": "passos_regra_correcional",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {"passos": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 8}},
                        "required": ["passos"],
                        "additionalProperties": False,
                    },
                }},
            )
            raw = response.output_text or ""
        elif provider == "gemini":
            if not settings.gemini_api_key:
                raise RuleGenerationError("GEMINI_API_KEY não está configurada no backend.")
            from google import genai
            from google.genai import types

            response = genai.Client(api_key=settings.gemini_api_key).models.generate_content(
                model=settings.gemini_model,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0, response_mime_type="application/json"),
            )
            raw = response.text or ""
        else:
            raise RuleGenerationError("LLM_PROVIDER inválido. Configure openai ou gemini no backend.")
    except RuleGenerationError:
        raise
    except Exception as error:
        raise RuleGenerationError(f"Não foi possível gerar os passos com a IA: {error}") from error

    result = _parse_response(raw)
    if any(not step for step in result.passos):
        raise RuleGenerationError("A IA retornou um passo vazio. Tente novamente.")
    return result
