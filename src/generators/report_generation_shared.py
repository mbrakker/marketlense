from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Callable, Optional, Protocol

from src.contracts.files import ReadTextRequest, WriteBytesRequest
from src.contracts.ingest import IngestSettings
from src.contracts.report_analysis import AnalysisPackPathRequest
from src.contracts.report_models import Figure, Quote, ReportPayload
from src.contracts.run_context import RunContext
from src.contracts.state import StateRecordRequest
from src.utils.analysis_family import family_is_abstained
from src.utils.errors import AppError
from src.utils.logging import child_context, log_event
from src.utils.slugify import slugify
from src.utils.cache_utils import sha256_json

LOGGER_NAME = "market_lense.report_generator"
logger = logging.getLogger(LOGGER_NAME)


class SupportsReadText(Protocol):
    read_text: Callable[[ReadTextRequest, RunContext], Any]


class SupportsWriteBytes(Protocol):
    write_bytes: Callable[[WriteBytesRequest, RunContext], Any]


class SupportsAnalysisPackPath(Protocol):
    analysis_pack_path: Callable[[AnalysisPackPathRequest, RunContext], Any]


class SupportsStateRecord(Protocol):
    state_record: Callable[[StateRecordRequest, RunContext], Any]


def derive_title(name: str) -> str:
    base = name.rsplit(".", 1)[0]
    cleaned = base.strip()
    return cleaned or name


def report_slug(file_name: str, file_id: str) -> str:
    return slugify(file_name or file_id)


def cache_dir(settings: IngestSettings, md5: str) -> Path:
    return Path(settings.cache_dir) / "pdf_cache" / md5


def read_cache_json(
    path: Path,
    ctx: RunContext,
    dependencies: SupportsReadText,
) -> Optional[dict]:
    try:
        resp = dependencies.read_text(
            ReadTextRequest(schema_version="1.0", path=str(path)),
            ctx,
        )
    except AppError as exc:
        if exc.code == "file_not_found":
            return None
        if exc.retryable:
            logger.info(
                log_event(
                    ctx,
                    role="generator",
                    event="cache_read_retryable_error_propagated",
                    module=logger.name,
                    fields={"path": str(path), "error": exc.message, "code": exc.code},
                )
            )
            raise
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="cache_read_failed",
                module=logger.name,
                fields={"path": str(path), "error": exc.message},
            )
        )
        return None
    try:
        payload = json.loads(resp.content)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def write_cache_json(
    path: Path,
    payload: dict,
    ctx: RunContext,
    dependencies: SupportsWriteBytes,
) -> None:
    data = json.dumps(payload, ensure_ascii=True)
    dependencies.write_bytes(
        WriteBytesRequest(
            schema_version="1.0", path=str(path), content=data.encode("utf-8")
        ),
        ctx,
    )


def pdf_info_cache_key(md5: str) -> str:
    return sha256_json({"schema_version": "1.0", "md5": md5})


def contents_cache_key(md5: str, settings: IngestSettings) -> str:
    return sha256_json(
        {
            "schema_version": "1.0",
            "md5": md5,
            "max_pages": settings.contents_max_pages,
            "min_headings": settings.contents_min_headings,
            "keywords": settings.contents_keywords,
        }
    )


def text_cache_key(md5: str, settings: IngestSettings) -> str:
    return sha256_json(
        {
            "schema_version": "1.0",
            "md5": md5,
            "max_pages": settings.pdf_text_max_pages,
            "max_chars": settings.pdf_text_max_chars,
        }
    )


def cache_path(cache_root: Path, prefix: str, cache_key: str) -> Path:
    return cache_root / f"{prefix}_{cache_key}.json"


def template_sha256(
    path: Path,
    ctx: RunContext,
    dependencies: SupportsReadText,
) -> Optional[str]:
    try:
        resp = dependencies.read_text(
            ReadTextRequest(schema_version="1.0", path=str(path)),
            ctx,
        )
    except AppError as exc:
        if exc.retryable:
            logger.info(
                log_event(
                    ctx,
                    role="generator",
                    event="template_hash_retryable_error_propagated",
                    module=logger.name,
                    fields={"path": str(path), "error": exc.message, "code": exc.code},
                )
            )
            raise
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="template_hash_failed",
                module=logger.name,
                fields={"path": str(path), "error": exc.message},
            )
        )
        return None
    return hashlib.sha256(resp.content.encode("utf-8")).hexdigest()


def html_cache_key(
    md5: str,
    template_sha256_value: str,
    data_sha256: str,
    preview_png: str,
    doc_name: str,
) -> str:
    return sha256_json(
        {
            "schema_version": "1.0",
            "md5": md5,
            "template_sha256": template_sha256_value,
            "data_sha256": data_sha256,
            "preview_png": preview_png,
            "doc_name": doc_name,
        }
    )


def base_payload(
    title: str,
    contents_page_number: int,
    contents_heading: str,
    contents_image: str,
) -> ReportPayload:
    return ReportPayload(
        tldr="Not available from text",
        title=title,
        insights=["", "", "", "", ""],
        quote=Quote(text="", author="Unknown"),
        figure=Figure(title="", evidence=""),
        commentary="",
        source="",
        publisher="",
        taxonomy=[],
        categories=[],
        region="",
        time_period="",
        contents_page_number=contents_page_number,
        contents_heading=contents_heading,
        _contents_image=contents_image,
    )


def merge_artifacts_into_payload(
    payload: ReportPayload, artifacts: dict
) -> ReportPayload:
    if not isinstance(artifacts, dict):
        return payload
    summary_abstained = family_is_abstained(artifacts, "summary")
    insights_abstained = family_is_abstained(artifacts, "insights_bundle")
    quotes_abstained = family_is_abstained(artifacts, "quotes")
    summary = (
        artifacts.get("summary") if isinstance(artifacts.get("summary"), dict) else {}
    )
    tldr = summary.get("tldr") if isinstance(summary, dict) else None
    exec_summary = (
        summary.get("executive_summary") if isinstance(summary, dict) else None
    )
    if summary_abstained:
        payload.tldr = ""
        payload.commentary = ""
    elif tldr:
        payload.tldr = str(tldr)
    if not summary_abstained and exec_summary:
        payload.commentary = str(exec_summary)
    insights_final = (
        artifacts.get("insights_final")
        if isinstance(artifacts.get("insights_final"), list)
        else []
    )
    if insights_abstained:
        payload.insights = ["", "", "", "", ""]
    elif insights_final:
        normalized = []
        for item in insights_final[:5]:
            if isinstance(item, dict):
                normalized.append(str(item.get("text") or ""))
            else:
                normalized.append(str(item))
        while len(normalized) < 5:
            normalized.append("")
        payload.insights = normalized
    quotes_final = (
        artifacts.get("quotes_final")
        if isinstance(artifacts.get("quotes_final"), list)
        else []
    )
    if quotes_abstained:
        payload.quote = Quote(text="", author="Unknown")
    elif quotes_final:
        first_quote = quotes_final[0] if quotes_final else {}
        if isinstance(first_quote, dict):
            payload.quote = Quote(
                text=str(first_quote.get("text") or ""),
                author=str(
                    first_quote.get("speaker") or first_quote.get("author") or "Unknown"
                ),
            )
    return payload


def resolve_publisher(payload: ReportPayload, pdf_metadata: dict[str, str]) -> str:
    del payload, pdf_metadata
    return ""


def pick_non_empty_text(*values: Any) -> str:
    for value in values:
        candidate = str(value or "").strip()
        if candidate:
            return candidate
    return ""


def resolve_doc_map_metadata(doc_map_pack: dict[str, Any]) -> tuple[str, str, str, str]:
    candidate = doc_map_pack
    candidate_prefix = "doc_map"
    for key in ("doc_map", "docmap", "docMap"):
        wrapped = doc_map_pack.get(key)
        if isinstance(wrapped, dict):
            candidate = wrapped
            candidate_prefix = key
            break
    document = (
        candidate.get("document") if isinstance(candidate.get("document"), dict) else {}
    )

    title = pick_non_empty_text(
        candidate.get("title"),
        candidate.get("document_title"),
        candidate.get("document_name"),
        candidate.get("name"),
        document.get("title"),
        document.get("name"),
    )
    publisher = pick_non_empty_text(
        candidate.get("publisher"),
        candidate.get("document_publisher"),
        candidate.get("document_organization"),
        candidate.get("document_organisation"),
        candidate.get("organization"),
        candidate.get("organisation"),
        document.get("publisher"),
        document.get("organization"),
        document.get("organisation"),
    )

    title_source = ""
    if title:
        if str(candidate.get("title") or "").strip():
            title_source = f"{candidate_prefix}.title"
        elif str(candidate.get("document_title") or "").strip():
            title_source = f"{candidate_prefix}.document_title"
        elif str(candidate.get("document_name") or "").strip():
            title_source = f"{candidate_prefix}.document_name"
        elif str(candidate.get("name") or "").strip():
            title_source = f"{candidate_prefix}.name"
        elif str(document.get("title") or "").strip():
            title_source = f"{candidate_prefix}.document.title"
        else:
            title_source = f"{candidate_prefix}.document.name"

    publisher_source = ""
    if publisher:
        if str(candidate.get("publisher") or "").strip():
            publisher_source = f"{candidate_prefix}.publisher"
        elif str(candidate.get("document_publisher") or "").strip():
            publisher_source = f"{candidate_prefix}.document_publisher"
        elif str(candidate.get("document_organization") or "").strip():
            publisher_source = f"{candidate_prefix}.document_organization"
        elif str(candidate.get("document_organisation") or "").strip():
            publisher_source = f"{candidate_prefix}.document_organisation"
        elif str(candidate.get("organization") or "").strip():
            publisher_source = f"{candidate_prefix}.organization"
        elif str(candidate.get("organisation") or "").strip():
            publisher_source = f"{candidate_prefix}.organisation"
        elif str(document.get("publisher") or "").strip():
            publisher_source = f"{candidate_prefix}.document.publisher"
        elif str(document.get("organization") or "").strip():
            publisher_source = f"{candidate_prefix}.document.organization"
        else:
            publisher_source = f"{candidate_prefix}.document.organisation"

    return title, publisher, title_source, publisher_source


def resolve_doc_map_primary_contributor(doc_map_pack: dict[str, Any]) -> str:
    candidate = doc_map_pack
    for key in ("doc_map", "docmap", "docMap"):
        wrapped = doc_map_pack.get(key)
        if isinstance(wrapped, dict):
            candidate = wrapped
            break
    contributors = (
        candidate.get("contributors")
        if isinstance(candidate.get("contributors"), list)
        else []
    )
    for contributor in contributors:
        if not isinstance(contributor, dict):
            continue
        name = pick_non_empty_text(
            contributor.get("name"),
            contributor.get("author"),
            contributor.get("full_name"),
        )
        if name:
            return name
    return ""


def pack_paths(
    output_dir: str,
    report_id: str,
    report_name: str,
    pack_names: list[str],
    ctx: RunContext,
    dependencies: SupportsAnalysisPackPath,
) -> dict[str, str]:
    return {
        name: dependencies.analysis_pack_path(
            AnalysisPackPathRequest(
                schema_version="1.0",
                output_dir=output_dir,
                report_id=report_id,
                pack_name=name,
                report_slug=report_name,
            ),
            child_context(ctx, task_id=f"{ctx.task_id}:analysis_pack_path:{name}"),
        ).output_path
        for name in pack_names
    }


def record_state_progress(
    *,
    settings: IngestSettings,
    file_id: str,
    md5: Optional[str],
    ctx: RunContext,
    dependencies: SupportsStateRecord,
    stage: str,
    vector_store_id: Optional[str] = None,
    vector_store_status: Optional[str] = None,
    indexed_at_utc: Optional[str] = None,
    openai_file_id: Optional[str] = None,
    last_error: Optional[str] = None,
) -> None:
    if not md5:
        return
    try:
        dependencies.state_record(
            StateRecordRequest(
                schema_version="1.0",
                state_db=settings.state_db,
                file_id=file_id,
                md5=md5,
                openai_file_id=openai_file_id or "",
                vector_store_id=vector_store_id,
                vector_store_status=vector_store_status,
                indexed_at_utc=indexed_at_utc,
                last_error=last_error,
            ),
            ctx,
        )
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="state_progress_recorded",
                module=logger.name,
                fields={
                    "file_id": file_id,
                    "stage": stage,
                    "vector_store_id": vector_store_id or "",
                    "vector_store_status": vector_store_status or "",
                    "indexed_at_utc": indexed_at_utc or "",
                },
            )
        )
    except Exception as exc:  # pragma: no cover - best-effort state tracking
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="state_progress_failed",
                module=logger.name,
                fields={"file_id": file_id, "stage": stage, "error": str(exc)},
            )
        )
