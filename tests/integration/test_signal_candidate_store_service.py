from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import asdict

import pytest

from src.contracts.signal_candidates import (
    SIGNAL_CANDIDATE_SCHEMA_VERSION,
    SignalCandidate,
    SignalCandidateGroup,
    SignalCandidateReadRequest,
    SignalCandidateSourceRef,
    SignalCandidateStoreRequest,
    SignalCandidateStoreResponse,
)
from src.services.analytics_store_service import (
    read_signal_candidates,
    upsert_signal_candidates,
)


def _source_ref(evidence_id: str) -> SignalCandidateSourceRef:
    return SignalCandidateSourceRef(
        schema_version=SIGNAL_CANDIDATE_SCHEMA_VERSION,
        report_id="report-a",
        evidence_id=evidence_id,
        source_table="report_claims",
        entity_uid=f"report-a:claim:{evidence_id}",
        content_class="claim",
        page_refs=[2],
        source_metadata={"pages": [2], "evidence": "projected claim"},
    )


def _candidate(candidate_id: str, *, group_id: str) -> SignalCandidate:
    return SignalCandidate(
        schema_version=SIGNAL_CANDIDATE_SCHEMA_VERSION,
        candidate_id=candidate_id,
        candidate_type="market_signal",
        title="AI",
        summary="AI commerce adoption is accelerating.",
        confidence=0.82,
        strength=4.5,
        support_level="single_report",
        caveats=["single_report_coverage"],
        source_report_ids=["report-a"],
        evidence_ids=["report-a:claim:1"],
        source_refs=[_source_ref("report-a:claim:1")],
        raw_source_context={
            "selected_theme": {"theme_id": "theme-ai"},
            "raw_metric_policy": "raw_metrics_preserved_without_normalization",
        },
        validation_status="approved",
        validation_notes=["source_backed"],
        group_id=group_id,
        extraction_request_id="extract-ai",
        generated_at_utc="2026-06-02T12:00:00Z",
    )


def _group(group_id: str, candidate_id: str) -> SignalCandidateGroup:
    return SignalCandidateGroup(
        schema_version=SIGNAL_CANDIDATE_SCHEMA_VERSION,
        group_id=group_id,
        stable_key="theme-ai:signal-ai",
        title="AI",
        summary="AI commerce adoption is accelerating.",
        support_level="single_report",
        candidate_ids=[candidate_id],
        source_report_ids=["report-a"],
        evidence_ids=["report-a:claim:1"],
        caveats=["single_report_coverage"],
        raw_group_context={"agreement_type": "thin_coverage"},
        validation_status="approved",
        extraction_request_id="extract-ai",
        generated_at_utc="2026-06-02T12:00:00Z",
    )


@pytest.mark.integration
def test_signal_candidate_store_persists_lineage_and_idempotent_readback(
    tmp_path,
    run_context,
    caplog,
    assert_logs_have_required_fields,
) -> None:
    db_path = str(tmp_path / "reports.sqlite")
    candidate = _candidate(
        "signal-candidate:theme-ai:signal-ai",
        group_id="signal-group:theme-ai:signal-ai",
    )
    group = _group("signal-group:theme-ai:signal-ai", candidate.candidate_id)
    request = SignalCandidateStoreRequest(
        schema_version=SIGNAL_CANDIDATE_SCHEMA_VERSION,
        db_path=db_path,
        extraction_request_id="extract-ai",
        candidates=[candidate],
        groups=[group],
    )

    caplog.set_level(logging.INFO, logger="market_lense.analytics_store_service")
    first = upsert_signal_candidates(request, run_context)
    second = upsert_signal_candidates(request, run_context)
    readback = read_signal_candidates(
        SignalCandidateReadRequest(
            schema_version=SIGNAL_CANDIDATE_SCHEMA_VERSION,
            db_path=db_path,
            validation_statuses=["approved"],
            limit=10,
        ),
        run_context,
    )

    assert isinstance(first, SignalCandidateStoreResponse)
    assert first.candidate_count == 1
    assert second.candidate_count == 1
    assert [item.candidate_id for item in readback.candidates] == [
        candidate.candidate_id
    ]
    assert readback.candidates[0] == candidate
    assert readback.groups[0] == group
    with sqlite3.connect(db_path) as conn:
        candidate_count = conn.execute(
            "SELECT COUNT(*) FROM signal_candidates"
        ).fetchone()[0]
        group_count = conn.execute(
            "SELECT COUNT(*) FROM signal_candidate_groups"
        ).fetchone()[0]
        stored = conn.execute(
            "SELECT source_refs_json, raw_source_context_json FROM signal_candidates"
        ).fetchone()
    assert candidate_count == 1
    assert group_count == 1
    assert json.loads(stored[0])[0]["source_table"] == "report_claims"
    assert json.loads(stored[1])["raw_metric_policy"] == (
        "raw_metrics_preserved_without_normalization"
    )

    events = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == "market_lense.analytics_store_service"
    ]
    assert_logs_have_required_fields(events)
    assert {event["event"] for event in events} >= {
        "signal_candidate_store_upsert_start",
        "signal_candidate_store_upsert_complete",
        "signal_candidate_store_read_start",
        "signal_candidate_store_read_complete",
    }


@pytest.mark.integration
def test_signal_candidate_store_removes_stale_rows_for_same_extraction_request(
    tmp_path,
    run_context,
) -> None:
    db_path = str(tmp_path / "reports.sqlite")
    old_candidate = _candidate(
        "signal-candidate:theme-ai:old", group_id="signal-group:theme-ai:old"
    )
    old_group = _group("signal-group:theme-ai:old", old_candidate.candidate_id)
    new_candidate = _candidate(
        "signal-candidate:theme-ai:new", group_id="signal-group:theme-ai:new"
    )
    new_group = _group("signal-group:theme-ai:new", new_candidate.candidate_id)

    upsert_signal_candidates(
        SignalCandidateStoreRequest(
            schema_version=SIGNAL_CANDIDATE_SCHEMA_VERSION,
            db_path=db_path,
            extraction_request_id="extract-ai",
            candidates=[old_candidate],
            groups=[old_group],
        ),
        run_context,
    )
    upsert_signal_candidates(
        SignalCandidateStoreRequest(
            schema_version=SIGNAL_CANDIDATE_SCHEMA_VERSION,
            db_path=db_path,
            extraction_request_id="extract-ai",
            candidates=[new_candidate],
            groups=[new_group],
        ),
        run_context,
    )

    readback = read_signal_candidates(
        SignalCandidateReadRequest(
            schema_version=SIGNAL_CANDIDATE_SCHEMA_VERSION,
            db_path=db_path,
            extraction_request_id="extract-ai",
            validation_statuses=["approved"],
            limit=10,
        ),
        run_context,
    )

    assert [asdict(item)["candidate_id"] for item in readback.candidates] == [
        new_candidate.candidate_id
    ]
