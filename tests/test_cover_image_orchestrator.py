from __future__ import annotations

import pytest

from src.contracts.cover_images import CoverImageOrchestratorRequest
from src.orchestrators.cover_image_orchestrator import run_cover_image_generation
from src.utils.errors import AppError


def test_cover_image_orchestrator_missing_file_is_typed_error(
    tmp_path: Path,
    assert_app_error,
) -> None:
    with pytest.raises(AppError) as exc_info:
        run_cover_image_generation(
            CoverImageOrchestratorRequest(
                schema_version="1.0",
                reports_db=str(tmp_path / "reports.sqlite"),
                output_dir=str(tmp_path / "out"),
                style_config_path=str(tmp_path / "cover-styles.yaml"),
                file_id="missing-file",
            )
        )

    assert_app_error(
        exc_info.value,
        code="cover_report_not_found",
        retryable=False,
    )
