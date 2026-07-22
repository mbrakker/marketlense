# ruff: noqa: F401,F403,F405
from __future__ import annotations

from src.generators._report_selection_generator import figure_selection

from ._shared import *  # noqa: F401,F403


def test_prefilter_uses_typed_candidate_features_without_meta():
    table = Candidate(
        schema_version="1.0",
        id="typed_table",
        kind="table",
        page=0,
        bbox=(10.0, 10.0, 300.0, 220.0),
        caption="",
        preview_text="",
        meta={},
        features=CandidateFeatures(
            schema_version="1.0",
            area_frac=0.12,
            rows=6,
            cols=4,
            numeric_ratio=0.25,
            avg_words_per_cell=1.8,
        ),
    )
    chart = Candidate(
        schema_version="1.0",
        id="typed_chart",
        kind="chart",
        page=0,
        bbox=(10.0, 10.0, 300.0, 220.0),
        caption="Figure 1",
        preview_text="",
        meta={},
        features=CandidateFeatures(
            schema_version="1.0",
            area_frac=0.14,
            text_ratio=0.2,
        ),
    )

    assert rsg._candidate_prefilter_reject_reason(table) == ""
    assert rsg._candidate_prefilter_reject_reason(chart) == ""
    assert rsg._candidate_is_obvious_pass(table) is True
    assert rsg._candidate_is_obvious_pass(chart) is True


def test_rank_candidate_batches_bound_each_model_response_to_four_candidates(
    tmp_path,
):
    settings = _settings(tmp_path)
    candidates = [
        _candidate(
            cid=f"chart_{index}",
            kind="chart",
            caption="Figure",
            meta={"area_frac": 0.2, "text_ratio": 0.2},
        )
        for index in range(9)
    ]
    calls: list[list[str]] = []

    def _render_prompt(req, ctx):
        return SimpleNamespace(text=req.variables.get("candidates_json", "system"))

    def _rank_candidates(req, ctx):
        identifiers = [item["id"] for item in json.loads(req.user_prompt)]
        calls.append(identifiers)
        return SimpleNamespace(
            results=[
                RankedCandidate(
                    id=identifier,
                    type="chart",
                    score=90,
                    quality_score=90,
                    insight_score=90,
                    data_score=90,
                    keep=True,
                )
                for identifier in identifiers
            ],
            prompt_tokens=1,
            completion_tokens=1,
            total_tokens=2,
            request_id="rank",
            raw_content="[]",
        )

    ranked, usage = figure_selection._rank_candidate_batches(
        table_candidates=[],
        chart_candidates=candidates,
        runtime=SimpleNamespace(
            settings=settings,
            ctx=_ctx(),
            report_worker_limit=1,
            parallel_within_file=False,
        ),
        dependencies=_deps(
            render_prompt=_render_prompt,
            rank_candidates=_rank_candidates,
        ),
    )

    assert [len(call) for call in calls] == [4, 4, 1]
    assert [row.id for row in ranked] == [candidate.id for candidate in candidates]
    assert usage == {"prompt_tokens": 3, "completion_tokens": 3, "total_tokens": 6}


def test_rank_candidates_payload_includes_quality_signals(tmp_path, caplog):
    settings = _settings(
        tmp_path,
        rank_model="gpt-rank",
        model_pricing={
            "gpt-rank": {
                "input_tokens_per_1k_usd": 1.0,
                "output_tokens_per_1k_usd": 2.0,
                "tool_call_usd": 0.0,
            }
        },
    )
    captured_rows: list[dict[str, object]] = []
    caplog.set_level(logging.INFO, logger="market_lense.report_generator")

    def _render_prompt(req, ctx):
        if "candidates_json" in req.variables:
            captured_rows.extend(json.loads(req.variables["candidates_json"]))
        return SimpleNamespace(text=req.variables.get("candidates_json", "system"))

    def _rank_candidates(req, ctx):
        assert req.candidate_count == 1
        assert '"quality_signals"' in req.user_prompt
        assert req.run_budget is not None
        assert req.run_budget.usage_db_path == settings.usage_db_path
        assert req.run_budget.run_id == ctx.run_id
        return SimpleNamespace(
            results=[
                RankedCandidate(
                    id="chart_signals",
                    type="chart",
                    score=94,
                    quality_score=93,
                    insight_score=92,
                    data_score=91,
                    keep=True,
                )
            ],
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            request_id="rank",
            raw_content="{}",
        )

    deps = _deps(render_prompt=_render_prompt, rank_candidates=_rank_candidates)
    candidate = Candidate(
        schema_version="1.0",
        id="chart_signals",
        kind="chart",
        page=0,
        bbox=(10.0, 20.0, 300.0, 260.0),
        caption="Figure 1. Revenue growth",
        preview_text="Revenue 2024 2025 2026",
        meta={},
        features=CandidateFeatures(
            schema_version="1.0",
            area_frac=0.18,
            text_chars=72,
            text_ratio=0.2,
            ocr_density=4.0,
            visual_entropy=0.62,
            chart_confidence=0.84,
        ),
    )

    result = rsg._rank_candidates_batch(
        candidates=[candidate],
        kind="chart",
        settings=settings,
        ctx=_ctx(),
        dependencies=deps,
    )

    assert result.ranked[0].id == "chart_signals"
    assert captured_rows
    row = captured_rows[0]
    assert row["quality_signals"] == {
        "ocr_density": 4.0,
        "visual_entropy": 0.62,
        "chart_confidence": 0.84,
        "table_confidence": 0.0,
    }
    features = row["features"]
    assert isinstance(features, dict)
    assert "schema_version" not in features
    assert "method" not in features
    assert features["ocr_density"] == 4.0
    assert features["visual_entropy"] == 0.62
    assert features["chart_confidence"] == 0.84
    assert features["area_frac"] == 0.18
    assert features["text_chars"] == 72
    assert "rows" not in features

    payload_logs = [
        json.loads(record.message)
        for record in caplog.records
        if '"event": "rank_payload_profile"' in record.message
    ]
    assert len(payload_logs) == 1
    payload_fields = payload_logs[0]["fields"]
    assert payload_fields["candidate_kind"] == "chart"
    assert payload_fields["candidate_count"] == 1
    assert (
        payload_fields["legacy_payload_chars"] > payload_fields["compact_payload_chars"]
    )
    assert payload_fields["payload_chars_saved"] > 0
    assert (
        payload_fields["legacy_input_tokens_est"]
        > payload_fields["compact_input_tokens_est"]
    )
    assert payload_fields["input_tokens_saved_est"] > 0
    assert (
        payload_fields["legacy_input_cost_usd_est"]
        > payload_fields["compact_input_cost_usd_est"]
    )
    assert payload_fields["input_cost_saved_usd_est"] > 0.0


def test_rank_candidates_payload_compacts_table_fields_and_text(tmp_path):
    settings = _settings(tmp_path, rank_model="gpt-rank")
    captured_rows: list[dict[str, object]] = []

    def _render_prompt(req, ctx):
        if "candidates_json" in req.variables:
            captured_rows.extend(json.loads(req.variables["candidates_json"]))
        return SimpleNamespace(text=req.variables.get("candidates_json", "system"))

    def _rank_candidates(req, ctx):
        return SimpleNamespace(
            results=[
                RankedCandidate(
                    id="table_compact",
                    type="table",
                    score=95,
                    quality_score=93,
                    insight_score=90,
                    data_score=96,
                    keep=True,
                )
            ],
            prompt_tokens=12,
            completion_tokens=4,
            total_tokens=16,
            request_id="rank-table",
            raw_content="{}",
        )

    deps = _deps(render_prompt=_render_prompt, rank_candidates=_rank_candidates)
    candidate = Candidate(
        schema_version="1.0",
        id="table_compact",
        kind="table",
        page=4,
        bbox=(10.0, 20.0, 300.0, 260.0),
        caption="T" * 260,
        preview_text="P" * 300,
        meta={},
        features=CandidateFeatures(
            schema_version="1.0",
            area_frac=0.1564,
            aspect=1.8,
            text_lines=14,
            text_chars=180,
            text_ratio=0.42,
            rows=12,
            cols=5,
            numeric_ratio=0.4875,
            avg_words_per_cell=2.2222,
            ocr_density=3.4567,
            visual_entropy=0.98,
            chart_confidence=0.12,
            table_confidence=0.8123,
            method="vision-pass",
        ),
    )

    result = rsg._rank_candidates_batch(
        candidates=[candidate],
        kind="table",
        settings=settings,
        ctx=_ctx(),
        dependencies=deps,
    )

    assert result.ranked[0].id == "table_compact"
    row = captured_rows[0]
    assert len(row["title_or_caption"]) == 220
    assert len(row["table_preview"]) == 240
    assert row["quality_signals"] == {
        "ocr_density": 3.457,
        "visual_entropy": 0.98,
        "chart_confidence": 0.12,
        "table_confidence": 0.812,
    }
    assert row["features"] == {
        "area_frac": 0.156,
        "rows": 12,
        "cols": 5,
        "numeric_ratio": 0.487,
        "avg_words_per_cell": 2.222,
        "text_chars": 180,
        "ocr_density": 3.457,
        "table_confidence": 0.812,
    }


def test_prefilter_rejects_low_signal_chart_fragment():
    candidate = Candidate(
        schema_version="1.0",
        id="chart_fragment",
        kind="chart",
        page=0,
        bbox=(10.0, 10.0, 140.0, 70.0),
        caption="",
        preview_text="",
        meta={},
        features=CandidateFeatures(
            schema_version="1.0",
            area_frac=0.08,
            text_chars=12,
            text_ratio=0.05,
            visual_entropy=0.02,
            chart_confidence=0.18,
        ),
    )

    assert rsg._candidate_prefilter_reject_reason(candidate) == "chart_low_confidence"


def test_refine_selection_adaptive_obvious_pass_skips_llm(tmp_path):
    settings = _settings(
        tmp_path, crop_refine_enabled=True, crop_refine_mode="adaptive"
    )
    llm_calls: list[int] = []
    deps = _deps(
        refine_candidate_crops=lambda req, ctx: (
            llm_calls.append(1)
            or (_ for _ in ()).throw(
                AssertionError("LLM refine should not be called for obvious pass")
            )
        )
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
    items, accepted = rsg.select_refined_candidate_items(
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
        dependencies=deps,
    )

    assert llm_calls == []
    assert len(items) == 1
    assert len(accepted) == 1
    assert items[0].id == "table_1"


def test_refine_selection_adaptive_ambiguous_calls_llm(tmp_path):
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

    deps = _deps(
        render_prompt=lambda req, ctx: SimpleNamespace(
            text=f"phase:{req.variables.get('phase', '')}"
            if getattr(req, "variables", None)
            else "phase:"
        ),
        refine_candidate_crops=_refine,
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
    items, accepted = rsg.select_refined_candidate_items(
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
        dependencies=deps,
    )

    assert llm_calls == [1, 1]
    assert len(items) == 1
    assert len(accepted) == 1
    assert items[0].bbox[0] < refined_bbox[0]
    assert items[0].bbox[1] < refined_bbox[1]
    assert items[0].bbox[2] > refined_bbox[2]
    assert items[0].bbox[3] > refined_bbox[3]


def test_refine_selection_batches_same_page_candidates_by_phase(tmp_path):
    settings = _settings(tmp_path, crop_refine_enabled=True, crop_refine_mode="always")
    llm_calls: list[list[str]] = []

    def _refine(req, ctx):
        candidate_ids = [candidate.id for candidate in req.candidates]
        llm_calls.append(candidate_ids)
        return CropRefineResponse(
            schema_version="1.0",
            results=[
                CropRefineResult(
                    schema_version="1.0",
                    id=candidate.id,
                    is_valid_candidate=True,
                    refined_bbox=(
                        float(candidate.bbox[0]) + 6.0,
                        float(candidate.bbox[1]) + 6.0,
                        float(candidate.bbox[2]) + 18.0,
                        float(candidate.bbox[3]) + 18.0,
                    ),
                    include_title=True,
                    include_note_if_present=True,
                    confidence=0.9,
                    reason="valid",
                )
                for candidate in req.candidates
            ],
            raw_content='{"results":[]}',
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            request_id="req",
        )

    deps = _deps(refine_candidate_crops=_refine)
    candidates = [
        _candidate(
            cid="chart_1",
            kind="chart",
            page=0,
            bbox=(10.0, 10.0, 220.0, 180.0),
            meta={"area_frac": 0.08, "text_ratio": 0.42},
        ),
        _candidate(
            cid="chart_2",
            kind="chart",
            page=0,
            bbox=(240.0, 20.0, 520.0, 260.0),
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
            score=90,
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

    assert llm_calls == [["chart_1", "chart_2"], ["chart_1", "chart_2"]]
    assert len(items) == 2
    assert len(accepted) == 2
    assert [item.id for item in items] == ["chart_1", "chart_2"]


def test_refine_selection_batched_page_maps_mixed_valid_invalid_decisions(tmp_path):
    settings = _settings(tmp_path, crop_refine_enabled=True, crop_refine_mode="always")
    llm_calls: list[list[str]] = []

    def _refine(req, ctx):
        candidate_ids = [candidate.id for candidate in req.candidates]
        llm_calls.append(candidate_ids)
        if len(llm_calls) == 1:
            return CropRefineResponse(
                schema_version="1.0",
                results=[
                    CropRefineResult(
                        schema_version="1.0",
                        id="chart_keep",
                        is_valid_candidate=True,
                        refined_bbox=(18.0, 18.0, 300.0, 240.0),
                        include_title=True,
                        include_note_if_present=True,
                        confidence=0.94,
                        reason="valid",
                    ),
                    CropRefineResult(
                        schema_version="1.0",
                        id="chart_drop",
                        is_valid_candidate=False,
                        refined_bbox=(260.0, 22.0, 320.0, 80.0),
                        include_title=False,
                        include_note_if_present=False,
                        confidence=0.22,
                        reason="decorative",
                    ),
                ],
                raw_content='{"results":[]}',
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=15,
                request_id="req-1",
            )
        return CropRefineResponse(
            schema_version="1.0",
            results=[
                CropRefineResult(
                    schema_version="1.0",
                    id="chart_keep",
                    is_valid_candidate=True,
                    refined_bbox=(20.0, 20.0, 302.0, 242.0),
                    include_title=True,
                    include_note_if_present=True,
                    confidence=0.96,
                    reason="valid",
                )
            ],
            raw_content='{"results":[]}',
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            request_id="req-2",
        )

    deps = _deps(refine_candidate_crops=_refine)
    candidates = [
        _candidate(
            cid="chart_keep",
            kind="chart",
            page=0,
            bbox=(12.0, 12.0, 280.0, 220.0),
            meta={"area_frac": 0.08, "text_ratio": 0.42},
        ),
        _candidate(
            cid="chart_drop",
            kind="chart",
            page=0,
            bbox=(250.0, 18.0, 330.0, 90.0),
            meta={"area_frac": 0.05, "text_ratio": 0.61},
        ),
    ]
    ranked = [
        RankedCandidate(
            id="chart_keep",
            type="chart",
            score=93,
            quality_score=91,
            insight_score=92,
            data_score=89,
            keep=True,
        ),
        RankedCandidate(
            id="chart_drop",
            type="chart",
            score=89,
            quality_score=86,
            insight_score=84,
            data_score=81,
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

    assert llm_calls == [["chart_keep", "chart_drop"], ["chart_keep"]]
    assert [item.id for item in items] == ["chart_keep"]
    assert [candidate.id for candidate in accepted] == ["chart_keep"]


__all__ = [
    "test_prefilter_uses_typed_candidate_features_without_meta",
    "test_rank_candidate_batches_bound_each_model_response_to_four_candidates",
    "test_rank_candidates_payload_includes_quality_signals",
    "test_rank_candidates_payload_compacts_table_fields_and_text",
    "test_prefilter_rejects_low_signal_chart_fragment",
    "test_refine_selection_adaptive_obvious_pass_skips_llm",
    "test_refine_selection_adaptive_ambiguous_calls_llm",
    "test_refine_selection_batches_same_page_candidates_by_phase",
    "test_refine_selection_batched_page_maps_mixed_valid_invalid_decisions",
]
