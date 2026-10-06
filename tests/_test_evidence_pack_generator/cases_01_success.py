# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._support_cases import *  # noqa: F401,F403


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
    assert (
        "European retail behavior"
        in prompt_client.variables["shared_retrieval_context_json"]
    )
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
