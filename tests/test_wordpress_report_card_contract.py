from __future__ import annotations

import json
import subprocess
from pathlib import Path


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
