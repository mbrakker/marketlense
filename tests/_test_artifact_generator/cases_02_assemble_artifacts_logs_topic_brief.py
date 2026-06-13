# ruff: noqa: F401,F403,F405
from __future__ import annotations

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


def test_generate_artifacts_normalizes_malformed_evidence_ids(tmp_path):
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
                        "evidence_id": "F1,F2",
                        "evidence": "Revenue +10%",
                        "pages": [2],
                    }
                ],
            }
        },
        "insights_candidates": {
            "insights_candidates": [
                {
                    "id": "c1",
                    "text": "Candidate 1",
                    "evidence_id": "['F2', 'F3']",
                    "evidence": "E2",
                    "metric": {},
                    "pages": [3],
                    "score": 0.9,
                },
                {
                    "id": "c2",
                    "text": "Candidate 2",
                    "evidence_id": "MISSING_REF",
                    "evidence": "E-missing",
                    "metric": {},
                    "pages": [4],
                    "score": 0.6,
                },
            ]
        },
        "insights_final": {
            "insights_final": [
                {
                    "id": "i1",
                    "text": "Final 1",
                    "evidence_id": "F3/F4",
                    "evidence": "E3",
                    "metric": {},
                    "pages": [4],
                },
                {
                    "id": "i2",
                    "text": "Final 2",
                    "evidence_id": "missing_final",
                    "evidence": "E-missing",
                    "metric": {},
                    "pages": [5],
                },
                {
                    "id": "i3",
                    "text": "Final 3",
                    "evidence_id": "f5",
                    "evidence": "E5",
                    "metric": {},
                    "pages": [6],
                },
                {
                    "id": "i4",
                    "text": "Final 4",
                    "evidence_id": "F1",
                    "evidence": "E1",
                    "metric": {},
                    "pages": [2],
                },
                {
                    "id": "i5",
                    "text": "Final 5",
                    "evidence_id": "['f2']",
                    "evidence": "E2",
                    "metric": {},
                    "pages": [3],
                },
            ]
        },
        "quotes": {
            "quotes_final": [
                {
                    "text": "We are expanding rapidly",
                    "speaker": "CEO",
                    "citation": "Earnings call",
                    "page": 3,
                    "evidence_id": "quote_1",
                }
            ]
        },
        "expert_comment": {"expert_comment": "Grounded comment"},
        "linkedin_post": {"linkedin_post": "Post summary"},
    }
    payload = generate_artifacts(
        report_id="r_malformed",
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

    assert payload["summary"]["claim_evidence_map"][0]["evidence_id"] == "f1"
    assert payload["insights_candidates"][0]["evidence_id"] == "f2"
    assert payload["insights_candidates"][1]["evidence_id"] == ""
    assert payload["insights_final"][0]["evidence_id"] == "f3"
    assert payload["insights_final"][1]["evidence_id"] == ""
    assert payload["insights_final"][2]["evidence_id"] == "f5"
    assert payload["insights_final"][3]["evidence_id"] == "f1"
    assert payload["insights_final"][4]["evidence_id"] == "f2"
    assert payload["quotes_final"][0]["evidence_id"] == "q1"

    validate_schema(
        SchemaValidateRequest(
            schema_version="1.0", payload=payload, schema_name="artifacts"
        ),
        _ctx(),
    )


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


def test_generate_artifacts_runs_llm_steps_serially_without_executor(tmp_path):
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
    assert fake_openai.max_in_flight == 1
    assert [req[2] for req in fake_openai.requests if req[0] == "vector"] == [
        "summary",
        "insights_candidates",
        "quotes",
        "insights_final",
        "expert_comment",
        "linkedin_post",
    ]
    assert len([req for req in fake_openai.requests if req[0] == "vector"]) == 6


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
    assert len([req for req in fake_openai.requests if req[0] == "vector"]) == 6
    assert len([req for req in fake_openai.requests if req[0] == "chat"]) == 0


__all__ = [
    "test_assemble_artifacts_logs_topic_brief_mapping_audit",
    "test_generate_artifacts_normalizes_malformed_evidence_ids",
    "test_generate_artifacts_backfills_missing_ids",
    "test_generate_artifacts_ignores_low_text_when_vector_store",
    "test_generate_artifacts_fails_when_inputs_unavailable_without_vector_store",
    "test_generate_artifacts_runs_llm_steps_serially_without_executor",
    "test_generate_artifacts_strips_inline_reference_tokens_from_summary_and_linkedin",
    "test_generate_artifacts_uses_vector_path_when_flag_enabled",
]
