"""
Serviço de integração com Gemini Flash.

Monta o prompt completo (sistema + schema + questionário + OCR) e envia
ao modelo Gemini configurável via variável de ambiente.
"""

from __future__ import annotations

import json
import re
import time
from datetime import date
from pathlib import Path

from google import genai
from google.genai import types

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.schemas import (
    LLMAnalysis,
    Questionario,
    RespostaItem,
)

logger = get_logger("gemini")

# O SDK já tenta novamente alguns erros transitórios. A repetição explícita
# cobre os casos que ainda escaparem, com limite para não prender o job.
_MAX_GEMINI_ATTEMPTS = 3
_RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}

# Diretório de prompts versionados
PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


class GeminiServiceError(Exception):
    """Erro na chamada ao Gemini."""


class GeminiJSONParseError(GeminiServiceError):
    """Erro ao parsear JSON da resposta do Gemini."""


def _is_retryable_gemini_error(error: Exception) -> bool:
    """Retorna se o erro parece transitório (HTTP 5xx/429 ou timeout)."""
    status = getattr(error, "code", None) or getattr(error, "status_code", None)
    try:
        if int(status) in _RETRYABLE_STATUS_CODES:
            return True
    except (TypeError, ValueError):
        pass

    # Alguns erros do transporte expõem somente o tipo ou a mensagem.
    return isinstance(error, TimeoutError) or "timeout" in str(error).lower()


def _generate_content_with_retry(client, *, model: str, contents: str, config):
    """Executa a chamada ao Gemini com até duas repetições exponenciais."""
    for attempt in range(_MAX_GEMINI_ATTEMPTS):
        try:
            return client.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )
        except Exception as error:
            if attempt == _MAX_GEMINI_ATTEMPTS - 1 or not _is_retryable_gemini_error(error):
                raise
            delay_seconds = 2**attempt
            logger.warning(
                "Falha transitória no Gemini; repetindo chamada",
                extra={"attempt": attempt + 1, "retry_in_seconds": delay_seconds},
            )
            time.sleep(delay_seconds)


def _load_prompt_template(prompt_version: str) -> str:
    """Carrega template de prompt do sistema de arquivos."""
    prompt_file = PROMPTS_DIR / f"{prompt_version}.md"
    if not prompt_file.exists():
        raise FileNotFoundError(f"Prompt não encontrado: {prompt_file}")
    return prompt_file.read_text(encoding="utf-8")


def _build_questions_block(questionnaire: Questionario) -> str:
    """Monta o bloco de perguntas formatadas para o prompt."""
    lines = ["[PERGUNTAS DO QUESTIONÁRIO]"]
    for p in questionnaire.perguntas:
        lines.append(f"- ID: {p.id} | Pergunta: {p.texto}")
    return "\n".join(lines)


def _build_response_schema_block() -> str:
    """Define o schema de saída esperado como instrução textual."""
    return """[SCHEMA DE SAÍDA OBRIGATÓRIO]
Retorne APENAS um objeto JSON válido, sem formatação markdown (```json), sem introdução ou conclusão. Siga esta estrutura:
{
  "respostas": [
    {
      "pergunta_id": "string — o ID da pergunta respondida",
      "resposta": "Sim | Não | Não se aplica",
      "paginas": [1, 2],
      "evidencia": "trecho literal curto do OCR que sustenta a resposta",
      "confianca": "alta | média | baixa",
      "observacao": "string ou null"
    }
  ]
}

Regras:
- Responda TODAS as perguntas listadas acima.
- Cada resposta deve ter exatamente um dos valores: "Sim", "Não" ou "Não se aplica".
- Toda resposta DEVE conter pelo menos uma página válida e um trecho de evidência literal do texto OCR.
- Se não encontrar evidência suficiente, responda "Não se aplica" e explique na observação.
- NÃO invente páginas ou evidências que não existam no texto."""


def _build_full_prompt(
    paginated_ocr_text: str,
    questionnaire: Questionario,
    prompt_version: str,
) -> str:
    """Monta o prompt completo para envio ao Gemini."""
    template = _load_prompt_template(prompt_version)

    # Substituir placeholders do template
    today_str = date.today().strftime("%d/%m/%Y")
    prompt = template.replace("[INSERIR_DATA_ATUAL_DO_SISTEMA]", today_str)

    # Inserir as regras como as perguntas do questionário
    questions_block = _build_questions_block(questionnaire)
    prompt = prompt.replace("[INSERIR_LISTA_DE_REGRAS_DO_BANCO_DE_DADOS]", questions_block)

    # Inserir texto OCR
    prompt = prompt.replace("[INSERIR_TEXTO_BRUTO_DO_OCR_AQUI]", paginated_ocr_text)

    return prompt


def _extract_json_from_response(text: str) -> str:
    """
    Extrai JSON de uma resposta que pode conter wrappers markdown.
    Tenta extrair de blocos ```json ... ``` ou usa o texto diretamente.
    """
    # Tentar extrair de bloco markdown
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if match:
        return match.group(1).strip()

    # Tentar encontrar JSON direto (começa com { e termina com })
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return match.group(0).strip()

    return text.strip()


def _parse_llm_response(
    raw_text: str,
    questionnaire: Questionario,
    modelo: str,
    prompt_version: str,
    processo_id: str | None,
) -> LLMAnalysis:
    """Parseia a resposta bruta do LLM em LLMAnalysis estruturado."""
    json_str = _extract_json_from_response(raw_text)

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise GeminiJSONParseError(f"JSON inválido na resposta do LLM: {e}") from e

    # Aceitar tanto resposta com wrapper "respostas" quanto lista direta
    respostas_raw = data.get("respostas", data) if isinstance(data, dict) else data

    if not isinstance(respostas_raw, list):
        raise GeminiJSONParseError("Resposta do LLM não contém lista de respostas")

    respostas = [RespostaItem(**r) for r in respostas_raw]

    return LLMAnalysis(
        processo_id=processo_id,
        questionario_id=questionnaire.id,
        modelo=modelo,
        versao_prompt=prompt_version,
        respostas=respostas,
    )


def analyze_with_gemini(
    paginated_ocr_text: str,
    questionnaire: Questionario,
    prompt_version: str,
    processo_id: str | None = None,
) -> LLMAnalysis:
    """
    Envia texto OCR paginado e questionário ao Gemini Flash.

    Args:
        paginated_ocr_text: Texto OCR com marcadores [PÁGINA N].
        questionnaire: Questionário com perguntas a responder.
        prompt_version: Nome do arquivo de prompt (sem extensão).
        processo_id: ID do processo fornecido pelo cliente.

    Returns:
        LLMAnalysis com respostas estruturadas.

    Raises:
        GeminiServiceError: Em caso de falha na chamada ou JSON inválido.
    """
    settings = get_settings()

    # Montar prompt completo
    system_prompt = _build_full_prompt(paginated_ocr_text, questionnaire, prompt_version)
    schema_instructions = _build_response_schema_block()
    full_user_content = f"{schema_instructions}\n\n{system_prompt}"

    # Configurar cliente
    client = genai.Client(
        api_key=settings.gemini_api_key,
        http_options=types.HttpOptions(timeout=settings.llm_timeout_seconds * 1000),
    )

    config = types.GenerateContentConfig(
        temperature=0,
        response_mime_type="application/json",
    )

    logger.info(
        "Chamando Gemini",
        extra={
            "status": "llm_start",
            "job_id": processo_id,
        },
    )
    start_time = time.time()

    try:
        response = _generate_content_with_retry(
            client,
            model=settings.gemini_model,
            contents=full_user_content,
            config=config,
        )
    except Exception as e:
        raise GeminiServiceError(f"Erro na chamada ao Gemini: {e}") from e

    duration_ms = int((time.time() - start_time) * 1000)
    logger.info(
        "Gemini respondeu",
        extra={"status": "llm_done", "duration_ms": duration_ms},
    )

    raw_text = response.text or ""

    # Primeira tentativa de parse
    try:
        return _parse_llm_response(
            raw_text, questionnaire, settings.gemini_model, prompt_version, processo_id
        )
    except GeminiJSONParseError:
        logger.warning("JSON inválido do LLM, tentando prompt de reparo")

    # ── Tentativa de reparo (máximo 1) ──────────────────────────────
    repair_prompt = (
        "A resposta anterior continha JSON inválido. "
        "Por favor, retorne APENAS o JSON válido seguindo o schema solicitado, "
        "sem texto adicional, sem blocos markdown."
        f"\n\nResposta anterior:\n{raw_text}"
    )

    try:
        repair_response = _generate_content_with_retry(
            client,
            model=settings.gemini_model,
            contents=repair_prompt,
            config=config,
        )
        repaired_text = repair_response.text or ""
        return _parse_llm_response(
            repaired_text, questionnaire, settings.gemini_model, prompt_version, processo_id
        )
    except (GeminiJSONParseError, Exception) as e:
        raise GeminiServiceError(
            f"JSON inválido mesmo após tentativa de reparo: {e}"
        ) from e
