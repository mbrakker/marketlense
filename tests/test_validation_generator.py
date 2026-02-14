from types import SimpleNamespace
import json
import threading
from pathlib import Path

from src.contracts.config import AppSettings
from src.contracts.prompts import PromptSet, PromptTemplate
from src.contracts.report_models import Figure, Quote, ReportPayload
from src.contracts.run_context import RunContext
from src.contracts.validation import ValidationRequest
from src.contracts.openai import OpenAIResponseResult
from src.generators.validation_generator import validate_report
from src.utils.slugify import slugify


class FakePromptClient:
    def load_prompt_set(self, request, ctx):
        tmpl = PromptTemplate(schema_version="1.0", path=f"{request.namespace}/system", text="system", sha256="s")
        user = PromptTemplate(schema_version="1.0", path=f"{request.namespace}/user", text="user {{ report_json }}", sha256="u")
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
            self.requests.append(("vector", req.vector_store_id, str(getattr(ctx, "task_id", ""))))
        return self.openai_chat_json(req, ctx)


class FakeAnalysisStore:
    def __init__(self):
        self.stored = []

    def store_pack(self, output_dir, report_id, pack_name, payload, ctx, report_slug=None, mirror_legacy=True):
        slug = slugify(report_slug or report_id)
        path = Path(output_dir) / slug / "report_analysis" / f"{pack_name}.json"
        self.stored.append((output_dir, report_id, pack_name, payload))
        return str(path)


def _settings(tmp_path):
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
        category_mapping_path="cats.yaml",
        cover_style_path=str(Path(__file__).resolve().parents[1] / "src" / "config" / "cover-styles.yaml"),
        ingest_lock_path=str(tmp_path / "lock"),
        ingest_lock_ttl_seconds=1.0,
        temperature=0.1,
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
        analysis_mode="vector_store",
        use_vector_store=True,
        vector_store_keep=True,
        cost_ledger_path=str(tmp_path / "cost-ledger.jsonl"),
        cost_daily_path=str(tmp_path / "cost-daily.json"),
        model_pricing={"gpt-4.1-mini": {"input_tokens_per_1k_usd": 0.003, "output_tokens_per_1k_usd": 0.006, "tool_call_usd": 0.0}},
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
            {"id": "i1", "text": "Insight text", "evidence_id": "e1", "evidence": "Growth was 5%", "metric": {"value": "10", "unit": "%", "timeframe": "2024"}},
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
            {"id": "q1", "text": "Revenue grew ten percent YoY", "speaker": "CEO", "citation": "The CEO noted a year-over-year increase of ten pct."},
        ],
    }
    semantic_payload = {
        "metrics": [{"id": "i1", "supported": True, "confidence": 0.82, "reason": "Paraphrase matches evidence"}],
        "quotes": [{"id": "q1", "supported": True, "confidence": 0.81, "reason": "Meaning preserved"}],
    }
    grounding_payload = {"unsupported": []}
    fake_openai = FakeOpenAI(semantic_payload=semantic_payload, grounding_payload=grounding_payload)
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
        "insights_final": [{"id": "i1", "text": "Insight 1", "evidence_id": "e1", "evidence": "Revenue up 5%", "metric": {"value": "5", "unit": "%", "timeframe": "2024"}}],
        "expert_comment": "We expect revenue to reach 99 soon.",
    }
    fake_openai = FakeOpenAI(
        semantic_payload={"metrics": [], "quotes": []},
        grounding_payload={"unsupported": [{"section": "expert_comment", "text": "We expect", "reason": "No evidence"}]},
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
        "summary": {"tldr": "TLDR", "executive_summary": "Exec 42%", "claim_evidence_map": []},
        "insights_final": [],
        "quotes_final": [{"text": "Revenue grew 42% year over year", "speaker": "CEO", "citation": "Revenue grew 42% year over year", "evidence_id": "f1"}],
        "expert_comment": "We expect revenue to stay around 42% growth.",
        "linkedin_post": "Analysts noted 42% expansion.",
    }
    evidence_packs = {"pack": {"findings": [{"id": "f1", "evidence": "Revenue grew 42% year over year"}]}}
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


def test_validation_warns_on_data_gap(tmp_path):
    settings = _settings(tmp_path)
    artifacts = {
        "insights_final": [{"id": "i1", "text": "Insight text", "evidence_id": "e1", "evidence": "", "metric": {"value": "10", "unit": "%", "timeframe": "2024"}}],
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
            {"id": "i1", "text": "Insight text", "evidence_id": "e1", "evidence": "Growth was 5%", "metric": {"value": "10", "unit": "%", "timeframe": "2024"}},
        ],
        "quotes_final": [{"id": "q1", "text": "Outside quote", "speaker": "CEO", "citation": ""}],
        "expert_comment": "We expect revenue to reach 99 soon.",
    }
    fake_openai = FakeOpenAI(
        semantic_payload={
            "metrics": [{"id": "i1", "supported": False, "confidence": 0.9, "reason": "Not grounded"}],
            "quotes": [{"id": "q1", "supported": False, "confidence": 0.9, "reason": "Not grounded"}],
        },
        grounding_payload={"unsupported": [{"section": "expert_comment", "text": "We expect", "reason": "No evidence"}]},
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
    idx_semantic_metric = next(i for i, message in enumerate(messages) if "Semantic check: metric for i1 not supported" in message)
    idx_metric_exact = next(i for i, message in enumerate(messages) if "Metric value '10' not found in evidence" in message)
    idx_quote_exact = next(i for i, message in enumerate(messages) if "Quote not verbatim in evidence" in message)
    idx_number = next(i for i, message in enumerate(messages) if "Number 99.0 not present in report or evidence" in message)
    idx_grounding = next(i for i, message in enumerate(messages) if "No evidence: We expect" in message)

    assert idx_semantic_metric < idx_metric_exact < idx_quote_exact < idx_number < idx_grounding
    assert len([req for req in fake_openai.requests if req[0] == "chat"]) == 2
