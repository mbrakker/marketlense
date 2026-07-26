"""Deterministic, value-free helpers for authenticated WordPress readback proof."""

from __future__ import annotations

import hashlib
import json


def canonical_wordpress_readback_value(value: object) -> str:
    """Normalize a REST value before equality checks or retained hashing."""

    if isinstance(value, dict):
        return json.dumps(
            {
                str(key): canonical_wordpress_readback_value(item)
                for key, item in value.items()
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    if isinstance(value, (list, tuple, set)):
        return json.dumps(
            sorted(canonical_wordpress_readback_value(item) for item in value),
            separators=(",", ":"),
        )
    return str(value or "")


def wordpress_readback_value_sha256(value: object) -> str:
    """Return the stable hash stored instead of a REST metadata value."""

    return hashlib.sha256(
        canonical_wordpress_readback_value(value).encode("utf-8")
    ).hexdigest()
