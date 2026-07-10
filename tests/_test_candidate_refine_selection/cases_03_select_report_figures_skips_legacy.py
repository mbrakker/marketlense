# ruff: noqa: F401,F403,F405
from __future__ import annotations

import threading

from ._shared import *  # noqa: F401,F403


def test_select_report_figures_skips_legacy_best_figure_when_candidate_gallery_exists(
    tmp_path,
):
    settings = _settings(
        tmp_path,
        crop_refine_enabled=False,
        crop_refine_mode="off",
        rank_selected_max=1,
        rank_max_candidates=4,
    )
    candidate = _candidate(
        cid="chart_keep",
        kind="chart",
        page=0,
        caption="Figure 1. Strong chart",
        meta={"area_frac": 0.2, "text_ratio": 0.2},
    )
    figure_calls: list[str] = []
    crop_calls: list[tuple[str, str, list[str]]] = []
    deps = _deps(
        collect_candidates=lambda req, ctx: SimpleNamespace(candidates=[candidate]),
        extract_best_figure=lambda req, ctx: (
            figure_calls.append(req.pdf_path)
            or SimpleNamespace(
                image_path="report/assets/legacy.png",
                caption="legacy",
                page=0,
            )
        ),
        rank_candidates=lambda req, ctx: SimpleNamespace(
            results=[
                RankedCandidate(
                    id="chart_keep",
                    type="chart",
                    score=98,
                    quality_score=98,
                    insight_score=98,
                    data_score=98,
                    keep=True,
                )
            ],
            prompt_tokens=None,
            completion_tokens=None,
            total_tokens=None,
            request_id="rank",
            raw_content="[]",
        ),
        crop_regions=lambda req, ctx: (
            crop_calls.append(
                (
                    str(req.subdir or ""),
                    str(req.mode or ""),
                    [str(item.id or "") for item in req.items],
                )
            )
            or SimpleNamespace(
                paths=[f"report/{req.subdir or 'slices'}/{req.items[0].id}.png"]
            )
        ),
    )
    payload = ReportPayload(
        tldr="",
        title="Report",
        insights=[],
        quote=Quote(text="q"),
        figure=Figure(title="", evidence=""),
        commentary="",
        source="",
    )
    runtime = SimpleNamespace(
        local_pdf_path=_pdf_path(tmp_path),
        settings=settings,
        report_name="report",
        file=SimpleNamespace(file_id="file"),
        md5=None,
        ctx=_ctx(),
        report_worker_limit=1,
        parallel_within_file=False,
    )
    source = SimpleNamespace(
        payload=payload,
        contents_page_number=0,
        pdf_context=None,
        pdf_context_for_tasks=None,
    )

    selection = rsg.select_report_figures(runtime, source, deps)

    assert figure_calls == []
    assert crop_calls == [("slices", "chart_strict", ["chart_keep"])]
    assert selection.payload._figure_gallery == ["report/slices/chart_keep.png"]
    assert selection.payload._figure_top == "report/slices/chart_keep.png"
    assert selection.payload._figure_section_enabled is True


def test_select_report_figures_uses_configured_final_crop_dpi_for_selected_gallery(
    tmp_path,
):
    settings = _settings(
        tmp_path,
        crop_refine_enabled=False,
        crop_refine_mode="off",
        final_crop_dpi=216,
        rank_selected_max=1,
        rank_max_candidates=4,
    )
    table = _candidate(
        cid="table_keep",
        kind="table",
        page=0,
        preview_text="A | B\n1 | 2\n3 | 4\n5 | 6",
        meta={"rows": 5, "cols": 3, "numeric_ratio": 0.4, "area_frac": 0.18},
    )
    chart = _candidate(
        cid="chart_keep",
        kind="chart",
        page=1,
        caption="Figure 2. Strong chart",
        meta={"area_frac": 0.2, "text_ratio": 0.2},
    )
    crop_calls: list[tuple[str, int, list[str]]] = []

    def _crop_regions(req, ctx):
        crop_calls.append(
            (
                str(req.mode or ""),
                int(req.dpi),
                [str(item.id or "") for item in req.items],
            )
        )
        return SimpleNamespace(
            paths=[f"report/slices/{item.id}-{int(req.dpi)}.png" for item in req.items]
        )

    deps = _deps(
        collect_candidates=lambda req, ctx: SimpleNamespace(candidates=[table, chart]),
        extract_best_figure=lambda req, ctx: (_ for _ in ()).throw(
            AssertionError("legacy best-figure fallback should not run")
        ),
        rank_candidates=lambda req, ctx: SimpleNamespace(
            results=[
                RankedCandidate(
                    id="table_keep",
                    type="table",
                    score=99,
                    quality_score=99,
                    insight_score=99,
                    data_score=99,
                    keep=True,
                ),
                RankedCandidate(
                    id="chart_keep",
                    type="chart",
                    score=98,
                    quality_score=98,
                    insight_score=98,
                    data_score=98,
                    keep=True,
                ),
            ],
            prompt_tokens=None,
            completion_tokens=None,
            total_tokens=None,
            request_id="rank",
            raw_content="[]",
        ),
        crop_regions=_crop_regions,
    )
    payload = ReportPayload(
        tldr="",
        title="Report",
        insights=[],
        quote=Quote(text="q"),
        figure=Figure(title="", evidence=""),
        commentary="",
        source="",
    )
    runtime = SimpleNamespace(
        local_pdf_path=_pdf_path(tmp_path),
        settings=settings,
        report_name="report",
        file=SimpleNamespace(file_id="file"),
        md5=None,
        ctx=_ctx(),
        report_worker_limit=1,
        parallel_within_file=False,
    )
    source = SimpleNamespace(
        payload=payload,
        contents_page_number=0,
        pdf_context=None,
        pdf_context_for_tasks=None,
    )

    selection = rsg.select_report_figures(runtime, source, deps)

    assert crop_calls == [
        ("table_strict", 216, ["table_keep"]),
        ("chart_strict", 216, ["chart_keep"]),
    ]
    assert selection.payload._figure_gallery == [
        "report/slices/table_keep-216.png",
        "report/slices/chart_keep-216.png",
    ]


def test_select_report_figures_ranks_table_and_chart_batches_concurrently(
    tmp_path,
):
    settings = _settings(
        tmp_path,
        crop_refine_enabled=False,
        crop_refine_mode="off",
        rank_selected_max=1,
        rank_max_candidates=4,
    )
    table = _candidate(
        cid="table_keep",
        kind="table",
        page=0,
        preview_text="A | B\n1 | 2\n3 | 4\n5 | 6",
        meta={
            "area_frac": 0.2,
            "rows": 4,
            "cols": 3,
            "numeric_ratio": 0.5,
            "table_confidence": 0.9,
        },
    )
    chart = _candidate(
        cid="chart_keep",
        kind="chart",
        page=1,
        caption="Figure 1. Strong chart",
        meta={"area_frac": 0.2, "text_ratio": 0.2, "chart_confidence": 0.9},
    )
    lock = threading.Lock()
    both_started = threading.Event()
    started: list[str] = []

    def _render_prompt(req, ctx):
        return SimpleNamespace(text=str(req.variables.get("candidates_json") or ""))

    def _rank_candidates(req, ctx):
        kind = "table" if '"type":"table"' in req.user_prompt else "chart"
        with lock:
            started.append(kind)
            if len(started) == 2:
                both_started.set()
        if not both_started.wait(timeout=0.5):
            raise AssertionError("table and chart rank batches did not overlap")
        return SimpleNamespace(
            results=[
                RankedCandidate(
                    id=f"{kind}_keep",
                    type=kind,
                    score=98,
                    quality_score=98,
                    insight_score=98,
                    data_score=98,
                    keep=True,
                )
            ],
            prompt_tokens=None,
            completion_tokens=None,
            total_tokens=None,
            request_id=f"rank-{kind}",
            raw_content="[]",
        )

    deps = _deps(
        collect_candidates=lambda req, ctx: SimpleNamespace(candidates=[table, chart]),
        render_prompt=_render_prompt,
        rank_candidates=_rank_candidates,
        crop_regions=lambda req, ctx: SimpleNamespace(
            paths=[f"report/{item.id}.png" for item in req.items]
        ),
    )
    payload = ReportPayload(
        tldr="",
        title="Report",
        insights=[],
        quote=Quote(text="q"),
        figure=Figure(title="", evidence=""),
        commentary="",
        source="",
    )
    runtime = SimpleNamespace(
        local_pdf_path=_pdf_path(tmp_path),
        settings=settings,
        report_name="report",
        file=SimpleNamespace(file_id="file"),
        md5=None,
        ctx=_ctx(),
        report_worker_limit=2,
        parallel_within_file=True,
    )
    source = SimpleNamespace(
        payload=payload,
        contents_page_number=0,
        pdf_context=None,
        pdf_context_for_tasks=None,
    )

    selection = rsg.select_report_figures(runtime, source, deps)

    assert sorted(started) == ["chart", "table"]
    assert selection.payload._figure_section_enabled is True


def test_select_report_figures_reuses_existing_candidate_crops_for_fallback_gallery(
    tmp_path,
):
    settings = _settings(
        tmp_path,
        crop_refine_enabled=False,
        crop_refine_mode="off",
        rank_selected_max=1,
        rank_max_candidates=4,
    )
    candidate = _candidate(
        cid="chart_keep",
        kind="chart",
        page=0,
        caption="Figure 1. Strong chart",
        meta={"area_frac": 0.2, "text_ratio": 0.2},
    )
    figure_calls: list[str] = []
    deps = _deps(
        collect_candidates=lambda req, ctx: SimpleNamespace(candidates=[candidate]),
        extract_best_figure=lambda req, ctx: (
            figure_calls.append(req.pdf_path)
            or SimpleNamespace(
                image_path="report/assets/legacy.png",
                caption="legacy",
                page=0,
            )
        ),
        rank_candidates=lambda req, ctx: SimpleNamespace(
            results=[],
            prompt_tokens=None,
            completion_tokens=None,
            total_tokens=None,
            request_id="rank",
            raw_content="[]",
        ),
        read_json_object_cache=lambda req, ctx: SimpleNamespace(
            found=True,
            payload={
                "schema_version": "1.0",
                "candidates": [
                    {
                        "id": "chart_keep",
                        "crop_path": "report/candidates/chart_keep.png",
                    }
                ],
            },
        ),
        crop_regions=lambda req, ctx: (_ for _ in ()).throw(
            AssertionError("fallback crop pass should be skipped when crop paths exist")
        ),
    )
    payload = ReportPayload(
        tldr="",
        title="Report",
        insights=[],
        quote=Quote(text="q"),
        figure=Figure(title="", evidence=""),
        commentary="",
        source="",
    )
    runtime = SimpleNamespace(
        local_pdf_path=_pdf_path(tmp_path),
        settings=settings,
        report_name="report",
        file=SimpleNamespace(file_id="file"),
        md5=None,
        ctx=_ctx(),
        report_worker_limit=1,
        parallel_within_file=False,
    )
    source = SimpleNamespace(
        payload=payload,
        contents_page_number=0,
        pdf_context=None,
        pdf_context_for_tasks=None,
    )

    selection = rsg.select_report_figures(runtime, source, deps)

    assert figure_calls == []
    assert selection.payload._figure_gallery == ["report/candidates/chart_keep.png"]
    assert selection.payload._figure_top == "report/candidates/chart_keep.png"
    assert selection.payload._figure_section_enabled is True


def test_select_report_figures_crops_only_missing_fallback_candidates_after_reuse(
    tmp_path,
):
    settings = _settings(
        tmp_path,
        crop_refine_enabled=False,
        crop_refine_mode="off",
        rank_selected_max=1,
        rank_max_candidates=4,
    )
    table_candidate = _candidate(
        cid="table_keep",
        kind="table",
        page=0,
        meta={"rows": 6, "cols": 4, "numeric_ratio": 0.3, "area_frac": 0.2},
    )
    chart_candidate = _candidate(
        cid="chart_keep",
        kind="chart",
        page=1,
        caption="Figure 2. Strong chart",
        meta={"area_frac": 0.18, "text_ratio": 0.2},
    )
    crop_calls: list[tuple[str, str, list[str]]] = []
    deps = _deps(
        collect_candidates=lambda req, ctx: SimpleNamespace(
            candidates=[table_candidate, chart_candidate]
        ),
        extract_best_figure=lambda req, ctx: (_ for _ in ()).throw(
            AssertionError("legacy best-figure fallback should not run")
        ),
        rank_candidates=lambda req, ctx: SimpleNamespace(
            results=[],
            prompt_tokens=None,
            completion_tokens=None,
            total_tokens=None,
            request_id="rank",
            raw_content="[]",
        ),
        read_json_object_cache=lambda req, ctx: SimpleNamespace(
            found=True,
            payload={
                "schema_version": "1.0",
                "candidates": [
                    {
                        "id": "chart_keep",
                        "crop_path": "report/candidates/chart_keep.png",
                    }
                ],
            },
        ),
        crop_regions=lambda req, ctx: (
            crop_calls.append(
                (
                    str(req.subdir or ""),
                    str(req.mode or ""),
                    [str(item.id or "") for item in req.items],
                )
            )
            or SimpleNamespace(paths=["report/candidates/table_keep.png"])
        ),
    )
    payload = ReportPayload(
        tldr="",
        title="Report",
        insights=[],
        quote=Quote(text="q"),
        figure=Figure(title="", evidence=""),
        commentary="",
        source="",
    )
    runtime = SimpleNamespace(
        local_pdf_path=_pdf_path(tmp_path),
        settings=settings,
        report_name="report",
        file=SimpleNamespace(file_id="file"),
        md5=None,
        ctx=_ctx(),
        report_worker_limit=1,
        parallel_within_file=False,
    )
    source = SimpleNamespace(
        payload=payload,
        contents_page_number=0,
        pdf_context=None,
        pdf_context_for_tasks=None,
    )

    selection = rsg.select_report_figures(runtime, source, deps)

    assert crop_calls == [("candidates", "legacy", ["table_keep"])]
    assert selection.payload._figure_gallery == [
        "report/candidates/table_keep.png",
        "report/candidates/chart_keep.png",
    ]
    assert selection.payload._figure_top == "report/candidates/table_keep.png"
    assert selection.payload._figure_section_enabled is True


__all__ = [
    "test_select_report_figures_skips_legacy_best_figure_when_candidate_gallery_exists",
    "test_select_report_figures_uses_configured_final_crop_dpi_for_selected_gallery",
    "test_select_report_figures_ranks_table_and_chart_batches_concurrently",
    "test_select_report_figures_reuses_existing_candidate_crops_for_fallback_gallery",
    "test_select_report_figures_crops_only_missing_fallback_candidates_after_reuse",
]
