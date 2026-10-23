"""
Configuração centralizada do Omnia Backend.

Todas as variáveis de ambiente são carregadas aqui via pydantic-settings.
Nenhum segredo deve ser hardcoded — tudo vem de .env ou variáveis de ambiente do sistema.
"""

from __future__ import annotations

import json
import os
import tempfile
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Raiz do projeto (dois níveis acima deste arquivo)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """Configurações globais da aplicação."""

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Gemini ───────────────────────────────────
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"

    # ── Provedor LLM ──────────────────────────────
    llm_provider: str = "openai"
    openai_api_key: str = ""
    openai_model: str = "gpt-6.1-sol"

    # ── Google Cloud ─────────────────────────────
    google_cloud_project: str = ""
    google_cloud_location: str = "us"
    google_application_credentials: str = ""
    google_application_credentials_json: str = ""

    # ── Document AI ──────────────────────────────
    document_ai_location: str = "us"
    document_ai_processor_id: str = ""
    document_ai_online_page_limit: int = 15

    # ── Google Cloud Storage ─────────────────────
    gcs_bucket_processos: str = ""
    gcs_processos_prefix: str = "processos"
    storage_backend: str = "local"  # "local" ou "gcs"
    local_storage_path: str = str(PROJECT_ROOT / "storage")

    # ── MongoDB ──────────────────────────────────
    mongodb_url: str = "mongodb://localhost:27017"
    mongodb_database: str = "omnia"

    # ── Limites ──────────────────────────────────
    max_pdf_size_mb: int = 100
    # Limite do pipeline completo; o OCR processa documentos em partes menores.
    max_pages_per_request: int = 500
    max_questions_per_questionnaire: int = 50
    processos_dir: str = str(PROJECT_ROOT.parent / "processos")
    max_processes_per_correction: int = 30

    # ── CORS ──────────────────────────────────────
    cors_origins: str = "http://localhost:4200,http://127.0.0.1:4200"

    @property
    def cors_origin_list(self) -> list[str]:
        """Origens autorizadas, separadas por vírgula, para chamadas do frontend."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    # ── Timeouts (segundos) ──────────────────────
    ocr_timeout_seconds: int = 300
    llm_timeout_seconds: int = 3600

    # ── Observabilidade ──────────────────────────
    log_level: str = "INFO"

    @property
    def max_pdf_size_bytes(self) -> int:
        return self.max_pdf_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    """Retorna instância cacheada das configurações."""
    settings = Settings()
    if settings.google_application_credentials_json:
        try:
            credentials = json.loads(settings.google_application_credentials_json)
        except json.JSONDecodeError as error:
            raise RuntimeError(
                "GOOGLE_APPLICATION_CREDENTIALS_JSON deve conter um JSON válido"
            ) from error
        if not isinstance(credentials, dict):
            raise RuntimeError(
                "GOOGLE_APPLICATION_CREDENTIALS_JSON deve conter credenciais de serviço"
            )
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".json",
            prefix="omnia-google-credentials-",
            delete=False,
        ) as credential_file:
            json.dump(credentials, credential_file)
        if os.name != "nt":
            os.chmod(credential_file.name, 0o600)
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credential_file.name
    elif settings.google_application_credentials and not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = settings.google_application_credentials
    return settings
