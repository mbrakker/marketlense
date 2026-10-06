# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._support_cases import *  # noqa: F401,F403


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
