"""Upload the local process corpus to the configured private GCS bucket."""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402

_PROCESS_FILE = re.compile(r"^processo-\d{20}\.pdf$", re.IGNORECASE)


def main() -> int:
    settings = get_settings()
    source_dir = Path(settings.processos_dir).resolve()
    if not source_dir.is_dir():
        print("Pasta local de processos não encontrada.", file=sys.stderr)
        return 1
    if not settings.gcs_bucket_processos:
        print("GCS_BUCKET_PROCESSOS não está configurado.", file=sys.stderr)
        return 1
    if settings.storage_backend.lower() != "gcs":
        print("Configure STORAGE_BACKEND=gcs antes do upload.", file=sys.stderr)
        return 1

    files = sorted(
        (
            path
            for path in source_dir.iterdir()
            if path.is_file()
            and not path.is_symlink()
            and _PROCESS_FILE.fullmatch(path.name)
        ),
        key=lambda path: path.name.lower(),
    )
    if not files:
        print("Nenhum PDF com nome processo-<20 dígitos>.pdf foi encontrado.", file=sys.stderr)
        return 1

    try:
        from google.api_core.exceptions import PreconditionFailed
        from google.cloud import storage

        client = storage.Client(project=settings.google_cloud_project or None)
        bucket = client.bucket(settings.gcs_bucket_processos)
        prefix = settings.gcs_processos_prefix.strip("/")
        uploaded = 0
        skipped = 0
        total_bytes = 0

        for index, path in enumerate(files, start=1):
            object_name = f"{prefix}/{path.name}" if prefix else path.name
            blob = bucket.blob(object_name)
            try:
                blob.upload_from_filename(
                    str(path),
                    content_type="application/pdf",
                    if_generation_match=0,
                )
                uploaded += 1
                total_bytes += path.stat().st_size
            except PreconditionFailed:
                skipped += 1

            if index % 10 == 0 or index == len(files):
                print(f"Processados {index}/{len(files)} PDFs...")

    except Exception as error:
        code = getattr(error, "code", None)
        detail = f" código HTTP {code}" if code else ""
        print(
            f"Upload interrompido ({type(error).__name__}{detail}). "
            "Verifique as credenciais e permissões no bucket.",
            file=sys.stderr,
        )
        return 1

    print(
        f"Upload concluído: {uploaded} enviados, {skipped} já existentes, "
        f"{total_bytes / (1024 ** 2):.1f} MiB enviados."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
