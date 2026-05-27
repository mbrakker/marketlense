from __future__ import annotations

import pytest

from src.services._browser_report_download._artifact.evidence import (
    _extract_visible_text_from_html,
)
from src.services._browser_report_download._browser_runtime.terminal_assets import (
    _browser_visible_text_from_html,
)
from src.services._browser_report_download._browser_runtime.terminal_state import (
    TerminalSnapshot,
    _terminal_quorum_text,
)
from src.services._browser_report_download._http.html_evidence import _html_to_text


@pytest.mark.parametrize(
    "sanitize",
    [
        _html_to_text,
        _extract_visible_text_from_html,
        _browser_visible_text_from_html,
        lambda html: _terminal_quorum_text(
            TerminalSnapshot(
                page=None,
                url="https://example.com/report",
                title="",
                html=html,
            )
        ),
    ],
)
def test_browser_html_text_sanitizers_exclude_script_and_style_text_with_spaced_end_tags(
    sanitize,
) -> None:
    text = sanitize(
        "<body>Visible report"
        "<script>FAKE THANK YOU DOWNLOAD REPORT</script >"
        "<style>FAKE HIDDEN DOWNLOAD CTA</style >"
        "</body>"
    )

    assert "Visible report" in text
    assert "FAKE" not in text
    assert "THANK YOU" not in text
    assert "HIDDEN" not in text
