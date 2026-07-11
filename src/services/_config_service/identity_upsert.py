from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import yaml

from src.contracts.browser_download import (
    BrowserDownloadIdentityField,
    BrowserDownloadIdentityFieldUpsertRequest,
    BrowserDownloadIdentityFieldUpsertResponse,
    BrowserDownloadPublisherOverride,
    BrowserDownloadRequiredSelectOverrideProposal,
    BrowserDownloadRequiredSelectOverrideRequest,
    BrowserDownloadRequiredSelectOverrideResponse,
)
from src.contracts.run_context import RunContext
from src.services._config_service.common import (
    _is_missing,
    _load_browser_download_identity,
    _load_yaml_mapping,
    _plan_browser_download_identity_field_upserts,
    _serialize_browser_download_identity,
    log_event,
    logger,
)
from src.services._config_service.identity import (
    identity_field_match_tokens,
    normalize_browser_download_identity_key,
)

_SAFE_REQUIRED_SELECT_FAMILIES = {
    "company_size": (
        "company_size",
        "employee_count",
        "employees",
        "number_of_employees",
    ),
    "revenue_band": ("revenue", "annual_revenue", "turnover"),
    "country": ("country", "country_region", "region_country"),
    "industry": ("industry", "sector"),
    "department": ("department", "business_department"),
    "organization_type": ("organization_type", "organisation_type", "company_type"),
}
_SENSITIVE_REQUIRED_SELECT_TOKENS = {
    "job_role",
    "role",
    "job_title",
    "title",
    "seniority",
    "phone",
    "mobile",
    "password",
    "consent",
    "newsletter",
}

def upsert_browser_download_identity_fields(
    request: BrowserDownloadIdentityFieldUpsertRequest,
    ctx: RunContext,
) -> BrowserDownloadIdentityFieldUpsertResponse:
    identity_path = Path(request.path).expanduser().resolve()
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_download_identity_upsert_start",
            module=logger.name,
            fields={
                "path": str(identity_path),
                "encountered_form_fields": request.encountered_form_fields,
            },
        )
    )
    identity_profile = _load_browser_download_identity(
        str(identity_path),
        load_yaml_mapping=_load_yaml_mapping,
        is_missing=_is_missing,
    )
    added_fields = _plan_browser_download_identity_field_upserts(
        identity_profile,
        encountered_form_fields=request.encountered_form_fields,
    )
    if added_fields:
        payload = _serialize_browser_download_identity(
            identity_profile,
            extra_fields=added_fields,
        )
        identity_path.parent.mkdir(parents=True, exist_ok=True)
        identity_path.write_text(
            yaml.safe_dump(payload, sort_keys=False, allow_unicode=False),
            encoding="utf-8",
        )

    response = BrowserDownloadIdentityFieldUpsertResponse(
        schema_version="1.0",
        path=str(identity_path),
        added_field_keys=[field.key for field in added_fields],
        total_fields=len(identity_profile.fields) + len(added_fields),
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_download_identity_upsert_complete",
            module=logger.name,
            fields=asdict(response),
        )
    )
    return response


def upsert_browser_download_required_select_overrides(
    request: BrowserDownloadRequiredSelectOverrideRequest,
    ctx: RunContext,
) -> BrowserDownloadRequiredSelectOverrideResponse:
    identity_path = Path(request.path).expanduser().resolve()
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_download_required_select_upsert_start",
            module=logger.name,
            fields={
                "path": str(identity_path),
                "evidence_count": len(request.evidence),
            },
        )
    )
    identity_profile = _load_browser_download_identity(
        str(identity_path),
        load_yaml_mapping=_load_yaml_mapping,
        is_missing=_is_missing,
    )
    overrides = list(identity_profile.publisher_overrides)
    proposals: list[BrowserDownloadRequiredSelectOverrideProposal] = []
    changed = False
    for evidence in request.evidence:
        proposal, overrides, item_changed = _plan_required_select_override(
            identity_profile,
            overrides,
            evidence=evidence,
            approved_defaults=dict(request.approved_defaults),
        )
        proposals.append(proposal)
        changed = changed or item_changed
    if changed:
        payload = _serialize_browser_download_identity(
            type(identity_profile)(
                schema_version=identity_profile.schema_version,
                fields=identity_profile.fields,
                delivery_emails=identity_profile.delivery_emails,
                publisher_overrides=overrides,
                consent_policy=identity_profile.consent_policy,
            )
        )
        identity_path.parent.mkdir(parents=True, exist_ok=True)
        identity_path.write_text(
            yaml.safe_dump(payload, sort_keys=False, allow_unicode=False),
            encoding="utf-8",
        )
    response = BrowserDownloadRequiredSelectOverrideResponse(
        schema_version="1.0",
        path=str(identity_path),
        proposals=proposals,
        applied_count=sum(1 for proposal in proposals if proposal.status == "applied"),
        refused_count=sum(
            1
            for proposal in proposals
            if proposal.status in {"refused", "refused_sensitive_field"}
        ),
        unchanged_count=sum(
            1 for proposal in proposals if proposal.status == "unchanged"
        ),
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_download_required_select_upsert_complete",
            module=logger.name,
            fields=asdict(response),
        )
    )
    return response


def _plan_required_select_override(
    identity_profile,
    overrides: list[BrowserDownloadPublisherOverride],
    *,
    evidence,
    approved_defaults: dict[str, str],
) -> tuple[
    BrowserDownloadRequiredSelectOverrideProposal,
    list[BrowserDownloadPublisherOverride],
    bool,
]:
    host = _normalize_host(evidence.host)
    label = _stable_label(evidence.field_label)
    family = _required_select_family(label, evidence.field_name)
    options = _visible_options(evidence.options)
    selected_value, match_source = _required_select_value(
        identity_profile,
        family=family,
        options=options,
        approved_defaults=approved_defaults,
    )
    if not host or not label:
        return (
            _required_select_proposal(
                host=host,
                field_key="",
                field_label=label,
                selected_value="",
                option_alias="",
                semantic_family=family,
                match_source="refused",
                status="refused",
                reason="missing_host_or_label",
            ),
            overrides,
            False,
        )
    if not family:
        token = normalize_browser_download_identity_key(
            f"{evidence.field_label} {evidence.field_name}"
        )
        sensitive = any(
            sensitive_token in token
            for sensitive_token in _SENSITIVE_REQUIRED_SELECT_TOKENS
        )
        return (
            _required_select_proposal(
                host=host,
                field_key="",
                field_label=label,
                selected_value="",
                option_alias="",
                semantic_family="",
                match_source="refused",
                status="refused_sensitive_field" if sensitive else "refused",
                reason="sensitive_required_select_field"
                if sensitive
                else "unsafe_or_unknown_required_select_family",
            ),
            overrides,
            False,
        )
    if not selected_value:
        return (
            _required_select_proposal(
                host=host,
                field_key=family,
                field_label=label,
                selected_value="",
                option_alias="",
                semantic_family=family,
                match_source="refused",
                status="refused",
                reason="no_safe_identity_value_or_approved_default",
            ),
            overrides,
            False,
        )
    new_field = BrowserDownloadIdentityField(
        schema_version="1.0",
        key=family,
        label=label,
        value=selected_value,
        aliases=[label],
        option_aliases=[selected_value],
    )
    next_overrides, changed, status = _upsert_host_override(
        overrides,
        host=host,
        field=new_field,
    )
    return (
        _required_select_proposal(
            host=host,
            field_key=family,
            field_label=label,
            selected_value=selected_value,
            option_alias=selected_value,
            semantic_family=family,
            match_source=match_source,
            status=status,
            reason="override_ready" if changed else "override_already_present",
        ),
        next_overrides,
        changed,
    )


def _required_select_proposal(
    *,
    host: str,
    field_key: str,
    field_label: str,
    selected_value: str,
    option_alias: str,
    semantic_family: str,
    match_source: str,
    status: str,
    reason: str,
) -> BrowserDownloadRequiredSelectOverrideProposal:
    return BrowserDownloadRequiredSelectOverrideProposal(
        schema_version="1.0",
        host=host,
        field_key=field_key,
        field_label=field_label,
        selected_value=selected_value,
        option_alias=option_alias,
        semantic_family=semantic_family,
        match_source=match_source,
        status=status,
        reason=reason,
    )


def _normalize_host(value: object) -> str:
    return str(value or "").strip().lower().removeprefix("www.")


def _stable_label(value: object) -> str:
    return " ".join(str(value or "").strip().split())


def _required_select_family(label: object, name: object) -> str:
    token = normalize_browser_download_identity_key(f"{label} {name}")
    token_parts = set(part for part in token.split("_") if part)
    if any(sensitive in token for sensitive in _SENSITIVE_REQUIRED_SELECT_TOKENS):
        if "department" not in token_parts:
            return ""
    for family, aliases in _SAFE_REQUIRED_SELECT_FAMILIES.items():
        if any(alias == token or alias in token for alias in aliases):
            return family
    return ""


def _visible_options(raw_options: object) -> list[str]:
    if not isinstance(raw_options, list):
        return []
    options: list[str] = []
    seen: set[str] = set()
    for raw_option in raw_options:
        option = _stable_label(raw_option)
        if not option:
            continue
        lowered = option.casefold()
        if lowered in {"select", "choose", "please select", "none"}:
            continue
        if lowered in seen:
            continue
        seen.add(lowered)
        options.append(option)
    return options


def _required_select_value(
    identity_profile,
    *,
    family: str,
    options: list[str],
    approved_defaults: dict[str, str],
) -> tuple[str, str]:
    if not family or not options:
        return "", ""
    option_by_key = {normalize_browser_download_identity_key(value): value for value in options}
    for field in identity_profile.fields:
        if family not in identity_field_match_tokens(field) and field.key != family:
            continue
        for candidate in [field.value, *field.option_aliases]:
            key = normalize_browser_download_identity_key(candidate)
            if key in option_by_key:
                return option_by_key[key], "identity_fact"
    default = approved_defaults.get(family) or approved_defaults.get(family.replace("_", " "))
    default_key = normalize_browser_download_identity_key(default)
    if default_key in option_by_key:
        return option_by_key[default_key], "approved_default"
    return "", ""


def _upsert_host_override(
    overrides: list[BrowserDownloadPublisherOverride],
    *,
    host: str,
    field: BrowserDownloadIdentityField,
) -> tuple[list[BrowserDownloadPublisherOverride], bool, str]:
    next_overrides: list[BrowserDownloadPublisherOverride] = []
    matched = False
    changed = False
    status = "applied"
    for override in overrides:
        if override.host_pattern != host:
            next_overrides.append(override)
            continue
        matched = True
        fields = list(override.field_values)
        replaced = False
        for index, existing in enumerate(fields):
            if existing.key != field.key:
                continue
            replaced = True
            if (
                existing.value == field.value
                and field.label in existing.aliases
                and field.value in existing.option_aliases
            ):
                status = "unchanged"
            else:
                alias_set = list(dict.fromkeys([*existing.aliases, field.label]))
                option_aliases = list(
                    dict.fromkeys([*existing.option_aliases, field.value or ""])
                )
                fields[index] = BrowserDownloadIdentityField(
                    schema_version="1.0",
                    key=field.key,
                    label=existing.label or field.label,
                    value=field.value,
                    aliases=[alias for alias in alias_set if alias],
                    option_aliases=[alias for alias in option_aliases if alias],
                )
                changed = True
            break
        if not replaced:
            fields.append(field)
            changed = True
        next_overrides.append(
            BrowserDownloadPublisherOverride(
                schema_version=override.schema_version,
                host_pattern=override.host_pattern,
                delivery_emails=override.delivery_emails,
                field_values=fields,
            )
        )
    if not matched:
        next_overrides.append(
            BrowserDownloadPublisherOverride(
                schema_version="1.0",
                host_pattern=host,
                delivery_emails=[],
                field_values=[field],
            )
        )
        changed = True
    return next_overrides, changed, status if not changed else "applied"

__all__ = [name for name in globals() if not name.startswith("__")]
