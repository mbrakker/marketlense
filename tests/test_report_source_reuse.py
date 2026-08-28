from __future__ import annotations

from dataclasses import replace
import sqlite3

import pytest

from src.contracts.drive import DriveFile
from src.contracts.ingest import IngestOutcome
from src.contracts.report_store import (
    ReportMetadataUpsertRequest,
    ReportSourceIdentityGetRequest,
    ReportSourceReuseResolveRequest,
    ReportSourceReuseTelemetryRecord,
    ReportSourceReuseTelemetryRecordRequest,
)
from src.orchestrators.ingest_orchestrator import _existing_report_html
from src.orchestrators.report_pipeline_orchestrator import run_report_pipeline
from src.services.report_store_service import (
    get_report_source_identity,
    record_report_source_reuse_telemetry,
    resolve_report_source_reuse,
    upsert_metadata,
)
from src.utils.logging import new_run_context


def test_resolves_completed_package_for_same_canonical_source_through_new_file_id(
    tmp_path,
) -> None:
    """Removing canonical-source lookup would make this duplicate reprocess."""
    ctx = new_run_context(task_id="canonical_source_reuse")
    db_path = str(tmp_path / "reports.sqlite")
    html_path = tmp_path / "retained.html"
    html_path.write_text("<html>retained</html>", encoding="utf-8")
    canonical_identity = "source:4e92d530d9518247686dd0fdd4aa4e39"
    upsert_metadata(
        ReportMetadataUpsertRequest(
            schema_version="1.0",
            db_path=db_path,
            file_id="drive-original",
            title="Canonical report",
            publisher="Publisher Example",
            html_path=str(html_path),
            md5="a" * 32,
            source_identity_id=canonical_identity,
            source_metadata_hash="b" * 64,
            source_identity_status="resolved",
        ),
        ctx,
    )

    reuse = resolve_report_source_reuse(
        ReportSourceReuseResolveRequest(
            schema_version="1.0",
            db_path=db_path,
            incoming_file_id="email-attachment-42",
            incoming_source_reference="email:message-42/attachment-1",
            canonical_source_identity=canonical_identity,
            canonical_source_identity_status="resolved",
            source_content_hash="md5:" + "a" * 32,
        ),
        ctx,
    )

    assert reuse.decision == "reuse"
    assert reuse.report_id == "drive-original"
    assert reuse.html_path == str(html_path)
    assert reuse.highest_reusable_checkpoint == "render_complete"


def test_ingest_html_lookup_reuses_canonical_package_before_acquisition(
    tmp_path, ingest_settings
) -> None:
    """Removing source-identity lookup would make an alternate Drive file download."""
    ctx = new_run_context(task_id="canonical_source_ingest_reuse")
    db_path = str(tmp_path / "reports.sqlite")
    html_path = tmp_path / "retained.html"
    html_path.write_text("<html>retained</html>", encoding="utf-8")
    md5 = "a" * 32
    upsert_metadata(
        ReportMetadataUpsertRequest(
            schema_version="1.0",
            db_path=db_path,
            file_id="drive-original",
            title="Canonical report",
            publisher="Publisher Example",
            html_path=str(html_path),
            md5=md5,
        ),
        ctx,
    )
    identity = get_report_source_identity(
        ReportSourceIdentityGetRequest(
            schema_version="1.0",
            db_path=db_path,
            report_title="Canonical report",
            md5=md5,
        ),
        ctx,
    ).resolution
    upsert_metadata(
        ReportMetadataUpsertRequest(
            schema_version="1.0",
            db_path=db_path,
            file_id="drive-original",
            title="Canonical report",
            publisher="Publisher Example",
            html_path=str(html_path),
            md5=md5,
            source_identity_id=identity.source_identity_id,
            source_metadata_hash=identity.source_metadata_hash,
            source_identity_status="resolved",
        ),
        ctx,
    )

    duplicate = DriveFile(
        schema_version="1.0",
        file_id="drive-mirror",
        name="mirror.pdf",
        modified_time=None,
        md5_checksum=md5,
    )
    settings = replace(ingest_settings, reports_db=db_path)

    package = _existing_report_html(duplicate, md5, settings, ctx)
    assert package is not None
    assert package.html_path == str(html_path)
    assert package.report_id == "drive-original"


@pytest.mark.parametrize(
    "incoming_reference",
    [
        "drive:mirror-file",
        "email:message-42/attachment-1",
        "file:C:/retained/report-copy.pdf",
    ],
)
def test_exact_source_reuse_is_route_independent(tmp_path, incoming_reference) -> None:
    """Changing only the acquisition reference must not create a second package."""
    ctx = new_run_context(task_id="canonical_source_route_reuse")
    db_path = str(tmp_path / "reports.sqlite")
    html_path = tmp_path / "retained.html"
    html_path.write_text("<html>retained</html>", encoding="utf-8")
    upsert_metadata(
        ReportMetadataUpsertRequest(
            schema_version="1.0",
            db_path=db_path,
            file_id="drive-original",
            title="Canonical report",
            publisher="Publisher Example",
            html_path=str(html_path),
            md5="a" * 32,
            source_identity_id="source:exact",
            source_metadata_hash="b" * 64,
            source_identity_status="resolved",
        ),
        ctx,
    )

    response = resolve_report_source_reuse(
        ReportSourceReuseResolveRequest(
            schema_version="1.0",
            db_path=db_path,
            incoming_file_id="alternate-reference",
            incoming_source_reference=incoming_reference,
            canonical_source_identity="source:exact",
            canonical_source_identity_status="resolved",
            source_content_hash="md5:" + "a" * 32,
        ),
        ctx,
    )

    assert (response.decision, response.report_id) == ("reuse", "drive-original")


def test_source_reuse_persists_bounded_decision_telemetry(tmp_path) -> None:
    """Removing telemetry persistence would leave duplicate suppression unauditable."""
    ctx = new_run_context(task_id="canonical_source_reuse_telemetry")
    db_path = str(tmp_path / "reports.sqlite")
    html_path = tmp_path / "retained.html"
    html_path.write_text("<html>retained</html>", encoding="utf-8")
    upsert_metadata(
        ReportMetadataUpsertRequest(
            schema_version="1.0",
            db_path=db_path,
            file_id="drive-original",
            title="Canonical report",
            publisher="Publisher Example",
            html_path=str(html_path),
            md5="a" * 32,
            source_identity_id="source:exact",
            source_identity_status="resolved",
        ),
        ctx,
    )

    reuse = resolve_report_source_reuse(
        ReportSourceReuseResolveRequest(
            schema_version="1.0",
            db_path=db_path,
            incoming_file_id="email-attachment-42",
            incoming_source_reference="email:message-42/attachment-1",
            canonical_source_identity="source:exact",
            canonical_source_identity_status="resolved",
            source_content_hash="md5:" + "a" * 32,
        ),
        ctx,
    )
    record_report_source_reuse_telemetry(
        ReportSourceReuseTelemetryRecordRequest(
            schema_version="1.0",
            db_path=db_path,
            record=ReportSourceReuseTelemetryRecord(
                schema_version="1.0",
                incoming_file_id="email-attachment-42",
                incoming_source_reference="email:message-42/attachment-1",
                canonical_source_identity="source:exact",
                source_content_hash="md5:" + "a" * 32,
                matched_report_id=reuse.report_id,
                matched_source_metadata_hash=reuse.source_metadata_hash,
                decision=reuse.decision,
                decision_reason=reuse.reason,
                highest_reused_checkpoint="render_complete",
                reused_stages=(
                    "acquisition",
                    "source_prepared",
                    "selection_complete",
                    "analysis_complete",
                    "render_complete",
                ),
                acquisition_actions_avoided=0,
                browser_launches_avoided=0,
                pdf_parse_avoided=0,
                ocr_avoided=0,
                extraction_avoided=0,
                vector_work_avoided=0,
            ),
        ),
        ctx,
    )

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT incoming_file_id, incoming_source_reference_hash,
                   canonical_source_identity, matched_report_id, decision,
                   decision_reason, highest_reused_checkpoint,
                   reused_stages_json, regenerated_stages_json,
                   acquisition_actions_avoided, browser_launches_avoided,
                   pdf_parse_avoided, ocr_avoided, extraction_avoided,
                   vector_work_avoided,
                   model_calls_avoided_status, tokens_avoided_status,
                   estimated_cost_avoided_status, model_calls_avoided,
                   input_tokens_avoided, output_tokens_avoided,
                   estimated_cost_avoided_usd
            FROM report_source_reuse_telemetry
            """
        ).fetchone()
    assert row == (
        "email-attachment-42",
        row[1],
        "source:exact",
        "drive-original",
        "reuse",
        "canonical_identity_and_content_hash_match",
        "render_complete",
        '["acquisition","source_prepared","selection_complete","analysis_complete","render_complete"]',
        "[]",
        0,
        0,
        0,
        0,
        0,
        0,
        "unavailable",
        "unavailable",
        "unavailable",
        0,
        0,
        0,
        0.0,
    )
    assert len(row[1]) == 64


def test_source_reuse_fails_closed_for_changed_or_unproven_source(tmp_path) -> None:
    """A metadata lookalike or changed bytes must still enter normal processing."""
    ctx = new_run_context(task_id="canonical_source_reuse_fail_closed")
    db_path = str(tmp_path / "reports.sqlite")
    upsert_metadata(
        ReportMetadataUpsertRequest(
            schema_version="1.0",
            db_path=db_path,
            file_id="drive-original",
            title="Same title",
            publisher="Same publisher",
            html_path=str(tmp_path / "retained.html"),
            md5="a" * 32,
            source_identity_id="source:original",
            source_identity_status="resolved",
        ),
        ctx,
    )

    changed = resolve_report_source_reuse(
        ReportSourceReuseResolveRequest(
            schema_version="1.0",
            db_path=db_path,
            incoming_file_id="changed-file",
            incoming_source_reference="drive:changed-file",
            canonical_source_identity="source:original",
            canonical_source_identity_status="resolved",
            source_content_hash="md5:" + "c" * 32,
        ),
        ctx,
    )
    lookalike = resolve_report_source_reuse(
        ReportSourceReuseResolveRequest(
            schema_version="1.0",
            db_path=db_path,
            incoming_file_id="same-title-different-bytes",
            incoming_source_reference="email:message-42/attachment-2",
            canonical_source_identity="source:different",
            canonical_source_identity_status="resolved",
            source_content_hash="md5:" + "a" * 32,
        ),
        ctx,
    )
    unknown = resolve_report_source_reuse(
        ReportSourceReuseResolveRequest(
            schema_version="1.0",
            db_path=db_path,
            incoming_file_id="identity-missing",
            incoming_source_reference="file:unknown.pdf",
            canonical_source_identity="",
            source_content_hash="",
        ),
        ctx,
    )

    assert changed.decision == "process"
    assert lookalike.decision == "process"
    assert unknown.reason == "canonical_source_identity_missing"


def test_direct_pipeline_route_runs_canonical_owner_checkpoint(
    tmp_path, ingest_settings
) -> None:
    """Removing the owner substitution would invoke report work under the duplicate ID."""
    ctx = replace(
        new_run_context(task_id="canonical_source_pipeline_reuse"),
        admission_decision_hash="admission-proof",
    )
    db_path = str(tmp_path / "reports.sqlite")
    html_path = tmp_path / "retained.html"
    html_path.write_text("<html>retained</html>", encoding="utf-8")
    md5 = "a" * 32
    upsert_metadata(
        ReportMetadataUpsertRequest(
            schema_version="1.0",
            db_path=db_path,
            file_id="drive-original",
            title="Canonical report",
            publisher="Publisher Example",
            html_path=str(html_path),
            md5=md5,
        ),
        ctx,
    )
    identity = get_report_source_identity(
        ReportSourceIdentityGetRequest(
            schema_version="1.0",
            db_path=db_path,
            report_title="Canonical report",
            md5=md5,
        ),
        ctx,
    ).resolution
    upsert_metadata(
        ReportMetadataUpsertRequest(
            schema_version="1.0",
            db_path=db_path,
            file_id="drive-original",
            title="Canonical report",
            publisher="Publisher Example",
            html_path=str(html_path),
            md5=md5,
            source_identity_id=identity.source_identity_id,
            source_metadata_hash=identity.source_metadata_hash,
            source_identity_status="resolved",
        ),
        ctx,
    )
    calls: list[tuple[str, str]] = []

    def _generate(
        file, _path, _settings, checksum, _ctx, *, resume_from_stage=None, **_kwargs
    ):
        calls.append((file.file_id, resume_from_stage or ""))
        return IngestOutcome(
            schema_version="1.0",
            file_id=file.file_id,
            name=file.name or file.file_id,
            md5=checksum,
            html_path=str(html_path),
            status="processed",
        )

    result = run_report_pipeline(
        DriveFile(
            schema_version="1.0",
            file_id="email-attachment-42",
            name="attachment.pdf",
            modified_time=None,
            md5_checksum=md5,
        ),
        local_pdf_path=str(tmp_path / "attachment.pdf"),
        settings=replace(ingest_settings, reports_db=db_path),
        md5=md5,
        ctx=ctx,
        retries=0,
        generate_report_fn=_generate,
        execution_plan_mode="disabled",
    )

    assert calls == [("drive-original", "latest_safe")]
    assert result.file_id == "email-attachment-42"
