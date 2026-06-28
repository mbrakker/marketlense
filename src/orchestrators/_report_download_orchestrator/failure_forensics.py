from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from src.contracts.browser_download import (
    DownloadTerminalEvidence,
    FailedAcquisitionForensicsArtifact,
    FailedAcquisitionForensicsPack,
    ReportDownloadOrchestratorRequest,
    ReportDownloadRoutePlanStep,
)
from src.contracts.files import FileStatRequest, ReadBytesRequest, WriteBytesRequest
from src.contracts.run_context import RunContext
from src.orchestrators._report_download_orchestrator.dependencies import (
    ReportDownloadDependencies,
)
from src.services._browser_report_download.request import resolve_download_dir_path
from src.utils.errors import AppError
from src.utils.url_utils import normalize_url

_MAX_FORENSICS_CONTEXT_CHARS = 500


def failure_error_class(exc: Exception) -> str:
    if not isinstance(exc, AppError):
        return "unexpected_exception"
    if exc.retryable:
        return "transient_app_error"
    return "permanent_app_error"


def _forensics_safe_token(value: str) -> str:
    cleaned = "".join(
        character if character.isalnum() else "_"
        for character in str(value or "").strip().lower()
    ).strip("_")
    return cleaned or "unknown"


def _bounded_forensics_token(value: str, *, max_chars: int) -> str:
    token = _forensics_safe_token(value)
    return token[:max_chars].rstrip("_") or token


def _truncated_context_value(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _truncated_context_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_truncated_context_value(item) for item in value[:25]]
    if isinstance(value, str):
        return (
            value
            if len(value) <= _MAX_FORENSICS_CONTEXT_CHARS
            else value[: _MAX_FORENSICS_CONTEXT_CHARS - 3] + "..."
        )
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)


def _coerce_network_events(
    value: object,
):
    from src.contracts.browser_download import BrowserDownloadNetworkEvent

    events: list[BrowserDownloadNetworkEvent] = []
    if not isinstance(value, list):
        return events
    for item in value:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if not url:
            continue
        events.append(
            BrowserDownloadNetworkEvent(
                schema_version=str(item.get("schema_version") or "1.0"),
                url=url,
                initiator_type=str(item.get("initiator_type") or "other"),
                signal_kind=str(item.get("signal_kind") or "other"),
            )
        )
    return events


def terminal_evidence_from_error_context(
    *,
    exc: Exception,
    request: ReportDownloadOrchestratorRequest,
    planned_step: ReportDownloadRoutePlanStep,
) -> DownloadTerminalEvidence | None:
    if not isinstance(exc, AppError):
        return None
    context = dict(exc.context or {})
    final_page_url = str(
        context.get("final_page_url")
        or context.get("final_url")
        or planned_step.attempt_url
        or request.url
    ).strip()
    if not final_page_url and not context:
        return None
    blocked_reason = str(context.get("blocked_reason") or "").strip()
    blocked_reason_detail = str(context.get("blocked_reason_detail") or "").strip()
    terminal_text_excerpt = str(context.get("terminal_text_excerpt") or "").strip()
    artifact_validation_status = "blocked" if blocked_reason else "none"
    artifact_validation_detail = (
        blocked_reason_detail or terminal_text_excerpt or exc.code
    )
    traversed_page_urls: list[str] = []
    for raw_value in (
        planned_step.attempt_url,
        context.get("execution_url"),
        final_page_url,
    ):
        token = str(raw_value or "").strip()
        if token and token not in traversed_page_urls:
            traversed_page_urls.append(token)
    return DownloadTerminalEvidence(
        schema_version="1.0",
        final_page_url=final_page_url,
        final_page_title=str(context.get("final_page_title") or "").strip(),
        terminal_text_excerpt=terminal_text_excerpt,
        artifact_url=str(context.get("resolved_target_url") or final_page_url).strip(),
        artifact_kind=str(context.get("route_kind") or "none").strip() or "none",
        artifact_validation_status=artifact_validation_status,
        artifact_validation_detail=artifact_validation_detail,
        confirmation_signal_count=0,
        traversed_page_urls=traversed_page_urls,
        visited_url_timeline=list(traversed_page_urls),
        observed_document_urls=[],
        network_events=_coerce_network_events(context.get("network_events")),
        html_snapshot_path=str(context.get("html_snapshot_path") or "").strip(),
        screenshot_path=str(context.get("screenshot_path") or "").strip(),
        dom_snapshot_sha256=str(context.get("dom_snapshot_sha256") or "").strip(),
        evidence_labels=[
            planned_step.route_family,
            exc.code,
            blocked_reason or artifact_validation_status,
        ],
    )


def _failure_artifact_candidates(
    *,
    exc: Exception,
    terminal_evidence: DownloadTerminalEvidence | None,
) -> list[tuple[str, str]]:
    context = dict(exc.context or {}) if isinstance(exc, AppError) else {}
    candidates: list[tuple[str, str]] = []

    def add(label: str, raw_path: object) -> None:
        token = str(raw_path or "").strip()
        if not token:
            return
        marker = (label, str(Path(token)))
        if marker in seen:
            return
        seen.add(marker)
        candidates.append((label, token))

    seen: set[tuple[str, str]] = set()
    if terminal_evidence is not None:
        add("terminal_html_snapshot", terminal_evidence.html_snapshot_path)
        add("terminal_screenshot", terminal_evidence.screenshot_path)
    add("downloaded_artifact", context.get("downloaded_file_path"))
    add("onsite_capture", context.get("onsite_capture_path"))
    claimed_paths = context.get("claimed_artifact_paths")
    if isinstance(claimed_paths, list):
        for index, claimed_path in enumerate(claimed_paths):
            add(f"claimed_artifact_{index + 1}", claimed_path)
    return candidates


def _persist_forensics_artifact(
    *,
    artifact_label: str,
    source_path: str,
    forensics_dir: Path,
    artifact_policy: str,
    ctx: RunContext,
    dependencies: ReportDownloadDependencies,
) -> FailedAcquisitionForensicsArtifact:
    source = Path(source_path)
    stat_response = dependencies.file_stat(
        FileStatRequest(schema_version="1.0", path=source_path),
        ctx,
    )
    if not stat_response.exists or not stat_response.is_file:
        return FailedAcquisitionForensicsArtifact(
            schema_version="1.0",
            artifact_label=artifact_label,
            source_path=source_path,
            persisted_path=None,
            retention_action="missing",
            size_bytes=None,
            md5=None,
        )
    if artifact_policy == "metadata_only":
        return FailedAcquisitionForensicsArtifact(
            schema_version="1.0",
            artifact_label=artifact_label,
            source_path=source_path,
            persisted_path=None,
            retention_action="metadata_only",
            size_bytes=None,
            md5=None,
        )
    read_response = dependencies.read_bytes(
        ReadBytesRequest(schema_version="1.0", path=source_path),
        ctx,
    )
    target_name = f"{_forensics_safe_token(artifact_label)}__{source.name}"
    target_path = forensics_dir / target_name
    write_response = dependencies.write_bytes(
        WriteBytesRequest(
            schema_version="1.0",
            path=str(target_path),
            content=read_response.content,
            make_parents=True,
        ),
        ctx,
    )
    return FailedAcquisitionForensicsArtifact(
        schema_version="1.0",
        artifact_label=artifact_label,
        source_path=source_path,
        persisted_path=write_response.path,
        retention_action="copied",
        size_bytes=write_response.bytes_written,
        md5=write_response.md5,
    )


def with_failure_forensics_context(
    exc: AppError,
    *,
    pack: FailedAcquisitionForensicsPack | None,
    terminal_evidence: DownloadTerminalEvidence | None,
) -> AppError:
    context = dict(exc.context or {})
    context["failure_error_class"] = failure_error_class(exc)
    if terminal_evidence is not None:
        context["terminal_evidence"] = asdict(terminal_evidence)
        context["terminal_html_snapshot_path"] = terminal_evidence.html_snapshot_path
        context["terminal_screenshot_path"] = terminal_evidence.screenshot_path
    if pack is not None:
        context["failure_forensics_pack_path"] = pack.pack_path
        context["failure_forensics_artifact_policy"] = pack.artifact_policy
        context["failure_forensics_artifacts"] = [
            asdict(item) for item in pack.artifacts
        ]
    return AppError(
        code=exc.code,
        message=exc.message,
        cause=exc.cause,
        retryable=exc.retryable,
        severity=exc.severity,
        context=context,
    )


def persist_failed_attempt_forensics_pack(
    *,
    request: ReportDownloadOrchestratorRequest,
    planned_step: ReportDownloadRoutePlanStep,
    exc: AppError,
    ctx: RunContext,
    dependencies: ReportDownloadDependencies,
) -> FailedAcquisitionForensicsPack | None:
    if not request.settings.failure_forensics_enabled:
        return None
    normalized_url = normalize_url(request.url)
    download_dir = resolve_download_dir_path(
        root_dir=request.settings.output_dir,
        normalized_url=normalized_url,
    )
    forensics_dir = download_dir.parent / f"{download_dir.name}__failure_forensics"
    artifact_policy = str(request.settings.failure_forensics_policy or "copy_artifacts")
    terminal_evidence = terminal_evidence_from_error_context(
        exc=exc,
        request=request,
        planned_step=planned_step,
    )
    artifacts = [
        _persist_forensics_artifact(
            artifact_label=artifact_label,
            source_path=source_path,
            forensics_dir=forensics_dir,
            artifact_policy=artifact_policy,
            ctx=ctx,
            dependencies=dependencies,
        )
        for artifact_label, source_path in _failure_artifact_candidates(
            exc=exc,
            terminal_evidence=terminal_evidence,
        )
    ]
    pack_name = (
        f"failed_attempt__{_bounded_forensics_token(planned_step.step_name, max_chars=18)}__"
        f"{_bounded_forensics_token(exc.code, max_chars=28)}.json"
    )
    pack_path = str(forensics_dir / pack_name)
    pack = FailedAcquisitionForensicsPack(
        schema_version="1.0",
        pack_path=pack_path,
        artifact_policy=artifact_policy,
        normalized_url=normalized_url,
        source_url=request.url,
        attempt_url=str(planned_step.attempt_url or request.url).strip(),
        step_name=planned_step.step_name,
        route_family=planned_step.route_family,
        route_kind_hint=planned_step.route_kind_hint,
        route_hint=planned_step.route_hint,
        route_step_hints=list(planned_step.route_step_hints),
        error_code=exc.code,
        error_message=exc.message,
        error_class=failure_error_class(exc),
        error_retryable=exc.retryable,
        error_severity=exc.severity,
        blocked_reason=str((exc.context or {}).get("blocked_reason") or "").strip()
        or None,
        blocked_reason_detail=str(
            (exc.context or {}).get("blocked_reason_detail") or ""
        ).strip()
        or None,
        terminal_evidence=terminal_evidence,
        artifacts=artifacts,
        failure_context={
            str(key): _truncated_context_value(value)
            for key, value in dict(exc.context or {}).items()
        },
    )
    dependencies.write_bytes(
        WriteBytesRequest(
            schema_version="1.0",
            path=pack_path,
            content=json.dumps(asdict(pack), indent=2, sort_keys=True).encode("utf-8"),
            make_parents=True,
        ),
        ctx,
    )
    return pack
