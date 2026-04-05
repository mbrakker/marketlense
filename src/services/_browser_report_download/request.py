from __future__ import annotations

from hashlib import sha1
from pathlib import Path
from shutil import rmtree
from urllib.parse import urlsplit

from src.contracts.browser_download import BrowserReportDownloadRequest
from src.utils.errors import AppError
from src.utils.url_utils import normalize_url


def validate_common_request(
    request: BrowserReportDownloadRequest,
    normalized_url: str,
) -> None:
    if not normalized_url:
        raise AppError(
            code="browser_download_url_invalid",
            message="A valid absolute URL is required for browser downloads",
            retryable=False,
        )
    if not request.settings.output_dir or not str(request.settings.output_dir).strip():
        raise AppError(
            code="browser_download_output_dir_missing",
            message="Browser download output directory is required",
            retryable=False,
        )


def validate_browser_runtime_settings(
    request: BrowserReportDownloadRequest,
) -> None:
    if (
        not request.settings.openrouter_api_key
        or not request.settings.openrouter_api_key.strip()
    ):
        raise AppError(
            code="browser_download_api_key_missing",
            message="OPENROUTER_API_KEY is required for local browser-use downloads",
            retryable=False,
        )
    if not request.settings.model or not request.settings.model.strip():
        raise AppError(
            code="browser_download_model_missing",
            message="A browser-download model must be configured",
            retryable=False,
        )


def validate_and_normalize_url(url: str) -> str:
    normalized_url = normalize_url(url)
    parts = urlsplit(normalized_url)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return ""
    return normalized_url


def url_looks_like_direct_pdf(normalized_url: str) -> bool:
    path = str(urlsplit(normalized_url).path or "").strip().lower()
    return path.endswith(".pdf")


def resolve_delivery_email_value(
    request: BrowserReportDownloadRequest,
) -> str | None:
    explicit_email = str(request.delivery_email or "").strip()
    if explicit_email:
        _validate_email_value(explicit_email, field_name="delivery_email")
        return explicit_email
    for field in request.settings.identity_profile.fields:
        if field.key != "work_email":
            continue
        configured_email = str(field.value or "").strip()
        if configured_email:
            _validate_email_value(configured_email, field_name="identity_profile.work_email")
            return configured_email
    return None


def prepare_download_dir(*, root_dir: str, normalized_url: str) -> Path:
    root = Path(root_dir).expanduser().resolve()
    host = urlsplit(normalized_url).netloc.replace(":", "_") or "unknown_host"
    url_hash = sha1(normalized_url.encode("utf-8")).hexdigest()[:12]
    download_dir = (root / host / url_hash).resolve()
    if download_dir != root and root not in download_dir.parents:
        raise AppError(
            code="browser_download_output_dir_invalid",
            message="Resolved browser download directory escapes the configured root",
            retryable=False,
            context={"root_dir": str(root), "download_dir": str(download_dir)},
        )
    if download_dir.exists():
        for child in download_dir.iterdir():
            if child.is_dir():
                rmtree(child)
            else:
                child.unlink()
    else:
        download_dir.mkdir(parents=True, exist_ok=True)
    return download_dir


def _validate_email_value(value: str, *, field_name: str) -> None:
    token = str(value or "").strip()
    if "@" not in token or "." not in token.split("@")[-1]:
        raise AppError(
            code="browser_download_email_invalid",
            message=f"{field_name} must be a valid email address when provided",
            retryable=False,
        )
