from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import yaml


_CONFIG_PATH = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "config"
    / "browser_download_identity.yaml"
)
_MAPPING_COVERAGE_SHA256 = (
    "98365293863231c535788a0ce3cb9575ba5f48f97549ae3f9e3ffbe23fd5576e"
)


def test_tracked_browser_identity_profile_is_a_value_free_complete_mapping() -> None:
    """The tracked profile supplies matching metadata, never a submit-ready identity."""
    payload = yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)

    fields = list(payload["fields"])
    overrides = list(payload.get("publisher_overrides") or [])
    override_fields = [
        field for override in overrides for field in override.get("field_values") or []
    ]

    assert payload.get("delivery_emails") == []
    assert all(field.get("value") is None for field in [*fields, *override_fields])
    assert len([field["key"] for field in fields]) == len(
        {field["key"] for field in fields}
    )
    assert len([override["host_pattern"] for override in overrides]) == len(
        {override["host_pattern"] for override in overrides}
    )
    for override in overrides:
        override_keys = [field["key"] for field in override.get("field_values") or []]
        assert len(override_keys) == len(set(override_keys))

    coverage = {
        "schema_version": payload.get("schema_version"),
        "fields": [
            {
                key: field.get(key)
                for key in (
                    "schema_version",
                    "key",
                    "label",
                    "aliases",
                    "option_aliases",
                )
            }
            for field in fields
        ],
        "publisher_overrides": [
            {
                "schema_version": override.get("schema_version"),
                "host_pattern": override.get("host_pattern"),
                "field_values": [
                    {
                        key: field.get(key)
                        for key in (
                            "schema_version",
                            "key",
                            "label",
                            "aliases",
                            "option_aliases",
                        )
                    }
                    for field in override.get("field_values") or []
                ],
            }
            for override in overrides
        ],
        "consent_policy": payload.get("consent_policy"),
    }
    serialized_coverage = json.dumps(
        coverage, sort_keys=True, separators=(",", ":")
    ).encode()
    assert sha256(serialized_coverage).hexdigest() == _MAPPING_COVERAGE_SHA256
