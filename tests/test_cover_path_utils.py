from pathlib import Path

import pytest

from src.utils.cover_path_utils import (
    build_cover_asset_path,
    build_report_card_asset_path,
)
from src.utils.errors import AppError
from src.utils.path_utils import (
    WINDOWS_COMPONENT_BUDGET,
    WINDOWS_PATH_BUDGET,
    is_windows_reserved_component,
    windows_path_units,
)


def _assert_windows_safe_cover_path(path: Path) -> None:
    resolved = path.resolve()
    temporary = path.with_suffix(path.suffix + ".tmp").resolve()
    assert windows_path_units(resolved) <= WINDOWS_PATH_BUDGET
    assert windows_path_units(temporary) <= WINDOWS_PATH_BUDGET
    for component in resolved.parts:
        if component in {resolved.anchor, ".", ""}:
            continue
        assert windows_path_units(component) <= WINDOWS_COMPONENT_BUDGET
        assert not is_windows_reserved_component(component)


def test_build_cover_asset_path_is_bounded_for_long_titles():
    title = (
        "Our not-yet-trending report is back for 2026. "
        "From food to fashion to home decor and more, see where tomorrow's trends "
        "will take your audience next."
    )
    publisher = "Pinterest"
    file_id = "1T0q1n4OL3Im6tthF2n45-n4RjSwMy2kf"

    path = build_cover_asset_path(
        "out", file_id=file_id, title=title, publisher=publisher
    )
    path_text = str(path)

    assert path_text.endswith(".png")
    assert "/assets/" in path_text.replace("\\", "/")
    assert len(path_text) < 220


def test_build_cover_asset_path_uses_file_id_suffix():
    path = build_cover_asset_path(
        "out",
        file_id="file_123",
        title="Retail trends 2026",
        publisher="Capgemini",
    )
    path_text = path.as_posix()
    assert "-file-123/" in path_text
    assert "-file-123.png" in path_text


def test_build_cover_asset_path_uses_report_slug_when_provided():
    path = build_cover_asset_path(
        "out",
        file_id="file_123",
        title="Retail trends 2026",
        publisher="Capgemini",
        report_slug="attest-uk-consumer-trends-report-2026-acig-pdf",
    )
    path_text = path.as_posix()
    assert "/attest-uk-consumer-trends-report-2026-acig-pdf/assets/" in path_text
    assert path_text.endswith("-file-123.png")


def test_cover_paths_preserve_normal_paths_and_bound_explicit_long_slug(tmp_path):
    normal = build_report_card_asset_path(
        "out", "file_123", "Retail trends 2026", "retail-trends", "medium"
    )
    assert normal == Path("out/retail-trends/assets/report-card-medium.png")

    deep_root = tmp_path / ("deep-root-" + "x" * 45)
    path = build_report_card_asset_path(
        str(deep_root),
        "file_123",
        "Retail trends 2026",
        "retail-trends-" + "y" * 105,
        "medium",
    )

    _assert_windows_safe_cover_path(path)
    assert (
        path.parent
        == build_report_card_asset_path(
            str(deep_root),
            "file_123",
            "Retail trends 2026",
            "retail-trends-" + "y" * 105,
            "small",
        ).parent
    )


def test_cover_paths_use_full_identity_for_distinct_truncated_inputs(tmp_path):
    root = tmp_path / ("r" * 100)
    common = "same-readable-prefix-" + "a" * 90
    first = build_report_card_asset_path(
        str(root), "file-one", "Title one", common + "-one", "small"
    )
    second = build_report_card_asset_path(
        str(root), "file-two", "Title two", common + "-two", "small"
    )

    assert first != second
    assert first == build_report_card_asset_path(
        str(root), "file-one", "Title one", common + "-one", "small"
    )
    _assert_windows_safe_cover_path(first)
    _assert_windows_safe_cover_path(second)


def test_cover_paths_bound_unicode_title_and_all_card_sizes(tmp_path):
    root = tmp_path / ("unicode-root-" + "u" * 35)
    title = "Market outlook " + ("long-title-" * 20) + " 東京 рынок"
    paths = [
        build_report_card_asset_path(
            str(root), "file-unicode", title, "report-" + "z" * 105, size
        )
        for size in ("small", "medium", "large")
    ]

    assert len({path.parent for path in paths}) == 1
    assert [path.name for path in paths] == [
        "report-card-small.png",
        "report-card-medium.png",
        "report-card-large.png",
    ]
    for path in paths:
        _assert_windows_safe_cover_path(path)


def test_cover_paths_keep_png_extension_when_both_components_compact(tmp_path):
    root = tmp_path / ("filename-compaction-root-" + "x" * 75)
    path = build_cover_asset_path(
        str(root),
        "file-" + "f" * 24,
        "title-" * 40,
        "publisher-" * 20,
        "report-" + "y" * 105,
    )

    assert path.suffix == ".png"
    _assert_windows_safe_cover_path(path)


def test_cover_paths_reject_impossible_root_before_filesystem_side_effect(tmp_path):
    root = tmp_path / ("impossible-root-" + "q" * 190)
    with pytest.raises(AppError) as exc_info:
        build_report_card_asset_path(str(root), "file-1", "Title", "report", "small")

    assert exc_info.value.code == "cover_asset_path_invalid"
    assert exc_info.value.retryable is False
    assert "shorten output_dir" in exc_info.value.message
    assert not root.exists()


def test_cover_paths_reject_reserved_output_root(tmp_path):
    with pytest.raises(AppError) as exc_info:
        build_report_card_asset_path(
            str(tmp_path / "CON"), "file-1", "Title", "report", "small"
        )

    assert exc_info.value.code == "cover_asset_path_invalid"
    assert exc_info.value.retryable is False
    assert not (tmp_path / "CON").exists()
