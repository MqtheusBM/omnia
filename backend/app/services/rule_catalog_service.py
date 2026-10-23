"""Catálogo compartilhado de regras executáveis pela API."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.models.database import listar_regras_personalizadas, salvar_regra_personalizada

from app.models.schemas import Pergunta, Questionario

RULES_FILE = Path(__file__).resolve().parent.parent / "questionarios" / "regras_correcionais_v1.json"


def listar_regras() -> list[dict[str, Any]]:
    return [*json.loads(RULES_FILE.read_text(encoding="utf-8")), *listar_regras_personalizadas()]


def salvar_regra(regra: dict) -> dict:
    """Persiste regra criada no fluxo assistido por IA."""
    salvar_regra_personalizada(regra)
    return {key: value for key, value in regra.items() if key != "created_at"}


def montar_questionario(regra_ids: list[str]) -> Questionario:
    regras = {regra["id"]: regra for regra in listar_regras()}
    ausentes = [regra_id for regra_id in regra_ids if regra_id not in regras]
    if ausentes:
        raise ValueError(f"Regras não disponíveis para execução: {', '.join(ausentes)}")

    perguntas = []
    for regra_id in regra_ids:
        regra = regras[regra_id]
        detalhes = [f"Critério: {regra['descricao']}"]
        if regra.get("passos"):
            detalhes.append("Passos de verificação: " + " ".join(regra["passos"]))
        cenarios = [
            ("Atende", regra.get("cenario_atende")),
            ("Não atende", regra.get("cenario_nao_atende")),
            ("Não se encaixa", regra.get("cenario_nao_se_encaixa")),
        ]
        detalhes.extend(f"{nome}: {texto}" for nome, texto in cenarios if texto)
        perguntas.append(
            Pergunta(
                id=regra_id,
                texto=(
                    f"A condição da regra {regra_id} ({regra['nome']}) está presente? "
                    "Responda Sim quando houver indício da condição. " + " ".join(detalhes)
                ),
            )
        )
    suffix = "-".join(regra_ids)
    return Questionario(
        id=f"regras-{suffix}",
        versao="1.0",
        titulo="Regras correicionais selecionadas",
        perguntas=perguntas,
    )
