from __future__ import annotations

import sqlite3
from dataclasses import asdict, replace

import pytest

from src.contracts.analytics_projection import (
    AnalyticsProjectionBuildRequest,
    AnalyticsProjectionFailureRequest,
    AnalyticsProjectionRunRequest,
    AnalyticsProjectionUpsertRequest,
    PROJECTION_SCHEMA_VERSION,
    PROJECTION_VERSION,
)
from src.contracts.drive import DriveFile
from src.contracts.ingest import IngestSettings
from src.contracts.pdf_text import PdfTextExtractResponse
from src.contracts.pdf_utils import PdfInfoResponse
from src.contracts.report_generation import (
    ReportAnalysisState,
    ReportRuntimeState,
    ReportSelectionState,
    ReportSourceState,
)
from src.contracts.report_models import Figure, Quote, ReportFigureAsset, ReportPayload
from src.contracts.run_context import RunContext
from src.contracts.validation import ValidationReport
from src.generators.analytics_projection_generator import build_projection
from src.generators.report_generation_shared import derive_title, report_slug
from src.orchestrators.analytics_projection_orchestrator import (
    AnalyticsProjectionDependencies,
    run_analytics_projection,
)
from src.services.analytics_store_service import (
    record_projection_failure,
    upsert_projection,
)
from src.utils.errors import AppError


def _payload() -> ReportPayload:
    return ReportPayload(
        schema_version="1.1",
        tldr="Short summary",
        title="Future Markets 2026",
        insights=["A", "B", "C", "D", "E"],
        quote=Quote(schema_version="1.0", text="A useful quote", author="Analyst"),
        figure=Figure(schema_version="1.0", title="Adoption", evidence="Survey"),
        commentary="Executive commentary",
        source="https://example.com/report",
        publisher="Acme Research",
        taxonomy=["AI", "Enterprise"],
        categories=["market-intelligence"],
        region="US",
        time_period="2026",
        _text_density=123.5,
        _text_not_available=False,
        _figure_assets=[
            ReportFigureAsset(
                schema_version="1.0",
                image_path="figures/chart-1.png",
                page=2,
                candidate_id="fig-1",
                kind="chart",
                is_primary=True,
                detected_caption="Detected adoption chart",
                generated_caption="Generated adoption chart caption",
                display_caption="Adoption chart caption",
                caption_source="generated",
            )
        ],
    )


def _runtime(settings: IngestSettings, ctx: RunContext) -> ReportRuntimeState:
    file = DriveFile(
        schema_version="1.0",
        file_id="drive-file-1",
        name="future-markets.pdf",
        modified_time=None,
        md5_checksum="source-md5",
    )
    return ReportRuntimeState(
        schema_version="1.0",
        file=file,
        local_pdf_path="C:/tmp/future-markets.pdf",
        settings=settings,
        md5="source-md5",
        ctx=ctx,
        file_name=file.name,
        report_name=report_slug(file.name, file.file_id),
        report_title=derive_title(file.name),
        analysis_mode="vector_store",
        analysis_modes=["vector_store"],
        report_worker_limit=1,
        parallel_within_file=False,
    )


def _analysis_state(
    settings: IngestSettings,
    ctx: RunContext,
    *,
    title: str = "Future Markets 2026",
) -> ReportAnalysisState:
    runtime = _runtime(settings, ctx)
    payload = replace(_payload(), title=title)
    source = ReportSourceState(
        schema_version="1.0",
        runtime=runtime,
        info_response=PdfInfoResponse(
            schema_version="1.0",
            path=runtime.local_pdf_path,
            page_count=5,
            metadata={"Author": "Acme"},
        ),
        contents_page_number=1,
        contents_heading="Contents",
        contents_image="contents.png",
        text_response=PdfTextExtractResponse(
            schema_version="1.0",
            text="body text",
            pages_extracted=2,
            char_count=247,
            text_density=123.5,
        ),
        text_status={"schema_version": "1.0", "not_available": False},
        text_validation_status="pass",
        text_validation_reason="",
        text_validation_pages=[1, 2],
        payload=payload,
    )
    selection = ReportSelectionState(
        schema_version="1.0",
        runtime=runtime,
        source=source,
        payload=payload,
        rank_usage={"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
        candidate_count=1,
    )
    evidence_packs = {
        "doc_map": {
            "doc_map": {
                "_cache": {"model": "gpt-5-mini"},
                "sections": [
                    {
                        "id": "s1",
                        "title": "Market Overview",
                        "summary": "Demand is expanding.",
                        "key_points": ["Budget growth", "Vendor consolidation"],
                        "pages": [1, 2],
                    }
                ],
            }
        },
        "findings": {
            "findings": [
                {
                    "id": "f1",
                    "text": "Budgets are increasing.",
                    "evidence": "Survey respondents reported larger budgets.",
                    "confidence": "high",
                    "pages": [2],
                }
            ]
        },
        "key_metrics": {
            "key_metrics": [
                {
                    "id": "m1",
                    "metric": "Budget growth",
                    "value": "18",
                    "unit": "%",
                    "evidence_id": "f1",
                    "pages": [2],
                }
            ]
        },
        "taxonomy": {
            "taxonomy": ["AI", "Enterprise"],
            "primary_tags": ["AI"],
            "secondary_tags": ["Enterprise"],
        },
        "context_category_fit": {
            "selected_category_ids": ["market-intelligence"],
            "category_fits": [
                {
                    "category_id": "market-intelligence",
                    "label": "Market Intelligence",
                    "fit_score": 0.91,
                    "decision": "primary",
                    "evidence_sections": ["Market Overview"],
                }
            ],
        },
    }
    artifacts = {
        "summary": {
            "tldr": "Short summary",
            "executive_summary": "Executive summary",
            "claim_evidence_map": [
                {
                    "claim": "Demand is expanding.",
                    "evidence_id": "f1",
                    "evidence": "Survey respondents reported larger budgets.",
                    "pages": [2],
                }
            ],
        },
        "quotes_final": [
            {
                "id": "q1",
                "text": "We are investing more in automation.",
                "speaker": "CIO",
                "citation": "p. 3",
                "page": 3,
                "evidence_id": "q1",
            }
        ],
    }
    return ReportAnalysisState(
        schema_version="1.0",
        runtime=runtime,
        source=source,
        selection=selection,
        payload=payload,
        normalized_payload=payload,
        data_dict=payload.to_dict(),
        evidence_paths={"doc_map": "doc_map.json"},
        evidence_packs=evidence_packs,
        artifacts_payload=artifacts,
        validation_report=ValidationReport(
            schema_version="1.1",
            status="pass",
            severity="pass",
            issues=[],
            source_path="validation.json",
        ),
        category_labels=["Market Intelligence"],
        vector_store_id="vs_1",
        vector_store_status="completed",
        indexed_at_utc="2026-04-22T00:00:00Z",
        openai_file_id="file_1",
    )


def _batch(settings: IngestSettings, ctx: RunContext):
    return build_projection(
        AnalyticsProjectionBuildRequest(
            schema_version=PROJECTION_SCHEMA_VERSION,
            analysis=_analysis_state(settings, ctx),
            rendered_html_path="out/report.html",
            generated_at_utc="2026-04-22T12:00:00Z",
        )
    )


def _fetch_one(db_path: str, sql: str, params: tuple = ()) -> sqlite3.Row:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(sql, params).fetchone()
    assert row is not None
    return row


def test_projection_generator_stable_ids_and_vector_serialization(
    ingest_settings: IngestSettings,
    run_context: RunContext,
    assert_no_defaulted_required_fields,
) -> None:
    first = _batch(ingest_settings, run_context)
    second = _batch(ingest_settings, run_context)

    assert first.report.report_id == "drive-file-1"
    assert "source_file_id" not in asdict(first.report)
    assert first.sections[0].section_uid == second.sections[0].section_uid
    assert first.findings[0].finding_uid == second.findings[0].finding_uid
    assert first.metrics[0].metric_uid == second.metrics[0].metric_uid
    assert first.categories[0].fit_score == 0.91
    assert first.categories[0].decision == "primary"
    assert first.report.projection_version == PROJECTION_VERSION
    assert_no_defaulted_required_fields(first.report)

    queue_by_type = {row.entity_type: row for row in first.vector_queue}
    assert {
        "report_summary",
        "section",
        "finding",
        "claim",
        "metric",
        "quote",
        "figure_caption",
    }.issubset(queue_by_type)
    finding_queue = queue_by_type["finding"]
    assert finding_queue.embedding_status == "pending"
    assert len(finding_queue.content_hash) == 64
    assert (
        finding_queue.content_hash
        == {row.entity_type: row for row in second.vector_queue}["finding"].content_hash
    )
    assert finding_queue.content_class == "evidence"
    assert "Budgets are increasing" in finding_queue.text_payload
    assert finding_queue.metadata["source_pack"] == "findings"
    assert "source_file_id" not in finding_queue.metadata


def test_projection_store_idempotent_upsert_and_report_scoped_stale_cleanup(
    ingest_settings: IngestSettings,
    run_context: RunContext,
) -> None:
    db_path = ingest_settings.reports_db
    batch = _batch(ingest_settings, run_context)

    first = upsert_projection(
        AnalyticsProjectionUpsertRequest(
            schema_version=PROJECTION_SCHEMA_VERSION,
            db_path=db_path,
            batch=batch,
        ),
        run_context,
    )
    second = upsert_projection(
        AnalyticsProjectionUpsertRequest(
            schema_version=PROJECTION_SCHEMA_VERSION,
            db_path=db_path,
            batch=batch,
        ),
        run_context,
    )

    assert first.projection_status == "projected"
    assert second.projection_attempt_count == 2
    assert _fetch_one(db_path, "SELECT COUNT(*) AS count FROM report_findings")[
        "count"
    ] == len(batch.findings)
    report = _fetch_one(
        db_path,
        "SELECT projection_status, projection_attempt_count, projection_error_code FROM reports WHERE file_id=?",
        ("drive-file-1",),
    )
    assert dict(report) == {
        "projection_status": "projected",
        "projection_attempt_count": 2,
        "projection_error_code": None,
    }
    with sqlite3.connect(db_path) as conn:
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(reports)").fetchall()
        }
    assert "source_file_id" not in columns

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO report_findings(finding_uid, report_id, finding_id, text, evidence, confidence, pages_json, schema_version, projection_version, source_pack, source_ref, model, generated_at_utc, analysis_run_id)
            VALUES('drive-file-1:finding:stale', 'drive-file-1', 'stale', 'stale', '', '', '[]', '1.0', ?, 'findings', 'stale', '', '2026-04-22T12:00:00Z', 'run')
            """,
            (PROJECTION_VERSION,),
        )
        conn.execute(
            """
            INSERT INTO report_findings(finding_uid, report_id, finding_id, text, evidence, confidence, pages_json, schema_version, projection_version, source_pack, source_ref, model, generated_at_utc, analysis_run_id)
            VALUES('other-report:finding:stale', 'other-report', 'stale', 'stale', '', '', '[]', '1.0', ?, 'findings', 'stale', '', '2026-04-22T12:00:00Z', 'run')
            """,
            (PROJECTION_VERSION,),
        )
        conn.commit()

    upsert_projection(
        AnalyticsProjectionUpsertRequest(
            schema_version=PROJECTION_SCHEMA_VERSION,
            db_path=db_path,
            batch=batch,
        ),
        run_context,
    )

    assert (
        _fetch_one(
            db_path,
            "SELECT COUNT(*) AS count FROM report_findings WHERE report_id='drive-file-1' AND finding_uid LIKE '%stale'",
        )["count"]
        == 0
    )
    assert (
        _fetch_one(
            db_path,
            "SELECT COUNT(*) AS count FROM report_findings WHERE report_id='other-report'",
        )["count"]
        == 1
    )


def test_projection_store_records_failure_and_validates_embedding_status(
    ingest_settings: IngestSettings,
    run_context: RunContext,
    assert_app_error,
) -> None:
    batch = _batch(ingest_settings, run_context)
    invalid_queue = replace(batch.vector_queue[0], embedding_status="queued")
    invalid_batch = replace(batch, vector_queue=[invalid_queue])

    with pytest.raises(AppError) as err:
        upsert_projection(
            AnalyticsProjectionUpsertRequest(
                schema_version=PROJECTION_SCHEMA_VERSION,
                db_path=ingest_settings.reports_db,
                batch=invalid_batch,
            ),
            run_context,
        )
    assert_app_error(
        err.value,
        code="analytics_projection_embedding_status_invalid",
        retryable=False,
    )

    response = record_projection_failure(
        AnalyticsProjectionFailureRequest(
            schema_version=PROJECTION_SCHEMA_VERSION,
            db_path=ingest_settings.reports_db,
            report_id="drive-file-1",
            projection_schema_version=PROJECTION_SCHEMA_VERSION,
            projection_version=PROJECTION_VERSION,
            generated_at_utc="2026-04-22T12:00:00Z",
            error_code="analytics_projection_test_failure",
            error_message="projection failed",
            error_retryable=False,
        ),
        run_context,
    )

    assert response.projection_status == "failed"
    row = _fetch_one(
        ingest_settings.reports_db,
        """
        SELECT projection_status, projection_attempt_count, projection_error_code,
               projection_error_message, projection_error_retryable
        FROM reports WHERE file_id=?
        """,
        ("drive-file-1",),
    )
    assert row["projection_status"] == "failed"
    assert row["projection_attempt_count"] >= 1
    assert row["projection_error_code"] == "analytics_projection_test_failure"
    assert row["projection_error_message"] == "projection failed"
    assert row["projection_error_retryable"] == 0


def test_projection_store_migrates_legacy_reports_schema_and_records_ledger(
    tmp_path,
    run_context: RunContext,
) -> None:
    db_path = tmp_path / "legacy_reports.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE reports (
              file_id TEXT PRIMARY KEY,
              title TEXT NOT NULL,
              taxonomy_json TEXT NOT NULL,
              created_at INTEGER NOT NULL,
              updated_at INTEGER NOT NULL
            );
            """
        )
        conn.commit()

    response = record_projection_failure(
        AnalyticsProjectionFailureRequest(
            schema_version=PROJECTION_SCHEMA_VERSION,
            db_path=str(db_path),
            report_id="drive-file-1",
            projection_schema_version=PROJECTION_SCHEMA_VERSION,
            projection_version=PROJECTION_VERSION,
            generated_at_utc="2026-04-22T12:00:00Z",
            error_code="analytics_projection_test_failure",
            error_message="projection failed",
            error_retryable=False,
        ),
        run_context,
    )

    assert response.projection_status == "failed"
    row = _fetch_one(
        str(db_path),
        """
        SELECT projection_status, projection_error_code
        FROM reports WHERE file_id=?
        """,
        ("drive-file-1",),
    )
    assert row["projection_status"] == "failed"
    assert row["projection_error_code"] == "analytics_projection_test_failure"
    with sqlite3.connect(db_path) as conn:
        schema_version = conn.execute(
            "SELECT current_version FROM schema_version WHERE database_key='reports_db'"
        ).fetchone()
        ledger_count = conn.execute(
            "SELECT COUNT(*) FROM schema_migration_ledger WHERE database_key='reports_db'"
        ).fetchone()[0]
        analytics_tables = {
            row[0]
            for row in conn.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type='table' AND name IN (
                  'report_sections',
                  'report_findings',
                  'report_metrics',
                  'report_quotes',
                  'report_claims',
                  'report_tags',
                  'report_categories',
                  'report_figures',
                  'vector_projection_queue'
                )
                """
            ).fetchall()
        }
    assert schema_version == (10,)
    assert ledger_count == 10
    assert analytics_tables == {
        "report_sections",
        "report_findings",
        "report_metrics",
        "report_quotes",
        "report_claims",
        "report_tags",
        "report_categories",
        "report_figures",
        "vector_projection_queue",
    }


def test_projection_orchestrator_records_failure_status(
    ingest_settings: IngestSettings,
    run_context: RunContext,
    assert_app_error,
) -> None:
    def _fail_build(_request):
        raise AppError(
            code="analytics_projection_build_failed",
            message="build failed",
            retryable=False,
            severity="error",
        )

    deps = AnalyticsProjectionDependencies(
        build_projection=_fail_build,
        upsert_projection=upsert_projection,
        record_projection_failure=record_projection_failure,
        utc_now=lambda: "2026-04-22T12:00:00Z",
    )

    with pytest.raises(AppError) as err:
        run_analytics_projection(
            AnalyticsProjectionRunRequest(
                schema_version=PROJECTION_SCHEMA_VERSION,
                db_path=ingest_settings.reports_db,
                analysis=_analysis_state(ingest_settings, run_context),
                rendered_html_path="out/report.html",
                ctx=run_context,
            ),
            dependencies=deps,
        )

    assert_app_error(
        err.value,
        code="analytics_projection_build_failed",
        retryable=False,
    )
    row = _fetch_one(
        ingest_settings.reports_db,
        "SELECT projection_status, projection_attempt_count, projection_error_code FROM reports WHERE file_id=?",
        ("drive-file-1",),
    )
    assert row["projection_status"] == "failed"
    assert row["projection_attempt_count"] == 1
    assert row["projection_error_code"] == "analytics_projection_build_failed"
