from __future__ import annotations

import hashlib
from copy import deepcopy

import pytest

from src.contracts.soft_copy_claim_provenance import (
    soft_copy_claim_provenance_to_payload,
    soft_copy_material_sentences,
)
from src.generators._artifact_generator.storage import (
    build_canonical_regeneration_derived_artifacts,
    derive_metric_spine_from_insights,
    finalize_regeneration_candidate_artifacts,
)
from src.generators.soft_copy_claim_provenance import (
    build_soft_copy_claim_provenance,
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
        atomic_source_patch={"quotes_final": deepcopy(candidate["quotes_final"])},
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
        atomic_source_patch={"quotes_final": deepcopy(candidate["quotes_final"])},
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
        atomic_source_patch={"insights_final": deepcopy(candidate["insights_final"])},
    )

    expected_spine = derive_metric_spine_from_insights([retained_insight])
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


def test_finalization_uses_only_the_atomic_source_patch() -> None:
    baseline = {
        "summary": {"claim_evidence_map": []},
        "insights_final": [
            {
                "id": "insight-1",
                "text": "Original source-backed finding.",
                "so_what": "Original implication.",
                "evidence_id": "f1",
                "pages": [4],
            }
        ],
        "quotes_final": [],
        "soft_copy_claim_provenance": soft_copy_claim_provenance_to_payload([]),
    }
    atomic_patch = deepcopy(baseline["insights_final"])
    atomic_patch[0]["so_what"] = "Repaired implication."
    candidate = deepcopy(baseline)
    candidate["insights_final"][0]["so_what"] = "Repaired implication."
    candidate["insights_final"].append(
        {
            "id": "out-of-scope-sibling",
            "text": "Unplanned sibling content.",
            "evidence_id": "f1",
            "pages": [4],
        }
    )

    finalize_regeneration_candidate_artifacts(
        promoted_baseline=baseline,
        candidate_artifacts=candidate,
        evidence_packs={
            "findings": {
                "findings": [{"id": "f1", "text": "Source evidence.", "pages": [4]}]
            }
        },
        atomic_source_patch={"insights_final": atomic_patch},
    )

    assert candidate["insights_final"] == atomic_patch
    assert all(
        item["id"] != "out-of-scope-sibling"
        for item in candidate["insights_final"]
    )


def test_finalization_rejects_derived_roots_in_the_atomic_source_patch() -> None:
    baseline = {"metric_spine": []}
    candidate = deepcopy(baseline)

    with pytest.raises(AppError) as error:
        finalize_regeneration_candidate_artifacts(
            promoted_baseline=baseline,
            candidate_artifacts=candidate,
            evidence_packs={},
            atomic_source_patch={"metric_spine": [{"value": "99%"}]},
        )

    assert error.value.code == "regeneration_deterministic_projection_failed"
    assert error.value.context["projection"] == "atomic_source_patch"


def test_finalization_does_not_extract_neighboring_numbers_into_key_figures() -> None:
    evidence_text = (
        "Retail media adoption reached 55% among merchants. "
        "A neighboring measure reached 99% in another cohort."
    )
    retained_insight = {
        "id": "retained-insight",
        "text": "Retail media adoption reached 55% among merchants.",
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
    removed_insight = {
        "id": "removed-insight",
        "text": "A neighboring measure reached 99% in another cohort.",
        "evidence": evidence_text,
        "evidence_id": "f1",
        "pages": [7],
        "metric": {
            "label": "Neighboring measure",
            "value": "99%",
            "confidence": "high",
            "segment": "another cohort",
        },
    }
    evidence_packs = {
        "findings": {"findings": [{"id": "f1", "text": evidence_text, "pages": [7]}]}
    }
    baseline = {
        "summary": {"claim_evidence_map": []},
        "insights_final": [retained_insight, removed_insight],
        "quotes_final": [],
        "toc_entries": [],
        "editorial_plan": {},
        "soft_copy_claim_provenance": soft_copy_claim_provenance_to_payload([]),
    }
    baseline.update(
        build_canonical_regeneration_derived_artifacts(
            artifacts=baseline,
            evidence_packs=evidence_packs,
            roots={"metric_spine", "key_figures", "chart_insight_cards"},
        )
    )
    candidate = deepcopy(baseline)
    candidate["insights_final"] = [retained_insight]

    finalize_regeneration_candidate_artifacts(
        promoted_baseline=baseline,
        candidate_artifacts=candidate,
        evidence_packs=evidence_packs,
        atomic_source_patch={"insights_final": deepcopy(candidate["insights_final"])},
    )

    assert [figure["figure"] for figure in candidate["key_figures"]] == ["55%"]
    assert all(
        card["insight_id"] == "retained-insight"
        for card in candidate["chart_insight_cards"]
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
        atomic_source_patch={"toc_entries": deepcopy(candidate["toc_entries"])},
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
            atomic_source_patch={"summary": deepcopy(candidate["summary"])},
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
        atomic_source_patch={"summary": deepcopy(candidate["summary"])},
    )

    assert candidate["soft_copy_claim_provenance"]["claims"][0]["evidence_ids"] == [
        "source-current"
    ]


def test_byte_identical_expert_and_linkedin_text_reuses_canonical_provenance() -> None:
    text = "U.S. merchants changed course. Planning followed."
    sentences = soft_copy_material_sentences(text)
    bindings = [
        {
            "claim": sentences[0],
            "classification": "interpretive",
            "evidence_ids": [],
        },
        {
            "claim": sentences[1],
            "classification": "recommendation",
            "evidence_ids": [],
        },
    ]

    def family_claims(family: str, *, attempt: int, identity: str):
        return build_soft_copy_claim_provenance(
            artifact_family=family,
            text=text,
            declared_claims=bindings,
            evidence_span_index={},
            producing_prompt_identity={"execution_identity": identity},
            generation_attempt=attempt,
            regeneration_attempt=attempt - 1,
        )

    baseline = {
        "summary": {},
        "insights_final": [],
        "quotes_final": [],
        "expert_comment": text,
        "linkedin_post": text,
        "soft_copy_claim_provenance": soft_copy_claim_provenance_to_payload(
            [
                *family_claims("expert_comment", attempt=1, identity="original"),
                *family_claims("linkedin_post", attempt=1, identity="original"),
            ]
        ),
    }
    candidate = deepcopy(baseline)
    candidate["soft_copy_claim_provenance"] = soft_copy_claim_provenance_to_payload(
        [
            *family_claims("expert_comment", attempt=2, identity="regenerated"),
            *family_claims("linkedin_post", attempt=2, identity="regenerated"),
        ]
    )

    finalize_regeneration_candidate_artifacts(
        promoted_baseline=baseline,
        candidate_artifacts=candidate,
        evidence_packs={},
        atomic_source_patch={"expert_comment": text, "linkedin_post": text},
    )

    assert (
        candidate["soft_copy_claim_provenance"]
        == baseline["soft_copy_claim_provenance"]
    )
    claims = candidate["soft_copy_claim_provenance"]["claims"]
    for family in ("expert_comment", "linkedin_post"):
        family_hashes = [
            claim["text_hash"] for claim in claims if claim["artifact_family"] == family
        ]
        assert family_hashes == [
            hashlib.sha256(sentence.encode("utf-8")).hexdigest()
            for sentence in sentences
        ]
