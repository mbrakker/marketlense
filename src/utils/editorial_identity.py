"""Deterministic identifiers for retained public editorial entities."""

from __future__ import annotations

from collections.abc import Mapping


def insight_entity_id(insight: Mapping[str, object]) -> str:
    """Return an insight's stable entity ID, never its linked evidence ID."""

    return str(insight.get("id") or insight.get("insight_id") or "").strip()


def insight_entity_id_from_public_item_id(public_item_id: str) -> str:
    """Extract the entity component from an atomic insight public-item ID."""

    kind, separator, remainder = str(public_item_id or "").partition(":")
    if kind != "insight" or not separator:
        return ""
    entity_id, separator, _ = remainder.partition(":")
    return entity_id.strip() if separator else ""


def failed_insight_id(entity_id: str, affected_section: str) -> str:
    """Resolve the failed atomic insight, including paired duplicate fields."""

    value = str(entity_id or "").strip()
    if value.startswith("insight:"):
        return value.split(":", 2)[1].split(".", 1)[0].strip()
    affected = str(affected_section or "").strip()
    if affected.casefold().startswith("insights:"):
        return affected.split(":", 1)[1].split("~", 1)[0].split(".", 1)[0].strip()
    return ""
