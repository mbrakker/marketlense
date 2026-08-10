# ruff: noqa: F401,F403,F405
from __future__ import annotations

from src.generators._artifact_generator.rendering import render_artifact_json_model
from src.generators._artifact_generator.storage import _validate_cover_semantics

from ._shared import *  # noqa: F401,F403


def test_assemble_artifacts_logs_topic_brief_mapping_audit(
    caplog, assert_logs_have_required_fields
) -> None:
    caplog.set_level(logging.INFO, logger="market_lense.artifact_generator")
    summary = {
        "tldr": "Grounded TLDR.",
        "card_tldr_compact": "Grounded TLDR.",
        "executive_summary": "Executive summary",
        "claim_evidence_map": [],
    }
    insights_final = [
        {
            "id": f"i{index}",
            "text": f"Insight {index}",
            "evidence_id": f"f{index}",
            "evidence": f"Evidence {index}",
            "metric": {},
            "pages": [index],
        }
        for index in range(1, 6)
    ]
    quotes_final = [
        {
            "text": "We are expanding rapidly",
            "speaker": "CEO",
            "citation": "Earnings call",
            "page": 3,
            "evidence_id": "q1",
        }
    ]
    family_status = build_artifact_family_status(
        summary=summary,
        insights_candidates=[],
        insights_final=insights_final,
        quotes_final=quotes_final,
        expert_comment="Grounded comment",
        linkedin_post="LinkedIn post",
    )

    assemble_artifacts_payload(
        report_id="r-topic-audit",
        report_name="topic-audit",
        doc_map={
            "doc_id": "r-topic-audit",
            "title": "Report",
            "sections": [
                {
                    "id": "demand-outlook",
                    "title": "Demand outlook",
                    "summary": "Demand growth is strongest in APAC.",
                    "key_points": ["APAC demand grew 12%."],
                    "pages": [2],
                }
            ],
        },
        evidence_packs=_evidence_packs(),
        toc_bundle={
            "toc_entries": [
                {
                    "section_id": "stale-section",
                    "section_title": "Old market overview",
                    "display_title": "Demand outlook",
                    "summary": "Old section summary.",
                    "key_points": ["Old point."],
                    "pages": [9],
                    "order": 1,
                }
            ],
            "toc_topics": ["Demand outlook"],
        },
        summary=summary,
        cover_semantics=_cover_semantics(),
        insights_candidates=[],
        insights_final=insights_final,
        quotes_final=quotes_final,
        expert_comment="Grounded comment",
        linkedin_post="LinkedIn post",
        source_status={"not_available": False, "reason": "", "evidence_present": True},
        family_status=family_status,
        ctx=_ctx(),
    )

    events = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == "market_lense.artifact_generator"
    ]
    audit_events = [
        event
        for event in events
        if event.get("event") == "artifact_topic_brief_mapping_audit"
    ]
    assert len(audit_events) == 1
    assert_logs_have_required_fields(audit_events)
    fields = audit_events[0]["fields"]
    assert fields["brief_count"] == 1
    assert fields["mapped_count"] == 0
    assert fields["unmapped_count"] == 1
    assert fields["issue_count"] == 1
    assert fields["status_counts"] == {"unknown_section": 1}
    assert fields["diagnostics"] == [
        {
            "topic_index": 0,
            "topic": "Demand outlook",
            "attached_section_id": "stale-section",
            "attached_section_title": "Old market overview",
            "resolved_section_id": "",
            "resolved_section_title": "",
            "current_score": 0,
            "best_section_id": "demand-outlook",
            "best_section_title": "Demand outlook",
            "best_score": 210,
            "status": "unknown_section",
            "min_score": 35,
        }
    ]


def test_generate_artifacts_backfills_missing_ids(tmp_path):
    responses = {
        "toc": {"toc_topics": ["Topic"]},
        "summary": {
            "summary": {
                "tldr": "Grounded TLDR.",
                "card_tldr_compact": "Grounded TLDR.",
                "executive_summary": "Exec",
                "claim_evidence_map": [{"claim": "Claim", "evidence": "Support"}],
            }
        },
        "insights_candidates": {
            "insights_candidates": [
                {"id": "c1", "text": "Candidate 1", "metric": {}, "pages": []}
            ]
        },
        "insights_final": {
            "insights_final": [
                {"id": "f1", "text": "Final 1", "metric": {}, "pages": []},
                {"id": "f2", "text": "Final 2", "metric": {}, "pages": []},
                {"id": "f3", "text": "Final 3", "metric": {}, "pages": []},
                {"id": "f4", "text": "Final 4", "metric": {}, "pages": []},
                {"id": "f5", "text": "Final 5", "metric": {}, "pages": []},
            ]
        },
        "quotes": {
            "quotes_final": [
                {
                    "text": "Quote",
                    "speaker": "Analyst",
                    "citation": "",
                    "page": 1,
                    "evidence_id": "q1",
                    "evidence_spans": [
                        {"evidence_id": "q1", "source_pack": "quote_candidates"}
                    ],
                }
            ]
        },
        "expert_comment": {"expert_comment": "Comment"},
        "linkedin_post": {"linkedin_post": "Post"},
    }
    fake_openai = FakeOpenAI(responses)
    payload = generate_artifacts(
        report_id="r2",
        report_name="report",
        doc_map=_doc_map(),
        evidence_packs=_evidence_packs(),
        settings=_settings(tmp_path),
        vector_store_id=None,
        ctx=_ctx(),
        openai_client=fake_openai,
        prompt_client=FakePromptClient(),
        analysis_store=FakeAnalysisStore(),
    )
    assert payload["summary"]["claim_evidence_map"] == []
    assert payload["family_status"]["summary"]["status"] == "abstained"
    assert (
        payload["family_status"]["summary"]["reason"]
        == "summary_missing_claim_evidence"
    )
    assert payload["insights_candidates"] == []
    assert payload["insights_final"] == []
    assert payload["family_status"]["insights_bundle"]["status"] == "abstained"
    assert payload["family_status"]["insights_bundle"]["policy_action"] == "regenerate"
    assert payload["quotes_final"][0]["evidence_id"] == "q1"
    assert payload["quotes_final"][0]["evidence_spans"][0]["source_pack"] == (
        "quote_candidates"
    )
    validate_schema(
        SchemaValidateRequest(
            schema_version="1.0", payload=payload, schema_name="artifacts"
        ),
        _ctx(),
    )


def test_generate_artifacts_ignores_low_text_when_vector_store(tmp_path):
    analysis_store = FakeAnalysisStore()
    responses = {
        "toc": {"toc_topics": ["Topic 1"]},
        "summary": {
            "summary": {
                "tldr": "Grounded TLDR.",
                "card_tldr_compact": "Grounded TLDR.",
                "executive_summary": "Exec",
                "claim_evidence_map": [
                    {
                        "claim": "Claim",
                        "evidence_id": "f1",
                        "evidence": "E",
                        "pages": [1],
                    }
                ],
            }
        },
        "insights_candidates": {
            "insights_candidates": [
                {
                    "id": "c1",
                    "text": "Insight",
                    "evidence_id": "f1",
                    "evidence": "E",
                    "metric": {},
                    "pages": [1],
                    "score": 0.9,
                }
            ]
        },
        "insights_final": {
            "insights_final": [
                {
                    "id": "f1",
                    "text": "Final",
                    "evidence_id": "f1",
                    "evidence": "E",
                    "metric": {},
                    "pages": [1],
                }
            ]
        },
        "quotes": {
            "quotes_final": [
                {
                    "text": "Quote",
                    "speaker": "Analyst",
                    "citation": "",
                    "page": 1,
                    "evidence_id": "q1",
                }
            ]
        },
        "expert_comment": {"expert_comment": "Comment"},
        "linkedin_post": {"linkedin_post": "Post"},
    }
    fake_openai = FakeOpenAI(responses)
    payload = generate_artifacts(
        report_id="low_text",
        report_name="report",
        doc_map=_doc_map(),
        evidence_packs=_evidence_packs(),
        settings=_settings(tmp_path, artifacts_use_vector_store=True),
        vector_store_id="vs_1",
        source_status=_low_text_status(),
        ctx=_ctx(),
        openai_client=fake_openai,
        prompt_client=FakePromptClient(),
        analysis_store=analysis_store,
    )
    assert payload["source_status"]["not_available"] is False
    assert fake_openai.requests and all(
        req[0] == "vector" for req in fake_openai.requests
    )
    validate_schema(
        SchemaValidateRequest(
            schema_version="1.0", payload=payload, schema_name="artifacts"
        ),
        _ctx(),
    )
    assert analysis_store.stored


def test_generate_artifacts_fails_when_inputs_unavailable_without_vector_store(
    tmp_path,
    assert_app_error,
):
    analysis_store = FakeAnalysisStore()

    with pytest.raises(AppError) as exc_info:
        generate_artifacts(
            report_id="low_text",
            report_name="report",
            doc_map={},
            evidence_packs={},
            settings=_settings(tmp_path),
            vector_store_id=None,
            source_status=_low_text_status(),
            ctx=_ctx(),
            openai_client=FakeOpenAI({}),
            prompt_client=FakePromptClient(),
            analysis_store=analysis_store,
        )

    assert_app_error(
        exc_info.value,
        code="artifact_inputs_unavailable",
        retryable=False,
        severity="error",
    )
    assert exc_info.value.context["report_id"] == "low_text"
    assert (
        exc_info.value.context["reason"]
        == "evidence_packs_empty,text_density_below_threshold"
    )
    assert exc_info.value.context["evidence_present"] is False
    assert analysis_store.stored == []


def test_generate_artifacts_runs_llm_steps_serially_without_executor(
    tmp_path, caplog, assert_logs_have_required_fields
):
    caplog.set_level(logging.INFO, logger="market_lense.artifact_generator")
    responses = {
        "toc": {"toc_topics": ["Topic 1", "Topic 2"]},
        "summary": {
            "summary": {
                "tldr": "Grounded TLDR.",
                "card_tldr_compact": "Grounded TLDR.",
                "executive_summary": "Exec",
                "claim_evidence_map": [
                    {
                        "claim": "Claim",
                        "evidence_id": "f1",
                        "evidence": "E",
                        "pages": [1],
                    }
                ],
            }
        },
        "insights_candidates": {
            "insights_candidates": [
                {
                    "id": "c1",
                    "text": "Insight",
                    "evidence_id": "f1",
                    "evidence": "E",
                    "metric": {},
                    "pages": [1],
                    "score": 0.9,
                }
            ]
        },
        "insights_final": {
            "insights_final": [
                {
                    "id": "f1",
                    "text": "Final",
                    "evidence_id": "f1",
                    "evidence": "E",
                    "metric": {},
                    "pages": [1],
                }
            ]
        },
        "quotes": {
            "quotes_final": [
                {
                    "text": "Quote",
                    "speaker": "Analyst",
                    "citation": "",
                    "page": 1,
                    "evidence_id": "q1",
                }
            ]
        },
        "cover_semantics": {
            "cover_semantics": {
                "evidence_shape": "trend",
                "direction": "rising",
                "geography_scope": "global",
                "evidence_density": "metric_rich",
                "domain_layer": "grid",
                "selection_reason": (
                    "Rising time-series evidence dominates the report."
                ),
            }
        },
        "expert_comment": {"expert_comment": "Grounded comment"},
        "linkedin_post": {"linkedin_post": "Post summary"},
    }
    prerequisites = {
        "insights_final": ["insights_candidates"],
        "expert_comment": ["summary", "insights_final", "quotes"],
        "linkedin_post": ["summary", "insights_final"],
    }
    fake_openai = FakeOpenAI(responses, sleep_seconds=0.05, prerequisites=prerequisites)
    prompt_client = CapturingPromptClient()
    payload = generate_artifacts(
        report_id="parallel",
        report_name="report",
        doc_map=_doc_map(),
        evidence_packs=_evidence_packs(),
        settings=_settings(tmp_path, artifacts_use_vector_store=True),
        vector_store_id="vs_1",
        categories=[
            " Consumer Behavior & Insights ",
            "Beauty",
            "Fashion",
            "Retail",
            "beauty",
        ],
        ctx=_ctx(),
        openai_client=fake_openai,
        prompt_client=prompt_client,
        analysis_store=FakeAnalysisStore(),
    )
    expert_vars = prompt_client.variables_for_namespace(
        "report_vs/artifacts/expert_comment"
    )
    assert payload["expert_comment"] == "Grounded comment"
    assert payload["linkedin_post"] == "Post summary"
    assert (
        expert_vars.get("expert_domain")
        == "Consumer Behavior & Insights, Beauty, Fashion"
    )
    requested_namespaces = {
        call["path"].removesuffix("/system").removesuffix("/user")
        for call in prompt_client.render_calls
    }
    assert "report_vs/artifacts/cover_semantics" in requested_namespaces
    cover_variables = prompt_client.variables_for_namespace(
        "report_vs/artifacts/cover_semantics"
    )
    assert set(cover_variables) == {
        "doc_map_json",
        "evidence_json",
        "summary_json",
        "insights_final_json",
        "categories_json",
        "region",
        "covered_period",
    }
    assert json.loads(cover_variables["categories_json"]) == [
        " Consumer Behavior & Insights ",
        "Beauty",
        "Fashion",
        "Retail",
        "beauty",
    ]
    assert payload["schema_version"] == "3.0"
    assert payload["cover_semantics"] == {
        "evidence_shape": "trend",
        "direction": "rising",
        "geography_scope": "global",
        "evidence_density": "metric_rich",
        "domain_layer": "grid",
        "selection_reason": "Rising time-series evidence dominates the report.",
    }
    assert fake_openai.max_in_flight == 1
    assert [req[2] for req in fake_openai.requests if req[0] == "vector"] == [
        "summary",
        "insights_candidates",
        "quotes",
        "insights_final",
        "cover_semantics",
        "expert_comment",
        "linkedin_post",
    ]
    assert len([req for req in fake_openai.requests if req[0] == "vector"]) == 7
    response_events = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == "market_lense.artifact_generator"
        and json.loads(record.message).get("event") == "artifact_model_response"
    ]
    assert len(response_events) == 7
    assert_logs_have_required_fields(response_events)


def test_generate_artifacts_strips_inline_reference_tokens_from_summary_and_linkedin(
    tmp_path,
):
    responses = {
        "toc": {"toc_topics": ["Topic 1"]},
        "summary": {
            "summary": {
                "tldr": "Grounded TLDR.",
                "card_tldr_compact": "Grounded TLDR.",
                "executive_summary": "Growth accelerated (F-001 / IC-004), especially in Q4.",
                "claim_evidence_map": [
                    {
                        "claim": "Claim",
                        "evidence_id": "f1",
                        "evidence": "E",
                        "pages": [1],
                    }
                ],
            }
        },
        "insights_candidates": {
            "insights_candidates": [
                {
                    "id": "c1",
                    "text": "Insight",
                    "evidence_id": "f1",
                    "evidence": "E",
                    "metric": {},
                    "pages": [1],
                    "score": 0.9,
                }
            ]
        },
        "insights_final": {
            "insights_final": [
                {
                    "id": "f1",
                    "text": "Final",
                    "evidence_id": "f1",
                    "evidence": "E",
                    "metric": {},
                    "pages": [1],
                }
            ]
        },
        "quotes": {
            "quotes_final": [
                {
                    "text": "Quote",
                    "speaker": "Analyst",
                    "citation": "",
                    "page": 1,
                    "evidence_id": "q1",
                }
            ]
        },
        "expert_comment": {"expert_comment": "Comment"},
        "linkedin_post": {
            "linkedin_post": "Leader takeaway (F-002 / IC-001): invest in omnichannel."
        },
    }
    payload = generate_artifacts(
        report_id="strip_refs",
        report_name="report",
        doc_map=_doc_map(),
        evidence_packs=_evidence_packs(),
        settings=_settings(tmp_path),
        vector_store_id="vs_1",
        ctx=_ctx(),
        openai_client=FakeOpenAI(responses),
        prompt_client=FakePromptClient(),
        analysis_store=FakeAnalysisStore(),
    )
    assert "(F-001 / IC-004)" not in payload["summary"]["executive_summary"]
    assert "(F-002 / IC-001)" not in payload["linkedin_post"]
    assert (
        payload["summary"]["executive_summary"]
        == "Growth accelerated, especially in Q4."
    )
    assert payload["linkedin_post"] == "Leader takeaway: invest in omnichannel."


def test_generate_artifacts_uses_vector_path_when_flag_enabled(tmp_path):
    responses = {
        "toc": {"toc_topics": ["Topic 1"]},
        "summary": {
            "summary": {
                "tldr": "Grounded TLDR.",
                "card_tldr_compact": "Grounded TLDR.",
                "executive_summary": "Exec",
                "claim_evidence_map": [
                    {
                        "claim": "Claim",
                        "evidence_id": "f1",
                        "evidence": "E",
                        "pages": [1],
                    }
                ],
            }
        },
        "insights_candidates": {
            "insights_candidates": [
                {
                    "id": "c1",
                    "text": "Insight",
                    "evidence_id": "f1",
                    "evidence": "E",
                    "metric": {},
                    "pages": [1],
                    "score": 0.9,
                }
            ]
        },
        "insights_final": {
            "insights_final": [
                {
                    "id": "f1",
                    "text": "Final",
                    "evidence_id": "f1",
                    "evidence": "E",
                    "metric": {},
                    "pages": [1],
                }
            ]
        },
        "quotes": {
            "quotes_final": [
                {
                    "text": "Quote",
                    "speaker": "Analyst",
                    "citation": "",
                    "page": 1,
                    "evidence_id": "q1",
                }
            ]
        },
        "expert_comment": {"expert_comment": "Comment"},
        "linkedin_post": {"linkedin_post": "Post"},
    }
    fake_openai = FakeOpenAI(responses)
    generate_artifacts(
        report_id="vector_enabled",
        report_name="report",
        doc_map=_doc_map(),
        evidence_packs=_evidence_packs(),
        settings=_settings(tmp_path, artifacts_use_vector_store=True),
        vector_store_id="vs_1",
        ctx=_ctx(),
        openai_client=fake_openai,
        prompt_client=FakePromptClient(),
        analysis_store=FakeAnalysisStore(),
    )
    assert len([req for req in fake_openai.requests if req[0] == "vector"]) == 7
    assert len([req for req in fake_openai.requests if req[0] == "chat"]) == 0


def test_cover_semantics_repairs_one_invalid_structured_response(tmp_path) -> None:
    class CoverRepairClient:
        def __init__(self) -> None:
            self.requests = []

        def openai_chat_json(self, request, ctx):
            del ctx
            self.requests.append(request)
            payload = (
                {
                    "cover_semantics": {
                        **_cover_semantics(),
                        "evidence_shape": "trendline",
                    }
                }
                if request.prompt_namespace == "report_vs/artifacts/cover_semantics"
                else _cover_semantics_response()
            )
            return OpenAIResponseResult(
                schema_version="1.0",
                text="{}",
                parsed_json=payload,
                input_tokens=0,
                output_tokens=0,
                tool_calls=0,
                model=request.model,
            )

    ctx = _ctx()
    client = CoverRepairClient()
    result = render_artifact_json_model(
        namespace="report_vs/artifacts/cover_semantics",
        variables={"doc_map_json": "{}"},
        settings=_settings(tmp_path),
        ctx=ctx,
        openai_client=client,
        prompt_client=FakePromptClient(),
        allow_vector_store=False,
        vector_store_id=None,
        payload_validator=lambda payload: _validate_cover_semantics(
            payload.get("cover_semantics"), ctx=ctx
        ),
        repair_namespace="report_vs/artifacts/cover_semantics_repair",
    )

    assert result["cover_semantics"] == _cover_semantics()
    assert [request.prompt_namespace for request in client.requests] == [
        "report_vs/artifacts/cover_semantics",
        "report_vs/structured_output/repair",
    ]
    assert client.requests[1].repair_attempt == 1


def test_generate_artifacts_repairs_unknown_insight_evidence_before_assembly(
    tmp_path,
) -> None:
    client = FakeOpenAI(
        [
            {
                "summary": {
                    "tldr": "Grounded TLDR.",
                    "card_tldr_compact": "Grounded TLDR.",
                    "executive_summary": "Executive summary.",
                    "claim_evidence_map": [],
                }
            },
            {
                "insights_candidates": [
                    {
                        "id": "candidate-1",
                        "text": "Candidate insight.",
                        "evidence_id": "f1",
                        "evidence": "Revenue rose.",
                        "metric": {},
                        "pages": [2],
                        "score": 0.9,
                    }
                ]
            },
            {
                "quotes_final": [
                    {
                        "text": "We are expanding rapidly",
                        "speaker": "CEO",
                        "citation": "Earnings call",
                        "page": 3,
                        "evidence_id": "q1",
                    }
                ]
            },
            {
                "insights_final": [
                    {
                        "id": "insight-1",
                        "text": "Final insight.",
                        "evidence_id": "unknown-reference",
                        "evidence": "Unsupported source.",
                        "metric": {},
                        "pages": [2],
                    }
                ]
            },
            {
                "insights_final": [
                    {
                        "id": "insight-1",
                        "text": "Final insight.",
                        "evidence_id": "f1",
                        "evidence": "Revenue rose.",
                        "metric": {},
                        "pages": [2],
                    }
                ]
            },
            _cover_semantics_response(),
            {"expert_comment": "Grounded comment."},
            {"linkedin_post": "Grounded post."},
        ]
    )

    payload = generate_artifacts(
        report_id="reference-repair",
        report_name="reference-repair",
        doc_map=_doc_map(),
        evidence_packs=_evidence_packs(),
        settings=_settings(tmp_path),
        vector_store_id="vs_1",
        ctx=_ctx(),
        openai_client=client,
        prompt_client=FakePromptClient(),
        analysis_store=FakeAnalysisStore(),
    )

    assert payload["insights_final"][0]["evidence_id"] == "f1"


__all__ = [
    "test_assemble_artifacts_logs_topic_brief_mapping_audit",
    "test_generate_artifacts_backfills_missing_ids",
    "test_generate_artifacts_ignores_low_text_when_vector_store",
    "test_generate_artifacts_fails_when_inputs_unavailable_without_vector_store",
    "test_generate_artifacts_runs_llm_steps_serially_without_executor",
    "test_generate_artifacts_strips_inline_reference_tokens_from_summary_and_linkedin",
    "test_generate_artifacts_uses_vector_path_when_flag_enabled",
    "test_cover_semantics_repairs_one_invalid_structured_response",
    "test_generate_artifacts_repairs_unknown_insight_evidence_before_assembly",
]
