from __future__ import annotations

import logging
import time
import json
from pathlib import Path
from typing import List, Optional

from src.contracts.files import ListHtmlRequest, ReadTextRequest
from src.contracts.publish import PublishOutcome, PublishRequest, PublishSettings
from src.contracts.report_store import ReportMetadataListRequest
from src.contracts.run_context import RunContext
from src.contracts.state import StateGetRequest, StatePublishCheckRequest, StatePublishRecordRequest
from src.contracts.validation import ValidationIssue, ValidationReport
from src.contracts.wordpress import WordPressPostLookupRequest
from src.services.file_service import list_html, read_text
from src.services.report_store_service import list_metadata
from src.services.state_service import already_published as state_already_published
from src.services.state_service import get as state_get
from src.services.state_service import record_publish as state_record_publish
from src.generators.publish_generator import publish_html
from src.orchestrators.retry_orchestrator import RetryPolicy, run_with_retry
from src.services.wordpress_service import find_post_by_file_id
from src.utils.html_utils import extract_file_id
from src.utils.errors import AppError
from src.utils.logging import child_context, log_event, new_run_context
from src.utils.wp_auth import build_auth_header

logger = logging.getLogger("market_lense.publish_orchestrator")


def _canonical_html_path(path: str) -> str:
    try:
        return str(Path(path).expanduser().resolve())
    except Exception:
        return str(Path(path))


def _load_html_file_id_map(reports_db: str, ctx: RunContext) -> dict[str, str]:
    if not reports_db.strip():
        return {}
    response = list_metadata(
        ReportMetadataListRequest(schema_version="1.1", db_path=reports_db),
        ctx,
    )
    mapping: dict[str, str] = {}
    records = sorted(
        response.records,
        key=lambda row: int(getattr(row, "updated_at", 0) or 0),
        reverse=True,
    )
    for row in records:
        html_path = (row.html_path or "").strip()
        file_id = (row.file_id or "").strip()
        if not html_path or not file_id:
            continue
        key = _canonical_html_path(html_path)
        if key not in mapping:
            mapping[key] = file_id
    logger.info(log_event(
        ctx,
        role="orchestrator",
        event="publish_html_file_id_map_loaded",
        module=logger.name,
        fields={"reports_db": reports_db, "rows": len(response.records), "mapped": len(mapping)},
    ))
    return mapping


def _validation_paths(output_dir: str, file_id: str, html_path: str) -> list[Path]:
    """
    Validation path in the per-report folder: out/<report-slug>/report_analysis/validation.json.
    """
    _ = file_id
    html_slug = Path(html_path).stem
    return [Path(output_dir) / html_slug / "report_analysis" / "validation.json"]


def _load_validation_report(file_id: str, html_path: str, settings: PublishSettings, ctx) -> Optional[ValidationReport]:
    candidates = _validation_paths(settings.output_dir, file_id, html_path)
    data = None
    used_path: Optional[Path] = None
    for path in candidates:
        try:
            resp = read_text(ReadTextRequest(schema_version="1.0", path=str(path)), ctx)
        except AppError as exc:
            logger.info(log_event(
                ctx,
                role="orchestrator",
                event="publish_validation_missing",
                module=logger.name,
                fields={"file_id": file_id, "path": str(path), "error": exc.message},
            ))
            continue
        try:
            data = json.loads(resp.content)
            used_path = path
            break
        except json.JSONDecodeError:
            logger.info(log_event(
                ctx,
                role="orchestrator",
                event="publish_validation_parse_failed",
                module=logger.name,
                fields={"file_id": file_id, "path": str(path)},
            ))
            continue
    if data is None or used_path is None:
        return None
    issues_payload = data.get("issues") if isinstance(data, dict) else []
    issues: List[ValidationIssue] = []
    if isinstance(issues_payload, list):
        for item in issues_payload:
            if not isinstance(item, dict):
                continue
            issues.append(ValidationIssue(
                schema_version=str(item.get("schema_version", "1.0")),
                message=str(item.get("message", "")),
                severity=str(item.get("severity", "warning")),
                affected_section=str(item.get("affected_section", "")),
            ))
    status = str(data.get("status") or "fail")
    severity = str(data.get("severity") or ("error" if status != "pass" else "pass"))
    severity_norm = severity if severity in {"pass", "warning", "error"} else "error"
    return ValidationReport(
        schema_version=str(data.get("schema_version", "1.1")),
        status=status,
        severity=severity_norm,
        issues=issues,
        source_path=str(used_path),
    )


def _with_validation(outcome: PublishOutcome, status: Optional[str], issues: List[str]) -> PublishOutcome:
    return PublishOutcome(
        schema_version=outcome.schema_version,
        html_path=outcome.html_path,
        file_id=outcome.file_id,
        status=outcome.status,
        post_id=outcome.post_id,
        post_url=outcome.post_url,
        error=outcome.error,
        validation_status=status,
        validation_issues=issues,
    )


def run_publish(
    settings: PublishSettings,
    *,
    limit: Optional[int] = None,
) -> List[PublishOutcome]:
    ctx = new_run_context()
    logger.info(log_event(
        ctx,
        role="orchestrator",
        event="publish_start",
        module=logger.name,
        fields={"limit": limit},
    ))

    list_resp = list_html(ListHtmlRequest(schema_version="1.0", root_dir=settings.output_dir), ctx)
    max_n = limit if limit is not None else len(list_resp.html_paths)

    outcomes: List[PublishOutcome] = []
    processed = 0
    base_url = settings.wp.site_url.rstrip("/")
    auth_header = build_auth_header(
        username=settings.wp.username,
        app_password=settings.wp.app_password,
        bearer_token=settings.wp.bearer_token,
    )
    html_file_id_map: dict[str, str] = {}
    mapping_ctx = child_context(ctx, task_id="publish_file_id_map")
    try:
        html_file_id_map = _load_html_file_id_map(settings.reports_db, mapping_ctx)
    except Exception as exc:
        logger.info(log_event(
            mapping_ctx,
            role="orchestrator",
            event="publish_html_file_id_map_failed",
            module=logger.name,
            fields={"reports_db": settings.reports_db, "error": str(exc)},
        ))
        html_file_id_map = {}

    for html_path in list_resp.html_paths:
        if processed >= max_n:
            break

        file_ctx = child_context(ctx, task_id=html_path)
        preloaded_html: Optional[str] = None
        file_id = html_file_id_map.get(_canonical_html_path(html_path), "")
        if file_id:
            logger.info(log_event(
                file_ctx,
                role="orchestrator",
                event="publish_file_id_resolved",
                module=logger.name,
                fields={"html_path": html_path, "file_id": file_id, "source": "reports_db"},
            ))
        else:
            html_resp = read_text(ReadTextRequest(schema_version="1.0", path=html_path), file_ctx)
            preloaded_html = html_resp.content
            file_id = extract_file_id(preloaded_html) or ""
            if file_id:
                logger.info(log_event(
                    file_ctx,
                    role="orchestrator",
                    event="publish_file_id_resolved",
                    module=logger.name,
                    fields={"html_path": html_path, "file_id": file_id, "source": "html"},
                ))

        if not file_id:
            logger.info(log_event(
                file_ctx,
                role="orchestrator",
                event="publish_missing_file_id",
                module=logger.name,
                fields={"html_path": html_path},
            ))
            outcomes.append(PublishOutcome(
                schema_version="1.0",
                html_path=html_path,
                file_id=None,
                status="error",
                error="missing_file_id",
            ))
            continue

        state_row = state_get(
            StateGetRequest(schema_version="1.0", state_db=settings.state_db, file_id=file_id),
            file_ctx,
        )
        if not state_row:
            logger.info(log_event(
                file_ctx,
                role="orchestrator",
                event="publish_not_processed",
                module=logger.name,
                fields={"file_id": file_id},
            ))
            outcomes.append(PublishOutcome(
                schema_version="1.0",
                html_path=html_path,
                file_id=file_id,
                status="error",
                error="not_processed",
            ))
            continue

        if state_already_published(
            StatePublishCheckRequest(schema_version="1.0", state_db=settings.state_db, file_id=file_id),
            file_ctx,
        ):
            logger.info(log_event(
                file_ctx,
                role="orchestrator",
                event="publish_already_published",
                module=logger.name,
                fields={"file_id": file_id},
            ))
            outcomes.append(PublishOutcome(
                schema_version="1.0",
                html_path=html_path,
                file_id=file_id,
                status="skipped",
                error="already_published",
            ))
            continue

        validation_report = _load_validation_report(file_id, html_path, settings, file_ctx)
        validation_status = validation_report.status if validation_report else "missing"
        validation_issues = [issue.message for issue in validation_report.issues] if validation_report else []
        if settings.validation_policy == "block" and validation_status != "pass":
            logger.info(log_event(
                file_ctx,
                role="orchestrator",
                event="publish_validation_blocked",
                module=logger.name,
                fields={
                    "file_id": file_id,
                    "validation_status": validation_status,
                    "issues": validation_issues,
                },
            ))
            outcomes.append(PublishOutcome(
                schema_version="1.0",
                html_path=html_path,
                file_id=file_id,
                status="error",
                error="validation_failed",
                validation_status=validation_status,
                validation_issues=validation_issues,
            ))
            continue
        if validation_status != "pass":
            logger.info(log_event(
                file_ctx,
                role="orchestrator",
                event="publish_validation_warning",
                module=logger.name,
                fields={
                    "file_id": file_id,
                    "validation_status": validation_status,
                    "issues": validation_issues,
                    "policy": settings.validation_policy,
                },
            ))

        outcome: Optional[PublishOutcome] = None

        def _publish_attempt() -> PublishOutcome:
            nonlocal outcome
            lookup_resp = find_post_by_file_id(
                WordPressPostLookupRequest(
                    schema_version="1.0",
                    base_url=base_url,
                    auth_header=auth_header,
                    file_id=file_id,
                ),
                file_ctx,
            )
            if lookup_resp.found and lookup_resp.post_id and lookup_resp.link:
                logger.info(log_event(
                    file_ctx,
                    role="orchestrator",
                    event="publish_existing_post",
                    module=logger.name,
                    fields={"file_id": file_id, "post_id": lookup_resp.post_id},
                ))
                state_record_publish(
                    StatePublishRecordRequest(
                        schema_version="1.0",
                        state_db=settings.state_db,
                        file_id=file_id,
                        md5=state_row.md5,
                        wp_post_id=lookup_resp.post_id,
                        wp_post_url=lookup_resp.link,
                    ),
                    file_ctx,
                )
                outcome = PublishOutcome(
                    schema_version="1.0",
                    html_path=html_path,
                    file_id=file_id,
                    status="skipped",
                    post_id=lookup_resp.post_id,
                    post_url=lookup_resp.link,
                    error="already_exists",
                )
                return _with_validation(outcome, validation_status, validation_issues)

            outcome = publish_html(
                PublishRequest(
                    schema_version="1.0",
                    html_path=html_path,
                    file_id=file_id,
                    html_text=preloaded_html,
                ),
                settings,
                file_ctx,
            )
            outcome = _with_validation(outcome, validation_status, validation_issues)
            if outcome.status == "published" and outcome.post_id and outcome.post_url:
                state_record_publish(
                    StatePublishRecordRequest(
                        schema_version="1.0",
                        state_db=settings.state_db,
                        file_id=file_id,
                        md5=state_row.md5,
                        wp_post_id=outcome.post_id,
                        wp_post_url=outcome.post_url,
                    ),
                    file_ctx,
                )
            return outcome

        try:
            outcome = run_with_retry(
                step_name="publish_html",
                operation=_publish_attempt,
                ctx=file_ctx,
                logger=logger,
                module_name=logger.name,
                policy=RetryPolicy(retries=2, base_delay_seconds=1.0, backoff_step_seconds=1.0, jitter_seconds=0.25),
                retry_event="publish_retry",
                retry_fields_builder=lambda exc, attempt: {
                    "file_id": file_id,
                    "attempt": attempt + 1,
                    "code": exc.code if isinstance(exc, AppError) else "",
                },
                is_retryable=lambda exc: isinstance(exc, AppError) and exc.retryable,
                sleep_fn=time.sleep,
            )
        except AppError as exc:
            logger.info(log_event(
                file_ctx,
                role="orchestrator",
                event="publish_error",
                module=logger.name,
                fields={"file_id": file_id, "error": exc.message, "code": exc.code},
            ))
            outcome = PublishOutcome(
                schema_version="1.0",
                html_path=html_path,
                file_id=file_id,
                status="error",
                error=exc.message,
            )
            outcome = _with_validation(outcome, validation_status, validation_issues)
        except Exception as exc:
            logger.info(log_event(
                file_ctx,
                role="orchestrator",
                event="publish_error",
                module=logger.name,
                fields={"file_id": file_id, "error": str(exc)},
            ))
            outcome = PublishOutcome(
                schema_version="1.0",
                html_path=html_path,
                file_id=file_id,
                status="error",
                error=str(exc),
            )
            outcome = _with_validation(outcome, validation_status, validation_issues)

        if outcome is not None:
            outcomes.append(outcome)
            if outcome.status == "published":
                processed += 1
            continue
        logger.info(log_event(
            file_ctx,
            role="orchestrator",
            event="publish_error",
            module=logger.name,
            fields={"file_id": file_id, "error": "publish_failed"},
        ))
        outcomes.append(PublishOutcome(
            schema_version="1.0",
            html_path=html_path,
            file_id=file_id,
            status="error",
            error="publish_failed",
            validation_status=validation_status,
            validation_issues=validation_issues,
        ))

    logger.info(log_event(
        ctx,
        role="orchestrator",
        event="publish_complete",
        module=logger.name,
        fields={"published": processed},
    ))
    return outcomes
