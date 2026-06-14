from __future__ import annotations

from pathlib import Path

import pytest

from src.contracts.cover_images import CoverStyleLoadRequest
from src.contracts.run_context import RunContext
from src.services.cover_style_service import load_cover_styles
from src.utils.errors import AppError


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def test_default_cover_style_exposes_three_canonical_layouts() -> None:
    response = load_cover_styles(
        CoverStyleLoadRequest(schema_version="1.0", path=""),
        _ctx(),
    )

    config = response.config
    assert config.schema_version == "2.0"
    assert (config.layouts["small"].width, config.layouts["small"].height) == (
        1600,
        900,
    )
    assert (config.layouts["medium"].width, config.layouts["medium"].height) == (
        1200,
        1500,
    )
    assert (config.layouts["large"].width, config.layouts["large"].height) == (
        1200,
        1600,
    )
    medium = config.layouts["medium"]
    assert medium.publisher_font_min >= 36
    assert medium.title_font_min >= 52
    assert medium.period_font_min >= 30
    assert not hasattr(config, "categories")


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
