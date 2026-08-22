from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from src.contracts.browser_download import BrowserReportDownloadRequest
from src.services._browser_report_download import rendered_terminal_preflight as terminal_runtime

from .builders import _settings


class _Page:
    def __init__(self, *, url: str, title: str, html: str) -> None:
        self._url = url
        self._title = title
        self._html = html

    async def get_url(self) -> str:
        return self._url

    async def get_title(self) -> str:
        return self._title

    async def evaluate(self, expression: str) -> str:
        assert "document.documentElement" in expression
        return self._html


class _BrowserSession:
    def __init__(self, *, url: str, title: str, html: str, **kwargs) -> None:
        self._page = _Page(url=url, title=title, html=html)
        self.started = False
        self.killed = False

    async def start(self) -> None:
        self.started = True

    async def navigate_to(self, url: str) -> None:
        return None

    async def get_current_page(self) -> _Page:
        return self._page

    async def kill(self) -> None:
        self.killed = True


def _request(tmp_path: Path) -> BrowserReportDownloadRequest:
    return BrowserReportDownloadRequest(
        schema_version="1.0",
        url="https://go.example.com/commerce-media-trends-report",
        settings=_settings(tmp_path),
        route_family_hint="browser_email_form",
    )


def test_rendered_terminal_preflight_returns_terminal_marker_without_agent(
    tmp_path: Path,
    run_context,
) -> None:
    sessions: list[_BrowserSession] = []

    def session_factory(**kwargs) -> _BrowserSession:
        session = _BrowserSession(
            url="https://www4.example.com/commerce-media-trends-report",
            title="404 Not Found",
            html=(
                "<html><body><h1>Not Found</h1><p>The requested URL was not found "
                "on this server.</p></body></html>"
            ),
            **kwargs,
        )
        sessions.append(session)
        return session

    response = terminal_runtime.try_rendered_terminal_preflight(
        request=_request(tmp_path),
        ctx=run_context,
        normalized_url="https://go.example.com/commerce-media-trends-report",
        execution_url="https://go.example.com/commerce-media-trends-report",
        browser_session_class=session_factory,
    )

    assert response is not None
    assert response.probe.status == "terminal_static_archive"
    assert response.probe.final_url == (
        "https://www4.example.com/commerce-media-trends-report"
    )
    assert response.probe.avoided_agent_call is True
    assert "preflight_terminal_not_found" in response.probe.evidence_labels
    assert "rendered_terminal_preflight" in response.probe.evidence_labels
    assert sessions[0].started is True
    assert sessions[0].killed is True


def test_rendered_terminal_preflight_does_not_treat_403_as_not_found(
    tmp_path: Path,
    run_context,
) -> None:
    response = terminal_runtime.try_rendered_terminal_preflight(
        request=_request(tmp_path),
        ctx=run_context,
        normalized_url="https://go.example.com/commerce-media-trends-report",
        execution_url="https://go.example.com/commerce-media-trends-report",
        browser_session_class=lambda **kwargs: _BrowserSession(
            url="https://go.example.com/commerce-media-trends-report",
            title="403 Forbidden",
            html="<html><body><h1>403 Forbidden</h1></body></html>",
            **kwargs,
        ),
    )

    assert response is None
