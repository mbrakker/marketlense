from __future__ import annotations

import logging
from typing import List, Optional

from src.contracts.files import ListHtmlRequest, ReadTextRequest
from src.contracts.publish import PublishOutcome, PublishRequest, PublishSettings
from src.contracts.state import StateGetRequest, StatePublishCheckRequest, StatePublishRecordRequest
from src.services.file_service import list_html, read_text
from src.services.state_service import StateStore
from src.services.state_service import already_published as state_already_published
from src.services.state_service import get as state_get
from src.services.state_service import record_publish as state_record_publish
from src.generators.publish_generator import publish_html
from src.utils.html_utils import extract_file_id
from src.utils.logging import child_context, log_event, new_run_context

logger = logging.getLogger("market_lense.publish_orchestrator")


def run_publish(
    settings: PublishSettings,
    *,
    limit: Optional[int] = None,
) -> List[PublishOutcome]:
    ctx = new_run_context()
    log_event(
        logger,
        ctx,
        role="orchestrator",
        event="publish_start",
        fields={"limit": limit},
    )

    list_resp = list_html(ListHtmlRequest(schema_version="1.0", root_dir=settings.output_dir), ctx)
    max_n = limit if limit is not None else len(list_resp.html_paths)

    outcomes: List[PublishOutcome] = []
    processed = 0

    with StateStore(settings.state_db) as state:
        for html_path in list_resp.html_paths:
            if processed >= max_n:
                break

            file_ctx = child_context(ctx, task_id=html_path)
            html_resp = read_text(ReadTextRequest(schema_version="1.0", path=html_path), file_ctx)
            file_id = extract_file_id(html_resp.content)

            if not file_id:
                log_event(
                    logger,
                    file_ctx,
                    role="orchestrator",
                    event="publish_missing_file_id",
                    fields={"html_path": html_path},
                )
                outcomes.append(PublishOutcome(
                    schema_version="1.0",
                    html_path=html_path,
                    file_id=None,
                    status="error",
                    error="missing_file_id",
                ))
                continue

            state_row = state_get(state, StateGetRequest(schema_version="1.0", file_id=file_id), file_ctx)
            if not state_row:
                log_event(
                    logger,
                    file_ctx,
                    role="orchestrator",
                    event="publish_not_processed",
                    fields={"file_id": file_id},
                )
                outcomes.append(PublishOutcome(
                    schema_version="1.0",
                    html_path=html_path,
                    file_id=file_id,
                    status="error",
                    error="not_processed",
                ))
                continue

            if state_already_published(state, StatePublishCheckRequest(schema_version="1.0", file_id=file_id), file_ctx):
                log_event(
                    logger,
                    file_ctx,
                    role="orchestrator",
                    event="publish_already_published",
                    fields={"file_id": file_id},
                )
                outcomes.append(PublishOutcome(
                    schema_version="1.0",
                    html_path=html_path,
                    file_id=file_id,
                    status="skipped",
                    error="already_published",
                ))
                continue

            try:
                outcome = publish_html(
                    PublishRequest(schema_version="1.0", html_path=html_path, file_id=file_id),
                    settings,
                    file_ctx,
                )
                if outcome.status == "published" and outcome.post_id and outcome.post_url:
                    state_record_publish(
                        state,
                        StatePublishRecordRequest(
                            schema_version="1.0",
                            file_id=file_id,
                            md5=state_row.md5,
                            wp_post_id=outcome.post_id,
                            wp_post_url=outcome.post_url,
                        ),
                        file_ctx,
                    )
                outcomes.append(outcome)
                if outcome.status == "published":
                    processed += 1
            except Exception as exc:
                log_event(
                    logger,
                    file_ctx,
                    role="orchestrator",
                    event="publish_error",
                    fields={"file_id": file_id, "error": str(exc)},
                )
                outcomes.append(PublishOutcome(
                    schema_version="1.0",
                    html_path=html_path,
                    file_id=file_id,
                    status="error",
                    error=str(exc),
                ))

    log_event(
        logger,
        ctx,
        role="orchestrator",
        event="publish_complete",
        fields={"published": processed},
    )
    return outcomes
