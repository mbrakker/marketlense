from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from datetime import date
import os
from pathlib import Path
import re
from urllib.parse import quote

from src.contracts.cover_images import CoverImageGenerationRequest, CoverImageReport
from src.contracts.files import FileStatRequest
from src.contracts.ingest import IngestOutcome
from src.contracts.report_assets import PreviewRequest, PreviewResponse, RenderRequest
from src.contracts.report_cards import (
    CardCoverAssetSet,
    CoverFingerprintProjectionRequest,
    ReportCardManifestRequest,
    ReportCardManifestWriteRequest,
)
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
from src.generators.report_card_projection import (
    build_cover_fingerprint,
    build_report_card_manifest,
)
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


def _publication_date(runtime: ReportRuntimeState, artifacts: dict) -> str:
    candidates = [
        artifacts.get("publication_date"),
        artifacts.get("published_date"),
        artifacts.get("report_date"),
        runtime.file.modified_time,
    ]
    for candidate in candidates:
        value = str(candidate or "").strip()
        if not value:
            continue
        normalized = value[:10]
        try:
            date.fromisoformat(normalized)
        except ValueError:
            continue
        return normalized
    raise AppError(
        code="card_publication_date_invalid",
        message="A valid report publication date is required for report cards",
        retryable=False,
    )


def _relative_cover_assets(
    assets: CardCoverAssetSet,
    report_output_dir: Path,
) -> CardCoverAssetSet:
    root = report_output_dir.resolve()
    payload = asdict(assets)
    for size in ("small", "medium", "large"):
        output_path = Path(str(payload[size]["output_path"]))
        if output_path.is_absolute():
            try:
                relative = output_path.resolve().relative_to(root)
            except ValueError as exc:
                raise AppError(
                    code="cover_asset_set_incomplete",
                    message="Cover assets must be stored inside the report output directory",
                    retryable=False,
                    context={"size": size, "output_path": str(output_path)},
                ) from exc
        else:
            relative = output_path
        if relative.is_absolute() or ".." in relative.parts:
            raise AppError(
                code="cover_asset_set_incomplete",
                message="Cover asset paths must be report-relative",
                retryable=False,
                context={"size": size, "output_path": str(output_path)},
            )
        payload[size]["output_path"] = relative.as_posix()
    return CardCoverAssetSet.from_dict(payload)


def _artifact_insights(artifacts: dict) -> tuple[dict[str, object], ...]:
    value = artifacts.get("insights_final")
    if isinstance(value, dict):
        value = value.get("insights_final")
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, dict))


def _is_card_contract_error(exc: AppError) -> bool:
    return exc.code.startswith("card_") or exc.code in {
        "cover_fingerprint_invalid",
        "cover_asset_set_incomplete",
    }


def _resolved_report_title(
    runtime: ReportRuntimeState,
    source: ReportSourceState,
    analysis: ReportAnalysisState,
) -> str:
    candidate = str(analysis.payload.title or runtime.report_title).strip()
    if not re.fullmatch(r"[0-9a-fA-F]{32,64}", candidate):
        return candidate
    metadata_title = str(source.info_response.metadata.get("Title") or "").strip()
    if metadata_title and not re.fullmatch(r"[0-9a-fA-F]{32,64}", metadata_title):
        return metadata_title
    return candidate


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
        title=_resolved_report_title(runtime, source, analysis),
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
    report_card_manifest_path = None
    report_card_error = None
    try:
        artifacts_payload = analysis.artifacts_payload or {}
        cover_semantics = artifacts_payload.get("cover_semantics")
        if not isinstance(cover_semantics, dict):
            raise AppError(
                code="cover_fingerprint_invalid",
                message="Grounded cover semantics are required for report cards",
                retryable=False,
            )
        fingerprint = build_cover_fingerprint(
            CoverFingerprintProjectionRequest(
                schema_version="1.0",
                file_id=runtime.file.file_id,
                artifact_hash=sha256_json(artifacts_payload),
                region=cover_region or "",
                cover_semantics=cover_semantics,
            )
        )
        cover_outcomes = dependencies.generate_cover_images(
            CoverImageGenerationRequest(
                schema_version="2.0",
                output_dir=runtime.settings.output_dir,
                style_config_path=runtime.settings.cover_style_path,
                reports=[
                    CoverImageReport(
                        schema_version="2.0",
                        file_id=runtime.file.file_id,
                        title=cover_title,
                        publisher=cover_publisher,
                        report_slug=runtime.report_name,
                        categories=list(analysis.payload.categories),
                        time_period=cover_time_period,
                        region=cover_region,
                        fingerprint=fingerprint,
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
        if (
            cover_outcome is not None
            and cover_outcome.status == "generated"
            and cover_assets is not None
        ):
            report_output_dir = Path(runtime.settings.output_dir) / runtime.report_name
            summary = artifacts_payload.get("summary")
            if not isinstance(summary, dict):
                summary = {}
            manifest = build_report_card_manifest(
                ReportCardManifestRequest(
                    schema_version="1.0",
                    title=cover_title,
                    publisher=cover_publisher,
                    published_date=_publication_date(runtime, artifacts_payload),
                    region=cover_region or "",
                    covered_period=cover_time_period or "",
                    tldr_compact=str(summary.get("card_tldr_compact") or ""),
                    tldr_standard=str(summary.get("tldr") or ""),
                    insights_final=_artifact_insights(artifacts_payload),
                    fingerprint=fingerprint,
                    covers=_relative_cover_assets(
                        cover_assets,
                        report_output_dir,
                    ),
                )
            )
            manifest_response = dependencies.write_report_card_manifest(
                ReportCardManifestWriteRequest(
                    schema_version="1.0",
                    output_dir=str(report_output_dir),
                    manifest=manifest,
                ),
                child_context(
                    runtime.ctx,
                    task_id=f"{runtime.ctx.task_id}:report_card_manifest",
                ),
            )
            report_card_manifest_path = manifest_response.manifest_path
        else:
            cover_error = str(
                getattr(cover_outcome, "error", None)
                or "All three canonical report-card covers are required"
            )
            report_card_error = f"cover_asset_set_incomplete: {cover_error}"
            logger.info(
                log_event(
                    cover_ctx,
                    role="generator",
                    event="report_card_cover_asset_set_incomplete",
                    module=logger.name,
                    fields={
                        "file_id": runtime.file.file_id,
                        "error": cover_error,
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
        if _is_card_contract_error(exc):
            report_card_error = f"{exc.code}: {exc.message}"
            event = "report_card_manifest_validation_failed"
        elif exc.code == "report_card_manifest_write_failed":
            report_card_error = f"{exc.code}: {exc.message}"
            event = "report_card_manifest_write_failed"
        else:
            event = "cover_image_generation_failed"
        logger.info(
            log_event(
                cover_ctx,
                role="generator",
                event=event,
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
        schema_version="1.1",
        file_id=runtime.file.file_id,
        name=runtime.file_name,
        md5=runtime.md5,
        html_path=out_html,
        status="error" if report_card_error else "processed",
        error=report_card_error,
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
        report_card_manifest_path=report_card_manifest_path,
    )
