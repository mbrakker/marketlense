from __future__ import annotations

import sqlite3
from pathlib import Path

from src.contracts.corpus_rehabilitation import (
    CorpusRehabilitationCampaignApprovalRequest,
    CorpusRehabilitationCampaignCreateRequest,
    CorpusRehabilitationPlanRequest,
)
from src.contracts.report_store import ReportMetadataUpsertRequest
from src.contracts.run_context import RunContext
from src.orchestrators.corpus_rehabilitation_orchestrator import (
    submit_corpus_rehabilitation_campaign,
)
from src.services._report_store_service.corpus_rehabilitation import (
    approve_corpus_rehabilitation_campaign,
    create_corpus_rehabilitation_campaign,
    read_corpus_rehabilitation_plan,
)
from src.services.report_store_service import upsert_metadata


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def test_rehabilitation_plan_classifies_retained_reports_without_writing(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "reports.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "CREATE TABLE reports("
            "file_id TEXT, html_path TEXT, validation_status TEXT, "
            "text_not_available INTEGER, md5 TEXT, source_url TEXT, "
            "projection_status TEXT)"
        )
        conn.execute(
            "CREATE TABLE artifact_lineage_records(report_id TEXT, artifact_id TEXT)"
        )
        conn.executemany(
            "INSERT INTO reports VALUES(?,?,?,?,?,?,?)",
            [
                ("bad-source", "", "", 0, "", "", ""),
                ("missing-html", "", "pass", 0, "m1", "https://example/a", ""),
                (
                    "bad-validation",
                    "out/a.html",
                    "fail",
                    0,
                    "m2",
                    "https://example/b",
                    "",
                ),
                ("reusable", "out/b.html", "pass", 0, "m3", "https://example/c", ""),
            ],
        )
        conn.execute(
            "INSERT INTO artifact_lineage_records VALUES('reusable','artifact-1')"
        )
    before = db_path.stat().st_mtime_ns

    response = read_corpus_rehabilitation_plan(
        CorpusRehabilitationPlanRequest(schema_version="1.0", db_path=str(db_path)),
        _ctx(),
    )

    assert [item.classification for item in response.candidates] == [
        "source_provenance_incomplete",
        "validation_failed",
        "missing_rendered_report",
        "validated_artifacts_reusable",
    ]
    assert response.classification_counts == {
        "missing_rendered_report": 1,
        "source_provenance_incomplete": 1,
        "validated_artifacts_reusable": 1,
        "validation_failed": 1,
    }
    assert all(item.estimate_status == "unavailable" for item in response.candidates)
    assert response.provider_calls == 0
    assert db_path.stat().st_mtime_ns == before


def test_approved_campaign_queues_only_revalidated_reusable_artifacts(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "reports.sqlite"
    state_db = tmp_path / "state.sqlite"
    upsert_metadata(
        ReportMetadataUpsertRequest(
            schema_version="1.0",
            db_path=str(db_path),
            file_id="reusable",
            title="Retained",
            source_url="https://example.test/report",
            html_path="out/reusable.html",
            md5="m3",
        ),
        _ctx(),
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO artifact_lineage_records("
            "artifact_id,artifact_kind,report_id,source_id,content_hash,storage_ref,"
            "producer,schema_version_used,processing_version,prompt_hash,model_provider,"
            "model_name,model_parameters_hash,validation_status,metadata_json,"
            "created_at_utc,compatibility_json,lineage_status) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "artifact-1",
                "summary",
                "reusable",
                "source-1",
                "m3",
                "out/reusable.html",
                "test",
                "1.0",
                "v1",
                "hash",
                "openai",
                "gpt-5-mini",
                "params",
                "valid",
                "{}",
                "2026-01-01T00:00:00Z",
                "{}",
                "active",
            ),
        )

    created = create_corpus_rehabilitation_campaign(
        CorpusRehabilitationCampaignCreateRequest(
            schema_version="1.0", db_path=str(db_path), batch_size=1, created_by="test"
        ),
        _ctx(),
    )
    assert created.created
    assert created.items[0].status == "ready_for_approval"

    approved = approve_corpus_rehabilitation_campaign(
        CorpusRehabilitationCampaignApprovalRequest(
            schema_version="1.0",
            db_path=str(db_path),
            campaign_id=created.campaign.campaign_id,
            approved_by="test",
            reason="bounded canary",
        ),
        _ctx(),
    )
    submitted = submit_corpus_rehabilitation_campaign(
        reports_db=str(db_path),
        state_db=str(state_db),
        campaign_id=approved.campaign.campaign_id,
        ctx=_ctx(),
        limit=1,
    )
    assert submitted.campaign.actual_provider_calls == 0
    assert submitted.items[0].status == "queued"
    assert submitted.items[0].queue_job_id

    repeated = submit_corpus_rehabilitation_campaign(
        reports_db=str(db_path),
        state_db=str(state_db),
        campaign_id=approved.campaign.campaign_id,
        ctx=_ctx(),
        limit=1,
    )
    assert repeated.items[0].queue_job_id == submitted.items[0].queue_job_id
