from __future__ import annotations

import asyncio
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
    BrowserDownloadRouteSuppressionPolicy,
    BrowserDownloadSessionReusePolicy,
    BrowserDownloadSettings,
    BrowserDownloadWarmWorkerPoolPolicy,
    BrowserReportDownloadRequest,
    BrowserRoutePlaybook,
    BrowserRoutePlaybookHistoryEntry,
    BrowserRoutePlaybookStep,
    BrowserRoutePrivateApiEvidence,
    BrowserRoutePlaybookSelection,
)
from src.contracts.logging import LoggingSetupRequest
from src.contracts.publisher_inventory import PublisherInventoryCandidateTrace
from src.contracts.run_budget import RunBudgetLimits
from src.contracts.run_context import RunContext
from src.contracts.semantic_ids import RunId, TaskId
from src.services._browser_report_download._browser_runtime.runtime import (
    browser_runtime_identity,
    load_browser_session_class,
    load_browser_use_runtime,
)
from src.services._browser_report_download.browser import (
    BrowserAgentWorkerResponse,
    _run_async_deterministic_browser_route_playbook,
    close_browser_preflight_session,
    run_browser_report_download_agent,
    start_browser_preflight_session,
)
from src.services._browser_report_download.prompt import (
    BrowserDownloadPromptBundle,
    redact_browser_report_download_prompt_for_log,
)
from src.services.logging_service import setup_logging
from src.utils.errors import AppError
from src.utils.logging import REDACTED

_EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
_DETERMINISTIC_NAVIGATION_SETTLE_SECONDS = 15.0


async def navigate_deterministic_playbook_page(
    *,
    browser: Any,
    execution_url: str,
    timeout_seconds: float = _DETERMINISTIC_NAVIGATION_SETTLE_SECONDS,
) -> bool:
    """Begin page navigation without letting an unsettled page suppress its route."""
    try:
        await asyncio.wait_for(
            browser.navigate_to(execution_url), timeout=max(0.01, timeout_seconds)
        )
    except TimeoutError:
        return False
    return True


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
    route_suppression_payload = payload.get("route_suppression_policy")
    route_budgets_payload = payload.get("route_budgets")
    model_pricing_payload = payload.get("model_pricing")
    run_budget_limits_run_payload = payload.get("run_budget_limits_run")
    run_budget_limits_day_payload = payload.get("run_budget_limits_day")
    run_budget_limits_publisher_payload = payload.get("run_budget_limits_publisher")
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
        openai_api_key=str(payload.get("openai_api_key") or ""),
        openrouter_model=str(payload.get("openrouter_model") or "openai/gpt-5-mini"),
        headed=bool(payload.get("headed", False)),
        retry_retries=int(payload.get("retry_retries", 0)),
        retry_base_delay_seconds=float(payload.get("retry_base_delay_seconds", 1.0)),
        retry_backoff_step_seconds=float(
            payload.get("retry_backoff_step_seconds", 1.0)
        ),
        retry_jitter_seconds=float(payload.get("retry_jitter_seconds", 0.0)),
        drive_upload_enabled=bool(payload.get("drive_upload_enabled", False)),
        drive_upload_required=bool(payload.get("drive_upload_required", True)),
        drive_upload_parent_folder_id=str(
            payload.get("drive_upload_parent_folder_id") or ""
        ),
        drive_upload_google_sa_path=str(
            payload.get("drive_upload_google_sa_path") or ""
        ),
        drive_upload_auth_mode=str(
            payload.get("drive_upload_auth_mode") or "service_account"
        ),
        drive_upload_oauth_client_path=payload.get("drive_upload_oauth_client_path"),
        drive_upload_oauth_token_path=payload.get("drive_upload_oauth_token_path"),
        drive_upload_supports_all_drives=bool(
            payload.get("drive_upload_supports_all_drives", True)
        ),
        drive_upload_include_items_from_all_drives=bool(
            payload.get("drive_upload_include_items_from_all_drives", True)
        ),
        drive_upload_drive_id=payload.get("drive_upload_drive_id"),
        failure_forensics_enabled=bool(payload.get("failure_forensics_enabled", True)),
        failure_forensics_policy=str(
            payload.get("failure_forensics_policy") or "copy_artifacts"
        ),
        route_playbook_dir=str(
            payload.get("route_playbook_dir") or "./src/playbooks/browser_routes"
        ),
        route_playbook_stale_policy=str(
            payload.get("route_playbook_stale_policy") or "fallback"
        ),
        route_memory_ttl_seconds=int(payload.get("route_memory_ttl_seconds", 2592000)),
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
        model_pricing=(
            model_pricing_payload if isinstance(model_pricing_payload, dict) else {}
        ),
        cost_ledger_path=str(
            payload.get("cost_ledger_path") or "./out/cost-ledger.jsonl"
        ),
        cost_daily_path=str(payload.get("cost_daily_path") or "./out/cost-daily.json"),
        usage_db_path=str(payload.get("usage_db_path") or "./state/llm_usage.sqlite"),
        run_budget_enabled=bool(payload.get("run_budget_enabled", False)),
        run_budget_max_browser_launches=_optional_int(
            payload.get("run_budget_max_browser_launches")
        ),
        run_budget_max_pdfs=_optional_int(payload.get("run_budget_max_pdfs")),
        run_budget_max_drive_writes=_optional_int(
            payload.get("run_budget_max_drive_writes")
        ),
        route_suppression_policy=_build_route_suppression_policy(
            route_suppression_payload
            if isinstance(route_suppression_payload, dict)
            else {}
        ),
        run_budget_max_drive_reads=_optional_int(
            payload.get("run_budget_max_drive_reads")
        ),
        run_budget_max_mailbox_reads=_optional_int(
            payload.get("run_budget_max_mailbox_reads")
        ),
        run_budget_max_retries=_optional_int(payload.get("run_budget_max_retries")),
        run_budget_max_runtime_seconds=_optional_int(
            payload.get("run_budget_max_runtime_seconds")
        ),
        run_budget_enabled_effect_kinds=tuple(
            str(kind).strip()
            for kind in payload.get("run_budget_enabled_effect_kinds", [])
            if str(kind).strip()
        ),
        run_budget_limit_decision=str(
            payload.get("run_budget_limit_decision") or "stop"
        ),
        run_budget_policy_version=str(
            payload.get("run_budget_policy_version") or "budget-authority-v2"
        ),
        run_budget_reservation_ttl_seconds=int(
            payload.get("run_budget_reservation_ttl_seconds", 300)
        ),
        run_budget_limits_run=_build_run_budget_limits(run_budget_limits_run_payload),
        run_budget_limits_day=_build_run_budget_limits(run_budget_limits_day_payload),
        run_budget_limits_publisher=_build_run_budget_limits(
            run_budget_limits_publisher_payload
        ),
        daily_spend_warn_usd=float(payload.get("daily_spend_warn_usd", 3.0)),
        daily_spend_pause_usd=_optional_float(payload.get("daily_spend_pause_usd")),
        daily_spend_stop_usd=_optional_float(payload.get("daily_spend_stop_usd")),
        accounting_queue_size=int(payload.get("accounting_queue_size", 256)),
        accounting_flush_timeout_seconds=float(
            payload.get("accounting_flush_timeout_seconds", 5.0)
        ),
    )


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, (str, bytes, bytearray, int, float)):
        return int(value)
    raise TypeError("optional integer configuration must be numeric")


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (str, bytes, bytearray, int, float)):
        return float(value)
    raise TypeError("optional float configuration must be numeric")


def _build_run_budget_limits(payload: object) -> RunBudgetLimits | None:
    if not isinstance(payload, dict):
        return None
    return RunBudgetLimits(
        schema_version=str(payload.get("schema_version", "1.0")),
        max_spend_usd=_optional_float(payload.get("max_spend_usd")),
        max_tokens=_optional_int(payload.get("max_tokens")),
        max_calls=_optional_int(payload.get("max_calls")),
        max_steps=_optional_int(payload.get("max_steps")),
        max_runtime_seconds=_optional_int(payload.get("max_runtime_seconds")),
        max_retries=_optional_int(payload.get("max_retries")),
        max_browser_launches=_optional_int(payload.get("max_browser_launches")),
        max_drive_writes=_optional_int(payload.get("max_drive_writes")),
        max_drive_reads=_optional_int(payload.get("max_drive_reads")),
        max_wordpress_writes=_optional_int(payload.get("max_wordpress_writes")),
        max_pdfs=_optional_int(payload.get("max_pdfs")),
        max_mailbox_reads=_optional_int(payload.get("max_mailbox_reads")),
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


def _build_route_suppression_policy(
    payload: dict,
) -> BrowserDownloadRouteSuppressionPolicy:
    classes = tuple(
        sorted(
            {
                str(item).strip()
                for item in payload.get("terminal_failure_classes", [])
                if str(item).strip()
            }
            or {
                "blocked_captcha",
                "blocked_email_domain",
                "blocked_no_progress",
            }
        )
    )
    return BrowserDownloadRouteSuppressionPolicy(
        schema_version=str(payload.get("schema_version", "1.0")),
        enabled=bool(payload.get("enabled", True)),
        minimum_sample_size=max(int(payload.get("minimum_sample_size", 3) or 3), 3),
        terminal_failure_threshold=min(
            1.0,
            max(0.0, float(payload.get("terminal_failure_threshold", 1.0) or 1.0)),
        ),
        ttl_seconds=max(int(payload.get("ttl_seconds", 604800) or 604800), 1),
        terminal_failure_classes=classes,
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
                locator_evidence=[
                    str(value).strip()
                    for value in item.get("locator_evidence", [])
                    if str(value or "").strip()
                ]
                if isinstance(item.get("locator_evidence"), list)
                else [],
                postcondition_evidence=[
                    str(value).strip()
                    for value in item.get("postcondition_evidence", [])
                    if str(value or "").strip()
                ]
                if isinstance(item.get("postcondition_evidence"), list)
                else [],
                verification_status=str(item.get("verification_status") or "").strip(),
                locator_role=str(item.get("locator_role") or "").strip(),
                locator_name=str(item.get("locator_name") or "").strip(),
                locator_label=str(item.get("locator_label") or "").strip(),
                locator_field_name=str(item.get("locator_field_name") or "").strip(),
                locator_data_attribute=str(
                    item.get("locator_data_attribute") or ""
                ).strip(),
                locator_css=str(item.get("locator_css") or "").strip(),
                locator_text=str(item.get("locator_text") or "").strip(),
                identity_field_reference=str(
                    item.get("identity_field_reference") or ""
                ).strip(),
                expected_url_contains=str(
                    item.get("expected_url_contains") or ""
                ).strip(),
                expected_text=str(item.get("expected_text") or "").strip(),
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
        publisher_name=str(payload.get("publisher_name") or "").strip(),
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
    normalized_url = str(raw_payload.get("normalized_url") or "").strip()
    execution_url = str(raw_payload.get("execution_url") or "").strip()
    download_dir = Path(str(raw_payload.get("download_dir") or "")).resolve()
    try:
        if raw_payload.get("execution_mode") == "deterministic_playbook":
            playbook = _build_deterministic_playbook(
                raw_payload.get("deterministic_playbook")
                if isinstance(raw_payload.get("deterministic_playbook"), dict)
                else {}
            )
            session = start_browser_preflight_session(
                browser_use=load_browser_use_runtime(normalized_url=normalized_url),
                request=request,
                ctx=ctx,
                normalized_url=normalized_url,
                download_dir=download_dir,
            )
            result = None
            try:

                async def execute_and_stop() -> Any:
                    try:
                        await session.browser.start()
                        await navigate_deterministic_playbook_page(
                            browser=session.browser,
                            execution_url=execution_url,
                        )
                        return await _run_async_deterministic_browser_route_playbook(
                            request=request,
                            ctx=ctx,
                            normalized_url=normalized_url,
                            execution_url=execution_url,
                            download_dir=download_dir,
                            browser=session.browser,
                            playbook=playbook,
                            browser_started=True,
                        )
                    finally:
                        await session.browser.kill()

                result = asyncio.run(execute_and_stop())
            finally:
                close_browser_preflight_session(
                    session=session,
                    ctx=ctx,
                    normalized_url=normalized_url,
                    outcome="completed" if result is not None else "failed",
                    verified_artifact_count=0,
                )
            if result is None:
                response = BrowserAgentWorkerResponse(
                    schema_version="1.0",
                    status="drifted",
                    result=None,
                    error=None,
                )
            else:
                response = BrowserAgentWorkerResponse(
                    schema_version="1.0",
                    status="ok",
                    result=asdict(result),
                    error=None,
                )
        else:
            result = run_browser_report_download_agent(
                request=request,
                ctx=ctx,
                normalized_url=normalized_url,
                execution_url=execution_url,
                download_dir=download_dir,
                prompt_bundle=_build_prompt_bundle(
                    raw_payload.get("prompt_bundle")
                    if isinstance(raw_payload.get("prompt_bundle"), dict)
                    else {}
                ),
                inside_worker=True,
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


def _build_deterministic_playbook(payload: dict[str, Any]) -> BrowserRoutePlaybook:
    return BrowserRoutePlaybook(
        **{
            **payload,
            "steps": [
                BrowserRoutePlaybookStep(**item) for item in payload.get("steps", [])
            ],
            "history": [
                BrowserRoutePlaybookHistoryEntry(**item)
                for item in payload.get("history", [])
            ],
            "private_api_evidence": [
                BrowserRoutePrivateApiEvidence(**item)
                for item in payload.get("private_api_evidence", [])
            ],
        }
    )


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
    if len(sys.argv) == 2 and sys.argv[1] == "--runtime-probe":
        runtime = load_browser_use_runtime()
        load_browser_session_class()
        print(json.dumps(browser_runtime_identity(runtime).__dict__, ensure_ascii=True))
        return 0
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
