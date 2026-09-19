import json
from pathlib import Path
from typing import Any

import pytest

from src.contracts.run_context import RunContext
from src.generators.artifact_normalization import (
    artifact_base_variables,
    normalize_artifact_evidence_ids,
    soft_copy_context_evidence_anchors,
)
from src.services.schema_validator_service import validate_evidence_references
from src.utils.errors import AppError

_FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "a21_bfab37bb_evidence_closure.json"
)


def _closure_fixture() -> dict[str, Any]:
    return json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))


def _evidence_packs_for(reference: dict[str, str]) -> dict[str, Any]:
    canonical_id = reference["canonical_id"]
    if reference["source_pack"] == "findings":
        return {"findings": {"findings": [{"id": canonical_id}]}}
    return {"quote_candidates": {"quote_candidates": [{"id": canonical_id}]}}


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def test_retained_a21_editorial_plan_reference_aliases_are_canonicalized() -> None:
    """Fails if editorial-plan references bypass the strict alias boundary."""
    fixture = _closure_fixture()

    for case in fixture["schema_reference_missing"]:
        for reference in case["retained_reference_aliases"]:
            editorial_plan = {"themes": [{"evidence_ids": [reference["alias"]]}]}

            stats = normalize_artifact_evidence_ids(
                summary={},
                editorial_plan=editorial_plan,
                insights_candidates=[],
                insights_final=[],
                quotes_final=[],
                doc_map={},
                evidence_packs=_evidence_packs_for(reference),
            )

            assert editorial_plan["themes"][0]["evidence_ids"] == [
                reference["canonical_id"]
            ]
            assert stats["normalized_count"] == 1
            assert stats["unresolved_count"] == 0


def test_editorial_plan_context_exposes_retained_canonical_id_vocabulary() -> None:
    """The model sees actual IDs for the Emplifi, Qualtrics, and Mintel forms."""
    cases = (
        ("finding-01", "quote_001"),
        ("finding-1", "quote_001"),
        ("f1", "quote-001"),
    )

    for finding_id, quote_id in cases:
        variables = artifact_base_variables(
            {},
            {
                "findings": {"findings": [{"id": finding_id}]},
                "quote_candidates": {"quote_candidates": [{"id": quote_id}]},
            },
        )

        assert json.loads(variables["canonical_evidence_ids_json"]) == [
            finding_id,
            quote_id,
        ]


def test_retained_publisher_reference_forms_resolve_to_their_unique_ids() -> None:
    """Regression coverage for the failing Emplifi, Qualtrics, and Mintel forms."""
    cases = (
        ("finding-01", "evidence:findings:finding-1"),
        ("finding-1", "evidence:findings:finding_1"),
        ("f1", "evidence:findings:Finding 1"),
    )

    for canonical_id, generated_id in cases:
        editorial_plan = {"themes": [{"evidence_ids": [generated_id]}]}
        evidence_packs = {"findings": {"findings": [{"id": canonical_id}]}}

        stats = normalize_artifact_evidence_ids(
            summary={},
            editorial_plan=editorial_plan,
            insights_candidates=[],
            insights_final=[],
            quotes_final=[],
            doc_map={},
            evidence_packs=evidence_packs,
        )

        assert editorial_plan["themes"][0]["evidence_ids"] == [canonical_id]
        assert stats["normalized_count"] == 1
        validate_evidence_references(
            {"editorial_plan": editorial_plan}, evidence_packs, _ctx()
        )


def test_common_reference_boundary_canonicalizes_every_artifact_family() -> None:
    """Valid aliases must resolve before the strict reference validator runs."""
    alias_finding = "evidence:findings:Finding 1"
    alias_quote = "evidence:quote_candidates:quote-1"
    summary = {
        "claim_evidence_map": [
            {
                "evidence_id": alias_finding,
                "evidence_spans": [{"evidence_id": alias_finding}],
            }
        ]
    }
    insights_candidates = [
        {
            "evidence_id": alias_finding,
            "evidence_spans": [{"evidence_id": alias_finding}],
        }
    ]
    insights_final = [
        {
            "evidence_id": alias_finding,
            "evidence_spans": [{"evidence_id": alias_finding}],
        }
    ]
    quotes_final = [
        {"evidence_id": alias_quote, "evidence_spans": [{"evidence_id": alias_quote}]}
    ]
    editorial_plan = {"themes": [{"evidence_ids": [alias_finding, alias_quote]}]}
    soft_copy_claim_provenance = {
        "claims": [
            {
                "evidence_ids": [alias_finding, "quote_001"],
                "source_spans": [
                    {"evidence_id": alias_finding},
                    {"evidence_id": alias_quote},
                ],
            }
        ]
    }
    evidence_packs = {
        "findings": {"findings": [{"id": "f1"}]},
        "quote_candidates": {"quote_candidates": [{"id": "quote_001"}]},
    }

    stats = normalize_artifact_evidence_ids(
        summary=summary,
        insights_candidates=insights_candidates,
        insights_final=insights_final,
        quotes_final=quotes_final,
        doc_map={},
        evidence_packs=evidence_packs,
        editorial_plan=editorial_plan,
        soft_copy_claim_provenance=soft_copy_claim_provenance,
    )

    assert summary["claim_evidence_map"][0] == {
        "evidence_id": "f1",
        "evidence_spans": [{"evidence_id": "f1"}],
    }
    assert insights_candidates[0]["evidence_id"] == "f1"
    assert insights_candidates[0]["evidence_spans"] == [{"evidence_id": "f1"}]
    assert insights_final[0]["evidence_id"] == "f1"
    assert insights_final[0]["evidence_spans"] == [{"evidence_id": "f1"}]
    assert quotes_final[0]["evidence_id"] == "quote_001"
    assert quotes_final[0]["evidence_spans"] == [{"evidence_id": "quote_001"}]
    assert editorial_plan["themes"][0]["evidence_ids"] == ["f1", "quote_001"]
    assert soft_copy_claim_provenance["claims"][0] == {
        "evidence_ids": ["f1", "quote_001"],
        "source_spans": [
            {"evidence_id": "f1"},
            {"evidence_id": "quote_001"},
        ],
    }
    assert stats["normalized_count"] == 13
    validate_evidence_references(
        {
            "summary": summary,
            "insights_candidates": insights_candidates,
            "insights_final": insights_final,
            "quotes_final": quotes_final,
            "editorial_plan": editorial_plan,
            "soft_copy_claim_provenance": soft_copy_claim_provenance,
        },
        evidence_packs,
        _ctx(),
    )


def test_common_reference_boundary_preserves_unknown_soft_copy_references() -> None:
    soft_copy_claim_provenance = {
        "claims": [{"evidence_ids": ["evidence:findings:unknown"]}]
    }
    evidence_packs = {"findings": {"findings": [{"id": "f1"}]}}

    stats = normalize_artifact_evidence_ids(
        summary={},
        insights_candidates=[],
        insights_final=[],
        quotes_final=[],
        doc_map={},
        evidence_packs=evidence_packs,
        soft_copy_claim_provenance=soft_copy_claim_provenance,
    )

    assert soft_copy_claim_provenance == {
        "claims": [{"evidence_ids": ["evidence:findings:unknown"]}]
    }
    assert stats["unresolved_count"] == 1
    with pytest.raises(AppError) as exc:
        validate_evidence_references(
            {"soft_copy_claim_provenance": soft_copy_claim_provenance},
            evidence_packs,
            _ctx(),
        )
    assert exc.value.code == "schema_reference_missing"


def test_common_reference_boundary_canonicalizes_compact_numeric_aliases() -> None:
    summary = {
        "claim_evidence_map": [{"evidence_id": "evidence:findings:F-1"}]
    }
    evidence_packs = {"findings": {"findings": [{"id": "f1"}]}}

    stats = normalize_artifact_evidence_ids(
        summary=summary,
        insights_candidates=[],
        insights_final=[],
        quotes_final=[],
        doc_map={},
        evidence_packs=evidence_packs,
    )

    assert summary["claim_evidence_map"][0]["evidence_id"] == "f1"
    assert stats["normalized_count"] == 1
    validate_evidence_references(
        {"summary": summary}, evidence_packs, _ctx()
    )


def test_common_reference_boundary_canonicalizes_unpadded_numeric_aliases() -> None:
    summary = {
        "claim_evidence_map": [{"evidence_id": "evidence:findings:metric-1"}]
    }
    evidence_packs = {"findings": {"findings": [{"id": "metric-001"}]}}

    stats = normalize_artifact_evidence_ids(
        summary=summary,
        insights_candidates=[],
        insights_final=[],
        quotes_final=[],
        doc_map={},
        evidence_packs=evidence_packs,
    )

    assert summary["claim_evidence_map"][0]["evidence_id"] == "metric-001"
    assert stats["normalized_count"] == 1
    validate_evidence_references(
        {"summary": summary}, evidence_packs, _ctx()
    )


def test_common_reference_boundary_rejects_unknown_numeric_aliases() -> None:
    summary = {
        "claim_evidence_map": [{"evidence_id": "evidence:findings:metric-2"}]
    }
    evidence_packs = {"findings": {"findings": [{"id": "metric-001"}]}}

    stats = normalize_artifact_evidence_ids(
        summary=summary,
        insights_candidates=[],
        insights_final=[],
        quotes_final=[],
        doc_map={},
        evidence_packs=evidence_packs,
    )

    assert summary["claim_evidence_map"][0]["evidence_id"] == (
        "evidence:findings:metric-2"
    )
    assert stats["unresolved_count"] == 1
    with pytest.raises(AppError) as exc:
        validate_evidence_references(
            {"summary": summary}, evidence_packs, _ctx()
        )
    assert exc.value.code == "schema_reference_missing"


def test_context_anchors_resolve_cited_metric_ids_to_retained_evidence() -> None:
    """A metric-spine identifier resolves to that row's own retained evidence."""

    soft_copy_claim_provenance = {
        "claims": [{"evidence_ids": ["insight_metric_1", "f3-retained-2"]}]
    }
    evidence_packs = {
        "findings": {"findings": [{"id": "f1"}, {"id": "f3"}]},
    }
    anchors = soft_copy_context_evidence_anchors(
        insights_final=[
            {"id": "insight-1", "evidence_id": "f1"},
        ],
        metric_spine=[
            {"metric_id": "insight_metric_1", "evidence_id": "f1"},
            {"metric_id": "f3-retained-2", "evidence_id": "f3"},
        ],
    )

    stats = normalize_artifact_evidence_ids(
        summary={},
        insights_candidates=[],
        insights_final=[],
        quotes_final=[],
        doc_map={},
        evidence_packs=evidence_packs,
        soft_copy_claim_provenance=soft_copy_claim_provenance,
        context_anchors=anchors,
    )

    assert soft_copy_claim_provenance == {"claims": [{"evidence_ids": ["f1", "f3"]}]}
    assert stats["normalized_count"] == 2
    validate_evidence_references(
        {"soft_copy_claim_provenance": soft_copy_claim_provenance},
        evidence_packs,
        _ctx(),
    )


def test_context_anchor_without_retained_target_stays_unknown() -> None:
    """Anchors never invent evidence: unknown targets still fail validation."""

    soft_copy_claim_provenance = {"claims": [{"evidence_ids": ["ghost-metric"]}]}
    anchors = soft_copy_context_evidence_anchors(
        insights_final=[],
        metric_spine=[{"metric_id": "ghost-metric", "evidence_id": ""}],
    )

    stats = normalize_artifact_evidence_ids(
        summary={},
        insights_candidates=[],
        insights_final=[],
        quotes_final=[],
        doc_map={},
        evidence_packs={"findings": {"findings": [{"id": "f1"}]}},
        soft_copy_claim_provenance=soft_copy_claim_provenance,
        context_anchors=anchors,
    )

    assert soft_copy_claim_provenance == {
        "claims": [{"evidence_ids": ["ghost-metric"]}]
    }
    assert stats["unresolved_count"] == 1
    with pytest.raises(AppError) as exc:
        validate_evidence_references(
            {"soft_copy_claim_provenance": soft_copy_claim_provenance},
            {"findings": {"findings": [{"id": "f1"}]}},
            _ctx(),
        )
    assert exc.value.code == "schema_reference_missing"


def test_common_reference_boundary_preserves_ambiguous_separator_variant() -> None:
    """A collision between retained IDs must not choose either by insertion order."""
    summary = {
        "claim_evidence_map": [
            {"evidence_id": "finding_1"},
            {"evidence_id": "FINDING_1"},
        ]
    }
    evidence_packs = {
        "findings": {
            "findings": [{"id": "finding-1"}, {"id": "finding_1"}]
        }
    }

    stats = normalize_artifact_evidence_ids(
        summary=summary,
        insights_candidates=[],
        insights_final=[],
        quotes_final=[],
        doc_map={},
        evidence_packs=evidence_packs,
    )

    assert summary["claim_evidence_map"][0]["evidence_id"] == "finding_1"
    assert stats["normalized_count"] == 0
    assert stats["unresolved_count"] == 1
    with pytest.raises(AppError) as exc:
        validate_evidence_references({"summary": summary}, evidence_packs, _ctx())
    assert exc.value.code == "schema_reference_missing"


def test_common_reference_boundary_binds_location_spans_to_proven_parent() -> None:
    summary = {
        "claim_evidence_map": [
            {
                "evidence_id": "evidence:findings:finding_001",
                "evidence_spans": [
                    {
                        "evidence_id": "source:page:3",
                        "source_pack": "source_pdf",
                        "page": 3,
                        "text": "Retained location context",
                    }
                ],
            }
        ]
    }
    soft_copy_claim_provenance = {
        "claims": [
            {
                "evidence_ids": ["evidence:findings:finding_001"],
                "source_spans": [
                    {
                        "evidence_id": "source:page:3",
                        "source_pack": "source_pdf",
                        "page": 3,
                        "text": "Retained location context",
                    }
                ],
            }
        ]
    }
    evidence_packs = {"findings": {"findings": [{"id": "finding_001"}]}}

    normalize_artifact_evidence_ids(
        summary=summary,
        insights_candidates=[],
        insights_final=[],
        quotes_final=[],
        doc_map={},
        evidence_packs=evidence_packs,
        soft_copy_claim_provenance=soft_copy_claim_provenance,
    )

    summary_span = summary["claim_evidence_map"][0]["evidence_spans"][0]
    soft_copy_span = soft_copy_claim_provenance["claims"][0]["source_spans"][0]
    assert summary_span == {
        "evidence_id": "finding_001",
        "source_pack": "source_pdf",
        "page": 3,
        "text": "Retained location context",
    }
    assert soft_copy_span == summary_span
    validate_evidence_references(
        {
            "summary": summary,
            "soft_copy_claim_provenance": soft_copy_claim_provenance,
        },
        evidence_packs,
        _ctx(),
    )


def test_retained_a21_queue_wrapper_classification_is_explicit_about_gaps() -> None:
    fixture = _closure_fixture()
    cases = fixture["workflow_queue_report_stage_failed"]

    recovered = [case for case in cases if case["recovery_status"] == "recovered"]
    unresolved = [case for case in cases if case["recovery_status"] == "unresolved"]

    assert [case["underlying_error_code"] for case in recovered] == [
        "publish_readiness_failed",
        "publish_readiness_failed",
    ]
    assert all(case["retained_rule_ids"] for case in recovered)
    assert len(unresolved) == 3
    assert all("underlying_error_code" not in case for case in unresolved)
    assert all(case["unresolved_reason"] for case in unresolved)
