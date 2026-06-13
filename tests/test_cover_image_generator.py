from dataclasses import replace
from pathlib import Path

import pytest

from src.contracts.cover_images import (
    CoverImageGenerationRequest,
    CoverImageRenderResponse,
    CoverImageReport,
)
from src.contracts.report_cards import CoverFingerprint
from src.contracts.run_context import RunContext
from src.generators.cover_image_generator import generate_cover_images
from src.services import cover_image_service
from src.utils.errors import AppError


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="cover", span_id="s")


def _request(tmp_path: Path) -> CoverImageGenerationRequest:
    return CoverImageGenerationRequest(
        schema_version="1.0",
        output_dir=str(tmp_path / "out"),
        style_config_path=str(
            Path(__file__).resolve().parents[1] / "src" / "config" / "cover-styles.yaml"
        ),
        reports=[
            CoverImageReport(
                schema_version="2.0",
                file_id="file-1",
                title="Retail Trends",
                publisher="Publisher",
                report_slug="retail-trends",
                categories=["retail_media"],
                time_period="2026",
                region="US",
                fingerprint=CoverFingerprint(
                    schema_version="1.0",
                    geometry_family="ascending_trajectory",
                    evidence_shape="trend",
                    direction="rising",
                    geography_scope="country",
                    evidence_density="metric_rich",
                    domain_layer="grid",
                    seed=1344902748,
                    selection_reason=(
                        "Rising time-series evidence dominates the report."
                    ),
                ),
            )
        ],
    )


def test_generate_cover_images_renders_complete_asset_set(
    tmp_path, external_boundary_mocks_only
):
    requests = []

    def _capture(request, ctx):
        del ctx
        requests.append(request)
        return CoverImageRenderResponse(
            schema_version="2.0",
            output_path=request.output_path,
            width=request.layout.width,
            height=request.layout.height,
            title_font_size=request.layout.title_font_max,
        )

    external_boundary_mocks_only.setattr(
        cover_image_service, "render_cover_image", _capture
    )

    outcomes = generate_cover_images(_request(tmp_path), _ctx())

    assert len(outcomes) == 1
    outcome = outcomes[0]
    assert outcome.status == "generated"
    assert not hasattr(outcome, "output_path")
    assert outcome.assets is not None
    assert [request.size for request in requests] == ["small", "medium", "large"]
    assert [Path(request.output_path).name for request in requests] == [
        "report-card-small.png",
        "report-card-medium.png",
        "report-card-large.png",
    ]
    assert {Path(request.output_path).parents[1].name for request in requests} == {
        "retail-trends"
    }
    assert outcome.assets.small.output_path == requests[0].output_path
    assert outcome.assets.medium.output_path == requests[1].output_path
    assert outcome.assets.large.output_path == requests[2].output_path


def test_generate_cover_images_propagates_retryable_render_error(
    tmp_path, external_boundary_mocks_only, assert_app_error
):
    def _raise_retryable(request, ctx):
        del request, ctx
        raise AppError(
            code="cover_render_failed",
            message="temporary cover render failure",
            retryable=True,
        )

    external_boundary_mocks_only.setattr(
        cover_image_service, "render_cover_image", _raise_retryable
    )

    with pytest.raises(AppError) as err:
        generate_cover_images(_request(tmp_path), _ctx())

    assert_app_error(
        err.value,
        code="cover_render_failed",
        retryable=True,
        severity="error",
    )


def test_generate_cover_images_rejects_blank_output_directory(
    tmp_path, assert_app_error
):
    request = replace(_request(tmp_path), output_dir="  ")

    with pytest.raises(AppError) as err:
        generate_cover_images(request, _ctx())

    assert_app_error(
        err.value,
        code="cover_output_missing",
        retryable=False,
        severity="error",
    )


def test_generate_cover_images_normalizes_slug_and_single_covered_period(
    tmp_path, external_boundary_mocks_only
):
    source = _request(tmp_path)
    report = replace(
        source.reports[0],
        report_slug="  ",
        region=None,
        time_period="  2026  ",
    )
    request = replace(source, reports=[report])
    captured = []

    def _capture(render_request, ctx):
        del ctx
        captured.append(render_request)
        return CoverImageRenderResponse(
            schema_version="2.0",
            output_path=render_request.output_path,
            width=render_request.layout.width,
            height=render_request.layout.height,
            title_font_size=render_request.layout.title_font_max,
        )

    external_boundary_mocks_only.setattr(
        cover_image_service, "render_cover_image", _capture
    )

    outcome = generate_cover_images(request, _ctx())[0]

    assert outcome.status == "generated"
    assert {item.time_period for item in captured} == {"2026"}
    assert {Path(item.output_path).parents[1].name for item in captured} == {
        "retail-trends-pdf-file-1"
    }
