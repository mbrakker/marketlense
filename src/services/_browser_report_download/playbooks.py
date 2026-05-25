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
    BrowserRoutePrivateApiEvidence,
    BrowserRoutePrivateApiPromotionRequest,
    BrowserRoutePlaybook,
    BrowserRoutePlaybookHistoryEntry,
    BrowserRoutePlaybookPromotionRequest,
    BrowserRoutePlaybookPromotionResponse,
    BrowserRoutePlaybookStep,
)
from src.contracts.run_context import RunContext
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.browser_report_download_service")

_PLAYBOOK_SCHEMA_VERSION = "1.0"
_PROMOTION_SUCCESS_OUTCOMES = {"downloaded", "email_requested", "captured"}
_PROMOTION_VERIFIED_STATUSES = {"verified", "recovered"}


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
    ]
    if not route_steps:
        route_steps = [
            BrowserRoutePlaybookStep(
                schema_version="1.0",
                action="follow_route",
                target=result.resolved_target_url or result.final_page_url,
                verification=_verification_for_result(result),
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


def _adapt_route_step_for_playbook(
    *,
    step: BrowserDownloadRouteStep,
    route_kind: str,
    outcome: str,
) -> BrowserRoutePlaybookStep:
    target = step.target_text or step.target_role or step.target_url or "page"
    verification = step.result or f"{route_kind}:{outcome}"
    return BrowserRoutePlaybookStep(
        schema_version="1.0",
        action=step.action or "follow_route",
        target=target,
        verification=verification,
    )


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
