# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403


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
    "test_generate_evidence_packs_success",
    "test_generate_evidence_packs_creates_context_when_missing",
    "test_generate_evidence_packs_marks_optional_empty_pack_as_abstained",
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
    "test_generate_evidence_packs_parses_limitations_json_array_from_text",
    "test_generate_evidence_packs_normalizes_quote_candidates_shape",
    "test_generate_evidence_packs_uses_registry_subset",
]
