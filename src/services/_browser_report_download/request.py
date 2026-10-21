from __future__ import annotations

import secrets
from hashlib import sha1
from pathlib import Path
from urllib.parse import urlsplit

from src.contracts.browser_download import (
    BrowserDownloadIdentityField,
    BrowserReportDownloadRequest,
)
from src.services._browser_report_download.artifact_paths import (
    bounded_browser_directory_component,
    ensure_browser_directory,
    validate_browser_download_directory,
)
from src.services._config_service.identity import (
    identity_field_match_tokens,
    normalize_browser_download_identity_key,
    resolve_browser_download_delivery_emails,
    resolve_browser_download_identity_fields,
)
from src.utils.errors import AppError
from src.utils.url_utils import normalize_url

_PUBLIC_EMAIL_DOMAINS = {
    "gmail.com",
    "googlemail.com",
    "hotmail.com",
    "live.com",
    "outlook.com",
    "yahoo.com",
    "icloud.com",
    "aol.com",
    "proton.me",
    "protonmail.com",
    "pm.me",
    "gmx.com",
}

# The stable URL namespace must leave room for the short, attempt-owned child
# workspace and its managed browser profile descendants.
_DOWNLOAD_WORKSPACE_COMPONENT_RESERVATION = "a000000"
_DOWNLOAD_WORKSPACE_PATH_SEPARATOR_RESERVATION = ""


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
    if not (
        str(getattr(request.settings, "openai_api_key", "") or "").strip()
        or str(request.settings.openrouter_api_key or "").strip()
    ):
        raise AppError(
            code="browser_download_api_key_missing",
            message="OPENAI_API_KEY or OPENROUTER_API_KEY is required for local browser-use downloads",
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
    candidates = resolve_browser_download_delivery_emails(
        request.settings.identity_profile,
        url=str(request.attempt_url or request.url).strip(),
    )
    effective_fields = resolve_effective_identity_fields(request)
    for field in effective_fields:
        if field.key != "work_email":
            continue
        configured_email = str(field.value or "").strip()
        if configured_email:
            candidates.append(configured_email)
    ranked: list[tuple[int, int, str]] = []
    for index, candidate in enumerate(candidates):
        _validate_email_value(candidate, field_name="identity_profile.work_email")
        ranked.append((_email_priority(candidate), index, candidate))
    if ranked:
        ranked.sort()
        return ranked[0][2]
    return None


def resolve_effective_identity_fields(
    request: BrowserReportDownloadRequest,
) -> list:
    resolved = resolve_browser_download_identity_fields(
        request.settings.identity_profile,
        url=str(request.attempt_url or request.url).strip(),
    )
    return _apply_semantic_identity_fallbacks(resolved)


def _apply_semantic_identity_fallbacks(
    fields: list[BrowserDownloadIdentityField],
) -> list[BrowserDownloadIdentityField]:
    family_defaults: dict[str, str] = {}
    for field in fields:
        value = str(field.value or "").strip()
        if not value:
            continue
        for family in _identity_families_for_field(field):
            family_defaults.setdefault(family, value)
    hydrated: list[BrowserDownloadIdentityField] = []
    for field in fields:
        value = str(field.value or "").strip()
        if value:
            hydrated.append(field)
            continue
        replacement = ""
        for family in _identity_families_for_field(field):
            replacement = family_defaults.get(family, "")
            if replacement:
                break
        if replacement:
            hydrated.append(
                BrowserDownloadIdentityField(
                    schema_version=field.schema_version,
                    key=field.key,
                    label=field.label,
                    value=replacement,
                    aliases=list(field.aliases),
                    option_aliases=list(field.option_aliases),
                )
            )
            continue
        hydrated.append(field)
    return hydrated


def _identity_families_for_field(field: BrowserDownloadIdentityField) -> set[str]:
    tokens = identity_field_match_tokens(field)
    normalized_tokens = {
        normalize_browser_download_identity_key(token)
        for token in tokens
        if normalize_browser_download_identity_key(token)
    }
    families: set[str] = set()
    has_company_markers = any(
        (
            "company" in token
            or "organization" in token
            or "employer" in token
            or "workplace" in token
            or ("business" in token and "email" not in token)
        )
        for token in normalized_tokens
    )
    if any("email" in token for token in normalized_tokens):
        families.add("email")
    if not has_company_markers and any(
        "name" in token or token in {"given", "surname", "family"}
        for token in normalized_tokens
    ):
        families.add("name")
    if has_company_markers:
        families.add("company")
    if any(
        marker in token
        for token in normalized_tokens
        for marker in ("title", "role", "job")
    ):
        families.add("role")
    if any(
        marker in token
        for token in normalized_tokens
        for marker in ("phone", "telephone", "mobile")
    ):
        families.add("phone")
    return families


def resolve_download_dir_path(*, root_dir: str, normalized_url: str) -> Path:
    try:
        root = Path(root_dir).expanduser().resolve()
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise AppError(
            code="browser_download_output_dir_invalid",
            message="Browser download output directory could not be resolved safely",
            cause=exc,
            retryable=False,
            context={
                "windows_path_budget": 240,
                "next_action": "Set a shorter writable browser output_dir",
            },
        ) from exc
    raw_host = (urlsplit(normalized_url).netloc or "unknown_host").casefold()
    url_hash = sha1(normalized_url.encode("utf-8")).hexdigest()[:12]
    trailing_components = (
        _DOWNLOAD_WORKSPACE_PATH_SEPARATOR_RESERVATION,
        url_hash,
        _DOWNLOAD_WORKSPACE_COMPONENT_RESERVATION,
    )
    try:
        host = bounded_browser_directory_component(
            parent_dir=root,
            raw_name=raw_host,
            identity=raw_host or normalized_url,
            trailing_components=trailing_components,
        )
    except AppError:
        # The URL hash below remains the complete source identity. When a
        # deep root leaves too little room for the regular host compaction,
        # use a short deterministic label so the attempt workspace and its
        # managed profile still fit the same validated budget.
        compact_host = f"h{sha1(raw_host.encode('utf-8')).hexdigest()[:6]}"
        host = bounded_browser_directory_component(
            parent_dir=root,
            raw_name=compact_host,
            identity=raw_host or normalized_url,
            trailing_components=trailing_components,
        )
    download_dir = (root / host / url_hash).resolve()
    if download_dir != root and root not in download_dir.parents:
        raise AppError(
            code="browser_download_output_dir_invalid",
            message="Resolved browser download directory escapes the configured root",
            retryable=False,
            context={"root_dir": str(root), "download_dir": str(download_dir)},
        )
    return validate_browser_download_directory(download_dir)


def prepare_download_dir(*, root_dir: str, normalized_url: str) -> Path:
    """Resolve one stable URL namespace without deleting prior attempts."""

    download_dir = resolve_download_dir_path(
        root_dir=root_dir,
        normalized_url=normalized_url,
    )
    return ensure_browser_directory(download_dir)


def create_download_workspace(download_dir: Path) -> Path:
    """Create one short, unique workspace for a single acquisition attempt."""

    stable_dir = validate_browser_download_directory(download_dir)
    ensure_browser_directory(stable_dir)
    for _ in range(32):
        workspace_candidate = stable_dir / f"a{secrets.token_hex(3)}"
        try:
            workspace = workspace_candidate.resolve()
            workspace.relative_to(stable_dir)
        except (OSError, RuntimeError, ValueError):
            continue
        validate_browser_download_directory(workspace)
        try:
            workspace_candidate.mkdir()
        except FileExistsError:
            continue
        except OSError as exc:
            raise AppError(
                code="browser_download_output_dir_invalid",
                message="Browser download attempt workspace could not be created",
                cause=exc,
                retryable=False,
                context={
                    "download_dir": str(stable_dir),
                    "next_action": "Choose a writable browser output directory",
                },
            ) from exc
        return workspace
    raise AppError(
        code="browser_download_workspace_create_failed",
        message="Could not allocate a unique browser download attempt workspace",
        retryable=True,
        context={
            "download_dir": str(stable_dir),
            "next_action": "Retry the browser download attempt",
        },
    )


def _validate_email_value(value: str, *, field_name: str) -> None:
    token = str(value or "").strip()
    if "@" not in token or "." not in token.split("@")[-1]:
        raise AppError(
            code="browser_download_email_invalid",
            message=f"{field_name} must be a valid email address when provided",
            retryable=False,
        )


def _email_priority(email_value: str) -> int:
    domain = str(email_value or "").strip().rsplit("@", 1)[-1].lower()
    return 1 if domain in _PUBLIC_EMAIL_DOMAINS else 0
