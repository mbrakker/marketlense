# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403

def test_report_db_access_connect_failure_is_typed_app_error(assert_app_error) -> None:
    ctx = new_run_context(task_id="test_db_access_connect_failure")

    original_connect = sqlite3.connect

    def _raise_connect(*args, **kwargs):
        raise sqlite3.OperationalError("connect boom")

    sqlite3.connect = _raise_connect
    try:
        with pytest.raises(AppError) as exc_info:
            check_report_db_access(
                ReportMetadataDbAccessRequest(
                    schema_version="1.0",
                    db_path="C:/tmp/reports.sqlite",
                    timeout_seconds=0.0,
                ),
                ctx,
            )
    finally:
        sqlite3.connect = original_connect

    assert_app_error(
        exc_info.value,
        code="metadata_db_unavailable",
        retryable=True,
    )

__all__ = [
    "test_report_db_access_connect_failure_is_typed_app_error",
]
