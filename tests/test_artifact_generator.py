import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.contracts.config import AppSettings
from src.contracts.openai import OpenAIResponseResult
from src.contracts.prompts import PromptSet, PromptTemplate
from src.contracts.run_context import RunContext
from src.contracts.schema_validation import SchemaValidateRequest
from src.generators.artifact_generator import (
    _load_cached_artifacts,
    build_topic_briefs,
    generate_artifacts,
)
from src.services.schema_validator_service import validate_schema
from src.utils.errors import AppError
from src.utils.slugify import slugify


class FakePromptClient:
    def load_prompt_set(self, request, ctx):
        tmpl = PromptTemplate(
            schema_version="1.0",
            path=f"{request.namespace}/system",
            text="system",
            sha256="s",
        )
        user = PromptTemplate(
            schema_version="1.0",
            path=f"{request.namespace}/user",
            text="user",
            sha256="u",
        )
        return PromptSet(schema_version="1.0", system=tmpl, user=user)

    def render_prompt(self, request, ctx):
        return SimpleNamespace(text=request.template.text)


class CapturingPromptClient(FakePromptClient):
    def __init__(self):
        self.render_calls = []

    def render_prompt(self, request, ctx):
        self.render_calls.append(
            {"path": request.template.path, "variables": dict(request.variables)}
        )
        return super().render_prompt(request, ctx)

    def variables_for_namespace(self, namespace):
        for call in self.render_calls:
            if call["path"] == f"{namespace}/system":
                return call["variables"]
        return {}


class FakeOpenAI:
    def __init__(self, responses, *, sleep_seconds=0.0, prerequisites=None):
        self.responses = responses if isinstance(responses, dict) else list(responses)
        self.sleep_seconds = float(sleep_seconds)
        self.prerequisites = prerequisites or {}
        self.requests = []
        self._events = {}
        self._lock = threading.Lock()
        self._in_flight = 0
        self.max_in_flight = 0

    def _step(self, ctx):
        task_id = getattr(ctx, "task_id", "")
        return task_id.rsplit(":", 1)[-1] if ":" in task_id else task_id

    def _next(self, step):
        if isinstance(self.responses, dict):
            return self.responses.get(step, {})
        if not self.responses:
            return {}
        return self.responses.pop(0)

    def _mark_started(self):
        with self._lock:
            self._in_flight += 1
            if self._in_flight > self.max_in_flight:
                self.max_in_flight = self._in_flight

    def _mark_completed(self, step):
        with self._lock:
            self._in_flight = max(0, self._in_flight - 1)
            event = self._events.get(step)
            if event is None:
                event = threading.Event()
                self._events[step] = event
            event.set()

    def _check_dependencies(self, step):
        for dep in self.prerequisites.get(step, []):
            event = self._events.get(dep)
            if event is None:
                event = threading.Event()
                self._events[dep] = event
            if not event.is_set():
                raise AssertionError(f"{step} called before dependency {dep}")

    def _payload_for_step(self, step):
        self._check_dependencies(step)
        self._mark_started()
        try:
            if self.sleep_seconds > 0:
                time.sleep(self.sleep_seconds)
            return self._next(step)
        finally:
            self._mark_completed(step)

    def openai_chat_json(self, req, ctx):
        step = self._step(ctx)
        self.requests.append(("chat", req, step))
        payload = self._payload_for_step(step)
        return OpenAIResponseResult(
            schema_version="1.0",
            text="{}",
            parsed_json=payload,
            input_tokens=0,
            output_tokens=0,
            tool_calls=0,
            model=req.model,
        )

    def openai_respond_with_vector_store(self, req, ctx):
        step = self._step(ctx)
        self.requests.append(("vector", req.vector_store_id, step))
        payload = self._payload_for_step(step)
        return OpenAIResponseResult(
            schema_version="1.0",
            text="{}",
            parsed_json=payload,
            input_tokens=0,
            output_tokens=0,
            tool_calls=0,
            model=req.model,
        )


class FakeAnalysisStore:
    def __init__(self):
        self.stored = []

    def store_pack(
        self, output_dir, report_id, pack_name, payload, ctx, report_slug=None
    ):
        slug = slugify(report_slug or report_id)
        path = Path(output_dir) / slug / "report_analysis" / f"{pack_name}.json"
        self.stored.append((output_dir, report_id, pack_name, payload))
        return str(path)


def _settings(
    tmp_path,
    *,
    artifacts_use_vector_store: bool = False,
    validation_grounding_use_vector_store: bool = False,
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
        artifact_parallel_workers=4,
        artifact_global_max_in_flight=4,
        artifact_global_min_interval_ms=0,
        vector_store_keep=True,
        artifacts_use_vector_store=artifacts_use_vector_store,
        validation_grounding_use_vector_store=validation_grounding_use_vector_store,
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


def _doc_map():
    return {
        "doc_id": "r1",
        "title": "Report",
        "sections": [{"id": "s1", "title": "Intro"}],
    }


def _evidence_packs():
    return {
        "findings": {
            "findings": [
                {
                    "id": "f1",
                    "text": "Revenue up 10%",
                    "evidence": "Revenue +10% YoY",
                    "pages": [2],
                },
                {
                    "id": "f2",
                    "text": "Margin pressure in EU",
                    "evidence": "Margin declined",
                    "pages": [3],
                },
                {
                    "id": "f3",
                    "text": "Retention stabilizing",
                    "evidence": "Retention improved",
                    "pages": [4],
                },
                {
                    "id": "f4",
                    "text": "APAC demand up",
                    "evidence": "APAC growth accelerated",
                    "pages": [5],
                },
                {
                    "id": "f5",
                    "text": "Ad spend efficiency up",
                    "evidence": "CPA improved",
                    "pages": [6],
                },
            ]
        },
        "quote_candidates": {
            "quote_candidates": [
                {
                    "id": "q1",
                    "text": "We are expanding rapidly",
                    "source": "CEO",
                    "page": 3,
                }
            ]
        },
    }


def _low_text_status():
    path = Path(__file__).parent / "fixtures" / "low_text_status.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_generate_artifacts_validates_schema_and_evidence_ids(tmp_path):
    responses = {
        "toc": {"toc_topics": ["Topic 1", "Topic 2"]},
        "summary": {
            "summary": {
                "tldr": "TLDR",
                "executive_summary": "Exec",
                "claim_evidence_map": [
                    {
                        "claim": "Claim",
                        "evidence_id": "f1",
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
                    "text": "Insight 1",
                    "evidence_id": "f1",
                    "evidence": "E1",
                    "metric": {
                        "value": "10",
                        "unit": "%",
                        "trend": "+",
                        "timeframe": "2024",
                        "geography": "US",
                        "segment": "",
                        "sample_size": "",
                        "confidence": "",
                    },
                    "pages": [2],
                    "score": 0.9,
                },
                {
                    "id": "c2",
                    "text": "Insight 2",
                    "evidence_id": "f2",
                    "evidence": "E2",
                    "metric": {
                        "value": "5",
                        "unit": "%",
                        "trend": "-",
                        "timeframe": "2023",
                        "geography": "EU",
                        "segment": "",
                        "sample_size": "",
                        "confidence": "",
                    },
                    "pages": [3],
                    "score": 0.8,
                },
                {
                    "id": "c3",
                    "text": "Insight 3",
                    "evidence_id": "f3",
                    "evidence": "E3",
                    "metric": {
                        "value": "2",
                        "unit": "pt",
                        "trend": "+",
                        "timeframe": "Q1",
                        "geography": "",
                        "segment": "",
                        "sample_size": "",
                        "confidence": "",
                    },
                    "pages": [4],
                    "score": 0.7,
                },
                {
                    "id": "c4",
                    "text": "Insight 4",
                    "evidence_id": "f4",
                    "evidence": "E4",
                    "metric": {
                        "value": "12",
                        "unit": "%",
                        "trend": "+",
                        "timeframe": "2024",
                        "geography": "APAC",
                        "segment": "",
                        "sample_size": "",
                        "confidence": "",
                    },
                    "pages": [5],
                    "score": 0.6,
                },
                {
                    "id": "c5",
                    "text": "Insight 5",
                    "evidence_id": "f5",
                    "evidence": "E5",
                    "metric": {
                        "value": "3",
                        "unit": "%",
                        "trend": "+",
                        "timeframe": "2024",
                        "geography": "",
                        "segment": "",
                        "sample_size": "",
                        "confidence": "",
                    },
                    "pages": [6],
                    "score": 0.5,
                },
            ]
        },
        "insights_final": {
            "insights_final": [
                {
                    "id": "f1",
                    "text": "Top 1",
                    "evidence_id": "f1",
                    "evidence": "E1",
                    "metric": {},
                    "pages": [2],
                },
                {
                    "id": "f2",
                    "text": "Top 2",
                    "evidence_id": "f2",
                    "evidence": "E2",
                    "metric": {},
                    "pages": [3],
                },
                {
                    "id": "f3",
                    "text": "Top 3",
                    "evidence_id": "f3",
                    "evidence": "E3",
                    "metric": {},
                    "pages": [4],
                },
                {
                    "id": "f4",
                    "text": "Top 4",
                    "evidence_id": "f4",
                    "evidence": "E4",
                    "metric": {},
                    "pages": [5],
                },
                {
                    "id": "f5",
                    "text": "Top 5",
                    "evidence_id": "f5",
                    "evidence": "E5",
                    "metric": {},
                    "pages": [6],
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
                    "evidence_id": "q1",
                }
            ]
        },
        "expert_comment": {"expert_comment": "Grounded comment"},
        "linkedin_post": {"linkedin_post": "Post summary"},
    }
    fake_openai = FakeOpenAI(responses)
    analysis_store = FakeAnalysisStore()
    payload = generate_artifacts(
        report_id="r1",
        report_name="report",
        doc_map=_doc_map(),
        evidence_packs=_evidence_packs(),
        settings=_settings(tmp_path),
        vector_store_id="vs_1",
        ctx=_ctx(),
        openai_client=fake_openai,
        prompt_client=FakePromptClient(),
        analysis_store=analysis_store,
    )
    assert all(item["evidence_id"] for item in payload["insights_candidates"])
    assert all(item["evidence_id"] for item in payload["insights_final"])
    assert payload["family_status"]["summary"]["status"] == "generated"
    assert payload["family_status"]["quotes"]["status"] == "generated"
    assert len([req for req in fake_openai.requests if req[0] == "chat"]) == 6
    assert len([req for req in fake_openai.requests if req[0] == "vector"]) == 0
    assert payload["toc_entries"][0]["section_title"] == "Intro"
    assert payload["toc_topics"] == ["Intro"]
    validate_schema(
        SchemaValidateRequest(
            schema_version="1.0", payload=payload, schema_name="artifacts"
        ),
        _ctx(),
    )
    assert analysis_store.stored and analysis_store.stored[0][2] == "artifacts"


def test_generate_artifacts_abstains_low_confidence_families_and_marks_regeneration(
    tmp_path,
):
    responses = {
        "summary": {
            "summary": {
                "tldr": "TLDR",
                "executive_summary": "Exec",
                "claim_evidence_map": [],
            }
        },
        "insights_candidates": {"insights_candidates": []},
        "insights_final": {"insights_final": []},
        "quotes": {"quotes_final": []},
        "expert_comment": {"expert_comment": "Keep the editorial note short."},
        "linkedin_post": {"linkedin_post": "LinkedIn summary."},
    }
    payload = generate_artifacts(
        report_id="r1",
        report_name="report",
        doc_map=_doc_map(),
        evidence_packs=_evidence_packs(),
        settings=_settings(tmp_path),
        ctx=_ctx(),
        openai_client=FakeOpenAI(responses),
        prompt_client=FakePromptClient(),
        analysis_store=FakeAnalysisStore(),
    )

    assert payload["summary"]["tldr"] == ""
    assert payload["summary"]["executive_summary"] == ""
    assert payload["insights_candidates"] == []
    assert payload["insights_final"] == []
    assert payload["quotes_final"] == []
    assert payload["family_status"]["summary"]["status"] == "abstained"
    assert payload["family_status"]["summary"]["policy_action"] == "regenerate"
    assert payload["family_status"]["insights_bundle"]["status"] == "abstained"
    assert payload["family_status"]["insights_bundle"]["policy_action"] == "regenerate"
    assert payload["family_status"]["quotes"]["status"] == "abstained"
    assert payload["family_status"]["quotes"]["policy_action"] == "regenerate"
    assert payload["family_status"]["expert_comment"]["status"] == "generated"
    assert payload["family_status"]["expert_comment"]["policy_action"] == "keep"
    assert payload["family_status"]["linkedin_post"]["status"] == "generated"
    assert payload["family_status"]["linkedin_post"]["policy_action"] == "keep"


def test_generate_artifacts_expands_topic_briefs_from_doc_map(tmp_path):
    responses = {
        "toc": {
            "toc_topics": [
                "Demand outlook",
                "Margin resilience",
                "Operating leverage",
            ]
        },
        "summary": {
            "summary": {
                "tldr": "TLDR",
                "executive_summary": "Exec",
                "claim_evidence_map": [
                    {
                        "claim": "Operating leverage improved through automation.",
                        "evidence_id": "f3",
                        "evidence": "Automation lifted leverage by 3 points.",
                        "pages": [4],
                    }
                ],
            }
        },
        "insights_candidates": {
            "insights_candidates": [
                {
                    "id": "c1",
                    "text": "Demand is strongest in APAC.",
                    "evidence_id": "f1",
                    "evidence": "APAC demand up 12%.",
                    "metric": {},
                    "pages": [2],
                    "score": 0.9,
                }
            ]
        },
        "insights_final": {
            "insights_final": [
                {
                    "id": "i1",
                    "text": "Demand is strongest in APAC.",
                    "evidence_id": "f1",
                    "evidence": "APAC demand up 12%.",
                    "metric": {},
                    "pages": [2],
                },
                {
                    "id": "i2",
                    "text": "Margins stabilized in H2 as input costs eased.",
                    "evidence_id": "f2",
                    "evidence": "Input cost pressure moderated.",
                    "metric": {},
                    "pages": [3],
                },
                {
                    "id": "i3",
                    "text": "Operating leverage improved through automation.",
                    "evidence_id": "f3",
                    "evidence": "Automation lifted leverage by 3 points.",
                    "metric": {},
                    "pages": [4],
                },
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
    payload = generate_artifacts(
        report_id="r_topic_briefs",
        report_name="report",
        doc_map={
            "doc_id": "r1",
            "title": "Report",
            "sections": [
                {
                    "id": "demand-outlook",
                    "title": "Demand outlook",
                    "summary": (
                        "Demand is strongest in APAC and improving in North America."
                    ),
                    "key_points": [
                        "APAC growth leads at +12%",
                        "North America recovered in Q4",
                    ],
                    "pages": [2],
                },
                {
                    "id": "margin-resilience",
                    "title": "Margin resilience",
                    "summary": "Margins stabilized in H2 as input costs eased.",
                    "key_points": [
                        "Input cost pressure moderated",
                        "Promotions remained disciplined",
                    ],
                    "pages": [3],
                },
            ],
        },
        evidence_packs=_evidence_packs(),
        settings=_settings(tmp_path),
        vector_store_id="vs_1",
        ctx=_ctx(),
        openai_client=FakeOpenAI(responses),
        prompt_client=FakePromptClient(),
        analysis_store=FakeAnalysisStore(),
    )

    toc_entries = payload["toc_entries"]
    topic_briefs = payload["toc_topics_expanded"]
    assert len(toc_entries) == 2
    assert [entry["display_title"] for entry in toc_entries] == [
        "Demand outlook",
        "Margin resilience",
    ]
    assert topic_briefs[0]["topic"] == "Demand outlook"
    assert topic_briefs[0]["summary"] == (
        "Demand is strongest in APAC and improving in North America."
    )
    assert topic_briefs[0]["key_points"][0] == "APAC growth leads at +12%"
    assert topic_briefs[1]["section_id"] == "margin-resilience"
    assert payload["toc_topics"] == ["Demand outlook", "Margin resilience"]


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


def test_generate_artifacts_normalizes_malformed_evidence_ids(tmp_path):
    responses = {
        "toc": {"toc_topics": ["Topic 1"]},
        "summary": {
            "summary": {
                "tldr": "TLDR",
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
                "tldr": "TLDR",
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
                {"text": "Quote", "speaker": "Analyst", "citation": "", "page": 1}
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
    assert payload["summary"]["claim_evidence_map"][0]["evidence_id"] == ""
    assert payload["insights_candidates"] == []
    assert payload["insights_final"] == []
    assert payload["family_status"]["insights_bundle"]["status"] == "abstained"
    assert payload["family_status"]["insights_bundle"]["policy_action"] == "regenerate"
    assert payload["quotes_final"][0]["evidence_id"] == ""
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
                "tldr": "TLDR",
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


def test_generate_artifacts_parallelizes_with_dependency_order(tmp_path):
    responses = {
        "toc": {"toc_topics": ["Topic 1", "Topic 2"]},
        "summary": {
            "summary": {
                "tldr": "TLDR",
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
    assert fake_openai.max_in_flight >= 2
    assert len([req for req in fake_openai.requests if req[0] == "vector"]) == 6


def test_generate_artifacts_strips_inline_reference_tokens_from_summary_and_linkedin(
    tmp_path,
):
    responses = {
        "toc": {"toc_topics": ["Topic 1"]},
        "summary": {
            "summary": {
                "tldr": "TLDR",
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
                "tldr": "TLDR",
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


def test_artifact_cache_isolated_by_retrieval_mode(tmp_path):
    responses = {
        "toc": {"toc_topics": ["Topic"]},
        "summary": {
            "summary": {
                "tldr": "TLDR",
                "executive_summary": "Exec",
                "claim_evidence_map": [
                    {
                        "claim": "Claim",
                        "evidence_id": "f1",
                        "evidence": "Support",
                        "pages": [1],
                    }
                ],
            }
        },
        "insights_candidates": {
            "insights_candidates": [
                {
                    "id": "c1",
                    "text": "Candidate 1",
                    "evidence_id": "f1",
                    "evidence": "Support",
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
                    "evidence": "Support",
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
    report_id = "cache_mode_report"
    report_name = "cache mode report"
    md5 = "md5-cache-mode"

    chat_settings = _settings(tmp_path, artifacts_use_vector_store=False)
    chat_openai = FakeOpenAI(responses)
    generate_artifacts(
        report_id=report_id,
        report_name=report_name,
        doc_map=_doc_map(),
        evidence_packs=_evidence_packs(),
        settings=chat_settings,
        vector_store_id="vs_1",
        ctx=_ctx(),
        openai_client=chat_openai,
        prompt_client=FakePromptClient(),
        md5=md5,
    )
    assert len(chat_openai.requests) == 6
    assert len([req for req in chat_openai.requests if req[0] == "chat"]) == 6

    vector_settings = _settings(tmp_path, artifacts_use_vector_store=True)
    vector_openai = FakeOpenAI(responses)
    generate_artifacts(
        report_id=report_id,
        report_name=report_name,
        doc_map=_doc_map(),
        evidence_packs=_evidence_packs(),
        settings=vector_settings,
        vector_store_id="vs_1",
        ctx=_ctx(),
        openai_client=vector_openai,
        prompt_client=FakePromptClient(),
        md5=md5,
    )
    assert len(vector_openai.requests) == 6
    assert len([req for req in vector_openai.requests if req[0] == "vector"]) == 6


def test_load_cached_artifacts_rejects_schema_invalid_payload(tmp_path):
    report_name = "artifact cache invalid"
    cache_path = tmp_path / slugify(report_name) / "report_analysis" / "artifacts.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps({"_cache": {"key": "cache-key"}}),
        encoding="utf-8",
    )

    cached = _load_cached_artifacts(
        output_dir=str(tmp_path),
        report_id="artifact-cache-invalid",
        report_name=report_name,
        cache_key="cache-key",
        ctx=_ctx(),
        analysis_store=None,
    )

    assert cached is None


def test_generate_artifacts_with_auto_context_preserves_input_evidence(tmp_path):
    responses = {
        "toc": {"toc_topics": ["Topic"]},
        "summary": {
            "summary": {
                "tldr": "TLDR",
                "executive_summary": "Exec",
                "claim_evidence_map": [
                    {
                        "claim": "Claim",
                        "evidence_id": "f1",
                        "evidence": "Support",
                        "pages": [1],
                    }
                ],
            }
        },
        "insights_candidates": {
            "insights_candidates": [
                {
                    "id": "c1",
                    "text": "Candidate 1",
                    "evidence_id": "f1",
                    "evidence": "Support",
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
                    "evidence": "Support",
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
        report_id="auto_ctx",
        report_name="auto context report",
        doc_map=_doc_map(),
        evidence_packs=_evidence_packs(),
        settings=_settings(tmp_path),
        vector_store_id=None,
        ctx=None,
        openai_client=fake_openai,
        prompt_client=FakePromptClient(),
        analysis_store=FakeAnalysisStore(),
    )
    assert payload["source_status"]["evidence_present"] is True
    assert payload["source_status"]["not_available"] is False
    assert len(fake_openai.requests) == 6
