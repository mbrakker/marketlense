from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from src.contracts.cross_report_analysis import (
    CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
    CrossReportEvidenceReference,
    CrossReportProjectedDataReadResponse,
    CrossReportPublishResultSummary,
    CrossReportSourceReportCandidate,
)
from src.contracts.publish import PublishOutcome
from src.contracts.wordpress import (
    WordPressPostLookupResponse,
    WordPressTagEnsureResponse,
    WordPressTaxonomyEnsureResponse,
)
from src.contracts.wordpress_entities import (
    WORDPRESS_ENTITY_SCHEMA_VERSION,
    SignalPostGenerationRequest,
    SignalPostWorkflowRequest,
)
from src.contracts.signal_candidates import (
    SIGNAL_CANDIDATE_SCHEMA_VERSION,
    SignalCandidate,
    SignalCandidateGroup,
    SignalCandidateReadResponse,
    SignalCandidateSourceRef,
)
from src.orchestrators.publish_orchestrator import publish_signal_projection
from src.orchestrators.signal_post_orchestrator import run_signal_post_workflow


def _candidate(report_id: str, publisher: str) -> CrossReportSourceReportCandidate:
    return CrossReportSourceReportCandidate(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        report_id=report_id,
        title=f"{publisher} AI Commerce Report",
        publisher=publisher,
        publisher_id=publisher.lower().replace(" ", "-"),
        report_date="2026-05-20",
        source_url=f"https://sources.example/{report_id}",
        projection_status="projected",
        content_hash=f"{report_id}-hash",
        category_labels=["Retail Strategy"],
        tags=["AI Commerce"],
        evidence_count=2,
        claim_count=2,
        finding_count=0,
        quote_count=0,
        metric_count=0,
        recency_score=0.0,
        relevance_score=0.0,
        diversity_score=0.0,
        density_score=2.0,
        total_score=0.0,
        selection_reasons=["projection_status:projected"],
        rejection_reasons=[],
        category_ids=["retail-strategy"],
    )


def _evidence(
    evidence_id: str, report_id: str, publisher: str
) -> CrossReportEvidenceReference:
    return CrossReportEvidenceReference(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        evidence_id=evidence_id,
        report_id=report_id,
        publisher=publisher,
        title=f"{publisher} AI Commerce Report",
        source_table="report_claims",
        entity_uid=f"{report_id}:claim:{evidence_id}",
        content_class="claim",
        text=f"{publisher} reports AI commerce adoption is changing checkout behavior.",
        source_metadata={
            "pages": [2],
            "source_url": f"https://sources.example/{report_id}",
        },
    )


def _projected_data() -> CrossReportProjectedDataReadResponse:
    return CrossReportProjectedDataReadResponse(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        source_candidates=[
            _candidate("report-a", "Publisher A"),
            _candidate("report-b", "Publisher B"),
        ],
        evidence=[
            _evidence("report-a:claim:1", "report-a", "Publisher A"),
            _evidence("report-b:claim:1", "report-b", "Publisher B"),
        ],
        raw_metrics=[],
        content_hashes={},
        excluded_report_counts={},
    )


def _generation_request() -> SignalPostGenerationRequest:
    return SignalPostGenerationRequest(
        schema_version=WORDPRESS_ENTITY_SCHEMA_VERSION,
        request_id="signal-ai-commerce",
        topic="AI commerce checkout behavior",
        category_filters=["Retail Strategy"],
        tag_filters=["AI Commerce"],
        publisher_filters=[],
        date_range_start=None,
        date_range_end=None,
        max_source_reports=3,
        max_evidence_items=6,
        minimum_source_reports=2,
        minimum_evidence_items=2,
    )


def _workflow_request(
    tmp_path, publication_mode: str = "publish_dry_run", signal_store_db: str = ""
) -> SignalPostWorkflowRequest:
    return SignalPostWorkflowRequest(
        schema_version=WORDPRESS_ENTITY_SCHEMA_VERSION,
        request_id="signal-workflow-ai-commerce",
        generation_request=_generation_request(),
        db_path=str(tmp_path / "analytics.sqlite"),
        signal_store_db=signal_store_db,
        output_root=str(tmp_path),
        cover_style_path=str(
            Path(__file__).resolve().parents[1] / "src" / "config" / "cover-styles.yaml"
        ),
        publication_mode=publication_mode,
    )


def _signal_card(projection) -> dict[str, object]:
    card = projection.card_content
    return {
        "schema_version": card.schema_version,
        "summary": card.summary,
        "confidence": card.confidence,
        "source_count": card.source_count,
        "evidence_count": card.evidence_count,
        "uncertainty": card.uncertainty,
        "covers": {
            "small": "signal-card-small.png",
            "medium": "signal-card-medium.png",
            "large": "signal-card-large.png",
        },
    }


def _ensure_taxonomy(request, ctx):
    if request.taxonomy_rest_base == "categories":
        return WordPressTaxonomyEnsureResponse(
            schema_version="1.0",
            slug_to_id={"retail-strategy": 11},
        )
    if request.taxonomy_rest_base == "ml_publisher":
        return WordPressTaxonomyEnsureResponse(
            schema_version="1.0",
            slug_to_id={"publisher-a": 21, "publisher-b": 22},
        )
    raise AssertionError(request.taxonomy_rest_base)


def _ensure_tags(request, ctx):
    return WordPressTagEnsureResponse(
        schema_version="1.0",
        slug_to_id={"ai-commerce": 31},
    )


def test_signal_workflow_dry_run_reads_projected_data_and_reports_payload(
    tmp_path,
    run_context,
) -> None:
    read_requests = []

    def _read_projected_data(request, ctx):
        read_requests.append(request)
        return _projected_data()

    outcome = run_signal_post_workflow(
        _workflow_request(tmp_path, "publish_dry_run"),
        run_context,
        read_projected_data_fn=_read_projected_data,
    )

    assert outcome.publish_result.status == "dry_run"
    assert outcome.publish_result.target_route == "wordpress:ml_signal"
    assert outcome.publish_result.target_post_type == "ml_signal"
    assert outcome.publish_result.target_slug == "ai-commerce-checkout-behavior-signal"
    assert outcome.publish_result.category_slugs == ["retail-strategy"]
    assert outcome.publish_result.tag_slugs == ["ai-commerce"]
    assert outcome.publish_result.taxonomy_term_slugs == {
        "ml_publisher": ["publisher-a", "publisher-b"]
    }
    assert read_requests[0].db_path == str(tmp_path / "analytics.sqlite")
    assert read_requests[0].minimum_projection_status == "projected"
    assert len(list(tmp_path.rglob("*.png"))) == 3


def test_signal_workflow_reads_candidates_from_separate_signal_store(
    tmp_path,
    run_context,
) -> None:
    projected_requests = []
    signal_candidate_requests = []

    def _read_projected_data(request, ctx):
        projected_requests.append(request)
        return _projected_data()

    def _read_signal_candidates(request, ctx):
        signal_candidate_requests.append(request)
        return SignalCandidateReadResponse(
            schema_version=SIGNAL_CANDIDATE_SCHEMA_VERSION,
            db_path=request.db_path,
            candidates=[],
            groups=[],
        )

    run_signal_post_workflow(
        _workflow_request(
            tmp_path,
            "generate_only",
            signal_store_db=str(tmp_path / "signals.sqlite"),
        ),
        run_context,
        read_projected_data_fn=_read_projected_data,
        read_signal_candidates_fn=_read_signal_candidates,
    )

    assert projected_requests[0].db_path == str(tmp_path / "analytics.sqlite")
    assert signal_candidate_requests[0].db_path == str(tmp_path / "signals.sqlite")


def test_signal_workflow_reads_stored_signal_candidates_before_publish(
    tmp_path,
    run_context,
) -> None:
    candidate = SignalCandidate(
        schema_version=SIGNAL_CANDIDATE_SCHEMA_VERSION,
        candidate_id="signal-candidate:theme-ai:signal-ai",
        candidate_type="market_signal",
        title="AI commerce adoption",
        summary="Stored Signal candidate.",
        confidence=0.81,
        strength=4.1,
        support_level="multi_report_convergent",
        caveats=["coverage limited to selected projected reports"],
        source_report_ids=["report-a", "report-b"],
        evidence_ids=["report-a:claim:1", "report-b:claim:1"],
        source_refs=[
            SignalCandidateSourceRef(
                schema_version=SIGNAL_CANDIDATE_SCHEMA_VERSION,
                report_id="report-a",
                evidence_id="report-a:claim:1",
                source_table="report_claims",
                entity_uid="report-a:claim:1",
                content_class="claim",
                page_refs=[2],
                source_metadata={"pages": [2]},
            )
        ],
        raw_source_context={
            "raw_metric_policy": "raw_metrics_preserved_without_normalization"
        },
        validation_status="approved",
        validation_notes=["source_backed"],
        group_id="signal-group:theme-ai:signal-ai",
        extraction_request_id="extract-ai",
        generated_at_utc="2026-06-02T12:00:00Z",
    )
    group = SignalCandidateGroup(
        schema_version=SIGNAL_CANDIDATE_SCHEMA_VERSION,
        group_id="signal-group:theme-ai:signal-ai",
        stable_key="theme-ai:signal-ai",
        title="AI commerce adoption",
        summary="Stored group.",
        support_level="multi_report_convergent",
        candidate_ids=[candidate.candidate_id],
        source_report_ids=["report-a", "report-b"],
        evidence_ids=["report-a:claim:1", "report-b:claim:1"],
        caveats=["coverage limited to selected projected reports"],
        raw_group_context={"agreement_type": "convergent"},
        validation_status="approved",
        extraction_request_id="extract-ai",
        generated_at_utc="2026-06-02T12:00:00Z",
    )
    read_candidate_requests = []

    def _read_signal_candidates(request, ctx):
        read_candidate_requests.append(request)
        return SignalCandidateReadResponse(
            schema_version=SIGNAL_CANDIDATE_SCHEMA_VERSION,
            db_path=request.db_path,
            candidates=[candidate],
            groups=[group],
        )

    outcome = run_signal_post_workflow(
        _workflow_request(tmp_path, "generate_only"),
        run_context,
        read_projected_data_fn=lambda request, ctx: _projected_data(),
        read_signal_candidates_fn=_read_signal_candidates,
    )

    assert read_candidate_requests[0].db_path == str(tmp_path / "analytics.sqlite")
    assert read_candidate_requests[0].validation_statuses == ["approved"]
    assert outcome.projection.confidence == 0.81
    assert "Publisher A AI Commerce Report, page 2" in outcome.projection.body_html
    assert candidate.candidate_id not in outcome.projection.body_html


def test_publish_signal_projection_live_builds_payload_and_reuses_idempotency(
    tmp_path,
    run_context,
    publish_settings_factory,
) -> None:
    from src.generators.signal_post_generator import build_signal_publish_projection

    settings = publish_settings_factory(validation_policy="warn")
    settings = replace(settings, wp=replace(settings.wp, post_type="ml_report"))
    projection = build_signal_publish_projection(
        _generation_request(),
        _projected_data(),
        run_context,
    )
    publish_calls = []

    def _lookup(request, ctx):
        assert request.post_type == "ml_signal"
        return WordPressPostLookupResponse(
            schema_version="1.0",
            found=False,
            post_id=None,
            link=None,
        )

    def _publish(request, settings, ctx):
        publish_calls.append((request, settings))
        return PublishOutcome(
            schema_version="1.0",
            html_path=request.html_path,
            file_id=request.file_id,
            status="published",
            post_id=77,
            post_url="https://example.com/signals/ai-commerce-checkout-behavior-signal/",
        )

    first = publish_signal_projection(
        projection,
        _signal_card(projection),
        settings,
        run_context,
        dry_run=False,
        publish_html_fn=_publish,
        find_post_by_file_id_fn=_lookup,
        ensure_taxonomy_terms_fn=_ensure_taxonomy,
        ensure_tags_fn=_ensure_tags,
        sleep_fn=lambda seconds: None,
    )
    second = publish_signal_projection(
        projection,
        _signal_card(projection),
        settings,
        run_context,
        dry_run=False,
        publish_html_fn=_publish,
        find_post_by_file_id_fn=_lookup,
        ensure_taxonomy_terms_fn=_ensure_taxonomy,
        ensure_tags_fn=_ensure_tags,
        sleep_fn=lambda seconds: None,
    )

    publish_request, publish_settings = publish_calls[0]
    assert first.status == "published"
    assert first.target_post_type == "ml_signal"
    assert first.target_slug == "ai-commerce-checkout-behavior-signal"
    assert second.idempotency_reused is True
    assert len(publish_calls) == 1
    assert publish_settings.wp.post_type == "ml_signal"
    assert publish_request.slug == "ai-commerce-checkout-behavior-signal"
    assert publish_request.resolved_terms.category_ids == [11]
    assert publish_request.resolved_terms.tag_ids == [31]
    assert publish_request.resolved_terms.taxonomy_terms == {"ml_publisher": [21, 22]}
    assert publish_request.html_snapshot is not None
    assert (
        publish_request.html_snapshot.signal_card["summary"]
        == projection.card_content.summary
    )


def test_publish_signal_projection_rejects_url_outside_signals_section(
    tmp_path,
    run_context,
    publish_settings_factory,
) -> None:
    from src.generators.signal_post_generator import build_signal_publish_projection

    projection = build_signal_publish_projection(
        _generation_request(),
        _projected_data(),
        run_context,
    )

    def _publish(request, settings, ctx):
        return PublishOutcome(
            schema_version="1.0",
            html_path=request.html_path,
            file_id=request.file_id,
            status="published",
            post_id=77,
            post_url="https://example.com/reports/ai-commerce-checkout-behavior-signal/",
        )

    result = publish_signal_projection(
        projection,
        _signal_card(projection),
        publish_settings_factory(validation_policy="warn"),
        run_context,
        dry_run=False,
        publish_html_fn=_publish,
        find_post_by_file_id_fn=lambda request, ctx: WordPressPostLookupResponse(
            schema_version="1.0",
            found=False,
            post_id=None,
            link=None,
        ),
        ensure_taxonomy_terms_fn=_ensure_taxonomy,
        ensure_tags_fn=_ensure_tags,
        sleep_fn=lambda seconds: None,
    )

    assert isinstance(result, CrossReportPublishResultSummary)
    assert result.status == "error"
    assert result.error_code == "signal_publish_url_mismatch"
    assert result.post_id is None
