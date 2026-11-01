from __future__ import annotations

from dataclasses import asdict
from types import SimpleNamespace

import pytest

from src.contracts.cross_report_analysis import (
    CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
    CrossReportAnalysisRequest,
    CrossReportEvidenceInputResult,
    CrossReportEvidenceReference,
    CrossReportProjectedDataReadResponse,
    CrossReportSelectedSourceReport,
    CrossReportSelectedTheme,
    CrossReportSourceReportCandidate,
    CrossReportSourceSelectionResult,
    CrossReportThemeSelectionResult,
    CrossReportValidationResult,
)
from src.contracts.publish import PublishOutcome
from src.contracts.run_context import RunContext
from src.contracts.wordpress import (
    WordPressPostLookupResponse,
    WordPressTagEnsureResponse,
    WordPressTaxonomyEnsureResponse,
)
from src.contracts.wordpress_entities import (
    WORDPRESS_ENTITY_SCHEMA_VERSION,
    SignalPostGenerationRequest,
)
from src.generators._cross_report_analysis_input.theme_selection import (
    validate_cross_report_publishability,
)
from src.generators.signal_post_generator import build_signal_publish_projection
from src.orchestrators._publish_orchestrator.cross_report import (
    _signal_projection_package,
)
from src.orchestrators.cross_report_analysis_orchestrator import _config_fingerprint
from src.orchestrators.publish_orchestrator import publish_signal_projection
from src.utils.errors import AppError


def _signal_source(
    report_id: str,
    publisher: str,
    *,
    source_validation_eligible: bool = True,
) -> CrossReportSourceReportCandidate:
    return CrossReportSourceReportCandidate(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        report_id=report_id,
        title=f"{publisher} report",
        publisher=publisher,
        publisher_id=publisher.casefold().replace(" ", "-"),
        report_date="2026-06-01",
        projection_status="projected",
        content_hash=f"{report_id}-hash",
        category_labels=["Retail"],
        tags=["AI"],
        evidence_count=1,
        claim_count=1,
        finding_count=0,
        quote_count=0,
        metric_count=0,
        recency_score=0.0,
        relevance_score=0.0,
        diversity_score=0.0,
        density_score=1.0,
        total_score=1.0,
        selection_reasons=["projected"],
        rejection_reasons=[],
        category_ids=["retail"],
        source_validation_eligible=source_validation_eligible,
    )


def _signal_evidence(evidence_id: str, report_id: str, publisher: str):
    return CrossReportEvidenceReference(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        evidence_id=evidence_id,
        report_id=report_id,
        publisher=publisher,
        title=f"{publisher} report",
        source_table="report_claims",
        entity_uid=evidence_id,
        content_class="claim",
        text=f"{publisher} reports AI adoption.",
        source_metadata={"pages": [2]},
    )


def _signal_request() -> SignalPostGenerationRequest:
    return SignalPostGenerationRequest(
        schema_version=WORDPRESS_ENTITY_SCHEMA_VERSION,
        request_id="signal-authority-regression",
        topic="AI adoption",
        category_filters=["Retail"],
        tag_filters=["AI"],
        publisher_filters=[],
        date_range_start=None,
        date_range_end=None,
        max_source_reports=2,
        max_evidence_items=2,
        minimum_source_reports=2,
        minimum_evidence_items=2,
    )


def _signal_projected_data(
    *, source_validation_eligible: bool = True
) -> CrossReportProjectedDataReadResponse:
    return CrossReportProjectedDataReadResponse(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        source_candidates=[
            _signal_source(
                "report-a",
                "Publisher A",
                source_validation_eligible=source_validation_eligible,
            ),
            _signal_source("report-b", "Publisher B"),
        ],
        evidence=[
            _signal_evidence("report-a:claim:1", "report-a", "Publisher A"),
            _signal_evidence("report-b:claim:1", "report-b", "Publisher B"),
        ],
        raw_metrics=[],
        content_hashes={},
        excluded_report_counts={},
    )


def test_direct_signal_fallback_is_blocked_before_wordpress_calls(
    run_context,
    publish_settings_factory,
) -> None:
    projection = build_signal_publish_projection(
        _signal_request(), _signal_projected_data(), run_context
    )
    assert projection.validation_status == "blocked"

    lookup_calls: list[object] = []
    write_calls: list[object] = []

    def lookup(request, ctx):
        lookup_calls.append(request)
        return WordPressPostLookupResponse(
            schema_version="1.0", found=False, post_id=None, link=None
        )

    def publish(request, settings, ctx):
        write_calls.append(request)
        return PublishOutcome(
            schema_version="1.0",
            html_path=request.html_path,
            file_id=request.file_id,
            status="published",
            post_id=1,
            post_url="https://example.com/signals/blocked",
        )

    def ensure_taxonomy(request, ctx):
        return WordPressTaxonomyEnsureResponse(schema_version="1.0", slug_to_id={})

    def ensure_tags(request, ctx):
        return WordPressTagEnsureResponse(schema_version="1.0", slug_to_id={})

    with pytest.raises(AppError) as exc_info:
        publish_signal_projection(
            projection,
            asdict(projection.card_content),
            publish_settings_factory(validation_policy="warn"),
            run_context,
            dry_run=False,
            publish_html_fn=publish,
            find_post_by_file_id_fn=lookup,
            ensure_taxonomy_terms_fn=ensure_taxonomy,
            ensure_tags_fn=ensure_tags,
            sleep_fn=lambda _: None,
        )

    assert exc_info.value.code == "signal_publish_validation_status_invalid"
    assert lookup_calls == []
    assert write_calls == []


def test_frozen_signal_rejects_currently_ineligible_source(
    run_context,
) -> None:
    request = SignalPostGenerationRequest(
        **{
            **_signal_request().__dict__,
            "candidate_group_id": "signal-group:ai",
            "candidate_manifest_sha256": "a" * 64,
            "extraction_request_id": "extract-ai",
            "candidate_ids": ["candidate-ai"],
            "source_report_ids": ["report-a", "report-b"],
            "evidence_ids": ["report-a:claim:1", "report-b:claim:1"],
            "topic_ids": ["retail"],
            "source_category_ids": {
                "report-a": ["retail"],
                "report-b": ["retail"],
            },
        }
    )
    from src.contracts.signal_candidates import (
        SIGNAL_CANDIDATE_SCHEMA_VERSION,
        SignalCandidate,
        SignalCandidateGroup,
        SignalCandidateReadResponse,
        SignalCandidateSourceRef,
    )

    evidence = _signal_projected_data().evidence
    candidate = SignalCandidate(
        schema_version=SIGNAL_CANDIDATE_SCHEMA_VERSION,
        candidate_id="candidate-ai",
        candidate_type="market_signal",
        title="AI adoption",
        summary="AI adoption is rising.",
        confidence=0.8,
        strength=1.0,
        support_level="multi_report_convergent",
        caveats=["source_backed"],
        source_report_ids=["report-a", "report-b"],
        evidence_ids=[item.evidence_id for item in evidence],
        source_refs=[
            SignalCandidateSourceRef(
                schema_version=SIGNAL_CANDIDATE_SCHEMA_VERSION,
                report_id=item.report_id,
                evidence_id=item.evidence_id,
                source_table="report_claims",
                entity_uid=item.entity_uid,
                content_class="claim",
                page_refs=[2],
                source_metadata={"pages": [2]},
            )
            for item in evidence
        ],
        raw_source_context={"evidence": [asdict(item) for item in evidence]},
        validation_status="approved",
        validation_notes=["source_backed"],
        group_id="signal-group:ai",
        extraction_request_id="extract-ai",
        generated_at_utc="2026-06-01T00:00:00Z",
    )
    group = SignalCandidateGroup(
        schema_version=SIGNAL_CANDIDATE_SCHEMA_VERSION,
        group_id="signal-group:ai",
        stable_key="ai",
        title="AI adoption",
        summary="AI adoption is rising.",
        support_level="multi_report_convergent",
        candidate_ids=["candidate-ai"],
        source_report_ids=["report-a", "report-b"],
        evidence_ids=[item.evidence_id for item in evidence],
        caveats=["source_backed"],
        raw_group_context={
            "source_content_hashes": {
                "report-a": "report-a-hash",
                "report-b": "report-b-hash",
            }
        },
        validation_status="approved",
        extraction_request_id="extract-ai",
        generated_at_utc="2026-06-01T00:00:00Z",
        topic="AI adoption",
        topic_ids=["retail"],
        source_category_ids={
            "report-a": ["retail"],
            "report-b": ["retail"],
        },
        publication_status="eligible",
        publication_hold_reason="",
    )

    with pytest.raises(AppError) as exc_info:
        build_signal_publish_projection(
            request,
            _signal_projected_data(source_validation_eligible=False),
            run_context,
            candidate_data=SignalCandidateReadResponse(
                schema_version=SIGNAL_CANDIDATE_SCHEMA_VERSION,
                db_path="signals.sqlite",
                candidates=[candidate],
                groups=[group],
                manifest_sha256="a" * 64,
            ),
        )

    assert exc_info.value.code == "signal_frozen_manifest_source_ineligible"


def _briefing_request() -> CrossReportAnalysisRequest:
    return CrossReportAnalysisRequest(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        request_id="briefing-authority-regression",
        topic="AI adoption",
        auto_theme=False,
        category_filters=[],
        tag_filters=[],
        publisher_filters=[],
        date_range_start=None,
        date_range_end=None,
        max_source_reports=2,
        diagnostic=False,
        override_publishability=False,
        publication_mode="publish_dry_run",
    )


def _briefing_selection() -> tuple[
    CrossReportThemeSelectionResult,
    CrossReportSourceSelectionResult,
    CrossReportEvidenceInputResult,
]:
    theme = CrossReportSelectedTheme(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        theme_id="theme-ai",
        label="AI adoption",
        rationale="Two sources cover the topic.",
        matched_tags=[],
        matched_categories=[],
        source_report_ids=["report-a", "report-b"],
        score_components={"source": 1.0},
        selection_reasons=["source_backed"],
        rejection_risks=[],
    )
    theme_selection = CrossReportThemeSelectionResult(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        selected_theme=theme,
        theme_candidates=[],
        rejected_theme_candidates=[],
    )
    sources = [
        CrossReportSelectedSourceReport(
            schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
            report_id="report-a",
            title="A",
            publisher="Publisher A",
            publisher_id="publisher-a",
            report_date="2026-06-01",
            projection_status="projected",
            content_hash="a-hash",
            rank=1,
            selection_reasons=["selected"],
            evidence_count=1,
            category_labels=[],
            tags=[],
            source_validation_eligible=True,
        ),
        CrossReportSelectedSourceReport(
            schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
            report_id="report-b",
            title="B",
            publisher="Publisher B",
            publisher_id="publisher-b",
            report_date="2026-06-01",
            projection_status="projected",
            content_hash="b-hash",
            rank=2,
            selection_reasons=["selected"],
            evidence_count=1,
            category_labels=[],
            tags=[],
            source_validation_eligible=True,
        ),
    ]
    source_selection = CrossReportSourceSelectionResult(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        selected_sources=sources,
        ranked_candidates=[],
        rejected_candidates=[],
        cleaned_filters={},
        excluded_report_counts={},
    )
    evidence = [
        CrossReportEvidenceReference(
            schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
            evidence_id="ev-a",
            report_id="report-a",
            publisher="Publisher A",
            title="A",
            source_table="report_claims",
            entity_uid="ev-a",
            content_class="claim",
            text="A evidence",
            source_metadata={},
        )
    ]
    evidence_input = CrossReportEvidenceInputResult(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        selected_sources=sources,
        evidence=evidence,
        raw_metrics=[],
        evidence_by_report_id={"report-a": ["ev-a"]},
        dropped_evidence_counts={},
        prompt_input_chars=1,
    )
    return theme_selection, source_selection, evidence_input


def test_briefing_validation_is_mandatory_when_legacy_flag_is_disabled(
    run_context,
) -> None:
    theme_selection, source_selection, evidence_input = _briefing_selection()
    result = validate_cross_report_publishability(
        _briefing_request(),
        theme_selection,
        source_selection,
        run_context,
        min_source_reports=1,
        min_source_publishers=1,
        min_evidence_items=1,
        publish_requires_validation_pass=False,
        validation_result=CrossReportValidationResult(
            schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
            status="fail",
            checked_evidence_ids=["ev-a"],
            issues=["section_missing_body:summary"],
            passed=False,
        ),
        evidence_input=evidence_input,
        raise_on_failure=False,
    )

    assert result.publishable is False
    assert result.source_report_count == 1
    assert result.source_publisher_count == 1
    assert result.evidence_count == 1
    assert "validation_not_passed" in result.issues


def test_briefing_publishability_blocks_absent_final_validation(
    run_context,
) -> None:
    theme_selection, source_selection, evidence_input = _briefing_selection()
    result = validate_cross_report_publishability(
        _briefing_request(),
        theme_selection,
        source_selection,
        run_context,
        min_source_reports=1,
        min_source_publishers=1,
        min_evidence_items=1,
        publish_requires_validation_pass=False,
        validation_result=None,
        evidence_input=evidence_input,
        raise_on_failure=False,
    )

    assert result.publishable is False
    assert "validation_result_required_for_publication" in result.issues


def test_publication_policy_changes_are_part_of_idempotency_fingerprint() -> None:
    base = SimpleNamespace(
        cross_report_analysis_publish_enabled=False,
        cross_report_analysis_publish_requires_validation_pass=True,
        cross_report_analysis_min_theme_source_publishers=2,
    )
    enabled = SimpleNamespace(
        **{**vars(base), "cross_report_analysis_publish_enabled": True}
    )
    relaxed = SimpleNamespace(
        **{
            **vars(base),
            "cross_report_analysis_publish_requires_validation_pass": False,
        }
    )
    stricter = SimpleNamespace(
        **{**vars(base), "cross_report_analysis_min_theme_source_publishers": 3}
    )

    assert _config_fingerprint(base) != _config_fingerprint(enabled)
    assert _config_fingerprint(base) != _config_fingerprint(relaxed)
    assert _config_fingerprint(base) != _config_fingerprint(stricter)


def test_signal_package_does_not_mark_unapproved_projection_publishable() -> None:
    projection = build_signal_publish_projection(
        _signal_request(),
        _signal_projected_data(),
        # A real context is only needed for structured logging.
        RunContext(schema_version="1.0", run_id="run", task_id="task", span_id="span"),
    )
    package = _signal_projection_package(projection, asdict(projection.card_content))
    assert package.machine_metadata["publishability"]["publishable"] is False
