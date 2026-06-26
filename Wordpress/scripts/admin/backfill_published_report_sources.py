#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlsplit

from src.contracts.config import ConfigLoadRequest
from src.contracts.report_store import (
    ReportMetadataGetRequest,
    ReportSourceLinkRequest,
    ReportSourceRecordRequest,
    ReportValueScoreRecordRequest,
    ReportValueScoreRequest,
)
from src.generators.report_value_generator import score_report_value
from src.services.config_service import load_settings
from src.services.report_store_service import (
    get_metadata,
    link_report_to_source,
    record_report_source,
    record_report_value_score,
)
from src.utils.logging import new_run_context

from ..wp_rest_common import WordPressRestClient, fail, load_rest_settings_from_env


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _published_file_ids(client: WordPressRestClient) -> list[str]:
    posts = client.get(
        "wp/v2/posts",
        params={
            "status": "publish",
            "per_page": 100,
            "context": "edit",
            "_fields": "meta",
        },
    )
    if not isinstance(posts, list):
        raise RuntimeError("WordPress published-post response must be a list")
    return sorted(
        {
            str((post.get("meta") or {}).get("ml_file_id", "")).strip()
            for post in posts
            if isinstance(post, dict)
            and str((post.get("meta") or {}).get("ml_file_id", "")).strip()
        }
    )


def main() -> None:
    try:
        client = WordPressRestClient(load_rest_settings_from_env())
        settings = load_settings(
            ConfigLoadRequest(schema_version="1.0", path=""),
            new_run_context(task_id="wordpress_published_report_source_backfill"),
        )
        ctx = new_run_context(task_id="wordpress_published_report_source_backfill")
        linked = 0
        unchanged = 0
        unavailable = 0
        for file_id in _published_file_ids(client):
            metadata = get_metadata(
                ReportMetadataGetRequest(
                    schema_version="1.0",
                    db_path=settings.reports_db,
                    file_id=file_id,
                ),
                ctx,
            )
            title = metadata.title.strip()
            publisher = str(metadata.publisher or "").strip()
            md5 = str(metadata.md5 or "").strip().lower()
            if not title or not publisher or not md5:
                unavailable += 1
                print(f"Skipped source backfill without required metadata: {file_id}")
                continue
            landing_page_url = (
                str(metadata.source_url or "").strip()
                or f"https://drive.google.com/file/d/{file_id}/view"
            )
            source_domain = (urlsplit(landing_page_url).hostname or "").lower()
            if not source_domain:
                unavailable += 1
                print(f"Skipped source backfill with invalid source URL: {file_id}")
                continue
            source_record = record_report_source(
                ReportSourceRecordRequest(
                    schema_version="1.0",
                    db_path=settings.reports_db,
                    source_domain=source_domain,
                    report_name=title,
                    landing_page_url=landing_page_url,
                    downloaded_at_utc=_utc_now_iso(),
                    md5=md5,
                    publisher_name=publisher,
                    source_page_url=landing_page_url,
                ),
                ctx,
            )
            score = score_report_value(
                ReportValueScoreRequest(
                    schema_version="1.0",
                    publisher_name=publisher,
                    source_domain=source_record.source_domain,
                    report_name=source_record.report_name,
                    landing_page_url=source_record.landing_page_url,
                    source_page_url=landing_page_url,
                    source_status="downloaded",
                    downloaded_at_utc=source_record.downloaded_at_utc,
                    md5=source_record.md5,
                    evaluation_year=datetime.now(timezone.utc).year,
                ),
                ctx,
            )
            record_report_value_score(
                ReportValueScoreRecordRequest(
                    schema_version="1.0",
                    db_path=settings.reports_db,
                    record_id=source_record.record_id,
                    score=score,
                    scored_at_utc=_utc_now_iso(),
                ),
                ctx,
            )
            response = link_report_to_source(
                ReportSourceLinkRequest(
                    schema_version="1.0",
                    db_path=settings.reports_db,
                    file_id=file_id,
                    source_md5=source_record.md5,
                ),
                ctx,
            )
            if response.linked:
                linked += 1
            else:
                unchanged += 1
        print(
            "Published report source backfill: "
            f"linked={linked} unchanged={unchanged} unavailable={unavailable}"
        )
    except RuntimeError as exc:
        fail(str(exc))


if __name__ == "__main__":
    main()
