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
