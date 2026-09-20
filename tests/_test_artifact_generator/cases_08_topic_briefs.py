# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403


def test_build_topic_briefs_avoids_positional_section_swap():
    topic_briefs = build_topic_briefs(
        toc_topics=[
            "Media receptivity and channel preferences",
            "Channel ad equity rankings",
            "Media brand ad equity",
            "Sentiments on generative AI",
            "Marketer investment priorities",
        ],
        doc_map={
            "doc_id": "doc-1",
            "title": "Media Reactions",
            "sections": [
                {
                    "id": "section-1",
                    "title": "Introduction",
                    "summary": "Study background.",
                    "key_points": [],
                    "pages": [2],
                },
                {
                    "id": "section-2",
                    "title": "Media landscape: Where do people prefer seeing advertising?",
                    "summary": (
                        "Consumer receptivity, channel preferences, and channel-level "
                        "Ad Equity rankings across APAC."
                    ),
                    "key_points": [
                        "Channel preferences differ between consumers and marketers.",
                        "DOOH leads channel Ad Equity.",
                    ],
                    "pages": [8, 10],
                },
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
                        "Marketers plan to increase investment in TikTok, YouTube, and Instagram.",
                    ],
                    "pages": [22, 27],
                },
            ],
        },
        summary={"claim_evidence_map": []},
        insights_final=[],
    )

    assert [item["section_id"] for item in topic_briefs] == [
        "section-2",
        "section-2",
        "section-3",
        "section-4",
        "section-5",
    ]
    assert (
        topic_briefs[2]["section_title"]
        == "Media brands: How do brands interact with people?"
    )
    assert (
        topic_briefs[3]["section_title"]
        == "Sentiments on GenAI: How do APAC consumers perceive AI?"
    )
    assert topic_briefs[4]["section_title"] == "Implications for marketers"


__all__ = ["test_build_topic_briefs_avoids_positional_section_swap"]
