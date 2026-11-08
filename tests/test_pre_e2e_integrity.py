# ruff: noqa: F401
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, replace

import pytest

from src.contracts.report_assets import RenderRequest
from src.generators.public_editorial_quality_generator import (
    _metric_label_relationship_explanation,
    _preferred_metric_relationship_evidence,
    evaluate_public_editorial_quality,
    public_editorial_report_review_scope,
    public_editorial_semantic_review_items,
    public_html_quality_issues,
)
from src.generators.report_render_generator import (
    _verified_render_authority,
    render_report_output,
)
from src.orchestrators._report_analysis_orchestrator.validation import (
    _public_editorial_review_issue,
    _substantive_public_review_reason,
    _validate_public_editorial_review_payload,
)
from src.services._render_service.view import _build_render_view
from src.utils.errors import AppError
from src.utils.verified_facts import build_verified_authority_context
from tests._test_pre_e2e_integrity.cases_01_public_surfaces_and_status import (
    _add_valid_obligation_contract,
    _report_review_verdict,
    _valid_report_review_payload,
    test_public_item_status_contract_is_fail_closed,
    test_public_report_status_contract_is_fail_closed,
    test_semantic_review_projection_includes_all_public_surface_fields,
    test_semantic_review_projection_matches_rendered_material_surfaces,
    test_verified_render_does_not_fallback_to_legacy_public_content,
    test_verified_signal_review_and_renderer_omit_unbound_topic_copy,
)
from tests._test_pre_e2e_integrity.cases_04_public_repair_and_render_contract import (
    test_derived_metric_claim_context_and_advisory,
    test_public_advisory_implications_route_to_unique_insight_leaves,
    test_public_derived_claim_routes_to_supported_insight_source,
    test_public_renderer_retains_complete_metric_context_and_status,
    test_public_review_uses_render_limits_and_one_complete_metric_card,
    test_unsupported_derived_public_target_fails_closed_without_planner_crash,
    test_verified_expert_context_falls_back_to_fact_qualifiers,
    test_verified_projection_covers_rendered_families_and_ambiguous_sources,
    test_verified_render_does_not_promote_discovery_methodology_or_chapter_copy,
)
from tests._test_report_render_generator._split_support_cases_01_render_output_and_cards import (  # noqa: E501
    _analysis,
    _deps,
    _runtime,
    _selection,
    _source,
)
from tests._test_validation_generator._shared import _ctx
from tests.test_verified_facts_validation_authority import _authority_artifacts


def test_verified_review_and_renderer_share_visible_topic_projection(tmp_path) -> None:
    artifacts = _authority_artifacts()
    evidence_id = "verified-fact:fact-1"
    artifacts.update(
        {
            "toc_topics": ["Adoption"],
            "toc_topics_expanded": [
                {"title": "Adoption", "summary": "Unreviewed TOC copy."}
            ],
            "topics_covered": [
                {
                    "topic": "Adoption",
                    "status": "source_backed",
                    "evidence_id": evidence_id,
                    "why_it_matters": "Reviewed source-backed topic copy.",
                    "subtopics": ["A supported subrelationship."],
                    "pages": [4],
                }
            ],
        }
    )

    request = RenderRequest(
        schema_version="1.0",
        data={"title": "Projection parity", "artifacts": artifacts},
        doc_name="projection-parity.pdf",
        file_id="projection-parity",
        out_dir=str(tmp_path),
    )
    view = _build_render_view(request, {})
    review_items = public_editorial_semantic_review_items(artifacts)
    review_topic = next(
        item for item in review_items if item["artifact"] == "topics_covered"
    )
    rendered_topic = view["signal_cards"][0]
    rendered_text = " ".join(
        value
        for value in (
            rendered_topic.get("title"),
            rendered_topic.get("summary"),
            rendered_topic.get("source_label"),
        )
        if value
    )

    assert "Unreviewed TOC copy." not in rendered_text
    assert "Reviewed source-backed topic copy." in rendered_text
    assert "Reviewed source-backed topic copy." in review_topic["text"]
    assert "A supported subrelationship." in review_topic["text"]


def test_verified_summary_review_matches_the_three_visible_claim_rows() -> None:
    artifacts = _authority_artifacts()
    evidence_id = "verified-fact:fact-1"
    artifacts["summary"] = {
        "claim_evidence_map": [
            {"claim": f"Visible claim {index}.", "evidence_id": evidence_id}
            for index in range(1, 6)
        ]
    }

    items = public_editorial_semantic_review_items(artifacts)
    summary_items = [item for item in items if item["artifact"] == "summary"]

    assert [item["text"] for item in summary_items] == [
        "Visible claim 1.",
        "Visible claim 2.",
        "Visible claim 3.",
    ]


def test_verified_claim_map_uses_bound_secondary_evidence_id() -> None:
    artifacts = _authority_artifacts()
    artifacts["summary"] = {
        "claim_evidence_map": [
            {
                "claim": "A claim with a secondary authoritative binding.",
                "evidence_id": "legacy-unbound-id",
                "evidence_ids": ["verified-fact:fact-1"],
            }
        ]
    }

    view = _build_render_view(
        RenderRequest(
            schema_version="1.0",
            data={"title": "Bound claim map", "artifacts": artifacts},
            doc_name="bound-claim-map.pdf",
            file_id="bound-claim-map",
            out_dir="",
        ),
        {},
    )

    assert view["summary"]["claim_map"] == [
        {
            "claim": "A claim with a secondary authoritative binding.",
            "evidence_id": "verified-fact:fact-1",
            "evidence": "",
            "citation_line": "Bound claim map",
        }
    ]


def test_public_review_explicit_empty_evidence_does_not_borrow_item_binding() -> None:
    issue = _public_editorial_review_issue(
        report_id="report-1",
        item={
            "public_item_id": "insights:fact-1",
            "artifact": "insights_final",
            "field": "insights:fact-1",
            "evidence_ids": ["verified-fact:fact-1"],
            "evidence_text": "Canonical evidence.",
        },
        rule_id="public_editorial_quality.material_claim_evidence_missing",
        severity="error",
        hard_fail_class="missing_evidence",
        explanation=(
            "The model explicitly reported that source evidence is unavailable."
        ),
        evidence_ids=[],
        repair_target="insights_bundle",
    )

    assert issue.evidence_ids == []
    assert issue.repair_eligible is False
    assert issue.repair_target == ""


def test_public_review_reason_validation_is_structural_not_word_count() -> None:
    assert _substantive_public_review_reason("Pass") is True
    assert _substantive_public_review_reason("   ") is False


def test_public_report_review_requires_complete_scope_verdict() -> None:
    artifacts = _authority_artifacts()
    items = public_editorial_semantic_review_items(artifacts)
    scope = public_editorial_report_review_scope(
        artifacts,
        items,
        source_identity=artifacts["verified_facts"][0]["source_identity"],
    )
    payload = {
        "verdicts": [
            {
                "item_id": str(item["public_item_id"]),
                "status": "pass",
                "classification": "factual_claim",
                "severity": "info",
                "rule_id": "",
                "hard_fail_class": "",
                "reason": "The final item is supported by its retained evidence.",
                "evidence_ids": list(item.get("evidence_ids") or []),
                "repair_target": "",
            }
            for item in items
        ]
    }

    with pytest.raises(AppError) as raised:
        _validate_public_editorial_review_payload(payload, items, _ctx(), scope)

    assert raised.value.code == "public_editorial_quality_report_review_incomplete"


def test_public_report_review_coverage_diagnostics_show_counts() -> None:
    artifacts = _authority_artifacts()
    items = public_editorial_semantic_review_items(artifacts)
    scope = public_editorial_report_review_scope(artifacts, items)
    payload = {
        "verdicts": [
            {
                "item_id": str(item["public_item_id"]),
                "status": "pass",
                "classification": "factual_claim",
                "severity": "info",
                "rule_id": "",
                "hard_fail_class": "",
                "reason": "The final item remains supported by retained evidence.",
                "evidence_ids": list(item.get("evidence_ids") or []),
                "repair_target": "",
            }
            for item in items[:-1]
        ],
        "report_verdict": _report_review_verdict(evidence_ids=["verified-fact:fact-1"]),
    }

    with pytest.raises(AppError) as raised:
        _validate_public_editorial_review_payload(payload, items, _ctx(), scope)

    assert raised.value.code == "public_editorial_quality_review_coverage_mismatch"
    assert raised.value.context["expected_item_count"] == len(items)
    assert raised.value.context["actual_item_count"] == len(payload["verdicts"])
    assert raised.value.context["missing_item_ids"] == [
        str(items[-1]["public_item_id"])
    ]


def test_unlocalized_report_quality_failure_cannot_request_broad_repair() -> None:
    artifacts = _authority_artifacts()
    items = public_editorial_semantic_review_items(artifacts)
    scope = public_editorial_report_review_scope(artifacts, items)
    payload = {
        "verdicts": [
            {
                "item_id": str(item["public_item_id"]),
                "status": "pass",
                "classification": "factual_claim",
                "severity": "info",
                "rule_id": "",
                "hard_fail_class": "",
                "reason": "The final item is supported by its retained evidence.",
                "evidence_ids": list(item.get("evidence_ids") or []),
                "repair_target": "",
            }
            for item in items
        ],
        "report_verdict": _report_review_verdict(
            status="fail", evidence_ids=["verified-fact:fact-1"], coverage_status="fail"
        ),
    }
    _add_valid_obligation_contract(items, scope, payload)

    _validate_public_editorial_review_payload(payload, items, _ctx(), scope)
    issue = _public_editorial_review_issue(
        report_id="report-1",
        item=None,
        rule_id="public_editorial_quality.report_acceptance",
        severity="error",
        hard_fail_class="report_editorial_acceptance",
        explanation="The report omits a material admitted finding.",
        evidence_ids=["verified-fact:fact-1"],
        repair_target="",
    )

    assert issue.repair_eligible is False
    assert issue.repair_target == ""


def test_report_review_accepts_selective_material_coverage_with_targeted_failure() -> (
    None
):
    artifacts = _authority_artifacts()
    items = public_editorial_semantic_review_items(artifacts)
    scope = public_editorial_report_review_scope(artifacts, items)
    item = items[0]
    item_verdicts = [
        {
            "item_id": str(value["public_item_id"]),
            "status": "fail" if value is item else "pass",
            "classification": "factual_claim",
            "severity": "error" if value is item else "info",
            "rule_id": (
                "public_editorial_quality.semantic_integrity" if value is item else ""
            ),
            "hard_fail_class": "factual_error" if value is item else "",
            "reason": (
                "The targeted item needs a scoped editorial correction."
                if value is item
                else "The item remains source-grounded and materially useful."
            ),
            "evidence_ids": list(value.get("evidence_ids") or []),
            "repair_target": str(value["repair_target"]) if value is item else "",
        }
        for value in items
    ]
    payload = {
        "verdicts": item_verdicts,
        "report_verdict": _report_review_verdict(
            status="fail",
            evidence_ids=list(item.get("evidence_ids") or []),
            affected_item_id=str(item["public_item_id"]),
            repair_target=str(item["repair_target"]),
            coverage_status="fail",
        ),
    }
    _add_valid_obligation_contract(items, scope, payload)

    _validate_public_editorial_review_payload(payload, items, _ctx(), scope)
    issue = _public_editorial_review_issue(
        report_id="report-1",
        item=item,
        rule_id="public_editorial_quality.report_acceptance",
        severity="error",
        hard_fail_class="report_editorial_acceptance",
        explanation="One admitted finding needs a targeted editorial correction.",
        evidence_ids=list(item.get("evidence_ids") or []),
        repair_target=str(item["repair_target"]),
    )

    assert issue.repair_eligible is True
    assert issue.repair_target == item["repair_target"]
    assert issue.evidence_ids == item["evidence_ids"]


def test_report_scope_keeps_complete_facts_once_and_preserves_identity() -> None:
    artifacts = _authority_artifacts()
    items = public_editorial_semantic_review_items(artifacts)
    scope = public_editorial_report_review_scope(
        artifacts,
        [*items, {"public_item_id": ""}],
        source_identity="source-override",
        verified_fact_digest="digest-override",
    )

    assert scope["authority"] == "canonical_verified_facts"
    assert scope["source_identity"] == "source-override"
    assert scope["verified_fact_digest"] == "digest-override"
    assert list(scope["verified_facts"]) == ["verified-fact:fact-1"]
    assert "verified_facts" not in scope["public_content"][0]
    assert "text" not in scope["public_content"][0]
    assert scope["public_content"][0]["item_id"] == items[0]["public_item_id"]
    assert items[0]["text"]


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        (
            lambda payload: payload["report_verdict"].update(evidence_ids=[]),
            "public_editorial_quality_report_review_evidence_missing",
        ),
        (
            lambda payload: payload["report_verdict"].update(
                evidence_ids=["unbound-evidence"]
            ),
            "public_editorial_quality_report_review_evidence_mismatch",
        ),
        (
            lambda payload: payload["report_verdict"].update(
                status="pass",
                severity="error",
            ),
            "public_editorial_quality_report_review_status_conflict",
        ),
        (
            lambda payload: payload["report_verdict"].update(
                status="fail",
                severity="error",
                dimensions={
                    name: {
                        "status": "pass",
                        "reason": "Every required report dimension remains covered.",
                    }
                    for name in (
                        "material_coverage",
                        "analytical_depth",
                        "distinctness",
                        "limitations",
                    )
                },
            ),
            "public_editorial_quality_report_review_status_conflict",
        ),
    ],
)
def test_public_report_review_rejects_unsafe_report_verdicts(
    mutation, expected_code
) -> None:
    items, scope, payload = _valid_report_review_payload()
    mutation(payload)

    with pytest.raises(AppError) as raised:
        _validate_public_editorial_review_payload(payload, items, _ctx(), scope)

    assert raised.value.code == expected_code


def test_public_report_review_rejects_unlocalized_or_wrong_target_repairs() -> None:
    items, scope, payload = _valid_report_review_payload()
    item_id = str(items[0]["public_item_id"])
    item_evidence = list(items[0].get("evidence_ids") or [])

    unlocalized = deepcopy(payload)
    unlocalized["report_verdict"].update(
        status="fail",
        severity="error",
        evidence_ids=item_evidence,
        repair_target="insights_bundle",
        affected_item_id="",
        dimensions=_report_review_verdict(status="fail", coverage_status="fail")[
            "dimensions"
        ],
    )
    with pytest.raises(AppError) as raised:
        _validate_public_editorial_review_payload(unlocalized, items, _ctx(), scope)
    assert raised.value.code == "public_editorial_quality_report_review_target_mismatch"

    wrong_target = deepcopy(payload)
    wrong_target["report_verdict"].update(
        status="fail",
        severity="error",
        evidence_ids=item_evidence,
        affected_item_id=item_id,
        repair_target="wrong-target",
        dimensions=_report_review_verdict(status="fail", coverage_status="fail")[
            "dimensions"
        ],
    )
    with pytest.raises(AppError) as raised:
        _validate_public_editorial_review_payload(wrong_target, items, _ctx(), scope)
    assert raised.value.code == "public_editorial_quality_report_review_target_mismatch"


def test_verified_render_rejects_missing_authority_before_metadata_side_effect(
    tmp_path,
) -> None:
    runtime = _runtime(tmp_path, md5="source-md5")
    source_identity = "frozen-report|pdf-sha256:" + "a" * 64
    runtime = replace(
        runtime, ctx=replace(runtime.ctx, source_identity_id=source_identity)
    )
    source = _source(runtime)
    selection = _selection(runtime, source)
    artifacts = _authority_artifacts()
    analysis = replace(
        _analysis(runtime, source, selection),
        artifacts_payload=artifacts,
        evidence_packs=artifacts["_cache"]["visual_authority_canary"][
            "verified_evidence_packs"
        ],
    )
    metadata_calls: list[object] = []
    dependencies = _deps(
        upsert_report_metadata=lambda request, ctx: metadata_calls.append(
            (request, ctx)
        )
    )

    with pytest.raises(AppError) as raised:
        render_report_output(
            runtime,
            source,
            selection,
            analysis,
            dependencies,
            preview_resp=type("Preview", (), {"image_path": "", "page_number": 0})(),
        )

    assert raised.value.code == "verified_authority_context_missing"
    assert raised.value.retryable is False
    assert metadata_calls == []


def test_verified_render_rejects_authority_projection_mismatch_before_render(
    tmp_path,
) -> None:
    runtime = _runtime(tmp_path, md5="source-md5")
    source_identity = "frozen-report|pdf-sha256:" + "a" * 64
    runtime = replace(
        runtime, ctx=replace(runtime.ctx, source_identity_id=source_identity)
    )
    source = _source(runtime)
    selection = _selection(runtime, source)
    artifacts = _authority_artifacts()
    authority = build_verified_authority_context(
        artifacts, expected_source_identity=source_identity
    )
    analysis = replace(
        _analysis(runtime, source, selection),
        artifacts_payload=artifacts,
        authoritative_evidence_packs={"findings": {"stale": True}},
        verified_authority_context=authority,
    )
    render_calls: list[object] = []
    dependencies = _deps(
        render_report=lambda request, ctx: render_calls.append((request, ctx))
    )

    with pytest.raises(AppError) as raised:
        render_report_output(
            runtime,
            source,
            selection,
            analysis,
            dependencies,
            preview_resp=type("Preview", (), {"image_path": "", "page_number": 0})(),
        )

    assert raised.value.code == "verified_authority_projection_mismatch"
    assert raised.value.retryable is False
    assert render_calls == []


def test_normal_render_does_not_require_verified_authority(tmp_path) -> None:
    runtime = _runtime(tmp_path, md5="md5")
    source = _source(runtime)
    selection = _selection(runtime, source)
    analysis = _analysis(runtime, source, selection)
    dependencies = _deps(
        render_report=lambda request, ctx: (_ for _ in ()).throw(
            AssertionError("normal render should reach its existing path")
        )
    )

    with pytest.raises(AssertionError, match="existing path"):
        render_report_output(
            runtime,
            source,
            selection,
            analysis,
            dependencies,
            preview_resp=type("Preview", (), {"image_path": "", "page_number": 0})(),
        )


def test_verified_render_uses_authoritative_packs_for_factual_editorial_cards() -> None:
    artifacts = _authority_artifacts()
    authoritative = deepcopy(
        artifacts["_cache"]["visual_authority_canary"]["verified_evidence_packs"]
    )
    authoritative["findings"]["findings"][0]["statement"] = "CANONICAL VERIFIED FINDING"
    discovery = {
        "findings": {
            "findings": [
                {
                    "id": "discovery-finding",
                    "statement": "CONTRADICTORY DISCOVERY FINDING",
                }
            ]
        },
        "doc_map": {"title": "Discovery navigation title"},
    }

    view = _build_render_view(
        RenderRequest(
            schema_version="1.0",
            data={
                "title": "Verified render authority",
                "artifacts": artifacts,
                "evidence_packs": discovery,
                "authoritative_evidence_packs": authoritative,
            },
            doc_name="verified-render-authority.pdf",
            file_id="verified-render-authority",
            out_dir="",
        ),
        _ctx(),
    )

    findings = next(
        card["items"] for card in view["editorial_cards"] if card["label"] == "Findings"
    )
    rendered = " ".join(findings)
    assert "CANONICAL VERIFIED FINDING" in rendered
    assert "CONTRADICTORY DISCOVERY FINDING" not in rendered


def test_report_scope_labels_surface_roles_for_intentional_evidence_reuse() -> None:
    artifacts = _authority_artifacts()
    artifacts["summary"] = {
        "claim_evidence_map": [
            {
                "claim": "The same fact is oriented in the summary.",
                "evidence_id": "verified-fact:fact-1",
            }
        ]
    }
    artifacts["expert_comment"] = "The same fact is interpreted for decision-makers."
    artifacts["linkedin_post"] = "The same fact is distributed to a wider audience."
    items = public_editorial_semantic_review_items(artifacts)
    scope = public_editorial_report_review_scope(artifacts, items)

    roles = {
        entry["artifact"]: entry["surface_role"]
        for entry in scope["public_content"]
        if entry["artifact"]
        in {"summary", "insights_final", "expert_comment", "linkedin_post"}
    }
    assert roles["summary"] == "summary_or_orientation"
    assert roles["insights_final"] == "primary_analysis"
    assert roles["expert_comment"] == "expert_synthesis"
    assert roles["linkedin_post"] == "distribution_copy"
    assert scope["reuse_guidance"]


def test_verified_render_accepts_matching_canonical_authority_projection(
    tmp_path,
) -> None:
    runtime = _runtime(tmp_path, md5="source-md5")
    source_identity = "frozen-report|pdf-sha256:" + "a" * 64
    runtime = replace(
        runtime, ctx=replace(runtime.ctx, source_identity_id=source_identity)
    )
    source = _source(runtime)
    selection = _selection(runtime, source)
    artifacts = _authority_artifacts()
    authority = build_verified_authority_context(
        artifacts, expected_source_identity=source_identity
    )
    analysis = replace(
        _analysis(runtime, source, selection),
        artifacts_payload=artifacts,
        authoritative_evidence_packs=authority.evidence_packs,
        verified_authority_context=authority,
        data_dict={
            "authoritative_evidence_packs": authority.evidence_packs,
            "verified_authority_context": asdict(authority),
        },
    )

    assert _verified_render_authority(runtime, analysis) == authority


def test_verified_render_accepts_exact_base_runtime_identity(
    tmp_path,
) -> None:
    runtime = _runtime(tmp_path, md5="source-md5")
    qualified_identity = "frozen-report|pdf-sha256:" + "a" * 64
    runtime = replace(
        runtime, ctx=replace(runtime.ctx, source_identity_id="frozen-report")
    )
    source = _source(runtime)
    selection = _selection(runtime, source)
    artifacts = _authority_artifacts()
    authority = build_verified_authority_context(
        artifacts, expected_source_identity=qualified_identity
    )
    analysis = replace(
        _analysis(runtime, source, selection),
        artifacts_payload=artifacts,
        authoritative_evidence_packs=authority.evidence_packs,
        verified_authority_context=authority,
        data_dict={
            "authoritative_evidence_packs": authority.evidence_packs,
            "verified_authority_context": asdict(authority),
        },
    )

    assert _verified_render_authority(runtime, analysis) == authority


def test_verified_render_rejects_wrong_qualified_runtime_identity(
    tmp_path,
) -> None:
    runtime = _runtime(tmp_path, md5="source-md5")
    authority_identity = "frozen-report|pdf-sha256:" + "a" * 64
    runtime = replace(
        runtime,
        ctx=replace(
            runtime.ctx,
            source_identity_id="frozen-report|pdf-sha256:" + "b" * 64,
        ),
    )
    source = _source(runtime)
    selection = _selection(runtime, source)
    artifacts = _authority_artifacts()
    authority = build_verified_authority_context(
        artifacts, expected_source_identity=authority_identity
    )
    analysis = replace(
        _analysis(runtime, source, selection),
        artifacts_payload=artifacts,
        authoritative_evidence_packs=authority.evidence_packs,
        verified_authority_context=authority,
        data_dict={
            "authoritative_evidence_packs": authority.evidence_packs,
            "verified_authority_context": asdict(authority),
        },
    )

    with pytest.raises(AppError) as raised:
        _verified_render_authority(runtime, analysis)

    assert raised.value.code == "verified_source_identity_mismatch"
    assert raised.value.retryable is False


def test_verified_render_rejects_noncanonical_authority_qualifier(tmp_path) -> None:
    runtime = _runtime(tmp_path, md5="source-md5")
    qualified_identity = "frozen-report|pdf-sha256:" + "a" * 64
    runtime = replace(
        runtime, ctx=replace(runtime.ctx, source_identity_id="frozen-report")
    )
    source = _source(runtime)
    selection = _selection(runtime, source)
    artifacts = _authority_artifacts()
    authority = build_verified_authority_context(
        artifacts, expected_source_identity=qualified_identity
    )
    analysis = replace(
        _analysis(runtime, source, selection),
        artifacts_payload=artifacts,
        authoritative_evidence_packs=authority.evidence_packs,
        verified_authority_context=replace(
            authority, source_identity=f"{qualified_identity}|suffix"
        ),
        data_dict={"authoritative_evidence_packs": authority.evidence_packs},
    )

    with pytest.raises(AppError) as raised:
        _verified_render_authority(runtime, analysis)

    assert raised.value.code == "verified_source_identity_mismatch"


def test_verified_render_rejects_missing_fact_snapshot_before_side_effects(
    tmp_path,
) -> None:
    runtime = _runtime(tmp_path, md5="source-md5")
    source_identity = "frozen-report|pdf-sha256:" + "a" * 64
    runtime = replace(
        runtime, ctx=replace(runtime.ctx, source_identity_id=source_identity)
    )
    source = _source(runtime)
    selection = _selection(runtime, source)
    artifacts = _authority_artifacts()
    artifacts.pop("verified_facts")
    authority = build_verified_authority_context(
        _authority_artifacts(), expected_source_identity=source_identity
    )
    analysis = replace(
        _analysis(runtime, source, selection),
        artifacts_payload=artifacts,
        authoritative_evidence_packs=authority.evidence_packs,
        verified_authority_context=authority,
        data_dict={"authoritative_evidence_packs": authority.evidence_packs},
    )

    with pytest.raises(AppError) as raised:
        _verified_render_authority(runtime, analysis)

    assert raised.value.code == "verified_authority_context_invalid"


def test_verified_render_rejects_stale_context_and_serialized_projection(
    tmp_path,
) -> None:
    runtime = _runtime(tmp_path, md5="source-md5")
    source_identity = "frozen-report|pdf-sha256:" + "a" * 64
    runtime = replace(
        runtime, ctx=replace(runtime.ctx, source_identity_id=source_identity)
    )
    source = _source(runtime)
    selection = _selection(runtime, source)
    artifacts = _authority_artifacts()
    authority = build_verified_authority_context(
        artifacts, expected_source_identity=source_identity
    )

    stale_context = replace(authority, verified_fact_digest="b" * 64)
    stale_analysis = replace(
        _analysis(runtime, source, selection),
        artifacts_payload=artifacts,
        authoritative_evidence_packs=authority.evidence_packs,
        verified_authority_context=stale_context,
        data_dict={"authoritative_evidence_packs": authority.evidence_packs},
    )
    with pytest.raises(AppError) as raised:
        _verified_render_authority(runtime, stale_analysis)
    assert raised.value.code == "verified_authority_context_mismatch"

    stale_projection = replace(
        _analysis(runtime, source, selection),
        artifacts_payload=artifacts,
        authoritative_evidence_packs=authority.evidence_packs,
        verified_authority_context=authority,
        data_dict={
            "authoritative_evidence_packs": authority.evidence_packs,
            "verified_authority_context": {
                **asdict(authority),
                "source_identity": "stale",
            },
        },
    )
    with pytest.raises(AppError) as raised:
        _verified_render_authority(runtime, stale_projection)
    assert raised.value.code == "verified_authority_context_mismatch"


def test_verified_render_rejects_invalid_canonical_snapshot_before_side_effects(
    tmp_path,
) -> None:
    runtime = _runtime(tmp_path, md5="source-md5")
    source_identity = "frozen-report|pdf-sha256:" + "a" * 64
    runtime = replace(
        runtime, ctx=replace(runtime.ctx, source_identity_id=source_identity)
    )
    source = _source(runtime)
    selection = _selection(runtime, source)
    artifacts = _authority_artifacts()
    artifacts["_cache"]["visual_authority_canary"]["digest"] = "b" * 64
    analysis = replace(
        _analysis(runtime, source, selection),
        artifacts_payload=artifacts,
        verified_authority_context=build_verified_authority_context(
            _authority_artifacts(), expected_source_identity=source_identity
        ),
    )

    with pytest.raises(AppError) as raised:
        _verified_render_authority(runtime, analysis)
    assert raised.value.code == "verified_authority_context_invalid"


def test_public_html_quality_compatibility_summary_maps_render_defects(
    tmp_path,
) -> None:
    issues = public_html_quality_issues(
        html=(
            "<img src='missing-chart.png'><p>{{ unresolved_title }}</p>"
            "<p>Revenue | 5</p>"
        ),
        html_path=str(tmp_path / "report.html"),
    )

    assert issues["placeholders"]
    assert issues["raw_fragments"]
    assert issues["broken_assets"]


def test_verified_public_quality_fails_closed_without_canonical_binding() -> None:
    artifacts = _authority_artifacts()
    artifacts["insights_final"][0]["evidence_id"] = ""
    artifacts["insights_final"][0]["evidence"] = ""

    report = evaluate_public_editorial_quality(
        report_id="missing-verified-binding", artifacts=artifacts
    )

    assert report.status == "fail"
    assert any(
        issue.rule_id == "public_editorial_quality.material_claim_evidence_missing"
        for issue in report.issues
    )


def test_metadata_quality_reconciles_html_meta_and_json_ld_identity() -> None:
    html = """
    <h1 id="report-title">Report</h1>
    <div class="meta-row">
      <span class="meta-pill">Publisher: Wrong Publisher</span>
      <span class="meta-pill">Author: Wrong Author</span>
      <span class="meta-pill">Edition: 2025</span>
      <span class="meta-pill">Published: 2025-01-01</span>
    </div>
    <script type="application/ld+json">
      {
        "publisher":{"name":"Wrong JSON Publisher"},
        "author":{"name":"Wrong JSON Author"}
      }
    </script>
    <script type="application/ld+json">not-json</script>
    <script type="application/ld+json">["not", "an", "object"]</script>
    """

    report = evaluate_public_editorial_quality(
        report_id="metadata-reconciliation",
        artifacts={},
        html=html,
        metadata_evidence={
            "title": "Market Outlook",
            "publisher": "Acme Research",
            "author": "Jane Analyst",
            "edition": "2026",
            "publication_date": "2026-01-01",
        },
    )

    identity_issues = [
        issue
        for issue in report.issues
        if issue.rule_id == "public_editorial_quality.metadata_identity"
    ]
    assert len(identity_issues) >= 4
    assert report.status == "fail"


def test_public_quality_html_and_editorial_projections_remain_deterministic() -> None:
    artifacts = _authority_artifacts()
    first = evaluate_public_editorial_quality(
        report_id="projection-regression", artifacts=artifacts
    )
    second = evaluate_public_editorial_quality(
        report_id="projection-regression", artifacts=deepcopy(artifacts)
    )

    assert first.status == second.status == "pass"
    assert [item.item_id for item in first.items] == [
        item.item_id for item in second.items
    ]


@pytest.mark.parametrize(
    ("claim", "evidence", "expected"),
    [
        (
            "Revenue was 42% in 2026.",
            "Revenue was 42% in 2025.",
            "attaches a retained metric value to a different source period",
        ),
        (
            "Alpha accounts for 50% of platform preference.",
            "Platform preference: Alpha 40%; Beta 50%.",
            "attaches a retained metric value to a different source category",
        ),
        (
            "Retailers account for 30% of online sales.",
            "Retailers account for 20% of online sales.",
            (
                "attaches a retained metric value to a different source cohort or "
                "denominator"
            ),
        ),
    ],
)
def test_metric_relationship_guard_preserves_period_category_and_denominator_bindings(
    claim: str, evidence: str, expected: str
) -> None:
    assert _metric_label_relationship_explanation(claim, evidence) == expected


def test_metric_relationship_guard_allows_explicit_combined_category_total() -> None:
    assert (
        _metric_label_relationship_explanation(
            "Alpha and Beta account for 90% of platform preference.",
            "Platform preference: Alpha 40%; Beta 50%.",
        )
        == ""
    )


def test_metric_relationship_evidence_ignores_non_findings_spans() -> None:
    assert (
        _preferred_metric_relationship_evidence(
            {
                "evidence_spans": [
                    None,
                    {"source_pack": "chart", "text": "context only"},
                    {
                        "source_pack": "findings_statement",
                        "text": "Revenue reached 42% in 2026.",
                    },
                ]
            }
        )
        == "Revenue reached 42% in 2026."
    )
