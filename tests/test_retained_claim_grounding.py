from __future__ import annotations

import hashlib
from dataclasses import replace
from types import SimpleNamespace

from src.contracts.claim_validation import ClaimValidationPackage
from src.contracts.protected_facts import PROTECTED_FACT_DIMENSIONS
from src.contracts.soft_copy_claim_provenance import (
    SoftCopyClaimProvenance,
    soft_copy_claim_provenance_to_payload,
)
from src.contracts.validation import ValidationRequest
from src.generators.claim_validation_generator import validate_retained_claims
from src.generators.validation.grounding import (
    _deterministic_claim_validation_issues,
    grounding_payload,
    run_grounding_check,
    run_grounding_rule,
)
from src.generators.validation.regeneration_candidate import (
    retained_claim_repair_issues,
)
from src.generators.validation_generator import validate_report
from src.orchestrators._report_analysis_orchestrator.regeneration_plan import (
    _build_regeneration_plan,
)
from tests._test_validation_generator._shared import (
    FakeAnalysisStore,
    FakeOpenAI,
    FakePromptClient,
    _ctx,
    _report,
    _settings,
)


def _retained_request() -> ValidationRequest:
    claim = "Wallet use is becoming a common checkout method across retailers."
    return ValidationRequest(
        schema_version="1.0",
        report_id="retained-grounding",
        report=_report(),
        artifacts={
            "summary": {
                "claim_evidence_map": [
                    {"id": "claim-1", "claim": claim, "evidence_id": "f1"}
                ]
            }
        },
        evidence_packs={
            "findings": {
                "findings": [
                    {
                        "id": "f1",
                        "text": "Wallet use is becoming a common checkout method.",
                    }
                ]
            }
        },
        source_id="source-retained-grounding",
    )


def test_deterministic_retained_claim_failure_enters_candidate_repair_plan() -> None:
    claim = (
        "“Actively exploring” and “plan to implement in the near future” are "
        "distinct positions grouped in the same finding."
    )
    source = (
        "The report highlight states: “63% of merchants are actively exploring "
        "or plan to implement agentic AI payments in the near future.”"
    )
    text_hash = hashlib.sha256(claim.encode("utf-8")).hexdigest()
    artifacts = {
        "linkedin_post": claim,
        "soft_copy_claim_provenance": soft_copy_claim_provenance_to_payload(
            [
                SoftCopyClaimProvenance(
                    schema_version="1.0",
                    artifact_family="linkedin_post",
                    claim_id=f"soft_copy:linkedin_post:{text_hash[:16]}",
                    text_hash=text_hash,
                    classification="factual",
                    evidence_ids=("f1",),
                    source_spans=(),
                    producing_prompt_identity={
                        "namespace": "report_vs/artifacts/linkedin_post"
                    },
                    generation_attempt=1,
                    regeneration_attempt=0,
                )
            ]
        ),
    }
    package = validate_retained_claims(
        artifacts,
        {
            "findings": {
                "findings": [{"id": "f1", "text": source}]
            }
        },
    )

    assert package.unsupported_factual_count == 1
    assert "quote_not_matched" in package.results[0].reasons
    issues = _deterministic_claim_validation_issues(package)
    assert len(issues) == 1
    assert issues[0].rule_id == "retained_claim.quote_match"
    assert issues[0].entity_id == package.results[0].candidate.claim_id
    assert issues[0].evidence_ids == ["f1"]

    plan = _build_regeneration_plan(
        issues=issues,
        artifacts=artifacts,
        broad_retry_available=False,
    )

    assert plan.mode == "targeted"
    assert plan.targets[0].target_section == "linkedin_post"
    assert plan.targets[0].allowed_paths == ["linkedin_post[claim_index=0]"]


def _grounding_check(item_id: str, text: str, outcome: str) -> dict:
    return {
        "item_id": item_id,
        "section": "summary.claim_evidence_map:claim-1.claim",
        "text": text,
        "classification": "factual_claim",
        "entailment_outcome": outcome,
        "proposition_status": "compatible",
        "protected_facts": {
            dimension: {
                "claim_value": None,
                "evidence_value": None,
                "status": "unknown",
            }
            for dimension in PROTECTED_FACT_DIMENSIONS
        },
        "reason": f"semantic_{outcome}",
    }


def test_grounding_rule_blocks_deterministic_quote_failure_before_promotion(
    tmp_path,
) -> None:
    claim = (
        "“Actively exploring” and “plan to implement in the near future” are "
        "distinct positions grouped in the same finding."
    )
    source = (
        "The report highlight states: “63% of merchants are actively exploring "
        "or plan to implement agentic AI payments in the near future.”"
    )
    text_hash = hashlib.sha256(claim.encode("utf-8")).hexdigest()
    artifacts = {
        "linkedin_post": claim,
        "soft_copy_claim_provenance": soft_copy_claim_provenance_to_payload(
            [
                SoftCopyClaimProvenance(
                    schema_version="1.0",
                    artifact_family="linkedin_post",
                    claim_id=f"soft_copy:linkedin_post:{text_hash[:16]}",
                    text_hash=text_hash,
                    classification="factual",
                    evidence_ids=("f1",),
                    source_spans=(),
                    producing_prompt_identity={"namespace": "test/linkedin"},
                    generation_attempt=1,
                    regeneration_attempt=0,
                )
            ]
        ),
    }
    evidence_packs = {
        "findings": {"findings": [{"id": "f1", "text": source}]}
    }
    request = ValidationRequest(
        schema_version="1.0",
        report_id="retained-claim-deterministic-failure",
        report=_report(),
        artifacts=artifacts,
        evidence_packs=evidence_packs,
        vector_store_id=None,
    )
    items = grounding_payload(request, artifacts)["public_factual_items"]
    checks = []
    for item in items:
        check = _grounding_check(item["item_id"], item["text"], "entailed")
        check["section"] = item["section"]
        checks.append(check)
    provider = FakeOpenAI(grounding_payload={"unsupported": [], "checks": checks})
    runtime = SimpleNamespace(
        request=request,
        source_id="",
        settings=_settings(tmp_path),
        prepared=SimpleNamespace(
            grounding_use_vector_store=False,
            evidence_texts=[source],
            evidence_windows=[],
        ),
        prompt_client=FakePromptClient(),
        openai_client=provider,
        ctx=_ctx(),
        vector_store_content_hash="",
        retained_claim_validation=None,
    )

    issues = run_grounding_rule(runtime)

    deterministic_failures = [
        issue for issue in issues if issue.rule_id == "retained_claim.quote_match"
    ]
    assert len(deterministic_failures) == 1
    assert deterministic_failures[0].severity == "error"
    assert deterministic_failures[0].entity_id == (
        f"soft_copy:linkedin_post:{text_hash[:16]}"
    )
    assert len(provider.requests) == 1


def test_grounding_payload_attaches_only_unresolved_claims_to_exact_evidence() -> None:
    request = _retained_request()
    payload = grounding_payload(request, request.artifacts)
    items = payload["retained_claims_to_ground"]

    assert len(items) == 1
    assert items[0]["item_id"] == "summary_claim:claim-1"
    assert items[0]["text"] == (
        "Wallet use is becoming a common checkout method across retailers."
    )
    assert len(items[0]["text_hash"]) == 64
    assert items[0]["evidence_ids"] == ["f1"]
    assert len(items[0]["evidence_hash"]) == 64
    retained_evidence = items[0]["retained_evidence"]
    assert len(retained_evidence) == 1
    assert retained_evidence[0]["evidence_id"] == "f1"
    assert retained_evidence[0]["source_pack"] == "findings"
    assert retained_evidence[0]["page"] is None
    assert retained_evidence[0]["text"] == (
        "Wallet use is becoming a common checkout method."
    )
    assert len(retained_evidence[0]["text_hash"]) == 64


def test_public_soft_copy_and_retained_claim_use_distinct_grounding_item_ids() -> None:
    sentence = "Retailer wallet use grew across checkout channels in 2025."
    claim_id = "soft_copy:expert_comment:1"
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
                    {"id": "f1", "text": "Retailer wallet use grew across channels."}
                ]
            }
        },
    )

    payload = grounding_payload(request, artifacts)

    public_ids = {
        item["item_id"] for item in payload["public_factual_items"]
    }
    retained = payload["retained_claims_to_ground"]
    assert len(retained) == 1
    assert claim_id in public_ids
    assert retained[0]["item_id"] not in public_ids
    assert retained[0]["text"] == sentence


def test_public_numeric_soft_copy_uses_its_retained_provenance_source_span() -> None:
    sentence = (
        "Generative AI tools drove a 693% increase in retail-site traffic "
        "during the 2025 holiday season compared with a year earlier."
    )
    source_text = (
        "The report cites a 693% year-over-year increase in retail-site traffic "
        "from generative AI tools during the 2025 holiday season."
    )
    claim_id = "soft_copy:linkedin_post:generative-ai-traffic"
    provenance = SoftCopyClaimProvenance(
        schema_version="1.0",
        artifact_family="linkedin_post",
        claim_id=claim_id,
        text_hash=hashlib.sha256(sentence.encode("utf-8")).hexdigest(),
        classification="factual",
        evidence_ids=("trend-2",),
        source_spans=(
            {
                "evidence_id": "trend-2",
                "source_pack": "doc_map",
                "page": 5,
                "text": source_text,
            },
            {
                "evidence_id": "neighboring-row",
                "source_pack": "doc_map",
                "page": 6,
                "text": "A separate category grew by 99%.",
            },
        ),
        producing_prompt_identity={"namespace": "report_vs/artifacts/linkedin_post"},
        generation_attempt=1,
        regeneration_attempt=0,
    )
    artifacts = {
        "insights_final": [
            {
                "id": "insight-1",
                "text": "A separate supported finding.",
                "evidence_id": "f3",
                "evidence": "A separate supported finding in another source section.",
            }
        ],
        "linkedin_post": sentence,
        "soft_copy_claim_provenance": soft_copy_claim_provenance_to_payload(
            [provenance]
        ),
    }
    request = replace(
        _retained_request(),
        artifacts=artifacts,
        evidence_packs={
            "doc_map": {
                "sections": [{"id": "trend-2", "text": source_text}]
            }
        },
    )

    payload = grounding_payload(request, artifacts)
    public_item = next(
        item
        for item in payload["public_factual_items"]
        if item["item_id"] == claim_id
    )

    assert public_item["evidence_ids"] == ["trend-2"]
    assert public_item["retained_evidence"] == source_text
    assert "neighboring-row" not in public_item["retained_evidence"]
    assert "99%" not in public_item["retained_evidence"]
    assert not any(
        item["text"] == sentence for item in payload["retained_claims_to_ground"]
    )


def test_summary_claim_validation_uses_the_joined_canonical_sentence_grid() -> None:
    summary = {
        "tldr": "U.S. revenue reached $918 billion",
        "card_tldr_compact": "in 2025.",
        "executive_summary": "",
        "claim_evidence_map": [],
    }
    sentence = "U.S. revenue reached $918 billion in 2025."
    provenance = SoftCopyClaimProvenance(
        schema_version="1.0",
        artifact_family="summary",
        claim_id="soft_copy:summary:us-revenue",
        text_hash=hashlib.sha256(sentence.encode("utf-8")).hexdigest(),
        classification="factual",
        evidence_ids=("f1",),
        source_spans=(),
        producing_prompt_identity={"namespace": "report_vs/artifacts/summary"},
        generation_attempt=1,
        regeneration_attempt=0,
    )
    artifacts = {
        "summary": summary,
        "soft_copy_claim_provenance": soft_copy_claim_provenance_to_payload(
            [provenance]
        ),
    }
    evidence_packs = {
        "findings": {
            "findings": [
                {"id": "f1", "text": "U.S. revenue reached $918 billion in 2025."}
            ]
        }
    }

    package = validate_retained_claims(artifacts, evidence_packs)
    summary_results = [
        result
        for result in package.results
        if result.candidate.source_family == "summary"
        and result.candidate.text.startswith("U.S. revenue")
    ]

    assert len(summary_results) == 1
    assert summary_results[0].candidate.text == sentence
    assert summary_results[0].candidate.claim_id == provenance.claim_id
    assert "soft_copy_provenance_sentence_missing" not in summary_results[0].reasons


def test_namespaced_retained_grounding_identity_maps_to_claim_lineage(tmp_path) -> None:
    sentence = "Retailer wallet use grew across checkout channels in 2025."
    claim_id = "soft_copy:expert_comment:1"
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
                    {"id": "f1", "text": "Retailer wallet use grew across channels."}
                ]
            }
        },
    )
    item_id = grounding_payload(request, artifacts)["retained_claims_to_ground"][0][
        "item_id"
    ]
    model_client = FakeOpenAI(
        grounding_payload={
            "unsupported": [],
            "checks": [_grounding_check(item_id, sentence, "entailed")],
        }
    )
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
        retained_claim_validation_sink=captured_packages.append,
    )

    assert issues == []
    assert len(captured_packages) == 1
    result = next(
        item
        for item in captured_packages[0].results
        if item.candidate.claim_id == claim_id
    )
    assert result.status == "supported"
    assert result.semantic_identity is not None
    assert result.semantic_identity.claim_id == claim_id


def test_semantic_fallback_payload_omits_proven_and_failed_claims() -> None:
    unresolved_text = (
        "Wallet use is becoming a common checkout method across retailers."
    )
    request = ValidationRequest(
        schema_version="1.0",
        report_id="retained-grounding-filter",
        report=_report(),
        artifacts={
            "summary": {
                "claim_evidence_map": [
                    {
                        "id": "unresolved",
                        "claim": unresolved_text,
                        "evidence_id": "f2",
                    },
                    {
                        "id": "supported",
                        "claim": "Wallet adoption reached 42% in 2026.",
                        "evidence_id": "f1",
                    },
                    {
                        "id": "contradicted",
                        "claim": "Wallet adoption reached 43% in 2026.",
                        "evidence_id": "f1",
                    },
                    {
                        "id": "unknown-evidence",
                        "claim": "Wallet use reached a new milestone.",
                        "evidence_id": "missing-id",
                    },
                ]
            },
            "expert_comment": "An unbound factual statement remains.",
        },
        evidence_packs={
            "findings": {
                "findings": [
                    {"id": "f1", "text": "Wallet adoption reached 42% in 2026."},
                    {
                        "id": "f2",
                        "text": "Wallet use is becoming a common checkout method.",
                    },
                ]
            }
        },
    )

    payload = grounding_payload(request, request.artifacts)

    assert [item["item_id"] for item in payload["retained_claims_to_ground"]] == [
        "summary_claim:unresolved"
    ]


def test_reused_report_grounding_maps_semantics_and_current_identity(tmp_path) -> None:
    request = _retained_request()
    item_id = "summary_claim:claim-1"
    text = request.artifacts["summary"]["claim_evidence_map"][0]["claim"]
    reused_output = {
        "unsupported": [],
        "checks": [_grounding_check(item_id, text, "entailed")],
    }
    reuse_requests = []
    captured_packages: list[ClaimValidationPackage] = []
    model_client = FakeOpenAI(grounding_payload=reused_output)

    def reuse_reader(reuse_request, _ctx):
        reuse_requests.append(reuse_request)
        return SimpleNamespace(
            reusable=True,
            reason="compatible_retained_output",
            output_payload=reused_output,
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
        prompt_family_reuse_reader=reuse_reader,
        prompt_family_materializer=lambda *_: None,
        retained_claim_validation_sink=captured_packages.append,
    )

    assert issues == []
    assert len(reuse_requests) == 1
    assert model_client.requests == []
    assert captured_packages[0].results[0].status == "supported"
    result = captured_packages[0].results[0]
    assert result.semantic_outcome == "entailed"
    assert result.semantic_identity is not None
    assert result.semantic_identity.claim_id == item_id
    assert result.semantic_identity.evidence_ids == ["f1"]
    assert result.semantic_identity.source_identity == request.source_id
    assert (
        result.semantic_identity.relevant_input_hash
        == reuse_requests[0].relevant_input_hash
    )
    assert (
        result.semantic_identity.configuration_policy_identity
        == reuse_requests[0].configuration_policy_hash
    )


def test_incomplete_reusable_grounding_is_rejected_and_revalidated(tmp_path) -> None:
    request = _retained_request()
    item_id = "summary_claim:claim-1"
    text = request.artifacts["summary"]["claim_evidence_map"][0]["claim"]
    model_client = FakeOpenAI(
        grounding_payload={
            "unsupported": [],
            "checks": [_grounding_check(item_id, text, "entailed")],
        }
    )
    captured_packages: list[ClaimValidationPackage] = []

    def incomplete_reader(_reuse_request, _ctx):
        return SimpleNamespace(
            reusable=True,
            reason="compatible_retained_output",
            output_payload={"unsupported": [], "checks": []},
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
        source_id=request.source_id,
        prompt_family_reuse_reader=incomplete_reader,
        prompt_family_materializer=lambda *_: None,
        retained_claim_validation_sink=captured_packages.append,
    )

    assert issues == []
    assert len(model_client.requests) == 1
    assert captured_packages[0].results[0].status == "supported"


def test_incomplete_grounding_output_exhausts_existing_bounded_recovery(
    tmp_path,
) -> None:
    request = _retained_request()
    model_client = FakeOpenAI(grounding_payload={"unsupported": [], "checks": []})
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
        retained_claim_validation_sink=captured_packages.append,
    )

    assert len(model_client.requests) == 3
    assert captured_packages == []
    assert len(issues) == 1
    assert issues[0].rule_id == "grounding"
    assert issues[0].severity == "error"
    assert (
        "did not produce a substantive schema-valid JSON artifact" in issues[0].message
    )


def test_conflicting_claim_identity_fails_before_provider_call(tmp_path) -> None:
    request = _retained_request()
    text = request.artifacts["summary"]["claim_evidence_map"][0]["claim"]
    request = replace(
        request,
        artifacts={
            "summary": {
                "claim_evidence_map": [
                    {"id": "duplicate", "claim": text, "evidence_id": "f1"},
                    {"id": "duplicate", "claim": text, "evidence_id": "f2"},
                ]
            }
        },
        evidence_packs={
            "findings": {
                "findings": [
                    {
                        "id": "f1",
                        "text": "Wallet use is becoming a common checkout method.",
                    },
                    {"id": "f2", "text": "Wallet checkout has grown among retailers."},
                ]
            }
        },
    )
    model_client = FakeOpenAI(grounding_payload={"unsupported": [], "checks": []})
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
        retained_claim_validation_sink=captured_packages.append,
    )

    assert model_client.requests == []
    assert captured_packages == []
    assert len(issues) == 1
    assert issues[0].severity == "error"
    assert "conflicting text or evidence" in issues[0].message


def test_multiple_retained_claims_use_one_report_level_grounding_call(tmp_path) -> None:
    request = _retained_request()
    second_text = (
        "Wallet use is becoming a familiar checkout route in several retail categories."
    )
    request = replace(
        request,
        source_id="",
        artifacts={
            "summary": {
                "claim_evidence_map": [
                    *request.artifacts["summary"]["claim_evidence_map"],
                    {"id": "claim-2", "claim": second_text, "evidence_id": "f1"},
                ]
            }
        },
    )
    checks = [
        _grounding_check(
            "summary_claim:claim-1",
            request.artifacts["summary"]["claim_evidence_map"][0]["claim"],
            "entailed",
        ),
        _grounding_check("summary_claim:claim-2", second_text, "entailed"),
    ]
    model_client = FakeOpenAI(grounding_payload={"unsupported": [], "checks": checks})
    captured_packages: list[ClaimValidationPackage] = []

    run_grounding_check(
        request=request,
        settings=_settings(tmp_path),
        grounding_use_vector_store=False,
        evidence_texts=[],
        evidence_windows=[],
        prompt_client=FakePromptClient(),
        openai_client=model_client,
        ctx=_ctx(),
        retained_claim_validation_sink=captured_packages.append,
    )

    grounding_calls = [
        call for call in model_client.requests if call[2].endswith(":grounding")
    ]
    assert len(grounding_calls) == 1
    assert len(captured_packages[0].results) == 2
    assert {result.status for result in captured_packages[0].results} == {"supported"}


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
        issue.severity == "error"
        and "[factual_claim|not_established]" in issue.message
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
        issue
        for issue in issues
        if "[factual_claim|not_established]" in issue.message
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
        "grounding_validation_output:1.4"
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
    assert identity["validator_version"] == "grounding_validation_output:1.4"
    assert identity["model_provider"]
    assert identity["model_name"]
    assert identity["configuration_policy_identity"]
    assert identity["relevant_input_hash"]
