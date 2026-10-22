from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.contracts.regeneration import (
    ArtifactRegenerationRequest,
    RegenerationIssue,
    RegenerationPlan,
    RegenerationTarget,
)
from src.contracts.verified_claims import (
    VERIFIED_CLAIMS_VISUAL_SCHEMA_VERSION,
    VisualClaimEvaluationResponse,
    VisualClaimEvaluationResult,
)
from src.generators._artifact_generator.generation import generate_artifacts
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
from tests._test_report_regeneration_generator import (
    _split_support_test_report_regeneration_generator as regeneration_support,
)

_FakeOpenAIClient = regeneration_support._FakeOpenAIClient
_FakePromptClient = regeneration_support._FakePromptClient
_current_artifacts = regeneration_support._current_artifacts
_regeneration_evidence_packs = regeneration_support._evidence_packs
_regeneration_settings = regeneration_support._settings
_regeneration_ctx = regeneration_support._ctx
_test_regenerate_artifacts = regeneration_support.regenerate_artifacts

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
) -> VisualClaimEvaluationResult:
    evidence_id = candidate["evidence_id"]
    page = physical_page or candidate["pages"][0]
    corrected_id = corrected_evidence_id or evidence_id
    corrected_pages = [page]
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
        corrected_evidence_ids=[corrected_id],
        corrected_evidence_spans=[
            {
                "evidence_id": corrected_id,
                "source_pack": "findings",
                "page": page,
                "text": candidate["evidence"],
            }
        ],
        corrected_metric_binding=deepcopy(corrected_metric or candidate["metric"]),
        corrected_source_binding_status=corrected_status,
        final_claim=final_claim or candidate["text"],
    )


def _response(*results: VisualClaimEvaluationResult) -> VisualClaimEvaluationResponse:
    return VisualClaimEvaluationResponse(
        schema_version=VERIFIED_CLAIMS_VISUAL_SCHEMA_VERSION,
        shadow_mode=True,
        claims=list(results),
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
    assert admitted["evidence_id"] == "finding-1"
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
    assert admission.audit["quarantined"][0]["reason"] == "corrected_binding_unbound"


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
    assert admitted["evidence_id"] == "finding-2"
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
    assert admission.audit["quarantined"][0]["reason"] == "physical_page_not_supported"


def test_generation_uses_admitted_pool_and_authority_digest(tmp_path):
    candidates = [
        _insight("f1", score=0.99, text="Retained first insight."),
        _insight("f2", score=0.98, text="Retained second insight."),
    ]
    prompt_client = CapturingPromptClient()

    def admit(shortlisted):
        assert [item["evidence_id"] for item in shortlisted] == ["f1", "f2"]
        admitted = deepcopy(shortlisted)
        admitted[0]["metric"]["timeframe"] = "2024"
        return SimpleNamespace(
            admitted_candidates=admitted,
            digest="d" * 64,
            audit={"evaluated_count": 2, "quarantined_count": 0},
        )

    payload = generate_artifacts(
        report_id="visual-authority-canary",
        report_name="Visual Authority Canary",
        doc_map=_doc_map(2),
        evidence_packs=_generation_evidence(2),
        settings=_settings(tmp_path),
        ctx=_ctx(),
        openai_client=FakeOpenAI(
            _generation_responses(candidates, plan_evidence_ids=["f1", "f2"])
        ),
        prompt_client=prompt_client,
        analysis_store=FakeAnalysisStore(),
        visual_authority_admitter=admit,
    )

    assert {item["evidence_id"] for item in payload["insights_final"]} == {"f1", "f2"}
    first_final = next(
        item for item in payload["insights_final"] if item["evidence_id"] == "f1"
    )
    assert first_final["metric"]["timeframe"] == "2024"
    assert payload["_cache"]["visual_authority_canary"]["digest"] == "d" * 64
    final_vars = prompt_client.variables_for_namespace(
        "report_vs/artifacts/insights_final"
    )
    assert final_vars["_visual_authority_digest"] == "d" * 64
    assert '"f1"' in final_vars["insights_candidates_json"]
    assert '"f2"' in final_vars["insights_candidates_json"]


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
        return SimpleNamespace(
            admitted_candidates=deepcopy(shortlisted),
            digest="c" * 64,
            audit={"evaluated_count": len(shortlisted), "quarantined_count": 0},
        )

    def generate():
        return generate_artifacts(
            report_id="visual-authority-cache-replay",
            report_name="Visual Authority Cache Replay",
            doc_map=_doc_map(2),
            evidence_packs=_generation_evidence(2),
            settings=_settings(tmp_path),
            md5="source-md5",
            ctx=_ctx(),
            openai_client=FakeOpenAI(
                _generation_responses(candidates, plan_evidence_ids=["f1", "f2"])
            ),
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


def test_scoped_regeneration_preserves_visual_authority_pool(tmp_path):
    current = _current_artifacts()
    admitted = deepcopy(current["insights_final"][:2])
    current["insights_candidates"] = deepcopy(admitted)
    current["_cache"]["visual_authority_canary"] = {
        "enabled": True,
        "digest": "e" * 64,
        "admitted_candidates": deepcopy(admitted),
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

    final_ids = {
        item["id"] for item in response.updated_artifacts["insights_final"]
    }
    candidate_ids = {
        item["id"] for item in response.updated_artifacts["insights_candidates"]
    }
    assert final_ids <= {item["id"] for item in admitted}
    assert candidate_ids <= {item["id"] for item in admitted}
    assert response.updated_artifacts["_cache"]["visual_authority_canary"][
        "digest"
    ] == "e" * 64

