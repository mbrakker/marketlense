from types import SimpleNamespace
from pathlib import Path
import sys
import json

sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.contracts.drive import DriveFile
from src.contracts.ingest import IngestOutcome, IngestSettings
from src.contracts.run_context import RunContext
from src.contracts.validation import ValidationReport
from src.contracts.report_assets import RenderResponse
from src.generators import report_generator as rg
from src.orchestrators import ingest_orchestrator as orch
from src.contracts.taxonomy import TaxonomyExtractResponse
from src.utils.slugify import slugify


def _ingest_settings(tmp_path):
    cover_style_path = Path(__file__).resolve().parents[1] / "src" / "config" / "cover-styles.yaml"
    return IngestSettings(
        schema_version="1.0",
        google_sa_path="sa.json",
        gdrive_folder_id="folder",
        openai_api_key="key",
        openai_model="gpt-4.1-mini",
        batch_limit=1,
        output_dir=str(tmp_path / "out"),
        cache_dir=str(tmp_path / "cache"),
        state_db=str(tmp_path / "state.sqlite"),
        reports_db=str(tmp_path / "reports.sqlite"),
        category_mapping_path="cats.yaml",
        cover_style_path=str(cover_style_path),
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
        model_pricing={},
    )


def test_ensure_vector_store_creates_and_waits(monkeypatch, tmp_path):
    settings = _ingest_settings(tmp_path)
    ctx = RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")
    file = DriveFile(schema_version="1.0", file_id="file_1", name="report.pdf", modified_time=None, md5_checksum="md5", version=None)
    calls: list[str] = []

    monkeypatch.setattr(rg.state_service, "get", lambda req, ctx: None)
    monkeypatch.setattr(
        rg.vector_store_service,
        "create_vector_store",
        lambda req, ctx: calls.append("create") or SimpleNamespace(vector_store_id="vs_123"),
    )
    monkeypatch.setattr(
        rg.vector_store_service,
        "upload_file",
        lambda req, ctx: calls.append("upload") or SimpleNamespace(openai_file_id="file_upload_1"),
    )
    monkeypatch.setattr(
        rg.vector_store_service,
        "attach_file",
        lambda req, ctx: calls.append("attach") or None,
    )
    monkeypatch.setattr(
        rg.vector_store_service,
        "wait_until_indexed",
        lambda req, ctx: calls.append("wait")
        or SimpleNamespace(status="completed", indexed_at_utc="2024-01-01T00:00:00Z", last_error=None),
    )
    vector_store_id, openai_file_id, status, indexed_at_utc, last_error = rg._ensure_vector_store(
        file, "local.pdf", settings, ctx
    )

    assert calls == ["create", "upload", "attach", "wait"]
    assert vector_store_id == "vs_123"
    assert openai_file_id == "file_upload_1"
    assert status == "completed"
    assert indexed_at_utc == "2024-01-01T00:00:00Z"
    assert last_error is None


def test_ingest_orchestrator_records_vector_events(monkeypatch, tmp_path):
    settings = _ingest_settings(tmp_path)
    file = DriveFile(schema_version="1.0", file_id="file", name="name.pdf", modified_time=None, md5_checksum="md5", version=None)
    outcome = IngestOutcome(
        schema_version="1.0",
        file_id=file.file_id,
        name=file.name,
        md5="md5",
        html_path="out/name.html",
        status="processed",
        vector_store_id="vs_1",
        vector_store_status="completed",
        indexed_at_utc="2024-01-01T00:00:00Z",
        openai_file_id="file_upload_1",
        evidence_packs={"doc_map": "path"},
        vector_store_last_error=None,
    )
    events = []
    state_records = []

    monkeypatch.setattr(orch, "acquire_lock", lambda req, ctx: SimpleNamespace(acquired=True, lock=SimpleNamespace(lock_path=req.lock_path, owner_id=req.owner_id, pid=req.pid), conflict=None))
    monkeypatch.setattr(orch, "release_lock", lambda req, ctx: None)
    monkeypatch.setattr(orch, "flush_uncategorized_tags", lambda req, ctx: None)
    monkeypatch.setattr(orch, "list_pdfs", lambda req, ctx: [file])
    monkeypatch.setattr(orch, "download_pdf", lambda req, ctx: SimpleNamespace(content=b"pdf-bytes", md5="md5"))
    monkeypatch.setattr(orch, "file_exists", lambda req, ctx: SimpleNamespace(exists=False))
    monkeypatch.setattr(orch, "write_bytes", lambda req, ctx: SimpleNamespace(md5="md5"))
    monkeypatch.setattr(orch, "check_pdf_eof", lambda req, ctx: SimpleNamespace(has_eof=True))
    monkeypatch.setattr(orch, "state_already_processed", lambda req, ctx: False)
    monkeypatch.setattr(orch, "file_md5", lambda req, ctx: SimpleNamespace(md5="md5"))
    monkeypatch.setattr(orch, "generate_report", lambda file, cache_path, settings, md5, ctx: outcome)

    def _record_state(req, ctx):
        state_records.append(req)

    monkeypatch.setattr(orch, "state_record", _record_state)
    monkeypatch.setattr(orch.logger, "info", lambda payload: events.append(payload))

    results = orch.run_ingest(settings, limit=1)

    assert results[0].vector_store_id == "vs_1"
    decoded = []
    for evt in events:
        try:
            decoded.append(json.loads(evt))
        except Exception:
            continue
    assert any(e.get("event") == "VECTOR_STORE_CREATED" for e in decoded)
    assert any(e.get("event") == "EVIDENCE_READY" for e in decoded)
    assert state_records, "state_record should be invoked"
    rec = state_records[0]
    assert rec.vector_store_id == "vs_1"
    assert rec.vector_store_status == "completed"
    assert rec.indexed_at_utc == "2024-01-01T00:00:00Z"
    assert rec.openai_file_id == "file_upload_1"


def test_generate_report_vector_store_with_validation(monkeypatch, tmp_path):
    settings = _ingest_settings(tmp_path)
    settings = settings.__class__(**{**settings.__dict__, "openai_timeout_seconds": 3600.0})
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")

    file = DriveFile(schema_version="1.0", file_id="file_vs", name="vector.pdf", modified_time=None, md5_checksum="md5", version=None)
    validation_calls = []
    analysis_store = []
    vector_calls = []
    ctx = RunContext(schema_version="1.0", run_id="run-vs", task_id="task-vs", span_id="span-vs")

    monkeypatch.setattr(rg.state_service, "get", lambda req, ctx: None)
    monkeypatch.setattr(rg.vector_store_service, "create_vector_store", lambda req, ctx: SimpleNamespace(vector_store_id="vs_new") if vector_calls.append(("create", req.name)) is None else SimpleNamespace(vector_store_id="vs_new"))
    monkeypatch.setattr(rg.vector_store_service, "upload_file", lambda req, ctx: SimpleNamespace(openai_file_id="file_upload") if vector_calls.append(("upload", req.vector_store_id, req.file_path)) is None else SimpleNamespace(openai_file_id="file_upload"))
    monkeypatch.setattr(rg.vector_store_service, "attach_file", lambda req, ctx: vector_calls.append(("attach", req.vector_store_id, req.openai_file_id)))
    monkeypatch.setattr(rg.vector_store_service, "wait_until_indexed", lambda req, ctx: vector_calls.append(("wait", req.timeout_s, req.poll_interval_s)) or SimpleNamespace(status="completed", indexed_at_utc="2024-01-01T00:00:00Z", last_error=None))
    monkeypatch.setattr(rg, "extract_pdf_info", lambda req, ctx: SimpleNamespace(schema_version="1.0", path=req.path, page_count=1, metadata={"k": "v"}))
    monkeypatch.setattr(rg, "build_pdf_context", lambda req, ctx: SimpleNamespace(schema_version="1.0", context=SimpleNamespace(fitz_doc=None, pypdf_reader=None, close=lambda: None), fitz_error=None, pypdf_error=None))
    monkeypatch.setattr(rg, "detect_contents_page_service", lambda req, ctx: SimpleNamespace(schema_version="1.0", path=req.path, has_contents=False, page_index=-1, page_number=0, heading="", confidence=0.0))
    monkeypatch.setattr(rg, "extract_pdf_text", lambda req, ctx: SimpleNamespace(schema_version="1.0", text="text", pages_extracted=1, char_count=4, text_density=4.0))
    monkeypatch.setattr(rg, "load_category_mappings", lambda req, ctx: SimpleNamespace(mappings=SimpleNamespace(schema_version="1.0", categories=[], uncategorized=[])))
    monkeypatch.setattr(rg, "categorize_taxonomy", lambda taxonomy, mappings, ctx: SimpleNamespace(categories=["cat"], category_labels=["Category"], unmapped_tags=[]))
    monkeypatch.setattr(rg, "update_uncategorized_tags", lambda req, ctx: None)
    monkeypatch.setattr(rg, "extract_best_figure_service", lambda req, ctx: SimpleNamespace(image_path=None, caption=None))
    monkeypatch.setattr(rg, "collect_candidates_service", lambda req, ctx: SimpleNamespace(candidates=[]))
    monkeypatch.setattr(rg, "render_preview_service", lambda req, ctx: SimpleNamespace(schema_version="1.1", image_path=str(tmp_path / "preview.png"), page_number=0))
    monkeypatch.setattr(rg, "extract_taxonomy", lambda req, ctx: TaxonomyExtractResponse(schema_version="1.0", taxonomy=["tag"], region="US", time_period="2024"))
    monkeypatch.setattr(rg.vector_store_service, "update_metadata", lambda req, ctx: None)

    def _fake_evidence(report_id, vector_store_id, settings, ctx, **kwargs):
        assert settings.openai_timeout_seconds == 3600.0
        return {
            "doc_map": {"doc_id": "d"},
            "scope": {},
            "methods": {},
            "findings": {},
            "limitations": {},
            "quote_candidates": {},
        }

    monkeypatch.setattr(rg, "generate_evidence_packs", _fake_evidence)
    def _fake_artifacts(report_id, doc_map, evidence_packs, settings, vector_store_id=None, source_status=None, ctx=None, report_name=None, **kwargs):
        payload = {
            "summary": {"tldr": "tldr", "executive_summary": "exec"},
            "insights_final": [{"text": "insight"}],
            "quotes_final": [{"text": "qt", "speaker": "sp"}],
        }
        rg.report_analysis_store_service.store_pack(
            settings.output_dir,
            report_id,
            "artifacts",
            payload,
            ctx,
            report_slug=report_name,
        )
        return payload

    monkeypatch.setattr(rg, "generate_artifacts", _fake_artifacts)
    monkeypatch.setattr(
        rg.report_analysis_store_service,
        "store_pack",
        lambda output_dir, report_id, pack_name, payload, ctx, **kwargs: analysis_store.append((pack_name, payload))
        or str(Path(output_dir) / slugify(kwargs.get("report_slug") or report_id) / "report_analysis" / f"{pack_name}.json"),
    )

    def _fake_validation(req, settings, ctx, pack_name="validation", **kwargs):
        validation_calls.append(req.report_id)
        slug = slugify(kwargs.get("report_name") or req.report_id)
        return ValidationReport(
            schema_version="1.1",
            status="pass",
            severity="pass",
            issues=[],
            source_path=str(Path(settings.output_dir) / slug / "report_analysis" / f"{pack_name}.json"),
        )

    monkeypatch.setattr(rg, "run_validation", _fake_validation)
    def _fake_render_report(req, ctx):
        html_path = tmp_path / "out.html"
        html_path.write_text("<html></html>", encoding="utf-8")
        return RenderResponse(schema_version="1.0", html_path=str(html_path))

    monkeypatch.setattr(rg, "render_report_service", _fake_render_report)
    monkeypatch.setattr(rg, "upsert_report_metadata", lambda req, ctx: None)

    outcome = rg.generate_report(file, str(pdf_path), settings, md5="md5", ctx=ctx)

    assert outcome.status == "processed"
    assert outcome.vector_store_id == "vs_new"
    assert "doc_map" in outcome.evidence_packs
    assert "validation" in outcome.evidence_packs
    assert Path(outcome.html_path).exists()
    assert validation_calls == ["file_vs"]
    assert ("artifacts", {"summary": {"tldr": "tldr", "executive_summary": "exec"}, "insights_final": [{"text": "insight"}], "quotes_final": [{"text": "qt", "speaker": "sp"}]}) in analysis_store
