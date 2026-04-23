from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Any

from src.contracts.run_context import RunContext
from src.contracts.ui_run_replay import (
    UiRunArtifactFingerprint,
    UiRunArtifactFingerprintRequest,
    UiRunArtifactFingerprintResponse,
    UiRunReplayCaptureRequest,
    UiRunReplayCaptureResponse,
    UiRunReplayManifest,
    UiRunReplayReadRequest,
    UiRunReplayReadResponse,
    UiRunReplayReport,
    UiRunReplayReportWriteRequest,
    UiRunReplayReportWriteResponse,
    UiRunWorkspaceFingerprintRequest,
    UiRunWorkspaceFingerprintResponse,
)
from src.utils.cache_utils import stable_json_dumps
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.ui_run_replay_service")

REPLAY_MANIFEST_FILE_NAME = "replay_manifest.json"
REPLAY_REPORT_DIR_NAME = "replays"


def _run_state_dir(registry_path: str) -> Path:
    registry = Path(registry_path).expanduser().resolve()
    return registry.parent / "ui_runs"


def _run_dir(registry_path: str, run_id: str) -> Path:
    return _run_state_dir(registry_path) / str(run_id).strip()


def _manifest_path(registry_path: str, run_id: str) -> Path:
    return _run_dir(registry_path, run_id) / REPLAY_MANIFEST_FILE_NAME


def _report_path(registry_path: str, report: UiRunReplayReport) -> Path:
    timestamp_token = (
        report.replayed_at_utc.replace(":", "").replace("-", "").replace("+", "_")
    )
    return (
        _run_dir(registry_path, report.run_id)
        / REPLAY_REPORT_DIR_NAME
        / f"replay_report_{timestamp_token}.json"
    )


def _json_file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(65536)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def _normalize_artifact_paths(paths: list[str]) -> list[Path]:
    normalized: list[Path] = []
    seen: set[str] = set()
    for raw_path in paths:
        token = str(raw_path or "").strip()
        if not token:
            continue
        resolved = Path(token).expanduser().resolve()
        key = str(resolved)
        if key in seen:
            continue
        seen.add(key)
        normalized.append(resolved)
    return normalized


def _fingerprint_artifact(path: Path) -> UiRunArtifactFingerprint:
    if not path.exists() or not path.is_file():
        return UiRunArtifactFingerprint(
            schema_version="1.0",
            path=str(path),
            exists=False,
            size_bytes=0,
            sha256="",
        )
    return UiRunArtifactFingerprint(
        schema_version="1.0",
        path=str(path),
        exists=True,
        size_bytes=int(path.stat().st_size),
        sha256=_json_file_sha256(path),
    )


def _iter_tree_files(root: Path) -> list[Path]:
    if not root.exists() or not root.is_dir():
        raise AppError(
            code="ui_run_replay_root_missing",
            message=f"Replay fingerprint root not found: {root}",
            retryable=False,
            context={"root": str(root)},
        )
    files: list[Path] = []
    is_prompt_tree = "prompts" in {part.lower() for part in root.parts}
    for candidate in root.rglob("*"):
        if not candidate.is_file():
            continue
        if not is_prompt_tree and candidate.suffix.lower() != ".py":
            continue
        files.append(candidate)
    files.sort(key=lambda item: str(item.relative_to(root)).replace("\\", "/"))
    return files


def _fingerprint_tree(root: Path) -> str:
    payload: list[dict[str, Any]] = []
    for file_path in _iter_tree_files(root):
        payload.append(
            {
                "path": str(file_path.relative_to(root)).replace("\\", "/"),
                "sha256": _json_file_sha256(file_path),
                "size_bytes": int(file_path.stat().st_size),
            }
        )
    return hashlib.sha256(stable_json_dumps({"files": payload}).encode("utf-8")).hexdigest()


def _artifact_fingerprint_dicts(
    fingerprints: list[UiRunArtifactFingerprint],
) -> list[dict[str, Any]]:
    return [asdict(item) for item in fingerprints]


def _manifest_from_payload(payload: dict[str, Any]) -> UiRunReplayManifest:
    artifact_fingerprints = [
        UiRunArtifactFingerprint(**dict(item))
        for item in list(payload.get("artifact_fingerprints") or [])
    ]
    return UiRunReplayManifest(
        schema_version=str(payload.get("schema_version") or "1.0"),
        run_id=str(payload.get("run_id") or "").strip(),
        run_type=str(payload.get("run_type") or "").strip(),
        recorded_at_utc=str(payload.get("recorded_at_utc") or "").strip(),
        status=str(payload.get("status") or "").strip(),
        request_payload=dict(payload.get("request_payload") or {}),
        config_snapshot=dict(payload.get("config_snapshot") or {}),
        config_fingerprint=str(payload.get("config_fingerprint") or "").strip(),
        source_tree_root=str(payload.get("source_tree_root") or "").strip(),
        source_tree_fingerprint=str(
            payload.get("source_tree_fingerprint") or ""
        ).strip(),
        prompt_tree_root=str(payload.get("prompt_tree_root") or "").strip(),
        prompt_tree_fingerprint=str(
            payload.get("prompt_tree_fingerprint") or ""
        ).strip(),
        result_summary=dict(payload.get("result_summary") or {}),
        artifact_fingerprints=artifact_fingerprints,
        error_code=str(payload.get("error_code") or "").strip(),
        error_message=str(payload.get("error_message") or "").strip(),
    )


def _validate_manifest(manifest: UiRunReplayManifest) -> None:
    if not manifest.run_type:
        raise AppError(
            code="ui_run_replay_manifest_invalid",
            message="Replay manifest run_type is required",
            retryable=False,
            context={"run_id": manifest.run_id},
        )
    if not manifest.status:
        raise AppError(
            code="ui_run_replay_manifest_invalid",
            message="Replay manifest status is required",
            retryable=False,
            context={"run_id": manifest.run_id},
        )
    if not manifest.config_fingerprint:
        raise AppError(
            code="ui_run_replay_manifest_invalid",
            message="Replay manifest config fingerprint is required",
            retryable=False,
            context={"run_id": manifest.run_id},
        )
    if not manifest.source_tree_fingerprint or not manifest.prompt_tree_fingerprint:
        raise AppError(
            code="ui_run_replay_manifest_invalid",
            message="Replay manifest workspace fingerprints are required",
            retryable=False,
            context={"run_id": manifest.run_id},
        )


def write_ui_run_replay_manifest(
    request: UiRunReplayCaptureRequest, ctx: RunContext
) -> UiRunReplayCaptureResponse:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="ui_run_replay_manifest_write_start",
            module=logger.name,
            fields={
                "registry_path": request.registry_path,
                "run_id": request.run_id,
                "run_type": request.run_type,
                "status": request.status,
                "artifact_count": len(request.artifact_paths),
            },
        )
    )
    artifact_fingerprints = [
        _fingerprint_artifact(path)
        for path in _normalize_artifact_paths(request.artifact_paths)
    ]
    manifest = UiRunReplayManifest(
        schema_version="1.0",
        run_id=request.run_id,
        run_type=request.run_type,
        recorded_at_utc=request.recorded_at_utc,
        status=request.status,
        request_payload=request.request_payload,
        config_snapshot=request.config_snapshot,
        config_fingerprint=request.config_fingerprint,
        source_tree_root=str(Path(request.source_tree_root).expanduser().resolve()),
        source_tree_fingerprint=_fingerprint_tree(
            Path(request.source_tree_root).expanduser().resolve()
        ),
        prompt_tree_root=str(Path(request.prompt_tree_root).expanduser().resolve()),
        prompt_tree_fingerprint=_fingerprint_tree(
            Path(request.prompt_tree_root).expanduser().resolve()
        ),
        result_summary=request.result_summary,
        artifact_fingerprints=artifact_fingerprints,
        error_code=request.error_code,
        error_message=request.error_message,
    )
    _validate_manifest(manifest)
    manifest_path = _manifest_path(request.registry_path, request.run_id)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(asdict(manifest), ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="ui_run_replay_manifest_write_complete",
            module=logger.name,
            fields={
                "registry_path": request.registry_path,
                "run_id": request.run_id,
                "manifest_path": str(manifest_path),
                "artifact_fingerprints": _artifact_fingerprint_dicts(
                    artifact_fingerprints
                ),
                "config_fingerprint": manifest.config_fingerprint,
                "source_tree_fingerprint": manifest.source_tree_fingerprint,
                "prompt_tree_fingerprint": manifest.prompt_tree_fingerprint,
            },
        )
    )
    return UiRunReplayCaptureResponse(
        schema_version="1.0",
        manifest_path=str(manifest_path),
        manifest=manifest,
    )


def fingerprint_ui_run_artifacts(
    request: UiRunArtifactFingerprintRequest, ctx: RunContext
) -> UiRunArtifactFingerprintResponse:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="ui_run_replay_artifact_fingerprint_start",
            module=logger.name,
            fields={
                "run_id": request.run_id,
                "artifact_count": len(request.artifact_paths),
            },
        )
    )
    fingerprints = [
        _fingerprint_artifact(path)
        for path in _normalize_artifact_paths(request.artifact_paths)
    ]
    logger.info(
        log_event(
            ctx,
            role="service",
            event="ui_run_replay_artifact_fingerprint_complete",
            module=logger.name,
            fields={
                "run_id": request.run_id,
                "artifact_fingerprints": _artifact_fingerprint_dicts(fingerprints),
            },
        )
    )
    return UiRunArtifactFingerprintResponse(
        schema_version="1.0",
        artifact_fingerprints=fingerprints,
    )


def fingerprint_ui_run_workspace(
    request: UiRunWorkspaceFingerprintRequest, ctx: RunContext
) -> UiRunWorkspaceFingerprintResponse:
    source_root = Path(request.source_tree_root).expanduser().resolve()
    prompt_root = Path(request.prompt_tree_root).expanduser().resolve()
    logger.info(
        log_event(
            ctx,
            role="service",
            event="ui_run_replay_workspace_fingerprint_start",
            module=logger.name,
            fields={
                "run_id": request.run_id,
                "source_tree_root": str(source_root),
                "prompt_tree_root": str(prompt_root),
            },
        )
    )
    response = UiRunWorkspaceFingerprintResponse(
        schema_version="1.0",
        source_tree_root=str(source_root),
        source_tree_fingerprint=_fingerprint_tree(source_root),
        prompt_tree_root=str(prompt_root),
        prompt_tree_fingerprint=_fingerprint_tree(prompt_root),
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="ui_run_replay_workspace_fingerprint_complete",
            module=logger.name,
            fields={
                "run_id": request.run_id,
                "source_tree_root": response.source_tree_root,
                "source_tree_fingerprint": response.source_tree_fingerprint,
                "prompt_tree_root": response.prompt_tree_root,
                "prompt_tree_fingerprint": response.prompt_tree_fingerprint,
            },
        )
    )
    return response


def read_ui_run_replay_manifest(
    request: UiRunReplayReadRequest, ctx: RunContext
) -> UiRunReplayReadResponse:
    manifest_path = _manifest_path(request.registry_path, request.run_id)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="ui_run_replay_manifest_read_start",
            module=logger.name,
            fields={
                "registry_path": request.registry_path,
                "run_id": request.run_id,
                "manifest_path": str(manifest_path),
            },
        )
    )
    if not manifest_path.exists():
        raise AppError(
            code="ui_run_replay_manifest_missing",
            message=f"Replay manifest not found for run: {request.run_id}",
            retryable=False,
            context={
                "registry_path": request.registry_path,
                "run_id": request.run_id,
                "manifest_path": str(manifest_path),
            },
        )
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AppError(
            code="ui_run_replay_manifest_invalid",
            message=f"Replay manifest JSON invalid: {manifest_path}",
            cause=exc,
            retryable=False,
            context={"manifest_path": str(manifest_path)},
        ) from exc
    if not isinstance(payload, dict):
        raise AppError(
            code="ui_run_replay_manifest_invalid",
            message=f"Replay manifest root must be an object: {manifest_path}",
            retryable=False,
            context={"manifest_path": str(manifest_path)},
        )
    manifest = _manifest_from_payload(payload)
    _validate_manifest(manifest)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="ui_run_replay_manifest_read_complete",
            module=logger.name,
            fields={
                "registry_path": request.registry_path,
                "run_id": request.run_id,
                "manifest_path": str(manifest_path),
                "artifact_count": len(manifest.artifact_fingerprints),
            },
        )
    )
    return UiRunReplayReadResponse(
        schema_version="1.0",
        manifest_path=str(manifest_path),
        manifest=manifest,
    )


def write_ui_run_replay_report(
    request: UiRunReplayReportWriteRequest, ctx: RunContext
) -> UiRunReplayReportWriteResponse:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="ui_run_replay_report_write_start",
            module=logger.name,
            fields={
                "registry_path": request.registry_path,
                "run_id": request.run_id,
                "replay_status": request.report.replay_status,
                "matched": request.report.matched,
            },
        )
    )
    report_path = _report_path(request.registry_path, request.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(asdict(request.report), ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="ui_run_replay_report_write_complete",
            module=logger.name,
            fields={
                "registry_path": request.registry_path,
                "run_id": request.run_id,
                "report_path": str(report_path),
                "delta_count": len(request.report.deltas),
                "matched": request.report.matched,
            },
        )
    )
    return UiRunReplayReportWriteResponse(
        schema_version="1.0",
        report_path=str(report_path),
        report=request.report,
    )
