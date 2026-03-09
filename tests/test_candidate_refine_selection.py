from pathlib import Path
from pypdf import PdfWriter

from src.contracts.candidates import Candidate
from src.contracts.ingest import IngestSettings
from src.contracts.report_assets import CropRefineResponse, CropRefineResult
from src.contracts.report_models import RankedCandidate
from src.contracts.run_context import RunContext
from src.generators import report_generator as rg


def _ctx() -> RunContext:
    return RunContext(
        schema_version="1.0", run_id="run", task_id="task", span_id="span"
    )


def _settings(tmp_path, **overrides) -> IngestSettings:
    cover_style_path = (
        Path(__file__).resolve().parents[1] / "src" / "config" / "cover-styles.yaml"
    )
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


def _pdf_path(tmp_path: Path) -> str:
    path = tmp_path / "dummy.pdf"
    writer = PdfWriter()
    for _ in range(10):
        writer.add_blank_page(width=600, height=800)
    with path.open("wb") as handle:
        writer.write(handle)
    return str(path)


def test_refine_selection_adaptive_obvious_pass_skips_llm(monkeypatch, tmp_path):
    settings = _settings(
        tmp_path, crop_refine_enabled=True, crop_refine_mode="adaptive"
    )
    llm_calls: list[int] = []

    def _fail_if_called(*args, **kwargs):
        llm_calls.append(1)
        raise AssertionError("LLM refine should not be called for obvious pass")

    monkeypatch.setattr(rg, "refine_candidate_crops_service", _fail_if_called)

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
        local_pdf_path=_pdf_path(tmp_path),
        report_name="report",
        file_id="file",
        md5=None,
        ctx=_ctx(),
        pdf_context=None,
        fallback_model="gpt-5-mini",
        selected_kind_max=max(1, int(settings.rank_selected_max)),
    )

    assert llm_calls == []
    assert len(items) == 1
    assert len(accepted) == 1
    assert items[0].id == "table_1"


def test_refine_selection_adaptive_ambiguous_calls_llm(monkeypatch, tmp_path):
    settings = _settings(
        tmp_path, crop_refine_enabled=True, crop_refine_mode="adaptive"
    )
    llm_calls: list[int] = []
    refined_bbox = (16.0, 18.0, 360.0, 310.0)

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
        local_pdf_path=_pdf_path(tmp_path),
        report_name="report",
        file_id="file",
        md5=None,
        ctx=_ctx(),
        pdf_context=None,
        fallback_model="gpt-5-mini",
        selected_kind_max=max(1, int(settings.rank_selected_max)),
    )

    # Adaptive LLM refine runs a two-pass sequence: coarse + finalize.
    assert llm_calls == [1, 1]
    assert len(items) == 1
    assert len(accepted) == 1
    assert items[0].bbox[0] < refined_bbox[0]
    assert items[0].bbox[1] < refined_bbox[1]
    assert items[0].bbox[2] > refined_bbox[2]
    assert items[0].bbox[3] > refined_bbox[3]


def test_refine_selection_early_stops_at_selected_max(monkeypatch, tmp_path):
    settings = _settings(
        tmp_path,
        crop_refine_enabled=True,
        crop_refine_mode="adaptive",
        rank_selected_max=5,
    )

    monkeypatch.setattr(
        rg,
        "refine_candidate_crops_service",
        lambda req, ctx: (_ for _ in ()).throw(
            AssertionError("LLM should not be called for obvious-pass tables")
        ),
    )

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
        local_pdf_path=_pdf_path(tmp_path),
        report_name="report",
        file_id="file",
        md5=None,
        ctx=_ctx(),
        pdf_context=None,
        fallback_model="gpt-5-mini",
        selected_kind_max=max(1, int(settings.rank_selected_max)),
    )

    assert len(items) == 5
    assert len(accepted) == 5


def test_refine_selection_enforces_per_kind_limit(tmp_path):
    settings = _settings(
        tmp_path, crop_refine_enabled=False, crop_refine_mode="off", rank_selected_max=1
    )

    candidates = [
        _candidate(
            cid="table_a",
            kind="table",
            page=0,
            meta={"rows": 6, "cols": 4, "numeric_ratio": 0.3, "area_frac": 0.2},
        ),
        _candidate(
            cid="table_b",
            kind="table",
            page=1,
            meta={"rows": 6, "cols": 4, "numeric_ratio": 0.3, "area_frac": 0.2},
        ),
        _candidate(
            cid="chart_a",
            kind="chart",
            page=2,
            caption="Figure 1",
            meta={"area_frac": 0.2, "text_ratio": 0.2},
        ),
        _candidate(
            cid="chart_b",
            kind="chart",
            page=3,
            caption="Figure 2",
            meta={"area_frac": 0.2, "text_ratio": 0.2},
        ),
    ]
    ranked_rows = [
        RankedCandidate(
            id="table_a",
            type="table",
            score=99,
            quality_score=99,
            insight_score=99,
            data_score=99,
            keep=True,
        ),
        RankedCandidate(
            id="table_b",
            type="table",
            score=98,
            quality_score=98,
            insight_score=98,
            data_score=98,
            keep=True,
        ),
        RankedCandidate(
            id="chart_a",
            type="chart",
            score=97,
            quality_score=97,
            insight_score=97,
            data_score=97,
            keep=True,
        ),
        RankedCandidate(
            id="chart_b",
            type="chart",
            score=96,
            quality_score=96,
            insight_score=96,
            data_score=96,
            keep=True,
        ),
    ]

    items, accepted = rg._select_refined_candidate_items(
        ranked_rows=ranked_rows,
        ranked_candidates=candidates,
        settings=settings,
        local_pdf_path=_pdf_path(tmp_path),
        report_name="report",
        file_id="file",
        md5=None,
        ctx=_ctx(),
        pdf_context=None,
        fallback_model="gpt-5-mini",
        selected_kind_max=1,
    )

    assert len(items) == 2
    assert len(accepted) == 2
    assert {item.type for item in items} == {"table", "chart"}


def test_select_fallback_candidate_crop_paths_prefers_ranked_order(tmp_path):
    candidates = [
        _candidate(
            cid="table_a",
            kind="table",
            page=0,
            meta={"rows": 6, "cols": 4, "numeric_ratio": 0.3, "area_frac": 0.2},
        ),
        _candidate(
            cid="chart_a",
            kind="chart",
            page=1,
            caption="Figure 1",
            meta={"area_frac": 0.18, "text_ratio": 0.2},
        ),
        _candidate(
            cid="chart_b",
            kind="chart",
            page=2,
            caption="Figure 2",
            meta={"area_frac": 0.2, "text_ratio": 0.2},
        ),
    ]
    ranked_rows = [
        RankedCandidate(
            id="chart_b",
            type="chart",
            score=97,
            quality_score=97,
            insight_score=97,
            data_score=97,
            keep=False,
            reject_reason="model_reject",
        ),
        RankedCandidate(
            id="table_a",
            type="table",
            score=91,
            quality_score=91,
            insight_score=91,
            data_score=91,
            keep=False,
            reject_reason="model_reject",
        ),
    ]

    paths, selected, stats = rg._select_fallback_candidate_crop_paths(
        ranked_rows=ranked_rows,
        prefiltered_candidates=candidates,
        candidate_path_by_id={
            "table_a": "report/candidates/table_a.png",
            "chart_a": "report/candidates/chart_a.png",
            "chart_b": "report/candidates/chart_b.png",
        },
        selected_kind_max=1,
    )

    assert paths == [
        "report/candidates/chart_b.png",
        "report/candidates/table_a.png",
    ]
    assert [candidate.id for candidate in selected] == ["chart_b", "table_a"]
    assert stats["selected_by_source"] == {"ranked": 2}


def test_select_fallback_candidate_crop_paths_skips_obvious_rejects():
    candidates = [
        _candidate(
            cid="bad_chart",
            kind="chart",
            page=0,
            meta={"area_frac": 0.04, "text_ratio": 0.95},
        ),
        _candidate(
            cid="good_chart",
            kind="chart",
            page=1,
            caption="Figure 3",
            meta={"area_frac": 0.18, "text_ratio": 0.2},
        ),
    ]
    ranked_rows = [
        RankedCandidate(
            id="bad_chart",
            type="chart",
            score=99,
            quality_score=99,
            insight_score=99,
            data_score=99,
            keep=False,
            reject_reason="model_reject",
        )
    ]

    paths, selected, stats = rg._select_fallback_candidate_crop_paths(
        ranked_rows=ranked_rows,
        prefiltered_candidates=candidates,
        candidate_path_by_id={
            "bad_chart": "report/candidates/bad_chart.png",
            "good_chart": "report/candidates/good_chart.png",
        },
        selected_kind_max=1,
    )

    assert paths == ["report/candidates/good_chart.png"]
    assert [candidate.id for candidate in selected] == ["good_chart"]
    assert stats["rejected_reasons"] == {"chart_text_fragment": 1}


def test_resolve_figure_section_assets_enables_primary_image_without_gallery():
    gallery, top, enabled = rg._resolve_figure_section_assets(
        [],
        "report/assets/figure.png",
    )

    assert gallery == []
    assert top == "report/assets/figure.png"
    assert enabled is True


def test_resolve_figure_section_assets_disables_without_any_asset():
    gallery, top, enabled = rg._resolve_figure_section_assets([], "")

    assert gallery == []
    assert top == ""
    assert enabled is False
