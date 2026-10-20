from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from src.services._browser_report_download.request import resolve_download_dir_path
from src.utils.errors import AppError


def _artifact_paths_module():
    try:
        return importlib.import_module(
            "src.services._browser_report_download.artifact_paths"
        )
    except ModuleNotFoundError as exc:
        pytest.fail(f"browser artifact path helper is not implemented: {exc}")


def test_windows_path_units_counts_utf16_code_units() -> None:
    helper = _artifact_paths_module()

    assert helper.windows_path_units("ascii") == 5
    assert helper.windows_path_units("😀") == 2
    assert helper.windows_path_units("a😀b") == 4


def test_short_pdf_name_is_preserved_and_part_sibling_fits(tmp_path: Path) -> None:
    helper = _artifact_paths_module()

    path = helper.resolve_browser_artifact_path(
        parent_dir=tmp_path,
        source_name="report.pdf",
        extension=".pdf",
        identity="https://example.com/report.pdf",
        temporary_suffixes=(".part",),
    )

    assert path.name == "report.pdf"
    assert (
        helper.validate_browser_artifact_path(path, temporary_suffixes=(".part",))
        == path
    )


def test_lossy_reserved_names_get_stable_identity_hashes(tmp_path: Path) -> None:
    helper = _artifact_paths_module()

    first = helper.resolve_browser_artifact_path(
        parent_dir=tmp_path,
        source_name="CON: отчёт.pdf",
        extension=".pdf",
        identity="https://publisher-a.example/report.pdf",
    )
    second = helper.resolve_browser_artifact_path(
        parent_dir=tmp_path,
        source_name="CON: отчёт.pdf",
        extension=".pdf",
        identity="https://publisher-b.example/report.pdf",
    )

    assert first != second
    assert first.suffix == second.suffix == ".pdf"
    assert "con" not in first.stem.casefold()
    assert first == helper.resolve_browser_artifact_path(
        parent_dir=tmp_path,
        source_name="CON: отчёт.pdf",
        extension=".pdf",
        identity="https://publisher-a.example/report.pdf",
    )


def test_long_filename_is_compacted_from_actual_parent_budget(tmp_path: Path) -> None:
    helper = _artifact_paths_module()
    parent = tmp_path
    while helper.windows_path_units(parent) < 150:
        parent /= "browser-output-segment"

    path = helper.resolve_browser_artifact_path(
        parent_dir=parent,
        source_name=("very-long-report-name-" * 30) + ".pdf",
        extension=".pdf",
        identity="https://example.com/reports/long-report.pdf?download=1",
        temporary_suffixes=(".part",),
    )

    assert path.suffix == ".pdf"
    assert helper.windows_path_units(path) <= 240
    assert helper.windows_path_units(path.with_suffix(path.suffix + ".part")) <= 240
    assert helper.windows_path_units(path.name) <= 255


def test_fixed_name_is_validated_without_being_renamed(tmp_path: Path) -> None:
    helper = _artifact_paths_module()

    path = helper.resolve_browser_artifact_path(
        parent_dir=tmp_path,
        source_name="ignored-source.html",
        fixed_name="onsite_capture.html",
    )

    assert path.name == "onsite_capture.html"


def test_impossible_parent_budget_raises_before_path_is_returned(
    tmp_path: Path,
) -> None:
    helper = _artifact_paths_module()
    parent = tmp_path
    while helper.windows_path_units(parent) < 235:
        parent /= "browser-output-segment"

    with pytest.raises(AppError) as error:
        helper.resolve_browser_artifact_path(
            parent_dir=parent,
            source_name="report.pdf",
            extension=".pdf",
            temporary_suffixes=(".part",),
        )

    assert error.value.retryable is False
    assert error.value.code in {
        "browser_download_output_dir_invalid",
        "browser_download_artifact_path_invalid",
    }


def test_profile_validation_accounts_for_chromium_descendants(
    tmp_path: Path,
) -> None:
    helper = _artifact_paths_module()

    profile = tmp_path / "browser-use-user-data-dir-profile-123-456"
    assert helper.validate_browser_profile_path(profile) == profile.resolve()


def test_download_root_budget_fails_before_directory_creation(tmp_path: Path) -> None:
    helper = _artifact_paths_module()
    root = tmp_path
    while helper.windows_path_units(root) < 190:
        root /= "browser-output-segment"

    with pytest.raises(AppError) as error:
        resolve_download_dir_path(
            root_dir=str(root),
            normalized_url="https://example.com/research/report",
        )

    assert error.value.retryable is False
    assert not root.exists()
