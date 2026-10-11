# ruff: noqa: F401,F403,F405
from __future__ import annotations

import json
from dataclasses import replace

import pytest

from src.contracts.openai import OpenAIResponseResult

from ._support_cases import *  # noqa: F401,F403,F405


def test_truncated_targeted_fallback_keeps_primary_findings_and_stays_bounded(
    tmp_path, caplog
):
    target_id = "market-share"
    doc_map = {
        **substantive_doc_map(),
        "sections": [
            {
                "id": target_id,
                "title": "Market share",
                "summary": "The leading product reached 41% share in 2025.",
                "key_points": ["The leading product reached 41% share in 2025."],
                "pages": [3],
            }
        ],
    }
    retained = {
        "findings": [
            {
                "id": "revenue-growth",
                "text": "Revenue grew 12% in 2025.",
                "evidence": "Revenue grew 12% in 2025.",
                "pages": [2],
                "section_id": "revenue",
                "section_title": "Revenue",
            }
        ]
    }

    class TruncatedTargetedFallbackClient:
        def __init__(self):
            self.findings_calls = []
            self.validation_calls = 0

        def openai_respond_with_vector_store(self, request, ctx):
            payload = doc_map if str(ctx.task_id).endswith(":doc_map") else retained
            return OpenAIResponseResult(
                schema_version="1.0",
                text=json.dumps(payload),
                parsed_json=payload,
                input_tokens=12,
                output_tokens=8,
                tool_calls=1,
                model=request.model,
            )

        def openai_chat_json(self, request, ctx):
            if request.stage == "evidence_pack_targeted_fallback":
                self.findings_calls.append(request)
                return OpenAIResponseResult(
                    schema_version="1.0",
                    text='{"findings":[{"id":"market-share",',
                    parsed_json=None,
                    input_tokens=40,
                    output_tokens=8192,
                    tool_calls=0,
                    model=request.model,
                )
            self.validation_calls += 1
            metrics_text = request.user_prompt.split("Metrics (JSON):", 1)[1]
            metrics_text = metrics_text.split("Quotes (JSON):", 1)[0].strip()
            metrics = json.loads(metrics_text)
            payload = {
                "metrics": [
                    {
                        "id": metric["id"],
                        "supported": True,
                        "confidence": 1.0,
                        "reason": "The source directly states the revenue change.",
                    }
                    for metric in metrics
                ],
                "quotes": [],
            }
            return OpenAIResponseResult(
                schema_version="1.0",
                text=json.dumps(payload),
                parsed_json=payload,
                input_tokens=8,
                output_tokens=4,
                tool_calls=0,
                model=request.model,
            )

    client = TruncatedTargetedFallbackClient()
    prompt_client = RecordingPromptClient()
    source_text = " ".join(
        f"Revenue series: {year} was {year - 2000}%" for year in range(2000, 2025)
    )
    packs = generate_evidence_packs(
        report_id="truncated-fallback-report",
        report_name="truncated-fallback-report.pdf",
        vector_store_id="vs_truncated_fallback",
        settings=_settings(tmp_path, evidence_pack_registry=["doc_map", "findings"]),
        ctx=replace(_ctx(), task_id="test:truncated-fallback-report"),
        source_text=source_text,
        source_spans=[
            {"id": "pdf:p2", "page": 2, "text": "Revenue grew 12% in 2025."},
            {
                "id": "pdf:p3",
                "page": 3,
                "text": "Leading product market share reached 41% in 2025.",
            },
        ],
        openai_client=client,
        prompt_client=prompt_client,
        analysis_store=FakeAnalysisStore(),
    )

    assert len(client.findings_calls) == 1
    fallback_variables = prompt_client.findings_variables
    assert fallback_variables is not None
    assert (
        "at most one concise finding per listed key point"
        in fallback_variables["findings_targeted_fallback_instruction"].casefold()
    )
    target_sections = json.loads(fallback_variables["doc_map_sections_json"])
    assert [section["id"] for section in target_sections] == [target_id]
    findings = packs["findings"]["findings"]
    assert [finding["id"] for finding in findings] == ["revenue-growth"]
    assert packs["evidence_fidelity"]["unsupported_factual_count"] == 0
    rejected_events = []
    for record in caplog.records:
        try:
            event = json.loads(record.message)
        except json.JSONDecodeError:
            continue
        if event.get("event") == "findings_targeted_fallback_rejected":
            rejected_events.append(event)
    assert len(rejected_events) == 1
    assert rejected_events[0]["fields"]["error_class"] == (
        "deterministic_repair_invalid"
    )


def test_targeted_fallback_keeps_validated_alternate_qualification(
    tmp_path,
):
    target_id = "commercial-results"
    doc_map = {
        **substantive_doc_map(),
        "sections": [
            {
                "id": target_id,
                "title": "Commercial results",
                "summary": "Revenue grew and market share increased in 2025.",
                "key_points": [
                    "Figure 1: Global revenue grew 12% in 2025.",
                    "Global market share reached 41% in 2025.",
                ],
                "pages": [3, 4],
            }
        ],
    }
    revenue_evidence = "Global revenue grew 12% in 2025."
    market_share_evidence = "Global market share reached 41% in 2025."
    primary = {
        "findings": [
            {
                "id": "revenue-growth-primary",
                "text": revenue_evidence,
                "evidence": revenue_evidence,
                "pages": [3],
                "section_id": target_id,
                "section_title": "Commercial results",
            }
        ]
    }
    fallback = {
        "findings": [
            {
                "id": "revenue-growth-targeted-copy",
                "text": "Global revenue increased 12% year over year in 2025.",
                "evidence": revenue_evidence,
                "pages": [3],
                "section_id": target_id,
                "section_title": "Commercial results",
            },
            {
                "id": "market-share-targeted",
                "text": "Global market share reached 41% in 2025.",
                "evidence": market_share_evidence,
                "pages": [4],
                "section_id": target_id,
                "section_title": "Commercial results",
            },
        ]
    }

    class DuplicateThenMissingKeypointClient:
        def __init__(self):
            self.fallback_calls = 0

        def openai_respond_with_vector_store(self, request, ctx):
            payload = doc_map if str(ctx.task_id).endswith(":doc_map") else primary
            return OpenAIResponseResult(
                schema_version="1.0",
                text=json.dumps(payload),
                parsed_json=payload,
                input_tokens=8,
                output_tokens=5,
                tool_calls=1,
                model=request.model,
            )

        def openai_chat_json(self, request, ctx):
            if request.stage == "evidence_pack_targeted_fallback":
                self.fallback_calls += 1
                payload = fallback
            else:
                metrics_text = request.user_prompt.split("Metrics (JSON):", 1)[1]
                metrics_text = metrics_text.split("Quotes (JSON):", 1)[0].strip()
                metrics = json.loads(metrics_text)
                payload = {
                    "metrics": [
                        {
                            "id": metric["id"],
                            "supported": True,
                            "confidence": 1.0,
                            "reason": "The source directly states the result.",
                        }
                        for metric in metrics
                    ],
                    "quotes": [],
                }
            return OpenAIResponseResult(
                schema_version="1.0",
                text=json.dumps(payload),
                parsed_json=payload,
                input_tokens=8,
                output_tokens=5,
                tool_calls=0,
                model=request.model,
            )

    client = DuplicateThenMissingKeypointClient()
    packs = generate_evidence_packs(
        report_id="duplicate-targeted-finding",
        report_name="duplicate-targeted-finding.pdf",
        vector_store_id="vs_duplicate_targeted_finding",
        settings=_settings(tmp_path, evidence_pack_registry=["doc_map", "findings"]),
        ctx=replace(_ctx(), task_id="test:duplicate-targeted-finding"),
        source_spans=[
            {"id": "pdf:p3", "page": 3, "text": revenue_evidence},
            {"id": "pdf:p4", "page": 4, "text": market_share_evidence},
        ],
        openai_client=client,
        prompt_client=FakePromptClient(),
        analysis_store=FakeAnalysisStore(),
    )

    findings = packs["findings"]["findings"]
    assert client.fallback_calls == 1
    assert [finding["id"] for finding in findings] == [
        "revenue-growth-primary",
        "revenue-growth-targeted-copy",
        "market-share-targeted",
    ]
    assert packs["evidence_fidelity"]["unsupported_factual_count"] == 0


@pytest.mark.parametrize("include_bogof", [True, False])
def test_targeted_fallback_retains_comparison_without_suppressing_primary_findings(
    tmp_path, include_bogof
):
    target_id = "careful-spending"
    doc_map = {
        **substantive_doc_map(),
        "sections": [
            {
                "id": target_id,
                "title": "Careful spending",
                "summary": "Consumers favor simple promotions and spend carefully.",
                "key_points": [
                    "In October 2025, money-off promotions were effective for 75% "
                    "of consumers, percentage-off for 74%, and buy-one-get-one-free "
                    "offers for 73%.",
                    "In October 2025, 54% made fewer impulse purchases than 71% "
                    "in November 2024.",
                ],
                "pages": [21, 24, 25],
            }
        ],
    }
    promotion_evidence = [
        "Money-off promotions were effective for 75% of consumers.",
        "Percentage-off promotions were effective for 74% of consumers.",
        "Buy-one-get-one-free promotions were effective for 73% of consumers.",
    ]
    primary_promotion_evidence = (
        promotion_evidence if include_bogof else promotion_evidence[:2]
    )
    primary = {
        "findings": [
            {
                "id": f"promotion-{index}",
                "text": evidence,
                "evidence": evidence,
                "pages": [25],
                "section_id": target_id,
                "section_title": "Careful spending",
            }
            for index, evidence in enumerate(primary_promotion_evidence, start=1)
        ]
    }
    promotion_summary = (
        "In Figure 9, consumers rated money-off promotions most effective (75%), "
        "followed by percentage-off promotions (74%) and buy-one-get-one-free "
        "offers (73%)."
    )
    impulse_evidence = (
        "In October 2025, 54% of consumers made fewer impulse purchases, down "
        "from 71% in November 2024."
    )
    fallback = {
        "findings": [
            {
                "id": "promotion-summary-targeted",
                "text": promotion_summary,
                "evidence": "Figure 9. " + " ".join(promotion_evidence),
                "pages": [24],
                "section_id": target_id,
                "section_title": "Careful spending",
            },
            {
                "id": "impulse-targeted",
                "text": impulse_evidence,
                "evidence": impulse_evidence,
                "pages": [21],
                "section_id": target_id,
                "section_title": "Careful spending",
            },
        ]
    }
    source_spans = [
        {
            "id": "pdf:p24",
            "page": 24,
            "text": "Figure 9. " + " ".join(promotion_evidence),
        },
        {"id": "pdf:p25", "page": 25, "text": " ".join(promotion_evidence)},
        {"id": "pdf:p21", "page": 21, "text": impulse_evidence},
    ]

    class SplitComparisonThenMissingFindingClient:
        def __init__(self):
            self.fallback_calls = 0

        def openai_respond_with_vector_store(self, request, ctx):
            payload = doc_map if str(ctx.task_id).endswith(":doc_map") else primary
            return OpenAIResponseResult(
                schema_version="1.0",
                text=json.dumps(payload),
                parsed_json=payload,
                input_tokens=8,
                output_tokens=5,
                tool_calls=1,
                model=request.model,
            )

        def openai_chat_json(self, request, ctx):
            if request.stage == "evidence_pack_targeted_fallback":
                self.fallback_calls += 1
                payload = fallback
            else:
                metrics_text = request.user_prompt.split("Metrics (JSON):", 1)[1]
                metrics_text = metrics_text.split("Quotes (JSON):", 1)[0].strip()
                metrics = json.loads(metrics_text)
                payload = {
                    "metrics": [
                        {
                            "id": metric["id"],
                            "supported": True,
                            "confidence": 1.0,
                            "reason": "The source directly states the result.",
                        }
                        for metric in metrics
                    ],
                    "quotes": [],
                }
            return OpenAIResponseResult(
                schema_version="1.0",
                text=json.dumps(payload),
                parsed_json=payload,
                input_tokens=8,
                output_tokens=5,
                tool_calls=0,
                model=request.model,
            )

    client = SplitComparisonThenMissingFindingClient()
    packs = generate_evidence_packs(
        report_id="split-comparison-dedup",
        report_name="split-comparison-dedup.pdf",
        vector_store_id="vs_split_comparison_dedup",
        settings=_settings(tmp_path, evidence_pack_registry=["doc_map", "findings"]),
        ctx=replace(_ctx(), task_id="test:split-comparison-dedup"),
        source_text="\n".join(span["text"] for span in source_spans),
        source_spans=source_spans,
        openai_client=client,
        analysis_store=FakeAnalysisStore(),
    )

    findings = packs["findings"]["findings"]
    assert client.fallback_calls == 1
    if include_bogof:
        expected = [
            "promotion-1",
            "promotion-2",
            "promotion-3",
            "promotion-summary-targeted",
        ]
    else:
        expected = ["promotion-1", "promotion-2", "promotion-summary-targeted"]
    expected.append("impulse-targeted")
    actual = [finding["id"] for finding in findings]
    assert actual == expected, actual
    assert packs["evidence_fidelity"]["unsupported_factual_count"] == 0


def test_targeted_fallback_drops_exact_duplicate_but_keeps_missing_finding(
    tmp_path,
):
    target_id = "careful-spending"
    doc_map = {
        **substantive_doc_map(),
        "sections": [
            {
                "id": target_id,
                "title": "Careful spending",
                "summary": "Consumers are spending carefully but still indulge.",
                "key_points": [
                    "In October 2025, 54% reported fewer impulse purchases, down "
                    "from 71% in November 2024.",
                    "In October 2025, 71% said small indulgences help manage "
                    "financial stress.",
                ],
                "pages": [21, 22],
            }
        ],
    }
    impulse_evidence = (
        "In October 2025, 54% of consumers reported fewer impulse purchases "
        "versus 71% last year."
    )
    indulgence_evidence = (
        "In October 2025, 71% say small indulgences help manage financial stress."
    )
    primary = {
        "findings": [
            {
                "id": "impulse-primary",
                "text": "Consumers reported fewer impulse purchases, 54% versus "
                "71% last year.",
                "evidence": impulse_evidence,
                "pages": [21],
                "section_id": target_id,
                "section_title": "Careful spending",
            }
        ]
    }
    fallback = {
        "findings": [
            {
                "id": "impulse-targeted-copy",
                    "text": "Consumers reported fewer impulse purchases, 54% versus "
                    "71% last year.",
                "evidence": impulse_evidence,
                "pages": [21],
                "section_id": target_id,
                "section_title": "Careful spending",
            },
            {
                "id": "indulgence-targeted",
                "text": (
                    "In October 2025, 71% of consumers said small indulgences help "
                    "manage financial stress."
                ),
                "evidence": indulgence_evidence,
                "pages": [22],
                "section_id": target_id,
                "section_title": "Careful spending",
            },
        ]
    }

    class BoilerplateDuplicateClient:
        def openai_respond_with_vector_store(self, request, ctx):
            payload = doc_map if str(ctx.task_id).endswith(":doc_map") else primary
            return OpenAIResponseResult(
                schema_version="1.0",
                text=json.dumps(payload),
                parsed_json=payload,
                input_tokens=8,
                output_tokens=5,
                tool_calls=1,
                model=request.model,
            )

        def openai_chat_json(self, request, ctx):
            if request.stage == "evidence_pack_targeted_fallback":
                payload = fallback
            else:
                metrics_text = request.user_prompt.split("Metrics (JSON):", 1)[1]
                metrics_text = metrics_text.split("Quotes (JSON):", 1)[0].strip()
                metrics = json.loads(metrics_text)
                payload = {
                    "metrics": [
                        {
                            "id": metric["id"],
                            "supported": True,
                            "confidence": 1.0,
                            "reason": "The source directly states the result.",
                        }
                        for metric in metrics
                    ],
                    "quotes": [],
                }
            return OpenAIResponseResult(
                schema_version="1.0",
                text=json.dumps(payload),
                parsed_json=payload,
                input_tokens=8,
                output_tokens=5,
                tool_calls=0,
                model=request.model,
            )

    packs = generate_evidence_packs(
        report_id="boilerplate-targeted-duplicate",
        report_name="boilerplate-targeted-duplicate.pdf",
        vector_store_id="vs_boilerplate_targeted_duplicate",
        settings=_settings(tmp_path, evidence_pack_registry=["doc_map", "findings"]),
        ctx=replace(_ctx(), task_id="test:boilerplate-targeted-duplicate"),
        source_spans=[
            {"id": "pdf:p21", "page": 21, "text": impulse_evidence},
            {"id": "pdf:p22", "page": 22, "text": indulgence_evidence},
        ],
        openai_client=BoilerplateDuplicateClient(),
        prompt_client=FakePromptClient(),
        analysis_store=FakeAnalysisStore(),
    )

    findings = packs["findings"]["findings"]
    assert [finding["id"] for finding in findings] == [
        "impulse-primary",
        "indulgence-targeted",
    ]
    assert packs["evidence_fidelity"]["unsupported_factual_count"] == 0
