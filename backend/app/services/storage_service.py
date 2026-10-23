"""
Serviço de armazenamento de artefatos.

Suporta dois backends:
- "local": armazenamento em disco para desenvolvimento.
- "gcs": Google Cloud Storage para produção.

PDFs, JSONs brutos do OCR e respostas do LLM são armazenados aqui.
O banco de dados guarda apenas referências (paths/URIs) e hashes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("storage")


class StorageService:
    """Gerencia armazenamento de artefatos com backend configurável."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.backend = self.settings.storage_backend

    def save_pdf(self, job_id: str, pdf_bytes: bytes, filename: str) -> str:
        """Salva PDF original e retorna a referência de armazenamento."""
        path = f"jobs/{job_id}/original/{filename}"
        self._save_bytes(path, pdf_bytes)
        logger.info("PDF salvo", extra={"job_id": job_id})
        return path

    def save_ocr_result(self, job_id: str, ocr_data: dict[str, Any]) -> str:
        """Salva resultado bruto do OCR em JSON."""
        path = f"jobs/{job_id}/ocr/document_ai_result.json"
        content = json.dumps(ocr_data, ensure_ascii=False, indent=2, default=str)
        self._save_bytes(path, content.encode("utf-8"))
        logger.info("OCR salvo", extra={"job_id": job_id})
        return path

    def save_llm_response(self, job_id: str, response_data: dict[str, Any]) -> str:
        """Salva resposta bruta do LLM."""
        path = f"jobs/{job_id}/llm/raw_response.json"
        content = json.dumps(response_data, ensure_ascii=False, indent=2, default=str)
        self._save_bytes(path, content.encode("utf-8"))
        logger.info("Resposta LLM salva", extra={"job_id": job_id})
        return path

    def save_validated_result(self, job_id: str, result_data: dict[str, Any]) -> str:
        """Salva resultado validado final."""
        path = f"jobs/{job_id}/result/validated_result.json"
        content = json.dumps(result_data, ensure_ascii=False, indent=2, default=str)
        self._save_bytes(path, content.encode("utf-8"))
        logger.info("Resultado validado salvo", extra={"job_id": job_id})
        return path

    def save_report(self, job_id: str, report_data: dict[str, Any]) -> str:
        """Salva a minuta estruturada do relatório correicional."""
        path = f"jobs/{job_id}/result/relatorio_correicional.json"
        content = json.dumps(report_data, ensure_ascii=False, indent=2, default=str)
        self._save_bytes(path, content.encode("utf-8"))
        logger.info("Relatório correicional salvo", extra={"job_id": job_id})
        return path

    def _save_bytes(self, path: str, data: bytes) -> None:
        """Salva bytes no backend configurado."""
        if self.backend == "gcs":
            self._save_to_gcs(path, data)
        else:
            self._save_to_local(path, data)

    def _save_to_local(self, path: str, data: bytes) -> None:
        """Salva no sistema de arquivos local."""
        base = Path(self.settings.local_storage_path)
        full_path = base / path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_bytes(data)

    def _save_to_gcs(self, path: str, data: bytes) -> None:
        """Salva no Google Cloud Storage."""
        bucket = self._gcs_bucket()
        blob = bucket.blob(path)
        blob.upload_from_string(data)

    def listar_pdfs_catalogo(self) -> list[dict[str, Any]]:
        """Lista metadados dos PDFs disponíveis no prefixo do acervo no GCS."""
        prefix = self.settings.gcs_processos_prefix.strip("/")
        prefix = f"{prefix}/" if prefix else ""
        return [
            {"name": blob.name, "size": blob.size}
            for blob in self._gcs_bucket().list_blobs(prefix=prefix)
            if blob.name and blob.size is not None
        ]

    def processo_pdf_existe(self, object_name: str) -> bool:
        """Confirma que o objeto solicitado existe dentro do prefixo do acervo."""
        if not self._is_process_catalog_object(object_name):
            return False
        return self._gcs_bucket().blob(object_name).exists()

    def ler_pdf_catalogo(self, object_name: str) -> bytes:
        """Baixa um PDF do acervo, recusando nomes fora do prefixo configurado."""
        if not self._is_process_catalog_object(object_name):
            raise FileNotFoundError("PDF não encontrado no acervo")
        blob = self._gcs_bucket().blob(object_name)
        if not blob.exists():
            raise FileNotFoundError("PDF não encontrado no acervo")
        return blob.download_as_bytes()

    def _gcs_bucket(self):
        """Retorna o bucket configurado usando Application Default Credentials."""
        from google.cloud import storage

        if not self.settings.gcs_bucket_processos:
            raise RuntimeError("GCS_BUCKET_PROCESSOS não configurado")
        client = storage.Client(project=self.settings.google_cloud_project or None)
        return client.bucket(self.settings.gcs_bucket_processos)

    def _is_process_catalog_object(self, object_name: str) -> bool:
        prefix = self.settings.gcs_processos_prefix.strip("/")
        expected_prefix = f"{prefix}/" if prefix else ""
        relative_name = object_name.removeprefix(expected_prefix)
        return (
            object_name.startswith(expected_prefix)
            and relative_name.endswith(".pdf")
            and "/" not in relative_name
            and relative_name not in {"", ".", ".."}
        )


def get_storage_service() -> StorageService:
    """Factory para o serviço de armazenamento."""
    return StorageService()
