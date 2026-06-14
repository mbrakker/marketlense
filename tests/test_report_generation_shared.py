from pathlib import Path
from types import SimpleNamespace

import pytest

from src.contracts.run_context import RunContext
from src.generators.report_generation_shared import read_cache_json, template_sha256
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
