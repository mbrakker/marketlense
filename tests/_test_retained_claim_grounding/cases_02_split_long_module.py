# ruff: noqa: F401,F403,F405
from __future__ import annotations
from pathlib import Path as _SplitPath

__file__ = str(
    _SplitPath(__file__).resolve().parent.parent / "test_retained_claim_grounding.py"
)

from ._split_support_test_retained_claim_grounding import *  # noqa: F401,F403


def test_large_grounding_inventory_is_split_without_losing_claim_coverage(
    tmp_path,
) -> None:
    from src.generators.claim_validation_generator import (
        retained_claim_semantic_inputs,
        validate_retained_claims,
    )

    claim_texts = [
        f"The report describes merchant payment operations from a distinctive {word} angle."
        for word in (
            "alpha",
            "bravo",
            "charlie",
            "delta",
            "echo",
            "foxtrot",
            "golf",
            "hotel",
            "india",
        )
    ]
    evidence_packs = {
        "findings": {
            "findings": [
                {
                    "id": f"evidence-{index}",
                    "text": "A retained passage discusses a separate operational subject.",
                }
                for index in range(len(claim_texts))
            ]
        }
    }
    artifacts = {
        "summary": {
            "claim_evidence_map": [
                {
                    "id": f"claim-{index}",
                    "claim": text,
                    "evidence_id": f"evidence-{index}",
                }
                for index, text in enumerate(claim_texts)
            ]
        }
    }
    request = replace(
        _retained_request(),
        source_id="",
        artifacts=artifacts,
        evidence_packs=evidence_packs,
    )
    package = validate_retained_claims(artifacts, evidence_packs)
    semantic_inputs = retained_claim_semantic_inputs(package, evidence_packs)
    assert len(semantic_inputs) == 9

    payload = grounding_payload(
        request,
        artifacts,
        retained_claim_inputs=semantic_inputs,
    )
    claim_entries = payload["retained_claims_to_ground"]
    expected_ids = {item["item_id"] for item in claim_entries}
    groups = (
        claim_entries[:4],
        claim_entries[4:8],
        claim_entries[8:],
    )
    responses = [
        {
            "unsupported": [],
            "checks": [
                _grounding_check(item["item_id"], item["text"], "entailed")
                for item in group
            ],
        }
        for group in groups
    ]
    model_client = FakeOpenAI(*responses)
    captured_packages: list[ClaimValidationPackage] = []

    issues = run_grounding_check(
        request=request,
        settings=_settings(tmp_path),
        grounding_use_vector_store=False,
        evidence_texts=[],
        evidence_windows=[],
        prompt_client=FakePromptClient(),
        openai_client=model_client,
        ctx=_ctx(),
        retained_claim_package=package,
        retained_claim_inputs=semantic_inputs,
        retained_claim_validation_sink=captured_packages.append,
    )

    grounding_calls = [
        call for call in model_client.requests if call[2].endswith(":grounding")
    ]
    assert issues == []
    assert len(grounding_calls) == 3
    assert len(captured_packages) == 1
    assert {result.candidate.claim_id for result in captured_packages[0].results} == (
        expected_ids
    )
    assert {result.status for result in captured_packages[0].results} == {"supported"}


def test_stale_report_grounding_is_not_reused_for_current_retained_claim(
    tmp_path,
) -> None:
    request = _retained_request()
    item_id = "summary_claim:claim-1"
    text = request.artifacts["summary"]["claim_evidence_map"][0]["claim"]
    new_output = {
        "unsupported": [],
        "checks": [_grounding_check(item_id, text, "not_established")],
    }
    reuse_requests = []
    model_client = FakeOpenAI(grounding_payload=new_output)
    captured_packages: list[ClaimValidationPackage] = []

    def stale_reader(reuse_request, _ctx):
        reuse_requests.append(reuse_request)
        return SimpleNamespace(
            reusable=False,
            reason="input_identity_mismatch",
            output_payload={
                "unsupported": [],
                "checks": [_grounding_check(item_id, text, "entailed")],
            },
        )

    issues = run_grounding_check(
        request=request,
        settings=_settings(tmp_path),
        grounding_use_vector_store=False,
        evidence_texts=["General report evidence."],
        evidence_windows=[],
        prompt_client=FakePromptClient(),
        openai_client=model_client,
        ctx=_ctx(),
        source_id=request.source_id,
        prompt_family_reuse_reader=stale_reader,
        prompt_family_materializer=lambda *_: None,
        retained_claim_validation_sink=captured_packages.append,
    )

    assert len(reuse_requests) == 1
    assert len(model_client.requests) == 1
    assert any(
        issue.severity == "error" and "[factual_claim|not_established]" in issue.message
        for issue in issues
    )
    assert captured_packages[0].results[0].status == "unresolved"
    assert captured_packages[0].results[0].semantic_outcome == "not_established"


def test_unresolved_retained_soft_copy_claim_blocks_report_validation(tmp_path) -> None:
    sentence = "The report documents wallet use across retail checkout channels."
    claim_id = "soft_copy:expert_comment:unresolved"
    provenance = SoftCopyClaimProvenance(
        schema_version="1.0",
        artifact_family="expert_comment",
        claim_id=claim_id,
        text_hash=hashlib.sha256(sentence.encode("utf-8")).hexdigest(),
        classification="factual",
        evidence_ids=("f1",),
        source_spans=(),
        producing_prompt_identity={"namespace": "report_vs/artifacts/expert_comment"},
        generation_attempt=1,
        regeneration_attempt=0,
    )
    artifacts = {
        "expert_comment": sentence,
        "soft_copy_claim_provenance": soft_copy_claim_provenance_to_payload(
            [provenance]
        ),
    }
    request = replace(
        _retained_request(),
        artifacts=artifacts,
        evidence_packs={
            "findings": {
                "findings": [
                    {"id": "f1", "text": "Wallet use is discussed in checkout."}
                ]
            }
        },
    )
    provider_item_id = grounding_payload(request, artifacts)[
        "retained_claims_to_ground"
    ][0]["item_id"]
    model_client = FakeOpenAI(
        grounding_payload={
            "unsupported": [],
            "checks": [
                {
                    **_grounding_check(provider_item_id, sentence, "not_established"),
                    "section": "expert_comment",
                }
            ],
        }
    )

    issues = run_grounding_check(
        request=request,
        settings=_settings(tmp_path),
        grounding_use_vector_store=False,
        evidence_texts=[],
        evidence_windows=[],
        prompt_client=FakePromptClient(),
        openai_client=model_client,
        ctx=_ctx(),
    )

    unresolved = [
        issue for issue in issues if "[factual_claim|not_established]" in issue.message
    ]
    assert len(unresolved) == 1
    assert unresolved[0].severity == "error"
    assert unresolved[0].affected_section == "expert_comment"
    assert unresolved[0].entity_id == claim_id
    plan = _build_regeneration_plan(
        issues=unresolved,
        artifacts=artifacts,
        broad_retry_available=True,
    )
    assert plan.mode == "targeted"
    assert plan.targets[0].target_section == "expert_comment"
    assert plan.targets[0].allowed_paths == ["expert_comment[claim_index=0]"]


def test_initial_and_regenerated_candidate_share_grounding_identity_and_cache(
    tmp_path,
) -> None:
    request = _retained_request()
    item_id = "summary_claim:claim-1"
    claim_text = request.artifacts["summary"]["claim_evidence_map"][0]["claim"]
    output = {
        "unsupported": [],
        "checks": [_grounding_check(item_id, claim_text, "entailed")],
    }
    settings = _settings(tmp_path)
    initial_store = FakeAnalysisStore()
    initial_client = FakeOpenAI(grounding_payload=output)
    validate_report(
        request,
        settings,
        _ctx(),
        prompt_client=FakePromptClient(),
        openai_client=initial_client,
        analysis_store=initial_store,
    )

    candidate_request = replace(request, artifacts=dict(request.artifacts))
    assert not retained_claim_repair_issues(
        candidate_request.artifacts,
        candidate_request.evidence_packs,
        previous_artifacts=request.artifacts,
    )
    candidate_store = FakeAnalysisStore()
    candidate_client = FakeOpenAI(grounding_payload=output)
    validate_report(
        candidate_request,
        settings,
        _ctx(),
        prompt_client=FakePromptClient(),
        openai_client=candidate_client,
        analysis_store=candidate_store,
        pack_name="validation_regen_candidate_1",
    )

    initial_package = next(
        item[3]
        for item in initial_store.stored
        if item[2] == "validation_retained_claim_validation_candidate"
    )
    candidate_package = next(
        item[3]
        for item in candidate_store.stored
        if item[2] == "validation_regen_candidate_1_retained_claim_validation_candidate"
    )
    initial_result = initial_package["results"][0]
    candidate_result = candidate_package["results"][0]
    initial_grounding_calls = [
        call for call in initial_client.requests if call[2].endswith(":grounding")
    ]
    candidate_grounding_calls = [
        call for call in candidate_client.requests if call[2].endswith(":grounding")
    ]
    assert len(initial_grounding_calls) == 1
    assert candidate_grounding_calls == []
    assert initial_result["status"] == candidate_result["status"] == "supported"
    assert initial_result["semantic_identity"] == candidate_result["semantic_identity"]


def test_unresolved_claim_candidate_is_persisted_for_final_readiness_materialization(
    tmp_path,
) -> None:
    request = _retained_request()
    request = replace(
        request,
        source_id="",
        validation_mode="deferred_grounding",
    )
    analysis_store = FakeAnalysisStore()
    claim_text = request.artifacts["summary"]["claim_evidence_map"][0]["claim"]
    report = validate_report(
        request,
        _settings(tmp_path),
        _ctx(),
        prompt_client=FakePromptClient(),
        openai_client=FakeOpenAI(
            grounding_payload={
                "unsupported": [
                    {
                        "item_id": "summary_claim:claim-1",
                        "section": "summary.claim_evidence_map:claim-1.claim",
                        "text": claim_text,
                        "classification": "factual_claim",
                        "entailment_outcome": "not_established",
                        "reason": "Evidence does not establish the claim.",
                    }
                ],
                "checks": [
                    _grounding_check(
                        "summary_claim:claim-1",
                        claim_text,
                        "not_established",
                    )
                ],
            }
        ),
        analysis_store=analysis_store,
    )

    assert report.status == "fail"
    package_entry = next(
        item
        for item in analysis_store.stored
        if item[2] == "validation_retained_claim_validation_candidate"
    )
    package = package_entry[3]
    assert not any(
        item[2] == "retained_claim_validation" for item in analysis_store.stored
    )
    assert package["unresolved_factual_count"] == 1
    assert package["readiness_status"] == "not_publishable"
    assert package["validation_identity"]["grounding_validator_version"] == (
        CLAIM_GROUNDING_VALIDATOR_VERSION
    )
    result = package["results"][0]
    assert result["status"] == "unresolved"
    assert result["semantic_outcome"] == "not_established"
    identity = result["semantic_identity"]
    assert identity["claim_id"] == "summary_claim:claim-1"
    assert identity["claim_text_hash"] == result["candidate"]["text_hash"]
    assert identity["evidence_ids"] == ["f1"]
    assert len(identity["evidence_hash"]) == 64
    assert identity["source_identity"] == ""
    assert identity["prompt_family"] == "report_vs/validate/grounding"
    assert identity["prompt_content_hash"]
    assert identity["execution_identity"]
    assert identity["validator_version"] == CLAIM_GROUNDING_VALIDATOR_VERSION
    assert identity["model_provider"]
    assert identity["model_name"]
    assert identity["configuration_policy_identity"]
    assert identity["relevant_input_hash"]


def test_key_figure_grounding_uses_the_full_public_metric_and_direct_evidence() -> None:
    evidence_id = "quality-brand-suitability-rate"
    evidence_text = (
        "In the Q1 2026 Global Quality Benchmarks, Brand Suitability Violation "
        "Rate was APAC 8.0%, EMEA 6.3%, LATAM 6.0%, and North America 3.7%."
    )
    figure = {
        "figure_id": "quality-brand-suitability-rate",
        "label": "Brand Suitability Violation Rate",
        "subject": "Brand Suitability Violation Rate",
        "figure": "8.0%",
        "geography": "APAC",
        "timeframe": "Q1 2026",
        "observation_status": "observed",
        "evidence_id": evidence_id,
    }
    request = ValidationRequest(
        schema_version="1.0",
        report_id="key-figure-grounding",
        report=_report(),
        artifacts={"key_figures": [figure]},
        evidence_packs={
            "findings": {
                "findings": [
                    {
                        "id": evidence_id,
                        "text": evidence_text,
                        "pages": [3],
                    }
                ]
            }
        },
        source_id="source-key-figure-grounding",
    )

    items = grounding_payload(request, request.artifacts)["public_factual_items"]
    key_figure_items = [
        item for item in items if item["item_id"].startswith("key_figure:1:")
    ]
    metric_item = next(
        item for item in key_figure_items if item["item_id"] == "key_figure:1:figure"
    )

    assert len(key_figure_items) == 1
    assert metric_item["section"] == "key_figures:1.figure"
    assert metric_item["text"] == (
        "Brand Suitability Violation Rate Brand Suitability Violation Rate "
        "8.0% APAC Q1 2026 observed"
    )
    assert metric_item["evidence_ids"] == [evidence_id]
    assert metric_item["retained_evidence"] == evidence_text


def test_key_figure_grounding_retains_cohort_and_denominator_scope() -> None:
    evidence_id = "f1"
    evidence_text = (
        "Born-tech companies created 52% of total market-value growth for the "
        "top 20 gainers across sectors since 2015."
    )
    figure = {
        "figure_id": "technology-market-growth-born-tech",
        "label": "Share of total market-value growth attributed to born-tech companies",
        "subject": "Born-tech companies",
        "figure": "52% of total market-value growth",
        "cohort": "Top 20 gainers across sectors",
        "denominator": "Total market-value growth",
        "timeframe": "since 2015",
        "observation_status": "observed",
        "evidence_id": evidence_id,
    }
    request = ValidationRequest(
        schema_version="1.0",
        report_id="key-figure-population-grounding",
        report=_report(),
        artifacts={"key_figures": [figure]},
        evidence_packs={
            "findings": {"findings": [{"id": evidence_id, "text": evidence_text}]}
        },
        source_id="source-key-figure-population-grounding",
    )

    items = grounding_payload(request, request.artifacts)["public_factual_items"]
    metric_item = next(
        item for item in items if item["item_id"] == "key_figure:1:figure"
    )

    assert "Top 20 gainers across sectors" in metric_item["text"]
    assert "Total market-value growth" in metric_item["text"]
    assert evidence_text in metric_item["retained_evidence"]
