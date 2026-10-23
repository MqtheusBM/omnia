"""
Orquestrador do fluxo de análise de processos.

Coordena a sequência completa:
PDF → OCR → Paginação → Gemini → Validação → Persistência.

Cada etapa é delegada a um serviço isolado, facilitando
testes unitários e evolução independente.
"""

from __future__ import annotations

import time
import traceback

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.security import compute_sha256, sanitize_filename
from app.models.database import (
    append_audit_entries,
    create_job,
    update_job_status,
)
from app.models.schemas import (
    JobStatus,
    Questionario,
    ValidatedAnalysis,
)
from app.services.document_ai_service import process_document_ocr
from app.services.llm_service import analyze_with_llm
from app.services.ocr_text_service import build_paginated_text
from app.services.report_generation_service import generate_report
from app.services.storage_service import get_storage_service
from app.services.validation_service import validate_llm_response

logger = get_logger("orchestrator")

# Versão padrão do prompt
DEFAULT_PROMPT_VERSION = "triagem_processual_v1"


def run_analysis(
    job_id: str,
    pdf_bytes: bytes,
    original_filename: str,
    questionario: Questionario,
    processo_id: str | None = None,
) -> None:
    """
    Executa o pipeline completo de análise de um processo.

    Esta função é chamada em background (BackgroundTasks do FastAPI).
    Toda exceção é capturada e registrada no banco sem expor dados sensíveis.

    Args:
        job_id: UUID do job.
        pdf_bytes: Bytes do PDF.
        original_filename: Nome original do arquivo.
        questionario: Questionário já validado.
        processo_id: ID do processo fornecido pelo cliente.
    """
    settings = get_settings()
    storage = get_storage_service()

    try:
        # ── 1. Persistir PDF original ──────────────────────────────
        safe_name = sanitize_filename(original_filename)
        sha256 = compute_sha256(pdf_bytes)

        pdf_ref = storage.save_pdf(job_id, pdf_bytes, safe_name)
        update_job_status(
            job_id,
            JobStatus.OCR_EM_ANDAMENTO,
            sha256_hash=sha256,
            storage_refs={"pdf": pdf_ref},
        )

        # ── 2. OCR com Document AI ─────────────────────────────────
        logger.info("Iniciando OCR", extra={"job_id": job_id})
        ocr_start = time.time()

        ocr_result = process_document_ocr(pdf_bytes)

        ocr_duration_ms = int((time.time() - ocr_start) * 1000)
        logger.info(
            "OCR concluído",
            extra={
                "job_id": job_id,
                "total_pages": ocr_result.total_pages,
                "duration_ms": ocr_duration_ms,
            },
        )

        # Salvar resultado OCR bruto
        ocr_ref = storage.save_ocr_result(job_id, ocr_result.model_dump())

        update_job_status(
            job_id,
            JobStatus.OCR_CONCLUIDO,
            total_pages=ocr_result.total_pages,
            ocr_duration_ms=ocr_duration_ms,
        )

        # Validar limite de páginas
        if ocr_result.total_pages > settings.max_pages_per_request:
            raise ValueError(
                f"Documento excede o limite de {settings.max_pages_per_request} páginas "
                f"({ocr_result.total_pages} páginas detectadas)"
            )

        # ── 3. Texto paginado ──────────────────────────────────────
        paginated_text = build_paginated_text(ocr_result)

        # ── 4. Análise com Gemini ──────────────────────────────────
        update_job_status(job_id, JobStatus.ANALISE_EM_ANDAMENTO)

        logger.info(
            "Iniciando análise LLM",
            extra={
                "job_id": job_id,
                "total_pages": ocr_result.total_pages,
            },
        )
        llm_start = time.time()

        llm_analysis = analyze_with_llm(
            paginated_ocr_text=paginated_text,
            questionnaire=questionario,
            prompt_version=DEFAULT_PROMPT_VERSION,
            processo_id=processo_id,
        )

        llm_duration_ms = int((time.time() - llm_start) * 1000)
        logger.info(
            "Análise LLM concluída",
            extra={"job_id": job_id, "duration_ms": llm_duration_ms},
        )

        # Salvar resposta bruta do LLM
        llm_ref = storage.save_llm_response(job_id, llm_analysis.model_dump())

        # ── 5. Validação defensiva ─────────────────────────────────
        validated: ValidatedAnalysis = validate_llm_response(
            analysis=llm_analysis,
            questionnaire=questionario,
            paginated_text=paginated_text,
            total_pages=ocr_result.total_pages,
        )

        # ── 5.1 Minuta do relatório institucional ──────────────────
        report = generate_report(
            paginated_ocr_text=paginated_text,
            analysis=validated.model_dump(mode="json"),
            processo_id=processo_id,
        )
        report_ref = storage.save_report(job_id, report.model_dump(mode="json"))

        # Salvar resultado validado
        result_ref = storage.save_validated_result(job_id, validated.model_dump())

        # ── 6. Persistir resultado final ───────────────────────────
        final_status = (
            JobStatus.REVISAO_NECESSARIA if validated.revisao_necessaria
            else JobStatus.CONCLUIDO
        )

        update_job_status(
            job_id,
            final_status,
            llm_duration_ms=llm_duration_ms,
            model_used=llm_analysis.modelo,
            prompt_version=llm_analysis.versao_prompt,
            validated_response=validated.model_dump(),
            revisao_necessaria=validated.revisao_necessaria,
            storage_refs={
                "pdf": pdf_ref,
                "ocr": ocr_ref,
                "llm_raw": llm_ref,
                "result": result_ref,
                "report": report_ref,
            },
            generated_report=report.model_dump(mode="json"),
        )

        # Salvar log de auditoria
        if validated.audit_log:
            append_audit_entries(
                job_id,
                [entry.model_dump() for entry in validated.audit_log],
            )

        logger.info(
            "Pipeline concluído",
            extra={
                "job_id": job_id,
                "status": final_status.value,
                "total_pages": ocr_result.total_pages,
                "revisao_necessaria": validated.revisao_necessaria,
            },
        )

    except Exception as e:
        error_category = type(e).__name__
        # Log sem dados sensíveis — apenas categoria e mensagem genérica
        logger.error(
            "Pipeline falhou",
            extra={
                "job_id": job_id,
                "error_category": error_category,
            },
        )
        # Mensagem segura para o banco (sem stack trace completo)
        safe_message = f"[{error_category}] {str(e)[:500]}"
        update_job_status(
            job_id,
            JobStatus.FALHOU,
            error_message=safe_message,
            error_category=error_category,
        )
