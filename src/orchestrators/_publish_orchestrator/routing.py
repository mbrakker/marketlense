"""Routing helpers for publication orchestration."""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import re
from dataclasses import replace
from pathlib import Path

from src.contracts.files import ReadBytesRequest, ReadTextRequest, WriteBytesRequest
from src.contracts.publish import (
    PublishEntityMetadata,
    PublishSettings,
)
from src.contracts.report_analysis import (
    AnalysisGenerationByIdReadRequest,
    AnalysisGenerationResponse,
)
from src.contracts.report_publication_package import ReportPublicationPackage
from src.contracts.report_store import (
    ReportMetadataGetResponse,
    ReportMetadataListRequest,
)
from src.contracts.run_context import RunContext
from src.contracts.semantic_ids import ReportId
from src.orchestrators._publish_orchestrator.models import (
    _PUBLISH_ENTITY_ROUTES,
    _PUBLISH_ROUTES_BY_INTENT,
    _PublishCandidate,
    _PublishEntityRoute,
)
from src.orchestrators.publish_shared import canonicalize_html_path
from src.services.file_service import read_bytes, read_text, write_bytes
from src.services.report_analysis_store_service import read_generation_by_id
from src.services.report_store_service import list_metadata
from src.utils.cache_utils import sha256_json
from src.utils.errors import AppError
from src.utils.html_utils import build_publish_html_snapshot
from src.utils.logging import child_context, log_event
from src.utils.slugify import slugify

logger = logging.getLogger("market_lense.publish_orchestrator")


_REPORT_GENERATION_PACKS = (
    "artifacts",
    "validation",
    "validation_retained_claim_validation_candidate",
)


def _evidence_hashes_match(hashes: dict, selected: AnalysisGenerationResponse) -> bool:
    evidence = selected.packs.get("authoritative_evidence")
    if evidence is None:
        return True  # Historical generations did not retain this pack.
    expected = {
        f"evidence:{name}": sha256_json(payload)
        for name, payload in evidence.items()
        if isinstance(payload, dict)
    }
    actual = {
        key: value for key, value in hashes.items() if key.startswith("evidence:")
    }
    return actual == expected


def create_report_publication_package(
    *,
    html_path: str,
    readiness_reference: str,
    output_dir: str,
    report_id: str,
    report_slug: str,
    pack_paths: dict[str, str],
    ctx: RunContext,
) -> ReportPublicationPackage:
    """Freeze rendered surfaces alongside the generation verified before rendering."""
    if any(not pack_paths.get(name) for name in _REPORT_GENERATION_PACKS):
        raise AppError(
            code="report_publish_generation_missing",
            message="Report publication requires all generation packs",
            retryable=False,
        )
    artifact_path = Path(pack_paths["artifacts"])
    if artifact_path.parent.parent.name != ".generations":
        raise AppError(
            code="report_publish_generation_invalid",
            message="Report publication requires immutable generation paths",
            retryable=False,
        )
    generation = artifact_path.parent.name
    selected_paths = {name: pack_paths[name] for name in _REPORT_GENERATION_PACKS}
    selected = validate_report_generation_binding(
        output_dir=output_dir,
        report_id=report_id,
        report_slug=report_slug,
        generation=generation,
        pack_paths=selected_paths,
        ctx=ctx,
    )
    if "authoritative_evidence" not in selected.packs:
        raise AppError(
            code="report_publish_generation_missing",
            message="New Report packages require generation-bound evidence",
            retryable=False,
        )
    html = read_bytes(
        ReadBytesRequest(schema_version="1.0", path=html_path), ctx
    ).content
    readiness = read_bytes(
        ReadBytesRequest(schema_version="1.0", path=readiness_reference), ctx
    ).content
    try:
        decision = json.loads(readiness)
        hashes = decision["artifact_hashes"]
        if (
            decision.get("report_id") != report_id
            or decision.get("final_html_hash") != hashlib.sha256(html).hexdigest()
            or not isinstance(hashes, dict)
            or any(
                hashes.get(name) != sha256_json(selected.packs[name])
                for name in ("artifacts", "validation")
            )
            or not _evidence_hashes_match(hashes, selected)
        ):
            raise ValueError("readiness does not match generation")
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        raise AppError(
            code="report_publish_generation_mismatch",
            message="Readiness does not match the selected report generation and HTML",
            cause=exc,
            retryable=False,
        ) from exc
    root = Path(html_path).parent / ".publication"
    html_hash = hashlib.sha256(html).hexdigest()
    readiness_hash = hashlib.sha256(readiness).hexdigest()
    frozen_html = str(root / (html_hash + ".html"))
    frozen_readiness = str(root / (readiness_hash + ".json"))
    for path, content in ((frozen_html, html), (frozen_readiness, readiness)):
        write_bytes(
            WriteBytesRequest(schema_version="1.0", path=path, content=content),
            ctx,
            reject_conflicting_existing=True,
        )
    manifest = {
        "schema_version": "2.0",
        "type": "report_publication_package",
        "html_path": frozen_html,
        "html_sha256": html_hash,
        "readiness_path": frozen_readiness,
        "readiness_sha256": readiness_hash,
        "generation": generation,
        "output_dir": output_dir,
        "report_id": report_id,
        "report_slug": report_slug,
        "pack_paths": selected_paths,
    }
    data = json.dumps(
        manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode()
    manifest_path = str(root / (hashlib.sha256(data).hexdigest() + ".json"))
    write_bytes(
        WriteBytesRequest(schema_version="1.0", path=manifest_path, content=data),
        ctx,
        reject_conflicting_existing=True,
    )
    checksum = report_publish_package_checksum(
        html_path=frozen_html,
        readiness_reference=manifest_path,
        package_version="2.0",
        analysis_generation=generation,
        ctx=ctx,
    )
    return ReportPublicationPackage(
        "2.0", frozen_html, frozen_readiness, manifest_path, generation, checksum
    )


def resolve_report_publication_package(
    *,
    html_path: str,
    readiness_reference: str,
    checksum: str,
    ctx: RunContext,
    expected_report_id: str = "",
) -> str:
    """Verify an approved legacy or generation-bound package and return readiness."""
    content = read_bytes(
        ReadBytesRequest(schema_version="1.0", path=readiness_reference), ctx
    ).content
    try:
        raw = json.loads(content)
        if not isinstance(raw, dict):
            raise ValueError("invalid package")
        version = raw.get("schema_version")
        if version == "2.0" or raw.get("type") == "report_publication_package":
            if version != "2.0" or raw.get("type") != "report_publication_package":
                raise ValueError("invalid package version")
            generation = raw["generation"]
            paths = raw["pack_paths"]
            if not isinstance(paths, dict) or any(
                not paths.get(name) for name in _REPORT_GENERATION_PACKS
            ):
                raise ValueError("generation packs missing")
            if raw["html_path"] != html_path:
                raise ValueError("html reference mismatch")
            if expected_report_id and raw["report_id"] != expected_report_id:
                raise ValueError("report identity mismatch")
            selected = validate_report_generation_binding(
                output_dir=raw["output_dir"],
                report_id=raw["report_id"],
                report_slug=raw["report_slug"],
                generation=generation,
                pack_paths={name: paths[name] for name in _REPORT_GENERATION_PACKS},
                ctx=ctx,
            )
            actual = report_publish_package_checksum(
                html_path=html_path,
                readiness_reference=readiness_reference,
                package_version="2.0",
                analysis_generation=generation,
                ctx=ctx,
            )
            readiness_path = raw["readiness_path"]
            html = read_bytes(
                ReadBytesRequest(schema_version="1.0", path=html_path), ctx
            ).content
            readiness = read_bytes(
                ReadBytesRequest(schema_version="1.0", path=readiness_path), ctx
            ).content
            if (
                hashlib.sha256(html).hexdigest() != raw["html_sha256"]
                or hashlib.sha256(readiness).hexdigest() != raw["readiness_sha256"]
            ):
                raise ValueError("package surface mismatch")
            decision = json.loads(readiness)
            hashes = decision["artifact_hashes"]
            if (
                decision.get("report_id") != raw["report_id"]
                or decision.get("final_html_hash") != raw["html_sha256"]
                or not isinstance(hashes, dict)
                or any(
                    hashes.get(name) != sha256_json(selected.packs[name])
                    for name in ("artifacts", "validation")
                )
                or not _evidence_hashes_match(hashes, selected)
            ):
                raise ValueError("readiness does not match generation")
        else:
            if expected_report_id and raw.get("report_id") != expected_report_id:
                raise ValueError("report identity mismatch")
            actual = report_publish_package_checksum(
                html_path=html_path, readiness_reference=readiness_reference, ctx=ctx
            )
            readiness_path = readiness_reference
        if actual != checksum:
            raise ValueError("package checksum mismatch")
        return readiness_path
    except (
        ValueError,
        KeyError,
        TypeError,
        AttributeError,
        UnicodeDecodeError,
        AppError,
    ) as exc:
        raise AppError(
            code="workflow_queue_report_publish_package_checksum_mismatch",
            message=(
                "Approved Report package no longer matches its immutable references"
            ),
            cause=exc,
            retryable=False,
        ) from exc


def validate_report_generation_binding(
    *,
    output_dir: str,
    report_id: str,
    report_slug: str,
    generation: str,
    pack_paths: dict[str, str],
    ctx: RunContext,
) -> AnalysisGenerationResponse:
    """Verify supplied pack paths against one committed, content-checked generation."""
    selected = read_generation_by_id(
        AnalysisGenerationByIdReadRequest(
            schema_version="1.0",
            output_dir=output_dir,
            report_id=ReportId(report_id),
            report_slug=report_slug,
            generation=generation,
        ),
        ctx,
    )
    if not pack_paths or any(
        name not in selected.pack_paths
        or Path(path).resolve() != Path(selected.pack_paths[name]).resolve()
        for name, path in pack_paths.items()
    ):
        raise AppError(
            code="report_publish_generation_mismatch",
            message=(
                "Report publication pack paths do not match the committed generation"
            ),
            retryable=False,
        )
    return selected


def report_publish_package_checksum(
    *,
    html_path: str,
    readiness_reference: str,
    ctx: RunContext,
    analysis_generation: str = "",
    package_version: str = "1.0",
) -> str:
    """Hash the exact immutable Report surfaces approved for queue publication."""

    if (
        package_version not in {"1.0", "2.0"}
        or (
            package_version == "2.0"
            and not re.fullmatch(r"[0-9a-f]{64}", analysis_generation)
        )
        or (package_version == "1.0" and analysis_generation)
    ):
        raise AppError(
            code="report_publish_generation_invalid",
            message="Report publication requires a valid analysis generation hash",
            retryable=False,
        )
    html = read_bytes(ReadBytesRequest(schema_version="1.0", path=html_path), ctx)
    readiness = read_bytes(
        ReadBytesRequest(schema_version="1.0", path=readiness_reference), ctx
    )
    payload = {
        "schema_version": "1.0",
        "entity_type": "report",
        "html_sha256": hashlib.sha256(html.content).hexdigest(),
        "readiness_sha256": hashlib.sha256(readiness.content).hexdigest(),
    }
    if package_version == "2.0":
        payload["schema_version"] = "2.0"
        payload["analysis_generation"] = analysis_generation
    return hashlib.sha256(
        json.dumps(
            payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def _metadata_index(
    settings: PublishSettings, ctx: RunContext
) -> tuple[dict[str, str], dict[str, ReportMetadataGetResponse]]:
    response = list_metadata(
        ReportMetadataListRequest(schema_version="1.1", db_path=settings.reports_db),
        ctx,
    )
    html_file_id_map: dict[str, str] = {}
    metadata_by_file_id: dict[str, ReportMetadataGetResponse] = {}
    records = sorted(
        response.records,
        key=lambda row: int(getattr(row, "updated_at", 0) or 0),
        reverse=True,
    )
    for row in records:
        file_id = str(row.file_id or "").strip()
        html_path = str(row.html_path or "").strip()
        if file_id and file_id not in metadata_by_file_id:
            metadata_by_file_id[file_id] = row
        if html_path and file_id:
            key = canonicalize_html_path(html_path)
            if key not in html_file_id_map:
                html_file_id_map[key] = file_id
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="publish_preflight_metadata_loaded",
            module=logger.name,
            fields={
                "records": len(response.records),
                "mapped_html_paths": len(html_file_id_map),
                "mapped_file_ids": len(metadata_by_file_id),
            },
        )
    )
    return html_file_id_map, metadata_by_file_id


def _sort_auto_discovered_html_paths(
    html_paths: list[str],
    *,
    html_file_id_map: dict[str, str],
    metadata_by_file_id: dict[str, ReportMetadataGetResponse],
) -> list[str]:
    indexed_paths: list[tuple[int, int, int, str]] = []
    for index, html_path in enumerate(html_paths):
        file_id = html_file_id_map.get(canonicalize_html_path(html_path), "")
        metadata = metadata_by_file_id.get(file_id)
        updated_at = int(getattr(metadata, "updated_at", 0) or 0) if metadata else 0
        indexed_paths.append(
            (0 if updated_at > 0 else 1, -updated_at, index, html_path)
        )
    return [html_path for _, _, _, html_path in sorted(indexed_paths)]


def _publish_settings_for_post_type(
    settings: PublishSettings,
    post_type: str,
) -> PublishSettings:
    if post_type == settings.wp.post_type:
        return settings

    try:
        route_wp_settings = replace(settings.wp, post_type=post_type)
    except TypeError:
        route_wp_settings = copy.copy(settings.wp)
        object.__setattr__(route_wp_settings, "post_type", post_type)

    try:
        return replace(settings, wp=route_wp_settings)
    except TypeError:
        route_settings = copy.copy(settings)
        object.__setattr__(route_settings, "wp", route_wp_settings)
        return route_settings


def _require_publish_settings(settings: PublishSettings | None) -> PublishSettings:
    if settings is None:
        raise AppError(
            code="cross_report_publish_settings_missing",
            message="Cross-report live publishing requires WordPress publish settings.",
            retryable=False,
            severity="error",
            context={},
        )
    return settings


def _publish_entity_error(
    *,
    code: str,
    message: str,
    html_path: str,
    metadata: PublishEntityMetadata | None,
    context: dict[str, object] | None = None,
) -> AppError:
    return AppError(
        code=code,
        message=message,
        retryable=False,
        severity="error",
        context={
            "html_path": html_path,
            "entity_type": metadata.entity_type if metadata else "",
            "canonical_route_intent": metadata.canonical_route_intent
            if metadata
            else "",
            **dict(context or {}),
        },
    )


def _route_publish_entity_metadata(
    *,
    metadata: PublishEntityMetadata | None,
    html_path: str,
) -> _PublishEntityRoute:
    if metadata is None:
        raise _publish_entity_error(
            code="publish_entity_metadata_missing",
            message="Generated HTML artifact is missing public entity metadata.",
            html_path=html_path,
            metadata=None,
        )
    if metadata.schema_version != "1.0":
        raise _publish_entity_error(
            code="publish_entity_metadata_schema_unsupported",
            message="Generated HTML artifact has unsupported entity metadata schema.",
            html_path=html_path,
            metadata=metadata,
            context={"schema_version": metadata.schema_version},
        )
    if not metadata.publish_eligible:
        raise _publish_entity_error(
            code="publish_entity_not_eligible",
            message="Generated HTML artifact is not eligible for publication.",
            html_path=html_path,
            metadata=metadata,
        )
    route_by_entity = _PUBLISH_ENTITY_ROUTES.get(metadata.entity_type)
    route_by_intent = _PUBLISH_ROUTES_BY_INTENT.get(metadata.canonical_route_intent)
    if route_by_entity is None or route_by_intent is None:
        raise _publish_entity_error(
            code="publish_entity_metadata_unsupported",
            message=(
                "Generated HTML artifact declares an unsupported public entity route."
            ),
            html_path=html_path,
            metadata=metadata,
        )
    if route_by_entity != route_by_intent:
        raise _publish_entity_error(
            code="publish_entity_metadata_mismatch",
            message=(
                "Generated HTML artifact entity type and route intent do not match."
            ),
            html_path=html_path,
            metadata=metadata,
            context={
                "expected_route_intent": route_by_entity.canonical_route_intent,
                "expected_post_type": route_by_entity.post_type,
            },
        )
    return route_by_entity


def _resolve_publish_candidates(
    *,
    html_paths: list[str],
    html_file_id_map: dict[str, str],
    ctx: RunContext,
    skip_unowned_nonpublish_html: bool = False,
) -> list[_PublishCandidate]:
    candidates: list[_PublishCandidate] = []
    for html_path in html_paths:
        file_ctx = child_context(ctx, task_id=html_path)
        html_text = read_text(
            ReadTextRequest(schema_version="1.0", path=html_path), file_ctx
        ).content
        html_snapshot = build_publish_html_snapshot(html_text)
        file_id = html_file_id_map.get(canonicalize_html_path(html_path), "")
        file_id_source = "reports_db" if file_id else ""
        if not file_id:
            file_id = str(
                html_snapshot.file_id
                or (
                    html_snapshot.entity_metadata.source_artifact_id
                    if html_snapshot.entity_metadata
                    else ""
                )
            ).strip()
            if file_id:
                file_id_source = "html" if html_snapshot.file_id else "entity_metadata"
        entity_route: _PublishEntityRoute | None = None
        entity_error: AppError | None = None
        try:
            if (
                html_snapshot.entity_metadata is None
                and file_id
                and file_id_source == "reports_db"
            ):
                # Report HTML intentionally contains no internal source ID or
                # hidden publication marker. The report-store mapping is the
                # authoritative private routing seam.
                entity_route = _PUBLISH_ENTITY_ROUTES["report"]
            else:
                entity_route = _route_publish_entity_metadata(
                    metadata=html_snapshot.entity_metadata,
                    html_path=html_path,
                )
            logger.info(
                log_event(
                    file_ctx,
                    role="orchestrator",
                    event="publish_entity_metadata_routed",
                    module=logger.name,
                    fields={
                        "html_path": html_path,
                        "entity_type": entity_route.entity_type,
                        "canonical_route_intent": entity_route.canonical_route_intent,
                        "post_type": entity_route.post_type,
                        "front_end_section": entity_route.front_end_section,
                        "template": entity_route.template,
                    },
                )
            )
        except AppError as exc:
            if (
                skip_unowned_nonpublish_html
                and exc.code == "publish_entity_metadata_missing"
                and not file_id
            ):
                logger.info(
                    log_event(
                        file_ctx,
                        role="orchestrator",
                        event="publish_non_entity_html_skipped",
                        module=logger.name,
                        fields={
                            "html_path": html_path,
                            "code": exc.code,
                            "reason": "missing_publish_metadata_and_source_artifact",
                        },
                    )
                )
                continue
            entity_error = exc
            logger.info(
                log_event(
                    file_ctx,
                    role="orchestrator",
                    event="publish_entity_metadata_invalid",
                    module=logger.name,
                    fields={
                        "html_path": html_path,
                        "code": exc.code,
                        "error": exc.message,
                        **exc.context,
                    },
                )
            )
        if file_id:
            logger.info(
                log_event(
                    file_ctx,
                    role="orchestrator",
                    event="publish_file_id_resolved",
                    module=logger.name,
                    fields={
                        "html_path": html_path,
                        "file_id": file_id,
                        "source": file_id_source,
                    },
                )
            )
        candidates.append(
            _PublishCandidate(
                html_path=html_path,
                file_id=file_id or None,
                html_snapshot=html_snapshot,
                entity_route=entity_route,
                entity_error=entity_error,
            )
        )
    return candidates


def _normalize_string_list(values: list[str] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_value in values or []:
        value = str(raw_value or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def _normalize_tag_slugs(values: list[str] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_value in values or []:
        slug = slugify(raw_value)
        if not slug or slug in seen:
            continue
        seen.add(slug)
        normalized.append(slug)
    return normalized
