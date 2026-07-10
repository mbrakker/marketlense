# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403

def test_load_cached_validation_rejects_schema_invalid_payload(tmp_path):
    report_name = "validation cache invalid"
    cache_path = tmp_path / slugify(report_name) / "report_analysis" / "validation.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps({"_cache": {"key": "cache-key"}}),
        encoding="utf-8",
    )

    cached = load_cached_validation(
        output_dir=str(tmp_path),
        report_id="validation-cache-invalid",
        pack_name="validation",
        report_name=report_name,
        cache_key="cache-key",
        ctx=_ctx(),
        analysis_store=None,
    )

    assert cached is None

def test_validation_parallel_branch_with_auto_context_logs_parallel_event(
    tmp_path, caplog
):
    settings = _settings(tmp_path, report_worker_limit=2)
    fake_openai = FakeOpenAI(
        semantic_payload={"metrics": [], "quotes": []},
        grounding_payload={"unsupported": []},
    )
    with caplog.at_level(logging.INFO, logger="market_lense.validation_generator"):
        validate_report(
            ValidationRequest(
                schema_version="1.0",
                report_id="r-parallel-auto",
                report=_report(),
                artifacts={"insights_final": []},
                evidence_packs={},
                vector_store_id=None,
            ),
            settings,
            ctx=None,
            prompt_client=FakePromptClient(),
            openai_client=fake_openai,
            analysis_store=FakeAnalysisStore(),
        )
    events: list[str] = []
    for record in caplog.records:
        try:
            payload = json.loads(record.getMessage())
        except json.JSONDecodeError:
            continue
        event = payload.get("event")
        if isinstance(event, str):
            events.append(event)
    assert "validation_parallel_start" in events

def test_validation_warn_policy_keeps_errors_without_data_gap(tmp_path):
    settings = _settings(tmp_path, validation_data_gap_policy="warn")
    artifacts = {
        "insights_final": [
            {
                "id": "i1",
                "text": "Insight text",
                "evidence_id": "e1",
                "evidence": "Growth was 5%",
                "metric": {"value": "10", "unit": "%", "timeframe": "2024"},
            }
        ],
        "quotes_final": [{"text": "Outside quote", "speaker": "CEO", "citation": ""}],
    }
    result = validate_report(
        ValidationRequest(
            schema_version="1.0",
            report_id="r-no-data-gap",
            report=_report(),
            artifacts=artifacts,
            evidence_packs={},
            vector_store_id=None,
        ),
        settings,
        _ctx(),
        prompt_client=FakePromptClient(),
        openai_client=FakeOpenAI({"unsupported": []}),
        analysis_store=FakeAnalysisStore(),
    )
    assert result.status == "fail"
    assert any(issue.severity == "error" for issue in result.issues)

def test_validation_fails_on_toc_integrity_breakage(tmp_path):
    settings = _settings(tmp_path)
    artifacts = {
        "toc_entries": [
            {
                "section_id": "section-4",
                "section_title": "Sentiments on GenAI: How do APAC consumers perceive AI?",
                "display_title": "Media brand ad equity",
                "summary": "GenAI summary",
                "key_points": [],
                "pages": [25],
                "order": 1,
            },
            {
                "section_id": "section-5",
                "section_title": "Implications for marketers",
                "display_title": "Sentiments on generative AI",
                "summary": "Implications summary",
                "key_points": [],
                "pages": [27],
                "order": 2,
            },
        ],
        "toc_topics": [
            "Media brand ad equity",
            "Sentiments on generative AI",
        ],
        "toc_topics_expanded": [
            {
                "topic": "Media brand ad equity",
                "summary": "GenAI summary",
                "key_points": [],
                "section_id": "section-4",
                "section_title": "Sentiments on GenAI: How do APAC consumers perceive AI?",
                "pages": [25],
            },
            {
                "topic": "Sentiments on generative AI",
                "summary": "Implications summary",
                "key_points": [],
                "section_id": "section-5",
                "section_title": "Implications for marketers",
                "pages": [27],
            },
        ],
        "summary": {
            "tldr": "",
            "executive_summary": "",
            "claim_evidence_map": [],
        },
        "insights_final": [],
        "quotes_final": [],
    }
    evidence_packs = {
        "doc_map": {
            "doc_id": "doc-1",
            "title": "Media Reactions",
            "sections": [
                {
                    "id": "section-3",
                    "title": "Media brands: How do brands interact with people?",
                    "summary": (
                        "Media-brand Ad Equity rankings with Netflix and OTT "
                        "platforms leading."
                    ),
                    "key_points": [
                        "Netflix is the #1 media brand for Ad Equity.",
                        "OTT platforms dominate the rankings.",
                    ],
                    "pages": [17, 18],
                },
                {
                    "id": "section-4",
                    "title": "Sentiments on GenAI: How do APAC consumers perceive AI?",
                    "summary": (
                        "Consumer and marketer attitudes to generative AI in "
                        "advertising."
                    ),
                    "key_points": [
                        "Consumers worry about fake content.",
                        "Marketers use generative AI for creativity and efficiency.",
                    ],
                    "pages": [25],
                },
                {
                    "id": "section-5",
                    "title": "Implications for marketers",
                    "summary": (
                        "Budget priorities, investment plans, and channel implications "
                        "for marketers."
                    ),
                    "key_points": [
                        "Online video and streaming remain top priorities.",
                    ],
                    "pages": [27],
                },
            ],
        }
    }
    result = validate_report(
        ValidationRequest(
            schema_version="1.0",
            report_id="r-topic-mapping",
            report=_report(),
            artifacts=artifacts,
            evidence_packs=evidence_packs,
            vector_store_id=None,
        ),
        settings,
        _ctx(),
        prompt_client=FakePromptClient(),
        openai_client=FakeOpenAI(
            semantic_payload={"metrics": [], "quotes": []},
            grounding_payload={"unsupported": []},
        ),
        analysis_store=FakeAnalysisStore(),
    )

    assert result.status == "fail"
    assert any(
        issue.affected_section.startswith("toc_entries") for issue in result.issues
    )
    assert any(issue.rule_id == "toc_integrity" for issue in result.issues)
    assert any(issue.repair_target == "topics" for issue in result.issues)
    assert any(issue.message.startswith("[toc_integrity]") for issue in result.issues)

def test_validation_fails_when_deterministic_toc_entries_are_missing(tmp_path):
    settings = _settings(tmp_path)
    artifacts = {
        "toc_topics": [],
        "toc_topics_expanded": [],
        "summary": {
            "tldr": "",
            "executive_summary": "",
            "claim_evidence_map": [],
        },
        "insights_final": [],
        "quotes_final": [],
    }
    evidence_packs = {
        "doc_map": {
            "doc_id": "doc-1",
            "title": "Media Reactions",
            "sections": [
                {
                    "id": "section-3",
                    "title": "Media brands: How do brands interact with people?",
                    "summary": (
                        "Media-brand Ad Equity rankings with Netflix and OTT "
                        "platforms leading."
                    ),
                    "key_points": [
                        "Netflix is the #1 media brand for Ad Equity.",
                        "OTT platforms dominate the rankings.",
                    ],
                    "pages": [17, 18],
                }
            ],
        }
    }
    result = validate_report(
        ValidationRequest(
            schema_version="1.0",
            report_id="r-topic-missing-entries",
            report=_report(),
            artifacts=artifacts,
            evidence_packs=evidence_packs,
            vector_store_id=None,
        ),
        settings,
        _ctx(),
        prompt_client=FakePromptClient(),
        openai_client=FakeOpenAI(
            semantic_payload={"metrics": [], "quotes": []},
            grounding_payload={"unsupported": []},
        ),
        analysis_store=FakeAnalysisStore(),
    )

    assert result.status == "fail"
    assert any(issue.affected_section == "toc_entries" for issue in result.issues)
    assert any(issue.rule_id == "toc_integrity" for issue in result.issues)
    assert any(issue.repair_target == "topics" for issue in result.issues)

def test_validation_rule_registry_is_deterministic():
    registry = build_validation_rule_registry()
    assert [rule.rule_id for rule in registry] == [
        "toc_integrity",
        "family_confidence",
        "claim_support",
        "artifact_quality",
        "semantic",
        "metrics",
        "quotes",
        "numbers",
        "grounding",
    ]
    assert [rule.stage for rule in registry] == [
        "bootstrap",
        "bootstrap",
        "bootstrap",
        "bootstrap",
        "bootstrap",
        "dependent",
        "dependent",
        "independent",
        "independent",
    ]

def test_validation_fails_on_regenerable_abstained_artifact_family(tmp_path):
    settings = _settings(tmp_path)
    artifacts = {
        "summary": {
            "tldr": "",
            "executive_summary": "",
            "claim_evidence_map": [],
        },
        "family_status": {
            "summary": {
                "schema_version": "1.0",
                "family": "summary",
                "source": "artifact",
                "status": "abstained",
                "confidence_score": 0.41,
                "policy_action": "regenerate",
                "reason": "summary_missing_claim_evidence",
            }
        },
    }
    result = validate_report(
        ValidationRequest(
            schema_version="1.0",
            report_id="r1",
            report=_report(),
            artifacts=artifacts,
            evidence_packs={},
            vector_store_id=None,
        ),
        settings,
        _ctx(),
        prompt_client=FakePromptClient(),
        openai_client=FakeOpenAI({"unsupported": []}),
        analysis_store=FakeAnalysisStore(),
    )

    assert result.status == "fail"
    assert any(issue.rule_id == "family_confidence" for issue in result.issues)
    assert any(issue.repair_target == "summary" for issue in result.issues)
    assert any(
        "abstained at confidence=0.41" in issue.message for issue in result.issues
    )

def test_validation_warns_on_abstained_quote_family_without_failing(tmp_path):
    settings = _settings(tmp_path)
    report = _report()
    report.quote = Quote(text="", author="Unknown")
    artifacts = {
        "summary": {
            "tldr": "TLDR",
            "executive_summary": "Exec",
            "claim_evidence_map": [],
        },
        "insights_final": [],
        "quotes_final": [],
        "family_status": {
            "quotes": {
                "schema_version": "1.0",
                "family": "quotes",
                "source": "artifact",
                "status": "abstained",
                "confidence_score": 0.65,
                "policy_action": "regenerate",
                "reason": "quotes_missing_verbatim_source",
            }
        },
    }
    result = validate_report(
        ValidationRequest(
            schema_version="1.0",
            report_id="r1",
            report=report,
            artifacts=artifacts,
            evidence_packs={},
            vector_store_id=None,
        ),
        settings,
        _ctx(),
        prompt_client=FakePromptClient(),
        openai_client=FakeOpenAI({"unsupported": []}),
        analysis_store=FakeAnalysisStore(),
    )

    assert result.status == "pass"
    assert result.severity == "warning"
    assert any(
        issue.rule_id == "family_confidence"
        and issue.affected_section == "quotes"
        and issue.severity == "warning"
        for issue in result.issues
    )

def test_validation_fails_when_summary_claim_is_missing_span_support(tmp_path):
    settings = _settings(tmp_path)
    artifacts = {
        "summary": {
            "tldr": "TLDR",
            "executive_summary": "Exec",
            "claim_evidence_map": [
                {"claim": "Grounded claim", "evidence_id": "f1", "evidence": "Support"}
            ],
        },
        "insights_final": [],
        "quotes_final": [],
        "expert_comment": "",
        "linkedin_post": "",
    }
    evidence_packs = {
        "findings": {
            "schema_version": "1.0",
            "findings": [{"id": "f1", "text": "Finding", "evidence": "Support"}],
        }
    }
    result = validate_report(
        ValidationRequest(
            schema_version="1.0",
            report_id="r1",
            report=_report(),
            artifacts=artifacts,
            evidence_packs=evidence_packs,
            vector_store_id=None,
        ),
        settings,
        _ctx(),
        prompt_client=FakePromptClient(),
        openai_client=FakeOpenAI({"unsupported": []}),
        analysis_store=FakeAnalysisStore(),
    )

    assert result.status == "fail"
    assert any(issue.rule_id == "claim_support" for issue in result.issues)
    assert any(issue.repair_target == "summary" for issue in result.issues)

def test_validation_warns_on_soft_artifact_abstention_and_info_evidence_pack_abstention(
    tmp_path,
):
    settings = _settings(tmp_path)
    report = ReportPayload(
        tldr="TLDR",
        title="Report",
        insights=[],
        quote=Quote(text="Quoted text", author="Analyst"),
        figure=Figure(title="Figure", evidence="Fig"),
        commentary="Commentary",
        source="Source",
    )
    artifacts = {
        "summary": {
            "tldr": "TLDR",
            "executive_summary": "Exec",
            "claim_evidence_map": [
                {
                    "claim": "Claim",
                    "evidence_id": "f1",
                    "evidence": "Evidence",
                    "evidence_spans": [
                        {"evidence_id": "f1", "source_pack": "findings", "page": 2}
                    ],
                }
            ],
        },
        "insights_final": [],
        "quotes_final": [
            {
                "id": "q1",
                "text": "Quoted text",
                "speaker": "Analyst",
                "citation": "Quoted text",
                "evidence_spans": [
                    {
                        "evidence_id": "q1",
                        "source_pack": "quote_candidates",
                        "page": 1,
                    }
                ],
            }
        ],
        "expert_comment": "",
        "linkedin_post": "",
        "family_status": {
            "expert_comment": {
                "schema_version": "1.0",
                "family": "expert_comment",
                "source": "artifact",
                "status": "abstained",
                "confidence_score": 0.52,
                "policy_action": "abstain",
                "reason": "generated_text_missing",
            }
        },
    }
    evidence_packs = {
        "findings": {
            "schema_version": "1.0",
            "findings": [{"id": "f1", "text": "Finding", "evidence": "Evidence"}],
            "family_status": {
                "schema_version": "1.0",
                "family": "findings",
                "source": "evidence_pack",
                "status": "abstained",
                "confidence_score": 0.0,
                "policy_action": "abstain",
                "reason": "insufficient_pack_content",
            },
        }
    }
    result = validate_report(
        ValidationRequest(
            schema_version="1.0",
            report_id="r1",
            report=report,
            artifacts=artifacts,
            evidence_packs=evidence_packs,
            vector_store_id=None,
        ),
        settings,
        _ctx(),
        prompt_client=FakePromptClient(),
        openai_client=FakeOpenAI(
            {"metrics": [], "quotes": []},
            semantic_payload={
                "metrics": [],
                "quotes": [
                    {
                        "id": "q1",
                        "supported": True,
                        "confidence": 0.86,
                        "reason": "Exact match",
                    }
                ],
            },
            grounding_payload={"unsupported": []},
        ),
        analysis_store=FakeAnalysisStore(),
    )

    assert result.status == "pass"
    assert result.severity == "warning"
    assert any(
        issue.rule_id == "family_confidence" and issue.severity == "warning"
        for issue in result.issues
    )
    assert any(
        issue.rule_id == "family_confidence" and issue.severity == "info"
        for issue in result.issues
    )
    assert any("intentionally omitted" in issue.message for issue in result.issues)

def test_validation_failures_include_rule_identity_prefix(tmp_path):
    settings = _settings(tmp_path)
    artifacts = {
        "insights_final": [
            {
                "id": "i1",
                "text": "Insight text",
                "evidence_id": "e1",
                "evidence": "Growth was 5%",
                "metric": {"value": "10", "unit": "%", "timeframe": "2024"},
            }
        ],
        "quotes_final": [
            {"id": "q1", "text": "Outside quote", "speaker": "CEO", "citation": ""}
        ],
        "expert_comment": "We expect revenue to reach 99 soon.",
    }
    result = validate_report(
        ValidationRequest(
            schema_version="1.0",
            report_id="r-rule-prefix",
            report=_report(),
            artifacts=artifacts,
            evidence_packs={},
            vector_store_id=None,
        ),
        settings,
        _ctx(),
        prompt_client=FakePromptClient(),
        openai_client=FakeOpenAI(
            semantic_payload={"metrics": [], "quotes": []},
            grounding_payload={
                "unsupported": [
                    {
                        "section": "expert_comment",
                        "text": "We expect revenue to reach 99 soon.",
                        "reason": "No evidence",
                    }
                ]
            },
        ),
        analysis_store=FakeAnalysisStore(),
    )
    assert any(issue.message.startswith("[metrics]") for issue in result.issues)
    assert any(issue.message.startswith("[quotes]") for issue in result.issues)
    assert any(issue.message.startswith("[numbers]") for issue in result.issues)
    assert any(issue.message.startswith("[grounding]") for issue in result.issues)

def test_validation_propagates_retryable_semantic_error(tmp_path, assert_app_error):
    settings = _settings(tmp_path, report_worker_limit=1)
    artifacts = {
        "insights_final": [
            {
                "id": "i1",
                "text": "Insight text",
                "evidence_id": "e1",
                "evidence": "Revenue grew 5%",
                "metric": {"value": "5", "unit": "%", "timeframe": "2024"},
            }
        ]
    }

    with pytest.raises(AppError) as err:
        validate_report(
            ValidationRequest(
                schema_version="1.0",
                report_id="r-semantic-retry",
                report=_report(),
                artifacts=artifacts,
                evidence_packs={},
                vector_store_id=None,
            ),
            settings,
            _ctx(),
            prompt_client=FakePromptClient(),
            openai_client=FailingOpenAI(
                semantic_exc=AppError(
                    code="openai_chat_failed",
                    message="semantic retry",
                    retryable=True,
                )
            ),
            analysis_store=FakeAnalysisStore(),
        )

    assert_app_error(
        err.value,
        code="openai_chat_failed",
        retryable=True,
        severity="error",
    )

def test_validation_propagates_retryable_grounding_error(tmp_path, assert_app_error):
    settings = _settings(
        tmp_path,
        report_worker_limit=1,
        validation_grounding_use_vector_store=True,
    )
    artifacts = {
        "insights_final": [
            {
                "id": "i1",
                "text": "Insight text",
                "evidence_id": "e1",
                "evidence": "Revenue grew 5%",
                "metric": {"value": "5", "unit": "%", "timeframe": "2024"},
            }
        ]
    }

    with pytest.raises(AppError) as err:
        validate_report(
            ValidationRequest(
                schema_version="1.0",
                report_id="r-grounding-retry",
                report=_report(),
                artifacts=artifacts,
                evidence_packs={},
                vector_store_id="vs_1",
            ),
            settings,
            _ctx(),
            prompt_client=FakePromptClient(),
            openai_client=FailingOpenAI(
                grounding_exc=AppError(
                    code="openai_request_failed",
                    message="grounding retry",
                    retryable=True,
                )
            ),
            analysis_store=FakeAnalysisStore(),
        )

    assert_app_error(
        err.value,
        code="openai_request_failed",
        retryable=True,
        severity="error",
    )

__all__ = [
    "test_load_cached_validation_rejects_schema_invalid_payload",
    "test_validation_parallel_branch_with_auto_context_logs_parallel_event",
    "test_validation_warn_policy_keeps_errors_without_data_gap",
    "test_validation_fails_on_toc_integrity_breakage",
    "test_validation_fails_when_deterministic_toc_entries_are_missing",
    "test_validation_rule_registry_is_deterministic",
    "test_validation_fails_on_regenerable_abstained_artifact_family",
    "test_validation_warns_on_abstained_quote_family_without_failing",
    "test_validation_fails_when_summary_claim_is_missing_span_support",
    "test_validation_warns_on_soft_artifact_abstention_and_info_evidence_pack_abstention",
    "test_validation_failures_include_rule_identity_prefix",
    "test_validation_propagates_retryable_semantic_error",
    "test_validation_propagates_retryable_grounding_error",
]
