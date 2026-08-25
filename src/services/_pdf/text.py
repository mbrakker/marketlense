from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pymupdf as fitz
from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError, PdfStreamError

from src.contracts.pdf_context import (
    PdfContext,
    PdfContextBuildRequest,
    PdfContextBuildResponse,
)
from src.contracts.pdf_ocr import (
    PdfHtmlRenderRequest,
    PdfHtmlRenderResponse,
    PdfImageRenderRequest,
    PdfImageRenderResponse,
    PdfOcrChunk,
    PdfOcrSplitRequest,
    PdfOcrSplitResponse,
    PdfTextRenderRequest,
    PdfTextRenderResponse,
)
from src.contracts.pdf_text import (
    PdfTextContainsRequest,
    PdfTextContainsResponse,
    PdfTextExtractRequest,
    PdfTextExtractResponse,
    PdfTextSample,
    PdfTextSampleRequest,
    PdfTextSampleResponse,
)
from src.contracts.pdf_utils import (
    PdfEofCheckRequest,
    PdfEofCheckResponse,
    PdfInfoRequest,
    PdfInfoResponse,
    PdfIntegrityCheckRequest,
    PdfIntegrityCheckResponse,
)
from src.contracts.run_context import RunContext
from src.utils.clock import utc_now_iso
from src.utils.errors import AppError
from src.utils.logging import log_event
from src.utils.pdf_utils import pdf_has_eof_marker as _pdf_has_eof_marker

from .page_artifacts import create_page_artifact_cache
from .shared import EOF_TAIL_BYTES, logger

PDF_TEXT_EXCEPTIONS = (OSError, RuntimeError, ValueError, TypeError, AttributeError)


def check_pdf_eof(request: PdfEofCheckRequest, ctx: RunContext) -> PdfEofCheckResponse:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="pdf_eof_check_start",
            module=logger.name,
            fields={"path": request.path, "tail_bytes": EOF_TAIL_BYTES},
        )
    )
    try:
        path = Path(request.path)
        with path.open("rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            if size <= 0:
                data = b""
            else:
                start = max(size - EOF_TAIL_BYTES, 0)
                fh.seek(start)
                data = fh.read()
    except FileNotFoundError as exc:
        raise AppError(
            code="pdf_not_found",
            message=f"PDF not found: {request.path}",
            cause=exc,
            retryable=False,
        ) from exc
    except OSError as exc:
        raise AppError(
            code="pdf_read_failed",
            message=f"Failed to read PDF bytes: {request.path}",
            cause=exc,
            retryable=True,
        ) from exc
    has_eof = _pdf_has_eof_marker(data)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="pdf_eof_check_complete",
            module=logger.name,
            fields={
                "path": request.path,
                "has_eof": has_eof,
                "tail_bytes": EOF_TAIL_BYTES,
            },
        )
    )
    return PdfEofCheckResponse(schema_version="1.0", path=request.path, has_eof=has_eof)


def check_pdf_integrity(
    request: PdfIntegrityCheckRequest,
    ctx: RunContext,
) -> PdfIntegrityCheckResponse:
    """Validate deterministic PDF structure without OCR, rendering, or model I/O."""
    path = Path(request.path)
    validator_version = "pdf-integrity-v1"
    try:
        raw = path.read_bytes()
    except FileNotFoundError as exc:
        raise AppError(
            code="pdf_not_found",
            message="PDF integrity validation requires a readable local file",
            cause=exc,
            retryable=False,
        ) from exc
    except OSError as exc:
        raise AppError(
            code="pdf_read_failed",
            message="PDF integrity validation could not read local bytes",
            cause=exc,
            retryable=True,
        ) from exc
    has_header = raw.startswith(b"%PDF-")
    has_eof = _pdf_has_eof_marker(raw[-EOF_TAIL_BYTES:]) if raw else False
    parser_opened = False
    page_count = 0
    failure_code = ""
    if not has_header:
        failure_code = "pdf_missing_header"
    elif not has_eof:
        failure_code = "pdf_missing_eof"
    else:
        try:
            reader = PdfReader(str(path), strict=False)
            page_count = len(reader.pages)
            parser_opened = True
            if page_count < 1:
                failure_code = "pdf_zero_pages"
        except (PdfReadError, PdfStreamError, OSError, RuntimeError, ValueError):
            failure_code = "pdf_parser_open_failed"
    response = PdfIntegrityCheckResponse(
        schema_version="1.0",
        path=str(path),
        size_bytes=len(raw),
        sha256=hashlib.sha256(raw).hexdigest(),
        md5=hashlib.md5(raw).hexdigest(),
        validator_version=validator_version,
        has_pdf_header=has_header,
        has_eof=has_eof,
        parser_opened=parser_opened,
        page_count=page_count,
        failure_code=failure_code,
        retryable=False,
        validated_at_utc=utc_now_iso(),
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="pdf_integrity_checked",
            module=logger.name,
            fields={
                "validator_version": validator_version,
                "size_bytes": response.size_bytes,
                "has_pdf_header": response.has_pdf_header,
                "has_eof": response.has_eof,
                "parser_opened": response.parser_opened,
                "page_count": response.page_count,
                "failure_code": response.failure_code,
            },
        )
    )
    return response


def build_pdf_context(
    request: PdfContextBuildRequest, ctx: RunContext
) -> PdfContextBuildResponse:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="pdf_context_build_start",
            module=logger.name,
            fields={
                "path": request.path,
                "load_fitz": request.load_fitz,
                "load_pypdf": request.load_pypdf,
            },
        )
    )

    fitz_doc = None
    fitz_error = None
    if request.load_fitz:
        try:
            fitz_doc = fitz.open(request.path)
        except (RuntimeError, ValueError, TypeError) as exc:
            fitz_error = str(exc)

    pypdf_reader = None
    pypdf_error = None
    if request.load_pypdf:
        try:
            pypdf_reader = PdfReader(request.path, strict=False)
        except FileNotFoundError as exc:
            raise AppError(
                code="pdf_not_found",
                message=f"PDF not found: {request.path}",
                cause=exc,
                retryable=False,
            ) from exc
        except (PdfReadError, PdfStreamError) as exc:
            pypdf_error = str(exc)
        except PDF_TEXT_EXCEPTIONS as exc:
            pypdf_error = str(exc)

    context = PdfContext(
        schema_version="1.0",
        path=request.path,
        fitz_doc=fitz_doc,
        pypdf_reader=pypdf_reader,
        page_artifact_cache=create_page_artifact_cache()
        if fitz_doc is not None
        else None,
    )

    logger.info(
        log_event(
            ctx,
            role="service",
            event="pdf_context_build_complete",
            module=logger.name,
            fields={
                "fitz_ready": fitz_doc is not None,
                "pypdf_ready": pypdf_reader is not None,
                "fitz_error": fitz_error or "",
                "pypdf_error": pypdf_error or "",
            },
        )
    )

    return PdfContextBuildResponse(
        schema_version="1.0",
        context=context,
        fitz_error=fitz_error,
        pypdf_error=pypdf_error,
    )


def extract_pdf_info(request: PdfInfoRequest, ctx: RunContext) -> PdfInfoResponse:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="pdf_info_extract_start",
            module=logger.name,
            fields={
                "path": request.path,
                "using_context": bool(
                    request.pdf_context and request.pdf_context.pypdf_reader
                ),
            },
        )
    )
    reader = request.pdf_context.pypdf_reader if request.pdf_context else None
    owns_reader = False
    if reader is None:
        try:
            reader = PdfReader(request.path, strict=False)
            owns_reader = True
        except FileNotFoundError as exc:
            raise AppError(
                code="pdf_not_found",
                message=f"PDF not found: {request.path}",
                cause=exc,
                retryable=False,
            ) from exc
        except (PdfReadError, PdfStreamError) as exc:
            raise AppError(
                code="pdf_info_read_failed",
                message=f"Failed to read PDF for info: {request.path}",
                cause=exc,
                retryable=True,
            ) from exc
        except PDF_TEXT_EXCEPTIONS as exc:
            raise AppError(
                code="pdf_info_read_failed",
                message=f"Failed to read PDF for info: {request.path}",
                cause=exc,
                retryable=True,
            ) from exc
    try:
        page_count = len(reader.pages)
        metadata = _normalize_metadata(reader.metadata)
        response = PdfInfoResponse(
            schema_version="1.0",
            path=request.path,
            page_count=page_count,
            metadata=metadata,
        )
        logger.info(
            log_event(
                ctx,
                role="service",
                event="pdf_info_extract_complete",
                module=logger.name,
                fields={
                    "path": request.path,
                    "page_count": page_count,
                    "metadata_keys": list(metadata.keys()),
                },
            )
        )
        return response
    finally:
        if owns_reader and reader is not None:
            _close_pypdf_reader(reader)


def extract_pdf_text(
    request: PdfTextExtractRequest, ctx: RunContext
) -> PdfTextExtractResponse:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="pdf_text_extract_start",
            module=logger.name,
            fields={
                "path": request.path,
                "max_pages": request.max_pages,
                "max_chars": request.max_chars,
                "using_context": bool(
                    request.pdf_context and request.pdf_context.pypdf_reader
                ),
            },
        )
    )
    reader = request.pdf_context.pypdf_reader if request.pdf_context else None
    owns_reader = False
    if reader is None:
        try:
            reader = PdfReader(request.path, strict=False)
            owns_reader = True
        except FileNotFoundError as exc:
            raise AppError(
                code="pdf_not_found",
                message=f"PDF not found: {request.path}",
                cause=exc,
                retryable=False,
            ) from exc
        except (PdfReadError, PdfStreamError) as exc:
            raise AppError(
                code="pdf_read_failed",
                message=f"Failed to read PDF: {request.path}",
                cause=exc,
                retryable=True,
            ) from exc
        except PDF_TEXT_EXCEPTIONS as exc:
            raise AppError(
                code="pdf_read_failed",
                message=f"Failed to read PDF: {request.path}",
                cause=exc,
                retryable=True,
            ) from exc

    try:
        pages = min(len(reader.pages), max(request.max_pages, 0))
        chunks = []
        for i in range(pages):
            try:
                text = reader.pages[i].extract_text() or ""
            except PDF_TEXT_EXCEPTIONS:
                text = ""
            chunks.append(text)
        raw_text = "\n\n".join(chunks)
        text_out = raw_text[: max(request.max_chars, 0)]
        density = _compute_text_density(raw_text, pages)
        response = PdfTextExtractResponse(
            schema_version="1.0",
            text=text_out,
            pages_extracted=pages,
            char_count=len(text_out),
            text_density=density,
        )
        logger.info(
            log_event(
                ctx,
                role="service",
                event="pdf_text_extract_complete",
                module=logger.name,
                fields={
                    "pages": response.pages_extracted,
                    "chars": response.char_count,
                    "text_density": response.text_density,
                },
            )
        )
        return response
    finally:
        if owns_reader and reader is not None:
            _close_pypdf_reader(reader)


def sample_pdf_text(
    request: PdfTextSampleRequest, ctx: RunContext
) -> PdfTextSampleResponse:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="pdf_text_sample_start",
            module=logger.name,
            fields={
                "path": request.path,
                "page_indices": request.page_indices,
                "using_context": bool(
                    request.pdf_context and request.pdf_context.pypdf_reader
                ),
            },
        )
    )
    reader = request.pdf_context.pypdf_reader if request.pdf_context else None
    owns_reader = False
    if reader is None:
        try:
            reader = PdfReader(request.path, strict=False)
            owns_reader = True
        except FileNotFoundError as exc:
            raise AppError(
                code="pdf_not_found",
                message=f"PDF not found: {request.path}",
                cause=exc,
                retryable=False,
            ) from exc
        except (PdfReadError, PdfStreamError) as exc:
            raise AppError(
                code="pdf_read_failed",
                message=f"Failed to read PDF: {request.path}",
                cause=exc,
                retryable=True,
            ) from exc
        except PDF_TEXT_EXCEPTIONS as exc:
            raise AppError(
                code="pdf_read_failed",
                message=f"Failed to read PDF: {request.path}",
                cause=exc,
                retryable=True,
            ) from exc

    try:
        page_count = len(reader.pages)
        samples = []
        for idx in request.page_indices:
            if idx < 0 or idx >= page_count:
                continue
            text = _extract_text(reader, idx)
            char_count = len(text)
            word_count = _meaningful_word_count(text)
            confidence_score = _score_native_text_confidence(
                text=text,
                char_count=char_count,
                word_count=word_count,
            )
            samples.append(
                PdfTextSample(
                    page_index=idx,
                    page_number=idx + 1,
                    char_count=char_count,
                    has_text=bool(text.strip()),
                    word_count=word_count,
                    confidence_score=confidence_score,
                )
            )
        any_text = any(sample.has_text for sample in samples)
        document_confidence_score = round(
            (
                sum(float(sample.confidence_score) for sample in samples)
                / float(len(samples))
            )
            if samples
            else 0.0,
            3,
        )
        response = PdfTextSampleResponse(
            schema_version="1.0",
            samples=samples,
            any_text=any_text,
            document_confidence_score=document_confidence_score,
        )
        logger.info(
            log_event(
                ctx,
                role="service",
                event="pdf_text_sample_complete",
                module=logger.name,
                fields={
                    "sample_count": len(samples),
                    "any_text": any_text,
                    "page_indices": [sample.page_index for sample in samples],
                    "page_confidence_scores": [
                        round(float(sample.confidence_score), 3) for sample in samples
                    ],
                    "document_confidence_score": document_confidence_score,
                },
            )
        )
        return response
    finally:
        if owns_reader and reader is not None:
            _close_pypdf_reader(reader)


def render_text_pdf(
    request: PdfTextRenderRequest,
    ctx: RunContext,
) -> PdfTextRenderResponse:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="pdf_text_render_start",
            module=logger.name,
            fields={
                "output_path": request.output_path,
                "page_count": len(request.pages),
            },
        )
    )
    output_path = Path(request.output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    try:
        for page in sorted(request.pages, key=lambda item: item.page_number):
            _append_text_page(doc, page.text)
        doc.save(output_path.as_posix())
    except (RuntimeError, ValueError, TypeError, OSError) as exc:
        raise AppError(
            code="pdf_text_render_failed",
            message=f"Failed to render OCR PDF: {request.output_path}",
            cause=exc,
            retryable=False,
        ) from exc
    finally:
        doc.close()
    response = PdfTextRenderResponse(
        schema_version="1.0",
        output_path=str(output_path),
        rendered_page_count=len(request.pages),
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="pdf_text_render_complete",
            module=logger.name,
            fields={
                "output_path": response.output_path,
                "rendered_page_count": response.rendered_page_count,
            },
        )
    )
    return response


def render_image_pdf(
    request: PdfImageRenderRequest,
    ctx: RunContext,
) -> PdfImageRenderResponse:
    """Render ordered encoded images into a locally verified PDF."""
    logger.info(
        log_event(
            ctx,
            role="service",
            event="pdf_image_render_start",
            module=logger.name,
            fields={
                "output_path": request.output_path,
                "image_count": len(request.image_bytes),
            },
        )
    )
    output_path = Path(request.output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    document = fitz.open()
    try:
        for image in request.image_bytes:
            pixmap = fitz.Pixmap(image)
            page = document.new_page(width=pixmap.width, height=pixmap.height)
            page.insert_image(page.rect, stream=image)
        document.save(output_path.as_posix(), garbage=4, deflate=True)
        rendered_page_count = _rendered_pdf_page_count(output_path)
        if rendered_page_count != len(request.image_bytes) or rendered_page_count < 1:
            raise ValueError("rendered image PDF page count did not match input")
    except (fitz.FileDataError, OSError, RuntimeError, TypeError, ValueError) as exc:
        raise AppError(
            code="pdf_image_render_failed",
            message=f"Failed to render image PDF: {request.output_path}",
            cause=exc,
            retryable=False,
        ) from exc
    finally:
        document.close()
    response = PdfImageRenderResponse(
        schema_version="1.0",
        output_path=str(output_path),
        rendered_page_count=rendered_page_count,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="pdf_image_render_complete",
            module=logger.name,
            fields={
                "output_path": response.output_path,
                "rendered_page_count": response.rendered_page_count,
            },
        )
    )
    return response


def render_html_pdf(
    request: PdfHtmlRenderRequest,
    ctx: RunContext,
) -> PdfHtmlRenderResponse:
    """Render sanitized local HTML into a bounded, verified PDF."""
    logger.info(
        log_event(
            ctx,
            role="service",
            event="pdf_html_render_start",
            module=logger.name,
            fields={
                "output_path": request.output_path,
                "html_char_count": len(request.html),
                "max_pages": request.max_pages,
            },
        )
    )
    output_path = Path(request.output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        story = fitz.Story(html=request.html)
        writer = fitz.DocumentWriter(output_path.as_posix())
        page_rect = fitz.paper_rect("a4")
        content_rect = page_rect + (36, 36, -36, -36)
        more = True
        page_count = 0
        while more and page_count < request.max_pages:
            device = writer.begin_page(page_rect)
            more, _ = story.place(content_rect)
            story.draw(device)
            writer.end_page()
            page_count += 1
        writer.close()
        if more:
            raise ValueError("rendered HTML exceeded the configured page limit")
        rendered_page_count = _rendered_pdf_page_count(output_path)
        if rendered_page_count != page_count or rendered_page_count < 1:
            raise ValueError("rendered HTML PDF page count was invalid")
    except (fitz.FileDataError, OSError, RuntimeError, TypeError, ValueError) as exc:
        raise AppError(
            code="pdf_html_render_failed",
            message=f"Failed to render HTML PDF: {request.output_path}",
            cause=exc,
            retryable=False,
        ) from exc
    response = PdfHtmlRenderResponse(
        schema_version="1.0",
        output_path=str(output_path),
        rendered_page_count=rendered_page_count,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="pdf_html_render_complete",
            module=logger.name,
            fields={
                "output_path": response.output_path,
                "rendered_page_count": response.rendered_page_count,
            },
        )
    )
    return response


def pdf_contains_text(
    request: PdfTextContainsRequest,
    ctx: RunContext | None = None,
) -> PdfTextContainsResponse:
    """Return whether a readable rendered page contains normalized text."""
    expected = " ".join(request.text.split())
    if ctx is not None:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="pdf_text_contains_start",
                module=logger.name,
                fields={
                    "path": request.path,
                    "expected_char_count": len(expected),
                },
            )
        )
    try:
        with fitz.open(request.path) as document:
            contains_text = bool(expected) and any(
                expected in " ".join(page.get_text("text").split()) for page in document
            )
    except Exception:
        contains_text = False
    response = PdfTextContainsResponse(
        schema_version="1.0", contains_text=contains_text
    )
    if ctx is not None:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="pdf_text_contains_complete",
                module=logger.name,
                fields={
                    "path": request.path,
                    "expected_char_count": len(expected),
                    "contains_text": response.contains_text,
                },
            )
        )
    return response


def _rendered_pdf_page_count(path: Path) -> int:
    with fitz.open(path) as document:
        return document.page_count


def split_pdf_for_ocr(
    request: PdfOcrSplitRequest,
    ctx: RunContext,
) -> PdfOcrSplitResponse:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="pdf_ocr_split_start",
            module=logger.name,
            fields={
                "source_pdf_path": request.source_pdf_path,
                "output_dir": request.output_dir,
                "chunk_page_count": request.chunk_page_count,
            },
        )
    )
    source_pdf_path = Path(request.source_pdf_path)
    if request.chunk_page_count < 1:
        raise AppError(
            code="pdf_ocr_split_invalid_request",
            message="chunk_page_count must be at least 1",
            retryable=False,
        )
    try:
        reader = PdfReader(source_pdf_path.as_posix(), strict=False)
    except FileNotFoundError as exc:
        raise AppError(
            code="pdf_not_found",
            message=f"PDF not found: {request.source_pdf_path}",
            cause=exc,
            retryable=False,
        ) from exc
    except (PdfReadError, PdfStreamError) as exc:
        raise AppError(
            code="pdf_ocr_split_read_failed",
            message=f"Failed to read PDF for OCR split: {request.source_pdf_path}",
            cause=exc,
            retryable=True,
        ) from exc
    except PDF_TEXT_EXCEPTIONS as exc:
        raise AppError(
            code="pdf_ocr_split_read_failed",
            message=f"Failed to read PDF for OCR split: {request.source_pdf_path}",
            cause=exc,
            retryable=True,
        ) from exc

    try:
        total_pages = len(reader.pages)
        if total_pages < 1:
            raise AppError(
                code="pdf_ocr_split_invalid_request",
                message="Cannot split a PDF with zero pages for OCR",
                retryable=False,
            )
        if total_pages <= request.chunk_page_count:
            chunk = PdfOcrChunk(
                schema_version="1.0",
                chunk_index=1,
                source_pdf_path=request.source_pdf_path,
                chunk_pdf_path=request.source_pdf_path,
                start_page_number=1,
                end_page_number=total_pages,
                page_count=total_pages,
            )
            response = PdfOcrSplitResponse(schema_version="1.0", chunks=[chunk])
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="pdf_ocr_split_complete",
                    module=logger.name,
                    fields={
                        "source_pdf_path": request.source_pdf_path,
                        "chunk_count": 1,
                        "total_pages": total_pages,
                        "single_chunk_passthrough": True,
                    },
                )
            )
            return response

        output_dir = Path(request.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        chunks: list[PdfOcrChunk] = []
        stem = source_pdf_path.stem or "ocr"
        for chunk_index, start_idx in enumerate(
            range(0, total_pages, request.chunk_page_count), start=1
        ):
            end_idx = min(start_idx + request.chunk_page_count, total_pages)
            writer = PdfWriter()
            for page_idx in range(start_idx, end_idx):
                writer.add_page(reader.pages[page_idx])
            start_page_number = start_idx + 1
            end_page_number = end_idx
            chunk_pdf_path = output_dir / (
                f"{stem}.ocr-pages-{start_page_number:04d}-{end_page_number:04d}.pdf"
            )
            with chunk_pdf_path.open("wb") as handle:
                writer.write(handle)
            chunks.append(
                PdfOcrChunk(
                    schema_version="1.0",
                    chunk_index=chunk_index,
                    source_pdf_path=request.source_pdf_path,
                    chunk_pdf_path=chunk_pdf_path.as_posix(),
                    start_page_number=start_page_number,
                    end_page_number=end_page_number,
                    page_count=end_idx - start_idx,
                )
            )
    finally:
        _close_pypdf_reader(reader)

    response = PdfOcrSplitResponse(schema_version="1.0", chunks=chunks)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="pdf_ocr_split_complete",
            module=logger.name,
            fields={
                "source_pdf_path": request.source_pdf_path,
                "chunk_count": len(response.chunks),
                "total_pages": total_pages,
                "single_chunk_passthrough": False,
            },
        )
    )
    return response


def _normalize_metadata(raw_meta) -> dict[str, str]:
    if not raw_meta:
        return {}
    normalized: dict[str, str] = {}
    try:
        items = raw_meta.items() if hasattr(raw_meta, "items") else []
    except (AttributeError, TypeError, ValueError):
        return {}
    for key, value in items:
        if key is None or value is None:
            continue
        key_str = str(key).strip()
        if not key_str:
            continue
        if key_str.startswith("/"):
            key_str = key_str[1:]
        try:
            val_str = str(value).strip()
        except (TypeError, ValueError):
            val_str = ""
        if not val_str:
            continue
        normalized[key_str] = val_str
    return normalized


def _extract_text(reader: PdfReader, page_index: int) -> str:
    try:
        return reader.pages[page_index].extract_text() or ""
    except PDF_TEXT_EXCEPTIONS:
        return ""


def _append_text_page(doc: fitz.Document, text: str) -> None:
    margin = 36.0
    page_width = 595.0
    estimated_lines = _estimate_wrapped_lines(text)
    line_height = 11.0
    page_height = max(842.0, margin * 2 + (estimated_lines + 2) * line_height)
    page = doc.new_page(width=page_width, height=page_height)
    rect = fitz.Rect(margin, margin, page_width - margin, page_height - margin)
    page.insert_textbox(rect, text, fontsize=9, fontname="helv", lineheight=1.2)


def _estimate_wrapped_lines(text: str) -> int:
    if not text.strip():
        return 1
    line_count = 0
    for raw_line in text.splitlines() or [""]:
        token = raw_line.rstrip()
        if not token:
            line_count += 1
            continue
        line_count += max(1, (len(token) // 90) + 1)
    return max(line_count, 1)


def _close_pypdf_reader(reader: PdfReader) -> None:
    try:
        stream = getattr(reader, "stream", None)
        if stream is None:
            return
        close_fn = getattr(stream, "close", None)
        if callable(close_fn):
            close_fn()
    except (AttributeError, RuntimeError, ValueError, TypeError):
        return


def _compute_text_density(text: str, pages: int) -> float:
    if not pages or pages <= 0:
        return 0.0
    try:
        return len(text or "") / float(pages)
    except (TypeError, ValueError):
        return 0.0


_WORD_PATTERN = re.compile(r"[A-Za-z0-9]{2,}")


def _meaningful_word_count(text: str) -> int:
    if not text:
        return 0
    return len(_WORD_PATTERN.findall(text))


def _score_native_text_confidence(
    *,
    text: str,
    char_count: int,
    word_count: int,
) -> float:
    stripped = (text or "").strip()
    if not stripped or char_count <= 0 or word_count <= 0:
        return 0.0

    non_space_chars = sum(1 for char in stripped if not char.isspace())
    if non_space_chars <= 0:
        return 0.0

    alpha_numeric_chars = sum(1 for char in stripped if char.isalnum())
    alpha_numeric_ratio = alpha_numeric_chars / float(non_space_chars)
    words = _WORD_PATTERN.findall(stripped)
    long_word_count = sum(1 for word in words if len(word) >= 4)
    long_word_ratio = long_word_count / float(word_count) if word_count > 0 else 0.0
    char_signal = min(char_count / 80.0, 1.0)
    word_signal = min(word_count / 12.0, 1.0)
    alpha_signal = min(alpha_numeric_ratio / 0.55, 1.0)
    long_word_signal = min(long_word_ratio / 0.45, 1.0)
    score = (
        (char_signal * 0.35)
        + (word_signal * 0.35)
        + (alpha_signal * 0.15)
        + (long_word_signal * 0.15)
    )
    return round(max(0.0, min(score, 1.0)), 3)
