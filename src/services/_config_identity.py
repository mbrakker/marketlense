from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from src.contracts.browser_download import (
    BrowserDownloadIdentity,
    BrowserDownloadIdentityField,
    BrowserDownloadPublisherOverride,
)


def normalize_browser_download_identity_key(raw_value: Any) -> str:
    token = str(raw_value or "").strip().lower()
    characters: list[str] = []
    previous_was_separator = False
    for char in token:
        if char.isalnum():
            characters.append(char)
            previous_was_separator = False
            continue
        if previous_was_separator:
            continue
        characters.append("_")
        previous_was_separator = True
    normalized = "".join(characters).strip("_")
    return normalized


def normalize_browser_download_identity_aliases(raw_value: Any) -> list[str]:
    if not isinstance(raw_value, list):
        return []
    aliases: list[str] = []
    seen: set[str] = set()
    for item in raw_value:
        token = str(item or "").strip()
        if not token:
            continue
        normalized = token.casefold()
        if normalized in seen:
            continue
        aliases.append(token)
        seen.add(normalized)
    return aliases


def _coerce_string_list(raw_value: Any) -> list[str]:
    if not isinstance(raw_value, list):
        return []
    values: list[str] = []
    seen: set[str] = set()
    for item in raw_value:
        token = str(item or "").strip()
        if not token:
            continue
        marker = token.casefold()
        if marker in seen:
            continue
        seen.add(marker)
        values.append(token)
    return values


def _parse_identity_fields(
    raw_fields: Any,
    *,
    path: str,
    field_scope: str,
    is_missing,
    allow_empty: bool = False,
) -> list[BrowserDownloadIdentityField]:
    if not isinstance(raw_fields, list):
        if allow_empty:
            return []
        raise RuntimeError(
            f"{field_scope} must be a non-empty list of mappings: {path}"
        )
    if not raw_fields and not allow_empty:
        raise RuntimeError(f"{field_scope} must not be empty: {path}")
    fields: list[BrowserDownloadIdentityField] = []
    seen_keys: set[str] = set()
    for entry in raw_fields:
        if not isinstance(entry, dict):
            raise RuntimeError(f"{field_scope} entries must be mappings: {path}")
        key = normalize_browser_download_identity_key(entry.get("key"))
        label = str(entry.get("label") or "").strip()
        if not key or not label:
            raise RuntimeError(
                f"{field_scope} entries require non-empty key and label: {path}"
            )
        if key in seen_keys:
            raise RuntimeError(
                f"{field_scope} keys must be unique; duplicate '{key}' in {path}"
            )
        seen_keys.add(key)
        fields.append(
            BrowserDownloadIdentityField(
                schema_version=str(entry.get("schema_version") or "1.0"),
                key=key,
                label=label,
                value=str(entry.get("value")).strip()
                if not is_missing(entry.get("value"))
                else None,
                aliases=normalize_browser_download_identity_aliases(
                    entry.get("aliases")
                ),
            )
        )
    return fields


def load_browser_download_identity(
    path: str,
    *,
    load_yaml_mapping,
    is_missing,
) -> BrowserDownloadIdentity:
    payload = load_yaml_mapping(path, label="Browser download identity")
    fields = _parse_identity_fields(
        payload.get("fields"),
        path=path,
        field_scope="Browser download identity fields",
        is_missing=is_missing,
    )
    publisher_overrides: list[BrowserDownloadPublisherOverride] = []
    raw_overrides = payload.get("publisher_overrides")
    if raw_overrides is not None:
        if not isinstance(raw_overrides, list):
            raise RuntimeError(
                f"Browser download identity publisher_overrides must be a list: {path}"
            )
        for entry in raw_overrides:
            if not isinstance(entry, dict):
                raise RuntimeError(
                    f"Browser download identity publisher overrides must be mappings: {path}"
                )
            host_pattern = str(entry.get("host_pattern") or "").strip().lower()
            if not host_pattern:
                raise RuntimeError(
                    f"Browser download identity publisher overrides require host_pattern: {path}"
                )
            publisher_overrides.append(
                BrowserDownloadPublisherOverride(
                    schema_version=str(entry.get("schema_version") or "1.0"),
                    host_pattern=host_pattern,
                    delivery_emails=_coerce_string_list(entry.get("delivery_emails")),
                    field_values=_parse_identity_fields(
                        entry.get("field_values") or [],
                        path=path,
                        field_scope=(
                            "Browser download identity publisher override field_values"
                        ),
                        is_missing=is_missing,
                        allow_empty=True,
                    ),
                )
            )
    return BrowserDownloadIdentity(
        schema_version=str(payload.get("schema_version") or "1.0"),
        fields=fields,
        delivery_emails=_coerce_string_list(payload.get("delivery_emails")),
        publisher_overrides=publisher_overrides,
    )


def identity_field_match_tokens(field: BrowserDownloadIdentityField) -> set[str]:
    tokens = {
        normalize_browser_download_identity_key(field.key),
        normalize_browser_download_identity_key(field.label),
    }
    for alias in field.aliases:
        token = normalize_browser_download_identity_key(alias)
        if token:
            tokens.add(token)
    return {token for token in tokens if token}


def resolve_browser_download_publisher_override(
    identity_profile: BrowserDownloadIdentity,
    *,
    url: str,
) -> BrowserDownloadPublisherOverride | None:
    host = str(urlsplit(str(url or "").strip()).hostname or "").strip().lower()
    if not host:
        return None
    exact_matches: list[BrowserDownloadPublisherOverride] = []
    suffix_matches: list[BrowserDownloadPublisherOverride] = []
    for override in identity_profile.publisher_overrides:
        pattern = str(override.host_pattern or "").strip().lower().lstrip(".")
        if not pattern:
            continue
        if host == pattern:
            exact_matches.append(override)
            continue
        if pattern.startswith("*."):
            pattern = pattern[2:]
        if host.endswith(f".{pattern}"):
            suffix_matches.append(override)
    if exact_matches:
        exact_matches.sort(key=lambda item: len(item.host_pattern), reverse=True)
        return exact_matches[0]
    if suffix_matches:
        suffix_matches.sort(key=lambda item: len(item.host_pattern), reverse=True)
        return suffix_matches[0]
    return None


def resolve_browser_download_identity_fields(
    identity_profile: BrowserDownloadIdentity,
    *,
    url: str,
) -> list[BrowserDownloadIdentityField]:
    merged: dict[str, BrowserDownloadIdentityField] = {
        field.key: field for field in identity_profile.fields
    }
    ordered_keys = [field.key for field in identity_profile.fields]
    override = resolve_browser_download_publisher_override(identity_profile, url=url)
    if override is None:
        return [merged[key] for key in ordered_keys]
    for field in override.field_values:
        if field.key not in merged:
            ordered_keys.append(field.key)
        merged[field.key] = field
    return [merged[key] for key in ordered_keys]


def resolve_browser_download_delivery_emails(
    identity_profile: BrowserDownloadIdentity,
    *,
    url: str,
) -> list[str]:
    override = resolve_browser_download_publisher_override(identity_profile, url=url)
    candidates: list[str] = []
    seen: set[str] = set()
    for raw_email in [
        *(override.delivery_emails if override is not None else []),
        *identity_profile.delivery_emails,
    ]:
        token = str(raw_email or "").strip()
        if not token:
            continue
        marker = token.casefold()
        if marker in seen:
            continue
        seen.add(marker)
        candidates.append(token)
    return candidates


def should_upsert_browser_download_identity_field(
    *,
    label: str,
    normalized_key: str,
) -> bool:
    lowered_label = str(label or "").strip().casefold()
    if not lowered_label or not normalized_key:
        return False
    alpha_count = sum(1 for char in lowered_label if char.isalpha())
    if alpha_count < 2:
        return False
    blocked_exact = {
        "submit",
        "send",
        "download",
        "download report",
        "get report",
        "get the report",
        "view report",
        "learn more",
        "read more",
        "continue",
        "next",
        "back",
        "cancel",
        "close",
        "search",
        "reset",
        "clear",
        "required",
        "optional",
        "captcha",
        "recaptcha",
        "privacy policy",
        "terms",
        "i agree",
        "consent",
    }
    if lowered_label in blocked_exact:
        return False
    blocked_prefixes = (
        "select ",
        "choose ",
        "option ",
        "click ",
    )
    if any(lowered_label.startswith(prefix) for prefix in blocked_prefixes):
        return False
    return True
