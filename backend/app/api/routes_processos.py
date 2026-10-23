"""
Rotas da API de processos.

Endpoints:
- POST /v1/processos/analisar — Envia PDF para análise
- GET  /v1/processos/{job_id} — Consulta status de um job
- GET  /v1/processos/{job_id}/resultado — Obtém resultado final
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.security import is_password_protected_pdf, is_valid_pdf_signature
from app.models.database import create_job, get_job
from app.models.schemas import (
    JobCreatedResponse,
    JobResultResponse,
    JobStatus,
    JobStatusResponse,
    RelatorioCorreicional,
    RespostaItem,
    RegraCreateRequest,
    RegraDraftRequest,
)
from app.services.process_catalog_service import listar_processos
from app.services.rule_catalog_service import listar_regras, salvar_regra
from app.services.rule_generation_service import RuleGenerationError, gerar_passos
from app.services.process_analysis_service import run_analysis
from app.services.questionario_service import load_questionario

logger = get_logger("api.processos")

router = APIRouter(prefix="/v1/processos", tags=["processos"])


@router.get("/catalogo", summary="Listar PDFs disponíveis no acervo local")
async def catalogo_processos():
    """Lista metadados dos PDFs sem expor caminhos do servidor ou ler seu conteúdo."""
    return listar_processos()


@router.get("/regras", summary="Listar regras disponíveis para análise")
async def catalogo_regras():
    """Retorna o catálogo versionado de regras executáveis."""
    return listar_regras()


@router.post("/regras/gerar", summary="Gerar passos de regra com IA")
async def gerar_regra(request: RegraDraftRequest):
    try:
        return gerar_passos(request)
    except RuleGenerationError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@router.post("/regras", status_code=201, summary="Salvar regra personalizada")
async def criar_regra(request: RegraCreateRequest):
    regra_id = f"RC-{uuid.uuid4().hex[:6].upper()}"
    regra = {
        "id": regra_id,
        "nome": request.nome.strip(),
        "versao": "1.0",
        "uso": "0 correições",
        "selecionada": False,
        "descricao": request.descricao.strip(),
        "competencia": "Não especificada",
        "fontes": "Critérios definidos na criação da regra",
        "autor": "Usuário",
        "aprovador": "Pendente de aprovação",
        "confirmacao": "—",
        "recomendada": False,
        "instrucao": request.instrucao,
        "cenario_atende": request.atende,
        "cenario_nao_atende": request.nao_atende,
        "cenario_nao_se_encaixa": request.nao_se_encaixa,
        "ajustes_solicitados": request.ajustes,
        "passos": request.passos,
        "created_at": datetime.now(timezone.utc),
    }
    return salvar_regra(regra)


@router.post(
    "/analisar",
    response_model=JobCreatedResponse,
    status_code=202,
    summary="Enviar processo para análise",
    description="Recebe um PDF de processo judicial e um ID de questionário. "
    "Retorna um job_id para acompanhamento assíncrono.",
)
async def analisar_processo(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="Arquivo PDF do processo"),
    questionario_id: str = Form(..., description="ID do questionário a aplicar"),
    processo_id: str | None = Form(None, description="ID do processo (opcional)"),
) -> JobCreatedResponse:
    """Recebe PDF e inicia pipeline de análise em background."""
    settings = get_settings()

    # ── Validação do questionário ──────────────────────────────────
    questionario = load_questionario(questionario_id)
    if questionario is None:
        raise HTTPException(
            status_code=400,
            detail=f"Questionário não encontrado: {questionario_id}",
        )

    if len(questionario.perguntas) > settings.max_questions_per_questionnaire:
        raise HTTPException(
            status_code=400,
            detail=f"Questionário excede o máximo de {settings.max_questions_per_questionnaire} perguntas",
        )

    # ── Validação do arquivo ───────────────────────────────────────
    if not file.filename:
        raise HTTPException(status_code=400, detail="Nome do arquivo é obrigatório")

    # Ler conteúdo
    pdf_bytes = await file.read()

    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="Arquivo vazio")

    # Validar tamanho
    if len(pdf_bytes) > settings.max_pdf_size_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Arquivo excede o limite de {settings.max_pdf_size_mb}MB",
        )

    # Validar assinatura PDF
    if not is_valid_pdf_signature(pdf_bytes):
        raise HTTPException(
            status_code=400,
            detail="Arquivo não é um PDF válido (assinatura inválida)",
        )

    # Verificar proteção por senha
    if is_password_protected_pdf(pdf_bytes):
        raise HTTPException(
            status_code=400,
            detail="PDFs protegidos por senha não são suportados nesta versão",
        )

    # ── Criar job ──────────────────────────────────────────────────
    job_id = str(uuid.uuid4())
    from app.core.security import compute_sha256

    sha256 = compute_sha256(pdf_bytes)

    create_job(
        job_id=job_id,
        processo_id=processo_id,
        questionario_id=questionario_id,
        original_filename=file.filename,
        sha256_hash=sha256,
    )

    logger.info(
        "Job criado via API",
        extra={"job_id": job_id, "status": "recebido"},
    )

    # ── Disparar processamento em background ───────────────────────
    background_tasks.add_task(
        run_analysis,
        job_id=job_id,
        pdf_bytes=pdf_bytes,
        original_filename=file.filename,
        questionario=questionario,
        processo_id=processo_id,
    )

    return JobCreatedResponse(
        job_id=job_id,
        status=JobStatus.RECEBIDO,
        processo_id=processo_id,
    )


@router.get(
    "/{job_id}",
    response_model=JobStatusResponse,
    summary="Consultar status de um job",
)
async def consultar_status(job_id: str) -> JobStatusResponse:
    """Retorna o status atual de um job de análise."""
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job não encontrado: {job_id}")

    return JobStatusResponse(
        job_id=job["job_id"],
        status=JobStatus(job["status"]),
        processo_id=job.get("processo_id"),
        total_paginas=job.get("total_pages"),
        created_at=job.get("created_at"),
        started_at=job.get("started_at"),
        completed_at=job.get("completed_at"),
        error_message=job.get("error_message"),
    )


@router.get(
    "/{job_id}/resultado",
    response_model=JobResultResponse,
    summary="Obter resultado final da análise",
)
async def obter_resultado(job_id: str) -> JobResultResponse:
    """Retorna o resultado completo e validado de uma análise."""
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job não encontrado: {job_id}")

    status = JobStatus(job["status"])
    if status not in (JobStatus.CONCLUIDO, JobStatus.REVISAO_NECESSARIA):
        raise HTTPException(
            status_code=409,
            detail=f"Resultado ainda não disponível. Status atual: {status.value}",
        )

    validated = job.get("validated_response")
    if not validated:
        raise HTTPException(
            status_code=500,
            detail="Resultado não encontrado no banco de dados",
        )

    respostas = [RespostaItem(**r) for r in validated.get("respostas", [])]

    return JobResultResponse(
        job_id=job["job_id"],
        status=status,
        total_paginas=job.get("total_pages", 0),
        questionario_id=validated.get("questionario_id", ""),
        modelo=validated.get("modelo", ""),
        versao_prompt=validated.get("versao_prompt", ""),
        revisao_necessaria=validated.get("revisao_necessaria", False),
        respostas=respostas,
        relatorio=(
            RelatorioCorreicional(**job["generated_report"])
            if job.get("generated_report") else None
        ),
    )
