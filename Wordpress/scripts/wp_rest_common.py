#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import os
import re
import sys
import warnings
from contextlib import contextmanager
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Dict, Iterator, NoReturn, Optional
from urllib.parse import urlencode, urlparse

import requests
import urllib3

try:
    from dotenv import find_dotenv, load_dotenv
except Exception:  # pragma: no cover - optional dependency at runtime
    find_dotenv = None
    load_dotenv = None


DEFAULT_TIMEOUT_SECONDS = 30


@dataclass(frozen=True)
class WordPressRestSettings:
    schema_version: str
    site_url: str
    auth_header: str
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    ssl_verify: bool = True
    ca_bundle_path: Optional[str] = None


@dataclass(frozen=True)
class WordPressRestEndpoint:
    schema_version: str
    request_url: str
    mode: str


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name, "").strip().lower()
    if value == "":
        return default
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(f"Invalid boolean environment variable: {name}={value}")


def load_rest_settings_from_env() -> WordPressRestSettings:
    _load_repo_env()
    site_url = require_env("WP_SITE_URL").rstrip("/")
    bearer = os.getenv("WP_BEARER_TOKEN", "").strip()
    if bearer:
        auth_header = f"Bearer {bearer}"
    else:
        username = require_env("WP_USERNAME")
        app_password = require_env("WP_APP_PASSWORD")
        raw = f"{username}:{app_password}".encode("utf-8")
        auth_header = f"Basic {base64.b64encode(raw).decode('ascii')}"
    ssl_verify = _env_bool("WP_SSL_VERIFY", True)
    ca_bundle_path = os.getenv("WP_CA_BUNDLE_PATH", "").strip() or None
    if ssl_verify and ca_bundle_path is not None and not Path(ca_bundle_path).exists():
        raise RuntimeError(f"CA bundle path does not exist: {ca_bundle_path}")
    return WordPressRestSettings(
        schema_version="1.0",
        site_url=site_url,
        auth_header=auth_header,
        ssl_verify=ssl_verify,
        ca_bundle_path=ca_bundle_path,
    )


def _load_repo_env() -> None:
    env_path = ""
    if load_dotenv is not None and find_dotenv is not None:
        env_path = find_dotenv(filename=".env", usecwd=True)
        if env_path:
            load_dotenv(env_path, override=False)
            return
    fallback = _find_env_file()
    if fallback is not None:
        _load_env_file_manually(fallback)


def _find_env_file() -> Optional[Path]:
    current = Path.cwd().resolve()
    for directory in [current, *current.parents]:
        candidate = directory / ".env"
        if candidate.is_file():
            return candidate
    return None


def _load_env_file_manually(path: Path) -> None:
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if key not in os.environ and value:
            os.environ[key] = value


class WordPressRestClient:
    def __init__(self, settings: WordPressRestSettings) -> None:
        self._settings = settings
        self._endpoint: Optional[WordPressRestEndpoint] = None

    @property
    def site_url(self) -> str:
        return self._settings.site_url

    def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        return self._request("GET", path, params=params)

    def post(self, path: str, payload: Optional[Dict[str, Any]] = None) -> Any:
        return self._request("POST", path, payload=payload or {})

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Any:
        endpoint = self._resolve_endpoint()
        url, request_params = self._build_request_target(endpoint, path, params)
        display_url = _format_request_url(url, request_params)
        headers = {
            "Authorization": self._settings.auth_header,
            "Content-Type": "application/json",
        }
        try:
            with _suppress_insecure_request_warning(
                ssl_verify=self._settings.ssl_verify
            ):
                resp = requests.request(
                    method,
                    url,
                    headers=headers,
                    params=request_params,
                    data=json.dumps(payload) if payload is not None else None,
                    timeout=self._settings.timeout_seconds,
                    verify=_requests_verify(self._settings),
                )
        except requests.RequestException as exc:
            raise RuntimeError(
                f"WordPress REST request failed: {method} {display_url}"
            ) from exc

        if resp.status_code >= 400:
            details = _extract_error_message(resp.text)
            raise RuntimeError(
                f"WordPress REST error {resp.status_code} on {method} {display_url}: {details}"
            )
        try:
            return resp.json()
        except ValueError as exc:
            raise RuntimeError(
                f"WordPress REST invalid JSON response on {method} {display_url}"
            ) from exc

    def _resolve_endpoint(self) -> WordPressRestEndpoint:
        if self._endpoint is not None:
            return self._endpoint
        self._endpoint = self._discover_endpoint()
        return self._endpoint

    def _discover_endpoint(self) -> WordPressRestEndpoint:
        site_url = self._settings.site_url.rstrip("/")
        candidates = [
            WordPressRestEndpoint(
                schema_version="1.0",
                request_url=f"{site_url}/wp-json/",
                mode="pretty",
            ),
            WordPressRestEndpoint(
                schema_version="1.0",
                request_url=f"{site_url}/",
                mode="query",
            ),
            WordPressRestEndpoint(
                schema_version="1.0",
                request_url=f"{site_url}/index.php",
                mode="index",
            ),
        ]
        last_error: Optional[str] = None
        for candidate in candidates:
            try:
                payload = self._probe_endpoint(candidate)
            except RuntimeError as exc:
                last_error = str(exc)
                continue
            if self._is_rest_index(payload):
                return candidate
            last_error = (
                "REST discovery probe returned a non-index payload "
                f"for mode '{candidate.mode}'"
            )
        detail = last_error or "no candidate endpoint returned a REST index payload"
        raise RuntimeError(
            "Unable to discover WordPress REST API root. "
            "Verify the site URL, REST availability, and TLS settings. "
            f"Last probe result: {detail}"
        )

    def _probe_endpoint(self, endpoint: WordPressRestEndpoint) -> Any:
        params = self._probe_params(endpoint)
        try:
            with _suppress_insecure_request_warning(
                ssl_verify=self._settings.ssl_verify
            ):
                resp = requests.request(
                    "GET",
                    endpoint.request_url,
                    headers={"Authorization": self._settings.auth_header},
                    params=params,
                    timeout=self._settings.timeout_seconds,
                    verify=_requests_verify(self._settings),
                )
        except requests.RequestException as exc:
            raise RuntimeError(
                f"REST discovery probe failed for mode '{endpoint.mode}'"
            ) from exc
        if resp.status_code >= 400:
            details = _extract_error_message(resp.text)
            raise RuntimeError(
                f"REST discovery probe failed for mode '{endpoint.mode}' "
                f"with status {resp.status_code}: {details}"
            )
        try:
            return resp.json()
        except ValueError as exc:
            raise RuntimeError(
                f"REST discovery probe for mode '{endpoint.mode}' returned invalid JSON"
            ) from exc

    def _build_request_target(
        self,
        endpoint: WordPressRestEndpoint,
        path: str,
        params: Optional[Dict[str, Any]],
    ) -> tuple[str, Optional[Dict[str, Any]]]:
        normalized_path = f"/{path.lstrip('/')}"
        request_params = dict(params or {})
        if endpoint.mode == "pretty":
            return f"{self._settings.site_url}/wp-json/{path.lstrip('/')}", request_params
        request_params["rest_route"] = normalized_path
        return endpoint.request_url, request_params

    def _probe_params(
        self, endpoint: WordPressRestEndpoint
    ) -> Optional[Dict[str, Any]]:
        if endpoint.mode == "pretty":
            return None
        return {"rest_route": "/"}

    def _is_rest_index(self, payload: Any) -> bool:
        if not isinstance(payload, dict):
            return False
        namespaces = payload.get("namespaces")
        if not isinstance(namespaces, list):
            return False
        return "wp/v2" in {str(namespace) for namespace in namespaces}


def _requests_verify(settings: WordPressRestSettings) -> bool | str:
    if not settings.ssl_verify:
        return False
    bundle_path = str(settings.ca_bundle_path or "").strip()
    return bundle_path or True


@contextmanager
def _suppress_insecure_request_warning(*, ssl_verify: bool) -> Iterator[None]:
    if ssl_verify:
        yield
        return
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", urllib3.exceptions.InsecureRequestWarning)
        yield


def slugify(value: str) -> str:
    token = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    token = token.strip("-")
    return token or "item"


def normalize_homepage(value: str) -> str:
    candidate = value.strip()
    if not candidate:
        return ""
    if "://" not in candidate:
        candidate = f"https://{candidate}"
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RuntimeError(f"Invalid homepage URL: {value}")
    if parsed.scheme == "http":
        https_candidate = parsed._replace(scheme="https").geturl()
        parsed_https = urlparse(https_candidate)
        if parsed_https.netloc:
            return https_candidate
    return candidate


def _extract_error_message(raw_text: str) -> str:
    try:
        payload = json.loads(raw_text)
    except ValueError:
        return raw_text.strip()[:500] or "unknown error"
    if isinstance(payload, dict):
        if payload.get("message"):
            return str(payload["message"])
        if payload.get("code"):
            return str(payload["code"])
    return raw_text.strip()[:500] or "unknown error"


def _format_request_url(url: str, params: Optional[Dict[str, Any]]) -> str:
    if not params:
        return url
    return f"{url}?{urlencode(params, doseq=True)}"


def fail(message: str) -> NoReturn:
    print(message, file=sys.stderr)
    raise SystemExit(1)
