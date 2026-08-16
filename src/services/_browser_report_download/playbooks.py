from __future__ import annotations

import difflib
import logging
import re
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml

from src.contracts.browser_download import (
    BrowserDownloadRouteStep,
    BrowserReportDownloadResult,
    BrowserRoutePlaybook,
    BrowserRoutePlaybookExecutionRequest,
    BrowserRoutePlaybookExecutionResponse,
    BrowserRoutePlaybookHistoryEntry,
    BrowserRoutePlaybookPromotionRequest,
    BrowserRoutePlaybookPromotionResponse,
    BrowserRoutePlaybookStep,
    BrowserRoutePlaybookStepExecution,
    BrowserRoutePrivateApiEvidence,
    BrowserRoutePrivateApiPromotionRequest,
)
from src.contracts.run_context import RunContext
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.browser_report_download_service")

_PLAYBOOK_SCHEMA_VERSION = "1.0"
_PROMOTION_SUCCESS_OUTCOMES = {"downloaded", "email_requested", "captured"}
_PROMOTION_VERIFIED_STATUSES = {"verified", "recovered"}
_EXECUTABLE_PLAYBOOK_ACTIONS = {
    "open",
    "navigate",
    "click",
    "click_cta",
    "submit",
    "fill",
    "type",
    "select",
    "verify",
}


def load_browser_route_playbooks(
    *,
    playbook_dir: str,
    ctx: RunContext,
) -> list[BrowserRoutePlaybook]:
    if not str(playbook_dir or "").strip():
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_route_playbook_load_disabled",
                module=logger.name,
                fields={"loaded_count": 0},
            )
        )
        return []
    root = Path(str(playbook_dir or "").strip()).expanduser()
    if not root.is_absolute():
        root = root.resolve()
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_route_playbook_load_start",
            module=logger.name,
            fields={"playbook_dir": str(root)},
        )
    )
    if not root.exists():
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_route_playbook_load_missing_dir",
                module=logger.name,
                fields={"playbook_dir": str(root), "loaded_count": 0},
            )
        )
        return []
    if not root.is_dir():
        raise AppError(
            code="browser_route_playbook_dir_invalid",
            message="Browser route playbook path is not a directory",
            retryable=False,
            context={"playbook_dir": str(root)},
        )
    playbooks: list[BrowserRoutePlaybook] = []
    for path in sorted(root.glob("*.yaml")):
        playbooks.append(_load_browser_route_playbook_file(path=path, ctx=ctx))
    private_api_dir = root / "private_api"
    if private_api_dir.is_dir():
        for path in sorted(private_api_dir.glob("*.yaml")):
            playbooks.append(_load_browser_route_playbook_file(path=path, ctx=ctx))
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_route_playbook_load_complete",
            module=logger.name,
            fields={
                "playbook_dir": str(root),
                "loaded_count": len(playbooks),
                "playbook_ids": [playbook.playbook_id for playbook in playbooks],
            },
        )
    )
    return playbooks


def promote_validated_browser_route_result_to_playbook(
    *,
    playbook_dir: str,
    result: BrowserReportDownloadResult,
    ctx: RunContext,
    observed_at: str = "",
    write_file: bool = True,
) -> BrowserRoutePlaybookPromotionResponse:
    route_steps = [
        _adapt_route_step_for_playbook(
            step=step,
            route_kind=result.route_kind,
            outcome=result.outcome,
        )
        for step in result.route_steps[:8]
        if _route_step_is_promotable(step)
    ]
    if not route_steps:
        target_url = result.resolved_target_url or result.final_page_url
        route_steps = [
            BrowserRoutePlaybookStep(
                schema_version="1.0",
                action="open",
                target=target_url,
                verification=_verification_for_result(result),
                selector_type="url",
                selector=target_url,
                expected_url_contains=urlsplit(target_url).path,
            )
        ]
    return promote_browser_route_playbook(
        request=BrowserRoutePlaybookPromotionRequest(
            schema_version="1.0",
            playbook_dir=playbook_dir,
            source_url=result.normalized_url or result.source_url,
            route_family=result.route_family,
            route_kind=result.route_kind,
            route_summary=result.route_summary,
            route_status=result.route_status,
            outcome=result.outcome,
            route_steps=route_steps,
            evidence_labels=list(result.terminal_evidence.evidence_labels),
            observed_at=observed_at,
            write_file=write_file,
        ),
        ctx=ctx,
    )


def promote_browser_route_playbook(
    *,
    request: BrowserRoutePlaybookPromotionRequest,
    ctx: RunContext,
) -> BrowserRoutePlaybookPromotionResponse:
    _validate_promotion_request(request)
    observed_at = _resolve_observed_at(request.observed_at)
    host = urlsplit(request.source_url).netloc.casefold()
    if not host:
        raise AppError(
            code="browser_route_playbook_promotion_invalid_url",
            message="Browser route playbook promotion requires a URL with a host",
            retryable=False,
            context={"source_url": request.source_url},
        )
    root = Path(request.playbook_dir).expanduser()
    if not root.is_absolute():
        root = root.resolve()
    playbook_id = f"learned-{_slugify(host)}-{_slugify(request.route_family)}"
    path = root / f"{playbook_id}.yaml"
    before_text = path.read_text(encoding="utf-8") if path.exists() else ""
    existing = _load_existing_for_promotion(path) if path.exists() else None
    version = _next_version(existing.version if existing is not None else "")
    payload = _build_promoted_playbook_payload(
        request=request,
        observed_at=observed_at,
        host=host,
        playbook_id=playbook_id,
        version=version,
        existing=existing,
    )
    after_text = yaml.safe_dump(payload, sort_keys=False, allow_unicode=False)
    review_diff = "".join(
        difflib.unified_diff(
            before_text.splitlines(keepends=True),
            after_text.splitlines(keepends=True),
            fromfile=f"{path.name}:before",
            tofile=f"{path.name}:after",
        )
    )
    if request.write_file:
        root.mkdir(parents=True, exist_ok=True)
        path.write_text(after_text, encoding="utf-8")
    response = BrowserRoutePlaybookPromotionResponse(
        schema_version="1.0",
        playbook_id=playbook_id,
        version=version,
        path=str(path),
        status=(
            "updated"
            if existing is not None and request.write_file
            else "created"
            if request.write_file
            else "dry_run_updated"
            if existing is not None
            else "dry_run_created"
        ),
        review_diff=review_diff,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_route_playbook_promoted",
            module=logger.name,
            fields={
                "playbook_id": response.playbook_id,
                "version": response.version,
                "path": response.path,
                "status": response.status,
                "write_file": request.write_file,
                "source_url": request.source_url,
                "route_family": request.route_family,
                "route_kind": request.route_kind,
                "outcome": request.outcome,
                "review_diff_line_count": len(review_diff.splitlines()),
            },
        )
    )
    return response


def promote_private_api_evidence_to_browser_playbook(
    *,
    request: BrowserRoutePrivateApiPromotionRequest,
    ctx: RunContext,
) -> BrowserRoutePlaybookPromotionResponse:
    _validate_private_api_promotion_request(request)
    observed_at = _resolve_observed_at(request.observed_at)
    host = urlsplit(request.source_url).netloc.casefold()
    if not host:
        raise AppError(
            code="browser_route_private_api_promotion_invalid_url",
            message="Private-API playbook promotion requires a URL with a host",
            retryable=False,
            context={"source_url": request.source_url},
        )
    root = Path(request.playbook_dir).expanduser()
    if not root.is_absolute():
        root = root.resolve()
    private_api_root = root / "private_api"
    if request.write_file:
        private_api_root.mkdir(parents=True, exist_ok=True)
    playbook_id = f"private-api-{_slugify(host)}-{_slugify(request.route_kind)}"
    path = private_api_root / f"{playbook_id}.yaml"
    before_text = path.read_text(encoding="utf-8") if path.exists() else ""
    existing = _load_existing_for_promotion(path) if path.exists() else None
    version = _next_version(existing.version if existing is not None else "")
    payload = _build_private_api_playbook_payload(
        request=request,
        observed_at=observed_at,
        host=host,
        playbook_id=playbook_id,
        version=version,
        existing=existing,
    )
    after_text = yaml.safe_dump(payload, sort_keys=False, allow_unicode=False)
    if request.write_file:
        path.write_text(after_text, encoding="utf-8")
    review_diff = "".join(
        difflib.unified_diff(
            before_text.splitlines(keepends=True),
            after_text.splitlines(keepends=True),
            fromfile=f"{path.name}:before",
            tofile=f"{path.name}:after",
        )
    )
    response = BrowserRoutePlaybookPromotionResponse(
        schema_version="1.0",
        playbook_id=playbook_id,
        version=version,
        path=str(path),
        status=("updated" if existing is not None else "created")
        if request.write_file
        else "dry_run",
        review_diff=review_diff,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_route_private_api_playbook_promoted",
            module=logger.name,
            fields={
                "playbook_id": response.playbook_id,
                "version": response.version,
                "path": response.path,
                "status": response.status,
                "source_url": request.source_url,
                "route_family": request.route_family,
                "route_kind": request.route_kind,
                "validated_success_count": request.validated_success_count,
                "endpoint_pattern": request.endpoint_pattern,
                "response_pdf_url_json_pointer": (
                    request.response_pdf_url_json_pointer
                ),
                "review_diff_line_count": len(review_diff.splitlines()),
            },
        )
    )
    return response


def _load_browser_route_playbook_file(
    *,
    path: Path,
    ctx: RunContext,
) -> BrowserRoutePlaybook:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise AppError(
            code="browser_route_playbook_yaml_invalid",
            message="Browser route playbook YAML is invalid",
            cause=exc,
            retryable=False,
            context={"path": str(path)},
        ) from exc
    except OSError as exc:
        raise AppError(
            code="browser_route_playbook_read_failed",
            message="Browser route playbook file could not be read",
            cause=exc,
            retryable=True,
            context={"path": str(path)},
        ) from exc
    if not isinstance(payload, dict):
        raise AppError(
            code="browser_route_playbook_root_invalid",
            message="Browser route playbook root must be a mapping",
            retryable=False,
            context={"path": str(path)},
        )
    playbook = _build_playbook(payload=payload, path=path)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_route_playbook_loaded",
            module=logger.name,
            fields={
                "path": str(path),
                "playbook_id": playbook.playbook_id,
                "version": playbook.version,
                "status": playbook.status,
                "route_family": playbook.route_family,
                "route_kind": playbook.route_kind,
                "step_count": len(playbook.steps),
            },
        )
    )
    return playbook


def _build_playbook(*, payload: dict[str, Any], path: Path) -> BrowserRoutePlaybook:
    required = (
        "playbook_id",
        "version",
        "updated_at",
        "publisher_pattern",
        "host_patterns",
        "route_family",
        "route_kind",
        "summary",
        "steps",
    )
    missing = [name for name in required if _is_blank(payload.get(name))]
    if missing:
        raise AppError(
            code="browser_route_playbook_contract_invalid",
            message="Browser route playbook is missing required fields",
            retryable=False,
            context={"path": str(path), "missing": missing},
        )
    steps_payload = payload.get("steps")
    if not isinstance(steps_payload, list) or not steps_payload:
        raise AppError(
            code="browser_route_playbook_steps_invalid",
            message="Browser route playbook must contain at least one step",
            retryable=False,
            context={"path": str(path)},
        )
    return BrowserRoutePlaybook(
        schema_version=str(payload.get("schema_version", _PLAYBOOK_SCHEMA_VERSION)),
        playbook_id=str(payload.get("playbook_id") or "").strip(),
        version=str(payload.get("version") or "").strip(),
        status=str(payload.get("status") or "active").strip(),
        updated_at=str(payload.get("updated_at") or "").strip(),
        stale_after_days=int(payload.get("stale_after_days", 180)),
        publisher_pattern=str(payload.get("publisher_pattern") or "").strip(),
        host_patterns=_string_list(payload.get("host_patterns")),
        url_path_markers=_string_list(payload.get("url_path_markers")),
        route_family=str(payload.get("route_family") or "").strip(),
        route_kind=str(payload.get("route_kind") or "").strip(),
        summary=str(payload.get("summary") or "").strip(),
        steps=[
            BrowserRoutePlaybookStep(
                schema_version=str(item.get("schema_version", "1.0")),
                action=str(item.get("action") or "").strip(),
                target=str(item.get("target") or "").strip(),
                verification=str(item.get("verification") or "").strip(),
                selector_type=str(item.get("selector_type") or "").strip(),
                selector=str(item.get("selector") or "").strip(),
                value=str(item.get("value") or "").strip(),
                value_reference=str(item.get("value_reference") or "").strip(),
                expected_url_contains=str(
                    item.get("expected_url_contains") or ""
                ).strip(),
                expected_text=str(item.get("expected_text") or "").strip(),
            )
            for item in steps_payload
            if isinstance(item, dict)
        ],
        traps=_string_list(payload.get("traps")),
        evidence_notes=_string_list(payload.get("evidence_notes")),
        source_evidence=_string_list(payload.get("source_evidence")),
        private_api_evidence=[
            BrowserRoutePrivateApiEvidence(
                schema_version=str(item.get("schema_version", "1.0")),
                evidence_id=str(item.get("evidence_id") or "").strip(),
                endpoint_pattern=str(item.get("endpoint_pattern") or "").strip(),
                method=str(item.get("method") or "GET").strip().upper(),
                request_shape_summary=str(
                    item.get("request_shape_summary") or ""
                ).strip(),
                response_pdf_url_json_pointer=str(
                    item.get("response_pdf_url_json_pointer") or ""
                ).strip(),
                expected_status_codes=[
                    int(value)
                    for value in item.get("expected_status_codes", [200])
                    if str(value).strip().isdigit()
                ]
                or [200],
                required_response_markers=_string_list(
                    item.get("required_response_markers")
                ),
                success_count=int(item.get("success_count", 0) or 0),
                fallback_route_family=str(
                    item.get("fallback_route_family") or ""
                ).strip(),
            )
            for item in payload.get("private_api_evidence", [])
            if isinstance(item, dict)
        ],
        history=[
            BrowserRoutePlaybookHistoryEntry(
                schema_version=str(item.get("schema_version", "1.0")),
                changed_at=str(item.get("changed_at") or "").strip(),
                source=str(item.get("source") or "").strip(),
                summary=str(item.get("summary") or "").strip(),
            )
            for item in payload.get("history", [])
            if isinstance(item, dict)
        ],
    )


def execute_browser_route_playbook(
    request: BrowserRoutePlaybookExecutionRequest,
    ctx: RunContext,
) -> BrowserRoutePlaybookExecutionResponse:
    playbook = request.playbook
    step_results: list[BrowserRoutePlaybookStepExecution] = []
    drift_reasons: list[str] = []
    if playbook.private_api_evidence:
        return BrowserRoutePlaybookExecutionResponse(
            schema_version="1.0",
            status="skipped",
            playbook_id=playbook.playbook_id,
            step_results=[],
            drift_reasons=["private_api_playbook_uses_http_executor"],
        )
    admission_reasons = _deterministic_playbook_admission_reasons(playbook)
    if admission_reasons:
        step_results = [
            BrowserRoutePlaybookStepExecution(
                schema_version="1.0",
                index=index,
                action=step.action,
                target=step.target,
                status="skipped",
                evidence="",
                drift_reason=reason,
            )
            for index, step in enumerate(playbook.steps)
            for reason in [_deterministic_step_admission_reason(step, index)]
            if reason
        ]
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_route_playbook_deterministic_execution_complete",
                module=logger.name,
                fields={
                    "playbook_id": playbook.playbook_id,
                    "status": "skipped",
                    "step_count": len(step_results),
                    "drift_reasons": admission_reasons,
                },
            )
        )
        return BrowserRoutePlaybookExecutionResponse(
            schema_version="1.0",
            status="skipped",
            playbook_id=playbook.playbook_id,
            step_results=step_results,
            drift_reasons=admission_reasons,
        )
    for index, step in enumerate(playbook.steps):
        result = _execute_playbook_step(
            step=step,
            index=index,
            normalized_url=request.normalized_url,
            page_driver=request.page_driver,
            identity_values=request.identity_values,
        )
        step_results.append(result)
        if result.status == "drifted":
            drift_reasons.append(result.drift_reason)
            break
    status = "completed"
    if drift_reasons:
        status = (
            "drifted"
            if any(result.status == "drifted" for result in step_results)
            else "skipped"
        )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_route_playbook_deterministic_execution_complete",
            module=logger.name,
            fields={
                "playbook_id": playbook.playbook_id,
                "status": status,
                "step_count": len(step_results),
                "drift_reasons": drift_reasons,
            },
        )
    )
    return BrowserRoutePlaybookExecutionResponse(
        schema_version="1.0",
        status=status,
        playbook_id=playbook.playbook_id,
        step_results=step_results,
        drift_reasons=drift_reasons,
    )


def _deterministic_playbook_admission_reasons(
    playbook: BrowserRoutePlaybook,
) -> list[str]:
    if not playbook.steps:
        return ["playbook_has_no_deterministic_steps"]
    return [
        reason
        for index, step in enumerate(playbook.steps)
        for reason in [_deterministic_step_admission_reason(step, index)]
        if reason
    ]


def _deterministic_step_admission_reason(
    step: BrowserRoutePlaybookStep,
    index: int,
) -> str:
    action = step.action.strip().lower()
    if action not in _EXECUTABLE_PLAYBOOK_ACTIONS:
        return f"step_{index}_unsupported_deterministic_action"
    if not step.selector.strip():
        return f"step_{index}_missing_deterministic_selector"
    if not (step.expected_url_contains.strip() or step.expected_text.strip()):
        return f"step_{index}_missing_deterministic_postcondition"
    return ""


def _execute_playbook_step(
    *,
    step: BrowserRoutePlaybookStep,
    index: int,
    normalized_url: str,
    page_driver,
    identity_values: dict[str, str],
) -> BrowserRoutePlaybookStepExecution:
    try:
        evidence = _dispatch_playbook_action(
            step=step,
            normalized_url=normalized_url,
            page_driver=page_driver,
            identity_values=identity_values,
        )
        drift_reason = _verify_playbook_step(step=step, page_driver=page_driver)
    except Exception as exc:
        return BrowserRoutePlaybookStepExecution(
            schema_version="1.0",
            index=index,
            action=step.action,
            target=step.target,
            status="drifted",
            evidence="",
            drift_reason=f"executor_error:{type(exc).__name__}",
        )
    if drift_reason:
        return BrowserRoutePlaybookStepExecution(
            schema_version="1.0",
            index=index,
            action=step.action,
            target=step.target,
            status="drifted",
            evidence=evidence,
            drift_reason=drift_reason,
        )
    return BrowserRoutePlaybookStepExecution(
        schema_version="1.0",
        index=index,
        action=step.action,
        target=step.target,
        status="executed",
        evidence=evidence,
        drift_reason="",
    )


def _dispatch_playbook_action(
    *,
    step: BrowserRoutePlaybookStep,
    normalized_url: str,
    page_driver,
    identity_values: dict[str, str],
) -> str:
    action = step.action.strip().lower()
    selector_type = step.selector_type.strip().lower()
    selector = step.selector.strip()
    if action in {"open", "navigate"}:
        target_url = selector or step.target or normalized_url
        return str(page_driver.open(target_url))
    if action in {"click", "click_cta", "submit"}:
        if selector_type == "role":
            role, name = _split_role_locator(selector)
            return str(page_driver.click_role(role, name))
        if selector_type == "label":
            return str(page_driver.click_label(selector))
        if selector_type == "name":
            return str(page_driver.click_name(selector))
        if selector_type == "data_attribute":
            return str(page_driver.click_data_attribute(selector))
        if selector_type == "text":
            return str(page_driver.click_text(selector))
        return str(page_driver.click_css(selector))
    if action in {"fill", "type"}:
        value = _resolve_playbook_step_value(step=step, identity_values=identity_values)
        if selector_type == "label":
            return str(page_driver.fill_label(selector, value))
        if selector_type == "name":
            return str(page_driver.fill_name(selector, value))
        if selector_type == "data_attribute":
            return str(page_driver.fill_data_attribute(selector, value))
        return str(page_driver.fill_css(selector, value))
    if action == "select":
        value = _resolve_playbook_step_value(step=step, identity_values=identity_values)
        if selector_type == "label":
            return str(page_driver.select_label(selector, value))
        if selector_type == "name":
            return str(page_driver.select_name(selector, value))
        if selector_type == "data_attribute":
            return str(page_driver.select_data_attribute(selector, value))
        return str(page_driver.select_css(selector, value))
    if action == "verify":
        return "verified"
    raise ValueError(f"unsupported_action:{step.action}")


def _split_role_locator(selector: str) -> tuple[str, str]:
    role, separator, name = selector.partition(":")
    if not separator or not role.strip() or not name.strip():
        raise ValueError("invalid_role_locator")
    return role.strip(), name.strip()


def _resolve_playbook_step_value(
    *,
    step: BrowserRoutePlaybookStep,
    identity_values: dict[str, str],
) -> str:
    reference = step.value_reference.strip()
    if not reference:
        return step.value
    if not (reference.startswith("${identity.") and reference.endswith("}")):
        raise ValueError("invalid_identity_reference")
    key = reference.removeprefix("${identity.").removesuffix("}")
    value = str(identity_values.get(key) or "")
    if not value:
        raise ValueError("identity_reference_unresolved")
    return value


def _verify_playbook_step(*, step: BrowserRoutePlaybookStep, page_driver) -> str:
    expected_url = step.expected_url_contains.strip()
    if expected_url and expected_url not in str(page_driver.current_url()):
        return "expected_url_not_observed"
    expected_text = step.expected_text.strip()
    if expected_text and not bool(page_driver.contains_text(expected_text)):
        return "expected_text_not_observed"
    return ""


def _load_existing_for_promotion(path: Path) -> BrowserRoutePlaybook:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise AppError(
            code="browser_route_playbook_root_invalid",
            message="Existing browser route playbook root must be a mapping",
            retryable=False,
            context={"path": str(path)},
        )
    return _build_playbook(payload=payload, path=path)


def _build_promoted_playbook_payload(
    *,
    request: BrowserRoutePlaybookPromotionRequest,
    observed_at: str,
    host: str,
    playbook_id: str,
    version: str,
    existing: BrowserRoutePlaybook | None,
) -> dict[str, Any]:
    history = [asdict(item) for item in existing.history] if existing else []
    history.append(
        asdict(
            BrowserRoutePlaybookHistoryEntry(
                schema_version="1.0",
                changed_at=observed_at,
                source="validated_route_promotion",
                summary=(
                    f"Promoted {request.route_family}/{request.route_kind} "
                    f"after {request.outcome} evidence."
                ),
            )
        )
    )
    source_evidence = list(existing.source_evidence) if existing else []
    for label in request.evidence_labels:
        if label and label not in source_evidence:
            source_evidence.append(label)
    return {
        "schema_version": _PLAYBOOK_SCHEMA_VERSION,
        "playbook_id": playbook_id,
        "version": version,
        "status": "active",
        "updated_at": observed_at,
        "stale_after_days": existing.stale_after_days if existing else 120,
        "publisher_pattern": host,
        "host_patterns": [host],
        "url_path_markers": _derive_path_markers(request.source_url),
        "route_family": request.route_family,
        "route_kind": request.route_kind,
        "summary": request.route_summary,
        "steps": [asdict(step) for step in request.route_steps],
        "traps": list(existing.traps) if existing else [],
        "evidence_notes": [
            f"Promoted only after {request.route_status} route evidence with outcome {request.outcome}."
        ],
        "source_evidence": source_evidence,
        "private_api_evidence": (
            [asdict(item) for item in existing.private_api_evidence] if existing else []
        ),
        "history": history,
    }


def _build_private_api_playbook_payload(
    *,
    request: BrowserRoutePrivateApiPromotionRequest,
    observed_at: str,
    host: str,
    playbook_id: str,
    version: str,
    existing: BrowserRoutePlaybook | None,
) -> dict[str, Any]:
    history = [asdict(item) for item in existing.history] if existing else []
    history.append(
        asdict(
            BrowserRoutePlaybookHistoryEntry(
                schema_version="1.0",
                changed_at=observed_at,
                source="validated_private_api_evidence_promotion",
                summary=(
                    f"Promoted private API evidence after "
                    f"{request.validated_success_count} validated successes."
                ),
            )
        )
    )
    source_evidence = list(existing.source_evidence) if existing else []
    for label in [
        "browser_network_private_api",
        "request_shape_documented",
        "deterministic_http_fallback",
        *request.evidence_labels,
    ]:
        if label and label not in source_evidence:
            source_evidence.append(label)
    return {
        "schema_version": _PLAYBOOK_SCHEMA_VERSION,
        "playbook_id": playbook_id,
        "version": version,
        "status": "active",
        "updated_at": observed_at,
        "stale_after_days": existing.stale_after_days if existing else 45,
        "publisher_pattern": host,
        "host_patterns": [host],
        "url_path_markers": _derive_path_markers(request.source_url),
        "route_family": request.route_family,
        "route_kind": request.route_kind,
        "summary": (
            "Use the validated network-learned private API endpoint before "
            "launching browser-use; fall back to the normal browser route when "
            "the response shape or artifact validation fails."
        ),
        "steps": [
            asdict(
                BrowserRoutePlaybookStep(
                    schema_version="1.0",
                    action="http_private_api",
                    target=request.endpoint_pattern,
                    verification=(
                        "response JSON yields a PDF URL and the downloaded "
                        "artifact validates as application/pdf"
                    ),
                )
            )
        ],
        "traps": list(existing.traps) if existing else [],
        "evidence_notes": [
            (
                "Promoted only after repeated validated success, documented "
                "request shape, and explicit fallback to normal discovery."
            ),
            f"Request shape: {request.request_shape_summary}",
        ],
        "source_evidence": source_evidence,
        "private_api_evidence": [
            asdict(
                BrowserRoutePrivateApiEvidence(
                    schema_version="1.0",
                    evidence_id=f"{playbook_id}-endpoint",
                    endpoint_pattern=request.endpoint_pattern,
                    method=request.method.strip().upper(),
                    request_shape_summary=request.request_shape_summary,
                    response_pdf_url_json_pointer=(
                        request.response_pdf_url_json_pointer
                    ),
                    expected_status_codes=list(request.expected_status_codes or [200]),
                    required_response_markers=list(request.required_response_markers),
                    success_count=request.validated_success_count,
                    fallback_route_family=request.fallback_route_family,
                )
            )
        ],
        "history": history,
    }


def _validate_promotion_request(request: BrowserRoutePlaybookPromotionRequest) -> None:
    if request.schema_version != "1.0":
        raise AppError(
            code="browser_route_playbook_promotion_schema_unsupported",
            message="Unsupported browser route playbook promotion schema version",
            retryable=False,
            context={"schema_version": request.schema_version},
        )
    if request.route_status not in _PROMOTION_VERIFIED_STATUSES:
        raise AppError(
            code="browser_route_playbook_promotion_unverified",
            message="Only verified or recovered browser routes can be promoted",
            retryable=False,
            context={"route_status": request.route_status},
        )
    if request.outcome not in _PROMOTION_SUCCESS_OUTCOMES:
        raise AppError(
            code="browser_route_playbook_promotion_unsuccessful",
            message="Only successful browser route outcomes can be promoted",
            retryable=False,
            context={"outcome": request.outcome},
        )
    missing = [
        name
        for name in (
            "playbook_dir",
            "source_url",
            "route_family",
            "route_kind",
            "route_summary",
        )
        if _is_blank(getattr(request, name))
    ]
    if missing:
        raise AppError(
            code="browser_route_playbook_promotion_contract_invalid",
            message="Browser route playbook promotion request is missing required fields",
            retryable=False,
            context={"missing": missing},
        )
    if not request.route_steps:
        raise AppError(
            code="browser_route_playbook_promotion_steps_invalid",
            message="Browser route playbook promotion requires at least one route step",
            retryable=False,
            context={"source_url": request.source_url},
        )


def _validate_private_api_promotion_request(
    request: BrowserRoutePrivateApiPromotionRequest,
) -> None:
    if request.schema_version != "1.0":
        raise AppError(
            code="browser_route_private_api_promotion_schema_unsupported",
            message="Unsupported private-API playbook promotion schema version",
            retryable=False,
            context={"schema_version": request.schema_version},
        )
    missing = [
        name
        for name in (
            "playbook_dir",
            "source_url",
            "route_family",
            "route_kind",
            "endpoint_pattern",
            "method",
            "request_shape_summary",
            "response_pdf_url_json_pointer",
            "fallback_route_family",
        )
        if _is_blank(getattr(request, name))
    ]
    if missing:
        raise AppError(
            code="browser_route_private_api_promotion_contract_invalid",
            message="Private-API playbook promotion request is missing required fields",
            retryable=False,
            context={"missing": missing},
        )
    if request.validated_success_count < 2:
        raise AppError(
            code="browser_route_private_api_promotion_insufficient_evidence",
            message="Private-API promotion requires repeated validated successes",
            retryable=False,
            context={"validated_success_count": request.validated_success_count},
        )
    if request.method.strip().upper() != "GET":
        raise AppError(
            code="browser_route_private_api_promotion_method_unsupported",
            message="Only GET private-API evidence can be promoted automatically",
            retryable=False,
            context={"method": request.method},
        )
    if not request.expected_status_codes:
        raise AppError(
            code="browser_route_private_api_promotion_statuses_missing",
            message="Private-API promotion requires expected status codes",
            retryable=False,
            context={"source_url": request.source_url},
        )
    if not [
        marker for marker in request.required_response_markers if str(marker).strip()
    ]:
        raise AppError(
            code="browser_route_private_api_promotion_markers_missing",
            message="Private-API promotion requires response-shape markers",
            retryable=False,
            context={"source_url": request.source_url},
        )
    labels = {
        str(label).strip() for label in request.evidence_labels if str(label).strip()
    }
    if not labels.intersection(
        {
            "network_document_request",
            "browser_network_private_api",
            "private_api_pdf_pointer",
        }
    ):
        raise AppError(
            code="browser_route_private_api_promotion_evidence_labels_missing",
            message="Private-API promotion requires durable browser network evidence labels",
            retryable=False,
            context={"source_url": request.source_url},
        )
    source_host = urlsplit(request.source_url).netloc.lower()
    endpoint_host = urlsplit(request.endpoint_pattern).netloc.lower()
    if endpoint_host and endpoint_host != source_host:
        raise AppError(
            code="browser_route_private_api_promotion_host_mismatch",
            message="Private-API endpoint host must match the source publisher host",
            retryable=False,
            context={
                "source_host": source_host,
                "endpoint_host": endpoint_host,
            },
        )


def _adapt_route_step_for_playbook(
    *,
    step: BrowserDownloadRouteStep,
    route_kind: str,
    outcome: str,
) -> BrowserRoutePlaybookStep:
    selector_type, selector = _stable_playbook_locator(step)
    target = step.target_text or step.target_role or step.target_url or "page"
    verification = step.result or f"{route_kind}:{outcome}"
    value_reference = _identity_value_reference(step.identity_field_reference)
    return BrowserRoutePlaybookStep(
        schema_version="1.0",
        action=step.action or "follow_route",
        target=target,
        verification=verification,
        selector_type=selector_type,
        selector=selector,
        value_reference=value_reference,
        expected_url_contains=step.expected_url_contains,
        expected_text=step.expected_text,
    )


def _route_step_is_promotable(step: BrowserDownloadRouteStep) -> bool:
    """Keep failed model actions in audit evidence, not active route guidance."""
    action = str(step.action or "").strip().casefold()
    result = str(step.result or "").casefold()
    if action not in _EXECUTABLE_PLAYBOOK_ACTIONS:
        return False
    if str(step.verification_status or "").strip().casefold() != "verified":
        return False
    if not step.observed_evidence:
        return False
    if action in {
        "fill",
        "type",
        "select",
    } and not _identity_value_reference(step.identity_field_reference):
        return False
    if action not in {"open", "navigate", "verify"} and not all(
        _stable_playbook_locator(step)
    ):
        return False
    return not any(
        marker in result
        for marker in (
            "not verified",
            "unverified",
            "blocked",
            "could not",
            "failed",
        )
    )


def _stable_playbook_locator(step: BrowserDownloadRouteStep) -> tuple[str, str]:
    role = str(step.locator_role or "").strip()
    name = str(step.locator_name or "").strip()
    if role and name:
        return "role", f"{role}:{name}"
    label = str(step.locator_label or "").strip()
    if label:
        return "label", label
    field_name = str(step.locator_field_name or "").strip()
    if field_name:
        return "name", field_name
    data_attribute = str(step.locator_data_attribute or "").strip()
    if data_attribute:
        return "data_attribute", data_attribute
    css = str(step.locator_css or "").strip()
    if css:
        return "css", css
    text = str(step.locator_text or "").strip()
    if text:
        return "text", text
    action = str(step.action or "").strip().casefold()
    if action in {"click", "click_cta", "submit"}:
        target_role = str(step.target_role or "").strip()
        target_name = str(step.target_text or "").strip()
        if target_role and target_name:
            return "role", f"{target_role}:{target_name}"
    if action in {"open", "navigate"}:
        target_url = str(step.target_url or "").strip()
        if target_url:
            return "url", target_url
    return "", ""


def _identity_value_reference(reference: str) -> str:
    token = str(reference or "").strip()
    if not token.startswith("identity.") or len(token) <= len("identity."):
        return ""
    if not re.fullmatch(r"identity\.[a-z][a-z0-9_]*", token):
        return ""
    return "${" + token + "}"


def _verification_for_result(result: BrowserReportDownloadResult) -> str:
    if result.outcome == "downloaded":
        return "verified local report artifact"
    if result.outcome == "email_requested":
        return "confirmed form submission or email-delivery terminal state"
    if result.outcome == "captured":
        return "local onsite capture artifact"
    return f"{result.route_kind}:{result.outcome}"


def _resolve_observed_at(observed_at: str) -> str:
    token = str(observed_at or "").strip()
    if token:
        return token
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _derive_path_markers(source_url: str) -> list[str]:
    path_parts = [
        item
        for item in urlsplit(source_url).path.casefold().split("/")
        if len(item) >= 4
    ]
    markers = []
    for part in path_parts:
        cleaned = re.sub(r"[^a-z0-9-]", "", part)
        if cleaned and cleaned not in markers:
            markers.append(cleaned)
    return markers[:5]


def _next_version(current: str) -> str:
    token = str(current or "").strip()
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", token)
    if not match:
        return "1.0.0"
    major, minor, patch = (
        int(match.group(1)),
        int(match.group(2)),
        int(match.group(3)),
    )
    return f"{major}.{minor}.{patch + 1}"


def _slugify(value: str) -> str:
    token = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return token or "unknown"


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


def _is_blank(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    if isinstance(value, list) and not value:
        return True
    return False
