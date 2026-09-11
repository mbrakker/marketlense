"""Canonical report identity accessors.

These helpers intentionally only read the admitted values carried by
``RunContext``.  Checksums, file IDs, and display metadata are not identities
and must never be promoted into provenance or budget fields.
"""

from __future__ import annotations

from typing import Any

from src.utils.errors import AppError


def canonical_source_identity_id(ctx: Any) -> str:
    """Return the canonical source identity, or an empty value when absent."""

    return str(getattr(ctx, "source_identity_id", "") or "").strip()


def canonical_publisher_id(ctx: Any) -> str:
    """Return the canonical publisher identity, or an empty value when absent."""

    return str(getattr(ctx, "publisher_id", "") or "").strip()


def require_admitted_report_identity(
    ctx: Any,
    *,
    legacy_source_values: tuple[str | None, ...] = (),
    legacy_publisher_values: tuple[str | None, ...] = (),
) -> tuple[str, str]:
    """Fail closed before a report workflow performs provider side effects."""

    source_identity_id = canonical_source_identity_id(ctx)
    publisher_id = canonical_publisher_id(ctx)
    missing = [
        name
        for name, value in (
            ("source_identity_id", source_identity_id),
            ("publisher_id", publisher_id),
        )
        if not value
    ]
    legacy_source_ids = {
        str(value or "").strip()
        for value in legacy_source_values
        if str(value or "").strip()
    }
    legacy_publisher_ids = {
        str(value or "").strip().casefold()
        for value in legacy_publisher_values
        if str(value or "").strip()
    }
    invalid = []
    if source_identity_id and source_identity_id in legacy_source_ids:
        invalid.append("source_identity_id")
    if publisher_id and (
        publisher_id.casefold()
        in {"unattributed", "drive_unattributed", "unknown", "unknown publisher"}
        or publisher_id.casefold() in legacy_publisher_ids
    ):
        invalid.append("publisher_id")
    if missing or invalid:
        raise AppError(
            code="report_canonical_identity_missing",
            message=(
                "Admitted report workflow requires canonical source and publisher "
                "identities"
            ),
            retryable=False,
            context={
                "missing_fields": missing,
                "invalid_fields": invalid,
                "run_id": str(getattr(ctx, "run_id", "") or "").strip(),
                "report_id": str(getattr(ctx, "report_id", "") or "").strip(),
            },
        )
    return source_identity_id, publisher_id
