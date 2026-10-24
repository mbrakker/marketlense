from __future__ import annotations

import hashlib

from src.contracts.soft_copy_claim_provenance import (
    SoftCopyClaimProvenance,
    soft_copy_claim_provenance_to_payload,
)
from src.generators.artifact_normalization import (
    build_expert_synthesis_context,
    normalize_artifact_insights,
    preserve_public_source_displays,
)
from src.generators.public_editorial_quality_generator import (
    evaluate_public_editorial_quality,
)

VIDEO_ID = "video_super_users_time_spend"
AUDIO_ID = "audio_super_users_time_spend"
VIDEO_PAGE = 15
AUDIO_PAGE = 17

VIDEO_FINDING = (
    "In the U.S. in 2017, the top 25% of video users "
    "(4.5+ hours of daily video attention) accounted for 61% of time spent "
    "and 34% of consumer spend; all other users accounted for 39% of time "
    "and 66% of spend."
)
AUDIO_FINDING = (
    "In the U.S. in 2017, the top 25% of audio users "
    "(3+ hours of daily audio attention) accounted for 64% of time spent "
    "and 47% of consumer spend; all other users accounted for 36% of time "
    "and 53% of spend."
)
VIDEO_OCR_EXCERPT = (
    "VIDEO TIME AND SPEND RELATIVE TO SHARE OF USERS, U.S., 2017, % TOTAL\n"
    "66%\n39%\n34%\n61%\nShare of Time Spent Share of Consumer Spend\n"
    "Top 25% of Users (4.5+ hours of daily video attention) All Other Users"
)
AUDIO_OCR_EXCERPT = (
    "AUDIO TIME AND SPEND RELATIVE TO SHARE OF USERS, U.S., 2017, % TOTAL\n"
    "53%\n36%\n47%\n64%\nShare of Time Spent Share of Consumer Spend\n"
    "Top 25% of Users (3+ hours of daily audio attention) All Other Users"
)


def _cohort_plan() -> dict[str, object]:
    return {
        "report_thesis": "Media attention and consumer spend diverge by cohort.",
        "themes": [
            {
                "theme": "Video attention and spend by cohort",
                "priority": 1,
                "evidence_ids": [VIDEO_ID],
            },
            {
                "theme": "Audio attention and spend by cohort",
                "priority": 2,
                "evidence_ids": [AUDIO_ID],
            },
        ],
    }


def _activate_evidence_packs() -> dict[str, object]:
    return {
        "findings": {
            "findings": [
                {
                    "id": VIDEO_ID,
                    "text": VIDEO_FINDING,
                    "evidence": VIDEO_OCR_EXCERPT,
                    "pages": [VIDEO_PAGE],
                },
                {
                    "id": AUDIO_ID,
                    "text": AUDIO_FINDING,
                    "evidence": AUDIO_OCR_EXCERPT,
                    "pages": [AUDIO_PAGE],
                },
            ]
        }
    }


def _factual_claim_binding(text: str, evidence_id: str) -> dict[str, object]:
    return soft_copy_claim_provenance_to_payload(
        [
            SoftCopyClaimProvenance(
                schema_version="1.0",
                artifact_family="expert_comment",
                claim_id=f"soft_copy:expert_comment:{hashlib.sha256(text.encode()).hexdigest()[:16]}",
                text_hash=hashlib.sha256(text.encode()).hexdigest(),
                classification="factual",
                evidence_ids=(evidence_id,),
                source_spans=(),
                producing_prompt_identity={"namespace": "test/activate-cohort"},
                generation_attempt=1,
                regeneration_attempt=0,
            )
        ]
    )


def _quality_report_for_expert_claim(
    *, text: str, source_evidence: str, evidence_id: str
):
    artifacts = {
        "insights_final": [
            {
                "id": evidence_id,
                "text": text,
                "evidence_id": evidence_id,
                "evidence": source_evidence,
                "metric": {},
                "pages": [VIDEO_PAGE if evidence_id == VIDEO_ID else AUDIO_PAGE],
            }
        ],
        "expert_comment": text,
        "soft_copy_claim_provenance": _factual_claim_binding(text, evidence_id),
    }
    return evaluate_public_editorial_quality(
        report_id="activate-cohort-binding",
        artifacts=artifacts,
    )


def test_activate_cohort_relationships_survive_into_expert_context() -> None:
    # These are the captured Activate insight claims. The compound metric
    # display is intentionally normalized away, while the complete finding
    # text and page-bound OCR excerpts remain available.
    insights = normalize_artifact_insights(
        [
            {
                "id": "video-attention-and-spend-cohorts",
                "text": VIDEO_FINDING,
                "evidence_id": VIDEO_ID,
                "evidence": VIDEO_FINDING,
                "metric": {
                    "label": "Video time and consumer spend by attention cohort",
                    "value": (
                        "Top 25%: 61% of time and 34% of spend vs all other users: "
                        "39% of time and 66% of spend"
                    ),
                    "unit": "Share of total (%)",
                    "subject": "Video time spent and consumer spend",
                    "cohort": (
                        "Top 25% with 4.5+ hours of daily video attention; "
                        "all other users"
                    ),
                    "denominator": "Total time spent and total consumer spend",
                    "timeframe": "2017",
                },
                "pages": [VIDEO_PAGE],
                "so_what": "Attention and spending are distinct measures.",
            },
        ],
        prefix="activate",
    )
    preserve_public_source_displays(
        summary={}, insights_final=insights, expert_comment="", linkedin_post=""
    )
    assert all(not item["metric"]["value"] for item in insights)

    context = build_expert_synthesis_context(
        editorial_plan=_cohort_plan(),
        insights_final=insights,
        doc_map={},
        evidence_packs=_activate_evidence_packs(),
    )

    by_evidence_id = {
        item["evidence_id"]: item for item in context["insight_implications"]
    }
    assert by_evidence_id[VIDEO_ID]["source_finding"] == VIDEO_FINDING
    assert by_evidence_id[VIDEO_ID]["source_excerpt"] == VIDEO_OCR_EXCERPT
    assert by_evidence_id[VIDEO_ID]["source_page"] == VIDEO_PAGE
    assert AUDIO_ID not in by_evidence_id
    theme_evidence = {
        item["evidence_id"]: item
        for theme in context["themes"]
        for item in theme["evidence"]
    }
    assert "source_finding" not in theme_evidence[VIDEO_ID]
    assert theme_evidence[AUDIO_ID]["source_finding"] == AUDIO_FINDING
    assert theme_evidence[AUDIO_ID]["text"] == AUDIO_OCR_EXCERPT
    assert theme_evidence[AUDIO_ID]["page"] == AUDIO_PAGE


def test_expert_context_retains_composite_metric_observation_boundaries() -> None:
    observations = [
        {
            "label": "Installs",
            "value": "19",
            "unit": "%",
            "segment": "Casual games",
            "timeframe": "YoY 2024–2025",
        },
        {
            "label": "Installs",
            "value": "-1",
            "unit": "%",
            "segment": "Strategy games",
            "timeframe": "YoY 2024–2025",
        },
    ]
    context = build_expert_synthesis_context(
        editorial_plan={
            "report_thesis": "Gaming subverticals diverge.",
            "themes": [
                {
                    "theme": "Gaming subverticals",
                    "priority": 1,
                    "evidence_ids": [VIDEO_ID],
                },
                {
                    "theme": "Gaming implications",
                    "priority": 2,
                    "evidence_ids": [VIDEO_ID],
                },
            ],
        },
        insights_final=[
            {
                "id": "gaming-subverticals",
                "evidence_id": VIDEO_ID,
                "so_what": "Acquisition and engagement can diverge by subvertical.",
                "metric": {
                    "label": "Gaming installs by subvertical",
                    "value": "Casual +19%; strategy -1%",
                    "unit": "% YoY",
                    "subject": "Gaming installs",
                    "cohort": "Named game subverticals",
                    "denominator": "Percentage change",
                    "timeframe": "YoY 2024–2025",
                    "forecast_status": "Observed",
                    "observations": observations,
                },
            }
        ],
        doc_map={},
        evidence_packs=_activate_evidence_packs(),
    )

    implication = context["insight_implications"][0]
    assert implication["metric"]["forecast_status"] == "Observed"
    assert implication["metric"]["observations"] == observations


def test_activate_cohort_relationship_validator_rejects_top_cohort_value_swaps() -> (
    None
):
    cases = (
        (
            VIDEO_ID,
            "Top 25% of video users account for 34% of consumer spend.",
            "Top 25% of video users account for 66% of consumer spend.",
            (
                "Top 25% of video users account for 34% of consumer spend. "
                "All other video users account for 66% of consumer spend."
            ),
        ),
        (
            AUDIO_ID,
            "Top 25% of audio users account for 47% of consumer spend.",
            "Top 25% of audio users account for 53% of consumer spend.",
            (
                "Top 25% of audio users account for 47% of consumer spend. "
                "All other audio users account for 53% of consumer spend."
            ),
        ),
    )
    for evidence_id, correct, swapped, source in cases:
        accepted = _quality_report_for_expert_claim(
            text=correct, source_evidence=source, evidence_id=evidence_id
        )
        rejected = _quality_report_for_expert_claim(
            text=swapped, source_evidence=source, evidence_id=evidence_id
        )

        assert "public_editorial_quality.metric_label_relationship" not in {
            issue.rule_id for issue in accepted.issues
        }
        assert "public_editorial_quality.metric_label_relationship" in {
            issue.rule_id for issue in rejected.issues
        }


def test_complete_structured_metric_binding_is_retained_with_its_source() -> None:
    finding = "Top cohort accounts for 42% of total spend in 2017."
    evidence_packs = {
        "findings": {
            "findings": [
                {
                    "id": "single-metric",
                    "text": finding,
                    "evidence": finding,
                    "pages": [10],
                }
            ]
        }
    }
    insights = normalize_artifact_insights(
        [
            {
                "id": "cohort-spend-share",
                "text": finding,
                "evidence_id": "single-metric",
                "evidence": finding,
                "metric": {
                    "label": "Spend by cohort",
                    "value": "42%",
                    "unit": "share of total",
                    "subject": "Spend",
                    "cohort": "Top cohort",
                    "denominator": "Total spend",
                    "timeframe": "2017",
                },
                "pages": [10],
                "so_what": "The cohort represents a defined share of spend.",
            }
        ],
        prefix="metric",
    )
    preserve_public_source_displays(
        summary={}, insights_final=insights, expert_comment="", linkedin_post=""
    )
    context = build_expert_synthesis_context(
        editorial_plan={
            "report_thesis": "The source reports a cohort spend share.",
            "themes": [
                {
                    "theme": "Spend share",
                    "priority": 1,
                    "evidence_ids": ["single-metric"],
                },
                {
                    "theme": "Scope",
                    "priority": 2,
                    "evidence_ids": ["single-metric"],
                },
            ],
        },
        insights_final=insights,
        doc_map={},
        evidence_packs=evidence_packs,
    )

    implication = context["insight_implications"][0]
    assert implication["source_finding"] == finding
    assert implication["source_excerpt"] == finding
    assert implication["source_page"] == 10
    assert implication["metric"] == {
        "label": "Spend by cohort",
        "value": "42%",
        "unit": "share of total",
        "subject": "Spend",
        "cohort": "Top cohort",
        "denominator": "Total spend",
        "timeframe": "2017",
    }


def test_ambiguous_activate_chart_excerpt_does_not_create_a_cohort_mapping() -> None:
    evidence_packs = _activate_evidence_packs()
    evidence_packs["findings"]["findings"][0]["text"] = (
        "The chart reports time and spending shares by user group."
    )
    context = build_expert_synthesis_context(
        editorial_plan=_cohort_plan(),
        insights_final=[
            {
                "id": "ambiguous-video-chart",
                "text": "",
                "evidence_id": VIDEO_ID,
                "metric": {
                    "label": "Video time and spend",
                    "value": "Top 25%: 61% time, 34% spend",
                    "unit": "%",
                    "subject": "Video",
                },
                "so_what": "The chart reports audience shares.",
            }
        ],
        doc_map={},
        evidence_packs=evidence_packs,
    )

    implication = context["insight_implications"][0]
    assert implication["evidence_id"] == VIDEO_ID
    assert implication["source_finding"] == (
        "The chart reports time and spending shares by user group."
    )
    assert "66%" not in implication["source_finding"]
    assert "metric" not in implication
