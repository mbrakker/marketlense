from __future__ import annotations

import pytest

from src.contracts.drive import DriveUploadBytesRequest
from src.contracts.run_budget import RunBudget, RunBudgetUsage
from src.contracts.run_context import RunContext
from src.contracts.wordpress import WordPressPostCreateRequest
from src.services.drive_service import upload_bytes
from src.services.wordpress_service import create_post
from src.utils.errors import AppError


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="budget-run", task_id="task", span_id="span")


def _budget() -> RunBudget:
    return RunBudget(
        schema_version="1.0",
        run_id="budget-run",
        publisher_name="publisher",
        max_drive_writes=1,
        max_wordpress_writes=1,
    )


def test_drive_budget_stop_occurs_before_authentication_or_network() -> None:
    with pytest.raises(AppError) as exc_info:
        upload_bytes(
            DriveUploadBytesRequest(
                schema_version="1.0", folder_id="folder", service_account_path="missing.json",
                file_name="artifact.json", content=b"{}", mime_type="application/json",
                run_budget=_budget(),
                run_budget_usage=RunBudgetUsage(schema_version="1.0", drive_writes=1),
            ),
            _ctx(),
        )

    assert exc_info.value.code == "drive_upload_budget_stop"
    assert exc_info.value.retryable is False


def test_wordpress_budget_stop_occurs_before_http_request() -> None:
    with pytest.raises(AppError) as exc_info:
        create_post(
            WordPressPostCreateRequest(
                schema_version="1.0", base_url="https://example.invalid", auth_header="redacted",
                title="Title", content_html="<p>content</p>", status="draft",
                run_budget=_budget(),
                run_budget_usage=RunBudgetUsage(schema_version="1.0", wordpress_writes=1),
            ),
            _ctx(),
        )

    assert exc_info.value.code == "wordpress_post_create_budget_stop"
    assert exc_info.value.retryable is False
