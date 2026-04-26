from types import SimpleNamespace
import json
import logging
import threading
from pathlib import Path

import pytest

from src.contracts.config import AppSettings
from src.contracts.prompts import PromptSet, PromptTemplate
from src.contracts.report_models import Figure, Quote, ReportPayload
from src.contracts.run_context import RunContext
from src.contracts.validation import ValidationRequest
from src.contracts.openai import OpenAIResponseResult
from src.generators.validation.cache import load_cached_validation
from src.generators.validation.registry import build_validation_rule_registry
from src.generators.validation_generator import validate_report
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
            text="user {{ report_json }}",
            sha256="u",
        )
        return PromptSet(schema_version="1.0", system=tmpl, user=user)

    def render_prompt(self, request, ctx):
        return SimpleNamespace(text=request.template.text)


class FakeOpenAI:
    def __init__(self, *payloads, semantic_payload=None, grounding_payload=None):
        self.payloads = list(payloads) or [{}]
        self.semantic_payload = semantic_payload
        self.grounding_payload = grounding_payload
        self.requests = []
        self._lock = threading.Lock()

    def _next_payload(self, ctx):
        task_id = str(getattr(ctx, "task_id", ""))
        if task_id.endswith(":semantic") and isinstance(self.semantic_payload, dict):
            return self.semantic_payload
        if task_id.endswith(":grounding") and isinstance(self.grounding_payload, dict):
            return self.grounding_payload
        with self._lock:
            if self.payloads:
                return self.payloads.pop(0)
            return {}

    def openai_chat_json(self, req, ctx):
        payload = self._next_payload(ctx)
        with self._lock:
            self.requests.append(("chat", req.model, str(getattr(ctx, "task_id", ""))))
        return OpenAIResponseResult(
            schema_version="1.0",
            text=json.dumps(payload),
            parsed_json=payload,
            input_tokens=0,
            output_tokens=0,
            tool_calls=0,
            model=req.model,
        )

    def openai_respond_with_vector_store(self, req, ctx):
        with self._lock:
            self.requests.append(
                ("vector", req.vector_store_id, str(getattr(ctx, "task_id", "")))
            )
        return self.openai_chat_json(req, ctx)


class FailingOpenAI(FakeOpenAI):
    def __init__(self, *, semantic_exc=None, grounding_exc=None):
        super().__init__(semantic_payload={"metrics": [], "quotes": []}, grounding_payload={"unsupported": []})
        self.semantic_exc = semantic_exc
        self.grounding_exc = grounding_exc

    def openai_chat_json(self, req, ctx):
        task_id = str(getattr(ctx, "task_id", ""))
        if task_id.endswith(":semantic") and self.semantic_exc is not None:
            raise self.semantic_exc
        if task_id.endswith(":grounding") and self.grounding_exc is not None:
            raise self.grounding_exc
        return super().openai_chat_json(req, ctx)

    def openai_respond_with_vector_store(self, req, ctx):
        task_id = str(getattr(ctx, "task_id", ""))
        if task_id.endswith(":grounding") and self.grounding_exc is not None:
            raise self.grounding_exc
        return super().openai_respond_with_vector_store(req, ctx)


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
    validation_grounding_use_vector_store: bool = False,
    report_worker_limit: int = 2,
    validation_data_gap_policy: str = "warn",
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
        ingest_lock_ttl_seconds=1.0,
        temperature=0.1,
        openai_seed=None,
        pdf_text_max_pages=1,
        pdf_text_max_chars=1000,
        rank_model="",
        rank_temperature=0.1,
        rank_seed=None,
        report_worker_limit=report_worker_limit,
        openai_timeout_seconds=5.0,
        rank_timeout_seconds=5.0,
        contents_max_pages=1,
        contents_min_headings=1,
        contents_keywords=["contents"],
        contents_preview_dpi=72,
        vector_store_keep=True,
        validation_grounding_use_vector_store=validation_grounding_use_vector_store,
        validation_data_gap_policy=validation_data_gap_policy,
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


def _report():
    return ReportPayload(
        tldr="TLDR",
        title="Report",
        insights=["i1", "i2", "i3", "i4", "i5"],
        quote=Quote(text="Quoted text", author="Analyst"),
        figure=Figure(title="Figure", evidence="Fig"),
        commentary="Commentary",
        source="Source",
    )


def _low_text_status():
    path = Path(__file__).parent / "fixtures" / "low_text_status.json"
    return json.loads(path.read_text(encoding="utf-8"))


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


def test_validation_accepts_paraphrased_metrics_and_quotes(tmp_path):
    settings = _settings(tmp_path)
    artifacts = {
        "insights_final": [
            {
                "id": "i1",
                "text": "Revenue grew year over year",
                "evidence_id": "e1",
                "evidence": "The company reported ten percent year-over-year revenue growth.",
                "metric": {"value": "10%", "unit": "%", "timeframe": "2024"},
            },
        ],
        "quotes_final": [
            {
                "id": "q1",
                "text": "Revenue grew ten percent YoY",
                "speaker": "CEO",
                "citation": "The CEO noted a year-over-year increase of ten pct.",
                "is_paraphrase": True,
            },
        ],
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
    grounding_payload = {"unsupported": []}
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
            evidence_packs={},
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


def test_commentary_numbers_allowed_when_in_report_or_evidence(tmp_path):
    settings = _settings(tmp_path)
    artifacts = {
        "summary": {
            "tldr": "TLDR",
            "executive_summary": "Exec 42%",
            "claim_evidence_map": [],
        },
        "insights_final": [],
        "quotes_final": [
            {
                "text": "Revenue grew 42% year over year",
                "speaker": "CEO",
                "citation": "Revenue grew 42% year over year",
                "evidence_id": "f1",
            }
        ],
        "expert_comment": "We expect revenue to stay around 42% growth.",
        "linkedin_post": "Analysts noted 42% expansion.",
    }
    evidence_packs = {
        "pack": {
            "findings": [{"id": "f1", "evidence": "Revenue grew 42% year over year"}]
        }
    }
    fake_openai = FakeOpenAI(
        semantic_payload={"metrics": [], "quotes": []},
        grounding_payload={"unsupported": []},
    )
    analysis_store = FakeAnalysisStore()
    result = validate_report(
        ValidationRequest(
            schema_version="1.0",
            report_id="r3",
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
    assert not any("Number" in issue.message for issue in result.issues)


def test_validation_allows_interpretation_and_recommendation_in_allowed_sections(
    tmp_path,
):
    settings = _settings(tmp_path)
    artifacts = {
        "insights_final": [
            {
                "id": "i1",
                "text": "Evidence baseline 42%",
                "evidence_id": "e1",
                "evidence": "Baseline metric is 42%",
            }
        ],
        "quotes_final": [
            {
                "id": "q1",
                "text": "Baseline metric is 42%",
                "speaker": "Analyst",
                "citation": "Baseline metric is 42%",
                "evidence_id": "e1",
            }
        ],
        "expert_comment": "This likely indicates teams should prioritize cross-platform governance.",
        "linkedin_post": "Recommendation: focus on governance and phased rollout.",
    }
    fake_openai = FakeOpenAI(
        semantic_payload={"metrics": [], "quotes": []},
        grounding_payload={
            "unsupported": [
                {
                    "section": "expert_comment",
                    "text": "This likely indicates teams should prioritize cross-platform governance.",
                    "classification": "prescriptive_recommendation",
                    "violation_type": "non_fatal_interpretation",
                    "reason": "Recommendation extends beyond evidence details.",
                }
            ]
        },
    )
    result = validate_report(
        ValidationRequest(
            schema_version="1.0",
            report_id="r-interpret",
            report=_report(),
            artifacts=artifacts,
            evidence_packs={},
            vector_store_id=None,
        ),
        settings,
        _ctx(),
        prompt_client=FakePromptClient(),
        openai_client=fake_openai,
        analysis_store=FakeAnalysisStore(),
    )
    assert result.status == "pass"
    assert not any(issue.severity == "error" for issue in result.issues)
    assert any(issue.affected_section == "expert_comment" for issue in result.issues)


def test_validation_fails_on_report_directive_misattribution(tmp_path):
    settings = _settings(tmp_path)
    artifacts = {
        "insights_final": [
            {
                "id": "i1",
                "text": "Evidence baseline 42%",
                "evidence_id": "e1",
                "evidence": "Baseline metric is 42%",
            }
        ],
        "expert_comment": "The report instructs brands to double investment immediately.",
    }
    fake_openai = FakeOpenAI(
        semantic_payload={"metrics": [], "quotes": []},
        grounding_payload={
            "unsupported": [
                {
                    "section": "expert_comment",
                    "text": "The report instructs brands to double investment immediately.",
                    "reason": "No directive exists in source report.",
                }
            ]
        },
    )
    result = validate_report(
        ValidationRequest(
            schema_version="1.0",
            report_id="r-directive",
            report=_report(),
            artifacts=artifacts,
            evidence_packs={},
            vector_store_id=None,
        ),
        settings,
        _ctx(),
        prompt_client=FakePromptClient(),
        openai_client=fake_openai,
        analysis_store=FakeAnalysisStore(),
    )
    assert result.status == "fail"
    assert any(
        "report_directive_misattribution" in issue.message for issue in result.issues
    )
    assert any(issue.severity == "error" for issue in result.issues)


def test_validation_number_matching_normalizes_percent_and_billions(tmp_path):
    settings = _settings(tmp_path)
    artifacts = {
        "insights_final": [
            {
                "id": "i1",
                "text": "Context says revenue is more than $10B and conversion is 37%.",
                "evidence_id": "e1",
                "evidence": "Revenue is more than $10B while conversion reached 37%.",
            }
        ],
        "quotes_final": [
            {
                "id": "q1",
                "text": "Revenue is more than $10B while conversion reached 37%.",
                "speaker": "Analyst",
                "citation": "Revenue is more than $10B while conversion reached 37%.",
                "evidence_id": "e1",
            }
        ],
        "expert_comment": "Market size is >10 in annual USD billions and conversion reached 37.0.",
        "linkedin_post": "Leaders should plan around >10 USD bn scale and a 37.0 conversion baseline.",
    }
    fake_openai = FakeOpenAI(
        semantic_payload={"metrics": [], "quotes": []},
        grounding_payload={"unsupported": []},
    )
    result = validate_report(
        ValidationRequest(
            schema_version="1.0",
            report_id="r-numbers",
            report=_report(),
            artifacts=artifacts,
            evidence_packs={},
            vector_store_id=None,
        ),
        settings,
        _ctx(),
        prompt_client=FakePromptClient(),
        openai_client=fake_openai,
        analysis_store=FakeAnalysisStore(),
    )
    assert result.status == "pass"
    assert not any("Number" in issue.message for issue in result.issues)


def test_validation_number_check_ignores_units_and_matches_numeric_value(tmp_path):
    settings = _settings(tmp_path)
    artifacts = {
        "insights_final": [
            {
                "id": "i1",
                "text": "Conversion reached 37%.",
                "evidence_id": "e1",
                "evidence": "Conversion reached 37%.",
            }
        ],
        "quotes_final": [
            {
                "id": "q1",
                "text": "Conversion reached 37%.",
                "speaker": "Analyst",
                "citation": "Conversion reached 37%.",
                "evidence_id": "e1",
            }
        ],
        "expert_comment": "The figure remains 37 USD in planning discussions.",
        "linkedin_post": "Leaders can use 37 EUR as a simple shorthand figure.",
    }
    fake_openai = FakeOpenAI(
        semantic_payload={"metrics": [], "quotes": []},
        grounding_payload={"unsupported": []},
    )
    result = validate_report(
        ValidationRequest(
            schema_version="1.0",
            report_id="r-units-ignore",
            report=_report(),
            artifacts=artifacts,
            evidence_packs={},
            vector_store_id=None,
        ),
        settings,
        _ctx(),
        prompt_client=FakePromptClient(),
        openai_client=fake_openai,
        analysis_store=FakeAnalysisStore(),
    )
    assert result.status == "pass"
    assert not any("Number" in issue.message for issue in result.issues)


def test_grounding_unsupported_number_is_downgraded_when_numeric_value_matches(
    tmp_path,
):
    settings = _settings(tmp_path)
    artifacts = {
        "insights_final": [
            {
                "id": "i1",
                "text": "Adoption reached 37%.",
                "evidence_id": "e1",
                "evidence": "Adoption reached 37%.",
            }
        ],
        "quotes_final": [
            {
                "id": "q1",
                "text": "Adoption reached 37%.",
                "speaker": "Analyst",
                "citation": "Adoption reached 37%.",
                "evidence_id": "e1",
            }
        ],
        "expert_comment": "Adoption reached 37 USD by segment.",
    }
    fake_openai = FakeOpenAI(
        semantic_payload={"metrics": [], "quotes": []},
        grounding_payload={
            "unsupported": [
                {
                    "section": "expert_comment",
                    "text": "Adoption reached 37 USD by segment.",
                    "classification": "factual_claim",
                    "violation_type": "unsupported_number",
                    "reason": "No matching metric in evidence.",
                }
            ]
        },
    )
    result = validate_report(
        ValidationRequest(
            schema_version="1.0",
            report_id="r-grounding-units-ignore",
            report=_report(),
            artifacts=artifacts,
            evidence_packs={},
            vector_store_id=None,
        ),
        settings,
        _ctx(),
        prompt_client=FakePromptClient(),
        openai_client=fake_openai,
        analysis_store=FakeAnalysisStore(),
    )
    assert result.status == "pass"
    assert any(
        "normalized_quantity_supported" in issue.message for issue in result.issues
    )
    assert not any(issue.severity == "error" for issue in result.issues)


def test_validation_warns_on_data_gap(tmp_path):
    settings = _settings(tmp_path)
    artifacts = {
        "insights_final": [
            {
                "id": "i1",
                "text": "Insight text",
                "evidence_id": "e1",
                "evidence": "",
                "metric": {"value": "10", "unit": "%", "timeframe": "2024"},
            }
        ],
        "source_status": _low_text_status(),
    }
    fake_openai = FakeOpenAI({"unsupported": []})
    analysis_store = FakeAnalysisStore()
    result = validate_report(
        ValidationRequest(
            schema_version="1.0",
            report_id="low_text_report",
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
    assert result.status == "pass"
    assert result.severity == "warning"
    assert any(issue.severity == "warning" for issue in result.issues)


def test_validation_issue_order_preserved_with_parallel_checks(tmp_path):
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
        "quotes_final": [
            {"id": "q1", "text": "Outside quote", "speaker": "CEO", "citation": ""}
        ],
        "expert_comment": "We expect revenue to reach 99 soon.",
    }
    fake_openai = FakeOpenAI(
        semantic_payload={
            "metrics": [
                {
                    "id": "i1",
                    "supported": False,
                    "confidence": 0.9,
                    "reason": "Not grounded",
                }
            ],
            "quotes": [
                {
                    "id": "q1",
                    "supported": False,
                    "confidence": 0.9,
                    "reason": "Not grounded",
                }
            ],
        },
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
            report_id="r-order",
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

    messages = [issue.message for issue in result.issues]
    idx_semantic_metric = next(
        i
        for i, message in enumerate(messages)
        if "Semantic check: metric for i1 not supported" in message
    )
    idx_metric_exact = next(
        i
        for i, message in enumerate(messages)
        if "Metric value '10' not found in evidence" in message
    )
    idx_quote_exact = next(
        i
        for i, message in enumerate(messages)
        if "Quote not verbatim in evidence" in message
    )
    idx_number = next(
        i
        for i, message in enumerate(messages)
        if "Number 99.0 not present in report or evidence" in message
    )
    idx_grounding = next(
        i for i, message in enumerate(messages) if "No evidence: We expect" in message
    )

    assert (
        idx_semantic_metric
        < idx_metric_exact
        < idx_quote_exact
        < idx_number
        < idx_grounding
    )
    assert len([req for req in fake_openai.requests if req[0] == "chat"]) == 2


def test_validation_grounding_uses_chat_path_when_flag_disabled(tmp_path):
    settings = _settings(tmp_path, validation_grounding_use_vector_store=False)
    fake_openai = FakeOpenAI(
        semantic_payload={"metrics": [], "quotes": []},
        grounding_payload={"unsupported": []},
    )
    validate_report(
        ValidationRequest(
            schema_version="1.0",
            report_id="r-grounding-chat",
            report=_report(),
            artifacts={"insights_final": []},
            evidence_packs={},
            vector_store_id="vs_1",
        ),
        settings,
        _ctx(),
        prompt_client=FakePromptClient(),
        openai_client=fake_openai,
        analysis_store=FakeAnalysisStore(),
    )
    grounding_calls = [
        req for req in fake_openai.requests if req[2].endswith(":grounding")
    ]
    assert grounding_calls
    assert grounding_calls[0][0] == "chat"


def test_validation_grounding_uses_vector_path_when_flag_enabled(tmp_path):
    settings = _settings(tmp_path, validation_grounding_use_vector_store=True)
    fake_openai = FakeOpenAI(
        semantic_payload={"metrics": [], "quotes": []},
        grounding_payload={"unsupported": []},
    )
    validate_report(
        ValidationRequest(
            schema_version="1.0",
            report_id="r-grounding-vector",
            report=_report(),
            artifacts={"insights_final": []},
            evidence_packs={},
            vector_store_id="vs_1",
        ),
        settings,
        _ctx(),
        prompt_client=FakePromptClient(),
        openai_client=fake_openai,
        analysis_store=FakeAnalysisStore(),
    )
    grounding_calls = [
        req for req in fake_openai.requests if req[2].endswith(":grounding")
    ]
    assert grounding_calls
    assert grounding_calls[0][0] == "vector"


def test_validation_cache_isolated_by_grounding_retrieval_mode(tmp_path):
    artifacts = {"insights_final": []}
    request = ValidationRequest(
        schema_version="1.0",
        report_id="r-cache-mode",
        report=_report(),
        artifacts=artifacts,
        evidence_packs={},
        vector_store_id="vs_1",
    )
    chat_openai = FakeOpenAI(
        semantic_payload={"metrics": [], "quotes": []},
        grounding_payload={"unsupported": []},
    )
    validate_report(
        request,
        _settings(tmp_path, validation_grounding_use_vector_store=False),
        _ctx(),
        prompt_client=FakePromptClient(),
        openai_client=chat_openai,
        md5="md5-cache-mode",
        report_name="cache-mode-report",
    )
    chat_grounding_calls = [
        req for req in chat_openai.requests if req[2].endswith(":grounding")
    ]
    assert chat_grounding_calls
    assert chat_grounding_calls[0][0] == "chat"

    vector_openai = FakeOpenAI(
        semantic_payload={"metrics": [], "quotes": []},
        grounding_payload={"unsupported": []},
    )
    validate_report(
        request,
        _settings(tmp_path, validation_grounding_use_vector_store=True),
        _ctx(),
        prompt_client=FakePromptClient(),
        openai_client=vector_openai,
        md5="md5-cache-mode",
        report_name="cache-mode-report",
    )
    vector_grounding_calls = [
        req for req in vector_openai.requests if req[2].endswith(":grounding")
    ]
    assert vector_grounding_calls
    assert vector_grounding_calls[0][0] == "vector"


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
    assert any("abstained at confidence=0.41" in issue.message for issue in result.issues)


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
                {"claim": "Claim", "evidence_id": "f1", "evidence": "Evidence"}
            ],
        },
        "insights_final": [],
        "quotes_final": [
            {
                "id": "q1",
                "text": "Quoted text",
                "speaker": "Analyst",
                "citation": "Quoted text",
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
            "findings": [],
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
