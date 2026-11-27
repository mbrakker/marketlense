from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
from contextlib import contextmanager
from pathlib import Path

from src.contracts.files import WriteBytesRequest
from src.contracts.report_analysis import (
    AnalysisGenerationByIdReadRequest,
    AnalysisGenerationCommitRequest,
    AnalysisGenerationReadRequest,
    AnalysisGenerationResponse,
    AnalysisPackPathRequest,
    AnalysisPackPathResponse,
    AnalysisStorePackRequest,
    AnalysisStorePackResponse,
)
from src.contracts.run_context import RunContext
from src.contracts.schema_validation import SchemaValidateRequest
from src.services import file_service, lock_service
from src.services.schema_validator_service import validate_schema
from src.utils.errors import AppError
from src.utils.logging import log_event
from src.utils.slugify import slugify

logger = logging.getLogger("market_lense.report_analysis_store_service")
_SAFE_PACK_NAME_RX = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_PATH_COMPONENT_HASH_LENGTH = 12
_MAX_SUPPORTED_PATH_LENGTH = file_service.WINDOWS_MAX_PATH_LENGTH - 1
_generation_lock = threading.Lock()


def _sync_generation_directory(directory: Path) -> None:
    # Windows does not expose a portable directory fsync through Python.
    if os.name != "nt":
        descriptor = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


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
    if max_length < len(digest):
        return ""
    if len(value) <= max_length:
        return value
    prefix_budget = max(0, max_length - len(digest) - 1)
    prefix = value[:prefix_budget].rstrip(" .-_")
    return f"{prefix}-{digest}" if prefix else digest


def _path_fits(path: Path) -> bool:
    return (
        len(str(path.resolve())) <= _MAX_SUPPORTED_PATH_LENGTH
        and file_service.atomic_write_temp_path_length(path)
        <= file_service.WINDOWS_SAFE_ATOMIC_PATH_LENGTH
    )


def _bounded_pack_components(
    output_dir: str, report_slug: str, pack_name: str
) -> tuple[str, str]:
    """Resolve deterministic names within both destination and atomic-temp budgets."""

    plain_path = _report_base_dir(output_dir, report_slug) / f"{pack_name}.json"
    if _path_fits(plain_path):
        return report_slug, pack_name

    hash_slug = hashlib.sha256(report_slug.encode("utf-8")).hexdigest()[
        :_PATH_COMPONENT_HASH_LENGTH
    ]
    slug_path = _report_base_dir(output_dir, hash_slug) / f"{pack_name}.json"
    if _path_fits(slug_path):
        final_room = max(0, _MAX_SUPPORTED_PATH_LENGTH - len(str(slug_path.resolve())))
        atomic_room = max(
            0,
            file_service.WINDOWS_SAFE_ATOMIC_PATH_LENGTH
            - file_service.atomic_write_temp_path_length(slug_path),
        )
        slug_max_length = _PATH_COMPONENT_HASH_LENGTH + min(final_room, atomic_room)
        return _compact_component(report_slug, slug_max_length), pack_name

    pack_hash = hashlib.sha256(pack_name.encode("utf-8")).hexdigest()[
        :_PATH_COMPONENT_HASH_LENGTH
    ]
    minimum_path = _report_base_dir(output_dir, hash_slug) / f"{pack_hash}.json"
    if not _path_fits(minimum_path):
        raise AppError(
            code="analysis_pack_path_too_long",
            message=(
                "Report-analysis pack destination cannot fit under the configured "
                "path budget without shortening the operator-supplied output root"
            ),
            retryable=False,
            context={
                "pack_name": pack_name,
                "destination_path_length": len(str(minimum_path.resolve())),
                "atomic_temp_path_length": file_service.atomic_write_temp_path_length(
                    minimum_path
                ),
            },
        )

    final_room = max(0, _MAX_SUPPORTED_PATH_LENGTH - len(str(minimum_path.resolve())))
    atomic_room = max(
        0,
        file_service.WINDOWS_SAFE_ATOMIC_PATH_LENGTH
        - file_service.atomic_write_temp_path_length(minimum_path),
    )
    # Keep readable prefixes on both components when the remaining budget allows.
    slug_room = min(atomic_room, final_room // 2)
    compact_slug = _compact_component(
        report_slug, _PATH_COMPONENT_HASH_LENGTH + slug_room
    )
    compact_base = _report_base_dir(output_dir, compact_slug) / f"{pack_hash}.json"
    pack_room = max(0, _MAX_SUPPORTED_PATH_LENGTH - len(str(compact_base.resolve())))
    compact_pack = _compact_component(
        pack_name, _PATH_COMPONENT_HASH_LENGTH + pack_room
    )
    compact_path = _report_base_dir(output_dir, compact_slug) / f"{compact_pack}.json"
    if not _path_fits(compact_path):
        raise AppError(
            code="analysis_pack_path_too_long",
            message=(
                "Report-analysis pack destination exceeds the supported path budget"
            ),
            retryable=False,
            context={
                "pack_name": pack_name,
                "destination_path_length": len(str(compact_path.resolve())),
                "atomic_temp_path_length": file_service.atomic_write_temp_path_length(
                    compact_path
                ),
            },
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


def _generation_directory(
    request: AnalysisGenerationReadRequest, ctx: RunContext
) -> Path:
    path = pack_path(
        AnalysisPackPathRequest(
            schema_version="1.0",
            output_dir=request.output_dir,
            report_id=request.report_id,
            report_slug=request.report_slug,
            pack_name="artifacts",
        ),
        ctx,
    )
    return Path(path.output_path).parent


@contextmanager
def _generation_writer_lock(directory: Path):
    # The stable lock file is never replaced or removed: the kernel releases the
    # byte-range/flock lock if a writer dies, including during manifest replacement.
    with (
        _generation_lock,
        lock_service.filesystem_coordination_guard(str(directory / ".generation.lock")),
    ):
        yield


def _read_generation(
    directory: Path, generation: str | None = None, *, expected_report_id: str = ""
) -> AnalysisGenerationResponse:
    try:
        if generation is None:
            manifest = json.loads(
                (directory / ".generation-manifest.json").read_bytes()
            )
            generation = manifest["generation"]
            if manifest.get("schema_version") != "1.0":
                raise ValueError("invalid generation manifest")
        if not isinstance(generation, str) or not re.fullmatch(
            r"[0-9a-f]{64}", generation
        ):
            raise ValueError("invalid generation manifest")
        data = (directory / ".generations" / (generation + ".json")).read_bytes()
        body = json.loads(data)
        if body.get("schema_version") not in {
            "1.0",
            "1.1",
            "1.2",
            "1.3",
        } or not isinstance(body.get("packs"), dict):
            raise ValueError("invalid generation")
        identity_body = body
        parent = ""
        if body["schema_version"] in {"1.1", "1.2", "1.3"}:
            if body["schema_version"] in {"1.2", "1.3"}:
                parent = body.get("parent_generation")
                if not isinstance(parent, str) or (
                    parent and not re.fullmatch(r"[0-9a-f]{64}", parent)
                ):
                    raise ValueError("invalid generation parent")
            report_id = (
                body.get("report_id", "") if body["schema_version"] == "1.3" else ""
            )
            if body["schema_version"] == "1.3" and (
                not isinstance(report_id, str)
                or not report_id
                or (expected_report_id and report_id != expected_report_id)
            ):
                raise ValueError("generation report identity mismatch")
            identity_body = _generation_identity_body(
                body["packs"],
                parent if body["schema_version"] in {"1.2", "1.3"} else None,
                report_id=report_id,
            )
            validation = body["packs"].get("validation")
            if validation is not None and validation.get("source_path") != str(
                _generation_pack_path(directory, generation, "validation")
            ):
                raise ValueError("validation source path mismatch")
        if (
            hashlib.sha256(_generation_pack_bytes(identity_body)).hexdigest()
            != generation
        ):
            raise ValueError("generation hash mismatch")
        paths = {}
        for name, payload in body["packs"].items():
            _validate_pack_name(name)
            if not isinstance(payload, dict):
                raise ValueError("invalid generation pack")
            path = _generation_pack_path(directory, generation, name)
            if path.read_bytes() != _generation_pack_bytes(payload):
                raise ValueError("generation pack mismatch")
            paths[name] = str(path)
        return AnalysisGenerationResponse(
            schema_version="1.0",
            generation=generation,
            packs=body["packs"],
            pack_paths=paths,
            parent_generation=parent,
        )
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise AppError(
            code="analysis_generation_invalid",
            message="Committed analysis generation is unavailable or invalid",
            retryable=False,
            cause=exc,
        ) from exc


def _generation_pack_bytes(payload: dict) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _generation_identity_body(
    packs: dict, parent: str | None = None, *, report_id: str = ""
) -> dict:
    identity_packs = dict(packs)
    if "validation" in identity_packs:
        identity_packs["validation"] = dict(
            identity_packs["validation"], source_path=""
        )
    body = {
        "schema_version": "1.3" if report_id else ("1.1" if parent is None else "1.2"),
        "packs": identity_packs,
    }
    if parent is not None:
        body["parent_generation"] = parent
    if report_id:
        body["report_id"] = report_id
    return body


def _generation_pack_path(directory: Path, generation: str, name: str) -> Path:
    name_hash = hashlib.sha256(name.encode("utf-8")).hexdigest()[:16]
    return directory / ".generations" / generation / (name_hash + ".json")


def _validate_generation_paths(
    directory: Path, generation: str, names: list[str]
) -> None:
    paths = [
        directory / ".generations" / (generation + ".json"),
        directory / ".generation-manifest.json",
        *(_generation_pack_path(directory, generation, name) for name in names),
    ]
    if os.name != "posix" and not all(_path_fits(path) for path in paths):
        raise AppError(
            code="analysis_generation_path_too_long",
            message=(
                "Generation paths exceed the supported atomic-write path budget; "
                "shorten the output root"
            ),
            retryable=False,
        )


def validate_generation_path(
    request: AnalysisGenerationReadRequest, ctx: RunContext
) -> None:
    """Check the immutable generation path budget without writing artifacts."""
    directory = _generation_directory(request, ctx)
    # All generation and pack identifiers have fixed digest lengths.
    _validate_generation_paths(directory, "0" * 64, ["artifacts"])


def _require_no_legacy_promotion(directory: Path) -> None:
    try:
        (directory / ".promotion-pending").lstat()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise AppError(
            code="regeneration_promotion_recovery_failed",
            message="Cannot verify existing promotion marker",
            retryable=False,
            cause=exc,
        ) from exc
    raise AppError(
        code="regeneration_promotion_recovery_failed",
        message="Existing promotion marker requires recovery",
        retryable=False,
    )


def _path_present(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise AppError(
            code="analysis_generation_invalid",
            message="Cannot inspect generation state",
            retryable=False,
            cause=exc,
        ) from exc
    return True


def read_generation(
    request: AnalysisGenerationReadRequest, ctx: RunContext
) -> AnalysisGenerationResponse:
    """Read one manifest-selected generation; legacy pack reads are independent."""
    if request.schema_version != "1.0":
        raise AppError(
            code="analysis_generation_version_invalid",
            message="Unsupported generation request version",
            retryable=False,
        )
    directory = _generation_directory(request, ctx)
    _require_no_legacy_promotion(directory)
    if not _path_present(directory / ".generation-manifest.json"):
        raise AppError(
            code="analysis_generation_missing",
            message="No committed analysis generation",
            retryable=False,
        )
    result = _read_generation(directory, expected_report_id=request.report_id)
    _require_no_legacy_promotion(directory)
    return result


def read_generation_by_id(
    request: AnalysisGenerationByIdReadRequest, ctx: RunContext
) -> AnalysisGenerationResponse:
    """Read a generation only if reachable from the current committed manifest."""
    if (
        request.schema_version != "1.0"
        or not isinstance(request.generation, str)
        or not re.fullmatch(r"[0-9a-f]{64}", request.generation)
    ):
        raise AppError(
            code="analysis_generation_invalid",
            message="Invalid generation identifier",
            retryable=False,
        )
    directory = _generation_directory(request, ctx)
    _require_no_legacy_promotion(directory)
    current = _read_generation(directory, expected_report_id=request.report_id)
    visited = set()
    while current.generation != request.generation:
        if not current.parent_generation or current.generation in visited:
            raise AppError(
                code="analysis_generation_invalid",
                message="Generation is not in the committed history",
                retryable=False,
            )
        visited.add(current.generation)
        current = _read_generation(
            directory, current.parent_generation, expected_report_id=request.report_id
        )
    return current


def commit_generation(
    request: AnalysisGenerationCommitRequest, ctx: RunContext, *, write_bytes=None
) -> AnalysisGenerationResponse:
    """Commit a complete generation if the manifest still names its expected parent.

    This primitive coordinates only participating writers. It does not project
    packs to legacy paths or coordinate the existing promotion marker producer.
    """
    write_bytes = write_bytes or file_service.write_bytes
    if (
        request.schema_version != "1.0"
        or not request.packs
        or not isinstance(request.report_id, str)
        or not request.report_id.strip()
    ):
        raise AppError(
            code="analysis_generation_invalid",
            message="Invalid generation request",
            retryable=False,
        )
    for name, payload in request.packs.items():
        _validate_pack_name(name)
        if not isinstance(payload, dict):
            raise AppError(
                code="analysis_generation_invalid",
                message="Generation packs must be objects",
                retryable=False,
            )
        schema_name = _schema_name_for_pack(name)
        if schema_name:
            validate_schema(
                SchemaValidateRequest(
                    schema_version="1.0", payload=payload, schema_name=schema_name
                ),
                ctx,
            )
    directory = _generation_directory(request, ctx)
    generation = hashlib.sha256(
        _generation_pack_bytes(
            _generation_identity_body(
                request.packs, request.expected_generation, report_id=request.report_id
            )
        )
    ).hexdigest()
    packs = dict(request.packs)
    if "validation" in packs:
        packs["validation"] = dict(
            packs["validation"],
            source_path=str(_generation_pack_path(directory, generation, "validation")),
        )
    data = _generation_pack_bytes(
        {
            "schema_version": "1.3",
            "packs": packs,
            "parent_generation": request.expected_generation,
            "report_id": request.report_id,
        }
    )
    # Keep the canonical directory and the conservative budget on Windows and
    # unknown platforms. POSIX writes use native limits and the same atomic protocol.
    _validate_generation_paths(directory, generation, list(packs))
    with _generation_writer_lock(directory):
        _require_no_legacy_promotion(directory)
        manifest = directory / ".generation-manifest.json"
        current = (
            _read_generation(directory, expected_report_id=request.report_id).generation
            if _path_present(manifest)
            else ""
        )
        if current != request.expected_generation:
            raise AppError(
                code="analysis_generation_conflict",
                message="Analysis generation changed",
                retryable=False,
            )
        if current:
            try:
                current_body = json.loads(
                    (directory / ".generations" / (current + ".json")).read_bytes()
                )
            except (OSError, ValueError) as exc:
                raise AppError(
                    code="analysis_generation_invalid",
                    message="Cannot inspect the current analysis generation",
                    retryable=False,
                    cause=exc,
                ) from exc
            if current_body.get("schema_version") != "1.3":
                raise AppError(
                    code="analysis_generation_identity_unbound",
                    message=(
                        "Cannot advance a historical generation without report identity"
                    ),
                    retryable=False,
                )
        generation_dir = directory / ".generations"
        generation_dir.mkdir(exist_ok=True)
        _sync_generation_directory(directory)
        generation_path = generation_dir / (generation + ".json")
        if _path_present(generation_path):
            if generation_path.read_bytes() != data:
                raise AppError(
                    code="analysis_generation_invalid",
                    message="Existing generation is corrupt",
                    retryable=False,
                )
        else:
            write_bytes(
                WriteBytesRequest(
                    schema_version="1.0", path=str(generation_path), content=data
                ),
                ctx,
            )
        pack_dir = generation_dir / generation
        pack_dir.mkdir(exist_ok=True)
        for name, payload in packs.items():
            pack_path = _generation_pack_path(directory, generation, name)
            data_for_pack = _generation_pack_bytes(payload)
            if _path_present(pack_path):
                if pack_path.read_bytes() != data_for_pack:
                    raise AppError(
                        code="analysis_generation_invalid",
                        message="Existing generation pack is corrupt",
                        retryable=False,
                    )
            else:
                write_bytes(
                    WriteBytesRequest(
                        schema_version="1.0", path=str(pack_path), content=data_for_pack
                    ),
                    ctx,
                )
        _sync_generation_directory(pack_dir)
        _sync_generation_directory(generation_dir)
        try:
            write_bytes(
                WriteBytesRequest(
                    schema_version="1.0",
                    path=str(manifest),
                    content=json.dumps(
                        {"schema_version": "1.0", "generation": generation},
                        sort_keys=True,
                    ).encode("utf-8"),
                ),
                ctx,
            )
        except Exception as write_error:
            try:
                observed = _read_generation(
                    directory, expected_report_id=request.report_id
                )
            except AppError:
                raise write_error from None
            if observed.generation != generation:
                raise
        _sync_generation_directory(directory)
        return _read_generation(directory, expected_report_id=request.report_id)
