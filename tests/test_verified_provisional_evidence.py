from __future__ import annotations

import hashlib

import pytest

from src.generators._artifact_generator.generation import generate_artifacts
from src.generators.artifact_normalization import (
    artifact_candidate_allowed_evidence_ids,
)
from src.generators.evidence_pack_generator import generate_evidence_packs
from src.generators.verified_claims_canary import (
    VisualAuthorityCanaryConfig,
    build_visual_authority_admitter,
)
from src.utils.cache_utils import sha256_json
from tests._test_artifact_generator._shared import (
    FakeAnalysisStore as ArtifactStore,
)
from tests._test_artifact_generator._shared import (
    FakeOpenAI,
)
from tests._test_artifact_generator._shared import (
    FakePromptClient as ArtifactPrompts,
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
    substantive_doc_map,
)
from tests._test_verified_claims_visual_generator.cases_01_visual import (
    _dependencies,
)
from tests._test_verified_claims_visual_generator.cases_01_visual import (
    _settings as visual_settings,
)


def test_verified_discovery_keeps_bound_claims_provisional(tmp_path):
    source = "Access Advertising Paid content 128 108 66 5.7 4.7 2.3"
    findings = [
        {
            "id": "correct",
            "text": "Access contributes 128 in forecast growth.",
            "evidence": source,
            "pages": [6],
        },
        {
            "id": "wrong",
            "text": "Access contributes 108 in forecast growth.",
            "evidence": source,
            "pages": [6],
        },
    ]
    store = FakeAnalysisStore()

    class Client(RoutedOpenAIClient):
        def openai_chat_json(self, request, ctx):
            raise AssertionError("text-only factual verdict was requested")

    packs = generate_evidence_packs(
        report_id="provisional",
        report_name="provisional.pdf",
        vector_store_id="vs",
        settings=_settings(tmp_path, evidence_pack_registry=["doc_map", "findings"]),
        ctx=_ctx(),
        source_spans=[{"id": "p6", "page": 6, "text": source}],
        visual_ambiguity_source_identity="report|pdf-sha256:" + "a" * 64,
        openai_client=Client(
            {"doc_map": substantive_doc_map(), "findings": {"findings": findings}}
        ),
        prompt_client=FakePromptClient(),
        analysis_store=store,
    )
    provisional = packs["_provisional_findings"]
    assert provisional["schema_version"] == "1.0"
    assert {entry["finding"]["id"] for entry in provisional["findings"]} == {
        "correct",
        "wrong",
    }
    assert all(
        entry["source_references"][0]["page"] == 6 for entry in provisional["findings"]
    )
    assert packs["findings"]["findings"] == []
    assert all(name != "findings" for _, name, _ in store.stored)


def test_verified_discovery_binds_distinct_source_pages(tmp_path):
    pages = [
        {"id": "p4", "page": 4, "text": "The first page describes forecast growth."},
        {
            "id": "p5",
            "page": 5,
            "text": "The second page provides the qualifying population.",
        },
    ]
    finding = {
        "id": "f1",
        "text": "A forecast applies to a population.",
        "evidence": (
            "The first page describes forecast growth. "
            "The second page provides the qualifying population."
        ),
        "pages": [4, 5],
    }
    packs = generate_evidence_packs(
        report_id="multi",
        report_name="multi.pdf",
        vector_store_id="vs",
        settings=_settings(tmp_path, evidence_pack_registry=["doc_map", "findings"]),
        ctx=_ctx(),
        source_spans=pages,
        visual_ambiguity_source_identity="report|pdf-sha256:" + "a" * 64,
        openai_client=RoutedOpenAIClient(
            {"doc_map": substantive_doc_map(), "findings": {"findings": [finding]}}
        ),
        prompt_client=FakePromptClient(),
        analysis_store=FakeAnalysisStore(),
    )
    entries = packs["_provisional_findings"]["findings"]
    assert len(entries) == 1
    assert {ref["page"] for ref in entries[0]["source_references"]} == {4, 5}


def test_verified_discovery_does_not_adjudicate_or_persist_quotes(tmp_path):
    source = "A source statement with a 40 percent forecast."

    class Client(RoutedOpenAIClient):
        def openai_chat_json(self, request, ctx):
            raise AssertionError("verified mode called text-only semantic validation")

    store = FakeAnalysisStore()
    packs = generate_evidence_packs(
        report_id="quotes",
        report_name="quotes.pdf",
        vector_store_id="vs",
        settings=_settings(
            tmp_path, evidence_pack_registry=["doc_map", "quote_candidates"]
        ),
        ctx=_ctx(),
        source_spans=[{"id": "p1", "page": 1, "text": source}],
        visual_ambiguity_source_identity="report|pdf-sha256:" + "a" * 64,
        openai_client=Client(
            {
                "doc_map": substantive_doc_map(),
                "quote_candidates": {
                    "quote_candidates": [
                        {
                            "id": "q1",
                            "text": "A fabricated 99 percent forecast.",
                            "page": 1,
                            "source": "Publisher",
                        }
                    ]
                },
            }
        ),
        prompt_client=FakePromptClient(),
        analysis_store=store,
    )
    assert not packs.get("quote_candidates", {}).get("quote_candidates")
    assert all(name != "quote_candidates" for _, name, _ in store.stored)
    provisional = packs["_provisional_findings"]["findings"]
    assert len(provisional) == 1
    assert provisional[0]["finding"]["text"] == "A fabricated 99 percent forecast."
    assert provisional[0]["source_references"][0]["page"] == 1


def test_verified_quote_discovery_is_not_reused_as_ordinary_evidence(tmp_path):
    from dataclasses import replace

    from src.contracts.prompt_family_materialization import PromptFamilyReuseResponse

    source = "Source text on a physical page."
    materialized = []
    reused = []

    def read_reuse(request, ctx):
        reused.append(request)
        return PromptFamilyReuseResponse(
            schema_version="1.0",
            reusable=False,
            reason="not_available",
            output_payload={},
            artifact_id="",
            output_hash="",
        )

    generate_evidence_packs(
        report_id="quotes",
        report_name="quotes.pdf",
        vector_store_id="vs",
        vector_store_content_hash="content-hash",
        settings=_settings(
            tmp_path, evidence_pack_registry=["doc_map", "quote_candidates"]
        ),
        ctx=replace(_ctx(), source_identity_id="source:report"),
        source_spans=[{"id": "p1", "page": 1, "text": source}],
        visual_ambiguity_source_identity="report|pdf-sha256:" + "a" * 64,
        openai_client=RoutedOpenAIClient(
            {
                "doc_map": substantive_doc_map(),
                "quote_candidates": {
                    "quote_candidates": [{"id": "q1", "text": source, "page": 1}]
                },
            }
        ),
        prompt_client=FakePromptClient(),
        analysis_store=FakeAnalysisStore(),
        prompt_family_reuse_reader=read_reuse,
        prompt_family_materializer=lambda request, ctx: materialized.append(request),
    )
    assert all(
        not request.family_id.endswith("/quote_candidates") for request in reused
    )
    assert all(
        not request.family_id.endswith("/quote_candidates") for request in materialized
    )


def test_verified_quote_hypothesis_reaches_visual_assessment(tmp_path):
    pdf = tmp_path / "source.pdf"
    pdf.write_bytes(b"source-pdf")
    identity = "report|pdf-sha256:" + hashlib.sha256(pdf.read_bytes()).hexdigest()
    source = "The source states a 40 percent forecast."
    spans = [{"id": "p1", "page": 1, "text": source}]
    packs = generate_evidence_packs(
        report_id="quotes",
        report_name="quotes.pdf",
        vector_store_id="vs",
        settings=_settings(
            tmp_path, evidence_pack_registry=["doc_map", "quote_candidates"]
        ),
        ctx=_ctx(),
        source_spans=spans,
        visual_ambiguity_source_identity=identity,
        openai_client=RoutedOpenAIClient(
            {
                "doc_map": substantive_doc_map(),
                "quote_candidates": {
                    "quote_candidates": [
                        {"id": "q1", "text": "A 99 percent forecast.", "page": 1}
                    ]
                },
            }
        ),
        prompt_client=FakePromptClient(),
        analysis_store=FakeAnalysisStore(),
    )
    provisional = packs.pop("_provisional_findings")
    requests = []
    admit = build_visual_authority_admitter(
        config=VisualAuthorityCanaryConfig(
            source_identity=identity,
            dependencies=_dependencies(
                iter([{"claim": "", "status": "unresolved", "issues": []}]),
                [],
                requests,
            ),
        ),
        pdf_path=str(pdf),
        default_output_dir=str(tmp_path),
        report_name="report",
        evidence_packs=packs,
        ctx=_ctx(),
        settings=visual_settings(tmp_path),
        doc_map={},
        provisional_evidence=provisional,
        source_spans=spans,
    )
    result = admit(
        [
            {
                "id": "candidate",
                "text": "A 99 percent forecast.",
                "evidence_id": "q1",
                "pages": [1],
            }
        ]
    )
    assert requests and requests[0].image_paths
    assert "A 99 percent forecast." in requests[0].user_prompt
    assert not result.verified_facts


def test_visual_admission_assesses_only_selected_provisional_findings(tmp_path):
    pdf = tmp_path / "source.pdf"
    pdf.write_bytes(b"source-pdf")
    identity = "report|pdf-sha256:" + hashlib.sha256(pdf.read_bytes()).hexdigest()
    text = "The chart compares forecast contributions of 40 and 60."
    entries = [
        {
            "finding": {"id": key, "text": claim, "evidence": text, "pages": [4]},
            "source_references": [
                {"evidence_id": "p4", "page": 4, "text_hash": sha256_json(text)}
            ],
        }
        for key, claim in [
            ("selected", "A contributes 40."),
            ("other", "B contributes 60."),
        ]
    ]
    requests = []
    admit = build_visual_authority_admitter(
        config=VisualAuthorityCanaryConfig(
            source_identity=identity,
            dependencies=_dependencies(
                iter([{"claim": "", "status": "unresolved", "issues": []}]),
                [],
                requests,
            ),
        ),
        pdf_path=str(pdf),
        default_output_dir=str(tmp_path),
        report_name="report",
        evidence_packs={"findings": {"findings": []}},
        ctx=_ctx(),
        settings=visual_settings(tmp_path),
        doc_map={},
        provisional_evidence={
            "schema_version": "1.0",
            "source_identity": identity,
            "findings": entries,
        },
        source_spans=[{"id": "p4", "page": 4, "text": text}],
    )
    result = admit(
        [
            {
                "id": "candidate",
                "text": "A contributes 40.",
                "evidence_id": "selected",
                "pages": [4],
            }
        ]
    )
    assert not result.verified_facts
    assert requests
    assert "A contributes 40." in requests[0].user_prompt
    assert all("B contributes 60." not in request.user_prompt for request in requests)


def test_visual_admission_preserves_distinct_claims_bound_to_same_finding(tmp_path):
    pdf = tmp_path / "source.pdf"
    pdf.write_bytes(b"source-pdf")
    identity = "report|pdf-sha256:" + hashlib.sha256(pdf.read_bytes()).hexdigest()
    text = "Source page describes two different forecast measures."
    provisional = {
        "schema_version": "1.0",
        "source_identity": identity,
        "findings": [
            {
                "finding": {
                    "id": "f1",
                    "text": "Two measures",
                    "evidence": text,
                    "pages": [4],
                },
                "source_references": [
                    {"evidence_id": "p4", "page": 4, "text_hash": sha256_json(text)}
                ],
            }
        ],
    }
    requests = []
    admit = build_visual_authority_admitter(
        config=VisualAuthorityCanaryConfig(
            source_identity=identity,
            dependencies=_dependencies(
                iter(
                    [
                        {"claim": "", "status": "unresolved", "issues": []},
                        {"claim": "", "status": "unresolved", "issues": []},
                        {"claim": "", "status": "unresolved", "issues": []},
                        {"claim": "", "status": "unresolved", "issues": []},
                    ]
                ),
                [],
                requests,
            ),
        ),
        pdf_path=str(pdf),
        default_output_dir=str(tmp_path),
        report_name="report",
        evidence_packs={"findings": {"findings": []}},
        ctx=_ctx(),
        settings=visual_settings(tmp_path),
        doc_map={},
        provisional_evidence=provisional,
        source_spans=[{"id": "p4", "page": 4, "text": text}],
    )
    result = admit(
        [
            {
                "id": "c1",
                "text": "First forecast measure.",
                "evidence_id": "f1",
                "pages": [4],
            },
            {
                "id": "c2",
                "text": "Second forecast measure.",
                "evidence_id": "f1",
                "pages": [4],
            },
        ]
    )
    assert not result.verified_facts
    assert len(requests) == 4
    assert "First forecast measure." in requests[0].user_prompt
    assert "Second forecast measure." in requests[2].user_prompt


def test_visual_admission_preserves_all_bound_pages_for_multifact_candidate(tmp_path):
    pdf = tmp_path / "source.pdf"
    pdf.write_bytes(b"source-pdf")
    identity = "report|pdf-sha256:" + hashlib.sha256(pdf.read_bytes()).hexdigest()
    first, second = "The first source statement.", "The second source statement."
    provisional = {
        "schema_version": "1.0",
        "source_identity": identity,
        "findings": [
            {
                "finding": {
                    "id": "f1",
                    "text": "First",
                    "evidence": first,
                    "pages": [4],
                },
                "source_references": [
                    {"evidence_id": "p4", "page": 4, "text_hash": sha256_json(first)}
                ],
            },
            {
                "finding": {
                    "id": "f2",
                    "text": "Second",
                    "evidence": second,
                    "pages": [5],
                },
                "source_references": [
                    {"evidence_id": "p5", "page": 5, "text_hash": sha256_json(second)}
                ],
            },
        ],
    }
    requests = []
    admit = build_visual_authority_admitter(
        config=VisualAuthorityCanaryConfig(
            source_identity=identity,
            dependencies=_dependencies(
                iter([{"claim": "", "status": "unresolved", "issues": []}] * 2),
                [],
                requests,
            ),
        ),
        pdf_path=str(pdf),
        default_output_dir=str(tmp_path),
        report_name="report",
        evidence_packs={"findings": {"findings": []}},
        ctx=_ctx(),
        settings=visual_settings(tmp_path),
        doc_map={},
        provisional_evidence=provisional,
        source_spans=[
            {"id": "p4", "page": 4, "text": first},
            {"id": "p5", "page": 5, "text": second},
        ],
    )
    result = admit(
        [
            {
                "id": "c1",
                "text": "First and second observations.",
                "evidence_id": "f1",
                "evidence_ids": ["f1", "f2"],
                "pages": [4, 5],
            }
        ]
    )
    assert not result.verified_facts
    assert len(requests[0].image_paths) == 2
    assert "physical PDF page 4" in requests[0].user_prompt
    assert "physical PDF page 5" in requests[0].user_prompt


def test_provisional_candidates_are_available_to_model_without_fidelity_promotion():
    evidence = {"findings": {"findings": []}, "evidence_fidelity": {"results": []}}
    provisional = {
        "schema_version": "1.0",
        "source_identity": "report|pdf-sha256:" + "a" * 64,
        "findings": [
            {
                "finding": {
                    "id": "f1",
                    "text": "A contributed 40.",
                    "evidence": "A B 40 60",
                    "pages": [4],
                },
                "source_references": [
                    {"evidence_id": "p4", "page": 4, "text_hash": "hash"}
                ],
            }
        ],
    }
    allowed = artifact_candidate_allowed_evidence_ids(
        evidence, require_fidelity=True, provisional_evidence=provisional
    )
    assert allowed == ["f1"]
    assert evidence["findings"]["findings"] == []
    assert evidence["evidence_fidelity"]["results"] == []


def test_generation_passes_model_selected_provisional_candidates_to_visual_admission(
    tmp_path,
):
    candidates = [_insight(f"f{i}", score=1 - i / 100) for i in range(1, 6)]
    evidence = _generation_evidence(5)
    findings = evidence["findings"]["findings"]
    provisional = {
        "schema_version": "1.0",
        "source_identity": "report|pdf-sha256:" + "a" * 64,
        "findings": [
            {
                "finding": finding,
                "source_references": [
                    {"evidence_id": f"page-{i}", "page": i + 1, "text_hash": "hash"}
                ],
            }
            for i, finding in enumerate(findings, start=1)
        ],
    }
    evidence["findings"] = {"findings": []}
    evidence["evidence_fidelity"] = {"results": []}
    selected = []

    class RecordingPrompts(ArtifactPrompts):
        def __init__(self):
            self.namespaces = []

        def load_prompt_set(self, request, ctx):
            self.namespaces.append(request.namespace)
            return super().load_prompt_set(request, ctx)

    prompts = RecordingPrompts()

    def admit(items):
        selected.extend(items)
        raise RuntimeError("visual boundary reached")

    with pytest.raises(RuntimeError, match="visual boundary reached"):
        generate_artifacts(
            report_id="provisional",
            report_name="report",
            doc_map=_doc_map(5),
            evidence_packs=evidence,
            settings=artifact_settings(tmp_path),
            ctx=artifact_ctx(),
            openai_client=FakeOpenAI(_verified_generation_responses(candidates)),
            prompt_client=prompts,
            analysis_store=ArtifactStore(),
            visual_authority_admitter=admit,
            provisional_evidence=provisional,
        )
    assert {item["evidence_id"] for item in selected} == {f"f{i}" for i in range(1, 6)}
    assert (
        "report_vs/artifacts/insights_candidates/visual_discovery" in prompts.namespaces
    )
    assert evidence["findings"]["findings"] == []


def test_generation_after_admission_uses_only_verified_fact_bindings(tmp_path):
    from tests.test_verified_claims_visual_authority_canary import _verified_admission

    candidates = [_insight(f"f{i}", score=1 - i / 100) for i in range(1, 6)]
    evidence = _generation_evidence(5)
    findings = evidence["findings"]["findings"]
    provisional = {
        "schema_version": "1.0",
        "source_identity": "report|pdf-sha256:" + "a" * 64,
        "findings": [
            {
                "finding": {**finding, "evidence": "UNVERIFIED DISCOVERY CONTEXT"},
                "source_references": [
                    {"evidence_id": f"page-{i}", "page": i + 1, "text_hash": "hash"}
                ],
            }
            for i, finding in enumerate(findings, start=1)
        ],
    }
    evidence["findings"] = {"findings": []}
    evidence["evidence_fidelity"] = {"results": []}
    responses = _verified_generation_responses(candidates)
    responses["summary"]["summary"]["claim_evidence_map"][0]["evidence_id"] = (
        f"verified-fact:{candidates[0]['id']}"
    )
    payload = generate_artifacts(
        report_id="provisional",
        report_name="report",
        doc_map=_doc_map(5),
        evidence_packs=evidence,
        settings=artifact_settings(tmp_path),
        ctx=artifact_ctx(),
        openai_client=FakeOpenAI(responses),
        prompt_client=ArtifactPrompts(),
        analysis_store=ArtifactStore(),
        provisional_evidence=provisional,
        visual_authority_admitter=lambda selected: _verified_admission(
            selected, digest="d" * 64
        ),
    )
    assert len(payload["verified_facts"]) == 5
    assert all(
        item["evidence_id"].startswith("verified-fact:")
        for item in payload["insights_final"]
    )
    assert "UNVERIFIED DISCOVERY CONTEXT" not in str(payload["insights_final"])
    assert "UNVERIFIED DISCOVERY CONTEXT" not in str(payload["summary"])


@pytest.mark.parametrize(
    "failure", ["identity", "page", "hash", "missing_span", "secondary"]
)
def test_provisional_admission_rejects_unbound_sources(tmp_path, failure):
    pdf = tmp_path / "source.pdf"
    pdf.write_bytes(b"source-pdf")
    identity = "report|pdf-sha256:" + hashlib.sha256(pdf.read_bytes()).hexdigest()
    text = "Source page text"
    entry = {
        "finding": {"id": "f1", "text": "Claim", "evidence": text, "pages": [4]},
        "source_references": [
            {"evidence_id": "p4", "page": 4, "text_hash": sha256_json(text)}
        ],
    }
    provisional = {
        "schema_version": "1.0",
        "source_identity": identity,
        "findings": [entry],
    }
    spans = [{"id": "p4", "page": 4, "text": text}]
    if failure == "identity":
        provisional["source_identity"] = "report|pdf-sha256:" + "0" * 64
    elif failure == "page":
        entry["source_references"][0]["page"] = 5
    elif failure == "hash":
        entry["source_references"][0]["text_hash"] = "0" * 64
    elif failure == "missing_span":
        spans = []
    requests = []
    admit = build_visual_authority_admitter(
        config=VisualAuthorityCanaryConfig(
            source_identity=identity, dependencies=_dependencies(iter([]), [], requests)
        ),
        pdf_path=str(pdf),
        default_output_dir=str(tmp_path),
        report_name="report",
        evidence_packs={"findings": {"findings": []}},
        ctx=_ctx(),
        settings=visual_settings(tmp_path),
        doc_map={},
        provisional_evidence=provisional,
        source_spans=spans,
    )
    candidate = {"id": "candidate", "text": "Claim", "evidence_id": "f1", "pages": [4]}
    if failure == "secondary":
        candidate["evidence_ids"] = ["f1", "missing-f2"]
    admission = admit([candidate])
    assert not admission.verified_facts
    assert admission.audit["terminal_error"] == "provisional_source_binding_invalid"
    assert admission.audit["expected_count"] == 1
    assert requests == []
