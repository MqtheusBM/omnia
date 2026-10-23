"""Criação e acompanhamento de execuções em lote sobre o acervo local."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.core.config import get_settings
from app.core.security import is_password_protected_pdf, is_valid_pdf_signature
from app.models.database import (
    create_correicao,
    create_job,
    get_correicao,
    get_correicao_jobs,
    listar_correicoes as listar_correicoes_db,
    update_job_status,
)
from app.models.schemas import (
    CorreicaoCreateRequest,
    CorreicaoCreatedResponse,
    CorreicaoJobResponse,
    CorreicaoStatusResponse,
    JobStatus,
)
from app.services.process_analysis_service import run_analysis
from app.services.process_catalog_service import (
    ler_pdf_referenciado,
    listar_processos,
    referencia_pdf,
)
from app.services.rule_catalog_service import montar_questionario

router = APIRouter(prefix="/v1/correicoes", tags=["correicoes"])


@router.post("", response_model=CorreicaoCreatedResponse, status_code=202)
async def criar_correicao(
    request: CorreicaoCreateRequest,
    background_tasks: BackgroundTasks,
) -> CorreicaoCreatedResponse:
    """Cria jobs para os processos selecionados e os executa em sequência."""
    settings = get_settings()
    if request.quantidade_processos != len(request.processo_ids):
        raise HTTPException(status_code=400, detail="A quantidade informada deve corresponder aos PDFs selecionados")
    if len(request.processo_ids) > settings.max_processes_per_correction:
        raise HTTPException(
            status_code=400,
            detail=f"O lote aceita até {settings.max_processes_per_correction} processos",
        )
    if len(request.regra_ids) > settings.max_questions_per_questionnaire:
        raise HTTPException(status_code=400, detail="Quantidade de regras excede o limite")

    catalog = {item["processo_id"]: item for item in listar_processos()}
    missing = [process_id for process_id in request.processo_ids if process_id not in catalog]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Processos não encontrados no acervo: {', '.join(missing)}",
        )
    try:
        questionario = montar_questionario(request.regra_ids)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    correicao_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    items: list[dict[str, Any]] = []
    for process_id in request.processo_ids:
        metadata = catalog[process_id]
        pdf_reference = referencia_pdf(process_id)
        if pdf_reference is None:
            raise HTTPException(status_code=400, detail=f"PDF indisponível: {process_id}")
        if int(metadata["tamanho_bytes"]) > settings.max_pdf_size_bytes:
            raise HTTPException(status_code=413, detail=f"PDF excede o limite de tamanho: {process_id}")
        job_id = str(uuid.uuid4())
        create_job(
            job_id=job_id,
            processo_id=process_id,
            questionario_id=questionario.id,
            original_filename=str(metadata["arquivo"]),
            sha256_hash="pendente",
            correicao_id=correicao_id,
            regra_ids=request.regra_ids,
        )
        items.append(
            {
                "job_id": job_id,
                "processo_id": process_id,
                "pdf_reference": pdf_reference,
                "filename": str(metadata["arquivo"]),
            }
        )

    create_correicao(
        {
            "_id": correicao_id,
            "correicao_id": correicao_id,
            "status": "recebida",
            "quantidade_processos": len(request.processo_ids),
            "unidade": request.unidade,
            "processo_ids": request.processo_ids,
            "regra_ids": request.regra_ids,
            "questionario_id": questionario.id,
            "created_at": now,
        }
    )
    background_tasks.add_task(executar_lote, items, questionario)
    return CorreicaoCreatedResponse(
        correicao_id=correicao_id,
        status="recebida",
        total_processos=len(items),
        quantidade_processos=len(items),
        unidade=request.unidade,
        processo_ids=request.processo_ids,
        regra_ids=request.regra_ids,
    )


def executar_lote(items: list[dict[str, Any]], questionario) -> None:
    """Executa um documento por vez para manter o uso de memória limitado."""
    for item in items:
        try:
            pdf_bytes = ler_pdf_referenciado(item["pdf_reference"])
            if not is_valid_pdf_signature(pdf_bytes):
                raise ValueError("Arquivo não possui assinatura PDF válida")
            if is_password_protected_pdf(pdf_bytes):
                raise ValueError("PDF protegido por senha não é suportado")
            run_analysis(
                job_id=item["job_id"],
                pdf_bytes=pdf_bytes,
                original_filename=item["filename"],
                questionario=questionario,
                processo_id=item["processo_id"],
            )
        except Exception as error:
            update_job_status(
                item["job_id"],
                JobStatus.FALHOU,
                error_message=f"[{type(error).__name__}] {str(error)[:300]}",
            )


def montar_resposta_status(correicao: dict[str, Any]) -> CorreicaoStatusResponse:
    correicao_id = str(correicao.get("correicao_id", correicao["_id"]))
    created_at = correicao.get("created_at")
    if isinstance(created_at, datetime):
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        else:
            created_at = created_at.astimezone(timezone.utc)
    jobs_data = get_correicao_jobs(correicao_id)
    jobs = [
        CorreicaoJobResponse(
            job_id=job["job_id"],
            processo_id=job["processo_id"],
            arquivo=job["original_filename"],
            status=JobStatus(job["status"]),
            total_paginas=job.get("total_pages"),
            error_message=job.get("error_message"),
        )
        for job in jobs_data
    ]
    terminal = {JobStatus.CONCLUIDO, JobStatus.REVISAO_NECESSARIA, JobStatus.FALHOU}
    completed = sum(job.status in terminal and job.status != JobStatus.FALHOU for job in jobs)
    failed = sum(job.status == JobStatus.FALHOU for job in jobs)
    if not jobs:
        status = "sem_processos"
    elif jobs and completed + failed == len(jobs):
        status = "concluida_com_falhas" if failed and completed else "falhou" if failed else "concluida"
    elif any(job.status != JobStatus.RECEBIDO for job in jobs):
        status = "em_andamento"
    else:
        status = "recebida"

    # Uma execução sem atualização recente foi interrompida (por exemplo, após
    # reinício do servidor) e não deve continuar ocupando o acompanhamento.
    if jobs and status in {"recebida", "em_andamento"}:
        timestamps = [
            job.get("updated_at") or job.get("started_at") or job.get("created_at")
            for job in jobs_data
        ]
        timestamps = [value for value in timestamps if isinstance(value, datetime)]
        if timestamps:
            latest = max(value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value for value in timestamps)
            if datetime.now(timezone.utc) - latest > timedelta(minutes=10):
                status = "interrompida"

    return CorreicaoStatusResponse(
        correicao_id=correicao_id,
        status=status,
        created_at=created_at,
        quantidade_processos=len(jobs),
        unidade=correicao.get("unidade"),
        total_processos=len(jobs),
        processos_concluidos=completed,
        processos_falhos=failed,
        processo_ids=correicao["processo_ids"],
        regra_ids=correicao["regra_ids"],
        jobs=jobs,
    )


@router.get("", response_model=list[CorreicaoStatusResponse])
async def listar_correicoes() -> list[CorreicaoStatusResponse]:
    """Lista execuções recentes para o dashboard localizar a correição ativa."""
    return [montar_resposta_status(correicao) for correicao in listar_correicoes_db()]


@router.get("/{correicao_id}", response_model=CorreicaoStatusResponse)
async def consultar_correicao(correicao_id: str) -> CorreicaoStatusResponse:
    """Retorna progresso e status dos jobs associados à correição."""
    correicao = get_correicao(correicao_id)
    if correicao is None:
        raise HTTPException(status_code=404, detail=f"Correição não encontrada: {correicao_id}")
    return montar_resposta_status(correicao)
