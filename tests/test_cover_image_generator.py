from pathlib import Path

import pytest

from src.contracts.cover_images import CoverImageGenerationRequest, CoverImageReport
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
                schema_version="1.0",
                file_id="file-1",
                title="Retail Trends",
                publisher="Publisher",
                report_slug="retail-trends",
                categories=["retail_media"],
                time_period="2026",
                region="US",
            )
        ],
    )


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
