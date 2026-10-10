# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._split_support_cases_01_validation_flags_metric_and_quote import *  # noqa: F401,F403


def test_validation_flags_metric_and_quote_mismatches(tmp_path):
    settings = _settings(tmp_path)
    artifacts = {
        "insights_final": [
            {
                "id": "i1",
                "text": "Insight text",
                "evidence_id": "e1",
                "evidence": "Growth was 5%",
                "metric": {"value": "10", "unit": "%", "timeframe": "2024"},
            },
        ],
        "quotes_final": [{"text": "Outside quote", "speaker": "CEO", "citation": ""}],
    }
    fake_openai = FakeOpenAI({"unsupported": []})
    analysis_store = FakeAnalysisStore()
    result = validate_report(
        ValidationRequest(
            schema_version="1.0",
            report_id="r1",
            report=_report(),
            artifacts=artifacts,
            evidence_packs={},
            vector_store_id=None,
            validation_mode="inline_deterministic",
        ),
        settings,
        _ctx(),
        prompt_client=FakePromptClient(),
        openai_client=fake_openai,
        analysis_store=analysis_store,
    )
    assert result.status == "fail"
    assert result.severity == "error"
    assert any("Metric value" in issue.message for issue in result.issues)
    assert any("Quote not verbatim" in issue.message for issue in result.issues)
    assert analysis_store.stored and analysis_store.stored[0][2] == "validation"


def test_validation_blocks_more_than_doubled_when_evidence_only_doubles(tmp_path):
    artifacts = {
        "insights_final": [
            {
                "id": "i1",
                "text": "Adoption more than doubled from the prior period.",
                "evidence_id": "e1",
                "evidence": "Adoption increased from 10% to 20%.",
                "metric": {"value": "20", "unit": "%", "timeframe": "2024"},
            }
        ]
    }
    result = validate_report(
        ValidationRequest(
            schema_version="1.0",
            report_id="r-double",
            report=_report(),
            artifacts=artifacts,
            evidence_packs={},
            vector_store_id=None,
            validation_mode="inline_deterministic",
        ),
        _settings(tmp_path),
        _ctx(),
        prompt_client=FakePromptClient(),
        openai_client=FakeOpenAI({"unsupported": []}),
        analysis_store=FakeAnalysisStore(),
    )

    assert result.status == "fail"
    assert any("more than doubled" in issue.message for issue in result.issues)


def test_number_validation_preserves_ordered_source_period_value_pairs() -> None:
    fixture_path = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "editorial_relationships"
        / "social_video_ordered_metrics.json"
    )
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    artifacts = {
        "summary": {
            "tldr": fixture["swapped_value_claim"],
            "executive_summary": fixture["swapped_value_claim"],
        },
        "expert_comment": fixture["swapped_value_claim"],
        "linkedin_post": fixture["valid_claim"],
        "insights_final": [
            {
                "id": "social-time",
                "text": fixture["swapped_value_claim"],
            }
        ],
        "key_figures": [
            {"figure": "0:48 in 2024E"},
        ],
    }

    issues = validate_new_numbers(
        artifacts=artifacts,
        insights=[],
        report=_report(),
        evidence_texts=[fixture["evidence"]],
        evidence_windows=[],
        source_text=fixture["source_ordered_text"],
    )

    failed_sections = {issue.affected_section for issue in issues}
    assert "summary.tldr" in failed_sections
    assert "summary.executive_summary" in failed_sections
    assert "expert_comment" in failed_sections
    assert "insights:social-time.text" in failed_sections
    assert "key_figures:1.figure" in failed_sections
    assert "linkedin_post" not in failed_sections


def test_number_validation_does_not_treat_decimal_year_pairs_as_ratios() -> None:
    sentence = (
        "Global finance app day 0 sessions per user declined from 1.52 in 2024 "
        "to 1.48 in 2025."
    )
    evidence = "Global finance app day 0 sessions per user declined from 1.52 to 1.48."

    issues = validate_new_numbers(
        artifacts={"expert_comment": sentence},
        insights=[],
        report=_report(),
        evidence_texts=[evidence],
        evidence_windows=[],
        source_text=evidence,
    )

    assert not issues


def test_validation_uses_retained_source_text_for_ordered_period_value_pairs(
    tmp_path,
) -> None:
    fixture_path = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "editorial_relationships"
        / "social_video_ordered_metrics.json"
    )
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    result = validate_report(
        ValidationRequest(
            schema_version="1.0",
            report_id="social-video",
            report=_report(),
            artifacts={
                "summary": {"tldr": fixture["swapped_value_claim"]},
                "insights_final": [],
            },
            evidence_packs={},
            source_text=fixture["source_ordered_text"],
            validation_mode="inline_deterministic",
        ),
        _settings(tmp_path),
        _ctx(),
        prompt_client=FakePromptClient(),
        openai_client=FakeOpenAI({"unsupported": []}),
        analysis_store=FakeAnalysisStore(),
    )

    assert any(
        issue.rule_id == "numbers"
        and issue.affected_section == "summary.tldr"
        and "2024e with 0:52" in issue.message
        for issue in result.issues
    )


def test_validation_cache_changes_when_retained_source_text_changes(tmp_path) -> None:
    from src.generators.validation.cache import validation_cache_meta

    common = {
        "schema_version": "1.0",
        "report_id": "social-video-cache",
        "report": _report(),
        "artifacts": {"insights_final": []},
        "evidence_packs": {},
    }
    early = validation_cache_meta(
        request=ValidationRequest(
            **common,
            source_text="2023 2024E 0:48 0:52",
        ),
        settings=_settings(tmp_path),
        prompt_client=FakePromptClient(),
        ctx=_ctx(),
        md5="source-md5",
        grounding_retrieval_mode="chat",
    )
    corrected = validation_cache_meta(
        request=ValidationRequest(
            **common,
            source_text="2023 2024E 0:47 0:52",
        ),
        settings=_settings(tmp_path),
        prompt_client=FakePromptClient(),
        ctx=_ctx(),
        md5="source-md5",
        grounding_retrieval_mode="chat",
    )

    assert early["inputs_sha256"] != corrected["inputs_sha256"]


def test_validation_accepts_paraphrased_metrics_and_quotes(tmp_path):
    settings = _settings(tmp_path)
    artifacts = {
        "insights_final": [
            {
                "id": "i1",
                "text": "Revenue grew year over year",
                "evidence_id": "e1",
                "evidence": (
                    "The company reported ten percent year-over-year revenue growth."
                ),
                "metric": {"value": "10%", "unit": "%", "timeframe": "2024"},
            },
        ],
        "quotes_final": [
            {
                "id": "q1",
                "text": "The CEO noted a year-over-year increase of ten percent.",
                "speaker": "CEO",
                "citation": "The CEO noted a year-over-year increase of ten pct.",
                "is_paraphrase": True,
                "evidence_id": "quote-source",
            },
        ],
    }
    evidence_packs = {
        "findings": {
            "findings": [
                {
                    "id": "e1",
                    "evidence": (
                        "The company reported ten percent year-over-year revenue "
                        "growth."
                    ),
                }
            ]
        },
        "quote_candidates": {
            "quote_candidates": [
                {
                    "id": "quote-source",
                    "text": "The CEO noted a year-over-year increase of ten pct.",
                }
            ]
        },
    }
    semantic_payload = {
        "metrics": [
            {
                "id": "i1",
                "supported": True,
                "confidence": 0.82,
                "reason": "Paraphrase matches evidence",
            }
        ],
        "quotes": [
            {
                "id": "q1",
                "supported": True,
                "confidence": 0.81,
                "reason": "Meaning preserved",
            }
        ],
    }
    grounding_payload = {
        "unsupported": [],
        "checks": [
            {
                "item_id": (
                    "retained_claim:7cabb7fe2be9624f33ad15d82e0598f"
                    "56a5dc508fe84fa8ec68423a3f83364c6"
                ),
                "section": "insights:i1.text",
                "text": "Revenue grew year over year",
                "classification": "factual_claim",
                "entailment_outcome": "entailed",
                "proposition_status": "compatible",
                "protected_facts": {
                    dimension: {
                        "claim_value": None,
                        "evidence_value": None,
                        "status": "unknown",
                    }
                    for dimension in PROTECTED_FACT_DIMENSIONS
                },
                "reason": "Grounding comparison completed.",
            }
        ],
    }
    fake_openai = FakeOpenAI(
        semantic_payload=semantic_payload, grounding_payload=grounding_payload
    )
    analysis_store = FakeAnalysisStore()
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
        openai_client=fake_openai,
        analysis_store=analysis_store,
    )
    assert result.status == "pass"
    assert result.severity in {"info", "pass"}
    assert all(issue.severity != "error" for issue in result.issues)
    assert any("semantically supported" in issue.message for issue in result.issues)
    assert analysis_store.stored and analysis_store.stored[0][2] == "validation"


def test_validation_detects_new_numbers_and_grounding(tmp_path):
    settings = _settings(tmp_path)
    artifacts = {
        "insights_final": [
            {
                "id": "i1",
                "text": "Insight 1",
                "evidence_id": "e1",
                "evidence": "Revenue up 5%",
                "metric": {"value": "5", "unit": "%", "timeframe": "2024"},
            }
        ],
        "expert_comment": "We expect revenue to reach 99 soon.",
    }
    fake_openai = FakeOpenAI(
        semantic_payload={"metrics": [], "quotes": []},
        grounding_payload={
            "unsupported": [
                {
                    "section": "expert_comment",
                    "text": "We expect",
                    "reason": "No evidence",
                }
            ]
        },
    )
    analysis_store = FakeAnalysisStore()
    result = validate_report(
        ValidationRequest(
            schema_version="1.0",
            report_id="r2",
            report=_report(),
            artifacts=artifacts,
            evidence_packs={},
            vector_store_id=None,
        ),
        settings,
        _ctx(),
        prompt_client=FakePromptClient(),
        openai_client=fake_openai,
        analysis_store=analysis_store,
    )
    assert result.status == "fail"
    assert any(issue.affected_section == "expert_comment" for issue in result.issues)
    assert any("No evidence" in issue.message for issue in result.issues)
    assert any("Number" in issue.message for issue in result.issues)


def test_inline_validation_records_deferred_grounding_without_model_client(tmp_path):
    settings = _settings(tmp_path)
    analysis_store = FakeAnalysisStore()
    result = validate_report(
        ValidationRequest(
            schema_version="1.0",
            report_id="inline-r1",
            report=_report(),
            artifacts={
                "summary": {
                    "tldr": "Revenue growth reached 10%.",
                    "card_tldr_compact": "Revenue growth reached 10%.",
                    "executive_summary": "Revenue growth reached 10% in 2026.",
                    "claim_evidence_map": [],
                },
                "insights_final": [],
                "quotes_final": [],
                "expert_comment": "Revenue growth reached 10% in 2026.",
                "linkedin_post": "Revenue growth reached 10% in 2026.",
            },
            evidence_packs={
                "findings": {
                    "findings": [
                        {
                            "id": "f1",
                            "evidence": "Revenue growth reached 10% in 2026.",
                        }
                    ]
                }
            },
            vector_store_id=None,
            validation_mode="inline_deterministic",
        ),
        settings,
        _ctx(),
        prompt_client=FakePromptClient(),
        openai_client=None,
        analysis_store=analysis_store,
    )

    assert any(
        issue.rule_id == "deferred_grounding_required" for issue in result.issues
    )
    assert analysis_store.stored[0][3]["issues"] != []


def test_claim_support_rejects_strong_claims_backed_only_by_weak_evidence(tmp_path):
    settings = _settings(tmp_path)
    result = validate_report(
        ValidationRequest(
            schema_version="1.0",
            report_id="quality-claim-r1",
            report=_report(),
            artifacts={
                "summary": {
                    "tldr": "Growth reached 42%.",
                    "card_tldr_compact": "Growth reached 42%.",
                    "executive_summary": (
                        "Growth reached 42% and proves durable demand."
                    ),
                    "claim_evidence_map": [
                        {
                            "claim": "Growth reached 42% and proves durable demand.",
                            "evidence_id": "f1",
                            "evidence_spans": [
                                {
                                    "evidence_id": "f1",
                                    "source_pack": "findings",
                                    "text": "Analyst commentary suggests growth.",
                                }
                            ],
                        }
                    ],
                },
                "insights_final": [],
                "quotes_final": [],
                "expert_comment": "",
                "linkedin_post": "",
            },
            evidence_packs={
                "findings": {
                    "findings": [
                        {
                            "id": "f1",
                            "evidence": "Analyst commentary suggests growth.",
                            "quality_grade": "weak_paraphrase",
                        }
                    ]
                }
            },
            vector_store_id=None,
            validation_mode="inline_deterministic",
        ),
        settings,
        _ctx(),
        prompt_client=FakePromptClient(),
        openai_client=None,
        analysis_store=FakeAnalysisStore(),
    )

    assert result.status == "fail"
    issue = next(
        issue
        for issue in result.issues
        if "weak_evidence_strong_claim" in issue.message
    )
    assert issue.rule_id == "claim_support"
    assert issue.severity == "error"
    assert issue.repair_target == "summary"
    assert issue.entity_id == "f1"


def test_claim_support_allows_contrast_scoped_only_with_weak_evidence(tmp_path):
    """A contrast-scoped exclusivity term does not overstate a weak-evidence claim.

    Regression: "managed ... rather than treated only as messaging" blocked an
    Emplifi summary claim that faithfully paraphrased the referenced strategy
    section's explicit recommendation.
    """

    settings = _settings(tmp_path)
    result = validate_report(
        ValidationRequest(
            schema_version="1.0",
            report_id="quality-claim-r2",
            report=_report(),
            artifacts={
                "summary": {
                    "tldr": "Brands manage authenticity across touchpoints.",
                    "card_tldr_compact": "Brands manage authenticity day to day.",
                    "executive_summary": (
                        "Authenticity works as an operating model across "
                        "customer touchpoints."
                    ),
                    "claim_evidence_map": [
                        {
                            "claim": (
                                "Authenticity should be managed across "
                                "interconnected customer touchpoints rather than "
                                "treated only as messaging."
                            ),
                            "evidence_id": "f1",
                            "evidence_spans": [
                                {
                                    "evidence_id": "f1",
                                    "source_pack": "findings",
                                    "text": (
                                        "The strategy section recommends making "
                                        "authenticity an operating model rather "
                                        "than a messaging tactic."
                                    ),
                                }
                            ],
                        }
                    ],
                },
                "insights_final": [],
                "quotes_final": [],
                "expert_comment": "",
                "linkedin_post": "",
            },
            evidence_packs={
                "findings": {
                    "findings": [
                        {
                            "id": "f1",
                            "evidence": (
                                "The strategy section recommends making "
                                "authenticity an operating model rather than a "
                                "messaging tactic."
                            ),
                            "quality_grade": "section_summary",
                        }
                    ]
                }
            },
            vector_store_id=None,
            validation_mode="inline_deterministic",
        ),
        settings,
        _ctx(),
        prompt_client=FakePromptClient(),
        openai_client=None,
        analysis_store=FakeAnalysisStore(),
    )

    assert not any(issue.rule_id == "claim_support" for issue in result.issues)


def test_claim_support_contrast_scope_boundaries():
    """Only contrast-governed exclusivity terms lose their strong-claim force."""

    assert _has_unscoped_strong_language(
        "Brands should use only first-party data rather than third-party cookies."
    )
    assert _has_unscoped_strong_language(
        "Growth reached 42 percent rather than the expected 5 percent."
    )
    assert _has_unscoped_strong_language(
        "Rather than treating it as messaging. It will only strengthen trust."
    )
    assert not _has_unscoped_strong_language(
        "Authenticity should be managed across touchpoints rather than treated "
        "only as messaging."
    )
    assert not _has_unscoped_strong_language(
        "Brands should invest in owned reviews, not only in paid ratings."
    )


def test_artifact_quality_flags_banned_generic_copy_and_allows_technical_terms(
    tmp_path,
):
    settings = _settings(tmp_path)
    result = validate_report(
        ValidationRequest(
            schema_version="1.0",
            report_id="quality-r1",
            report=_report(),
            artifacts={
                "summary": {
                    "tldr": "This report highlights a rapidly evolving landscape.",
                    "card_tldr_compact": "Revenue growth reached 10%.",
                    "executive_summary": (
                        "Financial leverage and robust standard errors frame the "
                        "market risk estimate."
                    ),
                    "claim_evidence_map": [],
                },
                "insights_final": [
                    {
                        "id": "i1",
                        "text": "This report highlights a game changer for markets.",
                        "evidence_id": "f1",
                    }
                ],
                "quotes_final": [],
                "expert_comment": (
                    "Financial leverage and robust standard errors frame the "
                    "market risk estimate."
                ),
                "linkedin_post": "Revenue growth reached 10% in 2026.",
            },
            evidence_packs={},
            vector_store_id=None,
            validation_mode="inline_deterministic",
        ),
        settings,
        _ctx(),
        prompt_client=FakePromptClient(),
        openai_client=None,
        analysis_store=FakeAnalysisStore(),
    )

    messages = [issue.message for issue in result.issues]
    assert any("rapidly evolving landscape" in message for message in messages)
    assert any("game changer" in message for message in messages)
    assert not any("financial leverage" in message.lower() for message in messages)


@pytest.mark.parametrize("retained_claim_matches", [True, False])
@pytest.mark.parametrize(
    "tldr",
    [
        "The outlook forecasts consumer internet and media revenue growth "
        "across segments in 2026.",
        "Market growth reaches 12 percent next year.",
    ],
)
def test_generic_summary_lead_warning_identifies_claim_and_stronger_finding(
    tmp_path, retained_claim_matches: bool, tldr: str
):
    retained_text = (
        tldr
        if retained_claim_matches
        else "A different retained sentence with its own provenance."
    )
    claims = build_soft_copy_claim_provenance(
        artifact_family="summary",
        text=retained_text,
        declared_claims=[
            {
                "claim": retained_text,
                "classification": "factual",
                "evidence_ids": ["intro-downloads"],
            }
        ],
        evidence_span_index={},
        producing_prompt_identity={},
        generation_attempt=1,
        regeneration_attempt=0,
    )
    result = validate_report(
        ValidationRequest(
            schema_version="1.0",
            report_id="quality-summary-retained-claim",
            report=_report(),
            artifacts={
                "summary": {
                    "tldr": tldr,
                    "claim_evidence_map": [
                        {
                            "claim": tldr,
                            "evidence_id": "intro-downloads",
                            "evidence": tldr,
                            "pages": [],
                        }
                    ],
                },
                "insights_final": [
                    {
                        "id": "ai-referrals",
                        "text": (
                            "AI answer engines divert readers from publisher sites, "
                            "weakening referral traffic."
                        ),
                        "evidence_id": "finding-ai-referrals",
                        "evidence": (
                            "AI answer engines answer queries directly, reducing "
                            "publisher referrals."
                        ),
                    }
                ],
                "soft_copy_claim_provenance": soft_copy_claim_provenance_to_payload(
                    claims
                ),
            },
            evidence_packs={
                "findings": {
                    "findings": [
                        {
                            "id": "intro-downloads",
                            "text": tldr,
                            "evidence": tldr,
                        },
                        {
                            "id": "finding-ai-referrals",
                            "text": "AI answer engines reduce publisher referrals.",
                            "evidence": (
                                "AI answer engines answer queries directly, reducing "
                                "publisher referrals."
                            ),
                        },
                    ]
                }
            },
            vector_store_id=None,
            validation_mode="inline_deterministic",
        ),
        _settings(tmp_path),
        _ctx(),
        prompt_client=FakePromptClient(),
        openai_client=FakeOpenAI({"unsupported": []}),
        analysis_store=FakeAnalysisStore(),
    )

    warning = next(
        issue
        for issue in result.issues
        if issue.rule_id == "artifact_quality"
        and issue.affected_section == "summary.tldr"
        and "broader than a retained source-supported finding" in issue.message
    )
    assert warning.severity == "warning"
    assert warning.entity_id == (
        claims[0].claim_id if retained_claim_matches else "summary.tldr"
    )
    assert warning.evidence_ids == ["finding-ai-referrals"]


def test_summary_quality_accepts_a_strong_quantitative_lead(tmp_path):
    tldr = (
        "The report states that more than 112.1 billion apps were downloaded in 2025."
    )
    result = validate_report(
        ValidationRequest(
            schema_version="1.0",
            report_id="quality-summary-quantitative-lead",
            report=_report(),
            artifacts={
                "summary": {
                    "tldr": tldr,
                    "claim_evidence_map": [
                        {
                            "claim": tldr,
                            "evidence_id": "intro-downloads",
                            "evidence": tldr,
                            "pages": [],
                        }
                    ],
                },
                "insights_final": [
                    {
                        "id": "ai-referrals",
                        "text": (
                            "AI answer engines divert readers from publisher sites, "
                            "weakening referral traffic."
                        ),
                        "evidence_id": "finding-ai-referrals",
                        "evidence": (
                            "AI answer engines answer queries directly, reducing "
                            "publisher referrals."
                        ),
                    }
                ],
            },
            evidence_packs={
                "findings": {
                    "findings": [
                        {
                            "id": "intro-downloads",
                            "text": tldr,
                            "evidence": tldr,
                        },
                        {
                            "id": "finding-ai-referrals",
                            "text": "AI answer engines reduce publisher referrals.",
                            "evidence": (
                                "AI answer engines answer queries directly, reducing "
                                "publisher referrals."
                            ),
                        },
                    ]
                }
            },
            vector_store_id=None,
            validation_mode="inline_deterministic",
        ),
        _settings(tmp_path),
        _ctx(),
        prompt_client=FakePromptClient(),
        openai_client=None,
        analysis_store=FakeAnalysisStore(),
    )

    assert not any(
        issue.rule_id == "artifact_quality" and issue.affected_section == "summary.tldr"
        for issue in result.issues
    )


def test_summary_quality_accepts_a_strong_qualitative_lead(tmp_path):
    tldr = (
        "Publishers lose search referrals when AI answer engines satisfy user "
        "queries directly."
    )
    result = validate_report(
        ValidationRequest(
            schema_version="1.0",
            report_id="quality-summary-qualitative-lead",
            report=_report(),
            artifacts={
                "summary": {
                    "tldr": tldr,
                    "claim_evidence_map": [
                        {
                            "claim": tldr,
                            "evidence_id": "finding-ai-referrals",
                            "evidence": tldr,
                            "pages": [],
                        }
                    ],
                },
                "insights_final": [
                    {
                        "id": "ai-referrals",
                        "text": tldr,
                        "evidence_id": "finding-ai-referrals",
                        "evidence": tldr,
                    }
                ],
            },
            evidence_packs={
                "findings": {
                    "findings": [
                        {
                            "id": "finding-ai-referrals",
                            "text": tldr,
                            "evidence": tldr,
                        }
                    ]
                }
            },
            vector_store_id=None,
            validation_mode="inline_deterministic",
        ),
        _settings(tmp_path),
        _ctx(),
        prompt_client=FakePromptClient(),
        openai_client=None,
        analysis_store=FakeAnalysisStore(),
    )

    assert not any(
        issue.rule_id == "artifact_quality" and issue.affected_section == "summary.tldr"
        for issue in result.issues
    )


def test_generic_summary_lead_is_not_flagged_without_a_stronger_finding(tmp_path):
    tldr = (
        "The outlook forecasts consumer internet and media revenue growth "
        "across segments in 2026."
    )
    result = validate_report(
        ValidationRequest(
            schema_version="1.0",
            report_id="quality-summary-no-stronger-finding",
            report=_report(),
            artifacts={"summary": {"tldr": tldr, "claim_evidence_map": []}},
            evidence_packs={},
            vector_store_id=None,
            validation_mode="inline_deterministic",
        ),
        _settings(tmp_path),
        _ctx(),
        prompt_client=FakePromptClient(),
        openai_client=None,
        analysis_store=FakeAnalysisStore(),
    )

    assert not any(
        issue.rule_id == "artifact_quality" and issue.affected_section == "summary.tldr"
        for issue in result.issues
    )


def test_artifact_quality_uses_a_source_topic_heading_as_public_category(tmp_path):
    settings = _settings(tmp_path)
    result = validate_report(
        ValidationRequest(
            schema_version="1.0",
            report_id="quality-topic-category",
            report=_report(),
            artifacts={
                "summary": {"claim_evidence_map": []},
                "insights_final": [],
                "quotes_final": [],
                "topics_covered": [
                    {
                        "topic": "Population by age",
                        "why_it_matters": (
                            "The report presents the median age and the "
                            "distribution across age groups."
                        ),
                    }
                ],
            },
            evidence_packs={},
            vector_store_id=None,
            validation_mode="inline_deterministic",
        ),
        settings,
        _ctx(),
        prompt_client=FakePromptClient(),
        openai_client=None,
        analysis_store=FakeAnalysisStore(),
    )

    assert not any(
        issue.rule_id == "artifact_quality"
        and issue.affected_section == "topics_covered[0].why_it_matters"
        for issue in result.issues
    )


def test_artifact_quality_keeps_us_abbreviation_with_its_opening_sentence(tmp_path):
    settings = _settings(tmp_path)
    result = validate_report(
        ValidationRequest(
            schema_version="1.0",
            report_id="quality-us-opening",
            report=_report(),
            artifacts={
                "summary": {"claim_evidence_map": []},
                "insights_final": [
                    {
                        "id": "usage",
                        "text": (
                            "U.S. household data usage is forecast to rise from "
                            "475GB per month to 1,000GB per month by 2024E."
                        ),
                        "evidence_id": "usage",
                        "evidence": (
                            "U.S. household data usage is forecast to rise from "
                            "475GB per month to 1,000GB per month by 2024E."
                        ),
                        "metric": {
                            "value": "475GB per month to 1,000GB per month by 2024E"
                        },
                    }
                ],
                "quotes_final": [],
            },
            evidence_packs={},
            vector_store_id=None,
            validation_mode="inline_deterministic",
        ),
        settings,
        _ctx(),
        prompt_client=FakePromptClient(),
        openai_client=None,
        analysis_store=FakeAnalysisStore(),
    )

    assert not any(
        issue.rule_id == "artifact_quality"
        and issue.affected_section == "insights_final[0].text"
        for issue in result.issues
    )


from .cases_01_split_long_module import *  # noqa: F401,F403,E402
