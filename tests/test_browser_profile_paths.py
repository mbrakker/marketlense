from __future__ import annotations

from pathlib import Path

import pytest

from src.contracts._browser_download.session_reuse import (
    BrowserDownloadSessionReusePolicy,
)
from src.contracts.run_context import RunContext
from src.services._browser_report_download.artifact_paths import (
    validate_browser_profile_path,
    validate_browser_session_reuse_base_path,
    windows_path_units,
)
from src.services._browser_report_download.session_reuse import (
    resolve_browser_session_reuse,
)
from src.utils.errors import AppError


def test_session_reuse_profile_ledger_and_index_fit_budget(tmp_path: Path) -> None:
    ctx = RunContext(schema_version="1.0", run_id="run", task_id="task", span_id="span")
    policy = BrowserDownloadSessionReusePolicy(
        schema_version="1.0",
        enabled=True,
        mode="same_publisher_batch",
        session_key="batch-key",
        publisher_scope="example.com",
        ttl_seconds=120.0,
        base_dir=str(tmp_path / "session-reuse"),
    )

    first = resolve_browser_session_reuse(
        policy=policy,
        default_base_dir=tmp_path / "default",
        normalized_url="https://example.com/report",
        ctx=ctx,
    )
    second = resolve_browser_session_reuse(
        policy=policy,
        default_base_dir=tmp_path / "default",
        normalized_url="https://example.com/other-report",
        ctx=ctx,
    )

    profile = Path(first.profile_path)
    assert first.accepted is True
    assert second.profile_reused is True
    assert second.profile_path == first.profile_path
    assert windows_path_units(profile) <= 240
    assert (profile / "session_reuse_ledger.json").exists()
    assert (profile.parent / "session_key_index.json").exists()
    assert (
        validate_browser_profile_path(
            profile,
            include_session_ledger=True,
        )
        == profile.resolve()
    )


def test_session_reuse_base_rejects_impossible_parent_before_creation(
    tmp_path: Path,
) -> None:
    base_dir = tmp_path
    while windows_path_units(base_dir) < 235:
        base_dir /= "session-reuse-segment"

    with pytest.raises(AppError) as error:
        validate_browser_session_reuse_base_path(base_dir)

    assert error.value.retryable is False
    assert not base_dir.exists()
