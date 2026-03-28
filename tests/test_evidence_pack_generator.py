import json
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.contracts.config import AppSettings
from src.contracts.openai import OpenAIResponseResult
from src.contracts.prompts import PromptSet, PromptTemplate
from src.contracts.run_context import RunContext
from src.generators.evidence_packs.registry import PACK_STRATEGIES
from src.generators.evidence_pack_generator import (
    _resolve_pack_steps,
    _strip_json_fence,
    generate_evidence_packs,
)
from src.utils.errors import AppError
from src.utils.slugify import slugify


class FakePromptClient:
    def load_prompt_set(self, request, ctx):
        tmpl = PromptTemplate(
            schema_version="1.0", path="system", text="sys", sha256="s"
        )
        user = PromptTemplate(
            schema_version="1.0", path="user", text="user", sha256="u"
        )
        return PromptSet(schema_version="1.0", system=tmpl, user=user)


class FakeOpenAIClient:
    def __init__(self, parsed):
        self._parsed = parsed

    def openai_respond_with_vector_store(self, req, ctx):
        text = "{}" if isinstance(self._parsed, dict) else ""
        return OpenAIResponseResult(
            schema_version="1.0",
            text=text,
            parsed_json=self._parsed,
            input_tokens=10,
            output_tokens=20,
            tool_calls=0,
            model=req.model,
        )


class RoutedOpenAIClient:
    def __init__(self, payloads_by_pack, text_by_pack=None):
        self._payloads_by_pack = payloads_by_pack
        self._text_by_pack = text_by_pack or {}

    def openai_respond_with_vector_store(self, req, ctx):
        task_id = getattr(ctx, "task_id", "")
        pack = ""
        for candidate in (
            "doc_map",
            "scope",
            "methods",
            "findings",
            "limitations",
            "quote_candidates",
            "key_metrics",
            "risk_register",
            "recommendations",
            "contradictions",
        ):
            if task_id.endswith(f":{candidate}"):
                pack = candidate
                break
        parsed = self._payloads_by_pack.get(pack)
        text = self._text_by_pack.get(pack, "")
        if not text and isinstance(parsed, (dict, list)):
            text = json.dumps(parsed)
        return OpenAIResponseResult(
            schema_version="1.0",
            text=text,
            parsed_json=parsed,
            input_tokens=1,
            output_tokens=1,
            tool_calls=0,
            model=req.model,
        )


class RetryingDocMapClient:
    def __init__(self):
        self.call_count = 0

    def openai_respond_with_vector_store(self, req, ctx):
        self.call_count += 1
        if self.call_count == 1:
            payload = None
            text = "not json"
        elif self.call_count == 2:
            payload = {
                "doc_id": "d1",
                "title": "title",
                "sections": [{"title": "Overview"}],
            }
            text = "{}"
        else:
            payload = {
                "scope": "ok",
                "methods": [],
                "findings": [],
                "limitations": [],
                "quote_candidates": [],
            }
            text = "{}"
        return OpenAIResponseResult(
            schema_version="1.0",
            text=text,
            parsed_json=payload,
            input_tokens=1,
            output_tokens=1,
            tool_calls=0,
            model=req.model,
        )


class TextFallbackDocMapClient:
    def __init__(self):
        self.call_count = 0

    def openai_respond_with_vector_store(self, req, ctx):
        self.call_count += 1
        if self.call_count == 1:
            return OpenAIResponseResult(
                schema_version="1.0",
                text='```json\n{"doc_id":"d1","title":"title","sections":[{"title":"Overview"}]}\n```',
                parsed_json=None,
                input_tokens=1,
                output_tokens=1,
                tool_calls=0,
                model=req.model,
            )
        return OpenAIResponseResult(
            schema_version="1.0",
            text="{}",
            parsed_json={
                "scope": "ok",
                "methods": [],
                "findings": [],
                "limitations": [],
                "quote_candidates": [],
            },
            input_tokens=1,
            output_tokens=1,
            tool_calls=0,
            model=req.model,
        )


class RetryableErrorOpenAIClient:
    def __init__(self, code="openai_request_failed"):
        self.code = code
        self.call_count = 0

    def openai_respond_with_vector_store(self, req, ctx):
        self.call_count += 1
        raise AppError(code=self.code, message="retry", retryable=True)


class FakeAnalysisStore:
    def __init__(self):
        self.stored = []

    def store_pack(
        self, output_dir, report_id, pack_name, payload, ctx, report_slug=None
    ):
        slug = slugify(report_slug or report_id)
        self.stored.append((report_id, pack_name, payload))
        return f"{output_dir}/{slug}/report_analysis/{pack_name}.json"


def _settings(
    tmp_path,
    *,
    evidence_pack_registry=None,
    evidence_pack_enable_new_variety_packs=False,
):
    return AppSettings(
        schema_version="1.0",
        google_sa_path="sa.json",
        gdrive_folder_id="folder",
        openai_api_key="key",
        openai_model="gpt-4.1-mini",
        batch_limit=1,
        output_dir=str(tmp_path),
        cache_dir=str(tmp_path / "cache"),
        state_db=str(tmp_path / "state.sqlite"),
        reports_db=str(tmp_path / "reports.sqlite"),
        publisher_profiles_path=str(tmp_path / "publisher-profiles.json"),
        category_mapping_path="cats.yaml",
        cover_style_path=str(
            Path(__file__).resolve().parents[1] / "src" / "config" / "cover-styles.yaml"
        ),
        ingest_lock_path=str(tmp_path / "lock"),
        temperature=0.1,
        ingest_lock_ttl_seconds=1.0,
        openai_seed=None,
        pdf_text_max_pages=1,
        pdf_text_max_chars=1000,
        rank_model="",
        rank_temperature=0.1,
        rank_seed=None,
        openai_timeout_seconds=5.0,
        rank_timeout_seconds=5.0,
        contents_max_pages=1,
        contents_min_headings=1,
        contents_keywords=["contents"],
        contents_preview_dpi=72,
        vector_store_keep=True,
        evidence_pack_registry=evidence_pack_registry
        or [
            "doc_map",
            "scope",
            "methods",
            "findings",
            "limitations",
            "quote_candidates",
        ],
        evidence_pack_enable_new_variety_packs=evidence_pack_enable_new_variety_packs,
        cost_ledger_path=str(tmp_path / "cost-ledger.jsonl"),
        cost_daily_path=str(tmp_path / "cost-daily.json"),
        model_pricing={
            "gpt-4.1-mini": {
                "input_tokens_per_1k_usd": 0.003,
                "output_tokens_per_1k_usd": 0.006,
                "tool_call_usd": 0.0,
            }
        },
    )


def _ctx():
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def test_generate_evidence_packs_success(tmp_path):
    parsed = {"doc_id": "d1", "title": "title", "sections": []}
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
    assert "doc_map" in packs
    assert packs["doc_map"]["doc_id"] == "d1"
    # ensure store called for each pack
    assert len(analysis_store.stored) == 6


def test_generate_evidence_packs_handles_missing_json(tmp_path):
    fake_openai = FakeOpenAIClient(parsed=None)
    analysis_store = FakeAnalysisStore()
    with pytest.raises(AppError) as exc_info:
        generate_evidence_packs(
            report_id="r1",
            report_name="report",
            vector_store_id="vs_1",
            settings=_settings(tmp_path),
            ctx=_ctx(),
            openai_client=fake_openai,
            prompt_client=FakePromptClient(),
            analysis_store=analysis_store,
        )
    assert exc_info.value.code == "doc_map_empty"
    assert len(analysis_store.stored) == 1
    stored_report_id, stored_pack, stored_payload = analysis_store.stored[0]
    assert stored_report_id == "r1"
    assert stored_pack == "doc_map"
    assert stored_payload["not_found_reason"] == "model_returned_no_json"


def test_generate_evidence_packs_propagates_retryable_app_error(
    tmp_path, assert_app_error
):
    fake_openai = RetryableErrorOpenAIClient()
    analysis_store = FakeAnalysisStore()
    with pytest.raises(AppError) as exc_info:
        generate_evidence_packs(
            report_id="r1",
            report_name="report",
            vector_store_id="vs_1",
            settings=_settings(tmp_path),
            ctx=_ctx(),
            openai_client=fake_openai,
            prompt_client=FakePromptClient(),
            analysis_store=analysis_store,
        )
    assert_app_error(
        exc_info.value,
        code="openai_request_failed",
        retryable=True,
        severity="error",
    )
    assert fake_openai.call_count == 1
    assert len(analysis_store.stored) == 0


def test_generate_evidence_packs_rejects_doc_map_with_only_doc_id(tmp_path):
    # `doc_id` can be present while the pack is still semantically empty.
    parsed = {"doc_id": "d1", "title": "", "sections": []}
    fake_openai = FakeOpenAIClient(parsed=parsed)
    analysis_store = FakeAnalysisStore()
    with pytest.raises(AppError) as exc_info:
        generate_evidence_packs(
            report_id="r1",
            report_name="report",
            vector_store_id="vs_1",
            settings=_settings(tmp_path),
            ctx=_ctx(),
            openai_client=fake_openai,
            prompt_client=FakePromptClient(),
            analysis_store=analysis_store,
        )
    assert exc_info.value.code == "doc_map_empty"
    assert exc_info.value.context["has_content"] is False
    assert exc_info.value.context["doc_id_present"] is True
    assert exc_info.value.context["title_present"] is False
    assert exc_info.value.context["sections_count"] == 0
    assert len(analysis_store.stored) == 1


def test_generate_evidence_packs_does_not_retry_doc_map_inside_generator(tmp_path):
    fake_openai = RetryingDocMapClient()
    analysis_store = FakeAnalysisStore()
    with pytest.raises(AppError) as exc_info:
        generate_evidence_packs(
            report_id="r1",
            report_name="report",
            vector_store_id="vs_1",
            settings=_settings(tmp_path),
            ctx=_ctx(),
            openai_client=fake_openai,
            prompt_client=FakePromptClient(),
            analysis_store=analysis_store,
        )
    assert exc_info.value.code == "doc_map_empty"
    assert fake_openai.call_count == 1
    assert len(analysis_store.stored) == 1


def test_generate_evidence_packs_parses_doc_map_json_from_text_fallback(tmp_path):
    fake_openai = TextFallbackDocMapClient()
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
    assert packs["doc_map"]["doc_id"] == "d1"
    assert packs["doc_map"]["title"] == "title"
    assert fake_openai.call_count == 6


def test_generate_evidence_packs_normalizes_docmap_wrapper(tmp_path):
    parsed = {
        "docmap": {"title": "Retail trends", "sections": [{"title": "Section A"}]}
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
    assert doc_map["sections"][0]["summary"] == ""
    assert doc_map["sections"][0]["key_points"] == []
    assert len(analysis_store.stored) == 6


def test_generate_evidence_packs_normalizes_docmap_camelcase_wrapper(tmp_path):
    parsed = {
        "docMap": {
            "title": "THE 2026 INDUSTRY PULSE REPORT",
            "publisher": "Integral Ad Science",
            "sections": [
                {"title": "Top media challenges and opportunities", "page": 5}
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
    assert doc_map["sections"][0]["summary"] == ""
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
            "brief": "A concise outlook covering demand, channels, and margin pressure.",
            "sections": [
                {
                    "title": "Demand outlook",
                    "brief": "Demand growth decelerates in H2 across most regions.",
                    "keyPoints": ["Growth slowing", "H2 deceleration"],
                    "page": "2",
                },
                {
                    "title": "Methodology",
                    "overview": "The report combines survey data with transaction panels.",
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
        "sections": [{"title": "Introduction", "summary": "Context and study framing."}],
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


def test_generate_evidence_packs_normalizes_legacy_findings_shape(tmp_path):
    fake_openai = RoutedOpenAIClient(
        payloads_by_pack={
            "doc_map": {
                "doc_id": "d1",
                "title": "title",
                "sections": [{"title": "Overview"}],
            },
            "findings": {
                "findings": [
                    {
                        "id": "finding-1",
                        "title": "Finding title",
                        "summary": "Finding summary",
                        "confidence": 0.88,
                        "evidence": [{"snippet": "Supported by evidence"}],
                        "page": "3",
                    }
                ]
            },
        }
    )
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
    finding = packs["findings"]["findings"][0]
    assert packs["findings"]["not_found_reason"] == ""
    assert finding["id"] == "finding-1"
    assert finding["text"] == "Finding summary"
    assert finding["evidence"] == "Supported by evidence"
    assert finding["confidence"] == "0.88"
    assert finding["pages"] == [3]


def test_generate_evidence_packs_parses_limitations_json_array_from_text(tmp_path):
    fake_openai = RoutedOpenAIClient(
        payloads_by_pack={
            "doc_map": {
                "doc_id": "d1",
                "title": "title",
                "sections": [{"title": "Overview"}],
            },
            "limitations": None,
        },
        text_by_pack={
            "limitations": '["Preliminary sample", "Regional bias"]',
        },
    )
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
    assert packs["limitations"]["not_found_reason"] == ""
    assert packs["limitations"]["limitations"] == [
        "Preliminary sample",
        "Regional bias",
    ]


def test_generate_evidence_packs_normalizes_quote_candidates_shape(tmp_path):
    fake_openai = RoutedOpenAIClient(
        payloads_by_pack={
            "doc_map": {
                "doc_id": "d1",
                "title": "title",
                "sections": [{"title": "Overview"}],
            },
            "quote_candidates": {
                "quotes": [
                    {
                        "quote": "The industry is shifting.",
                        "citation": "Section 2",
                        "pages": ["5"],
                    },
                ]
            },
        }
    )
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
    quote = packs["quote_candidates"]["quote_candidates"][0]
    assert packs["quote_candidates"]["not_found_reason"] == ""
    assert quote["text"] == "The industry is shifting."
    assert quote["source"] == "Section 2"
    assert quote["page"] == 5


def test_generate_evidence_packs_uses_registry_subset(tmp_path):
    fake_openai = RoutedOpenAIClient(
        payloads_by_pack={
            "doc_map": {
                "doc_id": "d1",
                "title": "title",
                "sections": [{"title": "Overview"}],
            },
            "findings": {
                "findings": [{"id": "f1", "text": "Finding", "evidence": "Evidence"}]
            },
        }
    )
    packs = generate_evidence_packs(
        report_id="r1",
        report_name="report",
        vector_store_id="vs_1",
        settings=_settings(tmp_path, evidence_pack_registry=["doc_map", "findings"]),
        ctx=_ctx(),
        openai_client=fake_openai,
        prompt_client=FakePromptClient(),
        analysis_store=FakeAnalysisStore(),
    )
    assert list(packs.keys()) == ["doc_map", "findings"]
    assert packs["findings"]["findings"][0]["id"] == "f1"


def test_generate_evidence_packs_generates_variety_packs_when_enabled(tmp_path):
    fake_openai = RoutedOpenAIClient(
        payloads_by_pack={
            "doc_map": {
                "doc_id": "d1",
                "title": "title",
                "sections": [{"title": "Overview"}],
            },
            "scope": {"scope": "Scope summary"},
            "methods": {"methods": ["Survey"]},
            "findings": {
                "findings": [{"id": "f1", "text": "Finding", "evidence": "Evidence"}]
            },
            "limitations": {"limitations": ["Small sample"]},
            "quote_candidates": {
                "quote_candidates": [
                    {"id": "q1", "text": "Quote", "source": "CEO", "page": 2}
                ]
            },
            "key_metrics": {
                "key_metrics": [
                    {
                        "id": "m1",
                        "metric": "Growth",
                        "value": "10",
                        "unit": "%",
                        "evidence_id": "f1",
                        "pages": [2],
                    }
                ]
            },
            "risk_register": {
                "risk_register": [
                    {
                        "id": "r1",
                        "risk": "Churn risk",
                        "impact": "Revenue",
                        "likelihood": "Medium",
                        "mitigation": "Retention",
                        "evidence_id": "f1",
                    }
                ]
            },
            "recommendations": {
                "recommendations": [
                    {
                        "id": "rec1",
                        "recommendation": "Invest in retention",
                        "rationale": "Churn pressure",
                        "evidence_id": "f1",
                    }
                ]
            },
            "contradictions": {
                "contradictions": [
                    {
                        "id": "c1",
                        "statement_a": "Demand up",
                        "statement_b": "Conversion down",
                        "explanation": "Segment split",
                        "evidence_ids": ["f1"],
                    }
                ]
            },
        }
    )
    packs = generate_evidence_packs(
        report_id="r1",
        report_name="report",
        vector_store_id="vs_1",
        settings=_settings(tmp_path, evidence_pack_enable_new_variety_packs=True),
        ctx=_ctx(),
        openai_client=fake_openai,
        prompt_client=FakePromptClient(),
        analysis_store=FakeAnalysisStore(),
    )
    assert "key_metrics" in packs
    assert "risk_register" in packs
    assert "recommendations" in packs
    assert "contradictions" in packs
    assert packs["key_metrics"]["key_metrics"][0]["id"] == "m1"
    assert packs["risk_register"]["risk_register"][0]["id"] == "r1"
    assert packs["recommendations"]["recommendations"][0]["id"] == "rec1"
    assert packs["contradictions"]["contradictions"][0]["id"] == "c1"


def test_generate_evidence_packs_variety_pack_non_json_falls_back_with_reason(tmp_path):
    fake_openai = RoutedOpenAIClient(
        payloads_by_pack={
            "doc_map": {
                "doc_id": "d1",
                "title": "title",
                "sections": [{"title": "Overview"}],
            },
            "key_metrics": None,
        },
        text_by_pack={
            "key_metrics": "not-json",
        },
    )
    packs = generate_evidence_packs(
        report_id="r1",
        report_name="report",
        vector_store_id="vs_1",
        settings=_settings(
            tmp_path,
            evidence_pack_registry=["doc_map", "key_metrics"],
            evidence_pack_enable_new_variety_packs=True,
        ),
        ctx=_ctx(),
        openai_client=fake_openai,
        prompt_client=FakePromptClient(),
        analysis_store=FakeAnalysisStore(),
    )
    assert packs["key_metrics"]["key_metrics"] == []
    assert packs["key_metrics"]["not_found_reason"] == "model_returned_no_json"


def test_strip_json_fence_requires_closing_fence():
    raw = '```json\n{"key":1}\n'
    assert _strip_json_fence(raw) == raw.strip()


def test_strip_json_fence_strips_allowed_json_fence():
    raw = '```json\n{"key":1}\n```'
    assert _strip_json_fence(raw) == '{"key":1}'


def test_resolve_pack_steps_prepends_doc_map_when_missing():
    settings = SimpleNamespace(
        evidence_pack_registry=["scope", "methods"],
        evidence_pack_enable_new_variety_packs=False,
    )
    steps = _resolve_pack_steps(settings)
    assert [name for name, _, _ in steps][:3] == ["doc_map", "scope", "methods"]


def test_pack_strategy_registry_exposes_expected_prompt_and_schema_metadata():
    expected = {
        "doc_map": ("doc_map", "doc_map"),
        "scope": ("evidence_packs/scope", "scope_pack"),
        "methods": ("evidence_packs/methods", "methods_pack"),
        "findings": ("evidence_packs/findings", "findings_pack"),
        "limitations": ("evidence_packs/limitations", "limitations_pack"),
        "quote_candidates": (
            "evidence_packs/quote_candidates",
            "quote_candidates_pack",
        ),
        "key_metrics": ("evidence_packs/key_metrics", "key_metrics_pack"),
        "risk_register": ("evidence_packs/risk_register", "risk_register_pack"),
        "recommendations": (
            "evidence_packs/recommendations",
            "recommendations_pack",
        ),
        "contradictions": ("evidence_packs/contradictions", "contradictions_pack"),
    }
    assert set(PACK_STRATEGIES.keys()) == set(expected.keys())
    for pack_name, (prompt_ns, schema_name) in expected.items():
        strategy = PACK_STRATEGIES[pack_name]
        assert strategy.prompt_namespace_suffix == prompt_ns
        assert strategy.schema_name == schema_name
