# ruff: noqa: F401,F403,F405
from __future__ import annotations

from pathlib import Path as _SplitPath

__file__ = str(
    _SplitPath(__file__).resolve().parent.parent
    / "test_report_regeneration_identity_and_failures.py"
)

from ._split_support_test_report_regeneration_identity_and_failures import *  # noqa: F401,F403


def test_empty_quarantined_grounding_skips_provider_strategies_before_regeneration(
    tmp_path,
):
    artifacts = _current_artifacts()
    artifacts["summary"]["claim_evidence_map"] = [
        {
            "claim": "The unsupported claim has no retained backing.",
            "evidence_id": "rejected-source",
            "evidence": "Rejected claim evidence.",
            "pages": [27],
        },
        {
            "id": "supported-sibling",
            "claim": "The sibling has distinct retained backing.",
            "evidence_id": "sibling-source",
            "evidence": "Retained evidence for the sibling claim.",
            "pages": [28],
        },
    ]
    issue = ValidationIssue(
        schema_version="1.0",
        message="The claim is not established by its cited source.",
        severity="error",
        affected_section="summary.claim_evidence_map:1.claim",
        rule_id="grounding",
    )
    evidence_packs = {
        "findings": {
            "findings": [
                {
                    "id": "sibling-source",
                    "evidence": "Retained evidence for the sibling claim.",
                    "pages": [28],
                }
            ]
        },
        "doc_map": {"sections": []},
    }
    plan = _build_regeneration_plan(
        issues=[issue],
        artifacts=artifacts,
        broad_retry_available=False,
    )
    rejected_strategy_keys = set()

    plan, skipped = _preflight_empty_grounding_strategies(
        plan=plan,
        issues=[issue],
        artifacts=artifacts,
        evidence_packs=evidence_packs,
        rejected_strategy_keys=rejected_strategy_keys,
        broad_retry_available=False,
    )

    assert skipped == [("summary", "current_evidence")]
    assert plan.targets[0].repair_action == "REMOVE_CLAIM"
    assert plan.targets[0].repair_strategy == "safe_removal"
    assert plan.targets[0].allowed_paths == ["summary.claim_evidence_map[0]"]
    assert plan.targets[0].selected_evidence_ids == []

    openai_client = _FakeOpenAIClient()
    prompt_client = _FakePromptClient()
    response = regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=1,
            plan=plan,
            current_artifacts=artifacts,
            doc_map=evidence_packs["doc_map"],
            evidence_packs=evidence_packs,
            settings=_settings(tmp_path),
            ctx=_ctx(),
            source_status=artifacts["source_status"],
            categories=["Category"],
            vector_store_id=None,
            md5="md5",
        ),
        openai_client=openai_client,
        prompt_client=prompt_client,
    )
    assert response.updated_artifacts["summary"]["claim_evidence_map"] == [
        artifacts["summary"]["claim_evidence_map"][1]
    ]
    assert openai_client.calls == []
    assert prompt_client.render_calls == []


def test_insight_rebind_without_direct_alternative_advances_to_safe_removal():
    artifacts = _current_artifacts()
    artifacts["insights_final"][0]["evidence_id"] = "quarantined-finding"
    artifacts["insights_final"][0]["pages"] = [7]
    issue = ValidationIssue(
        schema_version="1.1",
        rule_id="grounding",
        message="The insight is unsupported by its quarantined source.",
        severity="error",
        affected_section="insights:insight-1.text",
        entity_id="insight-1",
        evidence_ids=["quarantined-finding"],
    )
    first_plan = _build_regeneration_plan(
        issues=[issue],
        artifacts=artifacts,
        broad_retry_available=False,
    )
    rejected_strategies = {
        repair_strategy_fingerprint(
            [first_plan.targets[0].issues[0].failure_fingerprint],
            first_plan.targets[0].repair_strategy,
            first_plan.targets[0].selected_evidence_ids,
        )
    }
    alternative_plan = _build_regeneration_plan(
        issues=[issue],
        artifacts=artifacts,
        broad_retry_available=False,
        rejected_strategy_keys=rejected_strategies,
    )
    assert alternative_plan.targets[0].repair_action == "REBIND_EVIDENCE"
    assert alternative_plan.targets[0].repair_strategy == "alternative_evidence"

    evidence_packs = {
        "findings": {
            "findings": [
                {
                    "id": "quarantined-finding",
                    "text": "The rejected insight source.",
                    "evidence": "The rejected insight source.",
                    "pages": [7],
                }
            ]
        },
        "doc_map": {
            "sections": [
                {
                    "id": "executive-summary",
                    "summary": "A section summary is not direct source evidence.",
                    "pages": [7],
                }
            ]
        },
    }
    plan, skipped = _preflight_empty_grounding_strategies(
        plan=alternative_plan,
        issues=[issue],
        artifacts=artifacts,
        evidence_packs=evidence_packs,
        rejected_strategy_keys=rejected_strategies,
        broad_retry_available=False,
    )

    assert skipped == [("insights_bundle", "alternative_evidence")]
    assert plan.targets[0].repair_action == "REMOVE_CLAIM"
    assert plan.targets[0].repair_strategy == "safe_removal"


def test_retry_plan_keeps_new_blocking_family_failure_with_original_failure():
    artifacts = _current_artifacts()
    summary_claim = next(
        claim
        for claim in artifacts["soft_copy_claim_provenance"]["claims"]
        if claim["artifact_family"] == "summary"
    )
    expert_claim = next(
        claim
        for claim in artifacts["soft_copy_claim_provenance"]["claims"]
        if claim["artifact_family"] == "expert_comment"
    )
    original_issue = ValidationIssue(
        schema_version="1.1",
        rule_id="grounding",
        message="The summary claim is not established by its evidence.",
        severity="error",
        affected_section="summary.tldr",
        entity_id=summary_claim["claim_id"],
        evidence_ids=["f1"],
    )
    introduced_expert_issue = FailureFingerprint(
        rule_id="grounding",
        affected_section="expert_comment",
        entity_id=expert_claim["claim_id"],
        evidence_ids=["f1"],
    )

    plan = _build_regeneration_plan(
        issues=[original_issue],
        artifacts=artifacts,
        broad_retry_available=False,
        repair_memory=[RepairDelta(introduced_hard_failures=[introduced_expert_issue])],
    )

    assert [target.target_section for target in plan.targets] == [
        "summary",
        "expert_comment",
    ]
    assert all(
        target.repair_action == "REGENERATE_ITEM" for target in plan.targets
    )


def test_quotes_ladder_rejects_failed_restore_before_rewrite() -> None:
    issue = ValidationIssue(
        schema_version="1.1",
        rule_id="grounding",
        message="[factual_claim|misattributed_quote] Quote not verbatim.",
        severity="error",
        affected_section="quotes:q1",
        evidence_ids=["q1"],
    )

    plan = _build_regeneration_plan(
        issues=[issue],
        artifacts=_current_artifacts(),
        broad_retry_available=False,
    )
    assert plan.targets[0].repair_action == "COPY_CANONICAL_SOURCE_VALUE"
    assert plan.targets[0].repair_strategy == "canonical_quote_restore"

    fingerprints = [plan.targets[0].issues[0].failure_fingerprint]
    rejected_restore = {
        repair_strategy_fingerprint(fingerprints, "canonical_quote_restore", ["q1"])
    }
    second_plan = _build_regeneration_plan(
        issues=[issue],
        artifacts=_current_artifacts(),
        broad_retry_available=False,
        rejected_strategy_keys=rejected_restore,
    )
    assert second_plan.targets[0].repair_strategy == "current_evidence"
    assert second_plan.targets[0].repair_action == "REGENERATE_ITEM"


def test_identity_ladder_abstains_then_exhausts_without_repeats() -> None:
    issue = ValidationIssue(
        schema_version="1.1",
        rule_id="grounding",
        message=(
            "[factual_claim|unsupported_factual_claim] Title not supported: "
            "Wrong Title."
        ),
        severity="error",
        affected_section="metadata.title",
    )

    first_plan = _build_regeneration_plan(
        issues=[issue],
        artifacts=_current_artifacts(),
        broad_retry_available=False,
    )
    assert first_plan.targets[0].repair_strategy == "canonical_identity"
    assert first_plan.targets[0].repair_action == "COPY_CANONICAL_SOURCE_VALUE"

    fingerprints = [first_plan.targets[0].issues[0].failure_fingerprint]
    rejected_identity = {
        repair_strategy_fingerprint(fingerprints, "canonical_identity", [])
    }
    second_plan = _build_regeneration_plan(
        issues=[issue],
        artifacts=_current_artifacts(),
        broad_retry_available=False,
        rejected_strategy_keys=rejected_identity,
    )
    assert second_plan.targets[0].repair_strategy == "safe_abstain"
    assert second_plan.targets[0].repair_action == "ABSTAIN"

    rejected_abstain = rejected_identity | {
        repair_strategy_fingerprint(fingerprints, "safe_abstain", [])
    }
    exhausted_plan = _build_regeneration_plan(
        issues=[issue],
        artifacts=_current_artifacts(),
        broad_retry_available=False,
        rejected_strategy_keys=rejected_abstain,
    )
    # Every distinct identity strategy is rejected: no targeted plan remains,
    # so the loop stops with a typed terminal failure instead of repeating.
    assert exhausted_plan.mode == "skip"
    assert exhausted_plan.targets == []


def test_key_figure_ladder_has_one_deterministic_rebuild_strategy() -> None:
    artifacts = _current_artifacts()
    artifacts["key_figures"] = [
        {
            "figure_id": "figure-1",
            "insight_id": "insight-1",
            "figure": "50.0",
            "evidence_id": "f1",
        }
    ]
    issue = ValidationIssue(
        schema_version="1.1",
        rule_id="numbers",
        message="[numbers] Number 50.0 not present in report or evidence.",
        severity="error",
        affected_section="key_figures:figure-1.figure",
        entity_id="key_figure:figure-1:figure",
        evidence_ids=["f1"],
        repair_target="key_figures",
    )

    first_plan = _build_regeneration_plan(
        issues=[issue],
        artifacts=artifacts,
        broad_retry_available=False,
    )
    assert first_plan.targets[0].target_section == "key_figures"
    assert first_plan.targets[0].repair_strategy == "current_evidence"
    assert first_plan.targets[0].repair_action == "REGENERATE_ITEM"
    assert first_plan.targets[0].regenerate_steps == ["key_figures"]
    assert first_plan.targets[0].prompt_namespaces == []

    fingerprints = [first_plan.targets[0].issues[0].failure_fingerprint]
    rejected_current = {
        repair_strategy_fingerprint(fingerprints, "current_evidence", ["f1"])
    }
    exhausted_plan = _build_regeneration_plan(
        issues=[issue],
        artifacts=artifacts,
        broad_retry_available=False,
        rejected_strategy_keys=rejected_current,
    )

    assert exhausted_plan.mode == "skip"
    assert exhausted_plan.targets == []


def test_attempt_strategy_fingerprint_describes_actual_selection() -> None:
    from src.orchestrators._report_analysis_orchestrator.validation import (
        _attempt_strategy_fingerprint,
        _plan_strategy_fingerprint,
    )

    artifacts = _current_artifacts()
    next(
        claim
        for claim in artifacts["soft_copy_claim_provenance"]["claims"]
        if claim["artifact_family"] == "expert_comment"
    )["evidence_ids"] = ["f1"]
    issue = ValidationIssue(
        schema_version="1.1",
        rule_id="grounding",
        message="[factual_claim|unsupported_factual_claim] Unsupported claim.",
        severity="error",
        affected_section="expert_comment",
        evidence_ids=["f1"],
    )
    plan = _build_regeneration_plan(
        issues=[issue],
        artifacts=artifacts,
        broad_retry_available=False,
    )
    response = SimpleNamespace(
        repair_action="REBIND_EVIDENCE",
        repair_strategy="alternative_evidence",
        selected_evidence_ids=["f9"],
        payload_overrides={},
    )

    actual = _attempt_strategy_fingerprint(plan, response)
    planned = _plan_strategy_fingerprint(plan)

    assert actual == repair_strategy_fingerprint(
        [plan.targets[0].issues[0].failure_fingerprint],
        "alternative_evidence",
        ["f9"],
    )
    assert actual != planned
    # Legacy responses without actual strategy fall back to the plan view.
    legacy = SimpleNamespace()
    assert _attempt_strategy_fingerprint(plan, legacy) == planned
