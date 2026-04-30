from __future__ import annotations

from dataclasses import asdict
import hashlib
import logging
import time
import json
from pathlib import Path
from typing import List, Optional

from src.contracts.files import ListHtmlRequest, ReadTextRequest
from src.contracts.idempotency import (
    OrchestratorIdempotencyGetRequest,
    OrchestratorIdempotencyRecordRequest,
)
from src.contracts.publish import PublishOutcome, PublishRequest, PublishSettings
from src.contracts.run_context import RunContext
from src.contracts.state import (
    StateGetRequest,
    StatePublishCheckRequest,
    StatePublishRecordRequest,
)
from src.contracts.validation import ValidationReport
from src.contracts.wordpress import WordPressPostLookupRequest
from src.services.file_service import list_html, read_text
from src.services.state_service import already_published as state_already_published
from src.services.state_service import get as state_get
from src.services.state_service import record_publish as state_record_publish
from src.generators.publish_generator import publish_html
from src.orchestrators.publish_shared import (
    canonicalize_html_path,
    load_html_file_id_map,
)
from src.orchestrators.retry_orchestrator import RetryPolicy, run_with_retry
from src.services import idempotency_service
from src.services.wordpress_service import find_post_by_file_id
from src.utils.html_utils import extract_file_id
from src.utils.errors import AppError
from src.utils.logging import child_context, log_event, new_run_context
from src.utils.validation import parse_validation_report_payload
from src.utils.wp_auth import build_auth_header

logger = logging.getLogger("market_lense.publish_orchestrator")
_PUBLISH_IDEMPOTENCY_SCOPE = "publish_orchestrator.publish_html"


def _validation_paths(output_dir: str, file_id: str, html_path: str) -> list[Path]:
    """
    Validation path in the per-report folder: out/<report-slug>/report_analysis/validation.json.
    """
    _ = file_id
    html_slug = Path(html_path).stem
    return [Path(output_dir) / html_slug / "report_analysis" / "validation.json"]


def _load_validation_report(
    file_id: str, html_path: str, settings: PublishSettings, ctx
) -> Optional[ValidationReport]:
    candidates = _validation_paths(settings.output_dir, file_id, html_path)
    data = None
    used_path: Optional[Path] = None
    for path in candidates:
        try:
            resp = read_text(ReadTextRequest(schema_version="1.0", path=str(path)), ctx)
        except AppError as exc:
            logger.info(
                log_event(
                    ctx,
                    role="orchestrator",
                    event="publish_validation_missing",
                    module=logger.name,
                    fields={
                        "file_id": file_id,
                        "path": str(path),
                        "error": exc.message,
                    },
                )
            )
            continue
        try:
            data = json.loads(resp.content)
            used_path = path
            break
        except json.JSONDecodeError:
            logger.info(
                log_event(
                    ctx,
                    role="orchestrator",
                    event="publish_validation_parse_failed",
                    module=logger.name,
                    fields={"file_id": file_id, "path": str(path)},
                )
            )
            continue
    if data is None or used_path is None:
        return None
    return parse_validation_report_payload(data, source_path=str(used_path))


def _with_validation(
    outcome: PublishOutcome, status: Optional[str], issues: List[str]
) -> PublishOutcome:
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


def _publish_idempotency_key(*, file_id: str, post_type: str) -> str:
    return f"{post_type}:{file_id}"


def _publish_checksum(
    *,
    file_id: str,
    html_path: str,
    html_text: str,
    post_type: str,
    validation_status: str,
    validation_issues: List[str],
) -> str:
    html_sha256 = hashlib.sha256((html_text or "").encode("utf-8")).hexdigest()
    payload = {
        "schema_version": "1.0",
        "file_id": file_id,
        "html_path": html_path,
        "html_sha256": html_sha256,
        "post_type": post_type,
        "validation_status": validation_status,
        "validation_issues": list(validation_issues or []),
    }
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _lookup_publish_idempotency(
    *,
    settings: PublishSettings,
    file_id: str,
    post_type: str,
    checksum: str,
    ctx: RunContext,
) -> PublishOutcome | None:
    lookup = idempotency_service.get_outcome(
        OrchestratorIdempotencyGetRequest(
            schema_version="1.0",
            db_path=settings.state_db,
            scope=_PUBLISH_IDEMPOTENCY_SCOPE,
            idempotency_key=_publish_idempotency_key(
                file_id=file_id,
                post_type=post_type,
            ),
            input_checksum=checksum,
        ),
        ctx,
    )
    if not lookup.found or lookup.record is None:
        return None
    return PublishOutcome(**dict(lookup.record.outcome_payload or {}))


def _record_publish_idempotency(
    *,
    settings: PublishSettings,
    outcome: PublishOutcome,
    post_type: str,
    checksum: str,
    ctx: RunContext,
) -> None:
    if not outcome.file_id:
        return
    idempotency_service.record_outcome(
        OrchestratorIdempotencyRecordRequest(
            schema_version="1.0",
            db_path=settings.state_db,
            scope=_PUBLISH_IDEMPOTENCY_SCOPE,
            idempotency_key=_publish_idempotency_key(
                file_id=outcome.file_id,
                post_type=post_type,
            ),
            input_checksum=checksum,
            outcome_payload=asdict(outcome),
            artifact_references={
                "html_path": outcome.html_path,
                "status": outcome.status,
                "post_id": outcome.post_id,
                "post_url": outcome.post_url,
            },
        ),
        ctx,
    )


def run_publish(
    settings: PublishSettings,
    *,
    limit: Optional[int] = None,
    ctx: Optional[RunContext] = None,
) -> List[PublishOutcome]:
    root_ctx = ctx or new_run_context()
    logger.info(
        log_event(
            root_ctx,
            role="orchestrator",
            event="publish_start",
            module=logger.name,
            fields={"limit": limit},
        )
    )

    list_resp = list_html(
        ListHtmlRequest(schema_version="1.0", root_dir=settings.output_dir), root_ctx
    )
    max_n = limit if limit is not None else len(list_resp.html_paths)

    outcomes: List[PublishOutcome] = []
    attempted = 0
    published = 0
    base_url = settings.wp.site_url.rstrip("/")
    auth_header = build_auth_header(
        username=settings.wp.username,
        app_password=settings.wp.app_password,
        bearer_token=settings.wp.bearer_token,
    )
    logger.info(
        log_event(
            root_ctx,
            role="orchestrator",
            event="publish_auth_source",
            module=logger.name,
            fields={
                "source": "bearer_token"
                if settings.wp.bearer_token
                else "app_password"
            },
        )
    )
    html_file_id_map: dict[str, str] = {}
    mapping_ctx = child_context(root_ctx, task_id="publish_file_id_map")
    try:
        html_file_id_map = load_html_file_id_map(settings.reports_db, mapping_ctx)
    except Exception as exc:
        logger.info(
            log_event(
                mapping_ctx,
                role="orchestrator",
                event="publish_html_file_id_map_failed",
                module=logger.name,
                fields={"reports_db": settings.reports_db, "error": str(exc)},
            )
        )
        html_file_id_map = {}

    for html_path in list_resp.html_paths:
        if attempted >= max_n:
            break
        attempted += 1

        file_ctx = child_context(root_ctx, task_id=html_path)
        preloaded_html: Optional[str] = None
        file_id = html_file_id_map.get(canonicalize_html_path(html_path), "")
        if file_id:
            logger.info(
                log_event(
                    file_ctx,
                    role="orchestrator",
                    event="publish_file_id_resolved",
                    module=logger.name,
                    fields={
                        "html_path": html_path,
                        "file_id": file_id,
                        "source": "reports_db",
                    },
                )
            )
        else:
            html_resp = read_text(
                ReadTextRequest(schema_version="1.0", path=html_path), file_ctx
            )
            preloaded_html = html_resp.content
            file_id = extract_file_id(preloaded_html) or ""
            if file_id:
                logger.info(
                    log_event(
                        file_ctx,
                        role="orchestrator",
                        event="publish_file_id_resolved",
                        module=logger.name,
                        fields={
                            "html_path": html_path,
                            "file_id": file_id,
                            "source": "html",
                        },
                    )
                )

        if not file_id:
            logger.info(
                log_event(
                    file_ctx,
                    role="orchestrator",
                    event="publish_missing_file_id",
                    module=logger.name,
                    fields={"html_path": html_path},
                )
            )
            outcomes.append(
                PublishOutcome(
                    schema_version="1.0",
                    html_path=html_path,
                    file_id=None,
                    status="error",
                    error="missing_file_id",
                )
            )
            continue

        state_row = state_get(
            StateGetRequest(
                schema_version="1.0", state_db=settings.state_db, file_id=file_id
            ),
            file_ctx,
        )
        if not state_row:
            logger.info(
                log_event(
                    file_ctx,
                    role="orchestrator",
                    event="publish_not_processed",
                    module=logger.name,
                    fields={"file_id": file_id},
                )
            )
            outcomes.append(
                PublishOutcome(
                    schema_version="1.0",
                    html_path=html_path,
                    file_id=file_id,
                    status="error",
                    error="not_processed",
                )
            )
            continue

        validation_report = _load_validation_report(
            file_id, html_path, settings, file_ctx
        )
        validation_status = validation_report.status if validation_report else "missing"
        validation_issues = (
            [issue.message for issue in validation_report.issues]
            if validation_report
            else []
        )
        if preloaded_html is None:
            preloaded_html = read_text(
                ReadTextRequest(schema_version="1.0", path=html_path), file_ctx
            ).content
        publish_checksum = _publish_checksum(
            file_id=file_id,
            html_path=html_path,
            html_text=preloaded_html or "",
            post_type=settings.wp.post_type,
            validation_status=validation_status,
            validation_issues=validation_issues,
        )
        reused_outcome = _lookup_publish_idempotency(
            settings=settings,
            file_id=file_id,
            post_type=settings.wp.post_type,
            checksum=publish_checksum,
            ctx=file_ctx,
        )
        if reused_outcome is not None:
            logger.info(
                log_event(
                    file_ctx,
                    role="orchestrator",
                    event="publish_idempotency_reused",
                    module=logger.name,
                    fields={
                        "file_id": file_id,
                        "post_type": settings.wp.post_type,
                        "status": reused_outcome.status,
                        "post_id": reused_outcome.post_id,
                    },
                )
            )
            outcomes.append(reused_outcome)
            if reused_outcome.status == "published":
                published += 1
            continue
        if state_already_published(
            StatePublishCheckRequest(
                schema_version="1.0",
                state_db=settings.state_db,
                file_id=file_id,
                post_type=settings.wp.post_type,
            ),
            file_ctx,
        ):
            logger.info(
                log_event(
                    file_ctx,
                    role="orchestrator",
                    event="publish_already_published",
                    module=logger.name,
                    fields={"file_id": file_id},
                )
            )
            outcomes.append(
                PublishOutcome(
                    schema_version="1.0",
                    html_path=html_path,
                    file_id=file_id,
                    status="skipped",
                    error="already_published",
                )
            )
            continue
        if settings.validation_policy == "block" and validation_status != "pass":
            logger.info(
                log_event(
                    file_ctx,
                    role="orchestrator",
                    event="publish_validation_blocked",
                    module=logger.name,
                    fields={
                        "file_id": file_id,
                        "validation_status": validation_status,
                        "issues": validation_issues,
                    },
                )
            )
            outcomes.append(
                PublishOutcome(
                    schema_version="1.0",
                    html_path=html_path,
                    file_id=file_id,
                    status="error",
                    error="validation_failed",
                    validation_status=validation_status,
                    validation_issues=validation_issues,
                )
            )
            continue
        if validation_status != "pass":
            logger.info(
                log_event(
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
                )
            )

        outcome: Optional[PublishOutcome] = None

        def _publish_attempt() -> PublishOutcome:
            nonlocal outcome
            lookup_resp = find_post_by_file_id(
                WordPressPostLookupRequest(
                    schema_version="1.0",
                    base_url=base_url,
                    auth_header=auth_header,
                    file_id=file_id,
                    ssl_verify=settings.wp.ssl_verify,
                    ca_bundle_path=settings.wp.ca_bundle_path,
                    post_type=settings.wp.post_type,
                ),
                file_ctx,
            )
            if lookup_resp.found and lookup_resp.post_id and lookup_resp.link:
                logger.info(
                    log_event(
                        file_ctx,
                        role="orchestrator",
                        event="publish_existing_post",
                        module=logger.name,
                        fields={"file_id": file_id, "post_id": lookup_resp.post_id},
                    )
                )
                state_record_publish(
                    StatePublishRecordRequest(
                        schema_version="1.0",
                        state_db=settings.state_db,
                        file_id=file_id,
                        md5=state_row.md5,
                        wp_post_id=lookup_resp.post_id,
                        wp_post_url=lookup_resp.link,
                        post_type=settings.wp.post_type,
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
                    auth_header=auth_header,
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
                        post_type=settings.wp.post_type,
                    ),
                    file_ctx,
                )
            if outcome.status in {"published", "skipped"}:
                _record_publish_idempotency(
                    settings=settings,
                    outcome=outcome,
                    post_type=settings.wp.post_type,
                    checksum=publish_checksum,
                    ctx=file_ctx,
                )
            return outcome

        try:
            outcome = run_with_retry(
                step_name="publish_html",
                operation=_publish_attempt,
                ctx=file_ctx,
                logger=logger,
                module_name=logger.name,
                policy=RetryPolicy(
                    retries=2,
                    base_delay_seconds=1.0,
                    backoff_step_seconds=1.0,
                    jitter_seconds=0.25,
                ),
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
            logger.info(
                log_event(
                    file_ctx,
                    role="orchestrator",
                    event="publish_error",
                    module=logger.name,
                    fields={"file_id": file_id, "error": exc.message, "code": exc.code},
                )
            )
            outcome = PublishOutcome(
                schema_version="1.0",
                html_path=html_path,
                file_id=file_id,
                status="error",
                error=exc.message,
            )
            outcome = _with_validation(outcome, validation_status, validation_issues)
        except Exception as exc:
            logger.info(
                log_event(
                    file_ctx,
                    role="orchestrator",
                    event="publish_error",
                    module=logger.name,
                    fields={"file_id": file_id, "error": str(exc)},
                )
            )
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
                published += 1
            continue
        logger.info(
            log_event(
                file_ctx,
                role="orchestrator",
                event="publish_error",
                module=logger.name,
                fields={"file_id": file_id, "error": "publish_failed"},
            )
        )
        outcomes.append(
            PublishOutcome(
                schema_version="1.0",
                html_path=html_path,
                file_id=file_id,
                status="error",
                error="publish_failed",
                validation_status=validation_status,
                validation_issues=validation_issues,
            )
        )

    logger.info(
        log_event(
            root_ctx,
            role="orchestrator",
            event="publish_complete",
            module=logger.name,
            fields={"attempted": attempted, "published": published},
        )
    )
    return outcomes
