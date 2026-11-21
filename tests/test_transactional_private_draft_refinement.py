"""Regression for editorial-only private repair drafts using a retained report."""

import json
import os
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

import scripts.quality.replay_validation_repair_benchmark as replay
from src.contracts.openai import OpenAIResponseResult
from src.contracts.report_analysis import AnalysisStorePackRequest
from src.contracts.validation import ValidationIssue, ValidationReport
from src.generators.report_generation_dependencies import ReportAnalysisDependencies
from src.orchestrators._report_analysis_orchestrator.validation import (
    _run_validation_regeneration_loop,
)
from src.utils.errors import AppError
from src.utils.verified_facts import build_verified_authority_context
from tests._test_report_analysis_generator._shared import (
    _runtime,
    _SemanticPassOpenAIClient,
)


def _run_draft_scenario(tmp_path, scenario):
    if os.environ.get("MARKETLENSE_ACTIVATE_DRAFT_REPLAY") != "1":
        pytest.skip(
            "Set MARKETLENSE_ACTIVATE_DRAFT_REPLAY=1 to use retained Activate inputs"
        )
    root = Path(__file__).resolve().parent.parent
    manifest_path = root / "tmp/activate-repair-frozen-20261120/manifest.json"
    if not manifest_path.is_file():
        pytest.skip("Retained Activate benchmark manifest is unavailable")
    manifest, _ = replay._benchmark_manifest(manifest_path)
    if any(
        not (root / entry["path"]).is_file()
        for entry in manifest["cases"][0]["input_files"].values()
    ):
        pytest.skip("Retained Activate benchmark inputs are unavailable")
    ctx = replay._root_context(
        run_id="test",
        validation_run_id="test",
        cohort_id="test",
        configuration_hash="test-config",
        policy_hash="test-policy",
        implementation_sha="test",
    )
    case = replay._preflight_benchmark_cases(manifest["cases"], root, ctx)[0]
    if scenario in {"sibling", "sibling_missing", "sibling_acceptance"}:
        checkpoint_path = Path(
            "C:/ml-activate-e2e-dcd480bc-results/frozen-reliability-nem1t7kf/"
            "members/cohort-cbb6e7df67412186b8bc/ias-first-attempt-qfvmlp5m/"
            "output/.checkpoints/report_generation/cohort-cbb6e7df67412186b8bc/"
            "analysis_complete.json"
        )
        if not checkpoint_path.is_file():
            pytest.skip("Retained Activate sibling-field checkpoint is unavailable")
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        analysis = checkpoint["payload"]["analysis"]
        case["artifacts"] = analysis["artifacts_payload"]
        case["base_payload"] = replay._report_payload_from_dict(analysis["payload"])
        case["verified_authority_context"] = build_verified_authority_context(
            case["artifacts"],
            expected_source_identity=analysis["verified_authority_context"][
                "source_identity"
            ],
        )
    original = case["artifacts"]
    snapshot = deepcopy(original)
    authority = case["verified_authority_context"]
    runtime = _runtime(tmp_path)
    runtime = replace(
        runtime,
        settings=replace(
            runtime.settings,
            validation_regeneration_max_attempts=4
            if scenario == "repeated_draft"
            else 2,
        ),
        ctx=case["case_ctx"],
    )
    issue = ValidationIssue(
        schema_version="1.0",
        severity="error",
        rule_id="public_editorial_quality.semantic_generic_copy",
        message="The interpretation needs more specific analysis.",
        affected_section="summary.claim_evidence_map:2.claim",
        repair_target="summary",
        entity_id="summary:summary:claim_evidence_map:2:claim",
        evidence_ids=(
            ["verified-fact:s08-f01", "verified-fact:global-revenue-outlook"]
            if scenario == "repeated_draft"
            else ["verified-fact:s08-f01"]
        ),
        classification="analyst_interpretation",
        violation_type="editorial_quality",
    )
    if scenario in {"sibling", "sibling_missing", "sibling_acceptance"}:
        issue = replace(
            issue,
            affected_section="insights:video-superuser-spend-share.so_what",
            repair_target="insights_bundle",
            entity_id="insight:video-superuser-spend-share:so_what",
            evidence_ids=["verified-fact:video-superuser-spend-share"],
        )
    baseline = ValidationReport(
        schema_version="1.1", status="fail", severity="error", issues=[issue]
    )
    dependencies = ReportAnalysisDependencies.default()
    stored = dependencies.analysis_store_pack(
        AnalysisStorePackRequest(
            schema_version="1.0",
            output_dir=runtime.settings.output_dir,
            report_id=runtime.file.file_id,
            pack_name="artifacts",
            payload=original,
            report_slug=runtime.report_name,
        ),
        case["case_ctx"],
    )
    canonical_path = Path(stored.output_path)
    original_bytes = canonical_path.read_bytes()

    class Provider(_SemanticPassOpenAIClient):
        def __init__(self):
            self.repair_prompts = []
            self.editorial_prompts = []
            self.editorial_attempts = []

        def openai_chat_json(self, request, context):
            if (
                scenario in {"sibling", "sibling_missing", "sibling_acceptance"}
                and request.artifact_family == "insights_final"
            ):
                assert canonical_path.read_bytes() == original_bytes
                self.repair_prompts.append(request.user_prompt)
                field = "so_what" if context.repair_attempt == 1 else "now_what"
                path = f"insights_final[item=video-superuser-spend-share].{field}"
                value = (
                    "Heavy users concentrate activity and expenditure "
                    "across distinct measures."
                    if context.repair_attempt == 1
                    else "Plan separate viewing and spending analyses "
                    "for the heavy-user cohort."
                )
                payload = {
                    "repair_decision": {
                        "schema_version": "1.0",
                        "repair_action": "REGENERATE_ITEM",
                        "repair_strategy": "current_evidence",
                        "evidence_ids_used": [
                            "verified-fact:video-superuser-spend-share"
                        ],
                        "changed_paths": [path],
                        "minimal_patch": [
                            {"op": "replace", "path": path, "value": value}
                        ],
                    }
                }
                return OpenAIResponseResult(
                    schema_version="1.0",
                    text=json.dumps(payload),
                    parsed_json=payload,
                    request_id="local",
                )
            if request.artifact_family == "summary":
                assert canonical_path.read_bytes() == original_bytes
                self.repair_prompts.append(request.user_prompt)
                value = (
                    "Among U.S. adults watching sports weekly, sports fans "
                    "account for 90% of viewers."
                    if len(self.repair_prompts) == 1
                    else "Among U.S. adults watching sports weekly, "
                    "90% are sports fans, "
                    "underscoring the value of targeted programming."
                )
                if scenario == "repeated_draft" and context.repair_attempt >= 3:
                    value = (
                        "Among weekly U.S. adult sports viewers, sports fans "
                        "represent 90% of the audience."
                    )
                decision = {
                    "schema_version": "1.0",
                    "repair_action": "REGENERATE_ITEM",
                    "repair_strategy": "current_evidence",
                    "evidence_ids_used": ["verified-fact:s08-f01"],
                    "changed_paths": ["summary.claim_evidence_map[1].claim"],
                    "minimal_patch": [
                        {
                            "op": "replace",
                            "path": "summary.claim_evidence_map[1].claim",
                            "value": value,
                        }
                    ],
                }
                if (
                    request.structured_output_schema_identity
                    == "regeneration_claim_repair_proposal_v1"
                ):
                    payload = {
                        "claim_repair_proposal": {
                            "schema_version": "1.0",
                            "action": "replace",
                            "replacement_text": value,
                            "evidence_ids_used": ["verified-fact:s08-f01"],
                        }
                    }
                else:
                    payload = {"repair_decision": decision}
                return OpenAIResponseResult(
                    schema_version="1.0",
                    text=json.dumps(payload),
                    parsed_json=payload,
                    request_id="local",
                )
            response = super().openai_chat_json(request, context)
            if request.artifact_family == "public_editorial_quality":
                self.editorial_prompts.append(request.user_prompt)
                self.editorial_attempts.append(context.repair_attempt)
                payload = deepcopy(response.parsed_json)
                marker = request.user_prompt.find('"public_items"')
                start = request.user_prompt.rfind("{", 0, marker)
                review = json.JSONDecoder().raw_decode(request.user_prompt[start:])[0]
                items = review["public_items"]
                obligations = review["report_scope"][
                    "original_editorial_plan_coverage"
                ]["original_essential_obligations"]
                assessments = []
                for obligation in obligations:
                    evidence = obligation["evidence_ids"]
                    supporting = [
                        item
                        for item in items
                        if item["item_id"].startswith(("insight:", "insights:"))
                        and set(item.get("evidence_ids", [])) & set(evidence)
                    ]
                    bound = (
                        set().union(
                            *(set(item.get("evidence_ids", [])) for item in supporting)
                        )
                        if supporting
                        else set()
                    )
                    assert set(evidence) <= bound, (
                        obligation["theme"],
                        len(evidence),
                        len(bound),
                    )
                    assessments.append(
                        {
                            "theme": obligation["theme"],
                            "status": "covered",
                            "explanation": (
                                "The cited insights represent this original "
                                "editorial obligation."
                            ),
                            "evidence_ids": evidence,
                            "supporting_insight_ids": [
                                item["item_id"] for item in supporting
                            ],
                        }
                    )
                payload["original_essential_obligation_assessments"] = assessments
                if context.repair_attempt == 1 or (
                    context.repair_attempt in {2, 3}
                    and scenario in {"exhaustion", "repeated_draft"}
                ):
                    verdict = (
                        next(
                            v
                            for v in payload["verdicts"]
                            if "video-superuser-spend-share" in v["item_id"]
                            and "now_what" in v["item_id"]
                        )
                        if scenario
                        in {"sibling", "sibling_missing", "sibling_acceptance"}
                        else next(
                            v
                            for v in payload["verdicts"]
                            if "claim_evidence_map:2" in v["item_id"]
                        )
                        if context.repair_attempt == 1 or scenario == "repeated_draft"
                        else next(
                            v
                            for v in payload["verdicts"]
                            if v["item_id"]
                            in {
                                item["item_id"]
                                for item in items
                                if item.get("repair_target") == "summary"
                            }
                        )
                    )
                    verdict.update(
                        status="fail",
                        severity="error",
                        classification=(
                            "factual_claim"
                            if scenario in {"factual", "factual_mislabeled"}
                            else "analyst_interpretation"
                        ),
                        rule_id=(
                            "public_editorial_quality.semantic_unsupported_claim"
                            if scenario in {"factual", "factual_mislabeled"}
                            else "public_editorial_quality.semantic_unsupported_number"
                            if scenario == "unsupported_number"
                            else "public_editorial_quality.semantic_repetition"
                            if scenario == "repeated_draft"
                            else "public_editorial_quality.semantic_analytical_depth"
                            if scenario == "analytical_depth"
                            else "public_editorial_quality.semantic_decision_value"
                            if scenario == "typed_editorial"
                            else "public_editorial_quality.semantic_generic_copy"
                        ),
                        hard_fail_class=(
                            "source_integrity"
                            if scenario == "factual"
                            else "editorial_quality"
                            if scenario
                            in {
                                "factual_mislabeled",
                                "unsupported_number",
                                "legacy_editorial",
                            }
                            else "editorial_only"
                        ),
                        reason=(
                            "The source does not establish this factual claim."
                            if scenario in {"factual", "factual_mislabeled"}
                            else "The implication remains generic."
                        ),
                        repair_target="insights_bundle"
                        if scenario
                        in {"sibling", "sibling_missing", "sibling_acceptance"}
                        else "summary",
                    )
                    if (
                        scenario in {"sibling", "sibling_acceptance"}
                        and context.repair_attempt == 1
                    ):
                        selected_item = next(
                            item
                            for item in items
                            if item["item_id"] == verdict["item_id"]
                        )
                        assert selected_item["evidence_ids"]
                        verdict.update(
                            status="pass",
                            severity="info",
                            rule_id="",
                            hard_fail_class="",
                            repair_target="",
                            reason="The item is individually source supported.",
                        )
                        report = payload["report_verdict"]
                        report.update(
                            status="fail",
                            severity="error",
                            rule_id=(
                                "public_editorial_quality.semantic_analytical_depth"
                                if scenario == "sibling_acceptance"
                                else "public_editorial_quality.semantic_distinctness"
                            ),
                            hard_fail_class=(
                                "report_editorial_acceptance"
                                if scenario == "sibling_acceptance"
                                else "editorial_only"
                            ),
                            reason=(
                                "The implication and action repeat the same analysis."
                            ),
                            evidence_ids=selected_item["evidence_ids"],
                            repair_target="",
                            affected_item_id="",
                            repair_items=[
                                {
                                    "item_id": verdict["item_id"],
                                    "reason": (
                                        "Give the action a distinct analytical role."
                                    ),
                                    "evidence_ids": selected_item["evidence_ids"],
                                    "repair_target": "insights_bundle",
                                }
                            ],
                        )
                        dimension = (
                            "analytical_depth"
                            if scenario == "sibling_acceptance"
                            else "distinctness"
                        )
                        report["dimensions"][dimension] = {
                            "status": "fail",
                            "reason": "The insight pair repeats its analysis.",
                        }
                    if scenario == "analytical_depth" and context.repair_attempt == 1:
                        report = payload["report_verdict"]
                        report.update(
                            status="fail",
                            severity="error",
                            rule_id="public_editorial_quality.semantic_analytical_depth",
                            hard_fail_class="editorial_only",
                            reason="The report lacks sufficient specific analysis.",
                            repair_target="summary",
                            affected_item_id=verdict["item_id"],
                            evidence_ids=verdict["evidence_ids"],
                        )
                        report["dimensions"]["analytical_depth"] = {
                            "status": "fail",
                            "reason": "The analysis needs a more specific implication.",
                        }
                return replace(response, parsed_json=payload, text=json.dumps(payload))
            return response

    client = Provider()
    try:
        result = _run_validation_regeneration_loop(
            runtime=runtime,
            mode_ctx=case["case_ctx"],
            base_payload=case["base_payload"],
            current_artifacts=original,
            current_validation_report=baseline,
            evidence_packs=authority.evidence_packs,
            source_status=original["source_status"],
            category_labels=case["base_payload"].categories,
            vector_store_id=None,
            dependencies=dependencies,
            validation_openai_client=client,
            regeneration_openai_client=client,
            source_identity=authority.source_identity,
            verified_source_identity=authority.source_identity,
            verified_fact_digest=authority.verified_fact_digest,
            verified_authority_context=authority,
        )
    except AppError as exc:
        pytest.fail(f"Workflow failed before draft assertion: {exc.code} {exc.context}")
    promoted, validation, attempts, _, _, _ = result
    assert original == snapshot
    audits = [
        json.loads(Path(a.candidate_audit_path).read_text(encoding="utf-8"))
        for a in attempts
    ]
    if scenario in {"typed_editorial", "legacy_editorial"}:
        first_validation = json.loads(
            Path(attempts[0].candidate_audit_path)
            .with_name("validation_regen_candidate_1.json")
            .read_text(encoding="utf-8")
        )
        expected_rule = (
            "public_editorial_quality.semantic_decision_value"
            if scenario == "typed_editorial"
            else "public_editorial_quality.semantic_generic_copy"
        )
        failure = next(
            issue
            for issue in first_validation["issues"]
            if issue["rule_id"] == expected_rule and issue["severity"] == "error"
        )
        assert failure["violation_type"] == (
            "editorial_only" if scenario == "typed_editorial" else "editorial_quality"
        )
        assert failure["classification"] == "analyst_interpretation"
        if scenario == "legacy_editorial":
            assert audits[0]["promotion_outcome"] == "rolled_back", (
                "Legacy editorial_quality incorrectly authorized a private draft"
            )
            if len(audits) > 1:
                assert audits[1]["before_sha256"] == audits[0]["before_sha256"]
                assert all(
                    "sports fans account for 90%" not in prompt
                    for prompt in client.repair_prompts[1:]
                )
            return
        assert audits[0]["promotion_outcome"] == "candidate", (
            "Explicit editorial_only failure did not retain the private draft"
        )
        assert len(audits) == 2
        assert audits[1]["before_sha256"] == audits[0]["after_sha256"]
        assert "sports fans account for 90%" in client.repair_prompts[1]
        assert validation.status == "pass"
        assert attempts[-1].promotion_outcome == "promoted"
        assert (
            "targeted programming"
            in promoted["summary"]["claim_evidence_map"][1]["claim"]
        )
        return
    if scenario in {"sibling", "sibling_missing", "sibling_acceptance"}:
        assert audits[0]["allowed_paths"] == [
            "insights_final[item=video-superuser-spend-share].so_what"
        ]
        assert client.editorial_attempts[:1] == [1]
        sibling_validation = json.loads(
            Path(attempts[0].candidate_audit_path)
            .with_name("validation_regen_candidate_1.json")
            .read_text(encoding="utf-8")
        )
        errors = [
            item for item in sibling_validation["issues"] if item["severity"] == "error"
        ]
        if scenario == "sibling_acceptance":
            assert {item["rule_id"] for item in errors} == {
                "public_editorial_quality.semantic_collective_editorial_repair",
                "public_editorial_quality.semantic_analytical_depth",
            }
            assert all(item.get("classification") != "factual_claim" for item in errors)
            assert any("analytical_depth" in item["message"] for item in errors)
            assert audits[0]["promotion_outcome"] == "rolled_back"
            if len(audits) > 1:
                assert audits[1]["before_sha256"] == audits[0]["before_sha256"]
            return
        assert audits[0]["promotion_outcome"] == "candidate"
        if scenario == "sibling_missing":
            assert len(errors) == 1
            assert (
                errors[0]["rule_id"] == "public_editorial_quality.semantic_generic_copy"
            )
            assert len(audits) == 1, "Unnominated sibling field was refined"
            assert canonical_path.read_bytes() == original_bytes
            return
        assert any(
            error["rule_id"]
            == "public_editorial_quality.semantic_collective_editorial_repair"
            and "video-superuser-spend-share.now_what" in error["affected_section"]
            for error in errors
        )
        assert len(audits) >= 2, "Newly nominated sibling field was not refined"
        assert audits[1]["before_sha256"] == audits[0]["after_sha256"]
        assert (
            "insights_final[item=video-superuser-spend-share].now_what"
            in audits[1]["allowed_paths"]
        )
        assert validation.status == "pass"
        assert attempts[-1].promotion_outcome == "promoted"
        return
    assert client.editorial_attempts[:2] == [1, 2], [
        item["message"]
        for item in json.loads(
            Path(attempts[0].candidate_audit_path)
            .with_name("validation_regen_candidate_1.json")
            .read_text(encoding="utf-8")
        )["issues"]
        if item["severity"] == "error"
    ]
    first_validation = json.loads(
        Path(attempts[0].candidate_audit_path)
        .with_name("validation_regen_candidate_1.json")
        .read_text(encoding="utf-8")
    )
    first_errors = {
        item["rule_id"]
        for item in first_validation["issues"]
        if item["severity"] == "error"
    }
    if scenario in {"factual", "factual_mislabeled", "unsupported_number"}:
        assert first_errors == {
            "public_editorial_quality.semantic_unsupported_number"
            if scenario == "unsupported_number"
            else "public_editorial_quality.semantic_unsupported_claim"
        }
        if scenario == "factual_mislabeled":
            failure = next(
                item
                for item in first_validation["issues"]
                if item["severity"] == "error"
            )
            assert failure["classification"] == "factual_claim"
            assert failure["violation_type"] == "editorial_quality"
        assert audits[0]["promotion_outcome"] == "rolled_back"
        assert audits[1]["before_sha256"] == audits[0]["before_sha256"]
        assert all(
            "sports fans account for 90%" not in p for p in client.repair_prompts[1:]
        )
        return
    assert first_errors == {
        "public_editorial_quality.semantic_repetition"
        if scenario == "repeated_draft"
        else "public_editorial_quality.semantic_analytical_depth"
        if scenario == "analytical_depth"
        else "public_editorial_quality.semantic_generic_copy"
    }
    if scenario == "analytical_depth":
        depth_errors = [
            item
            for item in first_validation["issues"]
            if item["severity"] == "error"
            and item["rule_id"] == "public_editorial_quality.semantic_analytical_depth"
        ]
        assert len(depth_errors) >= 2
        assert any("analytical_depth" in item["message"] for item in depth_errors)
    assert audits[0]["repair_action"] == "REGENERATE_ITEM"
    if scenario == "repeated_draft":
        assert audits[0]["promotion_outcome"] == "candidate"
        assert audits[1]["before_sha256"] == audits[0]["after_sha256"]
        second_validation = json.loads(
            Path(attempts[1].candidate_audit_path)
            .with_name("validation_regen_candidate_2.json")
            .read_text(encoding="utf-8")
        )
        assert any(
            item["severity"] == "error"
            and item["rule_id"] == "public_editorial_quality.semantic_repetition"
            for item in second_validation["issues"]
        )
        assert audits[1]["promotion_outcome"] == "rolled_back"
        assert len(audits) >= 3, "The third candidate was not evaluated"
        assert client.editorial_attempts[:3] == [1, 2, 3]
        assert audits[2]["before_sha256"] == audits[0]["before_sha256"]
        assert audits[2]["repair_action"] == "REGENERATE_ITEM"
        third_validation = json.loads(
            Path(attempts[2].candidate_audit_path)
            .with_name("validation_regen_candidate_3.json")
            .read_text(encoding="utf-8")
        )
        assert {
            item["rule_id"]
            for item in third_validation["issues"]
            if item["severity"] == "error"
        } == {"public_editorial_quality.semantic_repetition"}
        assert audits[2]["promotion_outcome"] == "rolled_back"
        return
    if scenario == "exhaustion":
        assert audits[0]["promotion_outcome"] == "candidate"
        assert audits[1]["before_sha256"] == audits[0]["after_sha256"]
        assert len(client.repair_prompts) == 2
        assert "sports fans account for 90%" in client.repair_prompts[1]
        second_validation = json.loads(
            Path(attempts[1].candidate_audit_path)
            .with_name("validation_regen_candidate_2.json")
            .read_text(encoding="utf-8")
        )
        assert any(item["severity"] == "error" for item in second_validation["issues"])
        assert validation.status == "fail"
        assert attempts[-1].promotion_outcome == "rolled_back"
        assert promoted == snapshot
        assert canonical_path.read_bytes() == original_bytes
        return
    assert len(client.repair_prompts) == 2, (
        "Editorial-only rejected candidate was not refined"
    )
    assert "sports fans account for 90%" in client.repair_prompts[1]
    assert validation.status == "pass"
    assert attempts[-1].promotion_outcome == "promoted"
    assert (
        "targeted programming" in promoted["summary"]["claim_evidence_map"][1]["claim"]
    )


def test_editorial_failure_can_be_refined_as_private_draft(tmp_path):
    _run_draft_scenario(tmp_path, "promotion")


def test_factual_failure_is_not_retained_as_draft(tmp_path):
    _run_draft_scenario(tmp_path, "factual")


def test_factual_failure_mislabeled_editorial_is_not_retained_as_draft(tmp_path):
    _run_draft_scenario(tmp_path, "factual_mislabeled")


def test_unsupported_number_mislabeled_editorial_is_not_retained_as_draft(tmp_path):
    _run_draft_scenario(tmp_path, "unsupported_number")


def test_second_failure_preserves_original_canonical_artifacts(tmp_path):
    _run_draft_scenario(tmp_path, "exhaustion")


def test_failed_draft_refinement_does_not_become_a_second_draft(tmp_path):
    _run_draft_scenario(tmp_path, "repeated_draft")


def test_private_draft_refines_newly_nominated_sibling_insight(tmp_path):
    _run_draft_scenario(tmp_path, "sibling")


def test_report_acceptance_nomination_allows_sibling_refinement(tmp_path):
    _run_draft_scenario(tmp_path, "sibling_acceptance")


def test_private_draft_does_not_refine_sibling_without_collective_nomination(tmp_path):
    _run_draft_scenario(tmp_path, "sibling_missing")


def test_private_draft_refines_analytical_depth_failure(tmp_path):
    _run_draft_scenario(tmp_path, "analytical_depth")


def test_private_draft_accepts_explicit_editorial_only_with_arbitrary_rule(tmp_path):
    _run_draft_scenario(tmp_path, "typed_editorial")


def test_legacy_editorial_quality_cannot_authorize_private_draft(tmp_path):
    _run_draft_scenario(tmp_path, "legacy_editorial")
