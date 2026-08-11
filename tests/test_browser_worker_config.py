from __future__ import annotations

import pytest

from src.services._browser_report_download import browser_worker


@pytest.mark.parametrize(
    ("key", "error_message"),
    [
        ("run_budget_max_pdfs", "optional integer configuration must be numeric"),
        ("daily_spend_pause_usd", "optional float configuration must be numeric"),
    ],
)
def test_worker_rejects_non_numeric_optional_numeric_configuration(
    key: str, error_message: str
) -> None:
    with pytest.raises(TypeError, match=error_message):
        browser_worker._build_settings({key: []})
