from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from src.contracts.minimal_execution_plan import (
    MINIMAL_EXECUTION_PLAN_SCHEMA_VERSION,
    ExecutionCompatibilityVersions,
    MinimalExecutionPlanInput,
    RetainedArtifact,
    RetainedArtifactGraph,
)
from src.contracts.validation import ValidationReport
from src.generators.publish_readiness_generator import (
    evaluate_publish_readiness,
    plan_publish_readiness_refresh,
)
from src.utils.minimal_execution_planner import plan_minimal_execution

_HTML = (
    "<!doctype html><html><head><title>Report 2026 | MarketLense</title>"
    '<link rel="canonical" href="https://marketlense.example/reports/report">'
    "</head><body><h1>Report 2026</h1>"
    "<p>Revenue grew in the measured market.</p>"
    '<section id="source"><a href="https://publisher.example/report">'
    "Open original source</a></section></body></html>"
)
_FULL_PIPELINE_CALLS = {
    "pdf_parse",
    "ocr",
    "crop_render",
    "crop_qa",
    "vector_store",
    "report_analysis_model",
    "validator_model",
    "html_render",
}


def _artifact(
    artifact_id: str, artifact_kind: str, dependencies: list[str] | None = None
) -> RetainedArtifact:
    compatibility = {"artifact_family": artifact_kind}
    if artifact_kind == "artifacts":
        compatibility["prompt_versions"] = {}
    return RetainedArtifact(
        artifact_id=artifact_id,
        artifact_kind=artifact_kind,
        report_id="report-1",
        source_id="source-1",
        content_hash=artifact_id,
        storage_ref=f"retained/{artifact_id}",
        state="active",
        schema_version_used="1.0",
        processing_version="report_generation_checkpoint_v2",
        validation_status="pass",
        dependency_artifact_ids=dependencies or [],
        compatibility=compatibility,
        lineage_status="complete",
        storage_available=True,
        observed_content_hash=artifact_id,
    )


def _expired_readiness():
    return evaluate_publish_readiness(
        report_id="report-1",
        artifacts={
            "categories": ["markets"],
            "summary": {
                "claim_evidence_map": [
                    {
                        "claim": "Revenue grew in the measured market.",
                        "evidence_id": "F1",
                        "evidence": "Revenue grew in the measured market.",
                    }
                ]
            },
            "insights_final": [],
            "quotes_final": [],
            "chart_insight_cards": [],
        },
        evidence_packs={
            "findings": {
                "findings": [
                    {
                        "id": "F1",
                        "snippet": "Revenue grew in the measured market.",
                        "page": 1,
                    }
                ]
            }
        },
        validation_report=ValidationReport(schema_version="1.1", status="pass"),
        final_html=_HTML,
        final_html_path="out/report-1.html",
        category_ids=["markets"],
        configuration_hash="configuration-hash",
        policy_hash="policy-hash",
        producer_revision="producer-1",
        provenance={
            "publisher_landing_page_url": "https://publisher.example/report",
            "original_report_url": "",
            "marketlense_article_url": "https://marketlense.example/reports/report",
        },
        created_at=datetime(2026, 8, 26, 12, tzinfo=UTC),
    )


def test_stale_readiness_fixture_eliminates_full_pipeline_work_and_converges() -> None:
    refresh = plan_publish_readiness_refresh(
        report_id="report-1",
        readiness=_expired_readiness(),
        final_html=_HTML,
        configuration_hash="configuration-hash",
        policy_hash="policy-hash",
        producer_revision="producer-1",
        evaluated_at_utc=datetime(2026, 8, 28, 12, tzinfo=UTC),
    )
    source = _artifact("source", "source_pdf")
    analysis = _artifact("analysis", "analysis_pdf", ["source"])
    crop = _artifact("crop", "crop_image", ["analysis"])
    artifacts = _artifact("artifacts", "artifacts", ["analysis"])
    validation = _artifact("validation", "validation", ["artifacts"])
    rendered = _artifact(
        "rendered", "rendered_html", ["artifacts", "validation", "crop"]
    )
    minimum = plan_minimal_execution(
        MinimalExecutionPlanInput(
            schema_version=MINIMAL_EXECUTION_PLAN_SCHEMA_VERSION,
            execution_intent=refresh.execution_intent,
            report_id="report-1",
            source_id="source-1",
            current_source_content_hashes={"source-1": "source"},
            retained_graph=RetainedArtifactGraph(
                artifacts=[source, analysis, crop, artifacts, validation, rendered],
                edges=[
                    ("analysis", "source"),
                    ("crop", "analysis"),
                    ("artifacts", "analysis"),
                    ("validation", "artifacts"),
                    ("rendered", "artifacts"),
                    ("rendered", "validation"),
                    ("rendered", "crop"),
                ],
            ),
            requested_output_families=["rendered_html"],
            current_compatibility=ExecutionCompatibilityVersions(),
            forced_invalidations=refresh.forced_invalidations,
        )
    )

    assert refresh.previous_readiness_state == "stale"
    assert minimum.required_stages == ["render_complete"]
    assert minimum.required_external_calls == ["html_render"]
    assert set(minimum.required_external_calls) & {
        "report_analysis_model",
        "validator_model",
    } == set()
    assert _FULL_PIPELINE_CALLS - set(minimum.required_external_calls) == {
        "crop_qa",
        "crop_render",
        "ocr",
        "pdf_parse",
        "report_analysis_model",
        "validator_model",
        "vector_store",
    }

    # A new canonical readiness decision is signed by the renderer.
    current = evaluate_publish_readiness(
        report_id="report-1",
        artifacts={
            "categories": ["markets"],
            "summary": {
                "claim_evidence_map": [
                    {
                        "claim": "Revenue grew in the measured market.",
                        "evidence_id": "F1",
                        "evidence": "Revenue grew in the measured market.",
                    }
                ]
            },
            "insights_final": [],
            "quotes_final": [],
            "chart_insight_cards": [],
        },
        evidence_packs={
            "findings": {
                "findings": [
                    {
                        "id": "F1",
                        "snippet": "Revenue grew in the measured market.",
                        "page": 1,
                    }
                ]
            }
        },
        validation_report=ValidationReport(schema_version="1.1", status="pass"),
        final_html=_HTML,
        final_html_path="out/report-1.html",
        category_ids=["markets"],
        configuration_hash="configuration-hash",
        policy_hash="policy-hash",
        producer_revision="producer-1",
        provenance={
            "publisher_landing_page_url": "https://publisher.example/report",
            "original_report_url": "",
            "marketlense_article_url": "https://marketlense.example/reports/report",
        },
        created_at=datetime(2026, 8, 28, 12, tzinfo=UTC),
    )
    converged = plan_publish_readiness_refresh(
        report_id="report-1",
        readiness=current,
        final_html=_HTML,
        configuration_hash="configuration-hash",
        policy_hash="policy-hash",
        producer_revision="producer-1",
        evaluated_at_utc=datetime(2026, 8, 28, 13, tzinfo=UTC),
    )

    assert converged.previous_readiness_state == "ready"
    assert converged.regenerated_stages == []


def test_invalid_upstream_lineage_moves_refresh_to_source_preparation() -> None:
    refresh = plan_publish_readiness_refresh(
        report_id="report-1",
        readiness=_expired_readiness(),
        final_html=_HTML,
        configuration_hash="configuration-hash",
        policy_hash="policy-hash",
        producer_revision="producer-1",
        evaluated_at_utc=datetime(2026, 8, 28, 12, tzinfo=UTC),
    )
    source = replace(_artifact("source", "source_pdf"), observed_content_hash="changed")
    analysis = _artifact("analysis", "analysis_pdf", ["source"])
    rendered = _artifact("rendered", "rendered_html", ["analysis"])

    minimum = plan_minimal_execution(
        MinimalExecutionPlanInput(
            schema_version=MINIMAL_EXECUTION_PLAN_SCHEMA_VERSION,
            execution_intent=refresh.execution_intent,
            report_id="report-1",
            source_id="source-1",
            current_source_content_hashes={"source-1": "source"},
            retained_graph=RetainedArtifactGraph(
                artifacts=[source, analysis, rendered],
                edges=[("analysis", "source"), ("rendered", "analysis")],
            ),
            requested_output_families=["rendered_html"],
            current_compatibility=ExecutionCompatibilityVersions(),
            forced_invalidations=refresh.forced_invalidations,
        )
    )

    assert minimum.required_stages == [
        "source_prepared",
        "selection_complete",
        "analysis_complete",
        "render_complete",
    ]
