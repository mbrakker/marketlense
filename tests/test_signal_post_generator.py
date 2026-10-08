from __future__ import annotations

from dataclasses import asdict, replace

import pytest

from src.contracts.cross_report_analysis import (
    CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
    CrossReportEvidenceReference,
    CrossReportProjectedDataReadResponse,
    CrossReportSourceReportCandidate,
)
from src.contracts.signal_candidates import (
    SIGNAL_CANDIDATE_SCHEMA_VERSION,
    SignalCandidate,
    SignalCandidateGroup,
    SignalCandidateReadResponse,
    SignalCandidateSourceRef,
)
from src.contracts.wordpress_entities import (
    WORDPRESS_ENTITY_SCHEMA_VERSION,
    SignalPostGenerationRequest,
    SignalPublishProjection,
    SignalSourceAttribution,
)
from src.generators.signal_post_generator import build_signal_publish_projection
from src.orchestrators._publish_orchestrator.cross_report import (
    _signal_projection_package,
)
from src.utils.errors import AppError


def _candidate(
    report_id: str,
    *,
    publisher: str,
    evidence_count: int = 2,
    category_ids: list[str] | None = None,
    category_labels: list[str] | None = None,
    tags: list[str] | None = None,
) -> CrossReportSourceReportCandidate:
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
        category_labels=category_labels or ["Retail Strategy"],
        tags=tags or ["AI Commerce"],
        evidence_count=evidence_count,
        claim_count=evidence_count,
        finding_count=0,
        quote_count=0,
        metric_count=0,
        recency_score=0.0,
        relevance_score=0.0,
        diversity_score=0.0,
        density_score=float(evidence_count),
        total_score=0.0,
        selection_reasons=["projection_status:projected"],
        rejection_reasons=[],
        category_ids=category_ids or ["retail-strategy"],
    )


def _evidence(
    evidence_id: str, *, report_id: str, publisher: str
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
        text=(
            f"{publisher} reports that AI commerce adoption is changing checkout "
            "behavior."
        ),
        source_metadata={
            "pages": [2],
            "evidence": "projected claim",
            "source_url": f"https://sources.example/{report_id}",
        },
    )


def _projected_data() -> CrossReportProjectedDataReadResponse:
    return CrossReportProjectedDataReadResponse(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        source_candidates=[
            _candidate("report-a", publisher="Publisher A"),
            _candidate("report-b", publisher="Publisher B"),
        ],
        evidence=[
            _evidence(
                "report-a:claim:1", report_id="report-a", publisher="Publisher A"
            ),
            _evidence(
                "report-b:claim:1", report_id="report-b", publisher="Publisher B"
            ),
        ],
        raw_metrics=[],
        content_hashes={},
        excluded_report_counts={},
    )


def _request() -> SignalPostGenerationRequest:
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


def _frozen_request(**changes: object) -> SignalPostGenerationRequest:
    request = SignalPostGenerationRequest(
        **{
            **_request().__dict__,
            "candidate_group_id": "signal-group:ai-commerce",
            "extraction_request_id": "extract-ai-commerce",
            "candidate_ids": ["signal-candidate:ai-commerce"],
            "source_report_ids": ["report-a", "report-b"],
            "evidence_ids": ["report-a:claim:1", "report-b:claim:1"],
            "topic_ids": ["retail-strategy"],
            "source_category_ids": {
                "report-a": ["retail-strategy"],
                "report-b": ["retail-strategy"],
            },
        }
    )
    return SignalPostGenerationRequest(**{**request.__dict__, **changes})


def _frozen_candidate_data(
    *, publication_status: str = "eligible", hold_reason: str = ""
) -> SignalCandidateReadResponse:
    candidate = SignalCandidate(
        schema_version=SIGNAL_CANDIDATE_SCHEMA_VERSION,
        candidate_id="signal-candidate:ai-commerce",
        candidate_type="market_signal",
        title="AI commerce adoption",
        summary="AI commerce adoption is changing checkout behavior.",
        confidence=0.84,
        strength=4.2,
        support_level="multi_report_convergent",
        caveats=["coverage_limited_to_selected_projected_reports"],
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
            ),
            SignalCandidateSourceRef(
                schema_version=SIGNAL_CANDIDATE_SCHEMA_VERSION,
                report_id="report-b",
                evidence_id="report-b:claim:1",
                source_table="report_claims",
                entity_uid="report-b:claim:1",
                content_class="claim",
                page_refs=[2],
                source_metadata={"pages": [2]},
            ),
        ],
        raw_source_context={
            "evidence": [asdict(item) for item in _projected_data().evidence]
        },
        validation_status="approved",
        validation_notes=["source_backed"],
        group_id="signal-group:ai-commerce",
        extraction_request_id="extract-ai-commerce",
        generated_at_utc="2026-06-02T12:00:00Z",
    )
    group = SignalCandidateGroup(
        schema_version=SIGNAL_CANDIDATE_SCHEMA_VERSION,
        group_id="signal-group:ai-commerce",
        stable_key="ai-commerce",
        title="AI commerce adoption",
        summary="AI commerce adoption is changing checkout behavior.",
        support_level="multi_report_convergent",
        candidate_ids=[candidate.candidate_id],
        source_report_ids=["report-a", "report-b"],
        evidence_ids=["report-a:claim:1", "report-b:claim:1"],
        caveats=["coverage_limited_to_selected_projected_reports"],
        raw_group_context={"agreement_type": "convergent"},
        validation_status="approved",
        extraction_request_id="extract-ai-commerce",
        generated_at_utc="2026-06-02T12:00:00Z",
        topic="AI commerce checkout behavior",
        topic_ids=["retail-strategy"],
        source_category_ids={
            "report-a": ["retail-strategy"],
            "report-b": ["retail-strategy"],
        },
        publication_status=publication_status,
        publication_hold_reason=hold_reason,
    )
    return SignalCandidateReadResponse(
        schema_version=SIGNAL_CANDIDATE_SCHEMA_VERSION,
        db_path="state/signals.sqlite",
        candidates=[candidate],
        groups=[group],
    )


def test_signal_generator_builds_grounded_publish_projection(
    run_context,
    assert_no_defaulted_required_fields,
) -> None:
    projection = build_signal_publish_projection(
        _request(),
        _projected_data(),
        run_context,
    )

    assert isinstance(projection, SignalPublishProjection)
    assert_no_defaulted_required_fields(projection)
    assert projection.schema_version == WORDPRESS_ENTITY_SCHEMA_VERSION
    assert projection.target_route == "wordpress:ml_signal"
    assert projection.title == "AI commerce checkout behavior signal"
    assert projection.slug == "ai-commerce-checkout-behavior-signal"
    assert projection.evidence_ids == ["report-a:claim:1", "report-b:claim:1"]
    assert projection.source_report_ids == ["report-a", "report-b"]
    assert projection.topic_ids == ["retail-strategy"]
    assert projection.topic_labels == ["Retail Strategy"]
    assert projection.tag_labels == ["AI Commerce"]
    assert projection.publisher_labels == ["Publisher A", "Publisher B"]
    assert projection.source_attributions == [
        SignalSourceAttribution(report_id="report-a", publisher="Publisher A"),
        SignalSourceAttribution(report_id="report-b", publisher="Publisher B"),
    ]
    assert projection.validation_status == "approved"
    assert projection.confidence >= 0.7
    assert projection.card_content.summary
    assert projection.card_content.source_count == 2
    assert projection.card_content.evidence_count == 2
    assert projection.card_content.fingerprint.geometry_family
    assert "projected evidence" in projection.uncertainty
    assert "Publisher A AI Commerce Report, page 2" in projection.body_html
    assert "report-a:claim:1" not in projection.body_html
    assert "Publisher A" in projection.body_html
    direct_package = _signal_projection_package(
        projection, asdict(projection.card_content)
    )
    assert direct_package.source_metadata == [
        {"report_id": "report-a", "publisher": "Publisher A"},
        {"report_id": "report-b", "publisher": "Publisher B"},
    ]


def test_signal_generator_rejects_insufficient_grounding(run_context) -> None:
    projected_data = CrossReportProjectedDataReadResponse(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        source_candidates=[_candidate("report-a", publisher="Publisher A")],
        evidence=[
            _evidence("report-a:claim:1", report_id="report-a", publisher="Publisher A")
        ],
        raw_metrics=[],
        content_hashes={},
        excluded_report_counts={},
    )

    with pytest.raises(AppError) as exc_info:
        build_signal_publish_projection(_request(), projected_data, run_context)

    assert exc_info.value.code == "signal_grounding_insufficient"
    assert exc_info.value.retryable is False
    assert exc_info.value.severity == "error"


def test_signal_generator_rejects_relaxed_single_source_minimum(run_context) -> None:
    projected_data = CrossReportProjectedDataReadResponse(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        source_candidates=[_candidate("report-a", publisher="Publisher A")],
        evidence=[
            _evidence(
                "report-a:claim:1", report_id="report-a", publisher="Publisher A"
            ),
            _evidence(
                "report-a:claim:2", report_id="report-a", publisher="Publisher A"
            ),
        ],
        raw_metrics=[],
        content_hashes={},
        excluded_report_counts={},
    )
    request = _request()
    request = SignalPostGenerationRequest(
        **{**request.__dict__, "minimum_source_reports": 1}
    )

    with pytest.raises(AppError) as exc_info:
        build_signal_publish_projection(request, projected_data, run_context)

    assert exc_info.value.code == "signal_publication_minimum_invalid"
    assert exc_info.value.retryable is False


def test_frozen_multi_source_signal_uses_exact_manifest_and_replays_idempotently(
    run_context,
) -> None:
    projected_data = _projected_data()
    distractor = _candidate(
        "report-c",
        publisher="Publisher C",
        evidence_count=20,
        category_ids=["finance"],
        category_labels=["Finance"],
        tags=["Other topic"],
    )
    projected_data = CrossReportProjectedDataReadResponse(
        schema_version=projected_data.schema_version,
        source_candidates=[*projected_data.source_candidates, distractor],
        evidence=[
            *projected_data.evidence,
            _evidence(
                "report-c:claim:1", report_id="report-c", publisher="Publisher C"
            ),
        ],
        raw_metrics=[],
        content_hashes={},
        excluded_report_counts={},
    )
    request = _frozen_request(max_source_reports=1, max_evidence_items=1)
    candidate_data = _frozen_candidate_data()

    first = build_signal_publish_projection(
        request, projected_data, run_context, candidate_data=candidate_data
    )
    replay = build_signal_publish_projection(
        request, projected_data, run_context, candidate_data=candidate_data
    )

    assert first == replay
    assert first.source_report_ids == ["report-a", "report-b"]
    assert first.evidence_ids == ["report-a:claim:1", "report-b:claim:1"]


def test_same_topic_frozen_signal_groups_have_distinct_publication_identities(
    run_context,
) -> None:
    first_request = _frozen_request()
    first_data = _frozen_candidate_data()
    first = build_signal_publish_projection(
        first_request, _projected_data(), run_context, candidate_data=first_data
    )

    candidate_id = "signal-candidate:ai-commerce:second"
    group_id = "signal-group:ai-commerce:second"
    second_request = _frozen_request(
        candidate_ids=[candidate_id], candidate_group_id=group_id
    )
    second_candidate = replace(
        first_data.candidates[0], candidate_id=candidate_id, group_id=group_id
    )
    second_group = replace(
        first_data.groups[0],
        group_id=group_id,
        stable_key="ai-commerce:second",
        candidate_ids=[candidate_id],
    )
    second_data = replace(
        first_data, candidates=[second_candidate], groups=[second_group]
    )
    second = build_signal_publish_projection(
        second_request, _projected_data(), run_context, candidate_data=second_data
    )

    assert first.title == second.title == "AI commerce checkout behavior signal"
    assert first.slug != second.slug
    assert first.file_id != second.file_id


def test_frozen_signal_rejects_stored_manifest_changes(run_context) -> None:
    candidate_data = _frozen_candidate_data()
    changed_group = replace(
        candidate_data.groups[0], candidate_ids=["signal-candidate:changed"]
    )
    changed_candidate_data = replace(candidate_data, groups=[changed_group])

    with pytest.raises(AppError) as exc_info:
        build_signal_publish_projection(
            _frozen_request(),
            _projected_data(),
            run_context,
            candidate_data=changed_candidate_data,
        )

    assert exc_info.value.code == "signal_frozen_manifest_changed"
    assert exc_info.value.retryable is False


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("source", "signal_frozen_manifest_source_missing"),
        ("evidence", "signal_frozen_manifest_evidence_missing"),
    ],
)
def test_frozen_signal_rejects_sources_or_evidence_removed_after_approval(
    run_context, mutation: str, expected_code: str
) -> None:
    projected_data = _projected_data()
    if mutation == "source":
        projected_data = CrossReportProjectedDataReadResponse(
            schema_version=projected_data.schema_version,
            source_candidates=[projected_data.source_candidates[0]],
            evidence=projected_data.evidence,
            raw_metrics=[],
            content_hashes={},
            excluded_report_counts={},
        )
    else:
        projected_data = CrossReportProjectedDataReadResponse(
            schema_version=projected_data.schema_version,
            source_candidates=projected_data.source_candidates,
            evidence=projected_data.evidence[:1],
            raw_metrics=[],
            content_hashes={},
            excluded_report_counts={},
        )

    with pytest.raises(AppError) as exc_info:
        build_signal_publish_projection(
            _frozen_request(),
            projected_data,
            run_context,
            candidate_data=_frozen_candidate_data(),
        )

    assert exc_info.value.code == expected_code
    assert exc_info.value.retryable is False


def test_frozen_signal_rejects_evidence_changed_after_approval(run_context) -> None:
    projected_data = _projected_data()
    changed_evidence = replace(
        projected_data.evidence[0],
        text="Changed projected evidence with the same frozen evidence ID.",
    )
    changed_projected_data = CrossReportProjectedDataReadResponse(
        schema_version=projected_data.schema_version,
        source_candidates=projected_data.source_candidates,
        evidence=[changed_evidence, *projected_data.evidence[1:]],
        raw_metrics=[],
        content_hashes={},
        excluded_report_counts={},
    )

    with pytest.raises(AppError) as exc_info:
        build_signal_publish_projection(
            _frozen_request(),
            changed_projected_data,
            run_context,
            candidate_data=_frozen_candidate_data(),
        )

    assert exc_info.value.code == "signal_frozen_manifest_evidence_changed"
    assert exc_info.value.retryable is False


def test_frozen_signal_rejects_source_content_changed_after_approval(
    run_context,
) -> None:
    projected_data = _projected_data()
    changed_source = replace(
        projected_data.source_candidates[0],
        content_hash="changed-report-content-hash",
    )
    changed_projected_data = replace(
        projected_data,
        source_candidates=[changed_source, *projected_data.source_candidates[1:]],
    )
    candidate_data = _frozen_candidate_data()
    group = candidate_data.groups[0]
    candidate_data = replace(
        candidate_data,
        groups=[
            replace(
                group,
                raw_group_context={
                    **group.raw_group_context,
                    "source_content_hashes": {
                        "report-a": "report-a-hash",
                        "report-b": "report-b-hash",
                    },
                },
            )
        ],
        manifest_sha256="a" * 64,
    )

    with pytest.raises(AppError) as exc_info:
        build_signal_publish_projection(
            _frozen_request(candidate_manifest_sha256="a" * 64),
            changed_projected_data,
            run_context,
            candidate_data=candidate_data,
        )

    assert exc_info.value.code == "signal_frozen_manifest_source_changed"
    assert exc_info.value.retryable is False


def test_frozen_signal_rejects_request_filters_incompatible_with_group(
    run_context,
) -> None:
    with pytest.raises(AppError) as exc_info:
        build_signal_publish_projection(
            _frozen_request(category_filters=["Finance"]),
            _projected_data(),
            run_context,
            candidate_data=_frozen_candidate_data(),
        )

    assert exc_info.value.code == "signal_frozen_manifest_filter_mismatch"
    assert exc_info.value.retryable is False


def test_frozen_signal_rejects_topic_category_relationship_changes(run_context) -> None:
    projected_data = _projected_data()
    changed_source = replace(
        projected_data.source_candidates[0],
        category_ids=["different-category"],
        category_labels=["Different Category"],
    )
    changed_projected_data = replace(
        projected_data,
        source_candidates=[changed_source, *projected_data.source_candidates[1:]],
    )

    with pytest.raises(AppError) as exc_info:
        build_signal_publish_projection(
            _frozen_request(category_filters=[]),
            changed_projected_data,
            run_context,
            candidate_data=_frozen_candidate_data(),
        )

    assert exc_info.value.code == "signal_frozen_manifest_topic_category_changed"
    assert exc_info.value.retryable is False


def test_single_source_group_is_rejected_with_typed_grounding_reason(
    run_context,
) -> None:
    with pytest.raises(AppError) as exc_info:
        build_signal_publish_projection(
            _frozen_request(
                source_report_ids=["report-a"],
                evidence_ids=["report-a:claim:1", "report-a:claim:2"],
                source_category_ids={"report-a": ["retail-strategy"]},
            ),
            CrossReportProjectedDataReadResponse(
                schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
                source_candidates=[_candidate("report-a", publisher="Publisher A")],
                evidence=[
                    _evidence(
                        "report-a:claim:1",
                        report_id="report-a",
                        publisher="Publisher A",
                    ),
                    _evidence(
                        "report-a:claim:2",
                        report_id="report-a",
                        publisher="Publisher A",
                    ),
                ],
                raw_metrics=[],
                content_hashes={},
                excluded_report_counts={},
            ),
            run_context,
            candidate_data=_frozen_candidate_data(
                publication_status="held",
                hold_reason="signal_grounding_insufficient",
            ),
        )

    assert exc_info.value.code == "signal_grounding_insufficient"
    assert exc_info.value.retryable is False


def test_signal_generator_reuses_stored_signal_candidates(run_context) -> None:
    candidate = SignalCandidate(
        schema_version=SIGNAL_CANDIDATE_SCHEMA_VERSION,
        candidate_id="signal-candidate:theme-ai:signal-ai",
        candidate_type="market_signal",
        title="AI commerce adoption",
        summary="Stored candidate summary from projected reports.",
        confidence=0.84,
        strength=4.2,
        support_level="multi_report_divergent",
        caveats=["opposed_directional_language"],
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
        summary="Stored group summary.",
        support_level="multi_report_divergent",
        candidate_ids=[candidate.candidate_id],
        source_report_ids=["report-a", "report-b"],
        evidence_ids=["report-a:claim:1", "report-b:claim:1"],
        caveats=["opposed_directional_language"],
        raw_group_context={"agreement_type": "divergent"},
        validation_status="approved",
        extraction_request_id="extract-ai",
        generated_at_utc="2026-06-02T12:00:00Z",
    )

    projection = build_signal_publish_projection(
        _request(),
        _projected_data(),
        run_context,
        candidate_data=SignalCandidateReadResponse(
            schema_version=SIGNAL_CANDIDATE_SCHEMA_VERSION,
            db_path="state/reports.sqlite",
            candidates=[candidate],
            groups=[group],
        ),
    )

    assert projection.evidence_ids == ["report-a:claim:1", "report-b:claim:1"]
    assert projection.source_report_ids == ["report-a", "report-b"]
    assert projection.confidence == 0.84
    assert "opposed_directional_language" in projection.uncertainty
    assert "Publisher A AI Commerce Report, page 2" in projection.body_html
    assert candidate.candidate_id not in projection.body_html
    assert group.group_id not in projection.body_html


def test_signal_generator_keeps_stored_candidate_source_lineage_after_reranking(
    run_context,
) -> None:
    projected_data = CrossReportProjectedDataReadResponse(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        source_candidates=[
            _candidate("report-a", publisher="Publisher A", evidence_count=2),
            _candidate("report-b", publisher="Publisher B", evidence_count=10),
            _candidate("report-c", publisher="Publisher C", evidence_count=2),
        ],
        evidence=[
            _evidence(
                "report-a:claim:1", report_id="report-a", publisher="Publisher A"
            ),
            _evidence(
                "report-c:claim:1", report_id="report-c", publisher="Publisher C"
            ),
        ],
        raw_metrics=[],
        content_hashes={},
        excluded_report_counts={},
    )
    candidate = SignalCandidate(
        schema_version=SIGNAL_CANDIDATE_SCHEMA_VERSION,
        candidate_id="signal-candidate:theme-ai:signal-ai",
        candidate_type="market_signal",
        title="AI commerce adoption",
        summary="Stored candidate summary from projected reports.",
        confidence=0.8,
        strength=4.0,
        support_level="multi_report_convergent",
        caveats=["coverage_limited_to_selected_projected_reports"],
        source_report_ids=["report-a", "report-c"],
        evidence_ids=["report-a:claim:1", "report-c:claim:1"],
        source_refs=[
            SignalCandidateSourceRef(
                schema_version=SIGNAL_CANDIDATE_SCHEMA_VERSION,
                report_id="report-c",
                evidence_id="report-c:claim:1",
                source_table="report_claims",
                entity_uid="report-c:claim:1",
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
        summary="Stored group summary.",
        support_level="multi_report_convergent",
        candidate_ids=[candidate.candidate_id],
        source_report_ids=["report-a", "report-c"],
        evidence_ids=["report-a:claim:1", "report-c:claim:1"],
        caveats=["coverage_limited_to_selected_projected_reports"],
        raw_group_context={"agreement_type": "convergent"},
        validation_status="approved",
        extraction_request_id="extract-ai",
        generated_at_utc="2026-06-02T12:00:00Z",
    )

    projection = build_signal_publish_projection(
        SignalPostGenerationRequest(**{**_request().__dict__, "max_source_reports": 2}),
        projected_data,
        run_context,
        candidate_data=SignalCandidateReadResponse(
            schema_version=SIGNAL_CANDIDATE_SCHEMA_VERSION,
            db_path="state/reports.sqlite",
            candidates=[candidate],
            groups=[group],
        ),
    )

    assert projection.source_report_ids == ["report-a", "report-c"]
    assert projection.publisher_labels == ["Publisher A", "Publisher C"]
