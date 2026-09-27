from __future__ import annotations

import hashlib
from copy import deepcopy

import pytest

from src.contracts.soft_copy_claim_provenance import (
    soft_copy_claim_provenance_to_payload,
)
from src.generators._artifact_generator.storage import (
    build_canonical_regeneration_derived_artifacts,
    derive_metric_spine_from_insights,
    finalize_regeneration_candidate_artifacts,
)
from src.utils.errors import AppError


def test_finalization_preserves_unrelated_derived_roots_byte_for_byte() -> None:
    baseline = {
        "summary": {},
        "insights_final": [],
        "quotes_final": [{"id": "quote-one", "text": "Prior quote."}],
        "toc_entries": [],
        "editorial_plan": {"themes": [{"label": "Stable theme"}]},
        "metric_spine": [{"metric_id": "metric-one", "value": "17%"}],
        "topics_covered": [{"topic_id": "stable", "topic": "Stable topic"}],
        "key_figures": [{"figure_id": "stable", "figure": "17%"}],
        "chart_insight_cards": [{"candidate_id": "stable", "caption": "Stable"}],
        "executive_advisory": {"schema_version": "stale"},
        "claim_ledgers": [{"canonical_claim_id": "report-one:prior"}],
        "family_status": {"schema_version": "stale"},
        "soft_copy_claim_provenance": soft_copy_claim_provenance_to_payload([]),
    }
    candidate = deepcopy(baseline)
    candidate["quotes_final"] = [{"id": "quote-one", "text": "Repaired source quote."}]
    candidate["summary"] = {"tldr": "Incidental candidate assembly text."}
    candidate["toc_entries"] = [{"section_title": "Incidental assembly topic"}]
    candidate["editorial_plan"] = {"themes": [{"label": "Incidental theme"}]}
    for root in (
        "metric_spine",
        "topics_covered",
        "key_figures",
        "chart_insight_cards",
        "executive_advisory",
        "claim_ledgers",
        "family_status",
    ):
        candidate[root] = [{"candidate_assembly": root}]

    verified_paths = finalize_regeneration_candidate_artifacts(
        promoted_baseline=baseline,
        candidate_artifacts=candidate,
        evidence_packs={},
        authorized_source_roots={"quotes_final"},
    )

    for root in (
        "metric_spine",
        "topics_covered",
        "key_figures",
        "chart_insight_cards",
    ):
        assert candidate[root] == baseline[root]
    assert candidate["executive_advisory"] != baseline["executive_advisory"]
    assert candidate["claim_ledgers"] != baseline["claim_ledgers"]
    assert candidate["family_status"] != baseline["family_status"]
    assert candidate["summary"] == baseline["summary"]
    assert candidate["toc_entries"] == baseline["toc_entries"]
    assert candidate["editorial_plan"] == baseline["editorial_plan"]
    assert {path.split(".", 1)[0].split("[", 1)[0] for path in verified_paths} == {
        "executive_advisory",
        "claim_ledgers",
        "family_status",
    }
    finalized_once = deepcopy(candidate)
    repeated_paths = finalize_regeneration_candidate_artifacts(
        promoted_baseline=baseline,
        candidate_artifacts=candidate,
        evidence_packs={},
        authorized_source_roots={"quotes_final"},
    )
    assert candidate == finalized_once
    assert repeated_paths == verified_paths


def test_finalization_rebuilds_metric_dependents_from_promoted_patch() -> None:
    evidence_text = "Retail media adoption reached 55% among merchants."
    removed_insight = {
        "id": "removed-insight",
        "text": "Removed insight claimed 99% growth.",
        "evidence_id": "f1",
        "pages": [7],
        "metric": {
            "label": "Retail media adoption",
            "value": "99%",
            "confidence": "high",
        },
    }
    retained_insight = {
        "id": "retained-insight",
        "text": evidence_text,
        "evidence": evidence_text,
        "evidence_id": "f1",
        "pages": [7],
        "metric": {
            "label": "Retail media adoption",
            "value": "55%",
            "confidence": "high",
            "segment": "merchants",
        },
    }
    evidence_packs = {
        "findings": {"findings": [{"id": "f1", "text": evidence_text, "pages": [7]}]}
    }
    baseline = {
        "summary": {"claim_evidence_map": []},
        "insights_final": [removed_insight, retained_insight],
        "quotes_final": [],
        "toc_entries": [],
        "editorial_plan": {},
        "metric_spine": [{"metric_id": "removed-insight", "value": "99%"}],
        "topics_covered": [{"topic_id": "removed", "topic": "Removed insight"}],
        "key_figures": [{"figure_id": "removed-insight", "figure": "99%"}],
        "chart_insight_cards": [{"insight_id": "removed-insight", "caption": "99%"}],
        "executive_advisory": {"recommendations": {"items": ["99%"]}},
        "claim_ledgers": [
            {"canonical_claim_id": "report-one:removed-insight", "text": "99%"}
        ],
        "family_status": {"stale": "removed insight"},
        "soft_copy_claim_provenance": soft_copy_claim_provenance_to_payload([]),
    }
    candidate = deepcopy(baseline)
    candidate["insights_final"] = [retained_insight]

    verified_paths = finalize_regeneration_candidate_artifacts(
        promoted_baseline=baseline,
        candidate_artifacts=candidate,
        evidence_packs=evidence_packs,
        authorized_source_roots={"insights_final"},
    )

    expected_spine = derive_metric_spine_from_insights(
        [retained_insight], evidence_packs=evidence_packs
    )
    expected_dependents = build_canonical_regeneration_derived_artifacts(
        artifacts=candidate,
        evidence_packs=evidence_packs,
        roots={"key_figures", "chart_insight_cards"},
    )
    assert candidate["metric_spine"] == expected_spine
    assert candidate["key_figures"] == expected_dependents["key_figures"]
    assert (
        candidate["chart_insight_cards"] == expected_dependents["chart_insight_cards"]
    )
    assert candidate["key_figures"][0]["figure"] == "55%"
    assert candidate["key_figures"][0]["source_page"] == 7
    assert candidate["chart_insight_cards"][0]["evidence_id"] == "f1"
    assert "99%" not in repr(
        [
            candidate["metric_spine"],
            candidate["key_figures"],
            candidate["chart_insight_cards"],
            candidate["executive_advisory"],
            candidate["claim_ledgers"],
        ]
    )
    assert "removed-insight" not in repr(candidate["claim_ledgers"])
    assert "executive_advisory" in {
        path.split(".", 1)[0].split("[", 1)[0] for path in verified_paths
    }
    assert "removed-insight" not in repr(
        [candidate["topics_covered"], candidate["family_status"]]
    )


def test_finalization_rebuilds_topics_after_toc_source_change() -> None:
    baseline = {
        "summary": {},
        "insights_final": [],
        "quotes_final": [],
        "toc_entries": [
            {
                "section_id": "old-topic",
                "section_title": "Old topic",
                "pages": [3],
                "key_points": ["Old point"],
            }
        ],
        "topics_covered": [{"topic_id": "old-topic", "topic": "Old topic"}],
        "soft_copy_claim_provenance": soft_copy_claim_provenance_to_payload([]),
    }
    candidate = deepcopy(baseline)
    candidate["toc_entries"] = [
        {
            "section_id": "new-topic",
            "section_title": "New topic",
            "pages": [5],
            "key_points": ["New point"],
        }
    ]

    verified_paths = finalize_regeneration_candidate_artifacts(
        promoted_baseline=baseline,
        candidate_artifacts=candidate,
        evidence_packs={},
        authorized_source_roots={"toc_entries"},
    )

    expected = build_canonical_regeneration_derived_artifacts(
        artifacts=candidate,
        evidence_packs={},
        roots={"topics_covered"},
    )
    assert candidate["topics_covered"] == expected["topics_covered"]
    assert candidate["topics_covered"][0]["topic_id"] == "new-topic"
    assert any(path.startswith("topics_covered") for path in verified_paths)


def test_unreconstructable_final_provenance_has_typed_projection_failure() -> None:
    baseline = {
        "summary": {"tldr": "Original public text."},
        "insights_final": [],
        "quotes_final": [],
        "soft_copy_claim_provenance": soft_copy_claim_provenance_to_payload([]),
    }
    candidate = deepcopy(baseline)
    candidate["summary"]["tldr"] = "New public text with no retained binding."

    with pytest.raises(AppError) as error:
        finalize_regeneration_candidate_artifacts(
            promoted_baseline=baseline,
            candidate_artifacts=candidate,
            evidence_packs={},
            authorized_source_roots={"summary"},
        )

    assert error.value.code == "regeneration_deterministic_projection_failed"
    assert error.value.context["projection"] == "soft_copy_claim_provenance"
    assert error.value.context["cause_code"] == (
        "soft_copy_claim_provenance_sentence_missing"
    )


def test_finalization_rebinds_unchanged_public_text_to_candidate_provenance() -> None:
    text = "The retained source supports this statement."
    claim = {
        "schema_version": "1.0",
        "artifact_family": "summary",
        "claim_id": "summary:stable-claim",
        "text_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "classification": "factual",
        "evidence_ids": ["source-old"],
        "source_spans": [],
        "producing_prompt_identity": {"namespace": "report_vs/artifacts/summary"},
        "generation_attempt": 1,
        "regeneration_attempt": 0,
    }
    baseline = {
        "summary": {"tldr": text},
        "insights_final": [],
        "quotes_final": [],
        "soft_copy_claim_provenance": {
            "schema_version": "1.0",
            "claims": [claim],
        },
    }
    candidate = deepcopy(baseline)
    candidate["soft_copy_claim_provenance"]["claims"][0]["evidence_ids"] = [
        "source-current"
    ]

    finalize_regeneration_candidate_artifacts(
        promoted_baseline=baseline,
        candidate_artifacts=candidate,
        evidence_packs={},
        authorized_source_roots={"summary"},
    )

    assert candidate["soft_copy_claim_provenance"]["claims"][0]["evidence_ids"] == [
        "source-current"
    ]
