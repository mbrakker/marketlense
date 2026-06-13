from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "tests" / "wordpress_runtime" / "report_view_model_harness.php"


def _run_contract(payload: dict[str, object]) -> dict[str, object]:
    completed = subprocess.run(
        ["php", str(HARNESS)],
        input=json.dumps({"mode": "meta_contract", **payload}),
        capture_output=True,
        check=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(completed.stdout)


def _card_meta(*, geography_scope: str = "global") -> dict[str, object]:
    return {
        "ml_card_schema_version": "1.0",
        "ml_card_title_scale": "long",
        "ml_card_tldr_compact": "Complete compact TLDR.",
        "ml_card_tldr_standard": "Complete standard TLDR.",
        "ml_card_key_insights": ["First insight.", "Second insight."],
        "ml_card_geography_scope": geography_scope,
        "ml_card_cover_fingerprint": {
            "geometry_family": "ascending_trajectory",
            "seed": 184221,
        },
        "ml_card_cover_small_id": 301,
        "ml_card_cover_medium_id": 302,
        "ml_card_cover_large_id": 303,
        "ml_region": "Global" if geography_scope == "global" else "Europe",
    }


def _run_view_model(
    *,
    meta: dict[str, object],
    age_seconds: int = 0,
) -> dict[str, object]:
    now = 1_781_308_800
    completed = subprocess.run(
        ["php", str(HARNESS)],
        input=json.dumps(
            {
                "mode": "full",
                "content": "<section id='section-summary'><p>Legacy summary.</p></section>",
                "meta": meta,
                "now": now,
                "timestamp": now - age_seconds,
                "attachment_urls": {
                    "301": "https://example.test/media/small.png",
                    "302": "https://example.test/media/medium.png",
                    "303": "https://example.test/media/large.png",
                },
            }
        ),
        capture_output=True,
        check=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(completed.stdout)


def test_report_card_meta_fields_register_explicit_rest_contracts() -> None:
    result = _run_contract({})
    registrations = result["registrations"]

    expected_keys = {
        "ml_card_schema_version",
        "ml_card_title_scale",
        "ml_card_tldr_compact",
        "ml_card_tldr_standard",
        "ml_card_key_insights",
        "ml_card_geography_scope",
        "ml_card_cover_fingerprint",
        "ml_card_cover_small_id",
        "ml_card_cover_medium_id",
        "ml_card_cover_large_id",
    }
    assert expected_keys <= set(registrations)
    assert registrations["ml_card_key_insights"]["type"] == "array"
    insights_schema = registrations["ml_card_key_insights"]["show_in_rest"]["schema"]
    assert insights_schema["minItems"] == 2
    assert insights_schema["maxItems"] == 2
    fingerprint_schema = registrations["ml_card_cover_fingerprint"]["show_in_rest"][
        "schema"
    ]
    assert fingerprint_schema["required"] == ["geometry_family", "seed"]
    for key in (
        "ml_card_cover_small_id",
        "ml_card_cover_medium_id",
        "ml_card_cover_large_id",
    ):
        assert registrations[key]["type"] == "integer"


def test_report_card_meta_sanitizers_accept_only_complete_values() -> None:
    valid = _run_contract(
        {
            "insights": [" First insight. ", "Second   insight."],
            "fingerprint": {
                "geometry_family": "ascending_trajectory",
                "seed": 184221,
                "ignored": "value",
            },
            "media_id": 303,
        }
    )["sanitized"]
    assert valid == {
        "insights": ["First insight.", "Second insight."],
        "fingerprint": {
            "geometry_family": "ascending_trajectory",
            "seed": 184221,
        },
        "media_id": 303,
    }

    invalid = _run_contract(
        {
            "insights": ["Only one insight."],
            "fingerprint": {
                "geometry_family": "unsupported_family",
                "seed": -1,
            },
            "media_id": 0,
        }
    )["sanitized"]
    assert invalid == {"insights": [], "fingerprint": [], "media_id": 0}


def test_report_card_view_model_uses_registered_card_meta() -> None:
    model = _run_view_model(meta=_card_meta(), age_seconds=3600)

    assert model["card_contract_valid"] is True
    assert model["card_contract_errors"] == []
    assert model["title_scale"] == "long"
    assert model["tldr_compact"] == "Complete compact TLDR."
    assert model["tldr_standard"] == "Complete standard TLDR."
    assert model["key_insights"] == ["First insight.", "Second insight."]
    assert model["geography_scope"] == "global"
    assert model["geography"] == "Global"
    assert model["geography_icon"] == "globe"
    assert model["is_new"] is True
    assert model["covers"] == {
        "small": "https://example.test/media/small.png",
        "medium": "https://example.test/media/medium.png",
        "large": "https://example.test/media/large.png",
    }


@pytest.mark.parametrize(
    ("age_seconds", "expected"),
    ((0, True), (604799, True), (604800, False), (-1, False)),
)
def test_report_card_new_badge_uses_exact_seven_day_boundary(
    age_seconds: int,
    expected: bool,
) -> None:
    model = _run_view_model(meta=_card_meta(), age_seconds=age_seconds)

    assert model["is_new"] is expected


@pytest.mark.parametrize(
    ("scope", "label", "icon"),
    (
        ("regional", "Europe", "locator"),
        ("country", "Europe", "locator"),
        ("unknown", "", ""),
    ),
)
def test_report_card_geography_scope_controls_label_and_icon(
    scope: str,
    label: str,
    icon: str,
) -> None:
    model = _run_view_model(meta=_card_meta(geography_scope=scope))

    assert model["geography"] == label
    assert model["geography_icon"] == icon


def test_report_card_view_model_exposes_invalid_contract_errors() -> None:
    meta = _card_meta()
    meta["ml_card_tldr_compact"] = ""
    meta["ml_card_cover_medium_id"] = 0

    model = _run_view_model(meta=meta)

    assert model["card_contract_valid"] is False
    assert "tldr_compact" in model["card_contract_errors"]
    assert "cover_medium" in model["card_contract_errors"]
