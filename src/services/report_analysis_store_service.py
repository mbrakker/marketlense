from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path

from src.contracts.files import WriteBytesRequest
from src.contracts.report_analysis import (
    AnalysisPackPathRequest,
    AnalysisPackPathResponse,
    AnalysisStorePackRequest,
    AnalysisStorePackResponse,
)
from src.contracts.run_context import RunContext
from src.contracts.schema_validation import SchemaValidateRequest
from src.services import file_service
from src.services.schema_validator_service import validate_schema
from src.utils.errors import AppError
from src.utils.logging import log_event
from src.utils.path_utils import (
    WINDOWS_COMPONENT_BUDGET,
    is_windows_reserved_component,
    windows_path_units,
)
from src.utils.slugify import slugify

logger = logging.getLogger("market_lense.report_analysis_store_service")
_SAFE_PACK_NAME_RX = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_PATH_COMPONENT_HASH_LENGTH = 12
_MAX_SUPPORTED_PATH_LENGTH = file_service.WINDOWS_MAX_PATH_LENGTH - 1
_PACK_SCHEMA_NAMES: dict[str, str] = {
    "artifacts": "artifacts",
    "context_category_fit": "context_category_fit",
    "doc_map": "doc_map",
    "findings": "findings_pack",
    "limitations": "limitations_pack",
    "methods": "methods_pack",
    "publish_readiness": "publish_readiness",
    "quote_candidates": "quote_candidates_pack",
    "scope": "scope_pack",
    "taxonomy": "taxonomy",
    "validation": "validation_report",
    "retained_claim_validation": "claim_validation_package",
    "validation_retained_claim_validation_candidate": "claim_validation_package",
}


def _report_base_dir(output_dir: str, report_slug: str) -> Path:
    return Path(output_dir) / report_slug / "report_analysis"


def _compact_component(value: str, max_length: int) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[
        :_PATH_COMPONENT_HASH_LENGTH
    ]
    if max_length < windows_path_units(digest):
        return ""
    if windows_path_units(value) <= max_length:
        return value
    prefix_budget = max(0, max_length - windows_path_units(digest) - 1)
    prefix_chars: list[str] = []
    prefix_units = 0
    for character in value:
        character_units = windows_path_units(character)
        if prefix_units + character_units > prefix_budget:
            break
        prefix_chars.append(character)
        prefix_units += character_units
    prefix = "".join(prefix_chars).rstrip(" .-_")
    return f"{prefix}-{digest}" if prefix else digest


def _path_fits(path: Path) -> bool:
    try:
        resolved = path.resolve(strict=False)
        if windows_path_units(resolved) > _MAX_SUPPORTED_PATH_LENGTH:
            return False
        if (
            file_service.atomic_write_temp_path_length(resolved)
            > file_service.WINDOWS_SAFE_ATOMIC_PATH_LENGTH
        ):
            return False
    except (OSError, RuntimeError, TypeError, ValueError):
        return False
    anchor = resolved.anchor
    for component in resolved.parts:
        if component in {anchor, "/", "\\", ""}:
            continue
        if windows_path_units(component) > WINDOWS_COMPONENT_BUDGET:
            return False
        if is_windows_reserved_component(component):
            return False
    return True


def _safe_path_measurements(
    path: Path,
) -> tuple[int | None, int | None, str | None, Exception | None]:
    try:
        resolved = path.resolve(strict=False)
        return (
            windows_path_units(resolved),
            file_service.atomic_write_temp_path_length(resolved),
            None,
            None,
        )
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        return None, None, f"path_measurement_failed:{type(exc).__name__}", exc


def _raise_if_pack_path_redirected(output_dir: str, path: Path) -> None:
    reason = file_service.path_redirect_reason(
        path,
        allowed_root=Path(output_dir).expanduser(),
    )
    if reason is None:
        return
    raise AppError(
        code="analysis_pack_path_invalid",
        message=(
            "Report-analysis pack destination traverses a symlink or reparse "
            "point below the configured output root; choose a clean output root"
        ),
        retryable=False,
        context={
            "output_dir": output_dir,
            "path": str(path),
            "reason": reason,
            "next_action": "remove redirected child directories and retry",
        },
    )


def _bounded_pack_components(
    output_dir: str, report_slug: str, pack_name: str
) -> tuple[str, str]:
    """Resolve deterministic names within both destination and atomic-temp budgets."""

    plain_path = _report_base_dir(output_dir, report_slug) / f"{pack_name}.json"
    _raise_if_pack_path_redirected(output_dir, plain_path)
    if _path_fits(plain_path):
        return report_slug, pack_name

    hash_slug = hashlib.sha256(report_slug.encode("utf-8")).hexdigest()[
        :_PATH_COMPONENT_HASH_LENGTH
    ]
    slug_path = _report_base_dir(output_dir, hash_slug) / f"{pack_name}.json"
    _raise_if_pack_path_redirected(output_dir, slug_path)
    if _path_fits(slug_path):
        slug_destination_units, slug_atomic_units, _, _ = _safe_path_measurements(
            slug_path
        )
        if slug_destination_units is not None and slug_atomic_units is not None:
            final_room = max(0, _MAX_SUPPORTED_PATH_LENGTH - slug_destination_units)
            atomic_room = max(
                0,
                file_service.WINDOWS_SAFE_ATOMIC_PATH_LENGTH - slug_atomic_units,
            )
            slug_max_length = _PATH_COMPONENT_HASH_LENGTH + min(final_room, atomic_room)
            compact_slug = _compact_component(report_slug, slug_max_length)
            compact_path = (
                _report_base_dir(output_dir, compact_slug) / f"{pack_name}.json"
            )
            _raise_if_pack_path_redirected(output_dir, compact_path)
            if compact_slug and _path_fits(compact_path):
                return compact_slug, pack_name

    pack_hash = hashlib.sha256(pack_name.encode("utf-8")).hexdigest()[
        :_PATH_COMPONENT_HASH_LENGTH
    ]
    minimum_path = _report_base_dir(output_dir, hash_slug) / f"{pack_hash}.json"
    _raise_if_pack_path_redirected(output_dir, minimum_path)
    (
        minimum_destination_units,
        minimum_atomic_units,
        minimum_measurement_failure,
        minimum_measurement_cause,
    ) = _safe_path_measurements(minimum_path)
    if (
        not _path_fits(minimum_path)
        or minimum_destination_units is None
        or minimum_atomic_units is None
    ):
        raise AppError(
            code="analysis_pack_path_too_long",
            message=(
                "Report-analysis pack destination cannot fit under the configured "
                "path budget without shortening the operator-supplied output root"
            ),
            retryable=False,
            context={
                "pack_name": pack_name,
                "destination_path_length": minimum_destination_units,
                "atomic_temp_path_length": minimum_atomic_units,
                "measurement_failure": minimum_measurement_failure or "",
            },
            cause=minimum_measurement_cause,
        )

    final_room = max(0, _MAX_SUPPORTED_PATH_LENGTH - minimum_destination_units)
    atomic_room = max(
        0,
        file_service.WINDOWS_SAFE_ATOMIC_PATH_LENGTH - minimum_atomic_units,
    )
    # Keep readable prefixes on both components when the remaining budget allows.
    slug_room = min(atomic_room, final_room // 2)
    compact_slug = _compact_component(
        report_slug, _PATH_COMPONENT_HASH_LENGTH + slug_room
    )
    compact_base = _report_base_dir(output_dir, compact_slug) / f"{pack_hash}.json"
    _raise_if_pack_path_redirected(output_dir, compact_base)
    compact_base_destination_units, _, _, _ = _safe_path_measurements(compact_base)
    pack_room = max(
        0,
        _MAX_SUPPORTED_PATH_LENGTH
        - (compact_base_destination_units or _MAX_SUPPORTED_PATH_LENGTH),
    )
    compact_pack = _compact_component(
        pack_name, _PATH_COMPONENT_HASH_LENGTH + pack_room
    )
    compact_path = _report_base_dir(output_dir, compact_slug) / f"{compact_pack}.json"
    _raise_if_pack_path_redirected(output_dir, compact_path)
    (
        compact_destination_units,
        compact_atomic_units,
        compact_measurement_failure,
        compact_measurement_cause,
    ) = _safe_path_measurements(compact_path)
    if not compact_slug or not compact_pack or not _path_fits(compact_path):
        raise AppError(
            code="analysis_pack_path_too_long",
            message=(
                "Report-analysis pack destination exceeds the supported path budget"
            ),
            retryable=False,
            context={
                "pack_name": pack_name,
                "destination_path_length": compact_destination_units,
                "atomic_temp_path_length": compact_atomic_units,
                "measurement_failure": compact_measurement_failure or "",
            },
            cause=compact_measurement_cause,
        )
    return compact_slug, compact_pack


def _resolve_report_slug(report_slug: str | None, report_id: str) -> str:
    slug_source = report_slug if report_slug else report_id
    slug = slugify(slug_source)
    return slug or "report"


def _schema_name_for_pack(pack_name: str) -> str:
    normalized = str(pack_name or "").strip()
    if normalized.startswith("artifacts_regen_candidate_"):
        return "artifacts"
    if normalized.startswith("artifacts_regen_attempt_"):
        return "artifacts"
    if normalized.startswith("regeneration_candidate_audit_"):
        return "regeneration_candidate_audit"
    if normalized.startswith("validation_regen_candidate_") and normalized.endswith(
        "_retained_claim_validation_candidate"
    ):
        return "claim_validation_package"
    if normalized.startswith("validation_regen_candidate_"):
        return "validation_report"
    if normalized.startswith("validation_regen_attempt_"):
        return "validation_report"
    return _PACK_SCHEMA_NAMES.get(normalized, "")


def _validate_pack_name(pack_name: str) -> str:
    normalized = str(pack_name or "").strip()
    if normalized and _SAFE_PACK_NAME_RX.fullmatch(normalized):
        return normalized
    raise AppError(
        code="analysis_pack_name_invalid",
        message="Analysis pack name must be a single safe filename segment",
        retryable=False,
        context={"pack_name": pack_name},
    )


def pack_path(
    request: AnalysisPackPathRequest, ctx: RunContext
) -> AnalysisPackPathResponse:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="analysis_pack_path_start",
            module=logger.name,
            fields={
                "report_id": request.report_id,
                "pack_name": request.pack_name,
                "report_slug": request.report_slug or "",
            },
        )
    )
    pack_name = _validate_pack_name(request.pack_name)
    resolved_slug = _resolve_report_slug(request.report_slug, request.report_id)
    slug, stored_pack_name = _bounded_pack_components(
        request.output_dir, resolved_slug, pack_name
    )
    path = _report_base_dir(request.output_dir, slug) / f"{stored_pack_name}.json"
    response = AnalysisPackPathResponse(schema_version="1.0", output_path=str(path))
    logger.info(
        log_event(
            ctx,
            role="service",
            event="analysis_pack_path_complete",
            module=logger.name,
            fields={
                "path": response.output_path,
                "report_slug_compacted": slug != resolved_slug,
                "pack_name_compacted": stored_pack_name != pack_name,
            },
        )
    )
    return response


def store_pack(
    request: AnalysisStorePackRequest, ctx: RunContext
) -> AnalysisStorePackResponse:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="analysis_store_start",
            module=logger.name,
            fields={
                "report_id": request.report_id,
                "pack_name": request.pack_name,
                "report_slug": request.report_slug or "",
            },
        )
    )

    primary_path = Path(
        pack_path(
            AnalysisPackPathRequest(
                schema_version="1.0",
                output_dir=request.output_dir,
                report_id=request.report_id,
                pack_name=request.pack_name,
                report_slug=request.report_slug,
            ),
            ctx,
        ).output_path
    )
    schema_name = _schema_name_for_pack(request.pack_name)
    try:
        if schema_name:
            try:
                validate_schema(
                    SchemaValidateRequest(
                        schema_version="1.0",
                        payload=request.payload,
                        schema_name=schema_name,
                    ),
                    ctx,
                )
            except AppError as exc:
                logger.info(
                    log_event(
                        ctx,
                        role="service",
                        event="analysis_store_schema_validation_failed",
                        module=logger.name,
                        fields={
                            "report_id": request.report_id,
                            "pack_name": request.pack_name,
                            "schema_name": schema_name,
                            "path": str(primary_path),
                            "code": exc.code,
                            "message": exc.message,
                        },
                    )
                )
                raise
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="analysis_store_schema_validated",
                    module=logger.name,
                    fields={
                        "report_id": request.report_id,
                        "pack_name": request.pack_name,
                        "schema_name": schema_name,
                        "path": str(primary_path),
                    },
                )
            )
        primary_path.parent.mkdir(parents=True, exist_ok=True)
        payload_json = json.dumps(request.payload, ensure_ascii=False, indent=2)
        file_service.write_bytes(
            WriteBytesRequest(
                schema_version="1.0",
                path=str(primary_path),
                content=payload_json.encode("utf-8"),
            ),
            ctx,
        )
    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            code="analysis_store_failed",
            message=(
                f"Failed to store analysis pack '{request.pack_name}' for report "
                f"'{request.report_id}'"
            ),
            cause=exc,
            retryable=False,
            context={
                "output_dir": request.output_dir,
                "report_id": request.report_id,
                "pack_name": request.pack_name,
                "path": str(primary_path),
            },
        ) from exc

    response = AnalysisStorePackResponse(
        schema_version="1.0",
        output_path=str(primary_path),
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="analysis_store_complete",
            module=logger.name,
            fields={
                "report_id": request.report_id,
                "pack_name": request.pack_name,
                "path": response.output_path,
            },
        )
    )
    return response
