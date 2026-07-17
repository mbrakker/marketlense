from __future__ import annotations

from dataclasses import replace

from src.contracts.report_store import (
    ReportPublicationMetadataGetRequest,
    ReportSourceIdentityResolveRequest,
    ReportSourceRecordRequest,
    SourcePublicationMetadataExtractionRequest,
    SourcePublicationMetadataUpsertRequest,
)
from src.services.browser_report_download_service import (
    extract_source_publication_metadata,
)
from src.services.report_store_service import (
    get_report_publication_metadata,
    record_report_source,
    resolve_report_source_identity,
    upsert_source_publication_metadata,
)
from src.utils.logging import new_run_context


def _source_record(*, db_path: str, title: str, md5: str, url: str, ctx):
    return record_report_source(
        ReportSourceRecordRequest(
            schema_version="1.0",
            db_path=db_path,
            source_domain="publisher.example",
            report_name=title,
            landing_page_url=url,
            downloaded_at_utc="2026-07-17T08:30:00Z",
            md5=md5,
            publisher_name="Publisher Example",
        ),
        ctx,
    )


def test_extractor_preserves_source_precision_and_detects_conflicts() -> None:
    ctx = new_run_context(task_id="source_publication_extraction")
    verified = extract_source_publication_metadata(
        SourcePublicationMetadataExtractionRequest(
            schema_version="1.0",
            source_url="https://publisher.example/report",
            retrieved_at_utc="2026-07-17T08:30:00Z",
            html=(
                '<script type="application/ld+json">'
                '{"datePublished":"2026-07"}'
                "</script>"
            ),
        ),
        ctx,
    ).metadata
    assert verified.evidence_status == "verified"
    assert verified.publication_date == "2026-07"
    assert verified.publication_date_precision == "month"
    assert verified.evidence_kind == "json_ld_date_published"
    assert verified.evidence_value_hash

    meta_tag = extract_source_publication_metadata(
        SourcePublicationMetadataExtractionRequest(
            schema_version="1.0",
            source_url="https://publisher.example/report",
            retrieved_at_utc="2026-07-17T08:30:00Z",
            html=(
                '<meta property="article:published_time" '
                'content="2026-07-17T06:30:00+00:00">'
            ),
        ),
        ctx,
    ).metadata
    assert meta_tag.evidence_status == "verified"
    assert meta_tag.publication_date == "2026-07-17"
    assert meta_tag.evidence_kind == "open_graph_article_published_time"

    equivalent = extract_source_publication_metadata(
        SourcePublicationMetadataExtractionRequest(
            schema_version="1.0",
            source_url="https://publisher.example/report",
            retrieved_at_utc="2026-07-17T08:30:00Z",
            html=(
                '<meta property="article:published_time" '
                'content="2026-07-17T06:30:00+00:00">'
                '<meta name="publication_date" content="2026-07-17">'
            ),
        ),
        ctx,
    ).metadata
    assert equivalent.evidence_status == "verified"
    assert equivalent.contradiction_status == "none"

    invalid = extract_source_publication_metadata(
        SourcePublicationMetadataExtractionRequest(
            schema_version="1.0",
            source_url="https://publisher.example/report",
            retrieved_at_utc="2026-07-17T08:30:00Z",
            html='<meta name="publication_date" content="2026-13-99">',
        ),
        ctx,
    ).metadata
    assert invalid.evidence_status == "invalid"

    unknown = extract_source_publication_metadata(
        SourcePublicationMetadataExtractionRequest(
            schema_version="1.0",
            source_url="https://publisher.example/report-2026-07.pdf",
            retrieved_at_utc="2026-07-17T08:30:00Z",
            html="<title>Report 2026-07</title><p>Downloaded today</p>",
        ),
        ctx,
    ).metadata
    assert unknown.evidence_status == "unknown"
    assert unknown.publication_date == ""

    conflicting = extract_source_publication_metadata(
        SourcePublicationMetadataExtractionRequest(
            schema_version="1.0",
            source_url="https://publisher.example/report",
            retrieved_at_utc="2026-07-17T08:30:00Z",
            html=(
                '<meta property="article:published_time" content="2026-01-01T00:00:00Z">'
                '<meta name="publication_date" content="2026-02-01">'
            ),
        ),
        ctx,
    ).metadata
    assert conflicting.evidence_status == "conflicting"
    assert conflicting.contradiction_status == "conflicting"


def test_publication_metadata_round_trip_is_md5_bound_and_title_ambiguity_fails_closed(
    tmp_path,
) -> None:
    ctx = new_run_context(task_id="source_publication_round_trip")
    db_path = str(tmp_path / "reports.sqlite")
    source = _source_record(
        db_path=db_path,
        title="Shared Report",
        md5="source-md5-a",
        url="https://publisher.example/a",
        ctx=ctx,
    )
    _source_record(
        db_path=db_path,
        title="Shared Report",
        md5="source-md5-b",
        url="https://publisher.example/b",
        ctx=ctx,
    )
    extracted = extract_source_publication_metadata(
        SourcePublicationMetadataExtractionRequest(
            schema_version="1.0",
            source_url="https://publisher.example/a",
            retrieved_at_utc="2026-07-17T08:30:00Z",
            html='<script type="application/ld+json">{"datePublished":"2026-07-17"}</script>',
        ),
        ctx,
    ).metadata
    stored = upsert_source_publication_metadata(
        SourcePublicationMetadataUpsertRequest(
            schema_version="1.0",
            db_path=db_path,
            metadata=replace(
                extracted,
                source_record_id=source.record_id,
                source_identity=f"report_source:{source.record_id}",
            ),
        ),
        ctx,
    )
    repeat = upsert_source_publication_metadata(
        SourcePublicationMetadataUpsertRequest(
            schema_version="1.0",
            db_path=db_path,
            metadata=replace(
                extracted,
                source_record_id=source.record_id,
                source_identity=f"report_source:{source.record_id}",
            ),
        ),
        ctx,
    )
    resolved = get_report_publication_metadata(
        ReportPublicationMetadataGetRequest(
            schema_version="1.0",
            db_path=db_path,
            report_title="Shared Report",
            md5="source-md5-a",
        ),
        ctx,
    )
    ambiguous_identity = resolve_report_source_identity(
        ReportSourceIdentityResolveRequest(
            schema_version="1.0",
            db_path=db_path,
            report_title="Shared Report",
        ),
        ctx,
    )

    assert stored.changed is True
    assert repeat.changed is False
    assert resolved.resolution_source == "md5"
    assert resolved.metadata.source_record_id == source.record_id
    assert resolved.metadata.publication_date == "2026-07-17"
    assert resolved.metadata.evidence_status == "verified"
    assert ambiguous_identity.resolution_source == "unresolved"
    assert ambiguous_identity.source_url == ""
