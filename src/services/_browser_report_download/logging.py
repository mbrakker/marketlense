"""Bounded browser-acquisition log field summaries."""

from __future__ import annotations

import hashlib
from collections import Counter
from typing import Any
from urllib.parse import urlsplit

from src.contracts.browser_download import (
    BrowserDownloadSessionReuseDecision,
    BrowserDownloadWarmWorkerPoolDecision,
    BrowserDeveloperDiagnosticsRequest,
    BrowserDeveloperDiagnosticsResult,
    BrowserPreflightProbeResult,
    BrowserReportDownloadResult,
    PreBrowserDocTypePrediction,
)


def _url_hash(url: str) -> str:
    return hashlib.sha256(str(url or "").encode("utf-8")).hexdigest()


def _url_host(url: str) -> str:
    return str(urlsplit(str(url or "")).hostname or "").casefold()


def browser_download_result_log_fields(
    result: BrowserReportDownloadResult,
    *,
    artifact_sha256: str = "",
    artifact_size_bytes: int | None = None,
) -> dict[str, Any]:
    """Emit route outcomes and retained audit references, never browser text."""

    terminal = result.terminal_evidence
    artifact_path = result.downloaded_file_path or result.onsite_capture_path or ""
    return {
        "schema_version": result.schema_version,
        "outcome": result.outcome,
        "route_kind": result.route_kind,
        "route_family": result.route_family,
        "route_status": result.route_status,
        "normalized_url_sha256": _url_hash(result.normalized_url),
        "final_host": _url_host(result.final_page_url or terminal.final_page_url),
        "artifact_url_sha256": _url_hash(
            terminal.artifact_url or result.resolved_target_url
        ),
        "artifact_kind": terminal.artifact_kind,
        "artifact_validation_status": terminal.artifact_validation_status,
        "artifact_identity": result.downloaded_file_name
        or str(artifact_path).rsplit("/", 1)[-1].rsplit("\\", 1)[-1],
        "artifact_sha256": artifact_sha256,
        "artifact_size_bytes": artifact_size_bytes
        if artifact_size_bytes is not None
        else result.downloaded_size_bytes,
        "route_step_count": len(result.route_steps),
        "confirmation_score": result.confirmation_evidence.confirmation_score,
        "blocker_code": result.blocked_reason or "",
        "html_snapshot_audit_ref": terminal.html_snapshot_path,
        "screenshot_audit_ref": terminal.screenshot_path,
        "dom_snapshot_sha256": terminal.dom_snapshot_sha256,
    }


def pre_browser_doc_type_prediction_log_fields(
    prediction: PreBrowserDocTypePrediction,
) -> dict[str, Any]:
    return {
        "schema_version": prediction.schema_version,
        "predicted_doc_type": prediction.predicted_doc_type,
        "predicted_route_family": prediction.predicted_route_family,
        "probe_host": _url_host(prediction.probe_url),
        "probe_url_sha256": _url_hash(prediction.probe_url),
        "confidence_score": prediction.confidence_score,
        "requires_browser": prediction.requires_browser,
        "evidence_label_count": len(prediction.evidence_labels),
    }


def browser_preflight_probe_log_fields(
    *,
    normalized_url: str,
    probe: BrowserPreflightProbeResult,
) -> dict[str, Any]:
    return {
        "schema_version": probe.schema_version,
        "normalized_url_sha256": _url_hash(normalized_url),
        "status": probe.status,
        "final_host": _url_host(probe.final_url),
        "selected_pdf_url_sha256": _url_hash(probe.selected_pdf_url),
        "html_size": probe.html_size,
        "preflight_duration_seconds": probe.duration_seconds,
        "candidate_pdf_url_count": len(probe.candidate_pdf_urls),
        "observed_event_url_count": len(probe.observed_event_urls),
        "network_event_count": probe.network_event_count,
        "evidence_label_count": len(probe.evidence_labels),
        "escalation_reason": probe.escalation_reason,
        "avoided_agent_call": probe.avoided_agent_call,
        "false_negative_rate_sample": probe.false_negative_rate_sample,
        "reuse_state_present": probe.reuse_state is not None,
    }


def browser_session_reuse_log_fields(
    *,
    normalized_url: str,
    decision: BrowserDownloadSessionReuseDecision,
) -> dict[str, Any]:
    return {
        "schema_version": decision.schema_version,
        "normalized_url_sha256": _url_hash(normalized_url),
        "enabled": decision.enabled,
        "accepted": decision.accepted,
        "mode": decision.mode,
        "session_key_hash": decision.session_key_hash,
        "publisher_scope": decision.publisher_scope,
        "profile_reused": decision.profile_reused,
        "ttl_seconds": decision.ttl_seconds,
        "cleanup_removed_count": decision.cleanup_removed_count,
        "rejection_reason": decision.rejection_reason,
    }


def browser_warm_worker_pool_log_fields(
    *,
    normalized_url: str,
    decision: BrowserDownloadWarmWorkerPoolDecision,
) -> dict[str, Any]:
    return {
        "schema_version": decision.schema_version,
        "normalized_url_sha256": _url_hash(normalized_url),
        "enabled": decision.enabled,
        "accepted": decision.accepted,
        "publisher_scope": decision.publisher_scope,
        "pool_key_hash": decision.pool_key_hash,
        "max_runs_per_worker": decision.max_runs_per_worker,
        "max_memory_mb": decision.max_memory_mb,
        "rejection_reason": decision.rejection_reason,
    }


def browser_developer_diagnostics_request_log_fields(
    request: BrowserDeveloperDiagnosticsRequest,
) -> dict[str, Any]:
    return {
        "schema_version": request.schema_version,
        "headed": request.headed,
        "verification_host": _url_host(request.verification_url),
        "verification_url_sha256": _url_hash(request.verification_url),
        "cdp_url_configured": bool(request.cdp_url),
        "activate_verification_tab": request.activate_verification_tab,
        "cleanup_stale_once": request.cleanup_stale_once,
        "keep_browser_open": request.keep_browser_open,
        "timeout_seconds": request.timeout_seconds,
        "session_reuse_enabled": request.session_reuse_policy.enabled,
    }


def browser_developer_diagnostics_result_log_fields(
    result: BrowserDeveloperDiagnosticsResult,
) -> dict[str, Any]:
    check_status_counts = Counter(check.status for check in result.checks)
    return {
        "schema_version": result.schema_version,
        "status": result.status,
        "cdp_url_configured": bool(result.cdp_url),
        "active_tab_host": _url_host(result.active_tab_url),
        "active_tab_url_sha256": _url_hash(result.active_tab_url),
        "browser_use_connected": result.browser_use_connected,
        "cdp_available": result.cdp_available,
        "real_tab_available": result.real_tab_available,
        "cleanup_attempted": result.cleanup_attempted,
        "cleanup_status": result.cleanup_status,
        "verification_tab_activated": result.verification_tab_activated,
        "keep_browser_open": result.keep_browser_open,
        "check_count": len(result.checks),
        "check_status_counts": dict(sorted(check_status_counts.items())),
        "error_present": bool(result.error),
    }
