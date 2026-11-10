from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from src.contracts.regeneration import (
    ArtifactRegenerationRequest,
    RegenerationIssue,
    RegenerationPlan,
    RegenerationTarget,
)
from src.orchestrators._report_analysis_orchestrator.validation import (
    _reconcile_candidate_key_figure_projections,
    _require_candidate_artifacts_path,
)
from src.utils.cache_utils import sha256_json
from src.utils.errors import AppError
from tests._test_report_regeneration_generator import (
    _split_support_test_report_regeneration_generator as regeneration_support,
)
from tests.test_verified_claims_visual_authority_canary import (
    _verified_admission,
)

_FakeOpenAIClient = regeneration_support._FakeOpenAIClient
_FakePromptClient = regeneration_support._FakePromptClient
_current_artifacts = regeneration_support._current_artifacts
_regeneration_evidence_packs = regeneration_support._evidence_packs
_regeneration_settings = regeneration_support._settings
_regeneration_ctx = regeneration_support._ctx
_test_regenerate_artifacts = regeneration_support.regenerate_artifacts


def test_verified_regeneration_requires_persisted_candidate_path():
    response = type("Response", (), {"candidate_artifacts_path": ""})()

    with pytest.raises(AppError, match="persisted candidate artifact path") as exc_info:
        _require_candidate_artifacts_path(
            response, verified_mode=True, report_id="verified-report"
        )

    assert exc_info.value.code == "verified_regeneration_candidate_persistence_missing"
    assert exc_info.value.retryable is False
    assert _require_candidate_artifacts_path(
        response, verified_mode=False, report_id="legacy-report"
    ) == ""


def test_projection_mismatch_is_rejected_without_mutating_persisted_candidate():
    before = {
        "insights_final": [{"id": "insight-1", "text": "Source insight"}],
        "key_figures": [{"label": "Reach", "value": 10}],
        "chart_insight_cards": [{"insight_id": "insight-1", "value": 10}],
    }
    candidate = deepcopy(before)
    candidate["key_figures"][0]["value"] = 99

    with pytest.raises(AppError, match="derived projection") as exc_info:
        _reconcile_candidate_key_figure_projections(
            before=before,
            candidate=candidate,
            evidence_packs={},
        )

    assert exc_info.value.code == "regeneration_candidate_projection_mismatch"
    assert candidate["key_figures"][0]["value"] == 99


def _visual_regeneration_request(
    current: dict, evidence: dict, tmp_path: Path
) -> ArtifactRegenerationRequest:
    return ArtifactRegenerationRequest(
        report_id="visual-authority-regeneration",
        report_name="visual-authority-regeneration",
        attempt_index=1,
        plan=RegenerationPlan(
            mode="targeted",
            targets=[
                RegenerationTarget(
                    target_section="insights_bundle",
                    regenerate_steps=["insights_final"],
                    issues=[
                        RegenerationIssue(
                            rule_id="grounding",
                            affected_section="insights:insight-1.text",
                            message="The retained wording needs repair.",
                            severity="error",
                            entity_id="insight:insight-1:text",
                            evidence_ids=["f1"],
                        )
                    ],
                )
            ],
        ),
        current_artifacts=current,
        doc_map=evidence["doc_map"],
        evidence_packs=evidence,
        settings=_regeneration_settings(tmp_path),
        ctx=_regeneration_ctx(),
        source_status=current["source_status"],
        categories=["Category"],
    )


def test_scoped_regeneration_preserves_visual_authority_pool(tmp_path):
    current = _current_artifacts()
    admitted = deepcopy(current["insights_final"][:2])
    visual_admission = _verified_admission(admitted, digest="e" * 64)
    current["insights_candidates"] = deepcopy(admitted)
    current["verified_facts"] = deepcopy(visual_admission.verified_facts)
    current["_cache"]["visual_authority_canary"] = {
        "enabled": True,
        "digest": "e" * 64,
        "verified_fact_digest": "e" * 64,
        "verified_facts": deepcopy(visual_admission.verified_facts),
        "verified_evidence_packs": deepcopy(visual_admission.verified_evidence_packs),
        "admitted_candidates": deepcopy(visual_admission.admitted_candidates),
        "audit": {"admitted_count": 2},
    }
    evidence = _regeneration_evidence_packs()

    response = _test_regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="visual-authority-regeneration",
            report_name="visual-authority-regeneration",
            attempt_index=1,
            plan=RegenerationPlan(
                mode="targeted",
                targets=[
                    RegenerationTarget(
                        target_section="insights_bundle",
                        regenerate_steps=["insights_final"],
                        issues=[
                            RegenerationIssue(
                                rule_id="grounding",
                                affected_section="insights:insight-1.text",
                                message="The retained wording needs repair.",
                                severity="error",
                                entity_id="insight:insight-1:text",
                                evidence_ids=["f1"],
                            )
                        ],
                    )
                ],
            ),
            current_artifacts=current,
            doc_map=evidence["doc_map"],
            evidence_packs=evidence,
            settings=_regeneration_settings(tmp_path),
            ctx=_regeneration_ctx(),
            source_status=current["source_status"],
            categories=["Category"],
        ),
        openai_client=_FakeOpenAIClient(),
        prompt_client=_FakePromptClient(),
    )

    final_ids = {item["id"] for item in response.updated_artifacts["insights_final"]}
    candidate_ids = {
        item["id"] for item in response.updated_artifacts["insights_candidates"]
    }
    assert final_ids <= {item["id"] for item in admitted}
    assert candidate_ids <= {item["id"] for item in admitted}
    untouched_before = next(item for item in admitted if item["id"] == "insight-2")
    untouched_after = next(
        item
        for item in response.updated_artifacts["insights_final"]
        if item["id"] == "insight-2"
    )
    assert untouched_after == untouched_before
    assert (
        response.updated_artifacts["_cache"]["visual_authority_canary"]["digest"]
        == "e" * 64
    )


def test_persisted_regeneration_candidate_matches_validated_candidate(tmp_path):
    current = _current_artifacts()
    admitted = deepcopy(current["insights_final"][:2])
    visual_admission = _verified_admission(admitted, digest="h" * 64)
    current["insights_candidates"] = deepcopy(admitted)
    current["verified_facts"] = deepcopy(visual_admission.verified_facts)
    current["_cache"]["visual_authority_canary"] = {
        "enabled": True,
        "digest": "h" * 64,
        "verified_fact_digest": "h" * 64,
        "verified_facts": deepcopy(visual_admission.verified_facts),
        "verified_evidence_packs": deepcopy(visual_admission.verified_evidence_packs),
        "admitted_candidates": deepcopy(visual_admission.admitted_candidates),
        "audit": {"admitted_count": 2},
    }
    evidence = _regeneration_evidence_packs()

    response = _test_regenerate_artifacts(
        _visual_regeneration_request(current, evidence, tmp_path),
        openai_client=_FakeOpenAIClient(),
        prompt_client=_FakePromptClient(),
    )

    persisted = json.loads(
        Path(response.candidate_artifacts_path).read_text(encoding="utf-8")
    )
    assert persisted == response.updated_artifacts
    assert sha256_json(persisted) == sha256_json(response.updated_artifacts)


def test_verified_expert_comment_repair_preserves_unrelated_source_roots(tmp_path):
    current = _current_artifacts()
    extra = deepcopy(current["insights_final"][0])
    extra["id"] = "extra-verified-fact"
    extra["text"] = "An additional admitted fact."
    extra["evidence_id"] = "extra-finding"
    extra["pages"] = [6]
    admitted = deepcopy(current["insights_final"]) + [extra]
    visual_admission = _verified_admission(admitted, digest="g" * 64)
    current["insights_candidates"] = deepcopy(visual_admission.admitted_candidates[:-1])
    current["insights_final"] = deepcopy(visual_admission.admitted_candidates[:-1])
    current["summary"]["claim_evidence_map"][0]["evidence_id"] = (
        "verified-fact:insight-1"
    )
    current["summary"]["claim_evidence_map"][0]["evidence"] = (
        "Legacy summary evidence text"
    )
    current["verified_facts"] = deepcopy(visual_admission.verified_facts)
    current["_cache"]["visual_authority_canary"] = {
        "enabled": True,
        "digest": "g" * 64,
        "verified_fact_digest": "g" * 64,
        "verified_facts": deepcopy(visual_admission.verified_facts),
        "verified_evidence_packs": deepcopy(visual_admission.verified_evidence_packs),
        "admitted_candidates": deepcopy(visual_admission.admitted_candidates),
        "audit": {"admitted_count": 2},
    }
    evidence = _regeneration_evidence_packs()
    claim = next(
        item
        for item in current["soft_copy_claim_provenance"]["claims"]
        if item["artifact_family"] == "expert_comment"
    )
    evidence_ids = [f"verified-fact:{item['id']}" for item in admitted[:2]]
    response = _test_regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="visual-authority-regeneration",
            report_name="visual-authority-regeneration",
            attempt_index=1,
            plan=RegenerationPlan(
                mode="targeted",
                targets=[
                    RegenerationTarget(
                        target_section="expert_comment",
                        regenerate_steps=["expert_comment"],
                        issues=[
                            RegenerationIssue(
                                rule_id="grounding",
                                affected_section="expert_comment",
                                message="The retained expert comment needs repair.",
                                severity="error",
                                entity_id=claim["claim_id"],
                                evidence_ids=evidence_ids,
                            )
                        ],
                        allowed_paths=["expert_comment[claim_index=0]"],
                    )
                ],
            ),
            current_artifacts=current,
            doc_map=evidence["doc_map"],
            evidence_packs=evidence,
            settings=_regeneration_settings(tmp_path),
            ctx=_regeneration_ctx(),
            source_status=current["source_status"],
            categories=["Category"],
        ),
        openai_client=_FakeOpenAIClient(),
        prompt_client=_FakePromptClient(),
    )

    assert response.updated_artifacts["expert_comment"] != current["expert_comment"]
    for root in ("insights_candidates", "insights_final"):
        before = {
            item["id"]: (item.get("text"), item.get("evidence_id"), item.get("pages"))
            for item in current[root]
        }
        after = {
            item["id"]: (item.get("text"), item.get("evidence_id"), item.get("pages"))
            for item in response.updated_artifacts[root]
        }
        assert after == before
    assert response.updated_artifacts["summary"]["tldr"] == current["summary"]["tldr"]
    assert (
        response.updated_artifacts["summary"]["executive_summary"]
        == current["summary"]["executive_summary"]
    )
    assert [
        (
            item.get("claim"),
            item.get("evidence"),
            item.get("evidence_id"),
            item.get("pages"),
        )
        for item in response.updated_artifacts["summary"]["claim_evidence_map"]
    ] == [
        (
            item.get("claim"),
            item.get("evidence"),
            item.get("evidence_id"),
            item.get("pages"),
        )
        for item in current["summary"]["claim_evidence_map"]
    ]


def test_enabled_visual_cache_without_fact_snapshot_fails_closed(tmp_path):
    current = _current_artifacts()
    current["_cache"]["visual_authority_canary"] = {
        "enabled": True,
        "admitted_candidates": deepcopy(current["insights_final"][:2]),
    }
    evidence = _regeneration_evidence_packs()

    with pytest.raises(AppError, match="complete visual fact snapshot"):
        _test_regenerate_artifacts(
            _visual_regeneration_request(current, evidence, tmp_path),
            openai_client=_FakeOpenAIClient(),
            prompt_client=_FakePromptClient(),
        )


def test_verified_regeneration_preserves_unrelated_toc_during_insight_repair(tmp_path):
    current = _current_artifacts()
    admitted = deepcopy(current["insights_final"][:2])
    visual_admission = _verified_admission(admitted, digest="f" * 64)
    current["insights_candidates"] = deepcopy(admitted)
    current["verified_facts"] = deepcopy(visual_admission.verified_facts)
    current["toc_entries"] = [
        {
            "section_id": "raw-section",
            "section_title": "Raw discovery title",
            "display_title": "Raw discovery title",
            "summary": "Raw discovery summary",
            "topic_matters": "Raw discovery summary",
            "key_points": [],
            "evidence_ids": [],
            "pages": [],
            "order": 1,
            "status": "toc_only",
        }
    ]
    current["toc_topics"] = ["Raw discovery title"]
    current["toc_topics_expanded"] = [
        {
            "topic": "Raw discovery title",
            "summary": "Raw discovery summary",
            "key_points": [],
        }
    ]
    current["_cache"]["visual_authority_canary"] = {
        "enabled": True,
        "digest": "f" * 64,
        "verified_fact_digest": "f" * 64,
        "verified_facts": deepcopy(visual_admission.verified_facts),
        "verified_evidence_packs": deepcopy(visual_admission.verified_evidence_packs),
        "admitted_candidates": deepcopy(visual_admission.admitted_candidates),
        "audit": {"admitted_count": 2},
    }
    evidence = _regeneration_evidence_packs()

    response = _test_regenerate_artifacts(
        _visual_regeneration_request(current, evidence, tmp_path),
        openai_client=_FakeOpenAIClient(),
        prompt_client=_FakePromptClient(),
    )

    assert response.updated_artifacts["toc_entries"] == current["toc_entries"]
    assert response.updated_artifacts["toc_topics"] == current["toc_topics"]
    assert (
        response.updated_artifacts["toc_topics_expanded"]
        == current["toc_topics_expanded"]
    )
