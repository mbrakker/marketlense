from pathlib import Path
from types import SimpleNamespace

from src.contracts.candidates import Candidate
from src.contracts.ingest import IngestSettings
from src.contracts.report_assets import CropRefineResponse, CropRefineResult
from src.contracts.report_models import RankedCandidate
from src.contracts.run_context import RunContext
from src.generators import report_generator as rg


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="run", task_id="task", span_id="span")


def _settings(tmp_path, **overrides) -> IngestSettings:
    cover_style_path = Path(__file__).resolve().parents[1] / "src" / "config" / "cover-styles.yaml"
    base = IngestSettings(
        schema_version="1.0",
        google_sa_path="sa.json",
        gdrive_folder_id="folder",
        openai_api_key="key",
        openai_model="gpt-5-mini",
        batch_limit=1,
        output_dir=str(tmp_path / "out"),
        cache_dir=str(tmp_path / "cache"),
        state_db=str(tmp_path / "state.sqlite"),
        reports_db=str(tmp_path / "reports.sqlite"),
        category_mapping_path="cats.yaml",
        cover_style_path=str(cover_style_path),
        ingest_lock_path=str(tmp_path / "lock"),
        temperature=0.0,
    )
    payload = {**base.__dict__, **overrides}
    return IngestSettings(**payload)


def _candidate(
    *,
    cid: str,
    kind: str,
    page: int = 0,
    bbox=(10.0, 10.0, 300.0, 220.0),
    caption: str = "",
    preview_text: str = "",
    meta: dict | None = None,
) -> Candidate:
    return Candidate(
        schema_version="1.0",
        id=cid,
        kind=kind,
        page=page,
        bbox=bbox,
        caption=caption,
        preview_text=preview_text,
        meta=meta or {},
    )


def _patch_prompts(monkeypatch):
    prompt_set = SimpleNamespace(
        system=SimpleNamespace(path="system.yaml", sha256="sys", text="sys"),
        user=SimpleNamespace(path="user.yaml", sha256="usr", text="usr"),
    )
    monkeypatch.setattr(rg, "load_prompt_set", lambda req, ctx: prompt_set)
    monkeypatch.setattr(rg, "render_prompt", lambda req, ctx: SimpleNamespace(text="rendered"))


def test_refine_selection_adaptive_obvious_pass_skips_llm(monkeypatch, tmp_path):
    settings = _settings(tmp_path, crop_refine_enabled=True, crop_refine_mode="adaptive")
    _patch_prompts(monkeypatch)
    llm_calls: list[int] = []

    def _fail_if_called(*args, **kwargs):
        llm_calls.append(1)
        raise AssertionError("LLM refine should not be called for obvious pass")

    monkeypatch.setattr(rg, "refine_candidate_crops_service", _fail_if_called)
    monkeypatch.setattr(
        rg,
        "apply_crop_refine_bbox_service",
        lambda req, ctx: SimpleNamespace(schema_version="1.0", page=req.page, bbox=req.bbox),
    )

    cand = _candidate(
        cid="table_1",
        kind="table",
        meta={"rows": 6, "cols": 4, "numeric_ratio": 0.25, "area_frac": 0.11},
    )
    ranked = [
        RankedCandidate(
            id="table_1",
            type="table",
            score=92,
            quality_score=90,
            insight_score=91,
            data_score=93,
            keep=True,
        )
    ]
    items, accepted = rg._select_refined_candidate_items(
        ranked_rows=ranked,
        ranked_candidates=[cand],
        settings=settings,
        local_pdf_path=str(tmp_path / "dummy.pdf"),
        report_name="report",
        file_id="file",
        md5=None,
        ctx=_ctx(),
        pdf_context=None,
        fallback_model="gpt-5-mini",
    )

    assert llm_calls == []
    assert len(items) == 1
    assert len(accepted) == 1
    assert items[0].id == "table_1"


def test_refine_selection_adaptive_ambiguous_calls_llm(monkeypatch, tmp_path):
    settings = _settings(tmp_path, crop_refine_enabled=True, crop_refine_mode="adaptive")
    _patch_prompts(monkeypatch)
    llm_calls: list[int] = []
    refined_bbox = (16.0, 18.0, 360.0, 310.0)

    monkeypatch.setattr(
        rg,
        "render_page_for_crop_refine_service",
        lambda req, ctx: SimpleNamespace(
            schema_version="1.0",
            image_path="report/crop_refine_pages/page-0.png",
            page=req.page,
            image_width=1200,
            image_height=1600,
            page_width=600.0,
            page_height=800.0,
            scale_x=2.0,
            scale_y=2.0,
        ),
    )

    def _refine(req, ctx):
        llm_calls.append(1)
        return CropRefineResponse(
            schema_version="1.0",
            results=[
                CropRefineResult(
                    schema_version="1.0",
                    id="chart_1",
                    is_valid_candidate=True,
                    refined_bbox=refined_bbox,
                    include_title=True,
                    include_note_if_present=True,
                    confidence=0.9,
                    reason="valid",
                )
            ],
            raw_content='{"results":[{"id":"chart_1"}]}',
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            request_id="req",
        )

    monkeypatch.setattr(rg, "refine_candidate_crops_service", _refine)
    monkeypatch.setattr(
        rg,
        "apply_crop_refine_bbox_service",
        lambda req, ctx: SimpleNamespace(schema_version="1.0", page=req.page, bbox=req.bbox),
    )

    cand = _candidate(
        cid="chart_1",
        kind="chart",
        meta={"area_frac": 0.08, "text_ratio": 0.42},
    )
    ranked = [
        RankedCandidate(
            id="chart_1",
            type="chart",
            score=90,
            quality_score=88,
            insight_score=89,
            data_score=84,
            keep=True,
        )
    ]
    items, accepted = rg._select_refined_candidate_items(
        ranked_rows=ranked,
        ranked_candidates=[cand],
        settings=settings,
        local_pdf_path=str(tmp_path / "dummy.pdf"),
        report_name="report",
        file_id="file",
        md5=None,
        ctx=_ctx(),
        pdf_context=None,
        fallback_model="gpt-5-mini",
    )

    # Adaptive LLM refine runs a two-pass sequence: coarse + finalize.
    assert llm_calls == [1, 1]
    assert len(items) == 1
    assert len(accepted) == 1
    assert tuple(items[0].bbox) == refined_bbox


def test_refine_selection_early_stops_at_selected_max(monkeypatch, tmp_path):
    settings = _settings(tmp_path, crop_refine_enabled=True, crop_refine_mode="adaptive", rank_selected_max=5)
    _patch_prompts(monkeypatch)
    apply_calls: list[str] = []

    monkeypatch.setattr(
        rg,
        "refine_candidate_crops_service",
        lambda req, ctx: (_ for _ in ()).throw(AssertionError("LLM should not be called for obvious-pass tables")),
    )

    def _apply(req, ctx):
        apply_calls.append(req.page)
        return SimpleNamespace(schema_version="1.0", page=req.page, bbox=req.bbox)

    monkeypatch.setattr(rg, "apply_crop_refine_bbox_service", _apply)

    candidates = []
    ranked_rows = []
    for idx in range(8):
        cid = f"table_{idx}"
        candidates.append(
            _candidate(
                cid=cid,
                kind="table",
                page=idx,
                meta={"rows": 5, "cols": 4, "numeric_ratio": 0.3, "area_frac": 0.12},
            )
        )
        ranked_rows.append(
            RankedCandidate(
                id=cid,
                type="table",
                score=95 - idx,
                quality_score=95 - idx,
                insight_score=95 - idx,
                data_score=95 - idx,
                keep=True,
            )
        )

    items, accepted = rg._select_refined_candidate_items(
        ranked_rows=ranked_rows,
        ranked_candidates=candidates,
        settings=settings,
        local_pdf_path=str(tmp_path / "dummy.pdf"),
        report_name="report",
        file_id="file",
        md5=None,
        ctx=_ctx(),
        pdf_context=None,
        fallback_model="gpt-5-mini",
    )

    assert len(items) == 5
    assert len(accepted) == 5
    assert len(apply_calls) == 5
