"""Catalogação segura dos PDFs locais ou armazenados no GCS."""

from __future__ import annotations

import re
from pathlib import Path

from app.core.config import get_settings
from app.services.storage_service import get_storage_service

_PROCESS_FILE = re.compile(r"^processo-(\d{20})\.pdf$", re.IGNORECASE)


def formatar_numero_cnj(digits: str) -> str:
    """Formata os 20 dígitos CNJ presentes nos nomes dos arquivos."""
    if len(digits) != 20 or not digits.isdigit():
        raise ValueError("O número CNJ deve conter 20 dígitos")
    return f"{digits[:7]}-{digits[7:9]}.{digits[9:13]}.{digits[13]}.{digits[14:16]}.{digits[16:]}"


def listar_processos() -> list[dict[str, str | int]]:
    """Lista PDFs do acervo sem ler conteúdo nem revelar caminhos internos."""
    settings = get_settings()
    processos: list[dict[str, str | int]] = []
    if settings.storage_backend.lower() == "gcs":
        for blob in get_storage_service().listar_pdfs_catalogo():
            name = str(blob["name"])
            prefix = settings.gcs_processos_prefix.strip("/")
            relative_name = name[len(prefix) + 1 :] if prefix else name
            if "/" in relative_name:
                continue
            match = _PROCESS_FILE.fullmatch(relative_name)
            if not match:
                continue
            processos.append(
                _metadados_processo(
                    relative_name, match.group(1), int(blob["size"] or 0)
                )
            )
    else:
        directory = Path(settings.processos_dir).resolve()
        if not directory.is_dir():
            return []
        for path in sorted(directory.glob("*.pdf"), key=lambda item: item.name.lower()):
            match = _PROCESS_FILE.fullmatch(path.name)
            if not match or path.is_symlink():
                continue
            processos.append(_metadados_processo(path.name, match.group(1), path.stat().st_size))

    processos.sort(key=lambda item: str(item["arquivo"]).lower())
    return processos


def referencia_pdf(processo_id: str) -> dict[str, str] | None:
    """Resolve uma referência segura para um PDF local ou objeto do GCS."""
    if not re.fullmatch(r"\d{20}", processo_id):
        return None
    settings = get_settings()
    filename = f"processo-{processo_id}.pdf"
    if settings.storage_backend.lower() == "gcs":
        prefix = settings.gcs_processos_prefix.strip("/")
        object_name = f"{prefix}/{filename}" if prefix else filename
        if get_storage_service().processo_pdf_existe(object_name):
            return {"backend": "gcs", "object_name": object_name}
        return None

    directory = Path(settings.processos_dir).resolve()
    candidate = directory / filename
    if candidate.is_symlink():
        return None
    path = candidate.resolve()
    if path.parent != directory or not path.is_file():
        return None
    return {"backend": "local", "path": str(path)}


def ler_pdf_referenciado(reference: dict[str, str]) -> bytes:
    """Lê os bytes de uma referência produzida por ``referencia_pdf``."""
    if reference.get("backend") == "gcs":
        return get_storage_service().ler_pdf_catalogo(reference["object_name"])
    if reference.get("backend") != "local":
        raise FileNotFoundError("PDF não encontrado no acervo")

    path = Path(reference["path"]).resolve()
    directory = Path(get_settings().processos_dir).resolve()
    if path.parent != directory or path.is_symlink() or not path.is_file():
        raise FileNotFoundError("PDF não encontrado no acervo")
    return path.read_bytes()


def _metadados_processo(filename: str, process_id: str, size: int) -> dict[str, str | int]:
    return {
        "processo_id": process_id,
        "numero": formatar_numero_cnj(process_id),
        "arquivo": filename,
        "tamanho_bytes": size,
        "codigo_origem_cnj": process_id[16:],
    }
