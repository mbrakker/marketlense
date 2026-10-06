# ruff: noqa: F401,F403,F405
from __future__ import annotations

from dataclasses import replace

from ._shared import *  # noqa: F401,F403


def test_evidence_pack_family_reuses_retained_output_before_model_call(tmp_path):
    from src.contracts.prompt_family_materialization import PromptFamilyReuseResponse

    retained = substantive_doc_map()

    class FailIfCalled:
        calls = 0

        def openai_respond_with_vector_store(self, req, ctx):
            self.calls += 1
            raise AssertionError("compatible retained output must bypass the model")

    def reuse_reader(request, _ctx):
        assert request.family_id == "report_vs/doc_map"
        assert request.source_id == "source:canonical-report"
        return PromptFamilyReuseResponse(
            schema_version="1.0",
            reusable=True,
            reason="reused",
            output_payload=retained,
            artifact_id="retained-doc-map",
            output_hash="retained-hash",
        )

    client = FailIfCalled()
    packs = generate_evidence_packs(
        report_id="r1",
        report_name="report",
        vector_store_id="vs_1",
        vector_store_content_hash="verified-vector-content",
        settings=_settings(tmp_path, evidence_pack_registry=["doc_map"]),
        ctx=replace(_ctx(), source_identity_id="source:canonical-report"),
        md5="retained-source-md5",
        openai_client=client,
        prompt_client=FakePromptClient(),
        analysis_store=FakeAnalysisStore(),
        prompt_family_reuse_reader=reuse_reader,
    )

    assert client.calls == 0
    assert packs["doc_map"]["doc_id"] == retained["doc_id"]


def test_evidence_pack_missing_canonical_source_skips_retained_family_operations(
    tmp_path,
):
    retained_requests = []

    packs = generate_evidence_packs(
        report_id="r1",
        report_name="report",
        vector_store_id="vs_1",
        vector_store_content_hash="verified-vector-content",
        settings=_settings(tmp_path, evidence_pack_registry=["doc_map"]),
        ctx=_ctx(),
        md5="source-content-md5",
        openai_client=FakeOpenAIClient(substantive_doc_map()),
        prompt_client=FakePromptClient(),
        analysis_store=FakeAnalysisStore(),
        prompt_family_reuse_reader=lambda request, ctx: retained_requests.append(
            ("reuse", request.source_id)
        ),
        prompt_family_materializer=lambda request, ctx: retained_requests.append(
            ("materialize", request.source_id)
        ),
    )

    assert packs["doc_map"]["doc_id"] == "d1"
    assert retained_requests == []


def test_generate_evidence_packs_success(tmp_path):
    parsed = substantive_doc_map()
    fake_openai = FakeOpenAIClient(parsed)
    analysis_store = FakeAnalysisStore()
    packs = generate_evidence_packs(
        report_id="r1",
        report_name="report",
        vector_store_id="vs_1",
        settings=_settings(tmp_path),
        ctx=_ctx(),
        openai_client=fake_openai,
        prompt_client=FakePromptClient(),
        analysis_store=analysis_store,
    )
    assert "doc_map" in packs
    assert packs["doc_map"]["doc_id"] == "d1"
    assert packs["doc_map"]["family_status"]["status"] == "generated"
    assert packs["doc_map"]["family_status"]["policy_action"] == "keep"


def test_scope_reuses_doc_map_search_results_without_file_search(tmp_path):
    from src.contracts.openai import OpenAIFileSearchResult, OpenAIResponseResult

    class SharedRetrievalClient:
        def __init__(self):
            self.responses_requests = []
            self.chat_requests = []

        def openai_respond_with_vector_store(self, req, ctx):
            self.responses_requests.append(req)
            return OpenAIResponseResult(
                schema_version="1.0",
                text=json.dumps(substantive_doc_map()),
                parsed_json=substantive_doc_map(),
                input_tokens=5,
                output_tokens=5,
                tool_calls=1,
                model=req.model,
                file_search_results=[
                    OpenAIFileSearchResult(
                        schema_version="1.0",
                        queries=["Find scope and methods"],
                        file_id="file-report",
                        filename="report.pdf",
                        score=0.9,
                        text="The study covers European retail behavior in 2025.",
                    )
                ],
            )

        def openai_chat_json(self, req, ctx):
            self.chat_requests.append(req)
            return OpenAIResponseResult(
                schema_version="1.0",
                text=json.dumps({"scope": "European retail behavior in 2025"}),
                parsed_json={"scope": "European retail behavior in 2025"},
                input_tokens=5,
                output_tokens=5,
                tool_calls=0,
                model=req.model,
            )

    class CapturingPromptClient(FakePromptClient):
        def __init__(self):
            self.variables = {}

        def render_prompt(self, request, ctx):
            if "shared_retrieval_context_json" in request.variables:
                self.variables = dict(request.variables)
            return super().render_prompt(request, ctx)

    client = SharedRetrievalClient()
    prompt_client = CapturingPromptClient()
    packs = generate_evidence_packs(
        report_id="r1",
        report_name="report",
        vector_store_id="vs_1",
        vector_store_content_hash="verified-content-v1",
        settings=_settings(tmp_path, evidence_pack_registry=["doc_map", "scope"]),
        ctx=_ctx(),
        openai_client=client,
        prompt_client=prompt_client,
        analysis_store=FakeAnalysisStore(),
    )

    assert len(client.responses_requests) == 1
    assert client.responses_requests[0].include_file_search_results is True
    assert len(client.chat_requests) == 1
    assert "European retail behavior" in prompt_client.variables[
        "shared_retrieval_context_json"
    ]
    assert packs["scope"]["scope"] == "European retail behavior in 2025"


def test_scope_schema_repair_reuses_shared_retrieval_without_file_search(tmp_path):
    from src.contracts.openai import OpenAIFileSearchResult, OpenAIResponseResult

    class SharedRetrievalClient:
        def __init__(self):
            self.responses_requests = []
            self.chat_requests = []

        def openai_respond_with_vector_store(self, req, ctx):
            self.responses_requests.append(req)
            return OpenAIResponseResult(
                schema_version="1.0",
                text=json.dumps(substantive_doc_map()),
                parsed_json=substantive_doc_map(),
                input_tokens=5,
                output_tokens=5,
                tool_calls=1,
                model=req.model,
                file_search_results=[
                    OpenAIFileSearchResult(
                        schema_version="1.0",
                        queries=["Find the report's scope"],
                        file_id="file-report",
                        filename="report.pdf",
                        score=0.9,
                        text="The study covers European retail behavior in 2025.",
                    )
                ],
            )

        def openai_chat_json(self, req, ctx):
            self.chat_requests.append(req)
            if len(self.chat_requests) == 1:
                return OpenAIResponseResult(
                    schema_version="1.0",
                    text="not json",
                    parsed_json=None,
                    input_tokens=5,
                    output_tokens=5,
                    tool_calls=0,
                    model=req.model,
                )
            payload = {"scope": "European retail behavior in 2025"}
            return OpenAIResponseResult(
                schema_version="1.0",
                text=json.dumps(payload),
                parsed_json=payload,
                input_tokens=5,
                output_tokens=5,
                tool_calls=0,
                model=req.model,
            )

    client = SharedRetrievalClient()
    packs = generate_evidence_packs(
        report_id="r1",
        report_name="report",
        vector_store_id="vs_1",
        vector_store_content_hash="verified-content-v1",
        settings=_settings(tmp_path, evidence_pack_registry=["doc_map", "scope"]),
        ctx=_ctx(),
        openai_client=client,
        prompt_client=FakePromptClient(),
        analysis_store=FakeAnalysisStore(),
    )

    assert len(client.responses_requests) == 1
    assert len(client.chat_requests) == 2
    assert packs["scope"]["scope"] == "European retail behavior in 2025"


def test_doc_map_schema_repair_reuses_original_search_results(tmp_path):
    from src.contracts.openai import OpenAIFileSearchResult, OpenAIResponseResult

    class DocMapRepairClient:
        def __init__(self):
            self.responses_requests = []
            self.chat_requests = []

        def openai_respond_with_vector_store(self, req, ctx):
            self.responses_requests.append(req)
            return OpenAIResponseResult(
                schema_version="1.0",
                text="not json",
                parsed_json=None,
                input_tokens=5,
                output_tokens=5,
                tool_calls=1,
                model=req.model,
                file_search_results=[
                    OpenAIFileSearchResult(
                        schema_version="1.0",
                        queries=["Map report sections"],
                        file_id="file-report",
                        filename="report.pdf",
                        score=0.9,
                        text="The report examines cross-channel retail measurement.",
                    )
                ],
            )

        def openai_chat_json(self, req, ctx):
            self.chat_requests.append(req)
            payload = substantive_doc_map()
            return OpenAIResponseResult(
                schema_version="1.0",
                text=json.dumps(payload),
                parsed_json=payload,
                input_tokens=5,
                output_tokens=5,
                tool_calls=0,
                model=req.model,
            )

    client = DocMapRepairClient()
    packs = generate_evidence_packs(
        report_id="r1",
        report_name="report",
        vector_store_id="vs_1",
        vector_store_content_hash="verified-content-v1",
        settings=_settings(tmp_path, evidence_pack_registry=["doc_map"]),
        ctx=_ctx(),
        openai_client=client,
        prompt_client=FakePromptClient(),
        analysis_store=FakeAnalysisStore(),
    )

    assert len(client.responses_requests) == 1
    assert client.responses_requests[0].include_file_search_results is True
    assert len(client.chat_requests) == 1
    assert packs["doc_map"]["doc_id"] == "d1"


def test_evidence_pack_outcome_records_caller_prompt_family(tmp_path, caplog):
    """The generator, not a service default, supplies output prompt identity."""

    caplog.set_level(logging.INFO, logger="market_lense.structured_output_service")
    generate_evidence_packs(
        report_id="r1",
        report_name="report",
        vector_store_id="vs_1",
        settings=_settings(tmp_path),
        ctx=_ctx(),
        openai_client=FakeOpenAIClient(substantive_doc_map()),
        prompt_client=FakePromptClient(),
        analysis_store=FakeAnalysisStore(),
    )

    outcome = next(
        json.loads(record.message)["fields"]
        for record in caplog.records
        if '"event": "structured_output_recovery_outcome"' in record.message
    )
    assert outcome["workflow"] == "report_analysis"
    assert outcome["artifact_family"] == "doc_map"
    assert outcome["prompt_namespace"] == "report_vs/doc_map"


def test_generate_evidence_packs_creates_context_when_missing(tmp_path):
    parsed = substantive_doc_map()
    fake_openai = FakeOpenAIClient(parsed)
    packs = generate_evidence_packs(
        report_id="r1",
        report_name="report",
        vector_store_id="vs_1",
        settings=_settings(tmp_path),
        openai_client=fake_openai,
        prompt_client=FakePromptClient(),
        analysis_store=FakeAnalysisStore(),
    )

    assert packs["doc_map"]["doc_id"] == "d1"


def test_generate_evidence_packs_marks_optional_empty_pack_as_abstained(tmp_path):
    packs = generate_evidence_packs(
        report_id="r1",
        report_name="report",
        vector_store_id="vs_1",
        settings=_settings(tmp_path, evidence_pack_registry=["doc_map", "findings"]),
        ctx=_ctx(),
        openai_client=RoutedOpenAIClient(
            {
                "doc_map": {
                    **substantive_doc_map(),
                },
                "findings": {"not_found_reason": "source_has_no_findings"},
            }
        ),
        prompt_client=FakePromptClient(),
        analysis_store=FakeAnalysisStore(),
    )

    assert packs["findings"]["findings"] == []
    assert packs["findings"]["family_status"]["status"] == "abstained"
    assert packs["findings"]["family_status"]["policy_action"] == "abstain"
    assert packs["findings"]["family_status"]["reason"] == "source_has_no_findings"


def test_generate_evidence_packs_passes_doc_map_sections_to_findings_and_retains_links(
    tmp_path,
):
    prompt_client = RecordingPromptClient()
    packs = generate_evidence_packs(
        report_id="r1",
        report_name="report",
        vector_store_id="vs_1",
        settings=_settings(tmp_path, evidence_pack_registry=["doc_map", "findings"]),
        ctx=_ctx(),
        openai_client=RoutedOpenAIClient(
            {
                "doc_map": multi_section_doc_map(),
                "findings": {
                    "findings": [
                        {
                            "id": "finding-1",
                            "text": (
                                "Unified measurement connects retail media and "
                                "store outcomes."
                            ),
                            "evidence": (
                                "The report describes a shared cross-channel view."
                            ),
                            "pages": [2],
                            "section_id": "measurement-methods",
                            "section_title": "Cross-channel measurement methods",
                        },
                        {
                            "id": "finding-2",
                            "text": "Investment follows attributable outcomes.",
                            "evidence": (
                                "The outlook links buyer budgets to attribution."
                            ),
                            "pages": [8],
                            "section_id": "investment-outlook",
                            "section_title": "Investment outlook",
                        },
                    ]
                },
            }
        ),
        prompt_client=prompt_client,
        analysis_store=FakeAnalysisStore(),
    )

    assert prompt_client.findings_variables is not None
    sections = json.loads(prompt_client.findings_variables["doc_map_sections_json"])
    assert [section["id"] for section in sections] == [
        "measurement-methods",
        "investment-outlook",
    ]
    assert packs["findings"]["findings"] == [
        {
            "id": "finding-1",
            "text": "Unified measurement connects retail media and store outcomes.",
            "evidence": "The report describes a shared cross-channel view.",
            "confidence": "",
            "pages": [2],
            "section_id": "measurement-methods",
            "section_title": "Cross-channel measurement methods",
        },
        {
            "id": "finding-2",
            "text": "Investment follows attributable outcomes.",
            "evidence": "The outlook links buyer budgets to attribution.",
            "confidence": "",
            "pages": [8],
            "section_id": "investment-outlook",
            "section_title": "Investment outlook",
        },
    ]


def test_generate_evidence_packs_passes_source_temporal_relationships_to_findings(
    tmp_path,
):
    prompt_client = RecordingPromptClient()
    generate_evidence_packs(
        report_id="source-temporal-pairs",
        report_name="Source temporal pairs",
        vector_store_id="vs_1",
        source_text=(
            "2019 2020 2021 2022 2023 2024E 2028E 0:20 0:28 0:36 0:43 0:48 0:52 0:57"
        ),
        settings=_settings(tmp_path, evidence_pack_registry=["doc_map", "findings"]),
        ctx=_ctx(),
        openai_client=RoutedOpenAIClient(
            {
                "doc_map": substantive_doc_map(),
                "findings": {
                    "findings": [
                        {
                            "id": "finding-1",
                            "text": "Source-backed social-video growth.",
                            "evidence": "The source reports a social-video series.",
                            "pages": [2],
                        }
                    ]
                },
            }
        ),
        prompt_client=prompt_client,
        analysis_store=FakeAnalysisStore(),
    )

    assert prompt_client.findings_variables is not None
    assert json.loads(
        prompt_client.findings_variables["source_temporal_relationships_json"]
    ) == [
        {"period": "2019", "value": "0:20"},
        {"period": "2020", "value": "0:28"},
        {"period": "2021", "value": "0:36"},
        {"period": "2022", "value": "0:43"},
        {"period": "2023", "value": "0:48"},
        {"period": "2024e", "value": "0:52"},
        {"period": "2028e", "value": "0:57"},
    ]


def test_findings_context_retains_counterbalancing_major_docmap_sections(tmp_path):
    prompt_client = RecordingPromptClient()
    packs = generate_evidence_packs(
        report_id="counterbalanced-doc-map",
        report_name="Counterbalanced DocMap",
        vector_store_id="vs_1",
        settings=_settings(tmp_path, evidence_pack_registry=["doc_map", "findings"]),
        ctx=_ctx(),
        openai_client=RoutedOpenAIClient(
            {
                "doc_map": counterbalanced_doc_map(),
                "findings": {
                    "findings": [
                        {
                            "id": "benefit-1",
                            "text": "AI can improve operational efficiency.",
                            "evidence": "35% expect efficiency gains from AI.",
                            "pages": [4],
                            "section_id": "efficiency-value",
                            "section_title": "Efficiency and value",
                        },
                        {
                            "id": "risk-1",
                            "text": "AI-generated media needs trust safeguards.",
                            "evidence": "Trust concerns require governance controls.",
                            "pages": [12],
                            "section_id": "trust-governance",
                            "section_title": "Trust, risk, and governance",
                        },
                    ]
                },
            }
        ),
        prompt_client=prompt_client,
        analysis_store=FakeAnalysisStore(),
    )

    assert prompt_client.findings_variables is not None
    sections = json.loads(prompt_client.findings_variables["doc_map_sections_json"])
    assert [section["id"] for section in sections] == [
        "efficiency-value",
        "cost-savings",
        "trust-governance",
    ]
    assert [finding["section_id"] for finding in packs["findings"]["findings"]] == [
        "efficiency-value",
        "trust-governance",
    ]


def test_generate_evidence_packs_logs_prompt_observability_and_response_metadata(
    tmp_path, caplog, assert_logs_have_required_fields
):
    caplog.set_level(logging.INFO, logger="market_lense.evidence_pack_generator")
    packs = generate_evidence_packs(
        report_id="r1",
        report_name="report",
        vector_store_id="vs_1",
        settings=_settings(tmp_path),
        ctx=_ctx(),
        openai_client=FakeOpenAIClient(substantive_doc_map()),
        prompt_client=FakePromptClient(),
        analysis_store=FakeAnalysisStore(),
    )

    assert packs["doc_map"]["doc_id"] == "d1"
    events = []
    for record in caplog.records:
        try:
            payload = json.loads(record.message)
        except json.JSONDecodeError:
            continue
        if payload.get("event") in {
            "evidence_pack_prompt_rendered",
            "evidence_pack_response_received",
        }:
            events.append(payload)

    assert len(events) >= 2
    assert_logs_have_required_fields(events)
    rendered = next(
        event
        for event in events
        if event.get("event") == "evidence_pack_prompt_rendered"
    )
    rendered_fields = rendered["fields"]
    assert rendered_fields["namespace"] == "report_vs/doc_map"
    assert rendered_fields["system_path"] == "system"
    assert rendered_fields["user_path"] == "user"
    assert "system_prompt" not in rendered_fields
    assert "user_prompt" not in rendered_fields
    assert len(rendered_fields["execution_policy_hash"]) == 64
    assert rendered_fields["resolved_model"] == "gpt-4.1-mini"
    response = next(
        event
        for event in events
        if event.get("event") == "evidence_pack_response_received"
    )
    response_fields = response["fields"]
    assert response_fields["pack"] == "doc_map"
    assert response_fields["has_json"] is True
    assert response_fields["response_chars"] == 2
    response_hash = response_fields["response_sha256"]
    assert response_hash["redaction"] == "***REDACTED***"
    assert len(response_hash["sha256"]) == 64


def test_generate_evidence_packs_handles_missing_json(tmp_path):
    fake_openai = FakeOpenAIClient(parsed=None)
    analysis_store = FakeAnalysisStore()
    with pytest.raises(AppError) as exc_info:
        generate_evidence_packs(
            report_id="r1",
            report_name="report",
            vector_store_id="vs_1",
            settings=_settings(tmp_path),
            ctx=_ctx(),
            openai_client=fake_openai,
            prompt_client=FakePromptClient(),
            analysis_store=analysis_store,
        )
    assert exc_info.value.code == "doc_map_invalid_json"
    assert len(analysis_store.stored) == 0


def test_generate_evidence_packs_propagates_retryable_app_error(
    tmp_path, assert_app_error
):
    fake_openai = RetryableErrorOpenAIClient()
    analysis_store = FakeAnalysisStore()
    with pytest.raises(AppError) as exc_info:
        generate_evidence_packs(
            report_id="r1",
            report_name="report",
            vector_store_id="vs_1",
            settings=_settings(tmp_path),
            ctx=_ctx(),
            openai_client=fake_openai,
            prompt_client=FakePromptClient(),
            analysis_store=analysis_store,
        )
    assert_app_error(
        exc_info.value,
        code="openai_request_failed",
        retryable=True,
        severity="error",
    )
    assert fake_openai.call_count == 1
    assert len(analysis_store.stored) == 0


def test_generate_evidence_packs_rejects_doc_map_with_only_doc_id(tmp_path):
    # `doc_id` can be present while the pack is still semantically empty.
    parsed = {"doc_id": "d1", "title": "", "sections": []}
    fake_openai = FakeOpenAIClient(parsed=parsed)
    analysis_store = FakeAnalysisStore()
    with pytest.raises(AppError) as exc_info:
        generate_evidence_packs(
            report_id="r1",
            report_name="report",
            vector_store_id="vs_1",
            settings=_settings(tmp_path),
            ctx=_ctx(),
            openai_client=fake_openai,
            prompt_client=FakePromptClient(),
            analysis_store=analysis_store,
        )
    assert exc_info.value.code == "doc_map_invalid_json"
    assert len(analysis_store.stored) == 0


def test_generate_evidence_packs_recovers_identifier_only_doc_map(tmp_path):
    class PlaceholderThenSubstantiveClient:
        def __init__(self):
            self.doc_map_calls = 0

        def openai_respond_with_vector_store(self, req, ctx):
            if req.artifact_family != "doc_map":
                payload = {"not_found_reason": "fixture_insufficient_evidence"}
            else:
                self.doc_map_calls += 1
                payload = (
                    {
                        "doc_id": "report-42",
                        "title": "doc_map",
                        "summary": "report-42 | vs_42 | doc_map",
                        "sections": [
                            {
                                "id": "s1",
                                "title": "Metadata",
                                "summary": (
                                    "Key metadata fields extracted from source "
                                    "evidence."
                                ),
                                "key_points": [
                                    "report_name: report-42",
                                    "vector_store_id: vs_42",
                                ],
                                "pages": [],
                                "references": [],
                            }
                        ],
                    }
                    if self.doc_map_calls == 1
                    else {
                        "doc_id": "report-42",
                        "title": "Retail Measurement Outlook 2026",
                        "summary": (
                            "The report examines how retailers use cross-channel "
                            "measurement to improve campaign decisions."
                        ),
                        "sections": [
                            {
                                "id": "measurement-methods",
                                "title": "Cross-channel measurement methods",
                                "summary": (
                                    "Explains how campaign data connects retail media, "
                                    "stores, and ecommerce activity."
                                ),
                                "key_points": [
                                    (
                                        "Retail media requires comparable campaign "
                                        "signals."
                                    ),
                                    (
                                        "Store and ecommerce activity need a shared "
                                        "measurement view."
                                    ),
                                ],
                                "pages": [3],
                                "references": [],
                            }
                        ],
                    }
                )
            return OpenAIResponseResult(
                schema_version="1.0",
                text=json.dumps(payload),
                parsed_json=payload,
                input_tokens=1,
                output_tokens=1,
                tool_calls=0,
                model=req.model,
            )

    client = PlaceholderThenSubstantiveClient()
    packs = generate_evidence_packs(
        report_id="report-42",
        report_name="retail-measurement-outlook.pdf",
        vector_store_id="vs_42",
        settings=_settings(tmp_path),
        ctx=_ctx(),
        openai_client=client,
        prompt_client=FakePromptClient(),
        analysis_store=FakeAnalysisStore(),
    )

    assert client.doc_map_calls == 2
    assert packs["doc_map"]["title"] == "Retail Measurement Outlook 2026"
    assert packs["doc_map"]["family_status"]["status"] == "generated"


def test_generate_evidence_packs_recovers_doc_map_once_inside_shared_service(tmp_path):
    fake_openai = RetryingDocMapClient()
    analysis_store = FakeAnalysisStore()
    packs = generate_evidence_packs(
        report_id="r1",
        report_name="report",
        vector_store_id="vs_1",
        settings=_settings(tmp_path),
        ctx=_ctx(),
        openai_client=fake_openai,
        prompt_client=FakePromptClient(),
        analysis_store=analysis_store,
    )
    assert packs["doc_map"]["doc_id"] == "d1"
    assert fake_openai.call_count == 7
    assert len(analysis_store.stored) == 6


def test_generate_evidence_packs_parses_doc_map_json_from_text_fallback(tmp_path):
    fake_openai = TextFallbackDocMapClient()
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
    assert packs["doc_map"]["doc_id"] == "d1"
    assert packs["doc_map"]["title"] == "Retail Measurement Outlook"
    assert fake_openai.call_count == 6


def test_generate_evidence_packs_normalizes_docmap_wrapper(tmp_path):
    parsed = {
        "docmap": {
            "title": "Retail trends",
            "summary": "Examines changing retail demand and media performance.",
            "sections": [
                {
                    "title": "Retail demand trends",
                    "summary": (
                        "Describes how consumer demand changes across retail "
                        "categories."
                    ),
                }
            ],
        }
    }
    fake_openai = FakeOpenAIClient(parsed)
    analysis_store = FakeAnalysisStore()
    packs = generate_evidence_packs(
        report_id="r1",
        report_name="report",
        vector_store_id="vs_1",
        settings=_settings(tmp_path),
        ctx=_ctx(),
        openai_client=fake_openai,
        prompt_client=FakePromptClient(),
        analysis_store=analysis_store,
    )
    doc_map = packs["doc_map"]
    assert doc_map["doc_id"] == "r1"
    assert doc_map["title"] == "Retail trends"
    assert isinstance(doc_map["sections"], list)
    assert doc_map["sections"][0].get("id")
    assert doc_map["sections"][0]["summary"] == (
        "Describes how consumer demand changes across retail categories."
    )
    assert doc_map["sections"][0]["key_points"] == []
    assert len(analysis_store.stored) == 6


def test_generate_evidence_packs_normalizes_docmap_camelcase_wrapper(tmp_path):
    parsed = {
        "docMap": {
            "title": "THE 2026 INDUSTRY PULSE REPORT",
            "publisher": "Integral Ad Science",
            "sections": [
                {
                    "title": "Top media challenges and opportunities",
                    "summary": (
                        "Explains the measurement and quality challenges facing "
                        "digital media buyers."
                    ),
                    "page": 5,
                }
            ],
        }
    }
    fake_openai = FakeOpenAIClient(parsed)
    analysis_store = FakeAnalysisStore()
    packs = generate_evidence_packs(
        report_id="r1",
        report_name="report",
        vector_store_id="vs_1",
        settings=_settings(tmp_path),
        ctx=_ctx(),
        openai_client=fake_openai,
        prompt_client=FakePromptClient(),
        analysis_store=analysis_store,
    )
    doc_map = packs["doc_map"]
    assert doc_map["doc_id"] == "r1"
    assert doc_map["title"] == "THE 2026 INDUSTRY PULSE REPORT"
    assert doc_map["publisher"] == "Integral Ad Science"
    assert isinstance(doc_map["sections"], list)
    assert doc_map["sections"][0]["id"] == "top-media-challenges-and-opportunities"
    assert doc_map["sections"][0]["summary"] == (
        "Explains the measurement and quality challenges facing digital media buyers."
    )
    assert doc_map["sections"][0]["key_points"] == []
    assert doc_map["sections"][0]["pages"] == [5]
    assert len(analysis_store.stored) == 6


def test_generate_evidence_packs_normalizes_document_structure_shape(tmp_path):
    parsed = {
        "docmap_version": "1.0",
        "document": {
            "title": "Six Predictions for 2026 from AI to Gaming",
            "publisher": "Sensor Tower",
            "description": "Executive summary and six predictions.",
        },
        "structure": [
            {"title": "Executive Summary", "summary": "Overview of six predictions."}
        ],
    }
    fake_openai = FakeOpenAIClient(parsed)
    analysis_store = FakeAnalysisStore()
    packs = generate_evidence_packs(
        report_id="r1",
        report_name="report",
        vector_store_id="vs_1",
        settings=_settings(tmp_path),
        ctx=_ctx(),
        openai_client=fake_openai,
        prompt_client=FakePromptClient(),
        analysis_store=analysis_store,
    )
    doc_map = packs["doc_map"]
    assert doc_map["doc_id"] == "r1"
    assert doc_map["title"] == "Six Predictions for 2026 from AI to Gaming"
    assert doc_map["publisher"] == "Sensor Tower"
    assert doc_map["summary"] == "Executive summary and six predictions."
    assert isinstance(doc_map["sections"], list)
    assert doc_map["sections"][0]["id"] == "executive-summary"
    assert doc_map["sections"][0]["key_points"] == []
    assert len(analysis_store.stored) == 6


def test_generate_evidence_packs_normalizes_document_level_aliases(tmp_path):
    parsed = {
        "document_title": "Media Reactions (APAC) — Kantar 2025",
        "document_publisher": "Kantar",
        "document_summary": "Executive recap of APAC media receptivity shifts.",
        "sections": [{"title": "Introduction", "brief": "Context and study framing."}],
    }
    fake_openai = FakeOpenAIClient(parsed)
    analysis_store = FakeAnalysisStore()
    packs = generate_evidence_packs(
        report_id="r1",
        report_name="report",
        vector_store_id="vs_1",
        settings=_settings(tmp_path),
        ctx=_ctx(),
        openai_client=fake_openai,
        prompt_client=FakePromptClient(),
        analysis_store=analysis_store,
    )
    doc_map = packs["doc_map"]
    assert doc_map["doc_id"] == "r1"
    assert doc_map["title"] == "Media Reactions (APAC) — Kantar 2025"
    assert doc_map["publisher"] == "Kantar"
    assert doc_map["summary"] == "Executive recap of APAC media receptivity shifts."
    assert doc_map["sections"][0]["summary"] == "Context and study framing."
    assert len(analysis_store.stored) == 6


def test_generate_evidence_packs_normalizes_docmap_brief_aliases(tmp_path):
    parsed = {
        "docMap": {
            "title": "Retail Outlook 2026",
            "brief": (
                "A concise outlook covering demand, channels, and margin pressure."
            ),
            "sections": [
                {
                    "title": "Demand outlook",
                    "brief": "Demand growth decelerates in H2 across most regions.",
                    "keyPoints": ["Growth slowing", "H2 deceleration"],
                    "page": "2",
                },
                {
                    "title": "Methodology",
                    "overview": (
                        "The report combines survey data with transaction panels."
                    ),
                    "highlights": ["Survey + panel blend"],
                },
            ],
        }
    }
    fake_openai = FakeOpenAIClient(parsed)
    analysis_store = FakeAnalysisStore()
    packs = generate_evidence_packs(
        report_id="r1",
        report_name="report",
        vector_store_id="vs_1",
        settings=_settings(tmp_path),
        ctx=_ctx(),
        openai_client=fake_openai,
        prompt_client=FakePromptClient(),
        analysis_store=analysis_store,
    )
    doc_map = packs["doc_map"]
    assert doc_map["summary"] == (
        "A concise outlook covering demand, channels, and margin pressure."
    )
    assert doc_map["sections"][0]["summary"] == (
        "Demand growth decelerates in H2 across most regions."
    )
    assert doc_map["sections"][0]["key_points"] == [
        "Growth slowing",
        "H2 deceleration",
    ]
    assert doc_map["sections"][0]["pages"] == [2]
    assert doc_map["sections"][1]["summary"] == (
        "The report combines survey data with transaction panels."
    )
    assert doc_map["sections"][1]["key_points"] == ["Survey + panel blend"]
    assert len(analysis_store.stored) == 6


def test_generate_evidence_packs_derives_docmap_publisher_from_document_title(
    tmp_path,
):
    parsed = {
        "document_title": "Media Reactions (APAC) — Kantar 2025",
        "sections": [
            {"title": "Introduction", "summary": "Context and study framing."}
        ],
    }
    fake_openai = FakeOpenAIClient(parsed)
    analysis_store = FakeAnalysisStore()
    packs = generate_evidence_packs(
        report_id="r1",
        report_name="Kantar - Media Reactions 2025 APAC Webinar Deck_ACIG.pdf",
        vector_store_id="vs_1",
        settings=_settings(tmp_path),
        ctx=_ctx(),
        openai_client=fake_openai,
        prompt_client=FakePromptClient(),
        analysis_store=analysis_store,
    )
    doc_map = packs["doc_map"]
    assert doc_map["title"] == "Media Reactions (APAC) — Kantar 2025"
    assert doc_map["publisher"] == "Kantar"
    assert len(analysis_store.stored) == 6


def test_generate_evidence_packs_coerces_docmap_object_fields_to_schema_types(tmp_path):
    parsed = {
        "docMap": {
            "title": {"text": "Retail Outlook 2026"},
            "summary": {"text": "Document-level brief."},
            "sections": [
                {
                    "title": "Demand outlook",
                    "summary": {"text": "Demand growth decelerates in H2."},
                    "key_points": [{"text": "Growth slowing"}, {"point": "H2 shift"}],
                    "pages": ["2", "3"],
                }
            ],
        }
    }
    fake_openai = FakeOpenAIClient(parsed)
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
    doc_map = packs["doc_map"]
    assert doc_map["title"] == "Retail Outlook 2026"
    assert doc_map["summary"] == "Document-level brief."
    assert doc_map["sections"][0]["summary"] == "Demand growth decelerates in H2."
    assert doc_map["sections"][0]["key_points"] == ["Growth slowing", "H2 shift"]
    assert doc_map["sections"][0]["pages"] == [2, 3]


def test_generate_evidence_packs_warns_on_doc_map_sections_missing_summary(
    tmp_path, caplog, assert_logs_have_required_fields
):
    caplog.set_level(logging.WARNING, logger="market_lense.evidence_pack_generator")
    parsed = {
        "doc_id": "d1",
        "title": "Retail Outlook 2026",
        "sections": [
            {"id": "s1", "title": "Section 1", "summary": "", "key_points": []},
            {
                "id": "s2",
                "title": "Section 2",
                "summary": "Grounded brief",
                "key_points": ["Point A"],
            },
        ],
    }
    packs = generate_evidence_packs(
        report_id="r1",
        report_name="report",
        vector_store_id="vs_1",
        settings=_settings(tmp_path),
        ctx=_ctx(),
        openai_client=FakeOpenAIClient(parsed),
        prompt_client=FakePromptClient(),
        analysis_store=FakeAnalysisStore(),
    )
    assert packs["doc_map"]["sections"][0]["summary"] == ""
    events = []
    for record in caplog.records:
        try:
            payload = json.loads(record.message)
        except json.JSONDecodeError:
            continue
        if payload.get("event") == "doc_map_completeness_warning":
            events.append(payload)
    assert len(events) == 1
    assert_logs_have_required_fields(events)
    fields = events[0]["fields"]
    assert fields["sections_count"] == 2
    assert fields["sections_missing_summary"] == 1
    assert fields["summary_coverage_ratio"] == 0.5


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
                    }
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
    settings = _settings(
        tmp_path, evidence_pack_registry=["doc_map", "findings"]
    )
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
    assert reused_filtered_packs["findings"]["family_status"]["status"] == (
        "abstained"
    )
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


__all__ = [
    "test_evidence_pack_family_reuses_retained_output_before_model_call",
    "test_generate_evidence_packs_success",
    "test_scope_reuses_doc_map_search_results_without_file_search",
    "test_scope_schema_repair_reuses_shared_retrieval_without_file_search",
    "test_doc_map_schema_repair_reuses_original_search_results",
    "test_evidence_pack_outcome_records_caller_prompt_family",
    "test_generate_evidence_packs_creates_context_when_missing",
    "test_generate_evidence_packs_marks_optional_empty_pack_as_abstained",
    "test_generate_evidence_packs_passes_doc_map_sections_to_findings_and_retains_links",
    "test_findings_context_retains_counterbalancing_major_docmap_sections",
    "test_generate_evidence_packs_logs_prompt_observability_and_response_metadata",
    "test_generate_evidence_packs_handles_missing_json",
    "test_generate_evidence_packs_propagates_retryable_app_error",
    "test_generate_evidence_packs_rejects_doc_map_with_only_doc_id",
    "test_generate_evidence_packs_recovers_identifier_only_doc_map",
    "test_generate_evidence_packs_recovers_doc_map_once_inside_shared_service",
    "test_generate_evidence_packs_parses_doc_map_json_from_text_fallback",
    "test_generate_evidence_packs_normalizes_docmap_wrapper",
    "test_generate_evidence_packs_normalizes_docmap_camelcase_wrapper",
    "test_generate_evidence_packs_normalizes_document_structure_shape",
    "test_generate_evidence_packs_normalizes_document_level_aliases",
    "test_generate_evidence_packs_normalizes_docmap_brief_aliases",
    "test_generate_evidence_packs_derives_docmap_publisher_from_document_title",
    "test_generate_evidence_packs_coerces_docmap_object_fields_to_schema_types",
    "test_generate_evidence_packs_warns_on_doc_map_sections_missing_summary",
    "test_generate_evidence_packs_normalizes_legacy_findings_shape",
    "test_generate_evidence_packs_persists_untrusted_findings_exclusion",
    "test_legacy_unfiltered_prompt_family_cannot_restore_findings",
    "test_generate_evidence_packs_parses_limitations_json_array_from_text",
    "test_generate_evidence_packs_normalizes_quote_candidates_shape",
    "test_generate_evidence_packs_uses_registry_subset",
]
