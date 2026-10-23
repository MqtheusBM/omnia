"""
Serviço de OCR com Google Document AI — Enterprise Document OCR.

Responsável por enviar o PDF ao processador Document AI e retornar
o resultado estruturado em OCRDocument com texto separado por página.

PDFs acima do limite online (~15 páginas) são fatiados em chunks,
processados sequencialmente e unificados num único OCRDocument.
"""

from __future__ import annotations

import io
import time

from google.api_core.client_options import ClientOptions
from google.cloud import documentai_v1 as documentai
from pypdf import PdfReader, PdfWriter

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.schemas import OCRDocument, OCRPageResult

logger = get_logger("document_ai")


def process_document_ocr(pdf_bytes: bytes) -> OCRDocument:
    """
    Envia PDF ao Google Document AI e retorna OCRDocument estruturado.

    Se o PDF tiver mais páginas que ``document_ai_online_page_limit``,
    fatia em chunks, processa cada um e unifica o resultado com
    numeração global de páginas.

    Args:
        pdf_bytes: Conteúdo binário do arquivo PDF.

    Returns:
        OCRDocument com texto integral, texto por página, metadados e warnings.
    """
    settings = get_settings()
    page_limit = settings.document_ai_online_page_limit

    opts = ClientOptions(
        api_endpoint=f"{settings.document_ai_location}-documentai.googleapis.com"
    )
    client = documentai.DocumentProcessorServiceClient(client_options=opts)
    processor_name = client.processor_path(
        settings.google_cloud_project,
        settings.document_ai_location,
        settings.document_ai_processor_id,
    )

    chunks = _split_pdf_into_chunks(pdf_bytes, page_limit)
    total_chunks = len(chunks)

    logger.info(
        "Iniciando OCR via Document AI",
        extra={
            "status": "ocr_start",
            "chunks": total_chunks,
            "chunk_size": page_limit,
        },
    )
    start_time = time.time()

    all_pages: list[OCRPageResult] = []
    all_warnings: list[str] = []
    text_parts: list[str] = []
    mime_type = "application/pdf"
    page_offset = 0

    for chunk_index, chunk_bytes in enumerate(chunks):
        page_start = page_offset + 1
        page_end = page_offset + _count_pdf_pages(chunk_bytes)

        logger.info(
            "Processando chunk OCR",
            extra={
                "status": "ocr_chunk",
                "chunk": f"{chunk_index + 1}/{total_chunks}",
                "pages": f"{page_start}-{page_end}",
            },
        )

        chunk_result = _process_single_chunk(
            client=client,
            processor_name=processor_name,
            pdf_bytes=chunk_bytes,
            page_offset=page_offset,
            timeout=settings.ocr_timeout_seconds,
        )

        all_pages.extend(chunk_result["pages"])
        all_warnings.extend(chunk_result["warnings"])
        if chunk_result["full_text"]:
            text_parts.append(chunk_result["full_text"])
        if chunk_result["mime_type"]:
            mime_type = chunk_result["mime_type"]

        page_offset = page_end

    duration_ms = int((time.time() - start_time) * 1000)
    logger.info(
        "OCR concluído",
        extra={
            "status": "ocr_done",
            "duration_ms": duration_ms,
            "chunks": total_chunks,
            "total_pages": len(all_pages),
        },
    )

    return OCRDocument(
        full_text="\n".join(text_parts),
        pages=all_pages,
        total_pages=len(all_pages),
        processing_metadata={
            "duration_ms": duration_ms,
            "processor": settings.document_ai_processor_id,
            "mime_type": mime_type,
            "chunks": total_chunks,
            "chunk_size": page_limit,
        },
        warnings=all_warnings,
    )


def _split_pdf_into_chunks(pdf_bytes: bytes, page_limit: int) -> list[bytes]:
    """Fatia o PDF em chunks de no máximo ``page_limit`` páginas."""
    reader = PdfReader(io.BytesIO(pdf_bytes))
    total_pages = len(reader.pages)

    if total_pages <= page_limit:
        return [pdf_bytes]

    chunks: list[bytes] = []
    for start in range(0, total_pages, page_limit):
        writer = PdfWriter()
        end = min(start + page_limit, total_pages)
        for page_index in range(start, end):
            writer.add_page(reader.pages[page_index])
        buffer = io.BytesIO()
        writer.write(buffer)
        chunks.append(buffer.getvalue())

    return chunks


def _count_pdf_pages(pdf_bytes: bytes) -> int:
    """Conta páginas de um PDF em bytes."""
    return len(PdfReader(io.BytesIO(pdf_bytes)).pages)


def _process_single_chunk(
    *,
    client: documentai.DocumentProcessorServiceClient,
    processor_name: str,
    pdf_bytes: bytes,
    page_offset: int,
    timeout: int,
) -> dict:
    """
    Processa um único chunk no Document AI e retorna páginas com
    numeração global (``page_offset + i + 1``).
    """
    raw_document = documentai.RawDocument(
        content=pdf_bytes,
        mime_type="application/pdf",
    )
    request = documentai.ProcessRequest(
        name=processor_name,
        raw_document=raw_document,
    )

    result = client.process_document(request=request, timeout=timeout)
    document = result.document
    warnings: list[str] = []
    pages: list[OCRPageResult] = []

    for i, page in enumerate(document.pages):
        page_number = page_offset + i + 1
        page_text = _extract_page_text(document.text, page)
        has_text = bool(page_text.strip())

        if not has_text:
            warnings.append(f"Página {page_number} sem texto detectado")

        pages.append(
            OCRPageResult(
                page_number=page_number,
                text=page_text,
                has_text=has_text,
            )
        )

    return {
        "full_text": document.text or "",
        "pages": pages,
        "warnings": warnings,
        "mime_type": document.mime_type if document.mime_type else "application/pdf",
    }


def _extract_page_text(full_text: str, page: documentai.Document.Page) -> str:
    """
    Extrai o texto de uma página específica usando os text_segments do layout.

    O Document AI armazena o texto completo em document.text e cada página
    contém referências (offsets) para os trechos relevantes.
    """
    text_parts: list[str] = []

    if page.layout and page.layout.text_anchor and page.layout.text_anchor.text_segments:
        for segment in page.layout.text_anchor.text_segments:
            start = int(segment.start_index) if segment.start_index else 0
            end = int(segment.end_index) if segment.end_index else 0
            text_parts.append(full_text[start:end])

    return "".join(text_parts)
