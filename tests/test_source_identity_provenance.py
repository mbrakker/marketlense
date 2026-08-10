from __future__ import annotations

import sqlite3
from dataclasses import asdict, replace

import pytest

from src.contracts.report_store import (
    ReportSourceIdentityGetRequest,
    ReportSourceRecordRequest,
    SourceIdentityObservation,
    SourceIdentityObservationRecordRequest,
    SourceIdentityResolution,
)
from src.services.report_store_service import (
    get_report_source_identity,
    record_report_source,
    record_source_identity_observation,
)
from src.utils.errors import AppError
from src.utils.logging import new_run_context


def _record_source(*, db_path: str, title: str, md5: str, url: str, ctx):
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
            source_page_url=url,
        ),
        ctx,
    )


def _observation(*, source_record_id: int, date: str, date_status: str):
    return SourceIdentityObservation(
        schema_version="1.0",
        source_record_id=source_record_id,
        canonical_title="Publisher Evidence Report",
        title_evidence_locator="terminal_evidence.final_page_title",
        publisher_name="Publisher Example",
        canonical_landing_page_url="https://publisher.example/reports/evidence",
        acquired_artifact_url="https://publisher.example/files/evidence.pdf",
        source_page_url="https://publisher.example/reports/evidence",
        publication_date=date,
        publication_date_status=date_status,
        publication_date_evidence_locator=(
            "json_ld[0].datePublished" if date_status == "verified" else ""
        ),
        discovered_at_utc="2026-07-17T08:00:00Z",
        retrieved_at_utc="2026-07-17T08:30:00Z",
        acquisition_route="browser_direct_pdf",
        content_hash="md5:source-md5-evidence",
        resolution_method="browser_terminal_evidence",
        identity_confidence="high",
    )


def test_source_identity_contract_round_trips() -> None:
    observation = _observation(
        source_record_id=4,
        date="2026-07-10",
        date_status="verified",
    )
    assert SourceIdentityObservation(**asdict(observation)) == observation

    resolution = SourceIdentityResolution(
        schema_version="1.0",
        source_record_id=4,
        source_identity_id="source:abc",
        canonical_title=observation.canonical_title,
        canonical_landing_page_url=observation.canonical_landing_page_url,
        publication_date=observation.publication_date,
        publication_date_status=observation.publication_date_status,
        retrieved_at_utc=observation.retrieved_at_utc,
        content_hash=observation.content_hash,
        resolution_method="publisher_evidence_preferred",
        identity_confidence="high",
        identity_status="resolved",
        source_metadata_hash="a" * 64,
        observation_count=1,
    )
    assert SourceIdentityResolution(**asdict(resolution)) == resolution


def test_source_identity_migrates_v18_and_preserves_conflicting_observations(
    tmp_path,
) -> None:
    ctx = new_run_context(task_id="source_identity_provenance")
    db_path = str(tmp_path / "reports.sqlite")
    source = _record_source(
        db_path=db_path,
        title="Evidence Report",
        md5="source-md5-evidence",
        url="https://publisher.example/reports/evidence",
        ctx=ctx,
    )

    # Simulate a v18 database: later additive tables and ledger entries are absent.
    with sqlite3.connect(db_path) as conn:
        conn.execute("DROP TABLE source_identity_resolutions")
        conn.execute("DROP TABLE source_identity_observations")
        conn.execute(
            "DELETE FROM schema_migration_ledger "
            "WHERE database_key='reports_db' AND version IN (19, 20)"
        )
        conn.execute(
            "UPDATE schema_version SET current_version=18 "
            "WHERE database_key='reports_db'"
        )

    legacy = get_report_source_identity(
        ReportSourceIdentityGetRequest(
            schema_version="1.0",
            db_path=db_path,
            report_title="Evidence Report",
            md5="source-md5-evidence",
        ),
        ctx,
    ).resolution
    assert legacy.identity_status == "legacy_unverified"
    assert legacy.publication_date == ""
    assert legacy.publication_date_status == "unknown"

    first = record_source_identity_observation(
        SourceIdentityObservationRecordRequest(
            schema_version="1.0",
            db_path=db_path,
            observation=_observation(
                source_record_id=source.record_id,
                date="2026-07-10",
                date_status="verified",
            ),
        ),
        ctx,
    )
    repeat = record_source_identity_observation(
        SourceIdentityObservationRecordRequest(
            schema_version="1.0",
            db_path=db_path,
            observation=_observation(
                source_record_id=source.record_id,
                date="2026-07-10",
                date_status="verified",
            ),
        ),
        ctx,
    )
    conflicting = record_source_identity_observation(
        SourceIdentityObservationRecordRequest(
            schema_version="1.0",
            db_path=db_path,
            observation=replace(
                _observation(
                    source_record_id=source.record_id,
                    date="2026-07-10",
                    date_status="verified",
                ),
                publication_date="2026-07-11",
                retrieved_at_utc="2026-07-18T08:30:00Z",
            ),
        ),
        ctx,
    )

    assert first.created is True
    assert repeat.created is False
    assert first.resolution.identity_status == "resolved"
    assert first.resolution.publication_date == "2026-07-10"
    assert first.resolution.source_metadata_hash
    assert conflicting.resolution.identity_status == "conflicting"
    assert conflicting.resolution.publication_date == ""
    assert conflicting.resolution.publication_date_status == "unknown"
    assert "publication_date_conflict" in conflicting.resolution.identity_issues

    with sqlite3.connect(db_path) as conn:
        observation_count = conn.execute(
            "SELECT COUNT(*) FROM source_identity_observations WHERE source_record_id=?",
            (source.record_id,),
        ).fetchone()[0]
        version = conn.execute(
            "SELECT current_version FROM schema_version WHERE database_key='reports_db'"
        ).fetchone()
    assert observation_count == 2
    assert version == (20,)


def test_source_identity_keeps_unknown_dates_unknown(tmp_path) -> None:
    ctx = new_run_context(task_id="source_identity_unknown_date")
    db_path = str(tmp_path / "reports.sqlite")
    source = _record_source(
        db_path=db_path,
        title="Undated Report",
        md5="source-md5-undated",
        url="https://publisher.example/reports/undated",
        ctx=ctx,
    )
    recorded = record_source_identity_observation(
        SourceIdentityObservationRecordRequest(
            schema_version="1.0",
            db_path=db_path,
            observation=replace(
                _observation(
                    source_record_id=source.record_id,
                    date="",
                    date_status="unknown",
                ),
                canonical_title="Undated Report",
                content_hash="md5:source-md5-undated",
            ),
        ),
        ctx,
    )

    assert recorded.resolution.identity_status == "resolved"
    assert recorded.resolution.publication_date == ""
    assert recorded.resolution.publication_date_status == "unknown"


def test_source_identity_reads_stored_publisher_when_resolution_is_incomplete(
    tmp_path,
) -> None:
    ctx = new_run_context(task_id="source_identity_stored_publisher_fallback")
    db_path = str(tmp_path / "reports.sqlite")
    source = _record_source(
        db_path=db_path,
        title="Publisher Evidence Report",
        md5="source-md5-stored-publisher",
        url="https://publisher.example/reports/evidence",
        ctx=ctx,
    )
    record_source_identity_observation(
        SourceIdentityObservationRecordRequest(
            schema_version="1.0",
            db_path=db_path,
            observation=replace(
                _observation(
                    source_record_id=source.record_id,
                    date="",
                    date_status="unknown",
                ),
                publisher_name="",
                content_hash="md5:source-md5-stored-publisher",
            ),
        ),
        ctx,
    )

    resolved = get_report_source_identity(
        ReportSourceIdentityGetRequest(
            schema_version="1.0",
            db_path=db_path,
            report_title="Publisher Evidence Report",
            md5="source-md5-stored-publisher",
        ),
        ctx,
    ).resolution

    assert resolved.publisher_name == "Publisher Example"
    assert resolved.resolution_method == "legacy_report_sources_publisher_fallback"


def test_source_identity_rejects_unsafe_public_urls(tmp_path) -> None:
    ctx = new_run_context(task_id="source_identity_unsafe_url")
    db_path = str(tmp_path / "reports.sqlite")
    source = _record_source(
        db_path=db_path,
        title="Unsafe URL Report",
        md5="source-md5-unsafe-url",
        url="https://publisher.example/reports/unsafe-url",
        ctx=ctx,
    )

    with pytest.raises(AppError) as exc_info:
        record_source_identity_observation(
            SourceIdentityObservationRecordRequest(
                schema_version="1.0",
                db_path=db_path,
                observation=replace(
                    _observation(
                        source_record_id=source.record_id,
                        date="",
                        date_status="unknown",
                    ),
                    acquired_artifact_url="javascript:alert(1)",
                    content_hash="md5:source-md5-unsafe-url",
                ),
            ),
            ctx,
        )

    assert exc_info.value.code == "source_identity_url_invalid"
    with sqlite3.connect(db_path) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM source_identity_observations"
        ).fetchone()[0]
    assert count == 0

    legacy_source = _record_source(
        db_path=db_path,
        title="Unsafe Legacy URL Report",
        md5="source-md5-unsafe-legacy-url",
        url="javascript:alert(1)",
        ctx=ctx,
    )
    legacy = get_report_source_identity(
        ReportSourceIdentityGetRequest(
            schema_version="1.0",
            db_path=db_path,
            report_title=legacy_source.report_name,
            md5=legacy_source.md5,
        ),
        ctx,
    ).resolution
    assert legacy.canonical_landing_page_url == ""
