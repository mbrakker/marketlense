from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
from PIL import Image

from src.contracts.cover_images import (
    CoverImageGenerationRequest,
    CoverImageRenderRequest,
    CoverImageReport,
    CoverStyleLoadRequest,
)
from src.contracts.report_cards import CoverFingerprint
from src.contracts.run_context import RunContext
from src.generators.cover_image_generator import generate_cover_images
from src.services.cover_image_service import render_cover_image
from src.services.cover_style_service import load_cover_styles
from src.utils.errors import AppError
from src.utils.path_utils import (
    WINDOWS_COMPONENT_BUDGET,
    WINDOWS_PATH_BUDGET,
    is_windows_reserved_component,
    windows_path_units,
)

pytestmark = pytest.mark.integration

STYLE_PATH = (
    Path(__file__).resolve().parents[2] / "src" / "config" / "cover-styles.yaml"
)
LIVE_TITLE = (
    "Global Economic Conditions and Investment Outlook Across Major Markets "
    "Through the Second Half 2026."
)


def _ctx() -> RunContext:
    return RunContext(
        schema_version="1.0",
        run_id="cover-integration",
        task_id="render-assets",
        span_id="span-cover",
    )


def _fingerprint() -> CoverFingerprint:
    return CoverFingerprint(
        schema_version="1.0",
        geometry_family="forecast_horizon",
        evidence_shape="trend",
        direction="neutral",
        geography_scope="global",
        evidence_density="metric_rich",
        domain_layer="forecast",
        seed=1344902748,
        selection_reason="Forward projections dominate the report evidence.",
    )


def test_real_cover_renderer_writes_three_exact_assets_with_complete_title(
    tmp_path, caplog, assert_logs_have_required_fields
) -> None:
    assert len(LIVE_TITLE) == 100
    caplog.set_level(logging.INFO, logger="market_lense.cover_image_service")

    outcomes = generate_cover_images(
        CoverImageGenerationRequest(
            schema_version="2.0",
            output_dir=str(tmp_path / "out"),
            style_config_path=str(STYLE_PATH),
            reports=[
                CoverImageReport(
                    schema_version="2.0",
                    file_id="drive-123",
                    title=LIVE_TITLE,
                    publisher="Market Lense Research",
                    report_slug="global-economic-conditions",
                    time_period="Q2 2026",
                    region="Global",
                    fingerprint=_fingerprint(),
                )
            ],
        ),
        _ctx(),
    )

    assert len(outcomes) == 1
    assert outcomes[0].status == "generated"
    assets = outcomes[0].assets
    assert assets is not None
    assert Image.open(assets.small.output_path).size == (1600, 900)
    assert Image.open(assets.medium.output_path).size == (1200, 1500)
    assert Image.open(assets.large.output_path).size == (1200, 1600)
    complete_events = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == "market_lense.cover_image_service"
        and json.loads(record.message).get("event") == "cover_render_complete"
    ]
    assert len(complete_events) == 3
    assert_logs_have_required_fields(complete_events)
    assert {event["fields"]["size"] for event in complete_events} == {
        "small",
        "medium",
        "large",
    }
    assert all(event["fields"]["title"] == LIVE_TITLE for event in complete_events)


def test_real_cover_renderer_preserves_breakable_hyphenated_title(
    tmp_path, caplog
) -> None:
    title = "Activate-Technology-and-Media-Outlook-2019"
    caplog.set_level(logging.INFO, logger="market_lense.cover_image_service")

    outcomes = generate_cover_images(
        CoverImageGenerationRequest(
            schema_version="2.0",
            output_dir=str(tmp_path / "out"),
            style_config_path=str(STYLE_PATH),
            reports=[
                CoverImageReport(
                    schema_version="2.0",
                    file_id="drive-hyphenated",
                    title=title,
                    publisher="Activate",
                    report_slug="activate-technology-and-media-outlook-2019",
                    time_period="2019",
                    region="Global",
                    fingerprint=_fingerprint(),
                )
            ],
        ),
        _ctx(),
    )

    assert outcomes[0].status == "generated"
    complete_events = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == "market_lense.cover_image_service"
        and json.loads(record.message).get("event") == "cover_render_complete"
    ]
    assert len(complete_events) == 3
    assert all(event["fields"]["title"] == title for event in complete_events)


def test_real_cover_renderer_wraps_unbreakable_title_on_medium_cover(tmp_path) -> None:
    title = "doc_map: cf091e263a2b6ed29222c5c60b6ed133a90fbe0c-pdf"

    outcomes = generate_cover_images(
        CoverImageGenerationRequest(
            schema_version="2.0",
            output_dir=str(tmp_path / "out"),
            style_config_path=str(STYLE_PATH),
            reports=[
                CoverImageReport(
                    schema_version="2.0",
                    file_id="drive-unbreakable-title",
                    title=title,
                    publisher="Activate",
                    report_slug="unbreakable-title",
                    time_period="2019",
                    region="Global",
                    fingerprint=_fingerprint(),
                )
            ],
        ),
        _ctx(),
    )

    assert outcomes[0].status == "generated"
    assert outcomes[0].assets is not None
    assert Image.open(outcomes[0].assets.medium.output_path).size == (1200, 1500)


def test_briefing_cover_renderer_writes_three_exact_assets(tmp_path) -> None:
    outcomes = generate_cover_images(
        CoverImageGenerationRequest(
            schema_version="2.0",
            output_dir=str(tmp_path / "out"),
            style_config_path=str(STYLE_PATH),
            reports=[
                CoverImageReport(
                    schema_version="2.0",
                    file_id="briefing-123",
                    title="Retail Media Decision Window",
                    publisher="Market Bearing",
                    report_slug="retail-media-decision-window",
                    time_period="20 June 2026",
                    region="Global",
                    fingerprint=_fingerprint(),
                    cover_profile="briefing",
                )
            ],
        ),
        _ctx(),
    )

    assert outcomes[0].status == "generated"
    assets = outcomes[0].assets
    assert assets is not None
    assert Image.open(assets.small.output_path).size == (1600, 900)
    assert Image.open(assets.medium.output_path).size == (1200, 1500)
    assert Image.open(assets.large.output_path).size == (1200, 1600)


def test_signal_cover_renderer_writes_three_exact_assets(tmp_path) -> None:
    outcomes = generate_cover_images(
        CoverImageGenerationRequest(
            schema_version="2.0",
            output_dir=str(tmp_path / "out"),
            style_config_path=str(STYLE_PATH),
            reports=[
                CoverImageReport(
                    schema_version="2.0",
                    file_id="signal-123",
                    title="Checkout Trust Is Becoming a Conversion Condition",
                    publisher="Market Bearing Signal",
                    report_slug="checkout-trust-conversion-condition",
                    time_period=None,
                    region=None,
                    fingerprint=_fingerprint(),
                    cover_profile="signal",
                )
            ],
        ),
        _ctx(),
    )

    assert outcomes[0].status == "generated"
    assets = outcomes[0].assets
    assert assets is not None
    assert Image.open(assets.small.output_path).size == (1600, 900)
    assert Image.open(assets.medium.output_path).size == (1200, 1500)
    assert Image.open(assets.large.output_path).size == (1200, 1600)


def test_real_cover_renderer_wraps_complete_long_covered_period(tmp_path) -> None:
    covered_period = (
        "Primary focus: 2024-2028 with historical data points for 2019 and 2021 "
        "and forecasts extending through 2028"
    )

    outcomes = generate_cover_images(
        CoverImageGenerationRequest(
            schema_version="2.0",
            output_dir=str(tmp_path / "out"),
            style_config_path=str(STYLE_PATH),
            reports=[
                CoverImageReport(
                    schema_version="2.0",
                    file_id="drive-long-period",
                    title="Technology and Media Outlook 2025: Video Gaming",
                    publisher="Activate Consulting",
                    report_slug="technology-media-outlook-video-gaming",
                    time_period=covered_period,
                    region="Global",
                    fingerprint=_fingerprint(),
                )
            ],
        ),
        _ctx(),
    )

    assert outcomes[0].status == "generated"
    assert outcomes[0].assets is not None
    assert Image.open(outcomes[0].assets.small.output_path).size == (1600, 900)
    assert Image.open(outcomes[0].assets.medium.output_path).size == (1200, 1500)
    assert Image.open(outcomes[0].assets.large.output_path).size == (1200, 1600)


def test_real_cover_renderer_replays_long_title_under_deep_root(tmp_path) -> None:
    output_dir = tmp_path / ("deep-output-root-" + "x" * 25)
    title = (
        "Global Economic Conditions and Investment Outlook Across Major Markets "
        "Through the Second Half 2026 and Regional Scenarios"
    )
    request = CoverImageGenerationRequest(
        schema_version="2.0",
        output_dir=str(output_dir),
        style_config_path=str(STYLE_PATH),
        reports=[
            CoverImageReport(
                schema_version="2.0",
                file_id="deep-root-replay",
                title=title,
                publisher="Market Lense Research",
                report_slug="long-report-" + "y" * 105,
                time_period="Q2 2026",
                region="Global",
                fingerprint=_fingerprint(),
            )
        ],
    )

    first = generate_cover_images(request, _ctx())
    assert first[0].status == "generated"
    first_assets = first[0].assets
    assert first_assets is not None
    first_paths = {
        size: Path(getattr(first_assets, size).output_path)
        for size in ("small", "medium", "large")
    }
    assert len({path.parent for path in first_paths.values()}) == 1
    first_bytes = {}
    for path in first_paths.values():
        resolved = path.resolve()
        temporary = path.with_suffix(path.suffix + ".tmp").resolve()
        assert windows_path_units(resolved) <= WINDOWS_PATH_BUDGET
        assert windows_path_units(temporary) <= WINDOWS_PATH_BUDGET
        for component in resolved.parts:
            if component in {resolved.anchor, ".", ""}:
                continue
            assert windows_path_units(component) <= WINDOWS_COMPONENT_BUDGET
            assert not is_windows_reserved_component(component)
        with Image.open(path) as image:
            image.load()
            assert image.size in {(1600, 900), (1200, 1500), (1200, 1600)}
        first_bytes[path.name] = path.read_bytes()
    assert list(output_dir.rglob("*.png.tmp")) == []

    second = generate_cover_images(request, _ctx())
    assert second[0].status == "generated"
    second_assets = second[0].assets
    assert second_assets is not None
    second_paths = {
        size: Path(getattr(second_assets, size).output_path)
        for size in ("small", "medium", "large")
    }
    assert second_paths == first_paths
    assert {
        path.name: path.read_bytes() for path in second_paths.values()
    } == first_bytes
    assert list(output_dir.rglob("*.png.tmp")) == []


def test_real_cover_renderer_rejects_impossible_output_root_before_rendering(
    tmp_path,
) -> None:
    config = load_cover_styles(
        CoverStyleLoadRequest(schema_version="2.0", path=str(STYLE_PATH)),
        _ctx(),
    ).config
    output_root = tmp_path / ("impossible-root-" + "q" * 190)

    with pytest.raises(AppError) as captured:
        render_cover_image(
            CoverImageRenderRequest(
                schema_version="2.0",
                output_path=str(output_root / "cover.png"),
                size="small",
                title="A valid report title",
                publisher="Market Lense Research",
                time_period="Global | Q2 2026",
                style=config.profiles["report"].style,
                layout=config.profiles["report"].layouts["small"],
                fingerprint=_fingerprint(),
            ),
            _ctx(),
        )

    assert captured.value.code == "cover_asset_path_invalid"
    assert captured.value.retryable is False
    assert "shorten output_dir" in captured.value.message
    assert not output_root.exists()


def test_real_cover_renderer_rejects_impossible_unbroken_title(
    tmp_path, assert_app_error
) -> None:
    config = load_cover_styles(
        CoverStyleLoadRequest(schema_version="2.0", path=str(STYLE_PATH)),
        _ctx(),
    ).config

    with pytest.raises(AppError) as captured:
        render_cover_image(
            CoverImageRenderRequest(
                schema_version="2.0",
                output_path=str(tmp_path / "impossible.png"),
                size="small",
                title="X" * 1000,
                publisher="Market Lense Research",
                time_period="Global | Q2 2026",
                style=config.profiles["report"].style,
                layout=config.profiles["report"].layouts["small"],
                fingerprint=_fingerprint(),
            ),
            _ctx(),
        )

    assert_app_error(
        captured.value,
        code="cover_title_overflow",
        retryable=False,
    )
