# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403

def test_refine_selection_recovers_missing_batched_decisions(tmp_path):
    settings = _settings(tmp_path, crop_refine_enabled=True, crop_refine_mode="always")
    llm_calls: list[tuple[str, list[str]]] = []

    def _refine(req, ctx):
        candidate_ids = [candidate.id for candidate in req.candidates]
        phase = "finalize" if "finalize" in req.user_prompt else "coarse"
        llm_calls.append((phase, candidate_ids))
        if phase == "coarse" and candidate_ids == ["chart_1", "chart_2"]:
            return CropRefineResponse(
                schema_version="1.0",
                results=[
                    CropRefineResult(
                        schema_version="1.0",
                        id="chart_1",
                        is_valid_candidate=True,
                        refined_bbox=(20.0, 20.0, 280.0, 220.0),
                        include_title=True,
                        include_note_if_present=True,
                        confidence=0.91,
                        reason="valid",
                    )
                ],
                raw_content='{"results":[]}',
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=15,
                request_id="req-coarse-batch",
            )
        return CropRefineResponse(
            schema_version="1.0",
            results=[
                CropRefineResult(
                    schema_version="1.0",
                    id=candidate.id,
                    is_valid_candidate=True,
                    refined_bbox=(
                        float(candidate.bbox[0]) + 5.0,
                        float(candidate.bbox[1]) + 5.0,
                        float(candidate.bbox[2]) + 10.0,
                        float(candidate.bbox[3]) + 10.0,
                    ),
                    include_title=True,
                    include_note_if_present=True,
                    confidence=0.93,
                    reason="valid",
                )
                for candidate in req.candidates
            ],
            raw_content='{"results":[]}',
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            request_id="req-ok",
        )

    deps = _deps(refine_candidate_crops=_refine)
    candidates = [
        _candidate(
            cid="chart_1",
            kind="chart",
            page=0,
            bbox=(12.0, 12.0, 260.0, 200.0),
            meta={"area_frac": 0.08, "text_ratio": 0.42},
        ),
        _candidate(
            cid="chart_2",
            kind="chart",
            page=0,
            bbox=(250.0, 16.0, 500.0, 240.0),
            meta={"area_frac": 0.09, "text_ratio": 0.38},
        ),
    ]
    ranked = [
        RankedCandidate(
            id="chart_1",
            type="chart",
            score=92,
            quality_score=90,
            insight_score=91,
            data_score=88,
            keep=True,
        ),
        RankedCandidate(
            id="chart_2",
            type="chart",
            score=91,
            quality_score=89,
            insight_score=88,
            data_score=87,
            keep=True,
        ),
    ]

    items, accepted = rsg.select_refined_candidate_items(
        ranked_rows=ranked,
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
        dependencies=deps,
    )

    assert llm_calls[:2] == [
        ("coarse", ["chart_1", "chart_2"]),
        ("coarse", ["chart_2"]),
    ]
    assert [item.id for item in items] == ["chart_1", "chart_2"]
    assert [candidate.id for candidate in accepted] == ["chart_1", "chart_2"]

def test_refine_selection_recovers_multiple_missing_decisions_without_rescanning(
    tmp_path,
    caplog,
):
    settings = _settings(tmp_path, crop_refine_enabled=True, crop_refine_mode="always")
    caplog.set_level(logging.WARNING, logger="market_lense.report_generator")
    candidate_id_eq_checks = {"count": 0}

    class TrackingId(str):
        __hash__ = str.__hash__

        def __eq__(self, other):
            candidate_id_eq_checks["count"] += 1
            return super().__eq__(other)

    ids = [TrackingId(f"chart_{idx}") for idx in range(1, 5)]
    llm_calls: list[tuple[str, list[str]]] = []

    def _result_for(candidate):
        return CropRefineResult(
            schema_version="1.0",
            id=candidate.id,
            is_valid_candidate=True,
            refined_bbox=(
                float(candidate.bbox[0]) + 5.0,
                float(candidate.bbox[1]) + 5.0,
                float(candidate.bbox[2]) + 10.0,
                float(candidate.bbox[3]) + 10.0,
            ),
            include_title=True,
            include_note_if_present=True,
            confidence=0.93,
            reason="valid",
        )

    def _refine(req, ctx):
        candidate_ids = [str(candidate.id) for candidate in req.candidates]
        phase = "finalize" if "finalize" in req.user_prompt else "coarse"
        llm_calls.append((phase, candidate_ids))
        results = [_result_for(req.candidates[0])] if len(req.candidates) > 1 else [
            _result_for(candidate) for candidate in req.candidates
        ]
        return CropRefineResponse(
            schema_version="1.0",
            results=results,
            raw_content='{"results":[]}',
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            request_id=f"req-{phase}",
        )

    deps = _deps(
        render_prompt=lambda req, ctx: SimpleNamespace(
            text=str(req.variables.get("phase") or "prompt")
        ),
        refine_candidate_crops=_refine,
    )
    candidates = [
        _candidate(
            cid=cid,
            kind="chart",
            page=0,
            bbox=(
                12.0 + (idx * 40.0),
                12.0,
                260.0 + (idx * 40.0),
                200.0,
            ),
            meta={"area_frac": 0.08, "text_ratio": 0.42},
        )
        for idx, cid in enumerate(ids)
    ]
    ranked = [
        RankedCandidate(
            id=cid,
            type="chart",
            score=95 - idx,
            quality_score=93 - idx,
            insight_score=92 - idx,
            data_score=91 - idx,
            keep=True,
        )
        for idx, cid in enumerate(ids)
    ]

    items, accepted = rsg.select_refined_candidate_items(
        ranked_rows=ranked,
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
        dependencies=deps,
    )

    assert llm_calls[:4] == [
        ("coarse", ["chart_1", "chart_2", "chart_3", "chart_4"]),
        ("coarse", ["chart_2"]),
        ("coarse", ["chart_3"]),
        ("coarse", ["chart_4"]),
    ]
    assert ("finalize", ["chart_2"]) in llm_calls
    assert ("finalize", ["chart_3"]) in llm_calls
    assert ("finalize", ["chart_4"]) in llm_calls
    assert [str(item.id) for item in items] == [
        "chart_1",
        "chart_2",
        "chart_3",
        "chart_4",
    ]
    assert [str(candidate.id) for candidate in accepted] == [
        "chart_1",
        "chart_2",
        "chart_3",
        "chart_4",
    ]
    recovery_events = [
        json.loads(record.message)
        for record in caplog.records
        if json.loads(record.message).get("event")
        == "crop_refine_batch_missing_decisions_recover"
    ]
    assert [
        (
            event["fields"]["phase"],
            event["fields"]["missing_candidate_ids"],
        )
        for event in recovery_events
    ] == [
        ("coarse", ["chart_2", "chart_3", "chart_4"]),
        ("finalize", ["chart_2", "chart_3", "chart_4"]),
    ]
    assert candidate_id_eq_checks["count"] <= len(candidates)

def test_refine_selection_early_stops_at_selected_max(tmp_path):
    settings = _settings(
        tmp_path,
        crop_refine_enabled=True,
        crop_refine_mode="adaptive",
        rank_selected_max=5,
    )
    deps = _deps(
        refine_candidate_crops=lambda req, ctx: (_ for _ in ()).throw(
            AssertionError("LLM should not be called for obvious-pass tables")
        )
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

    items, accepted = rsg.select_refined_candidate_items(
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
        dependencies=deps,
    )

    assert len(items) == 5
    assert len(accepted) == 5

def test_refine_selection_enforces_per_kind_limit(tmp_path):
    settings = _settings(
        tmp_path, crop_refine_enabled=False, crop_refine_mode="off", rank_selected_max=1
    )
    deps = _deps()
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

    items, accepted = rsg.select_refined_candidate_items(
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
        dependencies=deps,
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

    paths, selected, stats = rsg._select_fallback_candidate_crop_paths(
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

    paths, selected, stats = rsg._select_fallback_candidate_crop_paths(
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

def test_select_fallback_candidate_crop_paths_blocks_threshold_rejects_with_settings(
    tmp_path,
):
    settings = _settings(tmp_path, rank_min_overall_score=90)
    candidates = [
        _candidate(
            cid="chart_low",
            kind="chart",
            page=0,
            caption="Figure 1",
            meta={"area_frac": 0.2, "text_ratio": 0.2},
        ),
        _candidate(
            cid="table_ok",
            kind="table",
            page=1,
            meta={"rows": 6, "cols": 4, "numeric_ratio": 0.3, "area_frac": 0.2},
        ),
        _candidate(
            cid="chart_ok",
            kind="chart",
            page=2,
            caption="Figure 2",
            meta={"area_frac": 0.18, "text_ratio": 0.2},
        ),
    ]
    ranked_rows = [
        RankedCandidate(
            id="chart_low",
            type="chart",
            score=70,
            quality_score=95,
            insight_score=95,
            data_score=95,
            keep=True,
        ),
        RankedCandidate(
            id="table_ok",
            type="table",
            score=94,
            quality_score=94,
            insight_score=94,
            data_score=94,
            keep=True,
        ),
    ]

    paths, selected, stats = rsg._select_fallback_candidate_crop_paths(
        ranked_rows=ranked_rows,
        prefiltered_candidates=candidates,
        candidate_path_by_id={
            "chart_low": "report/candidates/chart_low.png",
            "table_ok": "report/candidates/table_ok.png",
            "chart_ok": "report/candidates/chart_ok.png",
        },
        selected_kind_max=1,
        settings=settings,
    )

    assert paths == [
        "report/candidates/table_ok.png",
        "report/candidates/chart_ok.png",
    ]
    assert [candidate.id for candidate in selected] == ["table_ok", "chart_ok"]
    assert stats["selected_by_source"] == {"ranked": 1, "prefilter": 1}
    assert stats["rejected_reasons"] == {"overall_below_threshold": 1}

def test_candidate_prefilter_rejects_obvious_table_text_blocks():
    figure_text_table = _candidate(
        cid="table_figure",
        kind="table",
        preview_text="| Figure 2.4. The costs of regulation in Europe and Australia are similar to the United States |",
        meta={
            "rows": 8,
            "cols": 5,
            "numeric_ratio": 0.014,
            "avg_words_per_cell": 17.25,
            "area_frac": 0.4562,
        },
    )
    reference_block = _candidate(
        cid="table_refs",
        kind="table",
        preview_text='IEA (2025a), "Energy and AI", https://www.iea.org/reports/energy-and-ai.',
        meta={
            "rows": 48,
            "cols": 5,
            "numeric_ratio": 0.107,
            "avg_words_per_cell": 2.31,
            "area_frac": 0.7055,
        },
    )
    large_text_block = _candidate(
        cid="table_text_block",
        kind="table",
        preview_text="The growth of stablecoins may also pose risks to banks. Companies with crypto-related business models...",
        meta={
            "rows": 29,
            "cols": 3,
            "numeric_ratio": 0.017,
            "avg_words_per_cell": 13.52,
            "area_frac": 0.4184,
        },
    )

    assert (
        rsg._candidate_prefilter_reject_reason(figure_text_table)
        == "table_figure_text_block"
    )
    assert (
        rsg._candidate_prefilter_reject_reason(reference_block)
        == "table_reference_text_block"
    )
    assert (
        rsg._candidate_prefilter_reject_reason(large_text_block)
        == "table_large_text_block"
    )

def test_candidate_prefilter_does_not_reject_arbitrary_doi_substrings():
    pseudo_reference = _candidate(
        cid="table_pseudo_reference",
        kind="table",
        preview_text="This table discusses pseudoi.org metrics without a reference URL.",
        meta={
            "rows": 48,
            "cols": 5,
            "numeric_ratio": 0.107,
            "avg_words_per_cell": 2.31,
            "area_frac": 0.7055,
        },
    )

    assert (
        rsg._candidate_prefilter_reject_reason(pseudo_reference)
        != "table_reference_text_block"
    )

def test_truncate_prefiltered_candidates_keeps_kind_balance():
    candidates = []
    for idx in range(60):
        candidates.append(
            _candidate(
                cid=f"table_{idx}",
                kind="table",
                page=idx,
                preview_text="Large text-heavy table candidate",
                meta={
                    "rows": 30 + idx,
                    "cols": 3,
                    "numeric_ratio": 0.02,
                    "avg_words_per_cell": 12.0,
                    "area_frac": 0.35,
                },
            )
        )
    for idx in range(25):
        candidates.append(
            _candidate(
                cid=f"chart_{idx}",
                kind="chart",
                page=idx,
                caption=f"Figure {idx}",
                meta={"area_frac": 0.22, "text_ratio": 0.2},
            )
        )

    selected, kind_counts = rsg._truncate_prefiltered_candidates(candidates, 40)

    assert len(selected) == 40
    assert kind_counts == {"table": 20, "chart": 20}
    assert sum(1 for candidate in selected if candidate.kind == "chart") == 20
    assert sum(1 for candidate in selected if candidate.kind == "table") == 20

def test_resolve_figure_section_assets_enables_primary_image_without_gallery():
    gallery, top, enabled = rsg._resolve_figure_section_assets(
        [],
        "report/assets/figure.png",
    )

    assert gallery == []
    assert top == "report/assets/figure.png"
    assert enabled is True

def test_resolve_figure_section_assets_disables_without_any_asset():
    gallery, top, enabled = rsg._resolve_figure_section_assets([], "")

    assert gallery == []
    assert top == ""
    assert enabled is False

__all__ = [
    "test_refine_selection_recovers_missing_batched_decisions",
    "test_refine_selection_recovers_multiple_missing_decisions_without_rescanning",
    "test_refine_selection_early_stops_at_selected_max",
    "test_refine_selection_enforces_per_kind_limit",
    "test_select_fallback_candidate_crop_paths_prefers_ranked_order",
    "test_select_fallback_candidate_crop_paths_skips_obvious_rejects",
    "test_select_fallback_candidate_crop_paths_blocks_threshold_rejects_with_settings",
    "test_candidate_prefilter_rejects_obvious_table_text_blocks",
    "test_candidate_prefilter_does_not_reject_arbitrary_doi_substrings",
    "test_truncate_prefiltered_candidates_keeps_kind_balance",
    "test_resolve_figure_section_assets_enables_primary_image_without_gallery",
    "test_resolve_figure_section_assets_disables_without_any_asset",
]
