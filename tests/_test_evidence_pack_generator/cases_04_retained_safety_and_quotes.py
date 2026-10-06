# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._support_cases import *  # noqa: F401,F403


def test_generate_evidence_packs_normalizes_legacy_findings_shape(tmp_path):
    fake_openai = RoutedOpenAIClient(
        payloads_by_pack={
            "doc_map": {
                **substantive_doc_map(),
            },
            "findings": {
                "findings": [
                    {
                        "id": "finding-1",
                        "title": "Finding title",
                        "summary": "Finding summary",
                        "confidence": 0.88,
                        "evidence": [{"snippet": "Supported by evidence"}],
                        "page": "3",
                    }
                ]
            },
        }
    )
    packs = generate_evidence_packs(
        report_id="r1",
        report_name="report",
        vector_store_id="vs_1",
        settings=_settings(tmp_path),
        ctx=_ctx(),
        openai_client=fake_openai,
        prompt_client=FakePromptClient(),
        analysis_store=FakeAnalysisStore(),
    )
    finding = packs["findings"]["findings"][0]
    assert packs["findings"]["not_found_reason"] == ""
    assert finding["id"] == "finding-1"
    assert finding["text"] == "Finding summary"
    assert finding["evidence"] == "Supported by evidence"
    assert finding["confidence"] == "0.88"
    assert finding["pages"] == [3]


def test_generate_evidence_packs_persists_untrusted_findings_exclusion(tmp_path):
    from src.contracts.prompt_family_materialization import PromptFamilyReuseResponse

    analysis_store = FakeAnalysisStore()
    materialized = []
    reuse_requests = []
    unsupported_text = (
        "Survey findings reflect questionnaire respondents' views and are intended "
        "as directional guidance."
    )
    fake_openai = RoutedOpenAIClient(
        payloads_by_pack={
            "doc_map": substantive_doc_map(),
            "findings": {
                "findings": [
                    {
                        "id": "research-methodology",
                        "text": unsupported_text,
                        "pages": [64],
                    },
                    {
                        "id": "finding-supported",
                        "text": "Digital advertising grew 18% in 2025.",
                        "pages": [4],
                    },
                ]
            },
        }
    )
    source_ctx = replace(_ctx(), source_identity_id="source:canonical-report")

    def reuse_reader(request, _ctx):
        reuse_requests.append(request)
        # The prior family format may contain pre-filter findings. Treat it as
        # incompatible and require the regular generation path to run.
        if request.family_id == "report_vs/evidence_packs/findings":
            assert request.processing_version == "report_generation_checkpoint_v3"
            return PromptFamilyReuseResponse(
                schema_version="1.0",
                reusable=False,
                reason="processing_version_mismatch",
                output_payload={},
                artifact_id="legacy-unfiltered-findings",
                output_hash="legacy-hash",
            )
        return PromptFamilyReuseResponse(
            schema_version="1.0",
            reusable=False,
            reason="not_available",
            output_payload={},
            artifact_id="",
            output_hash="",
        )

    packs = generate_evidence_packs(
        report_id="r1",
        report_name="report",
        vector_store_id="vs_1",
        vector_store_content_hash="verified-vector-content",
        settings=_settings(tmp_path, evidence_pack_registry=["doc_map", "findings"]),
        ctx=source_ctx,
        openai_client=fake_openai,
        prompt_client=FakePromptClient(),
        analysis_store=analysis_store,
        prompt_family_reuse_reader=reuse_reader,
        prompt_family_materializer=lambda request, _ctx: materialized.append(request),
        source_spans=[
            {
                "id": "source:page:4",
                "page": 4,
                "text": "Digital advertising grew 18% in 2025.",
            }
        ],
    )

    persisted_findings = [
        payload
        for _, pack_name, payload in analysis_store.stored
        if pack_name == "findings"
    ]
    rejected = next(
        item
        for item in packs["evidence_fidelity"]["results"]
        if item["candidate"]["claim_id"] == "evidence:findings:research-methodology"
    )
    assert rejected["status"] == "unsupported"
    assert any(
        check["reason"] == "missing_or_unknown_evidence_reference"
        for check in rejected["checks"]
    )
    assert [item["id"] for item in packs["findings"]["findings"]] == [
        "finding-supported"
    ]
    assert [item["id"] for item in persisted_findings[-1]["findings"]] == [
        "finding-supported"
    ]
    findings_materialization = next(
        request
        for request in materialized
        if request.family_id == "report_vs/evidence_packs/findings"
    )
    assert [
        item["id"] for item in findings_materialization.output_payload["findings"]
    ] == ["finding-supported"]
    assert any(
        request.family_id == "report_vs/evidence_packs/findings"
        and request.processing_version == "report_generation_checkpoint_v3"
        for request in reuse_requests
    )


def test_legacy_unfiltered_prompt_family_cannot_restore_findings(tmp_path):
    from src.contracts.prompt_family_materialization import (
        PromptFamilyReuseRequest,
    )
    from src.services.prompt_family_materialization_service import (
        materialize_prompt_family,
        read_reusable_prompt_family,
    )

    unsupported_text = (
        "Survey findings reflect questionnaire respondents' views and are intended "
        "as directional guidance."
    )
    payloads = {
        "doc_map": substantive_doc_map(),
        "findings": {
            "findings": [
                {
                    "id": "research-methodology",
                    "text": unsupported_text,
                    "pages": [64],
                }
            ]
        },
    }
    settings = _settings(tmp_path, evidence_pack_registry=["doc_map", "findings"])
    source_ctx = replace(_ctx(), source_identity_id="source:canonical-report")
    analysis_store = FakeAnalysisStore()
    first_materializations = []
    client = RoutedOpenAIClient(payloads_by_pack=payloads)

    raw_packs = generate_evidence_packs(
        report_id="r1",
        report_name="report",
        vector_store_id="vs_1",
        vector_store_content_hash="verified-vector-content",
        settings=settings,
        ctx=source_ctx,
        openai_client=client,
        prompt_client=FakePromptClient(),
        analysis_store=analysis_store,
        prompt_family_materializer=lambda request, _ctx: first_materializations.append(
            request
        ),
    )
    generated_findings = next(
        request
        for request in first_materializations
        if request.family_id == "report_vs/evidence_packs/findings"
    )
    legacy_request = replace(
        generated_findings,
        processing_version="report_generation_checkpoint_v2",
        output_payload=raw_packs["findings"],
    )
    materialize_prompt_family(legacy_request, source_ctx)

    def to_reuse_request(request, *, processing_version):
        return PromptFamilyReuseRequest(
            schema_version=request.schema_version,
            db_path=request.db_path,
            output_dir=request.output_dir,
            report_id=request.report_id,
            report_slug=request.report_slug,
            source_id=request.source_id,
            family_id=request.family_id,
            family_schema_version=request.family_schema_version,
            processing_version=processing_version,
            prompt_content_hash=request.prompt_content_hash,
            execution_identity=request.execution_identity,
            model_provider=request.model_provider,
            model_name=request.model_name,
            model_policy_namespace=request.model_policy_namespace,
            routing_policy_version=request.routing_policy_version,
            validator_version=request.validator_version,
            relevant_input_hash=request.relevant_input_hash,
            configuration_policy_hash=request.configuration_policy_hash,
        )

    assert read_reusable_prompt_family(
        to_reuse_request(
            legacy_request,
            processing_version="report_generation_checkpoint_v2",
        ),
        source_ctx,
    ).reusable

    client_calls = []

    class CountingClient:
        def openai_respond_with_vector_store(self, request, ctx):
            client_calls.append(ctx.task_id)
            return client.openai_respond_with_vector_store(request, ctx)

    filtered_materializations = []

    def materialize_and_capture(request, ctx):
        filtered_materializations.append(request)
        return materialize_prompt_family(request, ctx)

    filtered_packs = generate_evidence_packs(
        report_id="r1",
        report_name="report",
        vector_store_id="vs_1",
        vector_store_content_hash="verified-vector-content",
        settings=settings,
        ctx=source_ctx,
        openai_client=CountingClient(),
        prompt_client=FakePromptClient(),
        analysis_store=analysis_store,
        prompt_family_reuse_reader=read_reusable_prompt_family,
        prompt_family_materializer=materialize_and_capture,
        source_spans=[
            {
                "id": "source:page:4",
                "page": 4,
                "text": "Digital advertising grew 18% in 2025.",
            }
        ],
    )

    assert any(task_id.endswith(":findings") for task_id in client_calls)
    assert filtered_packs["findings"]["findings"] == []
    persisted_findings = [
        payload
        for _, pack_name, payload in analysis_store.stored
        if pack_name == "findings"
    ]
    assert persisted_findings[-1]["findings"] == []
    filtered_request = next(
        request
        for request in filtered_materializations
        if request.family_id == "report_vs/evidence_packs/findings"
    )
    assert filtered_request.processing_version == "report_generation_checkpoint_v3"
    assert filtered_request.output_payload["findings"] == []
    findings_materializations_before_reuse = sum(
        request.family_id == "report_vs/evidence_packs/findings"
        for request in filtered_materializations
    )
    materialize_prompt_family(
        replace(filtered_request, output_payload=raw_packs["findings"]), source_ctx
    )

    client_calls.clear()
    reused_filtered_packs = generate_evidence_packs(
        report_id="r1",
        report_name="report",
        vector_store_id="vs_1",
        vector_store_content_hash="verified-vector-content",
        settings=settings,
        ctx=source_ctx,
        openai_client=CountingClient(),
        prompt_client=FakePromptClient(),
        analysis_store=analysis_store,
        prompt_family_reuse_reader=read_reusable_prompt_family,
        prompt_family_materializer=materialize_and_capture,
        source_spans=[
            {
                "id": "source:page:4",
                "page": 4,
                "text": "Digital advertising grew 18% in 2025.",
            }
        ],
    )

    assert not any(task_id.endswith(":findings") for task_id in client_calls)
    assert reused_filtered_packs["findings"]["findings"] == []
    assert reused_filtered_packs["findings"]["family_status"]["status"] == ("abstained")
    findings_materializations_after_reuse = sum(
        request.family_id == "report_vs/evidence_packs/findings"
        for request in filtered_materializations
    )
    assert findings_materializations_after_reuse == (
        findings_materializations_before_reuse + 1
    )
    filtered_request = next(
        request
        for request in reversed(filtered_materializations)
        if request.family_id == "report_vs/evidence_packs/findings"
    )
    assert filtered_request.output_payload["findings"] == []
    filtered_reuse = read_reusable_prompt_family(
        to_reuse_request(
            filtered_request,
            processing_version="report_generation_checkpoint_v3",
        ),
        source_ctx,
    )
    assert filtered_reuse.reusable
    assert filtered_reuse.output_payload["findings"] == []


def test_generate_evidence_packs_parses_limitations_json_array_from_text(tmp_path):
    fake_openai = RoutedOpenAIClient(
        payloads_by_pack={
            "doc_map": {
                **substantive_doc_map(),
            },
            "limitations": None,
        },
        text_by_pack={
            "limitations": '["Preliminary sample", "Regional bias"]',
        },
    )
    packs = generate_evidence_packs(
        report_id="r1",
        report_name="report",
        vector_store_id="vs_1",
        settings=_settings(tmp_path),
        ctx=_ctx(),
        openai_client=fake_openai,
        prompt_client=FakePromptClient(),
        analysis_store=FakeAnalysisStore(),
    )
    assert packs["limitations"]["not_found_reason"] == ""
    assert packs["limitations"]["limitations"] == [
        "Preliminary sample",
        "Regional bias",
    ]


def test_generate_evidence_packs_normalizes_quote_candidates_shape(tmp_path):
    fake_openai = RoutedOpenAIClient(
        payloads_by_pack={
            "doc_map": {
                **substantive_doc_map(),
            },
            "quote_candidates": {
                "quotes": [
                    {
                        "quote": "The industry is shifting.",
                        "citation": "Section 2",
                        "pages": ["5"],
                    },
                ]
            },
        }
    )
    packs = generate_evidence_packs(
        report_id="r1",
        report_name="report",
        vector_store_id="vs_1",
        settings=_settings(tmp_path),
        ctx=_ctx(),
        openai_client=fake_openai,
        prompt_client=FakePromptClient(),
        analysis_store=FakeAnalysisStore(),
    )
    quote = packs["quote_candidates"]["quote_candidates"][0]
    assert packs["quote_candidates"]["not_found_reason"] == ""
    assert quote["text"] == "The industry is shifting."
    assert quote["source"] == "Section 2"
    assert quote["page"] == 5


def test_generate_evidence_packs_uses_registry_subset(tmp_path):
    fake_openai = RoutedOpenAIClient(
        payloads_by_pack={
            "doc_map": {
                **substantive_doc_map(),
            },
            "findings": {
                "findings": [{"id": "f1", "text": "Finding", "evidence": "Evidence"}]
            },
        }
    )
    packs = generate_evidence_packs(
        report_id="r1",
        report_name="report",
        vector_store_id="vs_1",
        settings=_settings(tmp_path, evidence_pack_registry=["doc_map", "findings"]),
        ctx=_ctx(),
        openai_client=fake_openai,
        prompt_client=FakePromptClient(),
        analysis_store=FakeAnalysisStore(),
    )
    assert list(packs.keys()) == ["doc_map", "findings"]
    assert packs["findings"]["findings"][0]["id"] == "f1"
