from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path
from urllib.parse import quote

from src.contracts.cover_images import CoverImageGenerationRequest, CoverImageReport
from src.contracts.files import FileStatRequest
from src.contracts.ingest import IngestOutcome
from src.contracts.report_assets import PreviewRequest, PreviewResponse, RenderRequest
from src.contracts.report_generation import (
    ReportAnalysisState,
    ReportRuntimeState,
    ReportSelectionState,
    ReportSourceState,
)
from src.contracts.report_store import (
    ReportMetadataGetRequest,
    ReportMetadataUpsertRequest,
)
from src.generators.report_generation_dependencies import ReportRenderDependencies
from src.generators.report_generation_shared import (
    html_cache_key,
    logger,
    read_cache_json,
    template_sha256,
    write_cache_json,
)
from src.utils.cache_utils import sha256_json
from src.utils.errors import AppError
from src.utils.logging import child_context, log_event


def _build_metadata_upsert_request(
    runtime: ReportRuntimeState,
    source: ReportSourceState,
    analysis: ReportAnalysisState,
    html_path_value: str | None,
) -> ReportMetadataUpsertRequest:
    payload = analysis.payload
    return ReportMetadataUpsertRequest(
        schema_version="1.1",
        db_path=runtime.settings.reports_db,
        file_id=runtime.file.file_id,
        title=payload.title or runtime.report_title,
        file_name=runtime.file_name,
        publisher=payload.publisher or None,
        taxonomy=payload.taxonomy,
        categories=payload.categories,
        region=payload.region or None,
        time_period=payload.time_period or None,
        source_url=payload.source,
        html_path=html_path_value,
        md5=runtime.md5,
        page_count=source.info_response.page_count,
        pdf_metadata=source.info_response.metadata,
        contents_page_number=source.contents_page_number,
        analysis_mode=runtime.analysis_mode,
        vector_store_id=analysis.vector_store_id,
        evidence_pack_paths=analysis.evidence_paths,
    )


def _relative_href(from_dir: str, target_path: str) -> str:
    base = Path(from_dir).resolve()
    target = Path(target_path).resolve()
    try:
        relative = os.path.relpath(target, start=base)
    except ValueError:
        return target.as_uri()
    return quote(relative.replace(os.sep, "/"), safe="/#?=&:%")


def _report_template_bundle_sha(
    runtime: ReportRuntimeState, dependencies
) -> str | None:
    template_dir = Path(__file__).resolve().parents[2] / "templates"
    hashes: dict[str, str] = {}
    for template_name in ("report.html.j2", "report.css.j2", "_report_macros.j2"):
        digest = template_sha256(
            template_dir / template_name, runtime.ctx, dependencies
        )
        if not digest:
            return None
        hashes[template_name] = digest
    return sha256_json(
        {
            "schema_version": "1.0",
            "templates": hashes,
        }
    )


def _file_exists_via_service(
    runtime: ReportRuntimeState,
    dependencies: ReportRenderDependencies,
    path: str,
    task_suffix: str,
) -> bool:
    stat = dependencies.file_stat(
        FileStatRequest(schema_version="1.0", path=path),
        child_context(runtime.ctx, task_id=f"{runtime.ctx.task_id}:{task_suffix}"),
    )
    return bool(stat.exists)


def render_preview_asset(
    runtime: ReportRuntimeState,
    source: ReportSourceState,
    dependencies: ReportRenderDependencies,
):
    if source.contents_page_number == 1 and source.contents_image:
        logger.info(
            log_event(
                runtime.ctx,
                role="generator",
                event="preview_asset_reused_from_contents",
                module=logger.name,
                fields={
                    "file_id": runtime.file.file_id,
                    "image_path": source.contents_image,
                    "contents_page_number": source.contents_page_number,
                },
            )
        )
        return PreviewResponse(
            schema_version="1.1",
            image_path=source.contents_image,
            page_number=0,
        )
    preview_ctx = child_context(runtime.ctx, task_id=f"{runtime.ctx.task_id}:preview")
    return dependencies.render_preview(
        PreviewRequest(
            schema_version="1.1",
            pdf_path=runtime.local_pdf_path,
            out_dir=runtime.settings.output_dir,
            report_name=runtime.report_name,
            pdf_context=source.pdf_context,
        ),
        preview_ctx,
    )


def render_report_output(
    runtime: ReportRuntimeState,
    source: ReportSourceState,
    selection: ReportSelectionState,
    analysis: ReportAnalysisState,
    dependencies: ReportRenderDependencies,
    *,
    preview_resp,
) -> IngestOutcome:
    dependencies.upsert_report_metadata(
        _build_metadata_upsert_request(runtime, source, analysis, html_path_value=None),
        runtime.ctx,
    )
    render_meta = dependencies.get_report_metadata(
        ReportMetadataGetRequest(
            schema_version="1.1",
            db_path=runtime.settings.reports_db,
            file_id=runtime.file.file_id,
        ),
        child_context(runtime.ctx, task_id=f"{runtime.ctx.task_id}:render_metadata"),
    )
    render_data_dict = deepcopy(analysis.data_dict)
    if runtime.local_pdf_path and _file_exists_via_service(
        runtime,
        dependencies,
        runtime.local_pdf_path,
        "source_pdf_stat",
    ):
        render_data_dict["_source_download_href"] = _relative_href(
            runtime.settings.output_dir,
            runtime.local_pdf_path,
        )
    existing_title = str(render_data_dict.get("title") or "").strip()
    existing_publisher = str(render_data_dict.get("publisher") or "").strip()
    existing_time_period = str(render_data_dict.get("time_period") or "").strip()
    if render_meta is None:
        render_data_dict["title"] = existing_title
        render_data_dict["publisher"] = existing_publisher
        render_data_dict["time_period"] = existing_time_period
        logger.info(
            log_event(
                runtime.ctx,
                role="generator",
                event="render_metadata_missing",
                module=logger.name,
                fields={
                    "file_id": runtime.file.file_id,
                    "title": existing_title,
                    "publisher": existing_publisher,
                    "time_period": existing_time_period,
                    "source": "analysis_payload",
                },
            )
        )
    else:
        render_data_dict["title"] = str(render_meta.title or existing_title).strip()
        render_data_dict["publisher"] = str(
            render_meta.publisher or existing_publisher
        ).strip()
        render_data_dict["time_period"] = str(
            render_meta.time_period or existing_time_period
        ).strip()
        source_url = str(render_meta.source_url or "").strip()
        if source_url:
            render_data_dict["source"] = source_url
            render_data_dict["canonical_url"] = source_url
        logger.info(
            log_event(
                runtime.ctx,
                role="generator",
                event="render_metadata_sourced_from_db",
                module=logger.name,
                fields={
                    "file_id": runtime.file.file_id,
                    "title": render_data_dict["title"],
                    "publisher": render_data_dict["publisher"],
                    "time_period": render_data_dict["time_period"],
                    "source": "reports_db",
                },
            )
        )

    doc_name = runtime.file_name
    out_html = ""
    html_cache_hit = False
    template_sha = None
    html_cache_meta = None
    html_key = ""
    expected_html_path = (
        Path(runtime.settings.output_dir) / f"{runtime.report_name}.html"
    )
    if runtime.md5:
        template_sha = _report_template_bundle_sha(runtime, dependencies)
        if template_sha:
            data_sha = sha256_json(render_data_dict)
            html_cache_meta = {
                "schema_version": "1.0",
                "md5": runtime.md5,
                "template_sha256": template_sha,
                "data_sha256": data_sha,
                "preview_png": preview_resp.image_path or "",
                "doc_name": doc_name,
            }
            html_key = html_cache_key(
                runtime.md5,
                template_sha,
                data_sha,
                preview_resp.image_path or "",
                doc_name,
            )
            html_cache_path = Path(f"{expected_html_path}.cache.json")
            cached = read_cache_json(html_cache_path, runtime.ctx, dependencies)
            if cached and cached.get("key") == html_key:
                html_stat = dependencies.file_stat(
                    FileStatRequest(schema_version="1.0", path=str(expected_html_path)),
                    runtime.ctx,
                )
                if html_stat.exists:
                    out_html = str(expected_html_path)
                    html_cache_hit = True
                    logger.info(
                        log_event(
                            runtime.ctx,
                            role="generator",
                            event="render_html_cache_hit",
                            module=logger.name,
                            fields={
                                "file_id": runtime.file.file_id,
                                "html_path": out_html,
                            },
                        )
                    )
                else:
                    logger.info(
                        log_event(
                            runtime.ctx,
                            role="generator",
                            event="render_html_cache_stale",
                            module=logger.name,
                            fields={
                                "file_id": runtime.file.file_id,
                                "html_path": str(expected_html_path),
                            },
                        )
                    )
            else:
                logger.info(
                    log_event(
                        runtime.ctx,
                        role="generator",
                        event="render_html_cache_miss",
                        module=logger.name,
                        fields={
                            "file_id": runtime.file.file_id,
                            "cache_path": str(html_cache_path),
                        },
                    )
                )
    if not html_cache_hit:
        render_resp = dependencies.render_report(
            RenderRequest(
                schema_version="1.0",
                data=render_data_dict,
                doc_name=doc_name,
                file_id=runtime.file.file_id,
                out_dir=runtime.settings.output_dir,
                preview_png=preview_resp.image_path,
                tag_acronyms=runtime.settings.html_tag_acronyms,
            ),
            runtime.ctx,
        )
        out_html = render_resp.html_path
        if runtime.md5 and template_sha and html_cache_meta and html_key:
            cache_path = Path(f"{out_html}.cache.json")
            write_cache_json(
                cache_path,
                {**html_cache_meta, "key": html_key, "html_path": out_html},
                runtime.ctx,
                dependencies,
            )
            logger.info(
                log_event(
                    runtime.ctx,
                    role="generator",
                    event="render_html_cache_written",
                    module=logger.name,
                    fields={
                        "file_id": runtime.file.file_id,
                        "cache_path": str(cache_path),
                    },
                )
            )

    dependencies.upsert_report_metadata(
        _build_metadata_upsert_request(
            runtime, source, analysis, html_path_value=out_html
        ),
        runtime.ctx,
    )

    cover_meta = dependencies.get_report_metadata(
        ReportMetadataGetRequest(
            schema_version="1.0",
            db_path=runtime.settings.reports_db,
            file_id=runtime.file.file_id,
        ),
        child_context(runtime.ctx, task_id=f"{runtime.ctx.task_id}:cover_metadata"),
    )
    cover_title = (cover_meta.title if cover_meta else runtime.report_title).strip()
    cover_publisher = (
        (cover_meta.publisher or "").strip()
        if cover_meta
        else (analysis.payload.publisher or "")
    )
    cover_time_period = (
        cover_meta.time_period if cover_meta else (analysis.payload.time_period or None)
    )
    cover_region = (
        cover_meta.region if cover_meta else (analysis.payload.region or None)
    )

    cover_ctx = child_context(runtime.ctx, task_id=f"{runtime.ctx.task_id}:cover_image")
    try:
        cover_outcomes = dependencies.generate_cover_images(
            CoverImageGenerationRequest(
                schema_version="1.0",
                output_dir=runtime.settings.output_dir,
                style_config_path=runtime.settings.cover_style_path,
                reports=[
                    CoverImageReport(
                        schema_version="1.0",
                        file_id=runtime.file.file_id,
                        title=cover_title,
                        publisher=cover_publisher,
                        report_slug=runtime.report_name,
                        categories=list(analysis.payload.categories),
                        time_period=cover_time_period,
                        region=cover_region,
                    )
                ],
            ),
            cover_ctx,
        )
        cover_outcome = cover_outcomes[0] if cover_outcomes else None
        cover_assets = getattr(cover_outcome, "assets", None)
        logger.info(
            log_event(
                cover_ctx,
                role="generator",
                event="cover_image_generation_complete",
                module=logger.name,
                fields={
                    "file_id": runtime.file.file_id,
                    "status": cover_outcome.status if cover_outcome else "skipped",
                    "small_output_path": (
                        cover_assets.small.output_path if cover_assets else ""
                    ),
                    "medium_output_path": (
                        cover_assets.medium.output_path if cover_assets else ""
                    ),
                    "large_output_path": (
                        cover_assets.large.output_path if cover_assets else ""
                    ),
                    "error": cover_outcome.error if cover_outcome else "",
                },
            )
        )
    except AppError as exc:
        if exc.retryable:
            logger.info(
                log_event(
                    cover_ctx,
                    role="generator",
                    event="cover_image_retryable_error_propagated",
                    module=logger.name,
                    fields={
                        "file_id": runtime.file.file_id,
                        "code": exc.code,
                        "error": exc.message,
                    },
                )
            )
            raise
        logger.info(
            log_event(
                cover_ctx,
                role="generator",
                event="cover_image_generation_failed",
                module=logger.name,
                fields={
                    "file_id": runtime.file.file_id,
                    "code": exc.code,
                    "error": exc.message,
                },
            )
        )

    logger.info(
        log_event(
            runtime.ctx,
            role="generator",
            event="token_usage_summary",
            module=logger.name,
            fields={
                "report_generation": None,
                "rank_candidates": selection.rank_usage
                if selection.candidate_count
                else None,
            },
        )
    )
    logger.info(
        log_event(
            runtime.ctx,
            role="generator",
            event="report_generate_complete",
            module=logger.name,
            fields={
                "file_id": runtime.file.file_id,
                "html_path": out_html,
                "modes": runtime.analysis_modes,
            },
        )
    )

    return IngestOutcome(
        schema_version="1.0",
        file_id=runtime.file.file_id,
        name=runtime.file_name,
        md5=runtime.md5,
        html_path=out_html,
        status="processed",
        vector_store_id=analysis.vector_store_id,
        vector_store_status=analysis.vector_store_status,
        indexed_at_utc=analysis.indexed_at_utc,
        openai_file_id=analysis.openai_file_id,
        evidence_packs=analysis.evidence_paths or None,
        vector_store_last_error=analysis.last_error,
        text_validation_status=source.text_validation_status,
        text_validation_reason=source.text_validation_reason,
        text_validation_pages=source.text_validation_pages,
        ocr_fallback_used=source.ocr_fallback_used,
        ocr_pdf_path=source.ocr_pdf_path or None,
    )
