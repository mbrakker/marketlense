from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any, Callable

import pytest

from Wordpress.scripts import wp_rest_common as rest_common


@dataclass(frozen=True)
class FakeRestResponse:
    status_code: int
    text: str
    headers: dict[str, Any]
    reason: str = ""

    @classmethod
    def from_payload(
        cls,
        *,
        status_code: int,
        payload: object | None = None,
        text: str | None = None,
        headers: dict[str, Any] | None = None,
        reason: str = "",
    ) -> "FakeRestResponse":
        rendered = text if text is not None else json.dumps(payload)
        return cls(
            status_code=status_code,
            text=rendered,
            headers=dict(headers or {}),
            reason=reason,
        )

    def json(self) -> Any:
        return json.loads(self.text)


@dataclass(frozen=True)
class RecordedRestCall:
    method: str
    url: str
    headers: dict[str, Any]
    params: dict[str, Any]
    data: Any
    timeout: Any
    verify: Any


ResponseHandler = Callable[[RecordedRestCall], FakeRestResponse]


class RequestsBoundary:
    def __init__(self) -> None:
        self._routes: dict[
            tuple[str, str], list[FakeRestResponse | Exception | ResponseHandler]
        ] = {}
        self.calls: list[RecordedRestCall] = []

    def add(
        self,
        method: str,
        url: str,
        *responses: FakeRestResponse | Exception | ResponseHandler,
    ) -> None:
        if not responses:
            raise AssertionError("at least one fake response is required")
        key = (method.upper(), url)
        self._routes.setdefault(key, []).extend(responses)

    def add_json(
        self,
        method: str,
        url: str,
        *,
        status_code: int,
        payload: object | None = None,
        text: str | None = None,
        headers: dict[str, Any] | None = None,
        reason: str = "",
    ) -> None:
        self.add(
            method,
            url,
            FakeRestResponse.from_payload(
                status_code=status_code,
                payload=payload,
                text=text,
                headers=headers,
                reason=reason,
            ),
        )

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        data: Any = None,
        timeout: Any = None,
        verify: Any = None,
    ) -> FakeRestResponse:
        call = RecordedRestCall(
            method=method.upper(),
            url=url,
            headers=dict(headers or {}),
            params=dict(params or {}),
            data=data,
            timeout=timeout,
            verify=verify,
        )
        self.calls.append(call)
        key = (call.method, call.url)
        queue = self._routes.get(key)
        if not queue:
            raise AssertionError(
                f"no fake route registered for {call.method} {call.url}"
            )
        current = queue[0]
        if len(queue) > 1:
            queue.pop(0)
        if isinstance(current, Exception):
            raise current
        if callable(current):
            return current(call)
        return current


def test_client_discovers_query_route_when_pretty_permalinks_rest_404(
    external_boundary_mocks_only: ExternalBoundaryMocksOnly,
) -> None:
    boundary = RequestsBoundary()
    external_boundary_mocks_only.setattr(
        rest_common.requests, "request", boundary.request
    )
    site_url = "http://site.test"

    boundary.add_json(
        "GET",
        f"{site_url}/wp-json/",
        status_code=404,
        text="<html>404</html>",
        headers={"Content-Type": "text/html"},
    )

    def _query_route(call: RecordedRestCall) -> FakeRestResponse:
        if call.params == {"rest_route": "/"}:
            return FakeRestResponse.from_payload(
                status_code=200,
                payload={"namespaces": ["wp/v2", "oembed/1.0"]},
                headers={"Content-Type": "application/json"},
            )
        if call.params == {"rest_route": "/wp/v2/pages", "slug": "about"}:
            return FakeRestResponse.from_payload(
                status_code=200,
                payload=[{"id": 7, "slug": "about"}],
                headers={"Content-Type": "application/json"},
            )
        raise AssertionError(f"unexpected params: {call.params}")

    boundary.add("GET", f"{site_url}/", _query_route)

    client = rest_common.WordPressRestClient(
        rest_common.WordPressRestSettings(
            schema_version="1.0",
            site_url=site_url,
            auth_header="Basic token",
            ssl_verify=False,
        )
    )

    payload = client.get("wp/v2/pages", params={"slug": "about"})

    assert payload == [{"id": 7, "slug": "about"}]
    assert len(boundary.calls) == 3
    assert boundary.calls[1].params == {"rest_route": "/"}
    assert boundary.calls[2].params == {"rest_route": "/wp/v2/pages", "slug": "about"}
    assert boundary.calls[2].verify is False


def test_load_rest_settings_from_env_reads_tls_flags(
    external_boundary_mocks_only: ExternalBoundaryMocksOnly, tmp_path
) -> None:
    external_boundary_mocks_only.chdir(tmp_path)
    external_boundary_mocks_only.setenv("WP_SITE_URL", "https://site.test")
    external_boundary_mocks_only.setenv("WP_USERNAME", "admin")
    external_boundary_mocks_only.setenv("WP_APP_PASSWORD", "secret")
    external_boundary_mocks_only.setenv("WP_SSL_VERIFY", "false")
    external_boundary_mocks_only.delenv("WP_CA_BUNDLE_PATH", raising=False)

    settings = rest_common.load_rest_settings_from_env()

    expected_token = base64.b64encode(b"admin:secret").decode("ascii")
    assert settings.site_url == "https://site.test"
    assert settings.auth_header == f"Basic {expected_token}"
    assert settings.ssl_verify is False
    assert settings.ca_bundle_path is None


def test_client_raises_when_rest_root_cannot_be_discovered(
    external_boundary_mocks_only: ExternalBoundaryMocksOnly,
) -> None:
    boundary = RequestsBoundary()
    external_boundary_mocks_only.setattr(
        rest_common.requests, "request", boundary.request
    )
    site_url = "http://site.test"

    boundary.add_json(
        "GET",
        f"{site_url}/wp-json/",
        status_code=404,
        text="<html>404</html>",
        headers={"Content-Type": "text/html"},
    )
    boundary.add_json(
        "GET",
        f"{site_url}/",
        status_code=404,
        text="<html>404</html>",
        headers={"Content-Type": "text/html"},
    )
    boundary.add_json(
        "GET",
        f"{site_url}/index.php",
        status_code=404,
        text="<html>404</html>",
        headers={"Content-Type": "text/html"},
    )

    client = rest_common.WordPressRestClient(
        rest_common.WordPressRestSettings(
            schema_version="1.0",
            site_url=site_url,
            auth_header="Basic token",
        )
    )

    with pytest.raises(
        RuntimeError, match="Unable to discover WordPress REST API root"
    ):
        client.get("wp/v2/pages")


def test_query_route_client_error_reports_effective_rest_url(
    external_boundary_mocks_only: ExternalBoundaryMocksOnly,
) -> None:
    boundary = RequestsBoundary()
    external_boundary_mocks_only.setattr(
        rest_common.requests, "request", boundary.request
    )
    site_url = "http://site.test"

    def _query_route(call: RecordedRestCall) -> FakeRestResponse:
        if call.params == {"rest_route": "/"}:
            return FakeRestResponse.from_payload(
                status_code=200,
                payload={"namespaces": ["wp/v2"]},
                headers={"Content-Type": "application/json"},
            )
        if call.params == {"rest_route": "/wp/v2/pages", "context": "edit"}:
            return FakeRestResponse.from_payload(
                status_code=401,
                payload={
                    "code": "rest_not_logged_in",
                    "message": "You are not currently logged in.",
                },
                headers={"Content-Type": "application/json"},
            )
        raise AssertionError(f"unexpected params: {call.params}")

    boundary.add_json(
        "GET",
        f"{site_url}/wp-json/",
        status_code=404,
        text="<html>404</html>",
        headers={"Content-Type": "text/html"},
    )
    boundary.add("GET", f"{site_url}/", _query_route)

    client = rest_common.WordPressRestClient(
        rest_common.WordPressRestSettings(
            schema_version="1.0",
            site_url=site_url,
            auth_header="Basic token",
        )
    )

    with pytest.raises(RuntimeError) as exc_info:
        client.get("wp/v2/pages", params={"context": "edit"})

    message = str(exc_info.value)
    assert "http://site.test/?" in message
    assert "rest_route=%2Fwp%2Fv2%2Fpages" in message
    assert "context=edit" in message
