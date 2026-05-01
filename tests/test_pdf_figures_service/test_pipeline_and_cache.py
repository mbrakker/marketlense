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
