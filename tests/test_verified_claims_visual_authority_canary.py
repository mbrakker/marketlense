from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.contracts.verified_claims import (
    VERIFIED_CLAIMS_VISUAL_SCHEMA_VERSION,
    VisualClaimEvaluationResponse,
    VisualClaimEvaluationResult,
)
from src.generators._artifact_generator.family_policy import (
    build_artifact_family_status,
)
from src.generators._artifact_generator.generation import generate_artifacts
from src.generators.artifact_normalization import (
    artifact_evidence_span_index,
    bind_artifact_evidence_spans,
    build_verified_fact_doc_map,
    page_bound_direct_evidence_packs,
    remap_editorial_plan_to_verified_facts,
)
from src.generators.verified_claims_canary import (
    VisualAuthorityCanaryConfig,
    admit_visual_authority_candidates,
    build_visual_authority_admitter,
)
from src.utils.errors import AppError
from tests._test_artifact_generator._shared import (
    CapturingPromptClient,
    FakeAnalysisStore,
    FakeOpenAI,
    _ctx,
    _settings,
)
from tests._test_artifact_generator.cases_05_docmap_insight_selection import (
    _doc_map,
    _generation_evidence,
    _generation_responses,
    _insight,
)

SOURCE_IDENTITY = f"frozen-report|pdf-sha256:{'a' * 64}"


def _metric(value: str = "42%", *, cohort: str = "all buyers") -> dict[str, str]:
    return {
        "label": "Adoption",
        "value": value,
        "unit": "%",
        "trend": "up",
        "timeframe": "2026",
        "geography": "global",
        "segment": "buyers",
        "sample_size": "1000",
        "confidence": "high",
        "subject": "buyers",
        "cohort": cohort,
        "denominator": "respondents",
        "observation_status": "observed",
    }


def _candidate(
    candidate_id: str = "candidate-1",
    *,
    evidence_id: str = "finding-1",
    page: int = 4,
    text: str = "Buyers increasingly use online research before purchase.",
    metric: dict[str, str] | None = None,
    source_identity: str = "",
) -> dict:
    evidence = "Online research before purchase rose to 42% in 2026."
    item = {
        "id": candidate_id,
        "text": text,
        "evidence_id": evidence_id,
        "evidence": evidence,
        "pages": [page],
        "evidence_spans": [
            {
                "evidence_id": evidence_id,
                "source_pack": "findings",
                "page": page,
                "text": evidence,
            }
        ],
        "metric": deepcopy(metric or _metric()),
    }
    if source_identity:
        item["source_identity"] = source_identity
    return item


def _evidence_packs(*candidates: dict) -> dict:
    return {
        "findings": {
            "family_status": {"status": "generated", "policy_action": "keep"},
            "findings": [
                {
                    "id": item["evidence_id"],
                    "text": item["text"],
                    "evidence": item["evidence"],
                    "pages": item["pages"],
                }
                for item in candidates
            ],
        }
    }


def _result(
    candidate: dict,
    *,
    outcome: str = "verified",
    final_claim: str | None = None,
    source_identity: str = SOURCE_IDENTITY,
    corrected_status: str = "retained",
    corrected_evidence_id: str | None = None,
    corrected_metric: dict[str, str] | None = None,
    physical_page: int | None = None,
    verified_fact: dict | None = None,
) -> VisualClaimEvaluationResult:
    evidence_id = candidate["evidence_id"]
    page = physical_page or candidate["pages"][0]
    corrected_id = corrected_evidence_id or evidence_id
    corrected_pages = (
        [physical_page] if physical_page is not None else list(candidate["pages"])
    )
    if (
        verified_fact is None
        and corrected_status == "retained"
        and page in candidate["pages"]
    ):
        verified_fact = {
            "statement": final_claim or candidate["text"],
            "metric": deepcopy(candidate["metric"]),
            "qualifiers": [],
            "supporting_physical_pages": list(corrected_pages),
        }
    fact_payload = deepcopy(verified_fact or {})
    if fact_payload:
        fact_pages = fact_payload.get("supporting_physical_pages") or corrected_pages
        fact_payload["source_pdf_sha256"] = "a" * 64
        fact_payload["provenance"] = {
            **(
                fact_payload.get("provenance")
                if isinstance(fact_payload.get("provenance"), dict)
                else {}
            ),
            "source_truth_notes_by_page": {
                str(fact_page): "The inspected page supports the verified fact."
                for fact_page in fact_pages
            },
        }
        source_truth_notes_by_page = {
            str(fact_page): "The inspected page supports the verified fact."
            for fact_page in fact_pages
        }
    else:
        source_truth_notes_by_page = {}
    if corrected_status not in {"retained", "independently_bound"}:
        corrected_ids = []
        corrected_spans = []
        corrected_metric_binding = {}
    elif corrected_status == "retained":
        corrected_ids = [candidate["evidence_id"]]
        corrected_ids.extend(
            evidence_id
            for evidence_id in candidate.get("evidence_ids", [])
            if evidence_id not in corrected_ids
        )
        corrected_spans = deepcopy(candidate["evidence_spans"])
        corrected_metric_binding = deepcopy(candidate["metric"])
    else:
        corrected_ids = [corrected_id]
        corrected_spans = [
            {
                "evidence_id": corrected_id,
                "source_pack": "findings",
                "page": page,
                "text": candidate["evidence"],
            }
        ]
        corrected_metric_binding = deepcopy(corrected_metric or candidate["metric"])
    return VisualClaimEvaluationResult(
        schema_version=VERIFIED_CLAIMS_VISUAL_SCHEMA_VERSION,
        candidate_id=candidate["id"],
        original_claim=candidate["text"],
        source_identity=source_identity,
        physical_page=page,
        physical_pages=corrected_pages,
        outcome=outcome,
        evidence_ids=[evidence_id],
        evidence_spans=deepcopy(candidate["evidence_spans"]),
        original_metric_binding=deepcopy(candidate["metric"]),
        corrected_evidence_ids=corrected_ids,
        corrected_evidence_spans=corrected_spans,
        corrected_metric_binding=corrected_metric_binding,
        corrected_source_binding_status=corrected_status,
        final_claim=final_claim or candidate["text"],
        source_truth_notes_by_page=source_truth_notes_by_page,
        verified_fact=fact_payload,
    )


def _response(*results: VisualClaimEvaluationResult) -> VisualClaimEvaluationResponse:
    return VisualClaimEvaluationResponse(
        schema_version=VERIFIED_CLAIMS_VISUAL_SCHEMA_VERSION,
        shadow_mode=True,
        claims=list(results),
    )


def _verified_admission(shortlisted: list[dict], *, digest: str) -> SimpleNamespace:
    facts = []
    findings = []
    projections = []
    for index, candidate in enumerate(shortlisted):
        fact_id = candidate["id"]
        metric = deepcopy(candidate["metric"])
        if index == 0:
            metric["timeframe"] = "2024"
        evidence_id = f"verified-fact:{fact_id}"
        pages = list(candidate["pages"])
        fact = {
            "schema_version": "1.0",
            "fact_id": fact_id,
            "statement": candidate["text"],
            "metric": metric,
            "qualifiers": [],
            "source_identity": SOURCE_IDENTITY,
            "source_pdf_sha256": "a" * 64,
            "supporting_physical_pages": pages,
            "verification_outcome": "verified",
            "provenance": {
                "inspected_physical_pages": pages,
                "source_truth_notes_by_page": {
                    str(page): "The inspected page supports the verified fact."
                    for page in pages
                },
                "discovery_candidate_id": fact_id,
                "discovery_evidence_ids": [candidate["evidence_id"]],
            },
        }
        facts.append(fact)
        findings.append(
            {
                "id": evidence_id,
                "verified_fact_id": fact_id,
                "text": fact["statement"],
                "statement": fact["statement"],
                "evidence": fact["statement"],
                "evidence_spans": [
                    {
                        "evidence_id": evidence_id,
                        "source_pack": "verified_facts",
                        "page": page,
                        "text": "The inspected page supports the verified fact.",
                    }
                    for page in pages
                ],
                "pages": pages,
                "metric": metric,
                "source_identity": SOURCE_IDENTITY,
            }
        )
        projection = deepcopy(candidate)
        projection["evidence_id"] = evidence_id
        projection["evidence"] = fact["statement"]
        projection["evidence_spans"] = findings[-1]["evidence_spans"]
        projection["metric"] = metric
        projection["verified_fact_id"] = fact_id
        projection["verified_fact"] = deepcopy(fact)
        projections.append(projection)
    return SimpleNamespace(
        admitted_candidates=projections,
        verified_facts=facts,
        verified_evidence_packs={
            "findings": {
                "family_status": {
                    "family": "findings",
                    "source": "verified_facts",
                    "status": "generated",
                    "policy_action": "keep",
                },
                "findings": findings,
            },
            "verified_facts": {
                "family_status": {
                    "family": "verified_facts",
                    "source": "visual_verification",
                    "status": "generated",
                    "policy_action": "keep",
                },
                "verified_facts": deepcopy(facts),
            },
        },
        digest=digest,
        audit={"evaluated_count": len(shortlisted), "quarantined_count": 0},
    )


def test_unchanged_verified_claim_is_admitted_with_authoritative_candidate_fields():
    candidate = _candidate()

    admission = admit_visual_authority_candidates(
        candidates=[candidate],
        evaluation=_response(_result(candidate)),
        source_identity=SOURCE_IDENTITY,
        doc_map={},
        evidence_packs=_evidence_packs(candidate),
    )

    assert [item["id"] for item in admission.admitted_candidates] == ["candidate-1"]
    admitted = admission.admitted_candidates[0]
    assert admitted["text"] == candidate["text"]
    assert admitted["metric"] == candidate["metric"]
    assert admitted["evidence_id"] == "verified-fact:candidate-1"
    assert admitted["pages"] == [4]
    assert admission.digest
    assert admission.audit["admitted_count"] == 1


def test_material_correction_without_independent_binding_is_quarantined():
    candidate = _candidate()
    result = _result(
        candidate,
        final_claim="A different supported-looking conclusion replaces the claim.",
        corrected_status="unbound",
    )

    admission = admit_visual_authority_candidates(
        candidates=[candidate],
        evaluation=_response(result),
        source_identity=SOURCE_IDENTITY,
        doc_map={},
        evidence_packs=_evidence_packs(candidate),
    )

    assert admission.admitted_candidates == []
    assert admission.audit["quarantined"][0]["reason"] == "verified_fact_missing"


def test_material_correction_is_admitted_from_verified_fact_without_original_binding():
    candidate = _candidate(metric=_metric("42%", cohort="all buyers"))
    verified_metric = _metric("51%", cohort="repeat buyers")
    result = _result(
        candidate,
        final_claim="Repeat buyers reached 51% adoption in 2026.",
        corrected_status="unbound",
        verified_fact={
            "statement": "Repeat buyers reached 51% adoption in 2026.",
            "metric": verified_metric,
            "qualifiers": ["Observed among repeat buyers."],
            "supporting_physical_pages": [4],
        },
    )

    admission = admit_visual_authority_candidates(
        candidates=[candidate],
        evaluation=_response(result),
        source_identity=SOURCE_IDENTITY,
        doc_map={},
        evidence_packs=_evidence_packs(candidate),
    )

    assert len(admission.verified_facts) == 1
    fact = admission.verified_facts[0]
    assert fact["fact_id"] == "candidate-1"
    assert fact["statement"] == "Repeat buyers reached 51% adoption in 2026."
    assert fact["metric"] == verified_metric
    assert fact["source_pdf_sha256"] == "a" * 64
    assert fact["supporting_physical_pages"] == [4]
    assert fact["provenance"]["discovery_candidate_id"] == "candidate-1"
    assert fact["provenance"]["discovery_evidence_ids"] == ["finding-1"]
    assert (
        admission.verified_evidence_packs["findings"]["findings"][0]["id"]
        == "verified-fact:candidate-1"
    )
    assert (
        admission.verified_evidence_packs["findings"]["findings"][0]["evidence"]
        != candidate["evidence"]
    )


def test_verified_fact_is_required_for_material_correction():
    candidate = _candidate()
    result = _result(
        candidate,
        final_claim="A materially different source-supported conclusion.",
        corrected_status="unbound",
    )

    admission = admit_visual_authority_candidates(
        candidates=[candidate],
        evaluation=_response(result),
        source_identity=SOURCE_IDENTITY,
        doc_map={},
        evidence_packs=_evidence_packs(candidate),
    )

    assert admission.verified_facts == []
    assert admission.audit["quarantined"][0]["reason"] == "verified_fact_missing"


def test_material_correction_with_complete_independent_binding_replaces_facts():
    candidate = _candidate()
    corrected = _candidate(
        candidate["id"],
        evidence_id="finding-2",
        page=7,
        text="A source-supported replacement conclusion.",
        metric=_metric("51%", cohort="repeat buyers"),
    )
    result = _result(
        candidate,
        final_claim=corrected["text"],
        corrected_status="independently_bound",
        corrected_evidence_id=corrected["evidence_id"],
        corrected_metric=corrected["metric"],
        physical_page=7,
        verified_fact={
            "statement": corrected["text"],
            "metric": corrected["metric"],
            "qualifiers": ["Observed among repeat buyers."],
            "supporting_physical_pages": [7],
        },
    )

    admission = admit_visual_authority_candidates(
        candidates=[candidate],
        evaluation=_response(result),
        source_identity=SOURCE_IDENTITY,
        doc_map={},
        evidence_packs=_evidence_packs(candidate, corrected),
    )

    assert len(admission.admitted_candidates) == 1
    admitted = admission.admitted_candidates[0]
    assert admitted["text"] == corrected["text"]
    assert admitted["evidence_id"] == "verified-fact:candidate-1"
    assert admitted["pages"] == [7]
    assert admitted["metric"] == corrected["metric"]


@pytest.mark.parametrize(
    ("outcome", "source_identity"),
    [
        ("failed_verification", SOURCE_IDENTITY),
        ("unresolved", SOURCE_IDENTITY),
        ("skipped", SOURCE_IDENTITY),
        ("verified", "other-report|pdf-sha256:" + "a" * 64),
        ("verified", "frozen-report-without-hash"),
    ],
)
def test_non_terminal_or_source_mismatched_results_are_not_admitted(
    outcome: str, source_identity: str
):
    candidate = _candidate()
    result = _result(candidate, outcome=outcome, source_identity=source_identity)

    admission = admit_visual_authority_candidates(
        candidates=[candidate],
        evaluation=_response(result),
        source_identity=SOURCE_IDENTITY,
        doc_map={},
        evidence_packs=_evidence_packs(candidate),
    )

    assert admission.admitted_candidates == []


def test_conflicting_same_id_candidates_fail_closed_without_score_resolution():
    first = _candidate()
    conflicting = _candidate(
        first["id"], evidence_id="finding-2", page=7, metric=_metric("51%")
    )

    admission = admit_visual_authority_candidates(
        candidates=[first, conflicting],
        evaluation=_response(_result(first)),
        source_identity=SOURCE_IDENTITY,
        doc_map={},
        evidence_packs=_evidence_packs(first, conflicting),
    )

    assert admission.admitted_candidates == []
    assert admission.audit["quarantined"][0]["reason"] == "candidate_factual_conflict"


def test_same_id_identical_candidate_representations_remain_admissible():
    candidate = _candidate()
    duplicate = deepcopy(candidate)
    duplicate["score"] = 0.1

    admission = admit_visual_authority_candidates(
        candidates=[candidate, duplicate],
        evaluation=_response(_result(candidate)),
        source_identity=SOURCE_IDENTITY,
        doc_map={},
        evidence_packs=_evidence_packs(candidate),
    )

    assert [item["id"] for item in admission.admitted_candidates] == ["candidate-1"]


def test_same_id_equivalent_duplicate_is_evaluated_once_without_quarantine():
    candidate = _candidate()
    duplicate = deepcopy(candidate)
    duplicate["score"] = 0.1

    admission = admit_visual_authority_candidates(
        candidates=[candidate, duplicate],
        evaluation=_response(_result(candidate)),
        source_identity=SOURCE_IDENTITY,
        doc_map={},
        evidence_packs=_evidence_packs(candidate),
    )

    assert admission.audit["evaluated_count"] == 1
    assert admission.audit["quarantined"] == []
    assert admission.audit["coverage_complete"] is True


def test_verified_facts_survive_explicit_unresolved_sibling_results():
    first = _candidate("candidate-1", evidence_id="finding-1", page=4)
    second = _candidate("candidate-2", evidence_id="finding-2", page=5)

    admission = admit_visual_authority_candidates(
        candidates=[first, second],
        evaluation=_response(
            _result(first),
            _result(second, outcome="unresolved"),
        ),
        source_identity=SOURCE_IDENTITY,
        doc_map={},
        evidence_packs=_evidence_packs(first, second),
    )

    assert [fact["fact_id"] for fact in admission.verified_facts] == ["candidate-1"]
    assert admission.audit["coverage_complete"] is True
    assert admission.audit["outcome_counts"] == {"verified": 1, "unresolved": 1}
    assert admission.audit["quarantined"] == [
        {"candidate_id": "candidate-2", "reason": "outcome_unresolved"}
    ]


def test_missing_result_is_an_integrity_failure_not_partial_admission():
    first = _candidate("candidate-1", evidence_id="finding-1", page=4)
    second = _candidate("candidate-2", evidence_id="finding-2", page=5)

    admission = admit_visual_authority_candidates(
        candidates=[first, second],
        evaluation=_response(_result(first)),
        source_identity=SOURCE_IDENTITY,
        doc_map={},
        evidence_packs=_evidence_packs(first, second),
    )

    assert admission.verified_facts == []
    assert admission.audit["terminal_error"] == "evaluation_coverage_incomplete"
    assert {item["reason"] for item in admission.audit["quarantined"]} == {
        "evaluation_missing"
    }


def test_duplicate_result_id_is_an_integrity_failure_not_first_result_wins():
    candidate = _candidate()

    admission = admit_visual_authority_candidates(
        candidates=[candidate],
        evaluation=_response(
            _result(candidate),
            _result(candidate, final_claim="A conflicting duplicate result."),
        ),
        source_identity=SOURCE_IDENTITY,
        doc_map={},
        evidence_packs=_evidence_packs(candidate),
    )

    assert admission.verified_facts == []
    assert admission.audit["terminal_error"] == "evaluation_coverage_incomplete"
    assert admission.audit["quarantined"] == [
        {"candidate_id": "candidate-1", "reason": "duplicate_evaluation_id"}
    ]


def test_unexpected_result_id_is_an_integrity_failure_not_an_extra_fact():
    candidate = _candidate()
    unexpected = _candidate("candidate-2", evidence_id="finding-2", page=5)

    admission = admit_visual_authority_candidates(
        candidates=[candidate],
        evaluation=_response(_result(candidate), _result(unexpected)),
        source_identity=SOURCE_IDENTITY,
        doc_map={},
        evidence_packs=_evidence_packs(candidate),
    )

    assert admission.verified_facts == []
    assert admission.audit["terminal_error"] == "evaluation_coverage_incomplete"
    assert admission.audit["quarantined"] == [
        {"candidate_id": "candidate-2", "reason": "evaluation_unexpected_id"}
    ]


def test_failed_verification_is_accounted_without_discarding_valid_sibling():
    verified = _candidate("candidate-1", evidence_id="finding-1", page=4)
    failed = _candidate("candidate-2", evidence_id="finding-2", page=5)

    admission = admit_visual_authority_candidates(
        candidates=[verified, failed],
        evaluation=_response(
            _result(verified),
            _result(failed, outcome="failed_verification"),
        ),
        source_identity=SOURCE_IDENTITY,
        doc_map={},
        evidence_packs=_evidence_packs(verified, failed),
    )

    assert [fact["fact_id"] for fact in admission.verified_facts] == ["candidate-1"]
    assert admission.audit["coverage_complete"] is True
    assert admission.audit["outcome_counts"] == {
        "verified": 1,
        "failed_verification": 1,
    }
    assert admission.audit["quarantined"] == [
        {"candidate_id": "candidate-2", "reason": "outcome_failed_verification"}
    ]


def test_verified_fact_projection_is_not_direct_quote_evidence():
    candidate = _candidate()
    admission = admit_visual_authority_candidates(
        candidates=[candidate],
        evaluation=_response(_result(candidate)),
        source_identity=SOURCE_IDENTITY,
        doc_map={},
        evidence_packs=_evidence_packs(candidate),
    )

    evidence_id = "verified-fact:candidate-1"
    index = artifact_evidence_span_index(
        doc_map={}, evidence_packs=admission.verified_evidence_packs
    )
    assert index[evidence_id][0]["source_pack"] == "verified_facts"
    assert (
        page_bound_direct_evidence_packs(admission.verified_evidence_packs)["findings"][
            "findings"
        ]
        == []
    )
    quote_status = build_artifact_family_status(
        summary={},
        insights_candidates=[],
        insights_final=[],
        quotes_final=[
            {
                "text": candidate["text"],
                "evidence_id": evidence_id,
                "evidence_spans": index[evidence_id],
            }
        ],
        expert_comment="",
        linkedin_post="",
    )
    assert quote_status["quotes"]["reason"] == "quotes_missing_verbatim_source"

    projected = deepcopy(admission.admitted_candidates[0])
    bind_artifact_evidence_spans(
        summary={},
        insights_candidates=[],
        insights_final=[projected],
        quotes_final=[],
        doc_map={},
        evidence_packs=admission.verified_evidence_packs,
    )
    assert projected["text"] == candidate["text"]
    assert projected["pages"] == [4]
    assert projected["source_identity"] == SOURCE_IDENTITY
    assert projected["evidence_spans"][0]["source_pack"] == "verified_facts"
    assert projected["evidence_spans"][0]["text"] != candidate["evidence"]


def test_invalid_terminal_outcome_fails_closed_as_malformed_accounting():
    candidate = _candidate()
    result = _result(candidate, outcome="rejected")

    admission = admit_visual_authority_candidates(
        candidates=[candidate],
        evaluation=_response(result),
        source_identity=SOURCE_IDENTITY,
        doc_map={},
        evidence_packs=_evidence_packs(candidate),
    )

    assert admission.verified_facts == []
    assert admission.audit["terminal_error"] == "evaluation_coverage_incomplete"
    assert admission.audit["quarantined"] == [
        {"candidate_id": "candidate-1", "reason": "evaluation_outcome_invalid"}
    ]


def test_verified_fact_conflicting_identity_fails_closed():
    candidate = _candidate()
    result = _result(
        candidate,
        verified_fact={
            "statement": candidate["text"],
            "metric": candidate["metric"],
            "qualifiers": [],
            "supporting_physical_pages": [4],
            "source_identity": "other-report|pdf-sha256:" + "a" * 64,
        },
    )

    admission = admit_visual_authority_candidates(
        candidates=[candidate],
        evaluation=_response(result),
        source_identity=SOURCE_IDENTITY,
        doc_map={},
        evidence_packs=_evidence_packs(candidate),
    )

    assert admission.verified_facts == []
    assert admission.audit["quarantined"][0]["reason"] == (
        "verified_fact_source_identity_mismatch"
    )


def test_source_consistent_multi_page_binding_remains_admissible():
    candidate = _candidate()
    candidate["pages"] = [4, 5]
    candidate["evidence_spans"].append(
        {
            "evidence_id": "finding-1",
            "source_pack": "findings",
            "page": 5,
            "text": candidate["evidence"],
        }
    )

    admission = admit_visual_authority_candidates(
        candidates=[candidate],
        evaluation=_response(_result(candidate)),
        source_identity=SOURCE_IDENTITY,
        doc_map={},
        evidence_packs=_evidence_packs(candidate),
    )

    assert [item["pages"] for item in admission.admitted_candidates] == [[4, 5]]


def test_result_page_not_supported_by_canonical_evidence_fails_closed():
    candidate = _candidate()
    result = _result(candidate, physical_page=9)

    admission = admit_visual_authority_candidates(
        candidates=[candidate],
        evaluation=_response(result),
        source_identity=SOURCE_IDENTITY,
        doc_map={},
        evidence_packs=_evidence_packs(candidate),
    )

    assert admission.admitted_candidates == []
    assert admission.audit["quarantined"][0]["reason"] == "verified_fact_missing"


def test_generation_uses_admitted_pool_and_authority_digest(tmp_path):
    candidates = [
        _insight("f1", score=0.99, text="Retained first insight."),
        _insight("f2", score=0.98, text="Retained second insight."),
    ]
    prompt_client = CapturingPromptClient()

    def admit(shortlisted):
        assert [item["evidence_id"] for item in shortlisted] == ["f1", "f2"]
        return _verified_admission(shortlisted, digest="d" * 64)

    responses = _generation_responses(candidates, plan_evidence_ids=["f1", "f2"])
    responses["summary"]["summary"]["claim_evidence_map"][0]["evidence_id"] = (
        f"verified-fact:{candidates[0]['id']}"
    )
    payload = generate_artifacts(
        report_id="visual-authority-canary",
        report_name="Visual Authority Canary",
        doc_map=_doc_map(2),
        evidence_packs=_generation_evidence(2),
        settings=_settings(tmp_path),
        ctx=_ctx(),
        openai_client=FakeOpenAI(responses),
        prompt_client=prompt_client,
        analysis_store=FakeAnalysisStore(),
        visual_authority_admitter=admit,
    )

    verified_ids = {f"verified-fact:{candidate['id']}" for candidate in candidates}
    assert {item["evidence_id"] for item in payload["insights_final"]} == verified_ids
    assert payload["quotes_final"] == []
    assert (
        payload["verified_facts"]
        == payload["_cache"]["visual_authority_canary"]["verified_facts"]
    )
    first_final = next(
        item
        for item in payload["insights_final"]
        if item["evidence_id"] == f"verified-fact:{candidates[0]['id']}"
    )
    assert first_final["metric"]["timeframe"] == "2024"
    assert payload["_cache"]["visual_authority_canary"]["digest"] == "d" * 64
    assert any(
        item.get("evidence_id") == f"verified-fact:{candidates[0]['id']}"
        and item.get("timeframe") == "2024"
        for item in payload["metric_spine"]
    )
    final_vars = prompt_client.variables_for_namespace(
        "report_vs/artifacts/insights_final"
    )
    assert final_vars["_visual_authority_digest"] == "d" * 64
    assert (
        f'"verified-fact:{candidates[0]["id"]}"'
        in final_vars["insights_candidates_json"]
    )
    assert (
        f'"verified-fact:{candidates[1]["id"]}"'
        in final_vars["insights_candidates_json"]
    )
    for namespace in (
        "report_vs/artifacts/expert_comment",
        "report_vs/artifacts/linkedin_post",
    ):
        downstream_vars = prompt_client.variables_for_namespace(namespace)
        assert (
            f'"verified-fact:{candidates[0]["id"]}"'
            in downstream_vars["metric_spine_json"]
        )
    assert "The retained report confirms the trend." not in (
        prompt_client.variables_for_namespace("report_vs/artifacts/summary").get(
            "evidence_json", ""
        )
    )


def test_verified_fact_context_removes_discovery_facts_and_omits_unmapped_themes():
    source_doc_map = {
        "doc_id": "report-1",
        "title": "Report title",
        "region": "Global",
        "covered_period": "2026",
        "sections": [
            {
                "id": "section-1",
                "title": "Market signal",
                "summary": "Discovery summary must not flow downstream.",
                "key_points": ["Discovery point."],
                "pages": [4],
            }
        ],
    }
    facts = [
        {
            "fact_id": "candidate-1",
            "provenance": {
                "discovery_candidate_id": "candidate-1",
                "discovery_evidence_ids": ["finding-1"],
            },
        },
        {
            "fact_id": "candidate-2",
            "provenance": {
                "discovery_candidate_id": "candidate-2",
                "discovery_evidence_ids": ["finding-2"],
            },
        },
    ]
    plan = {
        "report_thesis": "The report has a planning thesis.",
        "themes": [
            {"theme": "Theme 1", "priority": 1, "evidence_ids": ["finding-1"]},
            {"theme": "Theme 2", "priority": 2, "evidence_ids": ["missing"]},
            {"theme": "Theme 3", "priority": 3, "evidence_ids": ["finding-2"]},
        ],
    }

    sanitized = build_verified_fact_doc_map(source_doc_map)
    remapped = remap_editorial_plan_to_verified_facts(plan, facts)

    assert sanitized == {
        "schema_version": "verified_fact_context:1.0",
        "doc_id": "report-1",
        "title": "Report title",
        "sections": [{"id": "section-1", "title": "Market signal"}],
    }
    assert [theme["evidence_ids"] for theme in remapped["themes"]] == [
        ["verified-fact:candidate-1"],
        ["verified-fact:candidate-2"],
    ]


def test_verified_fact_context_fails_closed_when_coverage_has_one_mapped_theme():
    plan = {
        "report_thesis": "The report has a planning thesis.",
        "themes": [
            {"theme": "Theme 1", "priority": 1, "evidence_ids": ["finding-1"]},
            {"theme": "Unsupported", "priority": 2, "evidence_ids": ["missing"]},
        ],
    }
    facts = [
        {
            "fact_id": "candidate-1",
            "provenance": {"discovery_evidence_ids": ["finding-1"]},
        }
    ]

    with pytest.raises(AppError, match="Verified-fact editorial coverage"):
        remap_editorial_plan_to_verified_facts(plan, facts)


def test_canary_replay_does_not_bypass_admission_with_cached_artifacts(tmp_path):
    class CachingAnalysisStore(FakeAnalysisStore):
        def pack_path(self, request, ctx):
            del ctx
            return str(Path(request.output_dir) / "cached-artifacts.json")

        def store_pack(
            self, output_dir, report_id, pack_name, payload, ctx, report_slug=None
        ):
            del report_id, pack_name, ctx, report_slug
            path = Path(output_dir) / "cached-artifacts.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload), encoding="utf-8")
            return str(path)

    candidates = [
        _insight("f1", score=0.99, text="Retained first insight."),
        _insight("f2", score=0.98, text="Retained second insight."),
    ]
    prompt_client = CapturingPromptClient()
    analysis_store = CachingAnalysisStore()
    admission_calls = 0

    def admit(shortlisted):
        nonlocal admission_calls
        admission_calls += 1
        return _verified_admission(shortlisted, digest="c" * 64)

    def generate():
        responses = _generation_responses(candidates, plan_evidence_ids=["f1", "f2"])
        responses["summary"]["summary"]["claim_evidence_map"][0]["evidence_id"] = (
            f"verified-fact:{candidates[0]['id']}"
        )
        return generate_artifacts(
            report_id="visual-authority-cache-replay",
            report_name="Visual Authority Cache Replay",
            doc_map=_doc_map(2),
            evidence_packs=_generation_evidence(2),
            settings=_settings(tmp_path),
            md5="source-md5",
            ctx=_ctx(),
            openai_client=FakeOpenAI(responses),
            prompt_client=prompt_client,
            analysis_store=analysis_store,
            visual_authority_admitter=admit,
        )

    first = generate()
    second = generate()

    assert admission_calls == 2
    assert second["_cache"]["visual_authority_canary"]["digest"] == "c" * 64
    assert second["insights_final"] == first["insights_final"]


def test_canary_configuration_requires_expected_pdf_hash():
    with pytest.raises(AppError, match="hash-bearing source identity"):
        build_visual_authority_admitter(
            config=VisualAuthorityCanaryConfig(source_identity="report-without-hash"),
            pdf_path="report.pdf",
            default_output_dir="out",
            report_name="Report",
            evidence_packs={},
            ctx=_ctx(),
            settings=object(),
            doc_map={},
        )
