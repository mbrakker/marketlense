from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from src.contracts.regeneration import (
    ArtifactRegenerationRequest,
    RegenerationIssue,
    RegenerationPlan,
    RegenerationTarget,
)
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
    assert (
        response.updated_artifacts["_cache"]["visual_authority_canary"]["digest"]
        == "e" * 64
    )


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
        (item.get("claim"), item.get("evidence_id"), item.get("pages"))
        for item in response.updated_artifacts["summary"]["claim_evidence_map"]
    ] == [
        (item.get("claim"), item.get("evidence_id"), item.get("pages"))
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


def test_verified_regeneration_replaces_stale_toc_with_structural_context(tmp_path):
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

    assert "Raw discovery title" not in response.updated_artifacts["toc_topics"]
    assert all(
        "Raw discovery summary" not in str(item)
        for item in response.updated_artifacts["toc_topics_expanded"]
    )
