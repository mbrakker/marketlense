from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.contracts.files import (  # noqa: E402
    FileStatRequest,
    JsonObjectCacheReadRequest,
    JsonObjectCacheWriteRequest,
)
from src.contracts.pdf_context import PdfContextBuildRequest  # noqa: E402
from src.contracts.pdf_page_reconciliation import (  # noqa: E402
    PDF_PAGE_RECONCILIATION_ALGORITHM_VERSION,
    PDF_PAGE_RECONCILIATION_SCHEMA_VERSION,
    PdfPageReconciliationRequest,
    PdfPageReconciliationResponse,
    response_from_payload,
)
from src.contracts.run_context import RunContext  # noqa: E402
from src.contracts.schema_validation import SchemaValidateRequest  # noqa: E402
from src.contracts.semantic_ids import RunId, TaskId  # noqa: E402
from src.services import file_service, pdf_service  # noqa: E402
from src.services.schema_validator_service import validate_schema  # noqa: E402
from src.utils.errors import AppError  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reconcile visible printed PDF page labels to physical pages."
    )
    parser.add_argument("--pdf", required=True, help="Path to the source PDF.")
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Explicit diagnostic directory for the cache JSON.",
    )
    parser.add_argument(
        "--force", action="store_true", help="Ignore and replace a reusable cache."
    )
    args = parser.parse_args(argv)
    ctx = RunContext(
        schema_version="1.0",
        run_id=RunId("pdf-page-reconciliation"),
        task_id=TaskId("quality-diagnostic"),
        span_id="standalone-runner",
    )
    try:
        response, cache_hit, elapsed_seconds, output_path = _run(
            pdf_path=Path(args.pdf),
            output_dir=Path(args.output_dir),
            force=bool(args.force),
            ctx=ctx,
        )
    except AppError as exc:
        print(f"error={exc.code}", file=sys.stderr)
        return 1

    coverage = response.coverage_statistics
    print(
        " ".join(
            [
                f"page_count={response.physical_page_count}",
                f"verified={coverage.verified_percentage:.2f}%",
                f"inferred={coverage.inferred_percentage:.2f}%",
                f"unresolved={coverage.unresolved_percentage:.2f}%",
                f"cache={'hit' if cache_hit else 'miss'}",
                f"elapsed_ms={elapsed_seconds * 1000.0:.2f}",
                f"output={output_path.name}",
            ]
        )
    )
    return 0


def _run(
    *,
    pdf_path: Path,
    output_dir: Path,
    force: bool,
    ctx: RunContext,
) -> tuple[PdfPageReconciliationResponse, bool, float, Path]:
    started = time.perf_counter()
    source_path = pdf_path.expanduser().resolve()
    diagnostic_dir = output_dir.expanduser().resolve()
    diagnostic_dir.mkdir(parents=True, exist_ok=True)
    stat = file_service.file_stat(
        FileStatRequest(schema_version="1.0", path=str(source_path), compute_md5=True),
        ctx,
    )
    if not stat.exists or not stat.is_file or not stat.md5:
        raise AppError(
            code="pdf_not_found",
            message=f"Input PDF is not a readable file: {source_path}",
            retryable=False,
        )
    md5 = stat.md5.lower()
    output_path = diagnostic_dir / f"page_reconciliation-{md5}.json"
    if (
        file_service.atomic_write_temp_path_length(output_path)
        > file_service.WINDOWS_SAFE_ATOMIC_PATH_LENGTH
    ):
        raise AppError(
            code="diagnostic_output_path_too_long",
            message="Diagnostic output path exceeds the Windows atomic-write budget",
            retryable=False,
        )

    page_count = _page_count(source_path, ctx)
    response = (
        None if force else _read_reusable_cache(output_path, md5, page_count, ctx)
    )
    cache_hit = response is not None
    if response is None:
        response = pdf_service.reconcile_pdf_pages(
            PdfPageReconciliationRequest(
                schema_version=PDF_PAGE_RECONCILIATION_SCHEMA_VERSION,
                path=str(source_path),
            ),
            ctx,
        )
        payload = json.loads(json.dumps(asdict(response), ensure_ascii=True))
        validate_schema(
            SchemaValidateRequest(
                schema_version="1.0",
                schema_name="pdf_page_reconciliation",
                payload=payload,
            ),
            ctx,
        )
        file_service.write_json_object_cache(
            JsonObjectCacheWriteRequest(
                schema_version="1.0", path=str(output_path), payload=payload
            ),
            ctx,
        )
    elapsed_seconds = time.perf_counter() - started
    return response, cache_hit, elapsed_seconds, output_path


def _page_count(path: Path, ctx: RunContext) -> int:
    context_response = pdf_service.build_pdf_context(
        PdfContextBuildRequest(
            schema_version="1.0",
            path=str(path),
            load_fitz=True,
            load_pypdf=False,
        ),
        ctx,
    )
    context = context_response.context
    try:
        if context.fitz_doc is None:
            raise AppError(
                code="pdf_open_failed",
                message=f"Failed to open PDF with PyMuPDF: {path}",
                retryable=False,
            )
        page_count = int(context.fitz_doc.page_count)
    except (AttributeError, RuntimeError, TypeError, ValueError) as exc:
        raise AppError(
            code="pdf_page_count_failed",
            message=f"Failed to determine PDF page count: {path}",
            cause=exc,
            retryable=False,
        ) from exc
    finally:
        context.close()
    if page_count <= 0:
        raise AppError(
            code="pdf_zero_pages",
            message=f"PDF contains no readable pages: {path}",
            retryable=False,
        )
    return page_count


def _read_reusable_cache(
    output_path: Path,
    input_pdf_md5: str,
    page_count: int,
    ctx: RunContext,
) -> PdfPageReconciliationResponse | None:
    cached = file_service.read_json_object_cache(
        JsonObjectCacheReadRequest(schema_version="1.0", path=str(output_path)),
        ctx,
    )
    if not cached.found or cached.payload is None:
        return None
    try:
        validate_schema(
            SchemaValidateRequest(
                schema_version="1.0",
                schema_name="pdf_page_reconciliation",
                payload=cached.payload,
            ),
            ctx,
        )
        response = response_from_payload(cached.payload)
    except (AppError, KeyError, TypeError, ValueError, OverflowError):
        return None
    if response.algorithm_version != PDF_PAGE_RECONCILIATION_ALGORITHM_VERSION:
        return None
    if response.input_pdf_md5 != input_pdf_md5:
        return None
    if response.physical_page_count != page_count:
        return None
    return response


if __name__ == "__main__":
    raise SystemExit(main())
