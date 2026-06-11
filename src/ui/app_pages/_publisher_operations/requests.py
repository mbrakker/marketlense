from __future__ import annotations

# ruff: noqa: F401,F403,F405,F821

from .shared import *  # noqa: F401,F403


def build_publisher_discovery_request_payload(*, insights_url: str) -> dict[str, str]:
    return {"insights_url": str(insights_url or "").strip()}


def build_report_download_request_payload(
    *,
    url: str,
    delivery_email: str,
) -> dict[str, str]:
    return {
        "url": str(url or "").strip(),
        "delivery_email": str(delivery_email or "").strip(),
    }


def build_acquisition_audit_request_payload(
    *,
    publisher_limit: int,
    candidate_limit_per_publisher: int,
    delivery_email: str,
) -> dict[str, int | str]:
    return {
        "publisher_limit": int(publisher_limit),
        "candidate_limit_per_publisher": int(candidate_limit_per_publisher),
        "delivery_email": str(delivery_email or "").strip(),
    }


def build_publisher_choice_options(publishers: list[object]) -> list[dict[str, str]]:
    options: list[dict[str, str]] = []
    for publisher in publishers:
        name = str(getattr(publisher, "name", "") or "").strip()
        url = str(getattr(publisher, "insights_url", "") or "").strip()
        if not name or not url:
            continue
        host = str(urlsplit(url).hostname or "").strip().lower()
        label = name if not host else f"{name} ({host})"
        options.append(
            {
                "label": label,
                "name": name,
                "url": url,
                "host": host,
            }
        )
    options.sort(key=lambda item: item["name"].casefold())
    return options


def build_saved_delivery_email_options(browser_settings: object | None) -> list[str]:
    identity_profile = getattr(browser_settings, "identity_profile", None)
    if identity_profile is None:
        return []
    raw_values: list[object] = []
    raw_values.extend(getattr(identity_profile, "delivery_emails", []) or [])
    for field in getattr(identity_profile, "fields", []) or []:
        raw_values.append(getattr(field, "value", None))
    for override in getattr(identity_profile, "publisher_overrides", []) or []:
        raw_values.extend(getattr(override, "delivery_emails", []) or [])
        for field in getattr(override, "field_values", []) or []:
            raw_values.append(getattr(field, "value", None))

    emails: list[str] = []
    seen: set[str] = set()
    for raw_value in raw_values:
        token = str(raw_value or "").strip()
        if "@" not in token:
            continue
        marker = token.casefold()
        if marker in seen:
            continue
        seen.add(marker)
        emails.append(token)
    return emails


def resolve_delivery_email_value(
    *,
    mode: str,
    saved_email: str,
    custom_email: str,
) -> str:
    if mode == "Use saved email":
        return str(saved_email or "").strip()
    if mode == "Custom email":
        return str(custom_email or "").strip()
    return ""


def resolve_audit_limits(
    *,
    preset: str,
    custom_publisher_limit: int,
    custom_candidate_limit: int,
) -> tuple[int, int]:
    if preset in _AUDIT_PRESETS:
        return _AUDIT_PRESETS[preset]
    return int(custom_publisher_limit), int(custom_candidate_limit)


def resolve_path_choice(
    *,
    mode: str,
    configured_path: str,
    custom_path: str,
) -> str:
    if mode == "Custom path":
        return str(custom_path or "").strip()
    return str(configured_path or "").strip()


def oauth_file_status_label(
    *,
    path_mode: str,
    selected_path: str,
    configured_path: str,
) -> str:
    selected = str(selected_path or "").strip()
    configured = str(configured_path or "").strip()
    if not selected:
        return "Missing: path not set"
    if path_mode == "Custom path":
        return "Selected; validated during login"
    if configured and os.path.exists(configured):
        return f"Present: {configured}"
    return f"Missing: {configured or 'path not set'}"


__all__ = [
    name
    for name in globals()
    if not name.startswith("__") and name not in {"annotations"}
]
