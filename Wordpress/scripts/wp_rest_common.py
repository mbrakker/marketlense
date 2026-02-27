#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import os
import re
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Dict, NoReturn, Optional
from urllib.parse import urlparse

import requests

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


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


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
    return WordPressRestSettings(
        schema_version="1.0",
        site_url=site_url,
        auth_header=auth_header,
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
        url = f"{self._settings.site_url}/wp-json/{path.lstrip('/')}"
        headers = {
            "Authorization": self._settings.auth_header,
            "Content-Type": "application/json",
        }
        try:
            resp = requests.request(
                method,
                url,
                headers=headers,
                params=params,
                data=json.dumps(payload) if payload is not None else None,
                timeout=self._settings.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise RuntimeError(f"WordPress REST request failed: {method} {url}") from exc

        if resp.status_code >= 400:
            details = _extract_error_message(resp.text)
            raise RuntimeError(
                f"WordPress REST error {resp.status_code} on {method} {url}: {details}"
            )
        try:
            return resp.json()
        except ValueError as exc:
            raise RuntimeError(
                f"WordPress REST invalid JSON response on {method} {url}"
            ) from exc


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


def fail(message: str) -> NoReturn:
    print(message, file=sys.stderr)
    raise SystemExit(1)
