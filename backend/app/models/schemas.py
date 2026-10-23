"""
Schemas Pydantic v2 para o Omnia Backend.

Define todos os modelos de dados: questionários, respostas do LLM,
validação de API e persistência de jobs.
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, field_validator


# ─── Enums ───────────────────────────────────────────────────────────


class RespostaEnum(str, enum.Enum):
    """Valores permitidos para respostas do LLM."""

    SIM = "Sim"
    NAO = "Não"
    NAO_SE_APLICA = "Não se aplica"


class ConfiancaEnum(str, enum.Enum):
    """Nível de confiança da resposta."""

    ALTA = "alta"
    MEDIA = "média"
    BAIXA = "baixa"


class JobStatus(str, enum.Enum):
    """Status do ciclo de vida de um job."""

    RECEBIDO = "recebido"
    OCR_EM_ANDAMENTO = "ocr_em_andamento"
    OCR_CONCLUIDO = "ocr_concluido"
    ANALISE_EM_ANDAMENTO = "analise_em_andamento"
    CONCLUIDO = "concluido"
    FALHOU = "falhou"
    REVISAO_NECESSARIA = "revisao_necessaria"


# ─── Questionário ────────────────────────────────────────────────────


class Pergunta(BaseModel):
    """Uma pergunta individual dentro de um questionário."""

    id: str = Field(..., min_length=1, description="Identificador único da pergunta")
    texto: str = Field(..., min_length=1, description="Texto da pergunta")


class Questionario(BaseModel):
    """Questionário versionado com lista de perguntas."""

    id: str = Field(..., min_length=1)
    versao: str = Field(..., min_length=1)
    titulo: str = Field(..., min_length=1)
    perguntas: list[Pergunta] = Field(..., min_length=1)

    @field_validator("perguntas")
    @classmethod
    def validar_ids_unicos(cls, v: list[Pergunta]) -> list[Pergunta]:
        ids = [p.id for p in v]
        if len(ids) != len(set(ids)):
            duplicados = [pid for pid in ids if ids.count(pid) > 1]
            raise ValueError(f"IDs de perguntas duplicados: {set(duplicados)}")
        return v


# ─── OCR ─────────────────────────────────────────────────────────────


class OCRPageResult(BaseModel):
    """Resultado do OCR para uma única página."""

    page_number: int = Field(..., ge=1)
    text: str = ""
    has_text: bool = True


class OCRDocument(BaseModel):
    """Resultado completo do OCR de um documento."""

    full_text: str = ""
    pages: list[OCRPageResult] = Field(default_factory=list)
    total_pages: int = 0
    processing_metadata: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


# ─── Resposta do LLM ────────────────────────────────────────────────


class RespostaItem(BaseModel):
    """Uma resposta individual do LLM a uma pergunta do questionário."""

    pergunta_id: str
    resposta: RespostaEnum
    paginas: list[int] = Field(..., min_length=1)
    evidencia: str = ""
    confianca: ConfiancaEnum = ConfiancaEnum.MEDIA
    observacao: str | None = None


class RegraVioladaItem(BaseModel):
    """Uma regra avaliada pelo LLM no formato de saída do prompt."""

    id_da_regra: str
    se_aplica: bool
    justificativa_baseada_no_texto: str


class LLMRawResponse(BaseModel):
    """Formato bruto da resposta esperada do Gemini (conforme prompt de saída)."""

    datas_identificadas: list[str] = Field(default_factory=list)
    ultima_movimentacao_data: str | None = None
    dias_inativo: int | None = None
    regras_violadas: list[RegraVioladaItem] = Field(default_factory=list)


class LLMAnalysis(BaseModel):
    """Análise completa retornada pelo serviço Gemini, após parsing."""

    processo_id: str | None = None
    questionario_id: str
    modelo: str
    versao_prompt: str
    respostas: list[RespostaItem]


# ─── Validação ───────────────────────────────────────────────────────


class AuditEntry(BaseModel):
    """Registro de alteração feita pelo validador sobre uma resposta."""

    pergunta_id: str
    campo_alterado: str
    valor_original: str
    valor_corrigido: str
    motivo: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ValidatedAnalysis(BaseModel):
    """Resultado final validado e auditável."""

    processo_id: str | None = None
    questionario_id: str
    modelo: str
    versao_prompt: str
    respostas: list[RespostaItem]
    revisao_necessaria: bool = False
    audit_log: list[AuditEntry] = Field(default_factory=list)


class RelatorioCorreicional(BaseModel):
    """Relatório institucional em seções para revisão humana no frontend."""

    titulo: str = "Relatório de Correição Ordinária"
    identificacao_unidade: str
    apresentacao: str
    objetivo: str
    informacoes_relevantes: list[str] = Field(default_factory=list)
    evolucao_unidade: list[str] = Field(default_factory=list)
    achados: list[str] = Field(default_factory=list)
    consideracoes_finais: list[str] = Field(default_factory=list)
    determinacoes: list[str] = Field(default_factory=list)
    recomendacoes: list[str] = Field(default_factory=list)
    conclusao: str
    dados_pendentes: list[str] = Field(default_factory=list)
    requer_revisao_humana: bool = True


# ─── API Responses ───────────────────────────────────────────────────


class JobCreatedResponse(BaseModel):
    """Resposta ao criar um novo job."""

    job_id: str
    status: JobStatus = JobStatus.RECEBIDO
    processo_id: str | None = None


class JobStatusResponse(BaseModel):
    """Resposta ao consultar status de um job."""

    job_id: str
    status: JobStatus
    processo_id: str | None = None
    total_paginas: int | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None


class JobResultResponse(BaseModel):
    """Resposta final completa de um job."""

    job_id: str
    status: JobStatus
    total_paginas: int
    questionario_id: str
    modelo: str
    versao_prompt: str
    revisao_necessaria: bool = False
    respostas: list[RespostaItem]
    relatorio: RelatorioCorreicional | None = None
    aviso: str = Field(
        default="Este resultado é apoio à triagem e exige revisão humana conforme política do usuário."
    )


class HealthResponse(BaseModel):
    """Resposta do healthcheck."""

    status: str = "ok"
    version: str = "0.1.0"
    service: str = "omnia-backend"


class ProcessoCatalogoResponse(BaseModel):
    processo_id: str
    numero: str
    arquivo: str
    tamanho_bytes: int
    codigo_origem_cnj: str


class CorreicaoCreateRequest(BaseModel):
    quantidade_processos: int = Field(..., ge=1)
    unidade: str | None = None
    processo_ids: list[str] = Field(..., min_length=1)
    regra_ids: list[str] = Field(..., min_length=1)

    @field_validator("processo_ids", "regra_ids")
    @classmethod
    def validar_ids_unicos(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("A lista contém identificadores duplicados")
        return values


class CorreicaoCreatedResponse(BaseModel):
    correicao_id: str
    status: str
    total_processos: int
    quantidade_processos: int
    unidade: str | None = None
    processo_ids: list[str]
    regra_ids: list[str]


class CorreicaoJobResponse(BaseModel):
    job_id: str
    processo_id: str
    arquivo: str
    status: JobStatus
    total_paginas: int | None = None
    error_message: str | None = None


class CorreicaoStatusResponse(BaseModel):
    correicao_id: str
    status: str
    created_at: datetime | None = None
    quantidade_processos: int
    unidade: str | None = None
    total_processos: int
    processos_concluidos: int
    processos_falhos: int
    processo_ids: list[str]
    regra_ids: list[str]
    jobs: list[CorreicaoJobResponse]


class RegraDraftRequest(BaseModel):
    instrucao: str = Field(..., min_length=10, max_length=4000)
    atende: str = Field(..., min_length=3, max_length=2000)
    nao_atende: str = Field(..., min_length=3, max_length=2000)
    nao_se_encaixa: str = Field(..., min_length=3, max_length=2000)
    ajustes: str | None = Field(default=None, max_length=2000)


class RegraDraftResponse(BaseModel):
    passos: list[str] = Field(..., min_length=3, max_length=10)


class RegraCreateRequest(RegraDraftRequest):
    nome: str = Field(..., min_length=3, max_length=160)
    descricao: str = Field(..., min_length=10, max_length=1000)
    passos: list[str] = Field(..., min_length=3, max_length=10)
