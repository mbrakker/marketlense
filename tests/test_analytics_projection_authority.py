from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

from src.contracts.analytics_projection import (
    PROJECTION_SCHEMA_VERSION,
    AnalyticsProjectionBuildRequest,
)
from src.contracts.ingest import IngestSettings
from src.contracts.run_context import RunContext
from src.contracts.validation import ValidationReport
from src.generators.analytics_projection_generator import build_projection
from src.utils.verified_facts import build_verified_authority_context
from tests.test_analytics_projection_foundation import _analysis_state
from tests.test_verified_facts_validation_authority import (
    SOURCE_IDENTITY,
    _authority_artifacts,
)


def test_normal_projection_requires_passing_validation_for_source_eligibility(
    ingest_settings: IngestSettings,
    run_context: RunContext,
) -> None:
    base = _analysis_state(ingest_settings, run_context)

    missing = build_projection(
        AnalyticsProjectionBuildRequest(
            schema_version=PROJECTION_SCHEMA_VERSION,
            analysis=replace(base, validation_report=None),
            rendered_html_path="out/report.html",
            generated_at_utc="2026-04-22T12:00:00Z",
        )
    )
    assert missing.report.source_validation_eligible is False

    failed = build_projection(
        AnalyticsProjectionBuildRequest(
            schema_version=PROJECTION_SCHEMA_VERSION,
            analysis=replace(
                base,
                validation_report=ValidationReport(
                    schema_version="1.1",
                    status="fail",
                    severity="error",
                    issues=["source_validation_failed"],
                    source_path="validation.json",
                ),
            ),
            rendered_html_path="out/report.html",
            generated_at_utc="2026-04-22T12:00:00Z",
        )
    )
    assert failed.report.source_validation_eligible is False


def test_verified_projection_requires_passing_validation_for_source_eligibility(
    ingest_settings: IngestSettings,
    run_context: RunContext,
) -> None:
    base = _analysis_state(ingest_settings, run_context)
    artifacts = _authority_artifacts()
    authority = build_verified_authority_context(
        artifacts, expected_source_identity=SOURCE_IDENTITY
    )
    runtime = replace(
        base.runtime,
        ctx=replace(base.runtime.ctx, source_identity_id=SOURCE_IDENTITY),
    )
    source = replace(base.source, runtime=runtime)
    common = dict(
        runtime=runtime,
        source=source,
        selection=replace(base.selection, runtime=runtime, source=source),
        artifacts_payload=artifacts,
        authoritative_evidence_packs=authority.evidence_packs,
        verified_authority_context=authority,
    )

    for validation_report in (
        None,
        ValidationReport(
            schema_version="1.1",
            status="fail",
            severity="error",
            issues=["source_validation_failed"],
            source_path="validation.json",
        ),
        ValidationReport(
            schema_version="1.1",
            status="unresolved",
            severity="warning",
            issues=["source_validation_unresolved"],
            source_path="validation.json",
        ),
    ):
        analysis = replace(base, validation_report=validation_report, **common)
        batch = build_projection(
            AnalyticsProjectionBuildRequest(
                schema_version=PROJECTION_SCHEMA_VERSION,
                analysis=analysis,
                rendered_html_path="out/report.html",
                generated_at_utc="2026-04-22T12:00:00Z",
            )
        )
        assert batch.report.source_validation_eligible is False


def test_verified_projection_keeps_unbound_claims_and_quotes_out_of_source_queue(
    ingest_settings: IngestSettings,
    run_context: RunContext,
) -> None:
    base = _analysis_state(ingest_settings, run_context)
    artifacts = deepcopy(_authority_artifacts())
    artifacts["summary"] = {
        "claim_evidence_map": [
            {
                "claim": "Analyst-derived claim",
                "evidence": "Analyst context",
                "evidence_id": "analyst-claim",
                "pages": [4],
            },
            {
                "claim": "Fact-bound claim",
                "evidence": "Canonical fact context",
                "evidence_id": "verified-fact:fact-1",
                "pages": [4],
            },
        ]
    }
    artifacts["quotes_final"] = [
        {"id": "unbound", "text": "Analyst quote", "page": 4, "evidence_id": ""},
        {
            "id": "bound",
            "text": "Canonical quote",
            "page": 4,
            "evidence_id": "verified-fact:fact-1",
        },
    ]
    authority = build_verified_authority_context(
        artifacts, expected_source_identity=SOURCE_IDENTITY
    )
    runtime = replace(
        base.runtime,
        ctx=replace(base.runtime.ctx, source_identity_id=SOURCE_IDENTITY),
    )
    source = replace(base.source, runtime=runtime)
    analysis = replace(
        base,
        runtime=runtime,
        source=source,
        selection=replace(base.selection, runtime=runtime, source=source),
        artifacts_payload=artifacts,
        authoritative_evidence_packs=authority.evidence_packs,
        verified_authority_context=authority,
    )

    batch = build_projection(
        AnalyticsProjectionBuildRequest(
            schema_version=PROJECTION_SCHEMA_VERSION,
            analysis=analysis,
            rendered_html_path="out/report.html",
            generated_at_utc="2026-04-22T12:00:00Z",
        )
    )

    claim_classes = {
        row.text_payload: row.content_class
        for row in batch.vector_queue
        if row.entity_type == "claim"
    }
    quote_classes = {
        row.text_payload: row.content_class
        for row in batch.vector_queue
        if row.entity_type == "quote"
    }
    assert (
        next(
            value
            for key, value in claim_classes.items()
            if "Analyst-derived claim" in key
        )
        == "editorial"
    )
    assert (
        next(value for key, value in claim_classes.items() if "Fact-bound claim" in key)
        == "evidence"
    )
    assert (
        next(value for key, value in quote_classes.items() if "Analyst quote" in key)
        == "editorial"
    )
    assert (
        next(value for key, value in quote_classes.items() if "Canonical quote" in key)
        == "evidence"
    )
    assert all("UNTRUSTED" not in row.text for row in batch.findings)
    finding_queue = next(
        row for row in batch.vector_queue if row.entity_type == "finding"
    )
    assert finding_queue.metadata["verified_fact_id"] == "fact-1"
    assert finding_queue.metadata["source_identity"] == SOURCE_IDENTITY
