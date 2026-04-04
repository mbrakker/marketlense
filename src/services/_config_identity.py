from __future__ import annotations

from typing import Any

from src.contracts.browser_download import (
    BrowserDownloadIdentity,
    BrowserDownloadIdentityField,
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


def load_browser_download_identity(
    path: str,
    *,
    load_yaml_mapping,
    is_missing,
) -> BrowserDownloadIdentity:
    payload = load_yaml_mapping(path, label="Browser download identity")
    raw_fields = payload.get("fields")
    if not isinstance(raw_fields, list) or not raw_fields:
        raise RuntimeError(
            f"Browser download identity YAML must contain a non-empty 'fields' list: {path}"
        )
    fields: list[BrowserDownloadIdentityField] = []
    seen_keys: set[str] = set()
    for entry in raw_fields:
        if not isinstance(entry, dict):
            raise RuntimeError(
                f"Browser download identity fields must be mappings: {path}"
            )
        key = normalize_browser_download_identity_key(entry.get("key"))
        label = str(entry.get("label") or "").strip()
        if not key or not label:
            raise RuntimeError(
                f"Browser download identity fields require non-empty key and label: {path}"
            )
        if key in seen_keys:
            raise RuntimeError(
                f"Browser download identity field keys must be unique; duplicate '{key}' in {path}"
            )
        seen_keys.add(key)
        raw_value = entry.get("value")
        value = None if is_missing(raw_value) else str(raw_value).strip()
        fields.append(
            BrowserDownloadIdentityField(
                schema_version=str(entry.get("schema_version") or "1.0"),
                key=key,
                label=label,
                value=value,
                aliases=normalize_browser_download_identity_aliases(
                    entry.get("aliases")
                ),
            )
        )
    return BrowserDownloadIdentity(
        schema_version=str(payload.get("schema_version") or "1.0"),
        fields=fields,
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
