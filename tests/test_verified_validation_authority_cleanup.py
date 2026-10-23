from __future__ import annotations

from copy import deepcopy
import hashlib

import pytest

from src.contracts.protected_facts import PROTECTED_FACT_DIMENSIONS
from src.contracts.soft_copy_claim_provenance import (
    SoftCopyClaimProvenance,
    soft_copy_claim_provenance_to_payload,
)
from src.contracts.validation import ValidationRequest
from src.generators.claim_validation_generator import validate_retained_claims
from src.generators.public_editorial_quality_generator import (
    evaluate_public_editorial_quality,
)
from src.generators.validation.grounding import (
    _deterministic_claim_validation_issues,
    _validate_grounding_check_coverage,
    grounding_payload,
    run_grounding_check,
)
from src.generators.validation.preparation import prepare_validation_inputs
from src.generators.validation.registry import (
    build_validation_rule_registry,
    rules_for_validation_mode,
)
from src.generators.validation.verified_facts import verified_facts_mode
from src.utils.errors import AppError
from tests._test_validation_generator._shared import (
    FakeOpenAI,
    FakePromptClient,
    _ctx,
    _settings,
)
from tests.test_verified_facts_validation_authority import (
    SOURCE_IDENTITY,
    SOURCE_SHA,
    _fact,
    _packs,
    _report,
    _verified_artifacts,
)


def _grounding_check(
    item_id: str,
    text: str,
    outcome: str,
    *,
    classification: str = "factual_claim",
) -> dict:
    dimension_status = (
        "compatible"
        if outcome == "entailed" and classification == "factual_claim"
        else "unknown"
    )
    return {
        "item_id": item_id,
        "section": "insights:fact-1.text",
        "text": text,
        "classification": classification,
        "entailment_outcome": outcome,
        "proposition_status": (
            "compatible"
            if outcome == "entailed" and classification == "factual_claim"
            else "unknown"
        ),
        "protected_facts": {
            dimension: {
                "claim_value": None,
                "evidence_value": None,
                "status": dimension_status,
            }
            for dimension in PROTECTED_FACT_DIMENSIONS
        },
        "reason": f"semantic_{outcome}",
    }


@pytest.mark.parametrize(
    "mode",
    ["verified_facts", "verified_facts_inline", "verified_facts_grounding"],
)
def test_explicit_verified_modes_require_a_valid_snapshot(tmp_path, mode):
    request = ValidationRequest(
        schema_version="1.0",
        report_id="verified-authority-cleanup",
        report=_report(),
        artifacts={},
        evidence_packs={},
        source_id=SOURCE_IDENTITY,
        validation_mode=mode,
    )

    with pytest.raises(AppError, match="snapshot is missing"):
        prepare_validation_inputs(request, _settings(tmp_path), _ctx(), md5=SOURCE_SHA)


@pytest.mark.parametrize(
    "mode",
    ["verified_facts", "verified_facts_inline", "verified_facts_grounding"],
)
def test_explicit_verified_modes_reject_malformed_source_identity(tmp_path, mode):
    artifacts = _verified_artifacts()
    artifacts["verified_facts"][0]["source_identity"] = "not-a-hash-bound-source"
    request = ValidationRequest(
        schema_version="1.0",
        report_id="verified-authority-cleanup",
        report=_report(),
        artifacts=artifacts,
        evidence_packs=_packs(),
        source_id=SOURCE_IDENTITY,
        validation_mode=mode,
    )

    with pytest.raises(AppError, match="source identity"):
        prepare_validation_inputs(request, _settings(tmp_path), _ctx(), md5=SOURCE_SHA)


def test_normal_mode_remains_backward_compatible_without_verified_facts(tmp_path):
    request = ValidationRequest(
        schema_version="1.0",
        report_id="normal-authority-cleanup",
        report=_report(),
        artifacts={},
        evidence_packs={},
        source_id="legacy-source",
        validation_mode="full",
    )

    prepared = prepare_validation_inputs(request, _settings(tmp_path), _ctx(), md5="")

    assert prepared.verified_facts_mode is False
    assert prepared.authority_evidence_packs == {}


def test_visual_authority_cache_marker_is_a_trusted_verified_mode_signal():
    artifacts = {
        "_cache": {
            "visual_authority_canary": {
                "enabled": True,
                "digest": "d" * 64,
            }
        }
    }

    assert verified_facts_mode(artifacts) is True


def test_verified_preparation_uses_canonical_evidence_instead_of_legacy_packs(tmp_path):
    artifacts = _verified_artifacts()
    request = ValidationRequest(
        schema_version="1.0",
        report_id="verified-authority-cleanup",
        report=_report(),
        artifacts=artifacts,
        evidence_packs={
            "doc_map": {"summary": "Legacy extraction says 99%."},
            "findings_legacy": {
                "findings": [
                    {"id": "legacy-1", "evidence": "Legacy extraction says 99%."}
                ]
            },
        },
        source_id=SOURCE_IDENTITY,
        validation_mode="verified_facts_inline",
    )

    prepared = prepare_validation_inputs(request, _settings(tmp_path), _ctx(), md5="")

    evidence_text = "\n".join(prepared.evidence_texts)
    assert "42%" in evidence_text
    assert "99%" not in evidence_text
    assert (
        prepared.authority_evidence_packs["findings"]["findings"][0]["id"]
        == "verified-fact:fact-1"
    )


def test_verified_grounding_does_not_promote_legacy_summary_evidence():
    artifacts = _verified_artifacts()
    artifacts["insights_final"][0]["text"] = (
        "Adoption reached 99% among buyers in 2026."
    )
    artifacts["summary"] = {
        "claim_evidence_map": [
            {
                "id": "summary-claim-1",
                "claim": "Adoption reached 99% among buyers in 2026.",
                "evidence_id": "verified-fact:fact-1",
                "evidence": "Legacy extraction says 99%.",
            }
        ]
    }
    request = ValidationRequest(
        schema_version="1.0",
        report_id="verified-authority-cleanup",
        report=_report(),
        artifacts=artifacts,
        evidence_packs={
            **_packs(),
            "findings_legacy": {
                "findings": [
                    {"id": "legacy-1", "evidence": "Legacy extraction says 99%."}
                ]
            },
        },
        source_id=SOURCE_IDENTITY,
        validation_mode="verified_facts_grounding",
    )

    payload = grounding_payload(request, artifacts)

    assert payload["summary"]["claim_evidence_map"][0]["evidence"] != (
        "Legacy extraction says 99%."
    )
    public_items = payload["public_factual_items"]
    false_claim = next(
        item for item in public_items if item["section"] == "insights:fact-1.text"
    )
    assert "99%" in false_claim["text"]
    assert "99%" not in false_claim["retained_evidence"]


def test_grounding_cache_identity_separates_authority_modes_and_snapshots(tmp_path):
    captured = []

    class StopAfterCapture(Exception):
        pass

    def capture_reuse(request, _ctx):
        captured.append(request)
        raise StopAfterCapture

    def run_until_reuse(request):
        with pytest.raises(StopAfterCapture):
            run_grounding_check(
                request=request,
                settings=_settings(tmp_path),
                grounding_use_vector_store=False,
                evidence_texts=[],
                evidence_windows=[],
                prompt_client=FakePromptClient(),
                openai_client=FakeOpenAI(),
                ctx=_ctx(),
                source_id=SOURCE_IDENTITY,
                prompt_family_reuse_reader=capture_reuse,
            )

    legacy_artifacts = _verified_artifacts()
    legacy_artifacts["verified_facts"] = []
    run_until_reuse(
        ValidationRequest(
            schema_version="1.0",
            report_id="verified-authority-cleanup",
            report=_report(),
            artifacts=legacy_artifacts,
            evidence_packs=_packs(),
            source_id=SOURCE_IDENTITY,
            validation_mode="full",
        )
    )
    run_until_reuse(
        ValidationRequest(
            schema_version="1.0",
            report_id="verified-authority-cleanup",
            report=_report(),
            artifacts=_verified_artifacts(),
            evidence_packs=_packs(),
            source_id=SOURCE_IDENTITY,
            validation_mode="verified_facts",
        )
    )
    alternate_fact = _fact()
    alternate_fact["statement"] = "Adoption reached 43% among buyers in 2026."
    alternate_fact["metric"]["value"] = "43%"
    run_until_reuse(
        ValidationRequest(
            schema_version="1.0",
            report_id="verified-authority-cleanup",
            report=_report(),
            artifacts=_verified_artifacts(fact=alternate_fact),
            evidence_packs=_packs(alternate_fact),
            source_id=SOURCE_IDENTITY,
            validation_mode="verified_facts_inline",
        )
    )

    assert len(captured) == 3
    assert len({request.relevant_input_hash for request in captured}) == 3


def test_verified_rule_modes_drop_legacy_rules_but_normal_keeps_them():
    registry = build_validation_rule_registry()

    assert "numbers" in {
        rule.rule_id for rule in rules_for_validation_mode(registry, mode="full")
    }
    assert "semantic" in {
        rule.rule_id for rule in rules_for_validation_mode(registry, mode="full")
    }

    for mode in ("verified_facts", "verified_facts_inline"):
        rule_ids = {
            rule.rule_id for rule in rules_for_validation_mode(registry, mode=mode)
        }
        assert "numbers" not in rule_ids
        assert "semantic" not in rule_ids

    assert [
        rule.rule_id
        for rule in rules_for_validation_mode(registry, mode="verified_facts_grounding")
    ] == ["grounding"]


def test_verified_public_quality_defers_factual_prose_to_semantic_grounding():
    artifacts = _verified_artifacts()
    artifacts["insights_final"][0]["text"] = (
        "Adoption reached 99% among buyers in 2024."
    )
    artifacts["insights_final"][0]["evidence_status"] = "limited"
    artifacts["insights_final"][0]["so_what"] = (
        "This definitively guarantees growth for every buyer."
    )

    report = evaluate_public_editorial_quality(
        report_id="verified-authority-cleanup",
        artifacts=artifacts,
    )

    rule_ids = {issue.rule_id for issue in report.issues}
    assert "public_editorial_quality.unsupported_numeric_claim" not in rule_ids
    assert "public_editorial_quality.metric_label_relationship" not in rule_ids
    assert "public_editorial_quality.temporal_integrity" not in rule_ids
    assert "public_editorial_quality.unsupported_certainty" not in rule_ids


def test_verified_provenanced_soft_copy_also_defers_factual_prose():
    artifacts = _verified_artifacts()
    text = "Revenue reached 99% among buyers in 2024."
    artifacts["expert_comment"] = text
    artifacts["soft_copy_claim_provenance"] = soft_copy_claim_provenance_to_payload(
        [
            SoftCopyClaimProvenance(
                schema_version="1.0",
                artifact_family="expert_comment",
                claim_id="soft_copy:expert_comment:verified-cleanup",
                text_hash=hashlib.sha256(text.encode()).hexdigest(),
                classification="factual",
                evidence_ids=("verified-fact:fact-1",),
                source_spans=(),
                producing_prompt_identity={"namespace": "verified-cleanup"},
                generation_attempt=1,
                regeneration_attempt=0,
            )
        ]
    )

    report = evaluate_public_editorial_quality(
        report_id="verified-authority-cleanup",
        artifacts=artifacts,
    )

    assert "public_editorial_quality.metric_label_relationship" not in {
        issue.rule_id for issue in report.issues
    }


def test_verified_metric_binding_mismatch_remains_deterministic():
    artifacts = _verified_artifacts()
    artifacts["insights_final"][0]["metric"]["value"] = "99%"

    report = evaluate_public_editorial_quality(
        report_id="verified-authority-cleanup",
        artifacts=artifacts,
    )

    assert "public_editorial_quality.metric_binding_mismatch" in {
        issue.rule_id for issue in report.issues
    }


def test_verified_grounding_payload_includes_metric_spine_claims():
    fact = _fact()
    artifacts = _verified_artifacts(fact=fact)
    metric_spine_item = deepcopy(fact["metric"])
    metric_spine_item.update(
        {
            "metric_id": "fact-1",
            "evidence_id": "verified-fact:fact-1",
        }
    )
    artifacts["metric_spine"] = [metric_spine_item]
    request = ValidationRequest(
        schema_version="1.0",
        report_id="verified-authority-cleanup",
        report=_report(),
        artifacts=artifacts,
        evidence_packs=_packs(fact),
        source_id=SOURCE_IDENTITY,
        validation_mode="verified_facts",
    )

    payload = grounding_payload(request, artifacts)

    spine_items = [
        item
        for item in payload["public_factual_items"]
        if item.get("section", "").startswith("metric_spine:")
    ]
    assert len(spine_items) == 1
    assert "42%" in spine_items[0]["text"]
    assert spine_items[0]["evidence_ids"] == ["verified-fact:fact-1"]


def test_verified_grounding_payload_rejects_public_items_without_fact_bindings():
    fact = _fact()
    artifacts = _verified_artifacts(fact=fact)
    artifacts["metric_spine"] = [
        {
            "label": "Adoption",
            "value": "42%",
            "unit": "%",
            "evidence_id": "",
        }
    ]
    request = ValidationRequest(
        schema_version="1.0",
        report_id="verified-authority-cleanup",
        report=_report(),
        artifacts=artifacts,
        evidence_packs=_packs(fact),
        source_id=SOURCE_IDENTITY,
        validation_mode="verified_facts",
    )

    with pytest.raises(AppError, match="authoritative evidence bindings"):
        grounding_payload(request, artifacts)


def test_verified_grounding_rejects_empty_check_explanations():
    with pytest.raises(AppError, match="substantive reason"):
        _validate_grounding_check_coverage(
            {
                "checks": [
                    {
                        "item_id": "public-item",
                        "text": "A supported claim.",
                        "classification": "factual_claim",
                        "entailment_outcome": "entailed",
                        "proposition_status": "compatible",
                        "protected_facts": {
                            dimension: {
                                "claim_value": None,
                                "evidence_value": None,
                                "status": "compatible",
                            }
                            for dimension in PROTECTED_FACT_DIMENSIONS
                        },
                        "reason": "",
                    }
                ],
                "unsupported": [],
            },
            [],
            {},
            expected_public_items=[
                {
                    "item_id": "public-item",
                    "section": "insights:fact-1.text",
                    "text": "A supported claim.",
                }
            ],
            require_public_coverage=True,
        )


def test_verified_deterministic_claim_filter_keeps_structural_failures_only():
    claim = "The report calls this “an unsupported quote”."
    package = validate_retained_claims(
        {
            "summary": {
                "claim_evidence_map": [
                    {"id": "claim-1", "claim": claim, "evidence_id": "f1"}
                ]
            }
        },
        {
            "findings": {
                "findings": [{"id": "f1", "evidence": "A different source sentence."}]
            }
        },
    )

    normal_issues = _deterministic_claim_validation_issues(package)
    verified_issues = _deterministic_claim_validation_issues(
        package, verified_mode=True
    )

    assert any(issue.rule_id == "retained_claim.quote_match" for issue in normal_issues)
    assert not any(
        issue.rule_id == "retained_claim.quote_match" for issue in verified_issues
    )


def test_verified_deterministic_claim_filter_keeps_missing_reference_failures():
    package = validate_retained_claims(
        {
            "summary": {
                "claim_evidence_map": [
                    {
                        "id": "claim-1",
                        "claim": "A retained source claim.",
                        "evidence_id": "missing-fact",
                    }
                ]
            }
        },
        {"findings": {"findings": []}},
    )

    issues = _deterministic_claim_validation_issues(package, verified_mode=True)

    assert [issue.rule_id for issue in issues] == [
        "retained_claim.evidence_reference_completeness"
    ]


def test_grounding_rejects_unknown_response_item_ids():
    with pytest.raises(AppError) as exc_info:
        _validate_grounding_check_coverage(
            {
                "public_factual_items": [
                    {
                        "item_id": "known-public-item",
                        "section": "insights:fact-1.text",
                        "text": "A supported claim.",
                    }
                ],
                "checks": [
                    {
                        "item_id": "unknown-public-item",
                        "text": "An unrequested claim.",
                        "classification": "factual_claim",
                    }
                ],
            },
            [],
            {},
            require_public_coverage=True,
        )

    assert exc_info.value.code == "grounding_claim_check_coverage_invalid"


def test_verified_grounding_requires_verdicts_for_every_public_item():
    with pytest.raises(AppError) as exc_info:
        _validate_grounding_check_coverage(
            {"checks": [], "unsupported": []},
            [],
            {},
            expected_public_items=[
                {
                    "item_id": "insight:fact-1:so_what",
                    "section": "insights:fact-1.so_what",
                    "text": "The finding changes the buying decision.",
                }
            ],
            require_public_coverage=True,
        )

    assert exc_info.value.code == "grounding_claim_check_coverage_invalid"


def test_verified_grounding_rejects_fabricated_number_through_llm_grounding(
    tmp_path,
):
    artifacts = _verified_artifacts()
    artifacts["insights_final"][0]["text"] = (
        "Adoption reached 99% among buyers in 2026."
    )
    request = ValidationRequest(
        schema_version="1.0",
        report_id="verified-authority-cleanup",
        report=_report(),
        artifacts=artifacts,
        evidence_packs=_packs(),
        source_id=SOURCE_IDENTITY,
        validation_mode="verified_facts",
    )
    payload = grounding_payload(request, artifacts)
    checks = []
    unsupported = []
    for entry in payload["retained_claims_to_ground"] + payload["public_factual_items"]:
        outcome = (
            "not_established" if "Adoption reached 99%" in entry["text"] else "entailed"
        )
        classification = entry.get("declared_classification") or "factual_claim"
        checks.append(
            _grounding_check(
                entry["item_id"],
                entry["text"],
                outcome,
                classification=classification,
            )
        )
        if outcome != "entailed":
            unsupported.append(
                {
                    "item_id": entry["item_id"],
                    "section": entry["section"],
                    "text": entry["text"],
                    "classification": classification,
                    "entailment_outcome": outcome,
                    "violation_type": "not_established",
                    "reason": "The verified fact does not establish the rewritten number.",
                }
            )

    issues = run_grounding_check(
        request=request,
        settings=_settings(tmp_path),
        grounding_use_vector_store=False,
        evidence_texts=[],
        evidence_windows=[],
        prompt_client=FakePromptClient(),
        openai_client=FakeOpenAI(
            grounding_payload={"unsupported": unsupported, "checks": checks}
        ),
        ctx=_ctx(),
        source_id=SOURCE_IDENTITY,
    )

    assert any(
        issue.rule_id == "grounding" and "not_established" in issue.message
        for issue in issues
    )
