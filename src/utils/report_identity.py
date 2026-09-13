"""Canonical report identity accessors.

These helpers intentionally only read the admitted values carried by
``RunContext``.  Checksums, file IDs, and display metadata are not identities
and must never be promoted into provenance or budget fields.
"""

from __future__ import annotations

from typing import Any

from src.utils.errors import AppError

_UNATTRIBUTED_PUBLISHER_IDS = frozenset(
    {"", "unattributed", "drive_unattributed", "unknown", "unknown publisher"}
)


def canonical_source_identity_id(ctx: Any) -> str:
    """Return the canonical source identity, or an empty value when absent."""

    return str(getattr(ctx, "source_identity_id", "") or "").strip()


def canonical_publisher_id(ctx: Any) -> str:
    """Return the canonical publisher identity, or an empty value when absent."""

    return str(getattr(ctx, "publisher_id", "") or "").strip()


def is_unattributed_publisher_id(value: object) -> bool:
    """Return whether a value is an explicit non-identity publisher sentinel."""

    return str(value or "").strip().casefold() in _UNATTRIBUTED_PUBLISHER_IDS


def require_admitted_report_identity(
    ctx: Any,
    *,
    legacy_source_values: tuple[str | None, ...] = (),
    legacy_publisher_values: tuple[str | None, ...] = (),
) -> tuple[str, str]:
    """Fail closed before a report workflow performs provider side effects."""

    # Publisher display metadata is not an identity alias. A canonical ID may
    # legitimately equal that text, so it must never participate in rejection.
    del legacy_publisher_values
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
    invalid = []
    if source_identity_id and source_identity_id in legacy_source_ids:
        invalid.append("source_identity_id")
    if publisher_id and is_unattributed_publisher_id(publisher_id):
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
