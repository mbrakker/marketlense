from __future__ import annotations

from pathlib import Path

import pytest

from src.contracts.cover_images import CoverStyleLoadRequest
from src.contracts.run_context import RunContext
from src.services.cover_style_service import load_cover_styles
from src.utils.errors import AppError


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def test_cover_style_service_rejects_non_mapping_root(
    tmp_path: Path,
    assert_app_error,
) -> None:
    config_path = tmp_path / "cover-styles.yaml"
    config_path.write_text("- not-a-mapping\n", encoding="utf-8")

    with pytest.raises(AppError) as exc_info:
        load_cover_styles(
            CoverStyleLoadRequest(schema_version="1.0", path=str(config_path)),
            _ctx(),
        )

    assert_app_error(
        exc_info.value,
        code="cover_style_invalid",
        retryable=False,
    )
