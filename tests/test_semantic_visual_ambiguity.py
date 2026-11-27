import hashlib
import json
from dataclasses import replace

import pytest

from src.generators._artifact_generator.generation import generate_artifacts
from src.generators.claim_validation_generator import validate_evidence_fidelity
from src.generators.evidence_pack_generator import generate_evidence_packs
from src.generators.validation.semantic import parse_semantic_response
from src.generators.verified_claims_canary import (
    VisualAuthorityCanaryConfig,
    build_visual_authority_admitter,
)
from src.utils.cache_utils import sha256_json
from tests._test_artifact_generator._shared import (
    CapturingPromptClient,
    FakeOpenAI,
)
from tests._test_artifact_generator._shared import (
    FakeAnalysisStore as ArtifactStore,
)
from tests._test_artifact_generator._shared import (
    _ctx as artifact_ctx,
)
from tests._test_artifact_generator._shared import (
    _settings as artifact_settings,
)
from tests._test_artifact_generator.cases_05_docmap_insight_selection import (
    _doc_map,
    _generation_evidence,
    _insight,
    _verified_generation_responses,
)
from tests._test_evidence_pack_generator._shared import (
    FakeAnalysisStore,
    FakePromptClient,
    RoutedOpenAIClient,
    _ctx,
    _settings,
    semantic_response_for_request,
    substantive_doc_map,
)
from tests._test_verified_claims_visual_generator.cases_01_visual import (
    _dependencies,
)
from tests._test_verified_claims_visual_generator.cases_01_visual import (
    _settings as _visual_settings,
)


def test_visual_ambiguity_requires_explicit_consistent_model_verdict():
    outcome = parse_semantic_response(
        {
            "metrics": [
                {
                    "id": "ambiguous",
                    "supported": False,
                    "confidence": 0.8,
                    "reason": "visual association unclear",
                    "disposition": "visual_ambiguity",
                },
                {
                    "id": "contradicted",
                    "supported": False,
                    "confidence": 0.9,
                    "reason": "contradicted",
                    "disposition": "contradicted",
                },
                {
                    "id": "inconsistent",
                    "supported": True,
                    "confidence": 0.9,
                    "reason": "inconsistent",
                    "disposition": "visual_ambiguity",
                },
                {
                    "id": "legacy",
                    "supported": False,
                    "confidence": 0.8,
                    "reason": "unknown",
                },
            ],
            "quotes": [],
        }
    )

    assert outcome.metric_support["ambiguous"].disposition == "visual_ambiguity"
    assert outcome.metric_support["contradicted"].disposition == "contradicted"
    assert outcome.metric_support["inconsistent"].disposition is None
    assert outcome.metric_support["legacy"].disposition is None


def test_fidelity_keeps_explicit_visual_ambiguity_unresolved_and_bound():
    packs = {
        "findings": {
            "findings": [
                {
                    "id": "f1",
                    "text": "A is 40%",
                    "evidence": "A B 40% 60%",
                    "pages": [4],
                }
            ]
        }
    }
    source_spans = [{"id": "page-4", "page": 4, "text": "A B 40% 60%"}]
    result = validate_evidence_fidelity(
        packs,
        source_spans=source_spans,
        semantic_batch_validator=lambda candidates, sources: {
            candidates[0].claim_id: (
                False,
                "association unclear",
                "execution-1",
                "visual_ambiguity",
            )
        },
    ).results[0]
    assert result.status == "unresolved"
    assert result.semantic_classification == "visual_ambiguity"
    assert result.candidate.evidence_references[0].page == 4


@pytest.mark.parametrize("disposition", ["contradicted", "unsupported", ""])
def test_non_visual_fidelity_failures_are_not_deferred(disposition):
    packs = {
        "findings": {
            "findings": [{"id": "f1", "text": "A is 40%", "evidence": "A B 40% 60%"}]
        }
    }
    result = validate_evidence_fidelity(
        packs,
        source_spans=[{"id": "page-4", "page": 4, "text": "A B 40% 60%"}],
        semantic_batch_validator=lambda candidates, sources: {
            candidates[0].claim_id: (False, "not supported", "execution-1", disposition)
        },
    ).results[0]
    assert result.status == "unsupported"


def test_visual_ambiguity_without_execution_identity_is_not_deferred():
    packs = {
        "findings": {
            "findings": [{"id": "f1", "text": "A is 40%", "evidence": "A B 40% 60%"}]
        }
    }
    result = validate_evidence_fidelity(
        packs,
        source_spans=[{"id": "page-4", "page": 4, "text": "A B 40% 60%"}],
        semantic_batch_validator=lambda candidates, sources: {
            candidates[0].claim_id: (
                False,
                "association unclear",
                "",
                "visual_ambiguity",
            )
        },
    ).results[0]
    assert result.status == "unsupported"


def test_verified_evidence_generation_retains_source_bound_provisional_finding(
    tmp_path,
):
    source = "The chart has two series at 40% and 60%."
    finding = {
        "id": "f1",
        "text": "Series A reached 40%.",
        "evidence": source,
        "pages": [4],
    }

    class Client(RoutedOpenAIClient):
        def openai_chat_json(self, request, ctx):
            response = semantic_response_for_request(request, supported=False)
            payload = response.parsed_json
            for metric in payload["metrics"]:
                metric["disposition"] = "visual_ambiguity"
            return replace(response, parsed_json=payload, text=json.dumps(payload))

    packs = generate_evidence_packs(
        report_id="ambiguous",
        report_name="ambiguous.pdf",
        vector_store_id="vs",
        settings=_settings(tmp_path, evidence_pack_registry=["doc_map", "findings"]),
        ctx=_ctx(),
        source_spans=[{"id": "p4", "page": 4, "text": source}],
        visual_ambiguity_source_identity="report|pdf-sha256:" + "a" * 64,
        openai_client=Client(
            {"doc_map": substantive_doc_map(), "findings": {"findings": [finding]}}
        ),
        prompt_client=FakePromptClient(),
        analysis_store=FakeAnalysisStore(),
    )
    assert packs["findings"]["findings"] == []
    assert [
        item["finding"]["id"] for item in packs["_provisional_findings"]["findings"]
    ] == ["f1"]


def test_visual_findings_do_not_populate_ordinary_reuse_cache(tmp_path):
    source = "The chart has two series at 40% and 60%."
    finding = {"id": "f1", "text": "Series A reached 40%.", "evidence": source}
    materialized = []

    class Client(RoutedOpenAIClient):
        def openai_chat_json(self, request, ctx):
            response = semantic_response_for_request(request, supported=False)
            payload = response.parsed_json
            for metric in payload["metrics"]:
                metric["disposition"] = "visual_ambiguity"
            return replace(response, parsed_json=payload, text=json.dumps(payload))

    from src.contracts.prompt_family_materialization import PromptFamilyReuseResponse

    generate_evidence_packs(
        report_id="ambiguous",
        report_name="ambiguous.pdf",
        vector_store_id="vs",
        vector_store_content_hash="verified-content",
        settings=_settings(tmp_path, evidence_pack_registry=["doc_map", "findings"]),
        ctx=replace(_ctx(), source_identity_id="source:canonical-report"),
        source_spans=[{"id": "p4", "page": 4, "text": source}],
        visual_ambiguity_source_identity="report|pdf-sha256:" + "a" * 64,
        openai_client=Client(
            {"doc_map": substantive_doc_map(), "findings": {"findings": [finding]}}
        ),
        prompt_client=FakePromptClient(),
        analysis_store=FakeAnalysisStore(),
        prompt_family_reuse_reader=lambda request, ctx: PromptFamilyReuseResponse(
            schema_version="1.0",
            reusable=False,
            reason="not_available",
            output_payload={},
            artifact_id="",
            output_hash="",
        ),
        prompt_family_materializer=lambda request, ctx: materialized.append(request),
    )
    assert all(not request.family_id.endswith("/findings") for request in materialized)


def test_quarantined_finding_reaches_existing_visual_admission(tmp_path):
    pdf = tmp_path / "source.pdf"
    pdf.write_bytes(b"source-pdf")
    identity = "report|pdf-sha256:" + hashlib.sha256(pdf.read_bytes()).hexdigest()
    finding = {
        "id": "f1",
        "text": "Series A reached 40%.",
        "evidence": "A B 40% 60%",
        "pages": [4],
    }
    responses = iter(
        [
            {"claim": finding["text"], "status": "corrected", "issues": []},
            {
                "outcome": "verified",
                "diagnostics": [],
                "source_truth_notes": (
                    "The chart on page 4 associates series A with 40 percent."
                ),
                "verified_fact": {
                    "statement": finding["text"],
                    "metric": {},
                    "qualifiers": [],
                },
            },
        ]
    )
    renders, calls = [], []
    admit = build_visual_authority_admitter(
        config=VisualAuthorityCanaryConfig(
            source_identity=identity,
            dependencies=_dependencies(responses, renders, calls),
        ),
        pdf_path=str(pdf),
        default_output_dir=str(tmp_path),
        report_name="report",
        evidence_packs={"findings": {"findings": []}},
        ctx=_ctx(),
        settings=_visual_settings(tmp_path),
        doc_map={},
        visual_quarantine={
            "schema_version": "1.0",
            "source_identity": identity,
            "findings": [
                {
                    "finding": finding,
                    "source_references": [
                        {
                            "evidence_id": "p4",
                            "page": 4,
                            "text_hash": sha256_json(finding["evidence"]),
                        }
                    ],
                }
            ],
        },
        source_spans=[{"id": "p4", "page": 4, "text": finding["evidence"]}],
    )
    admission = admit([])
    assert [fact["statement"] for fact in admission.verified_facts] == [
        finding["text"]
    ], json.dumps(
        {"audit": admission.audit, "calls": len(calls), "renders": len(renders)}
    )


@pytest.mark.parametrize(
    "change", ["identity", "missing_source", "wrong_page", "wrong_hash", "missing_pack"]
)
def test_visual_quarantine_rejects_unbound_source(tmp_path, change):
    pdf = tmp_path / "source.pdf"
    pdf.write_bytes(b"source-pdf")
    identity = "report|pdf-sha256:" + hashlib.sha256(pdf.read_bytes()).hexdigest()
    finding = {"id": "f1", "text": "A reached 40%.", "evidence": "A 40%", "pages": [4]}
    ref = {"evidence_id": "p4", "page": 4, "text_hash": sha256_json("A 40%")}
    quarantine = {
        "schema_version": "1.0",
        "source_identity": identity,
        "findings": [{"finding": finding, "source_references": [ref]}],
    }
    spans = [{"id": "p4", "page": 4, "text": "A 40%"}]
    if change == "identity":
        quarantine["source_identity"] = "other|pdf-sha256:" + "a" * 64
    elif change == "missing_source":
        spans = []
    elif change == "wrong_page":
        ref["page"] = 5
    elif change == "wrong_hash":
        ref["text_hash"] = "0" * 64
    renders, calls = [], []
    admit = build_visual_authority_admitter(
        config=VisualAuthorityCanaryConfig(
            source_identity=identity,
            dependencies=_dependencies(iter([]), renders, calls),
        ),
        pdf_path=str(pdf),
        default_output_dir=str(tmp_path),
        report_name="report",
        evidence_packs={}
        if change == "missing_pack"
        else {"findings": {"findings": []}},
        ctx=_ctx(),
        settings=_visual_settings(tmp_path),
        doc_map={},
        visual_quarantine=quarantine,
        source_spans=spans,
    )
    assert admit([]).verified_facts == []
    assert not calls


def test_visual_quarantine_verified_fact_reaches_artifact_selection(tmp_path):
    pdf = tmp_path / "source.pdf"
    pdf.write_bytes(b"source-pdf")
    identity = "report|pdf-sha256:" + hashlib.sha256(pdf.read_bytes()).hexdigest()
    regular = [_insight(f"f{i}", score=1 - i / 100) for i in range(1, 5)]
    finding = {"id": "f5", "text": "Finding 5", "evidence": "Evidence 5", "pages": [6]}
    quarantined_candidate = _insight("f5", score=0.95, text="Finding 5")
    quarantined_candidate["id"] = "f5"
    evidence = _generation_evidence(5)
    evidence["findings"]["findings"] = evidence["findings"]["findings"][:4]
    evidence["evidence_fidelity"]["results"] = evidence["evidence_fidelity"]["results"][
        :4
    ]
    replies = []
    for item in [*regular, quarantined_candidate]:
        replies.extend(
            [
                {"claim": item["text"], "status": "corrected", "issues": []},
                {
                    "outcome": "verified",
                    "diagnostics": [],
                    "source_truth_notes": (
                        "The inspected page supports the stated finding."
                    ),
                    "verified_fact": {
                        "statement": item["text"],
                        "metric": {},
                        "qualifiers": [],
                    },
                },
            ]
        )
    renders, calls = [], []
    admit = build_visual_authority_admitter(
        config=VisualAuthorityCanaryConfig(
            source_identity=identity,
            dependencies=_dependencies(iter(replies), renders, calls),
        ),
        pdf_path=str(pdf),
        default_output_dir=str(tmp_path),
        report_name="report",
        evidence_packs=evidence,
        ctx=artifact_ctx(),
        settings=_visual_settings(tmp_path),
        doc_map={},
        visual_quarantine={
            "schema_version": "1.0",
            "source_identity": identity,
            "findings": [
                {
                    "finding": finding,
                    "source_references": [
                        {
                            "evidence_id": "p6",
                            "page": 6,
                            "text_hash": sha256_json("Evidence 5"),
                        }
                    ],
                }
            ],
        },
        source_spans=[{"id": "p6", "page": 6, "text": "Evidence 5"}],
    )
    responses = _verified_generation_responses([*regular, quarantined_candidate])
    responses["insights_candidates"] = {"insights_candidates": regular}
    responses["summary"]["summary"]["claim_evidence_map"][0]["evidence_id"] = (
        f"verified-fact:{regular[0]['id']}"
    )
    prompt_client = CapturingPromptClient()
    payload = generate_artifacts(
        report_id="quarantine",
        report_name="report",
        doc_map=_doc_map(5),
        evidence_packs=evidence,
        settings=artifact_settings(tmp_path),
        ctx=artifact_ctx(),
        openai_client=FakeOpenAI(responses),
        prompt_client=prompt_client,
        analysis_store=ArtifactStore(),
        visual_authority_admitter=admit,
    )
    assert any(
        item["evidence_id"] == "verified-fact:f5" for item in payload["insights_final"]
    )
    assert len(calls) >= 10
