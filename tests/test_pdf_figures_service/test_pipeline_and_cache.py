from __future__ import annotations

from .builders import *  # noqa: F401,F403


def test_visual_probe_profile_reuses_shared_raster_cache():
    doc = fitz.open()
    try:
        page = doc.new_page(width=300, height=240)
        page.draw_rect(fitz.Rect(40, 40, 220, 160), color=(0, 0, 0), width=1.5)
        page.draw_line(
            fitz.Point(60, 135), fitz.Point(200, 85), color=(0, 0, 1), width=2
        )
        rect = fitz.Rect(35, 35, 225, 165)
        cache = _RasterProbeCache(images={}, profiles={})

        first = _visual_probe_profile(page, rect, probe_cache=cache)
        second = _visual_probe_profile(page, rect, probe_cache=cache)

        assert first == second
        assert first is not None
        stats = cache.stats()
        assert stats["hits"] >= 1
        assert stats["misses"] >= 1
        assert stats["image_entries"] == 1
        assert stats["profile_entries"] == 1
    finally:
        doc.close()


def test_collect_candidates_returns_chart_and_table_contracts(
    tmp_path,
    caplog,
    assert_logs_have_required_fields,
    assert_no_defaulted_required_fields,
) -> None:
    pdf_path = tmp_path / "candidates.pdf"
    out_dir = tmp_path / "out"
    _build_candidates_pdf(pdf_path)

    caplog.set_level(
        logging.INFO, logger="market_lense.pdf_service.candidate_extraction"
    )

    response = collect_candidates(
        ExtractCandidatesRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="report",
        ),
        _ctx(),
    )

    assert response.candidates
    kinds = {candidate.kind for candidate in response.candidates}
    assert "chart" in kinds
    assert "table" in kinds
    assert_no_defaulted_required_fields(response)
    for candidate in response.candidates:
        assert_no_defaulted_required_fields(candidate)
        assert isinstance(candidate.features, CandidateFeatures)
        assert candidate.features.ocr_density >= 0.0
        assert 0.0 <= candidate.features.visual_entropy <= 1.0
        if candidate.kind == "chart":
            assert candidate.features.chart_confidence > 0.0
            assert candidate.meta is not None
            assert "chart_confidence" in candidate.meta
        if candidate.kind == "table":
            assert candidate.features.table_confidence > 0.0
            assert candidate.meta is not None
            assert "table_confidence" in candidate.meta

    events = _events(caplog, "market_lense.pdf_service.candidate_extraction")
    assert_logs_have_required_fields(events)
    event_names = {str(event["event"]) for event in events}
    assert {"extract_candidates_start", "extract_candidates_complete"} <= event_names
    complete = next(
        event for event in events if event.get("event") == "extract_candidates_complete"
    )
    complete_fields = cast(dict[str, Any], complete.get("fields") or {})
    page_triage_records = complete_fields.get("page_triage_records") or []
    assert page_triage_records
    assert {"page", "score", "threshold", "action", "reasons"} <= set(
        page_triage_records[0]
    )
    assert response.stats.page_triage_records
    assert response.stats.page_triage_evaluated_count == len(
        response.stats.page_triage_records
    )


def test_pdf_page_artifact_cache_reused_across_candidate_and_crop_passes(
    tmp_path,
    caplog,
) -> None:
    pdf_path = tmp_path / "candidates-cache.pdf"
    out_dir = tmp_path / "out"
    _build_candidates_pdf(pdf_path)

    caplog.set_level(logging.INFO, logger="market_lense.pdf_service")
    caplog.set_level(
        logging.INFO, logger="market_lense.pdf_service.candidate_extraction"
    )
    caplog.set_level(logging.INFO, logger="market_lense.pdf_service.crop")

    context_response = build_pdf_context(
        PdfContextBuildRequest(schema_version="1.0", path=pdf_path.as_posix()),
        _ctx(),
    )
    pdf_context = context_response.context
    try:
        cache = pdf_context.page_artifact_cache

        assert cache is not None
        assert cache.stats()["artifact_entries"] == 0

        candidates_response = collect_candidates(
            ExtractCandidatesRequest(
                schema_version="1.0",
                pdf_path=pdf_path.as_posix(),
                out_dir=out_dir.as_posix(),
                report_name="cache-report",
                pdf_context=pdf_context,
            ),
            _ctx(),
        )

        chart_candidate = next(
            candidate
            for candidate in candidates_response.candidates
            if candidate.kind == "chart"
        )
        after_collect_stats = cache.stats()

        assert after_collect_stats["artifact_entries"] >= 1
        assert after_collect_stats["misses"] >= 1

        crop_response = crop_regions(
            CropRequest(
                schema_version="1.0",
                pdf_path=pdf_path.as_posix(),
                out_dir=out_dir.as_posix(),
                report_name="cache-report",
                subdir="candidates",
                items=[
                    CropItem(
                        id=chart_candidate.id,
                        type=chart_candidate.kind,
                        score=1.0,
                        page=chart_candidate.page,
                        bbox=chart_candidate.bbox,
                    )
                ],
                pdf_context=pdf_context,
            ),
            _ctx(),
        )

        after_crop_stats = cache.stats()

        assert len(crop_response.paths) == 1
        assert (
            after_crop_stats["artifact_entries"]
            == after_collect_stats["artifact_entries"]
        )
        assert after_crop_stats["text_block_pair_entries"] >= 1
        assert after_crop_stats["hits"] > after_collect_stats["hits"]

        candidate_events = _events(
            caplog,
            "market_lense.pdf_service.candidate_extraction",
        )
        candidate_complete = next(
            event
            for event in candidate_events
            if event.get("event") == "extract_candidates_complete"
        )
        candidate_fields = cast(dict[str, Any], candidate_complete.get("fields") or {})
        candidate_cache = cast(
            dict[str, Any],
            candidate_fields.get("page_artifact_cache") or {},
        )
        assert int(candidate_cache.get("artifact_entries", 0)) >= 1

        crop_events = _events(caplog, "market_lense.pdf_service.crop")
        crop_complete = next(
            event
            for event in crop_events
            if event.get("event") == "crop_regions_complete"
        )
        crop_fields = cast(dict[str, Any], crop_complete.get("fields") or {})
        crop_cache = cast(dict[str, Any], crop_fields.get("page_artifact_cache") or {})
        assert int(crop_cache.get("artifact_entries", 0)) >= 1
        assert int(crop_cache.get("text_block_pair_entries", 0)) >= 1
    finally:
        pdf_context.close()


def test_collect_candidates_skips_full_page_scan_without_text(tmp_path, caplog) -> None:
    pdf_path = tmp_path / "full-page-scan.pdf"
    out_dir = tmp_path / "out"
    _build_full_page_scan_pdf(pdf_path)

    caplog.set_level(
        logging.INFO, logger="market_lense.pdf_service.candidate_extraction"
    )

    response = collect_candidates(
        ExtractCandidatesRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="full-page-scan",
        ),
        _ctx(),
    )

    assert response.candidates == []
    events = _events(caplog, "market_lense.pdf_service.candidate_extraction")
    complete = next(
        event for event in events if event.get("event") == "extract_candidates_complete"
    )
    complete_fields = cast(dict[str, Any], complete.get("fields") or {})
    assert int(complete_fields.get("triaged_full_scan_pages", 0)) == 1


def test_candidate_page_plan_records_triage_failure_include_policy() -> None:
    plan = _plan_candidate_pages(
        _ExplodingTriageDoc(),
        set(),
        artifact_cache=create_page_artifact_cache(),
        degraded_page_policy="include_with_warning",
    )

    assert plan.chart_pages == [0]
    assert plan.table_pages == [0]
    assert len(plan.degraded_pages) == 1
    assert plan.degraded_pages[0].reason_code == "pdf_candidate_page_triage_failed"
    assert plan.degraded_pages[0].policy == "include_with_warning"


def test_candidate_page_plan_records_triage_failure_skip_policy() -> None:
    plan = _plan_candidate_pages(
        _ExplodingTriageDoc(),
        set(),
        artifact_cache=create_page_artifact_cache(),
        degraded_page_policy="skip_with_warning",
    )

    assert plan.chart_pages == []
    assert plan.table_pages == []
    assert plan.degraded_pages[0].policy == "skip_with_warning"


def test_candidate_page_plan_fails_on_triage_failure_fail_policy() -> None:
    try:
        _plan_candidate_pages(
            _ExplodingTriageDoc(),
            set(),
            artifact_cache=create_page_artifact_cache(),
            degraded_page_policy="fail",
        )
    except AppError as exc:
        assert exc.code == "pdf_candidate_page_triage_failed"
        assert exc.context["page"] == 0
    else:
        raise AssertionError("fail policy must raise AppError")


def test_candidate_page_plan_scores_and_skips_low_value_pages() -> None:
    doc = fitz.open()
    try:
        prose_page = doc.new_page(width=420, height=560)
        prose_page.insert_textbox(
            fitz.Rect(40, 60, 380, 220),
            "This page contains narrative context without figures, tables, or metrics.",
            fontsize=11,
        )
        chart_page = doc.new_page(width=420, height=560)
        chart_page.insert_text((48, 42), "Figure 1. Quarterly growth", fontsize=12)
        chart_page.draw_rect(fitz.Rect(60, 110, 360, 360), color=(0, 0, 0), width=1.2)
        chart_page.draw_line(
            fitz.Point(80, 320), fitz.Point(330, 150), color=(0, 0, 1), width=2.0
        )
        table_page = doc.new_page(width=420, height=560)
        table_page.insert_textbox(
            fitz.Rect(45, 70, 390, 230),
            (
                "Table 2. Market size\n"
                "Region 2023 2024 2025\n"
                "North America 12.5 14.0 15.2\n"
                "Europe 8.2 8.9 9.4\n"
                "Asia 15.1 17.4 19.0\n"
            ),
            fontsize=10,
        )
        trailing_prose = doc.new_page(width=420, height=560)
        trailing_prose.insert_textbox(
            fitz.Rect(40, 60, 380, 220),
            "Additional prose without visual extraction value.",
            fontsize=11,
        )

        plan = _plan_candidate_pages(
            doc,
            set(),
            artifact_cache=create_page_artifact_cache(),
            page_gate_enabled=True,
            page_gate_min_score=0.25,
            page_gate_min_recall_pages=0,
            page_gate_min_recall_page_fraction=0.0,
        )
    finally:
        doc.close()

    assert plan.chart_pages == [1, 2]
    assert plan.table_pages == [1, 2]
    assert [record.action for record in plan.page_triage_records] == [
        "skip_low_score",
        "include_score",
        "include_score",
        "skip_low_score",
    ]
    assert plan.page_triage_records[1].score >= 0.25
    assert "visual_drawing_signal" in plan.page_triage_records[1].reasons
    assert "tabular_text_signal" in plan.page_triage_records[2].reasons


def test_candidate_page_plan_recall_floor_includes_top_scoring_pages() -> None:
    doc = fitz.open()
    try:
        for page_index in range(4):
            page = doc.new_page(width=420, height=560)
            page.insert_textbox(
                fitz.Rect(40, 60, 380, 220),
                f"Low-signal prose page {page_index} with limited metric detail.",
                fontsize=11,
            )

        plan = _plan_candidate_pages(
            doc,
            set(),
            artifact_cache=create_page_artifact_cache(),
            page_gate_enabled=True,
            page_gate_min_score=0.99,
            page_gate_min_recall_pages=0,
            page_gate_min_recall_page_fraction=0.5,
        )
    finally:
        doc.close()

    assert len(plan.chart_pages or []) == 2
    assert plan.chart_pages == plan.table_pages
    assert sum(
        1
        for record in plan.page_triage_records
        if record.action == "include_recall_floor"
    ) == 2
    assert plan.page_triage_skipped_pages == 2


def test_extract_best_figure_writes_asset_and_logs(
    tmp_path,
    caplog,
    assert_logs_have_required_fields,
    assert_no_defaulted_required_fields,
) -> None:
    pdf_path = tmp_path / "figure.pdf"
    out_dir = tmp_path / "out"
    _build_candidates_pdf(pdf_path)

    caplog.set_level(logging.INFO, logger="market_lense.pdf_service.figure")

    response = extract_best_figure(
        FigureExtractRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="report",
        ),
        _ctx(),
    )

    assert response.image_path == "report/assets/report.png"
    assert response.caption == "Figure 1. Synthetic chart"
    assert response.page == 0
    assert (out_dir / response.image_path).exists()
    assert_no_defaulted_required_fields(response)

    events = _events(caplog, "market_lense.pdf_service.figure")
    assert_logs_have_required_fields(events)
    event_names = {str(event["event"]) for event in events}
    assert {"figure_extract_start", "figure_extract_complete"} <= event_names


def test_extract_best_figure_compacts_filename_for_long_report_slug(tmp_path) -> None:
    pdf_path = tmp_path / "figure.pdf"
    out_dir = tmp_path.parent / "lf"
    _build_candidates_pdf(pdf_path)
    report_name = (
        "institute-for-canadian-citizenship-retention-trends-in-highly-skilled-"
        "immigrants-and-in-demand-occupations-acig-pdf"
    )

    response = extract_best_figure(
        FigureExtractRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name=report_name,
        ),
        _ctx(),
    )

    assert response.image_path is not None
    artifact_path = out_dir / response.image_path
    assert artifact_path.is_file()
    assert artifact_path.name.startswith("figure-")
    assert len(artifact_path.name) <= 96


def test_extract_best_figure_sanitizes_report_name_segment(tmp_path) -> None:
    pdf_path = tmp_path / "figure_escape.pdf"
    out_dir = tmp_path / "out"
    _build_candidates_pdf(pdf_path)

    response = extract_best_figure(
        FigureExtractRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=out_dir.as_posix(),
            report_name="../escape",
        ),
        _ctx(),
    )

    assert response.image_path == "escape/assets/escape.png"
    assert (out_dir / response.image_path).exists()
