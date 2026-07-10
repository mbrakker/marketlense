from __future__ import annotations

import json
import os
import re
import sys
import traceback
from dataclasses import asdict
from pathlib import Path
from typing import Any

from src.contracts.browser_download import (
    BrowserDownloadCaptchaHandoffPolicy,
    BrowserDownloadIdentity,
    BrowserDownloadIdentityField,
    BrowserDownloadPublisherOverride,
    BrowserDownloadRouteBudget,
    BrowserDownloadRouteStep,
    BrowserDownloadSessionReusePolicy,
    BrowserDownloadSettings,
    BrowserDownloadWarmWorkerPoolPolicy,
    BrowserReportDownloadRequest,
    BrowserRoutePlaybookSelection,
)
from src.contracts.logging import LoggingSetupRequest
from src.contracts.publisher_inventory import PublisherInventoryCandidateTrace
from src.contracts.run_context import RunContext
from src.contracts.semantic_ids import RunId, TaskId
from src.services._browser_report_download.browser import (
    BrowserAgentWorkerResponse,
    run_browser_report_download_agent,
)
from src.services._browser_report_download.prompt import (
    BrowserDownloadPromptBundle,
    redact_browser_report_download_prompt_for_log,
)
from src.services.logging_service import setup_logging
from src.utils.errors import AppError
from src.utils.logging import REDACTED

_EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)


def _build_identity_field(payload: dict) -> BrowserDownloadIdentityField:
    return BrowserDownloadIdentityField(
        schema_version=str(payload.get("schema_version", "1.0")),
        key=str(payload.get("key") or "").strip(),
        label=str(payload.get("label") or "").strip(),
        value=payload.get("value"),
        aliases=[
            str(item) for item in payload.get("aliases", []) if str(item or "").strip()
        ],
        option_aliases=[
            str(item)
            for item in payload.get("option_aliases", [])
            if str(item or "").strip()
        ],
    )


def _build_identity(payload: dict) -> BrowserDownloadIdentity:
    overrides_payload = payload.get("publisher_overrides", [])
    overrides: list[BrowserDownloadPublisherOverride] = []
    if isinstance(overrides_payload, list):
        for item in overrides_payload:
            if not isinstance(item, dict):
                continue
            overrides.append(
                BrowserDownloadPublisherOverride(
                    schema_version=str(item.get("schema_version", "1.0")),
                    host_pattern=str(item.get("host_pattern") or "").strip(),
                    delivery_emails=[
                        str(email)
                        for email in item.get("delivery_emails", [])
                        if str(email or "").strip()
                    ],
                    field_values=[
                        _build_identity_field(field_payload)
                        for field_payload in item.get("field_values", [])
                        if isinstance(field_payload, dict)
                    ],
                )
            )
    return BrowserDownloadIdentity(
        schema_version=str(payload.get("schema_version", "1.0")),
        fields=[
            _build_identity_field(item)
            for item in payload.get("fields", [])
            if isinstance(item, dict)
        ],
        delivery_emails=[
            str(item)
            for item in payload.get("delivery_emails", [])
            if str(item or "").strip()
        ],
        publisher_overrides=overrides,
    )


def _build_settings(payload: dict) -> BrowserDownloadSettings:
    identity_payload = payload.get("identity_profile")
    session_reuse_payload = payload.get("session_reuse_policy")
    warm_worker_pool_payload = payload.get("warm_worker_pool_policy")
    captcha_handoff_payload = payload.get("captcha_handoff_policy")
    route_budgets_payload = payload.get("route_budgets")
    session_reuse_policy = _build_session_reuse_policy(
        session_reuse_payload if isinstance(session_reuse_payload, dict) else {}
    )
    return BrowserDownloadSettings(
        schema_version=str(payload.get("schema_version", "1.0")),
        openrouter_api_key=str(payload.get("openrouter_api_key") or ""),
        model=str(payload.get("model") or ""),
        temperature=float(payload.get("temperature", 0.0)),
        timeout_seconds=float(payload.get("timeout_seconds", 1.0)),
        max_steps=int(payload.get("max_steps", 1)),
        max_tokens=int(payload.get("max_tokens", 12000)),
        output_dir=str(payload.get("output_dir") or ""),
        state_db=str(payload.get("state_db") or ""),
        reports_db=str(payload.get("reports_db") or ""),
        identity_config_path=str(payload.get("identity_config_path") or ""),
        identity_profile=_build_identity(
            identity_payload if isinstance(identity_payload, dict) else {}
        ),
        openrouter_http_referer=payload.get("openrouter_http_referer"),
        headed=bool(payload.get("headed", False)),
        retry_retries=int(payload.get("retry_retries", 0)),
        retry_base_delay_seconds=float(payload.get("retry_base_delay_seconds", 1.0)),
        retry_backoff_step_seconds=float(
            payload.get("retry_backoff_step_seconds", 1.0)
        ),
        retry_jitter_seconds=float(payload.get("retry_jitter_seconds", 0.0)),
        route_playbook_dir=str(
            payload.get("route_playbook_dir") or "./src/playbooks/browser_routes"
        ),
        route_playbook_stale_policy=str(
            payload.get("route_playbook_stale_policy") or "fallback"
        ),
        route_playbook_promotion_mode=str(
            payload.get("route_playbook_promotion_mode") or "disabled"
        ),
        private_api_playbook_promotion_mode=str(
            payload.get("private_api_playbook_promotion_mode") or "disabled"
        ),
        private_api_playbook_min_success_count=int(
            payload.get("private_api_playbook_min_success_count") or 3
        ),
        private_api_playbook_min_distinct_source_urls=int(
            payload.get("private_api_playbook_min_distinct_source_urls") or 2
        ),
        session_reuse_policy=session_reuse_policy,
        warm_worker_pool_policy=_build_warm_worker_pool_policy(
            warm_worker_pool_payload
            if isinstance(warm_worker_pool_payload, dict)
            else {}
        ),
        captcha_handoff_policy=_build_captcha_handoff_policy(
            captcha_handoff_payload if isinstance(captcha_handoff_payload, dict) else {}
        ),
        route_budgets=[
            _build_route_budget(item)
            for item in route_budgets_payload
            if isinstance(item, dict)
        ]
        if isinstance(route_budgets_payload, list)
        else [],
    )


def _build_route_budget(payload: dict) -> BrowserDownloadRouteBudget:
    max_steps = payload.get("max_steps")
    timeout_seconds = payload.get("timeout_seconds")
    return BrowserDownloadRouteBudget(
        schema_version=str(payload.get("schema_version", "1.0")),
        route_family=str(payload.get("route_family") or "").strip(),
        max_steps=int(max_steps) if max_steps is not None else None,
        timeout_seconds=(
            float(timeout_seconds) if timeout_seconds is not None else None
        ),
    )


def _build_captcha_handoff_policy(payload: dict) -> BrowserDownloadCaptchaHandoffPolicy:
    return BrowserDownloadCaptchaHandoffPolicy(
        schema_version=str(payload.get("schema_version", "1.0")),
        enabled=bool(payload.get("enabled", False)),
        timeout_seconds=max(float(payload.get("timeout_seconds", 120.0)), 1.0),
    )


def _build_session_reuse_policy(payload: dict) -> BrowserDownloadSessionReusePolicy:
    return BrowserDownloadSessionReusePolicy(
        schema_version=str(payload.get("schema_version", "1.0")),
        enabled=bool(payload.get("enabled", False)),
        mode=str(payload.get("mode") or "disabled"),
        session_key=str(payload.get("session_key") or "").strip(),
        publisher_scope=str(payload.get("publisher_scope") or "").strip(),
        ttl_seconds=float(payload.get("ttl_seconds", 0.0)),
        base_dir=str(payload.get("base_dir") or "").strip(),
        cleanup_expired=bool(payload.get("cleanup_expired", True)),
        allow_cross_publisher=bool(payload.get("allow_cross_publisher", False)),
    )


def _build_warm_worker_pool_policy(
    payload: dict,
) -> BrowserDownloadWarmWorkerPoolPolicy:
    return BrowserDownloadWarmWorkerPoolPolicy(
        schema_version=str(payload.get("schema_version", "1.0")),
        enabled=bool(payload.get("enabled", False)),
        max_workers=max(int(payload.get("max_workers", 1) or 1), 1),
        max_runs_per_worker=max(int(payload.get("max_runs_per_worker", 3) or 3), 1),
        max_memory_mb=max(int(payload.get("max_memory_mb", 768) or 768), 128),
        idle_ttl_seconds=max(
            float(payload.get("idle_ttl_seconds", 300.0) or 300.0), 1.0
        ),
        fallback_to_subprocess=bool(payload.get("fallback_to_subprocess", True)),
    )


def _build_candidate_trace(payload: dict) -> PublisherInventoryCandidateTrace | None:
    if not isinstance(payload, dict):
        return None
    canonical_url = str(payload.get("canonical_url") or "").strip()
    title = str(payload.get("title") or "").strip()
    if not canonical_url or not title:
        return None
    return PublisherInventoryCandidateTrace(
        schema_version=str(payload.get("schema_version", "1.0")),
        canonical_url=canonical_url,
        title=title,
        discovered_on_page_number=int(payload.get("discovered_on_page_number", 0)),
        source_page_urls=[
            str(item)
            for item in payload.get("source_page_urls", [])
            if str(item or "").strip()
        ],
        discovery_provenances=[
            str(item)
            for item in payload.get("discovery_provenances", [])
            if str(item or "").strip()
        ],
        pdf_url=payload.get("pdf_url"),
        published_at_text=payload.get("published_at_text"),
        max_confidence=(
            float(raw_max_confidence)
            if (raw_max_confidence := payload.get("max_confidence")) is not None
            else None
        ),
    )


def _build_request(payload: dict) -> BrowserReportDownloadRequest:
    route_step_hints_payload = payload.get("route_step_hints", [])
    selected_playbooks_payload = payload.get("selected_playbooks", [])
    settings_payload = payload.get("settings")
    candidate_trace_payload = payload.get("candidate_trace")
    return BrowserReportDownloadRequest(
        schema_version=str(payload.get("schema_version", "1.0")),
        url=str(payload.get("url") or "").strip(),
        settings=_build_settings(
            settings_payload if isinstance(settings_payload, dict) else {}
        ),
        delivery_email=payload.get("delivery_email"),
        route_hint=payload.get("route_hint"),
        route_step_hints=[
            BrowserDownloadRouteStep(
                schema_version=str(item.get("schema_version", "1.0")),
                index=int(item.get("index", 0)),
                action=str(item.get("action") or "").strip(),
                target_text=str(item.get("target_text") or "").strip(),
                target_role=str(item.get("target_role") or "").strip(),
                target_url=str(item.get("target_url") or "").strip(),
                result=str(item.get("result") or "").strip(),
                expected_evidence=[
                    str(value).strip()
                    for value in item.get("expected_evidence", [])
                    if str(value or "").strip()
                ]
                if isinstance(item.get("expected_evidence"), list)
                else [],
                observed_evidence=[
                    str(value).strip()
                    for value in item.get("observed_evidence", [])
                    if str(value or "").strip()
                ]
                if isinstance(item.get("observed_evidence"), list)
                else [],
                verification_status=str(item.get("verification_status") or "").strip(),
            )
            for item in route_step_hints_payload
            if isinstance(item, dict)
        ],
        route_kind_hint=payload.get("route_kind_hint"),
        candidate_trace=_build_candidate_trace(
            candidate_trace_payload if isinstance(candidate_trace_payload, dict) else {}
        ),
        publisher_discovery_route_kind=payload.get("publisher_discovery_route_kind"),
        publisher_recommended_discovery_route_kind=payload.get(
            "publisher_recommended_discovery_route_kind"
        ),
        attempt_url=payload.get("attempt_url"),
        route_family_hint=payload.get("route_family_hint"),
        source_page_url_hint=payload.get("source_page_url_hint"),
        selected_playbooks=[
            BrowserRoutePlaybookSelection(
                schema_version=str(item.get("schema_version", "1.0")),
                playbook_id=str(item.get("playbook_id") or "").strip(),
                version=str(item.get("version") or "").strip(),
                route_family=str(item.get("route_family") or "").strip(),
                route_kind=str(item.get("route_kind") or "").strip(),
                match_reason=str(item.get("match_reason") or "").strip(),
                summary=str(item.get("summary") or "").strip(),
                step_lines=[
                    str(line)
                    for line in item.get("step_lines", [])
                    if str(line or "").strip()
                ],
                trap_lines=[
                    str(line)
                    for line in item.get("trap_lines", [])
                    if str(line or "").strip()
                ],
            )
            for item in selected_playbooks_payload
            if isinstance(item, dict)
        ],
    )


def _build_prompt_bundle(payload: dict) -> BrowserDownloadPromptBundle:
    return BrowserDownloadPromptBundle(
        schema_version=str(payload.get("schema_version", "1.0")),
        namespace=str(payload.get("namespace") or "").strip(),
        system_prompt_path=str(payload.get("system_prompt_path") or "").strip(),
        user_prompt_path=str(payload.get("user_prompt_path") or "").strip(),
        system_prompt_sha256=str(payload.get("system_prompt_sha256") or "").strip(),
        user_prompt_sha256=str(payload.get("user_prompt_sha256") or "").strip(),
        rendered_system_prompt=str(payload.get("rendered_system_prompt") or ""),
        rendered_user_prompt=str(payload.get("rendered_user_prompt") or ""),
        task_prompt=str(payload.get("task_prompt") or ""),
    )


def _build_ctx(payload: dict) -> RunContext:
    return RunContext(
        schema_version=str(payload.get("schema_version", "1.0")),
        run_id=RunId(str(payload.get("run_id") or "")),
        task_id=TaskId(str(payload.get("task_id") or "")),
        span_id=str(payload.get("span_id") or ""),
    )


def _redact_worker_response_for_disk(
    payload: Any,
    request: BrowserReportDownloadRequest,
) -> Any:
    if isinstance(payload, str):
        redacted = redact_browser_report_download_prompt_for_log(
            request=request,
            text=payload,
            delivery_email=request.delivery_email,
        )
        return _EMAIL_PATTERN.sub(REDACTED, redacted)
    if isinstance(payload, list):
        return [_redact_worker_response_for_disk(item, request) for item in payload]
    if isinstance(payload, dict):
        return {
            str(_redact_worker_response_for_disk(key, request)): (
                _redact_worker_response_for_disk(value, request)
            )
            for key, value in payload.items()
        }
    return payload


def _process_payload(payload_path: Path, response_path: Path) -> int:
    raw_payload = json.loads(payload_path.read_text(encoding="utf-8"))
    ctx = _build_ctx(
        raw_payload.get("ctx") if isinstance(raw_payload.get("ctx"), dict) else {}
    )
    setup_logging(LoggingSetupRequest(schema_version="1.0"), ctx)
    request = _build_request(
        raw_payload.get("request")
        if isinstance(raw_payload.get("request"), dict)
        else {}
    )
    try:
        result = run_browser_report_download_agent(
            request=request,
            ctx=ctx,
            normalized_url=str(raw_payload.get("normalized_url") or "").strip(),
            execution_url=str(raw_payload.get("execution_url") or "").strip(),
            download_dir=Path(str(raw_payload.get("download_dir") or "")).resolve(),
            prompt_bundle=_build_prompt_bundle(
                raw_payload.get("prompt_bundle")
                if isinstance(raw_payload.get("prompt_bundle"), dict)
                else {}
            ),
        )
        response = BrowserAgentWorkerResponse(
            schema_version="1.0",
            status="ok",
            result=asdict(result),
            error=None,
        )
    except AppError as exc:
        response = BrowserAgentWorkerResponse(
            schema_version="1.0",
            status="app_error",
            result=None,
            error={
                "code": exc.code,
                "message": exc.message,
                "retryable": exc.retryable,
                "severity": exc.severity,
                "context": exc.context,
            },
        )
    except Exception as exc:  # pragma: no cover - defensive worker envelope
        response = BrowserAgentWorkerResponse(
            schema_version="1.0",
            status="error",
            result=None,
            error={
                "code": "browser_download_agent_worker_failed",
                "message": str(exc),
                "retryable": True,
                "severity": "error",
                "context": {"traceback": traceback.format_exc()},
            },
        )
    response_path.write_text(
        json.dumps(
            _redact_worker_response_for_disk(asdict(response), request),
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )
    return 0


def _serve() -> int:
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            command = json.loads(line)
            payload_path = Path(str(command.get("payload_path") or "")).resolve()
            response_path = Path(str(command.get("response_path") or "")).resolve()
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            continue
        _process_payload(payload_path, response_path)
    return 0


def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1] == "--serve":
        return _serve()
    if len(sys.argv) != 3:
        return 2
    return _process_payload(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve())


if __name__ == "__main__":
    exit_code = main()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(exit_code)
