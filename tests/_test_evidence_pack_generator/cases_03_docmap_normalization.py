# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._support_cases import *  # noqa: F401,F403


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
