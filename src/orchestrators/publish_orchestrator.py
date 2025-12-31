from __future__ import annotations

import logging
import time
from typing import List, Optional

from src.contracts.files import ListHtmlRequest, ReadTextRequest
from src.contracts.publish import PublishOutcome, PublishRequest, PublishSettings
from src.contracts.state import StateGetRequest, StatePublishCheckRequest, StatePublishRecordRequest
from src.contracts.wordpress import WordPressPostLookupRequest
from src.services.file_service import list_html, read_text
from src.services.state_service import already_published as state_already_published
from src.services.state_service import get as state_get
from src.services.state_service import record_publish as state_record_publish
from src.generators.publish_generator import publish_html
from src.services.wordpress_service import find_post_by_file_id
from src.utils.html_utils import extract_file_id
from src.utils.errors import AppError
from src.utils.logging import child_context, log_event, new_run_context
from src.utils.wp_auth import build_auth_header

logger = logging.getLogger("market_lense.publish_orchestrator")


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

    for html_path in list_resp.html_paths:
        if processed >= max_n:
            break

        file_ctx = child_context(ctx, task_id=html_path)
        html_resp = read_text(ReadTextRequest(schema_version="1.0", path=html_path), file_ctx)
        file_id = extract_file_id(html_resp.content)

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

        retries = 2
        outcome: Optional[PublishOutcome] = None
        for attempt in range(retries + 1):
            try:
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
                    break

                outcome = publish_html(
                    PublishRequest(schema_version="1.0", html_path=html_path, file_id=file_id),
                    settings,
                    file_ctx,
                )
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
                break
            except AppError as exc:
                if not exc.retryable or attempt >= retries:
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
                    break
                logger.info(log_event(
                    file_ctx,
                    role="orchestrator",
                    event="publish_retry",
                    module=logger.name,
                    fields={"file_id": file_id, "attempt": attempt + 1, "code": exc.code},
                ))
                time.sleep(1 + attempt)
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
                break

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
        ))

    logger.info(log_event(
        ctx,
        role="orchestrator",
        event="publish_complete",
        module=logger.name,
        fields={"published": processed},
    ))
    return outcomes
