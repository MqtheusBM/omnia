"""
Acesso ao banco de dados MongoDB para o Omnia Backend.

Gerencia conexão, coleção de jobs e operações CRUD.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

from app.core.config import get_settings
from app.models.schemas import JobStatus

logger = logging.getLogger("omnia.database")

# Singleton de conexão
_client: MongoClient | None = None
_db: Database | None = None


def get_database() -> Database:
    """Retorna instância do banco MongoDB (lazy init)."""
    global _client, _db
    if _db is None:
        settings = get_settings()
        _client = MongoClient(settings.mongodb_url)
        _db = _client[settings.mongodb_database]
        logger.info("Conexão MongoDB estabelecida", extra={"status": "connected"})
    return _db


def get_jobs_collection() -> Collection:
    """Retorna a coleção de jobs."""
    return get_database()["jobs"]


def get_correicoes_collection() -> Collection:
    """Retorna a coleção de execuções correicionais."""
    return get_database()["correicoes"]


def get_regras_collection() -> Collection:
    """Retorna a coleção de regras criadas pelos usuários."""
    return get_database()["regras"]


def listar_regras_personalizadas() -> list[dict[str, Any]]:
    return list(get_regras_collection().find({}, {"_id": 0}).sort("created_at", 1))


def salvar_regra_personalizada(regra: dict[str, Any]) -> None:
    get_regras_collection().insert_one({**regra, "_id": regra["id"]})


def close_database() -> None:
    """Fecha conexão com o MongoDB."""
    global _client, _db
    if _client:
        _client.close()
        _client = None
        _db = None
        logger.info("Conexão MongoDB encerrada")


# ─── CRUD de Jobs ────────────────────────────────────────────────────


def create_job(
    job_id: str,
    processo_id: str | None,
    questionario_id: str,
    original_filename: str,
    sha256_hash: str,
    total_pages: int | None = None,
    correicao_id: str | None = None,
    regra_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Cria um novo registro de job no banco."""
    now = datetime.now(timezone.utc)
    doc: dict[str, Any] = {
        "_id": job_id,
        "job_id": job_id,
        "processo_id": processo_id,
        "questionario_id": questionario_id,
        "correicao_id": correicao_id,
        "regra_ids": regra_ids or [],
        "original_filename": original_filename,
        "sha256_hash": sha256_hash,
        "status": JobStatus.RECEBIDO.value,
        "total_pages": total_pages,
        "created_at": now,
        "started_at": None,
        "completed_at": None,
        "ocr_duration_ms": None,
        "llm_duration_ms": None,
        "model_used": None,
        "prompt_version": None,
        "raw_llm_response": None,
        "validated_response": None,
        "revisao_necessaria": False,
        "audit_log": [],
        "error_message": None,
        "error_category": None,
        "storage_refs": {},
    }
    get_jobs_collection().insert_one(doc)
    logger.info("Job criado", extra={"job_id": job_id, "status": "recebido"})
    return doc


def create_correicao(document: dict[str, Any]) -> None:
    """Persiste o escopo de uma execução correicional."""
    get_correicoes_collection().insert_one(document)


def get_correicao(correicao_id: str) -> dict[str, Any] | None:
    """Busca uma execução correicional pelo identificador."""
    return get_correicoes_collection().find_one({"_id": correicao_id})


def listar_correicoes(limit: int = 50) -> list[dict[str, Any]]:
    """Lista execuções mais recentes para o painel de acompanhamento."""
    return list(get_correicoes_collection().find({}).sort("created_at", -1).limit(limit))


def get_correicao_jobs(correicao_id: str) -> list[dict[str, Any]]:
    """Retorna apenas os campos operacionais dos jobs de uma correição."""
    return list(
        get_jobs_collection()
        .find(
            {"correicao_id": correicao_id},
            {
                "_id": 0,
                "job_id": 1,
                "processo_id": 1,
                "original_filename": 1,
                "status": 1,
                "total_pages": 1,
                "error_message": 1,
                "created_at": 1,
                "started_at": 1,
                "completed_at": 1,
                "updated_at": 1,
            },
        )
        .sort("original_filename", 1)
    )


def update_job_status(
    job_id: str,
    status: JobStatus,
    **extra_fields: Any,
) -> None:
    """Atualiza status e campos adicionais de um job."""
    update: dict[str, Any] = {"status": status.value, "updated_at": datetime.now(timezone.utc)}
    update.update(extra_fields)

    if status in (JobStatus.CONCLUIDO, JobStatus.FALHOU, JobStatus.REVISAO_NECESSARIA):
        update.setdefault("completed_at", datetime.now(timezone.utc))

    if status == JobStatus.OCR_EM_ANDAMENTO:
        update.setdefault("started_at", datetime.now(timezone.utc))

    get_jobs_collection().update_one({"_id": job_id}, {"$set": update})
    logger.info("Job atualizado", extra={"job_id": job_id, "status": status.value})


def get_job(job_id: str) -> dict[str, Any] | None:
    """Busca um job pelo ID."""
    return get_jobs_collection().find_one({"_id": job_id})


def append_audit_entries(job_id: str, entries: list[dict[str, Any]]) -> None:
    """Adiciona entradas ao log de auditoria de um job."""
    if entries:
        get_jobs_collection().update_one(
            {"_id": job_id},
            {"$push": {"audit_log": {"$each": entries}}},
        )
