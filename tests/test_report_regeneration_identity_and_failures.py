from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.contracts.openai import OpenAIResponseResult
from src.contracts.regeneration import (
    ArtifactRegenerationRequest,
    RegenerationIssue,
    RegenerationPlan,
    RegenerationTarget,
    repair_strategy_fingerprint,
)
from src.contracts.validation import ValidationIssue
from src.generators.report_regeneration_generator import regenerate_artifacts
from src.utils.errors import AppError
from tests.test_report_regeneration_generator import (
    METRIC,
    _build_regeneration_plan,
    _ctx,
    _current_artifacts,
    _evidence_packs,
    _FakeOpenAIClient,
    _FakePromptClient,
    _settings,
)
from ._test_report_regeneration_identity_and_failures._shared import (
    _source_backed_artifacts,
)


def test_regenerate_artifacts_propagates_retryable_app_error(
    tmp_path, assert_app_error
):
    class _RetryingOpenAI(_FakeOpenAIClient):
        def _legacy_chat_json(self, req, ctx):
            del req, ctx
            raise AppError(
                code="openai_chat_failed",
                message="retry later",
                retryable=True,
            )

    with pytest.raises(AppError) as exc_info:
        regenerate_artifacts(
            ArtifactRegenerationRequest(
                report_id="report-1",
                report_name="report-1",
                attempt_index=1,
                plan=RegenerationPlan(
                    mode="targeted",
                    targets=[
                        RegenerationTarget(
                            target_section="summary",
                            regenerate_steps=["summary"],
                            prompt_namespaces=[
                                "report_vs/artifacts/regenerate/summary"
                            ],
                            issues=[
                                RegenerationIssue(
                                    rule_id="grounding",
                                    affected_section="executive_summary",
                                    message="[grounding] Unsupported summary claim",
                                    severity="error",
                                    evidence_ids=["f1"],
                                    pages=[1],
                                )
                            ],
                            allowed_paths=[
                                "summary.executive_summary[claim_index=0]"
                            ],
                        )
                    ],
                    unmappable_issues=[],
                    broad_retry_allowed=True,
                ),
                current_artifacts=_current_artifacts(),
                doc_map=_evidence_packs()["doc_map"],
                evidence_packs=_evidence_packs(),
                settings=_settings(tmp_path),
                ctx=_ctx(),
                source_status=_current_artifacts()["source_status"],
                categories=["Category"],
                vector_store_id=None,
                md5="md5",
            ),
            openai_client=_RetryingOpenAI(),
            prompt_client=_FakePromptClient(),
        )

    assert_app_error(
        exc_info.value,
        code="openai_chat_failed",
        retryable=True,
        severity="error",
    )


def test_regenerate_artifacts_propagates_non_retryable_prompt_error(
    tmp_path,
    assert_app_error,
):
    class _FailingPromptClient(_FakePromptClient):
        def load_prompt_set(self, req, ctx):
            del req, ctx
            raise AppError(
                code="prompt_not_found",
                message="missing prompt",
                retryable=False,
            )

    with pytest.raises(AppError) as exc_info:
        regenerate_artifacts(
            ArtifactRegenerationRequest(
                report_id="report-1",
                report_name="report-1",
                attempt_index=1,
                plan=RegenerationPlan(
                    mode="targeted",
                    targets=[
                        RegenerationTarget(
                            target_section="summary",
                            regenerate_steps=["summary"],
                            prompt_namespaces=[
                                "report_vs/artifacts/regenerate/summary"
                            ],
                            issues=[
                                RegenerationIssue(
                                    rule_id="grounding",
                                    affected_section="executive_summary",
                                    message="[grounding] Unsupported summary claim",
                                    severity="error",
                                    evidence_ids=["f1"],
                                    pages=[1],
                                )
                            ],
                            allowed_paths=[
                                "summary.executive_summary[claim_index=0]"
                            ],
                        )
                    ],
                    unmappable_issues=[],
                    broad_retry_allowed=True,
                ),
                current_artifacts=_current_artifacts(),
                doc_map=_evidence_packs()["doc_map"],
                evidence_packs=_evidence_packs(),
                settings=_settings(tmp_path),
                ctx=_ctx(),
                source_status=_current_artifacts()["source_status"],
                categories=["Category"],
                vector_store_id=None,
                md5="md5",
            ),
            openai_client=_FakeOpenAIClient(),
            prompt_client=_FailingPromptClient(),
        )

    assert_app_error(
        exc_info.value,
        code="prompt_not_found",
        retryable=False,
        severity="error",
    )


def test_regenerate_artifacts_rejects_unknown_target_section(
    tmp_path,
    assert_app_error,
):
    with pytest.raises(AppError) as exc_info:
        regenerate_artifacts(
            ArtifactRegenerationRequest(
                report_id="report-1",
                report_name="report-1",
                attempt_index=1,
                plan=RegenerationPlan(
                    mode="targeted",
                    targets=[
                        RegenerationTarget(
                            target_section="unsupported_section",
                            regenerate_steps=["summary"],
                            prompt_namespaces=[
                                "report_vs/artifacts/regenerate/summary"
                            ],
                            issues=[
                                RegenerationIssue(
                                    rule_id="grounding",
                                    affected_section="executive_summary",
                                    message="[grounding] Unsupported summary claim",
                                    severity="error",
                                    evidence_ids=["f1"],
                                    pages=[1],
                                )
                            ],
                        )
                    ],
                    unmappable_issues=[],
                    broad_retry_allowed=True,
                ),
                current_artifacts=_current_artifacts(),
                doc_map=_evidence_packs()["doc_map"],
                evidence_packs=_evidence_packs(),
                settings=_settings(tmp_path),
                ctx=_ctx(),
                source_status=_current_artifacts()["source_status"],
                categories=["Category"],
                vector_store_id=None,
                md5="md5",
            ),
            openai_client=_FakeOpenAIClient(),
            prompt_client=_FakePromptClient(),
        )

    assert_app_error(
        exc_info.value,
        code="artifact_regeneration_target_unsupported",
        retryable=False,
        severity="error",
    )


class _NoModelCallsAllowed:
    """Fail the test the moment a repair attempts a model call."""

    def __init__(self) -> None:
        self.calls: list = []

    def openai_chat_json(self, req, ctx):
        self.calls.append(req)
        raise AssertionError("Deterministic repair must not call the model")

    def openai_chat_json_with_images(self, req, ctx):
        self.calls.append(req)
        raise AssertionError("Deterministic repair must not call the model")

    def openai_respond(self, req, ctx):
        self.calls.append(req)
        raise AssertionError("Deterministic repair must not call the model")

    def openai_respond_with_vector_store(self, req, ctx):
        self.calls.append(req)
        raise AssertionError("Deterministic repair must not call the model")


def _identity_plan() -> RegenerationPlan:
    return RegenerationPlan(
        mode="targeted",
        targets=[
            RegenerationTarget(
                target_section="report_identity",
                regenerate_steps=[],
                prompt_namespaces=[],
                issues=[
                    RegenerationIssue(
                        rule_id="grounding",
                        affected_section="metadata.title",
                        message=(
                            "[factual_claim|unsupported_factual_claim] The summary "
                            "title is not supported by retained evidence."
                        ),
                        severity="error",
                    )
                ],
                repair_action="COPY_CANONICAL_SOURCE_VALUE",
                repair_strategy="canonical_identity",
            )
        ],
        unmappable_issues=[],
        broad_retry_allowed=False,
    )


def test_metadata_title_grounding_failure_routes_to_report_identity_repair() -> None:
    issue = ValidationIssue(
        schema_version="1.1",
        rule_id="grounding",
        message=(
            "[factual_claim|unsupported_factual_claim] Title not supported by "
            "retained evidence: Wrong Title."
        ),
        severity="error",
        affected_section="metadata.title",
    )

    plan = _build_regeneration_plan(
        issues=[issue],
        artifacts=_current_artifacts(),
        broad_retry_available=False,
    )

    assert plan.mode == "targeted"
    assert [target.target_section for target in plan.targets] == ["report_identity"]
    target = plan.targets[0]
    assert target.repair_action == "COPY_CANONICAL_SOURCE_VALUE"
    assert target.repair_strategy == "canonical_identity"
    assert target.regenerate_steps == []
    assert target.prompt_namespaces == []


def test_plan_declares_one_insight_field_path() -> None:
    issue = ValidationIssue(
        schema_version="1.1",
        rule_id="retained_claim.number_value_unit_match",
        message="[retained_claim.number_value_unit_match|quantity_not_entailed] Failed.",
        severity="error",
        affected_section="insights:insight-1.text",
        entity_id="insight:insight-1:text",
        evidence_ids=["f1"],
    )

    plan = _build_regeneration_plan(
        issues=[issue],
        artifacts=_current_artifacts(),
        broad_retry_available=False,
    )

    assert plan.targets[0].allowed_paths == ["insights_final[item=insight-1].text"]


def test_report_identity_repair_copies_canonical_title_without_model_calls(
    tmp_path,
) -> None:
    openai_client = _NoModelCallsAllowed()
    current_artifacts = _source_backed_artifacts()
    response = regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=1,
            plan=_identity_plan(),
            current_artifacts=current_artifacts,
            doc_map=_evidence_packs()["doc_map"],
            evidence_packs=_evidence_packs(),
            settings=_settings(tmp_path),
            ctx=_ctx(),
            source_status=current_artifacts["source_status"],
            categories=["Category"],
            vector_store_id=None,
            md5="md5",
        ),
        openai_client=openai_client,
        prompt_client=_FakePromptClient(),
    )

    assert openai_client.calls == []
    assert response.payload_overrides == {"title": "Doc title"}
    assert response.repair_action == "COPY_CANONICAL_SOURCE_VALUE"
    assert response.repair_strategy == "canonical_identity"
    assert response.selected_evidence_ids == []
    assert response.regenerated_sections == ["report_identity"]
    # Unrelated claim families keep their retained content byte-for-byte;
    # assembly only adds its deterministic derived provenance (evidence spans).
    after = response.updated_artifacts
    for field_name in ("tldr", "card_tldr_compact", "executive_summary"):
        assert after["summary"][field_name] == current_artifacts["summary"][field_name]
    assert [
        (item["id"], item["text"], item["evidence_id"])
        for item in after["insights_final"]
    ] == [
        (item["id"], item["text"], item["evidence_id"])
        for item in current_artifacts["insights_final"]
    ]
    assert [item["text"] for item in after["quotes_final"]] == ["Old quote"]
    assert after["expert_comment"] == current_artifacts["expert_comment"]
    assert after["linkedin_post"] == current_artifacts["linkedin_post"]


def test_model_repair_changes_only_the_identified_final_insight(tmp_path) -> None:
    current_artifacts = _source_backed_artifacts()
    before_final = [dict(item) for item in current_artifacts["insights_final"]]
    before_candidates = [
        dict(item) for item in current_artifacts["insights_candidates"]
    ]
    plan = RegenerationPlan(
        mode="targeted",
        targets=[
            RegenerationTarget(
                target_section="insights_bundle",
                regenerate_steps=["insights_final"],
                prompt_namespaces=["report_vs/artifacts/regenerate/insights_final"],
                issues=[
                    RegenerationIssue(
                        rule_id="grounding",
                        affected_section="insights:insight-1.text",
                        message="[grounding|unsupported_factual_claim] Repair one item.",
                        severity="error",
                        entity_id="insight:insight-1:text",
                        evidence_ids=["f1"],
                    )
                ],
                repair_action="REGENERATE_ITEM",
                repair_strategy="current_evidence",
                allowed_paths=["insights_final[item=insight-1].text"],
            )
        ],
        unmappable_issues=[],
        broad_retry_allowed=False,
    )
    openai_client = _FakeOpenAIClient()

    response = regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=1,
            plan=plan,
            current_artifacts=current_artifacts,
            doc_map=_evidence_packs()["doc_map"],
            evidence_packs=_evidence_packs(),
            settings=_settings(tmp_path),
            ctx=_ctx(),
            source_status=current_artifacts["source_status"],
            categories=["Category"],
            vector_store_id=None,
            md5="md5",
        ),
        openai_client=openai_client,
        prompt_client=_FakePromptClient(),
    )

    after_final = response.updated_artifacts["insights_final"]
    assert len(openai_client.calls) == 1
    assert len(after_final) == len(before_final)
    for before, after in zip(before_final, after_final, strict=True):
        if before["id"] == "insight-1":
            assert after["text"] == "Repaired final insight"
            assert after["metric"] == before["metric"]
        else:
            assert after == before
    assert response.updated_artifacts["insights_candidates"] == before_candidates


def test_model_repair_changes_only_the_identified_quote(tmp_path) -> None:
    class _AtomicQuoteOpenAIClient(_FakeOpenAIClient):
        def _legacy_chat_json(self, req, ctx):
            del ctx
            self.calls.append(req)
            return OpenAIResponseResult(
                schema_version="1.0",
                text=(
                    '{"quotes_final":[{"evidence_id":"q1","text":"Repaired quote."},'
                    '{"evidence_id":"q2","text":"Altered sibling quote."}]}'
                ),
                parsed_json={
                    "quotes_final": [
                        {"evidence_id": "q1", "text": "Repaired quote."},
                        {"evidence_id": "q2", "text": "Altered sibling quote."},
                    ]
                },
                request_id="req-atomic-quote",
            )

    current_artifacts = _source_backed_artifacts()
    current_artifacts["quotes_final"].append(
        {
            "id": "q2",
            "text": "Untouched sibling quote.",
            "speaker": "Other speaker",
            "evidence_id": "q2",
            "page": 2,
        }
    )
    before_quotes = [dict(item) for item in current_artifacts["quotes_final"]]
    plan = RegenerationPlan(
        mode="targeted",
        targets=[
            RegenerationTarget(
                target_section="quotes",
                regenerate_steps=["quotes"],
                prompt_namespaces=["report_vs/artifacts/regenerate/quotes"],
                issues=[
                    RegenerationIssue(
                        rule_id="grounding",
                        affected_section="quotes:q1",
                        message="[grounding|unsupported_quote] repair one quote",
                        severity="error",
                        entity_id="quote:q1:text",
                        evidence_ids=["q1"],
                    )
                ],
                repair_action="REGENERATE_ITEM",
                repair_strategy="current_evidence",
                allowed_paths=["quotes_final[0].text"],
            )
        ],
        unmappable_issues=[],
        broad_retry_allowed=False,
    )
    openai_client = _AtomicQuoteOpenAIClient()

    response = regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=1,
            plan=plan,
            current_artifacts=current_artifacts,
            doc_map=_evidence_packs()["doc_map"],
            evidence_packs=_evidence_packs(),
            settings=_settings(tmp_path),
            ctx=_ctx(),
            source_status=current_artifacts["source_status"],
            categories=["Category"],
            vector_store_id=None,
            md5="md5",
        ),
        openai_client=openai_client,
        prompt_client=_FakePromptClient(),
    )

    after_quotes = response.updated_artifacts["quotes_final"]
    assert len(openai_client.calls) == 1
    assert after_quotes[0]["text"] == "Repaired quote."
    assert after_quotes[1] == before_quotes[1]


def test_report_identity_repair_abstains_without_canonical_source(tmp_path) -> None:
    openai_client = _NoModelCallsAllowed()
    current_artifacts = _source_backed_artifacts()
    doc_map = {"doc_id": "doc-1", "sections": []}
    response = regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=1,
            plan=_identity_plan(),
            current_artifacts=current_artifacts,
            doc_map=doc_map,
            evidence_packs=_evidence_packs(),
            settings=_settings(tmp_path),
            ctx=_ctx(),
            source_status=current_artifacts["source_status"],
            categories=["Category"],
            vector_store_id=None,
            md5="md5",
        ),
        openai_client=openai_client,
        prompt_client=_FakePromptClient(),
    )

    assert openai_client.calls == []
    assert response.payload_overrides == {}
    assert response.repair_action == "ABSTAIN"


def _quotes_plan() -> RegenerationPlan:
    return RegenerationPlan(
        mode="targeted",
        targets=[
            RegenerationTarget(
                target_section="quotes",
                regenerate_steps=["quotes"],
                prompt_namespaces=["report_vs/artifacts/regenerate/quotes"],
                issues=[
                    RegenerationIssue(
                        rule_id="grounding",
                        affected_section="quotes:q1",
                        message=(
                            "[factual_claim|misattributed_quote] Quote text is not "
                            "verbatim: A drifted paraphrase of the source."
                        ),
                        severity="error",
                        evidence_ids=["q1"],
                    )
                ],
                repair_action="COPY_CANONICAL_SOURCE_VALUE",
                repair_strategy="canonical_quote_restore",
            )
        ],
        unmappable_issues=[],
        broad_retry_allowed=False,
    )


def test_exact_quote_failure_restores_retained_source_without_model_calls(
    tmp_path,
) -> None:
    openai_client = _NoModelCallsAllowed()
    current_artifacts = _source_backed_artifacts()
    current_artifacts["quotes_final"][0]["text"] = "A drifted paraphrase of the source."
    response = regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=1,
            plan=_quotes_plan(),
            current_artifacts=current_artifacts,
            doc_map=_evidence_packs()["doc_map"],
            evidence_packs=_evidence_packs(),
            settings=_settings(tmp_path),
            ctx=_ctx(),
            source_status=current_artifacts["source_status"],
            categories=["Category"],
            vector_store_id=None,
            md5="md5",
        ),
        openai_client=openai_client,
        prompt_client=_FakePromptClient(),
    )

    assert openai_client.calls == []
    assert response.repair_action == "COPY_CANONICAL_SOURCE_VALUE"
    assert response.repair_strategy == "canonical_quote_restore"
    assert "q1" in response.selected_evidence_ids
    assert response.regenerated_sections == ["quotes"]
    restored_quote = response.updated_artifacts["quotes_final"][0]
    assert restored_quote["text"] == "Old quote"
    assert restored_quote["speaker"] == "Speaker"
    assert restored_quote["evidence_id"] == "q1"
    assert len(response.updated_artifacts["quotes_final"]) == 1
    for field_name in ("tldr", "card_tldr_compact", "executive_summary"):
        assert (
            response.updated_artifacts["summary"][field_name]
            == current_artifacts["summary"][field_name]
        )


def test_insight_metric_conflict_is_corrected_from_retained_candidate(
    tmp_path,
) -> None:
    openai_client = _NoModelCallsAllowed()
    current_artifacts = _source_backed_artifacts()
    evidence_packs = _evidence_packs()
    evidence_packs["findings"]["findings"][0] = {
        "id": "f1",
        "evidence": "Europe margin reached 46% in 2025.",
        "text": "Europe margin reached 46% in 2025.",
        "page": 1,
    }
    supported_text = "Europe margin reached 46% in 2025."
    candidate_metric = dict(
        METRIC, label="Europe margin", value="46%", unit="%", geography="Europe"
    )
    drifted_metric = dict(
        METRIC, label="Drifted label", value="99%", unit="%", geography="Global"
    )
    current_artifacts["insights_candidates"] = [
        {
            "id": "insight-1",
            "text": supported_text,
            "evidence_id": "f1",
            "evidence": "Europe margin reached 46% in 2025.",
            "metric": dict(candidate_metric),
            "pages": [1],
            "score": 1.0,
        }
    ] + current_artifacts["insights_candidates"]
    current_artifacts["insights_final"][0] = {
        "id": "insight-1",
        "text": supported_text,
        "evidence_id": "missing-evidence",
        "evidence": "Drifted evidence binding.",
        "metric": dict(drifted_metric),
        "pages": [99],
    }
    plan = RegenerationPlan(
        mode="targeted",
        targets=[
            RegenerationTarget(
                target_section="insights_bundle",
                regenerate_steps=["insights_candidates", "insights_final"],
                prompt_namespaces=[
                    "report_vs/artifacts/regenerate/insights_candidates",
                    "report_vs/artifacts/regenerate/insights_final",
                ],
                issues=[
                    RegenerationIssue(
                        rule_id="grounding",
                        affected_section="insights:insight-1.text",
                        message=(
                            "[factual_claim|numerically_inconsistent] Protected "
                            "dimensions: value, geography."
                        ),
                        severity="error",
                        entity_id="insight:insight-1:text",
                        evidence_ids=["f1"],
                    )
                ],
                repair_action="CORRECT_PROTECTED_FACT",
                repair_strategy="canonical_metric_copy",
                allowed_paths=[
                    "insights_final[item=insight-1].text",
                    "insights_final[item=insight-1].metric",
                    "insights_final[item=insight-1].evidence_id",
                    "insights_final[item=insight-1].evidence",
                    "insights_final[item=insight-1].evidence_spans",
                    "insights_final[item=insight-1].pages",
                ],
            )
        ],
        unmappable_issues=[],
        broad_retry_allowed=False,
    )
    response = regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=1,
            plan=plan,
            current_artifacts=current_artifacts,
            doc_map=evidence_packs["doc_map"],
            evidence_packs=evidence_packs,
            settings=_settings(tmp_path),
            ctx=_ctx(),
            source_status=current_artifacts["source_status"],
            categories=["Category"],
            vector_store_id=None,
            md5="md5",
        ),
        openai_client=openai_client,
        prompt_client=_FakePromptClient(),
    )

    assert openai_client.calls == []
    assert response.repair_action == "CORRECT_PROTECTED_FACT"
    assert response.repair_strategy == "canonical_metric_copy"
    assert "f1" in response.selected_evidence_ids
    repaired_insight = next(
        insight
        for insight in response.updated_artifacts["insights_final"]
        if insight["id"] == "insight-1"
    )
    assert repaired_insight["metric"]["value"] == "46%"
    assert repaired_insight["metric"]["geography"] == "Europe"
    assert repaired_insight["evidence_id"] == "f1"
    assert repaired_insight["evidence"] == "Europe margin reached 46% in 2025."
    assert repaired_insight["pages"] == [1]
    untouched = next(
        insight
        for insight in response.updated_artifacts["insights_final"]
        if insight["id"] == "insight-2"
    )
    assert untouched == current_artifacts["insights_final"][1]


def test_strategy_ladder_skips_rejected_and_stays_distinct() -> None:
    artifacts = _current_artifacts()
    next(
        claim
        for claim in artifacts["soft_copy_claim_provenance"]["claims"]
        if claim["artifact_family"] == "expert_comment"
    )["evidence_ids"] = ["f1"]
    issue = ValidationIssue(
        schema_version="1.1",
        rule_id="grounding",
        message="[factual_claim|unsupported_factual_claim] Unsupported expert claim.",
        severity="error",
        affected_section="expert_comment",
        entity_id="soft_copy:expert_comment:abc",
        evidence_ids=["f1"],
    )

    first_plan = _build_regeneration_plan(
        issues=[issue],
        artifacts=artifacts,
        broad_retry_available=False,
    )
    assert first_plan.targets[0].repair_strategy == "current_evidence"
    assert first_plan.targets[0].repair_action == "REGENERATE_ITEM"

    fingerprints = [first_plan.targets[0].issues[0].failure_fingerprint]
    rejected_current = {
        repair_strategy_fingerprint(fingerprints, "current_evidence", ["f1"])
    }
    second_plan = _build_regeneration_plan(
        issues=[issue],
        artifacts=artifacts,
        broad_retry_available=False,
        rejected_strategy_keys=rejected_current,
    )
    assert second_plan.targets[0].repair_strategy == "alternative_evidence"
    assert second_plan.targets[0].repair_action == "REBIND_EVIDENCE"

    rejected_alternative = rejected_current | {
        repair_strategy_fingerprint(fingerprints, "alternative_evidence", ["f1"])
    }
    third_plan = _build_regeneration_plan(
        issues=[issue],
        artifacts=artifacts,
        broad_retry_available=False,
        rejected_strategy_keys=rejected_alternative,
    )
    assert third_plan.targets[0].repair_strategy == "safe_removal"
    assert third_plan.targets[0].repair_action == "REMOVE_CLAIM"
    assert third_plan.targets[0].selected_evidence_ids == []


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
            "key_figure_id": "display-viewability-duration-criterion-retained-5",
            "figure": "50.0",
            "evidence_id": "s4",
        }
    ]
    issue = ValidationIssue(
        schema_version="1.1",
        rule_id="numbers",
        message="[numbers] Number 50.0 not present in report or evidence.",
        severity="error",
        affected_section="key_figures:display-viewability-duration-criterion-retained-5.figure",
        entity_id="key_figure:display-viewability-duration-criterion-retained-5:figure",
        evidence_ids=["s4"],
    )

    first_plan = _build_regeneration_plan(
        issues=[issue],
        artifacts=artifacts,
        broad_retry_available=False,
    )
    assert first_plan.targets[0].repair_strategy == "current_evidence"
    assert first_plan.targets[0].repair_action == "REGENERATE_ITEM"

    fingerprints = [first_plan.targets[0].issues[0].failure_fingerprint]
    rejected_current = {
        repair_strategy_fingerprint(fingerprints, "current_evidence", ["s4"])
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


from ._test_report_regeneration_identity_and_failures.cases_01_atomic_model_repair import *  # noqa: F401,F403
