from types import SimpleNamespace
from pathlib import Path

from src.contracts.config import AppSettings
from src.contracts.openai import OpenAIResponseResult
from src.contracts.prompts import PromptSet, PromptTemplate
from src.contracts.run_context import RunContext
from src.generators.evidence_pack_generator import generate_evidence_packs
from src.utils.slugify import slugify


class FakePromptClient:
    def load_prompt_set(self, request, ctx):
        tmpl = PromptTemplate(schema_version="1.0", path="system", text="sys", sha256="s")
        user = PromptTemplate(schema_version="1.0", path="user", text="user", sha256="u")
        return PromptSet(schema_version="1.0", system=tmpl, user=user)


class FakeOpenAIClient:
    def __init__(self, parsed):
        self._parsed = parsed

    def openai_respond_with_vector_store(self, req, ctx):
        return OpenAIResponseResult(
            schema_version="1.0",
            text="{}",
            parsed_json=self._parsed,
            input_tokens=10,
            output_tokens=20,
            tool_calls=0,
            model=req.model,
        )


class FakeAnalysisStore:
    def __init__(self):
        self.stored = []

    def store_pack(self, output_dir, report_id, pack_name, payload, ctx, report_slug=None, mirror_legacy=True):
        slug = slugify(report_slug or report_id)
        self.stored.append((report_id, pack_name, payload))
        return f"{output_dir}/{slug}/report_analysis/{pack_name}.json"


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
        analysis_mode="vector_store",
        use_vector_store=True,
        vector_store_keep=True,
        cost_ledger_path=str(tmp_path / "cost-ledger.jsonl"),
        cost_daily_path=str(tmp_path / "cost-daily.json"),
        model_pricing={"gpt-4.1-mini": {"input_tokens_per_1k_usd": 0.003, "output_tokens_per_1k_usd": 0.006, "tool_call_usd": 0.0}},
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
    assert packs["scope"]["not_found_reason"] == "model_returned_no_json"
