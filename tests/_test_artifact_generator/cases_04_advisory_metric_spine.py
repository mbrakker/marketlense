# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403


def test_derive_metric_spine_selects_strong_supported_metrics() -> None:
    spine = derive_metric_spine(
        {
            "key_metrics": {
                "metrics": [
                    {
                        "metric_id": "m2",
                        "label": "Low support metric",
                        "value": "",
                        "unit": "percent",
                        "evidence_id": "ev2",
                    },
                    {
                        "metric_id": "m1",
                        "label": "Wallet adoption",
                        "value": "42",
                        "unit": "percent",
                        "timeframe": "2026",
                        "segment": "enterprise merchants",
                        "geography": "Global",
                        "comparator": "2025",
                        "delta": "+7 points",
                        "sample_size": "n=500",
                        "evidence_id": "ev1",
                    },
                ]
            }
        }
    )

    assert spine == [
        {
            "schema_version": "1.0",
            "metric_id": "m1",
            "label": "Wallet adoption",
            "value": "42",
            "unit": "percent",
            "timeframe": "2026",
            "segment": "enterprise merchants",
            "geography": "Global",
            "comparator": "2025",
            "baseline": "",
            "delta": "+7 points",
            "sample_size": "n=500",
            "confidence": "source_backed",
            "missing_context_notes": [],
            "evidence_id": "ev1",
        }
    ]


def test_build_executive_advisory_artifacts_surfaces_not_found_states() -> None:
    advisory = build_executive_advisory_artifacts(
        summary={
            "executive_summary": (
                "Wallets matter because evidence shows adoption is rising."
            )
        },
        insights_final=[
            {
                "id": "i1",
                "text": "Wallet adoption is rising among enterprise merchants.",
                "evidence_id": "ev1",
                "evidence_spans": [
                    {"evidence_id": "ev1", "source_pack": "key_metrics"}
                ],
            }
        ],
        quotes_final=[],
        metric_spine=[],
        evidence_packs={},
    )

    assert advisory["decision_brief"]["status"] == "generated"
    assert advisory["recommendations"]["status"] == "recommendations_not_found"
    assert advisory["risks"]["status"] == "risks_not_found"
    assert advisory["coverage_diagnostics"]["metric_spine_count"] == 0
    assert advisory["audience_variants"]["status"] == "not_requested"


def test_generate_artifacts_passes_metric_spine_to_editorial_prompts(tmp_path) -> None:
    evidence = _evidence_packs()
    evidence["key_metrics"] = {
        "metrics": [
            {
                "metric_id": "m1",
                "label": "Wallet adoption",
                "value": "42",
                "unit": "percent",
                "timeframe": "2026",
                "segment": "enterprise merchants",
                "geography": "Global",
                "delta": "+7 points",
                "sample_size": "n=500",
                "evidence_id": "f1",
            }
        ]
    }
    responses = {
        "summary": {
            "tldr": "Wallet adoption is rising.",
            "tldr_card": "Wallet adoption rose.",
            "executive_summary": "Wallet adoption is rising among merchants.",
            "claim_evidence_map": [
                {
                    "claim": "Wallet adoption is rising.",
                    "evidence_id": "f1",
                    "evidence": "Revenue +10% YoY",
                    "pages": [2],
                }
            ],
        },
        "insights_candidates": {
            "insights_candidates": [
                {
                    "id": "i1",
                    "text": "Wallet adoption is rising among merchants.",
                    "evidence_id": "f1",
                    "evidence": "Revenue +10% YoY",
                    "metric": {},
                    "pages": [2],
                }
            ]
        },
        "insights_final": {
            "insights_final": [
                {
                    "id": "i1",
                    "text": "Wallet adoption is rising among merchants.",
                    "evidence_id": "f1",
                    "evidence": "Revenue +10% YoY",
                    "metric": {},
                    "pages": [2],
                }
            ]
        },
        "quotes": {"quotes": []},
        "cover_semantics": _cover_semantics_response(),
        "expert_comment": {"expert_comment": "Grounded comment"},
        "linkedin_post": {"linkedin_post": "Post summary"},
    }
    prompt_client = CapturingPromptClient()

    payload = generate_artifacts(
        report_id="metric-spine",
        report_name="Metric Spine",
        doc_map=_doc_map(),
        evidence_packs=evidence,
        settings=_settings(tmp_path),
        vector_store_id=None,
        categories=[],
        ctx=_ctx(),
        openai_client=FakeOpenAI(responses),
        prompt_client=prompt_client,
        analysis_store=FakeAnalysisStore(),
    )

    expert_vars = prompt_client.variables_for_namespace(
        "report_vs/artifacts/expert_comment"
    )
    linkedin_vars = prompt_client.variables_for_namespace(
        "report_vs/artifacts/linkedin_post"
    )

    assert payload["metric_spine"][0]["label"] == "Wallet adoption"
    assert json.loads(expert_vars["metric_spine_json"])[0]["evidence_id"] == "f1"
    assert json.loads(linkedin_vars["metric_spine_json"])[0]["label"] == (
        "Wallet adoption"
    )


__all__ = [
    "test_derive_metric_spine_selects_strong_supported_metrics",
    "test_build_executive_advisory_artifacts_surfaces_not_found_states",
    "test_generate_artifacts_passes_metric_spine_to_editorial_prompts",
]
