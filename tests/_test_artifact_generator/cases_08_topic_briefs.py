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


def test_build_topic_briefs_preserves_multilingual_text_and_canonical_unicode():
    doc_map = {
        "sections": [
            {
                "id": "ru-market",
                "title": "Рост рынка",
                "summary": "Рынок вырос на 12%.",
                "key_points": ["Спрос вырос на 12%", "Спрос вырос на 12%"],
                "pages": [3],
            },
            {
                "id": "el-market",
                "title": "Ανάπτυξη αγοράς",
                "summary": "Η αγορά αναπτύχθηκε.",
                "key_points": ["Οι πωλήσεις αυξήθηκαν."],
                "pages": [4],
            },
            {
                "id": "zh-market",
                "title": "市场增长",
                "summary": "市场增长了。",
                "key_points": ["需求增加。"],
                "pages": [5],
            },
            {
                "id": "accent-market",
                "title": "Café growth",
                "summary": "Café demand is rising.",
                "key_points": ["Cafe\u0301 demand rose.", "Café demand rose."],
                "pages": [6],
            },
        ]
    }
    briefs = build_topic_briefs(
        toc_topics=[
            "Рост рынка",
            "Ανάπτυξη αγοράς",
            "市场增长",
            "Cafe\u0301 growth",
        ],
        doc_map=doc_map,
        summary={"claim_evidence_map": []},
        insights_final=[],
    )

    assert [brief["section_id"] for brief in briefs] == [
        "ru-market",
        "el-market",
        "zh-market",
        "accent-market",
    ]
    assert briefs[0]["summary"] == "Рынок вырос на 12%."
    assert briefs[0]["key_points"] == ["Спрос вырос на 12%"]
    assert briefs[1]["key_points"] == ["Οι πωλήσεις αυξήθηκαν."]
    assert briefs[2]["key_points"] == ["需求增加。"]
    assert briefs[3]["key_points"] == ["Cafe\u0301 demand rose."]
    assert [brief["pages"] for brief in briefs] == [[3], [4], [5], [6]]


def test_build_topic_briefs_uses_exact_ids_and_abstains_on_ambiguous_titles():
    doc_map = {
        "sections": [
            {
                "id": "cafe-one",
                "title": "Café growth",
                "summary": "First section summary.",
                "key_points": [],
                "pages": [7],
            },
            {
                "id": "cafe-two",
                "title": "Cafe\u0301 growth",
                "summary": "Second section summary.",
                "key_points": [],
                "pages": [8],
            },
        ]
    }
    common = {
        "doc_map": doc_map,
        "summary": {"claim_evidence_map": []},
        "insights_final": [],
    }

    ambiguous = build_topic_briefs(toc_topics=["Café growth"], **common)
    exact = build_topic_briefs(
        toc_topics=[
            {
                "topic": "Café growth",
                "section_id": "cafe-two",
                "section_title": "Cafe\u0301 growth",
            }
        ],
        **common,
    )
    unknown = build_topic_briefs(
        toc_topics=[
            {
                "topic": "Café growth",
                "section_id": "missing-section",
                "section_title": "Café growth",
            }
        ],
        **common,
    )

    assert ambiguous[0]["section_id"] == ""
    assert ambiguous[0]["summary"] == ""
    assert exact[0]["section_id"] == "cafe-two"
    assert exact[0]["summary"] == "Second section summary."
    assert exact[0]["pages"] == [8]
    assert unknown[0]["section_id"] == "missing-section"
    assert unknown[0]["summary"] == ""
    assert unknown[0]["pages"] == []


def test_toc_display_titles_deduplicate_canonically_equivalent_unicode():
    from src.generators.artifact_generator import build_toc_artifacts

    bundle = build_toc_artifacts(
        doc_map={
            "sections": [
                {"id": "cafe-one", "title": "Café growth", "pages": [1]},
                {"id": "cafe-two", "title": "Cafe\u0301 growth", "pages": [2]},
            ]
        }
    )

    assert [entry["section_id"] for entry in bundle["toc_entries"]] == [
        "cafe-one",
        "cafe-two",
    ]
    assert [entry["display_title"] for entry in bundle["toc_entries"]] == [
        "Café growth",
        "Cafe\u0301 growth (2)",
    ]


__all__ = [
    "test_build_topic_briefs_avoids_positional_section_swap",
    "test_build_topic_briefs_preserves_multilingual_text_and_canonical_unicode",
    "test_build_topic_briefs_uses_exact_ids_and_abstains_on_ambiguous_titles",
    "test_toc_display_titles_deduplicate_canonically_equivalent_unicode",
]
