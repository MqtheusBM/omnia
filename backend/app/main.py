"""
Ponto de entrada principal do Omnia Backend.

Inicializa FastAPI, configura logging, registra rotas e
gerencia lifecycle do banco de dados.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes_processos import router as processos_router
from app.api.routes_correicoes import router as correicoes_router
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.models.database import close_database, get_database
from app.models.schemas import HealthResponse


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Gerencia startup e shutdown da aplicação."""
    # Startup
    setup_logging()
    get_database()  # Inicializa conexão MongoDB
    yield
    # Shutdown
    close_database()


def create_app() -> FastAPI:
    """Factory da aplicação FastAPI."""
    settings = get_settings()

    app = FastAPI(
        title="Omnia Backend",
        description=(
            "Serviço de análise de processos judiciais com Document AI e Gemini Flash. "
            "⚠️ Este resultado é apoio à triagem e exige revisão humana conforme "
            "política do usuário."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Accept"],
    )

    # Registrar rotas
    app.include_router(processos_router)
    app.include_router(correicoes_router)

    # Healthcheck
    @app.get(
        "/health",
        response_model=HealthResponse,
        tags=["infra"],
        summary="Verificar saúde do serviço",
    )
    async def health() -> HealthResponse:
        return HealthResponse()

    return app


app = create_app()
