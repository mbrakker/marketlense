from pathlib import Path
from types import SimpleNamespace

import pytest

from src.contracts.run_context import RunContext
from src.generators.report_generation_dependencies import ReportSourceDependencies
from src.generators.report_generation_shared import (
    cache_path,
    read_cache_json,
    template_sha256,
)
from src.generators.report_source_cache import (
    bind_report_source_cache,
    load_report_source_cache,
    write_report_source_cache,
)
from src.services.file_service import (
    WINDOWS_SAFE_ATOMIC_PATH_LENGTH,
    atomic_write_temp_path_length,
)
from src.utils.errors import AppError


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def test_read_cache_json_propagates_retryable_read_error(assert_app_error):
    dependencies = SimpleNamespace(
        read_json_object_cache=lambda request, ctx: (_ for _ in ()).throw(
            AppError(
                code="file_read_failed",
                message="temporary cache read failure",
                retryable=True,
            )
        )
    )

    with pytest.raises(AppError) as err:
        read_cache_json(Path("cache.json"), _ctx(), dependencies)

    assert_app_error(
        err.value,
        code="file_read_failed",
        retryable=True,
        severity="error",
    )


def test_template_sha256_propagates_retryable_read_error(assert_app_error):
    dependencies = SimpleNamespace(
        hash_file_bundle=lambda request, ctx: (_ for _ in ()).throw(
            AppError(
                code="file_read_failed",
                message="temporary template read failure",
                retryable=True,
            )
        )
    )

    with pytest.raises(AppError) as err:
        template_sha256(Path("template.j2"), _ctx(), dependencies)

    assert_app_error(
        err.value,
        code="file_read_failed",
        retryable=True,
        severity="error",
    )


def test_cache_path_compacts_destination_and_temp_paths_for_atomic_write() -> None:
    cache_root = (
        Path(Path.cwd().anchor)
        / ("isolated-cohort-" + "x" * 110)
        / "pdf_cache"
        / ("a" * 32)
    )
    uncompact_path = cache_root / f"pdf_info_{'b' * 64}.json"
    assert atomic_write_temp_path_length(uncompact_path) <= (
        WINDOWS_SAFE_ATOMIC_PATH_LENGTH
    )
    assert len(str(uncompact_path.resolve())) > WINDOWS_SAFE_ATOMIC_PATH_LENGTH

    path = cache_path(
        cache_root,
        "pdf_info",
        "b" * 64,
    )

    assert path != uncompact_path
    assert atomic_write_temp_path_length(path) <= WINDOWS_SAFE_ATOMIC_PATH_LENGTH
    assert len(str(path.resolve())) <= WINDOWS_SAFE_ATOMIC_PATH_LENGTH


def test_cache_path_rejects_a_compact_candidate_that_still_exceeds_windows_budget(
    tmp_path: Path,
    assert_app_error,
) -> None:
    cache_root = tmp_path / ("isolated-cohort-" + "x" * 190) / ("a" * 32)

    with pytest.raises(AppError) as err:
        cache_path(cache_root, "pdf_info", "b" * 64)

    assert_app_error(err.value, code="report_cache_path_invalid", retryable=False)


def test_cache_path_rejects_utf16_component_over_windows_component_budget(
    tmp_path: Path,
    assert_app_error,
) -> None:
    cache_root = tmp_path / ("😀" * 130) / ("a" * 32)

    with pytest.raises(AppError) as err:
        cache_path(cache_root, "pdf_info", "b" * 64)

    assert_app_error(err.value, code="report_cache_path_invalid", retryable=False)


def test_report_source_cache_round_trips_through_persisted_compact_binding(
    tmp_path: Path,
) -> None:
    settings = SimpleNamespace(
        cache_dir=str(tmp_path / ("isolated-cohort-" + "x" * 55))
    )
    dependencies = ReportSourceDependencies.default()
    binding = bind_report_source_cache(
        settings=settings,
        md5="a" * 32,
        file_id="file-1",
        phase="pdf_info",
        prefix="pdf_info",
        cache_key="b" * 64,
    )
    payload = {"key": "b" * 64, "value": {"page_count": 4}}

    write_report_source_cache(
        binding,
        payload=payload,
        ctx=_ctx(),
        dependencies=dependencies,
    )
    loaded = load_report_source_cache(
        binding,
        ctx=_ctx(),
        dependencies=dependencies,
        adapt_payload=lambda value: value.get("value"),
    )

    assert Path(binding.cache_path).is_file()
    assert loaded.status == "hit"
    assert loaded.value == {"page_count": 4}
