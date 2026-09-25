"""Replay the sanitized StackAdapt and DoubleVerify A21 repair states."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.contracts.report_models import Figure, Quote, ReportPayload
from src.contracts.run_context import RunContext
from src.contracts.validation import ValidationIssue, ValidationRequest
from src.generators.public_editorial_quality_generator import (
    evaluate_public_editorial_quality,
    validation_issues_from_public_editorial_quality,
)
from src.generators.report_regeneration_generator import (
    _build_grounding_package,
    _build_regeneration_state,
    _handle_insights_bundle_regeneration,
    _RegenerationHandlerExecution,
    _resolve_regeneration_handler,
)
from src.generators.validation.evidence import extract_quotes
from src.generators.validation.regeneration_candidate import (
    validate_regeneration_candidate,
)
from src.generators.validation.semantic import semantic_payload
from src.orchestrators._report_analysis_orchestrator.regeneration_plan import (
    _build_regeneration_plan,
)
from src.utils.errors import AppError

_FIXTURE = Path(__file__).parent / "fixtures" / "a21_historical_semantic_residuals.json"


def _case(name: str) -> dict:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))["cases"][name]


def _context() -> RunContext:
    return RunContext(schema_version="1.0", run_id="a21", task_id="replay", span_id="1")


def _candidate_check(case: dict, candidate: dict):
    return validate_regeneration_candidate(
        current_artifacts=case["artifacts"],
        candidate_artifacts=candidate,
        evidence_packs=case["evidence_packs"],
        ctx=_context(),
    )


def test_stackadapt_abstained_quote_cannot_enter_semantic_request() -> None:
    case = _case("stackadapt")
    artifacts = case["artifacts"]
    issue = ValidationIssue(**case["blocking_issues"][0])
    assert (issue.rule_id, issue.affected_section) == ("semantic", "quotes:f1")
    assert artifacts["quotes_final"] == []
    assert artifacts["family_status"]["quotes"]["status"] == "abstained"
    assert all(audit["quotes_final_count"] == 0 for audit in case["candidate_audits"])
    assert all(
        audit["promotion_outcome"] == "rolled_back"
        for audit in case["candidate_audits"]
    )

    report = ReportPayload(
        tldr="",
        title="Retained report",
        insights=["", "", "", "", ""],
        quote=Quote(text="", author="Unknown"),
        figure=Figure(title="", evidence=""),
        commentary="",
        source="",
    )
    request = ValidationRequest(
        schema_version="1.0",
        report_id=case["report_id"],
        report=report,
        artifacts=artifacts,
        evidence_packs=case["evidence_packs"],
    )
    quotes = extract_quotes(request, artifacts["insights_final"])
    assert quotes == []
    assert semantic_payload(artifacts["insights_final"], quotes)["quotes"] == []
    assert _candidate_check(case, artifacts).passed
    assert _candidate_check(case, case["candidate_attempt_1"]).passed

    plan = _build_regeneration_plan(
        issues=[issue], artifacts=artifacts, broad_retry_available=True
    )
    assert [target.target_section for target in plan.targets] == ["quotes"]
    assert plan.targets[0].selected_evidence_ids == []


def test_doubleverify_duplicate_replay_preserves_sibling_and_grounding() -> None:
    case = _case("doubleverify")
    artifacts = case["artifacts"]
    candidate = case["candidate_attempt_1"]
    issue = ValidationIssue(**case["blocking_issues"][0])
    duplicate_id = "insight-q1-2026-emea-quality"
    sibling_id = "insight-q1-2026-apac-quality"

    original = evaluate_public_editorial_quality(
        report_id=case["report_id"], artifacts=artifacts
    )
    assert [item.rule_id for item in original.issues] == [
        "public_editorial_quality.duplicate_insight"
    ]
    assert validation_issues_from_public_editorial_quality(original) == [issue]
    assert _candidate_check(case, artifacts).passed
    assert _candidate_check(case, candidate).passed

    pair = {
        item["id"]: item
        for item in artifacts["insights_final"]
        if item["id"] in {duplicate_id, sibling_id}
    }
    candidate_pair = {
        item["id"]: item
        for item in candidate["insights_final"]
        if item["id"] in {duplicate_id, sibling_id}
    }
    assert pair[duplicate_id]["text"] == pair[sibling_id]["text"]
    assert candidate_pair == pair
    assert all(
        audit["promotion_outcome"] == "rolled_back"
        for audit in case["candidate_audits"]
    )
    assert all(
        any(item["rule_id"] == issue.rule_id for item in audit["blocking_issues"])
        for audit in case["candidate_audits"]
    )
    replayed = evaluate_public_editorial_quality(
        report_id=case["report_id"], artifacts=candidate
    )
    assert any(item.rule_id == issue.rule_id for item in replayed.issues)

    plan = _build_regeneration_plan(
        issues=[issue], artifacts=artifacts, broad_retry_available=True
    )
    assert [target.target_section for target in plan.targets] == ["insights_bundle"]
    assert plan.targets[0].issues[0].entity_id == f"insight:{duplicate_id}:text"
    assert plan.targets[0].selected_evidence_ids == ["global-quality-benchmarks"]
    assert plan.targets[0].quarantined_evidence_ids == []
    grounding = _build_grounding_package(
        target=plan.targets[0],
        prepared=SimpleNamespace(evidence_windows=[]),
        artifacts=artifacts,
        evidence_packs=case["evidence_packs"],
        doc_map=case["evidence_packs"]["doc_map"],
    )
    assert grounding["evidence_ids"] == ["global-quality-benchmarks"]
    assert grounding["quarantined_evidence_ids"] == []

    retained_candidate = next(
        item for item in artifacts["insights_candidates"] if item["id"] == duplicate_id
    )
    copied = deepcopy(artifacts)
    next(item for item in copied["insights_final"] if item["id"] == duplicate_id)[
        "text"
    ] = retained_candidate["text"]
    assert _candidate_check(case, copied).passed
    copied_quality = evaluate_public_editorial_quality(
        report_id=case["report_id"], artifacts=copied
    )
    assert [item.rule_id for item in copied_quality.issues] == [
        "public_editorial_quality.unsupported_numeric_claim"
    ]


def _doubleverify_removal_execution(case: dict):
    artifacts = case["artifacts"]
    issue = ValidationIssue(**case["blocking_issues"][0])
    plan = _build_regeneration_plan(
        issues=[issue],
        artifacts=artifacts,
        broad_retry_available=True,
    )
    target = replace(
        plan.targets[0], repair_action="REMOVE_CLAIM", repair_strategy="safe_removal"
    )
    state = _build_regeneration_state(
        safe_artifacts=artifacts,
        fallback_toc_bundle={},
        source_status={},
    )
    execution = _RegenerationHandlerExecution(
        handler=_resolve_regeneration_handler("insights_bundle"),
        runtime=SimpleNamespace(
            request=SimpleNamespace(report_id=case["report_id"]),
            safe_evidence=case["evidence_packs"],
            safe_doc_map=case["evidence_packs"]["doc_map"],
            openai_client=None,
            prompt_client=None,
        ),
        state=state,
        target=target,
        target_ctx=_context(),
        grounding_package={},
    )
    return execution


def test_doubleverify_safe_removal_abstains_without_retained_replacement() -> None:
    case = _case("doubleverify")
    execution = _doubleverify_removal_execution(case)

    with pytest.raises(AppError) as error:
        _handle_insights_bundle_regeneration(execution)

    assert error.value.code == "insight_safe_removal_no_replacement"
    assert execution.state.insights_final == case["artifacts"]["insights_final"]
    assert execution.state.prompt_namespaces == []


def test_doubleverify_safe_removal_resolves_failed_id_from_affected_section() -> None:
    case = _case("doubleverify")
    execution = _doubleverify_removal_execution(case)
    issue = replace(execution.target.issues[0], entity_id="")
    execution = replace(execution, target=replace(execution.target, issues=[issue]))

    with pytest.raises(AppError) as error:
        _handle_insights_bundle_regeneration(execution)

    assert error.value.code == "insight_safe_removal_no_replacement"


def test_doubleverify_safe_removal_uses_only_distinct_supported_retained_finding() -> (
    None
):
    case = _case("doubleverify")
    artifacts = case["artifacts"]
    failed_id = "insight-q1-2026-emea-quality"
    sibling_id = "insight-q1-2026-apac-quality"
    finding_text = "The source describes a separate measurement method for channels."
    retained_finding = {
        "id": "retained-independent-finding",
        "text": finding_text,
        "evidence": finding_text,
        "pages": [12],
    }
    case["evidence_packs"]["findings"] = {"findings": [retained_finding]}
    case["evidence_packs"]["doc_map"]["sections"].append(
        {
            "id": retained_finding["id"],
            "summary": retained_finding["evidence"],
            "pages": [12],
        }
    )
    execution = _doubleverify_removal_execution(case)
    unrelated = (
        deepcopy(execution.state.summary),
        deepcopy(execution.state.quotes_final),
        execution.state.expert_comment,
        execution.state.linkedin_post,
    )

    _handle_insights_bundle_regeneration(execution)

    final = execution.state.insights_final
    assert len(final) == 5
    assert failed_id not in {item["id"] for item in final}
    assert next(item for item in final if item["id"] == sibling_id) == next(
        item for item in artifacts["insights_final"] if item["id"] == sibling_id
    )
    assert {item["id"] for item in final} - {
        item["id"] for item in artifacts["insights_final"]
    } == {retained_finding["id"]}
    assert execution.state.prompt_namespaces == []
    assert execution.state.deterministic_repairs == ["safe_removal"]
    assert (
        execution.state.summary,
        execution.state.quotes_final,
        execution.state.expert_comment,
        execution.state.linkedin_post,
    ) == unrelated
    assert all(item["id"] != failed_id for item in execution.state.insights_candidates)
    assert not evaluate_public_editorial_quality(
        report_id=case["report_id"], artifacts={"insights_final": final}
    ).issues
    assert (
        case["evidence_packs"]["doc_map"]["sections"][2]["id"]
        == "global-quality-benchmarks"
    )
    candidate = deepcopy(artifacts)
    candidate["insights_final"] = final
    candidate["insights_candidates"] = execution.state.insights_candidates
    assert _candidate_check(case, candidate).passed


def test_doubleverify_safe_removal_rejects_unsupported_numeric_retained_candidate() -> (
    None
):
    case = _case("doubleverify")
    bad = deepcopy(case["artifacts"]["insights_candidates"][-1])
    bad["id"] = "retained-distinct-but-unsupported"
    case["artifacts"]["insights_candidates"].append(bad)
    execution = _doubleverify_removal_execution(case)

    with pytest.raises(AppError) as error:
        _handle_insights_bundle_regeneration(execution)

    assert error.value.code == "insight_safe_removal_no_replacement"
    assert execution.state.prompt_namespaces == []
