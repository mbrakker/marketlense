from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "Wordpress"
    / "scripts"
    / "verify-publish-entity-rest.py"
)
SPEC = importlib.util.spec_from_file_location("verify_publish_entity_rest", SCRIPT_PATH)
assert SPEC is not None
verify_publish_entity_rest = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = verify_publish_entity_rest
SPEC.loader.exec_module(verify_publish_entity_rest)


class FakeRestClient:
    def __init__(self) -> None:
        self.created: dict[tuple[str, int], dict[str, Any]] = {}
        self.next_id = 100

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        if path == "wp/v2/types":
            return {
                "ml_briefing": {
                    "rest_base": "ml_briefing",
                    "_links": {
                        "wp:items": [
                            {"href": "https://site.test/wp-json/wp/v2/ml_briefing"}
                        ]
                    },
                },
                "ml_signal": {
                    "rest_base": "ml_signal",
                    "_links": {
                        "wp:items": [
                            {"href": "https://site.test/wp-json/wp/v2/ml_signal"}
                        ]
                    },
                },
            }
        parts = path.split("/")
        assert parts[:2] == ["wp", "v2"]
        post_type = parts[2]
        post_id = int(parts[3])
        payload = self.created[(post_type, post_id)]
        return {
            "id": post_id,
            "type": post_type,
            "slug": payload["slug"],
            "title": {"raw": payload["title"]},
            "status": payload["status"],
            "link": f"https://site.test/{post_type}/{payload['slug']}/",
            "permalink_template": (
                "https://site.test/briefings/%pagename%/"
                if post_type == "ml_briefing"
                else "https://site.test/signals/%pagename%/"
            ),
            "meta": payload["meta"],
            "_params": params or {},
        }

    def post(self, path: str, payload: dict[str, Any] | None = None) -> Any:
        assert payload is not None
        post_type = path.split("/")[-1]
        post_id = self.next_id
        self.next_id += 1
        self.created[(post_type, post_id)] = dict(payload)
        return {"id": post_id}


def test_build_briefing_payload_uses_existing_publish_package(tmp_path: Path) -> None:
    artifact = tmp_path / "analysis.json"
    artifact.write_text(
        json.dumps(
            {
                "publish_package": {
                    "target_route": "wordpress:ml_briefing",
                    "title": "Boardroom briefing",
                    "slug": "boardroom-briefing",
                    "body_html": "<article>Generated briefing body</article>",
                    "excerpt": "Generated briefing excerpt",
                    "source_metadata": [{"report_id": "r1"}, {"report_id": "r2"}],
                    "evidence_reference_ids": ["e1", "e2", "e3"],
                }
            }
        ),
        encoding="utf-8",
    )

    payload = verify_publish_entity_rest.build_briefing_payload(
        artifact,
        slug_suffix="rest-check",
        status="draft",
    )

    assert payload.post_type == "ml_briefing"
    assert payload.slug == "boardroom-briefing-rest-check"
    assert payload.meta == {
        "ml_briefing_source_count": 2,
        "ml_briefing_evidence_count": 3,
    }


def test_build_signal_payload_uses_approved_signal_candidate(tmp_path: Path) -> None:
    artifact = tmp_path / "signals.json"
    artifact.write_text(
        json.dumps(
            {
                "candidates": [
                    {
                        "title": "Ignored",
                        "validation_status": "blocked",
                    },
                    {
                        "title": "Checkout trust",
                        "summary": "Checkout trust is becoming a conversion condition.",
                        "confidence": 0.84,
                        "validation_status": "approved",
                        "source_report_ids": ["r1", "r2"],
                        "evidence_ids": ["e1", "e2", "e3"],
                        "source_refs": [{"evidence_id": "e1"}],
                        "caveats": ["multi_report_coverage"],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    payload = verify_publish_entity_rest.build_signal_payload(
        artifact,
        slug_suffix="rest-check",
        status="draft",
    )

    assert payload.post_type == "ml_signal"
    assert payload.slug == "checkout-trust-rest-check"
    assert payload.meta["ml_signal_card_schema_version"] == "1.0"
    assert payload.meta["ml_signal_source_count"] == 2
    assert payload.meta["ml_signal_evidence_count"] == 3
    assert "Checkout trust is becoming" in payload.content_html


def test_verify_remote_entities_creates_and_reads_back_each_entity(
    tmp_path: Path,
) -> None:
    briefing_payload = verify_publish_entity_rest.EntityDraftPayload(
        schema_version="1.0",
        post_type="ml_briefing",
        source_artifact_path=str(tmp_path / "analysis.json"),
        title="Briefing title",
        slug="briefing-title-rest-check",
        content_html="<article>Briefing</article>",
        excerpt="Briefing",
        status="draft",
        meta={"ml_briefing_source_count": 2},
    )
    signal_payload = verify_publish_entity_rest.EntityDraftPayload(
        schema_version="1.0",
        post_type="ml_signal",
        source_artifact_path=str(tmp_path / "signals.json"),
        title="Signal title",
        slug="signal-title-rest-check",
        content_html="<article>Signal</article>",
        excerpt="Signal",
        status="draft",
        meta={"ml_signal_card_schema_version": "1.0"},
    )
    client = FakeRestClient()

    result = verify_publish_entity_rest.verify_remote_entities(
        client,
        briefing_payload=briefing_payload,
        signal_payload=signal_payload,
    )

    assert [item.post_type for item in result] == ["ml_briefing", "ml_signal"]
    assert all(item.route_confirmed for item in result)
    assert result[0].collection_route.endswith("/wp/v2/ml_briefing")
    assert result[1].collection_route.endswith("/wp/v2/ml_signal")


def test_verify_remote_entities_rejects_missing_remote_signal_type(
    tmp_path: Path,
) -> None:
    class MissingSignalTypeClient(FakeRestClient):
        def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
            if path == "wp/v2/types":
                payload = super().get(path, params)
                del payload["ml_signal"]
                return payload
            return super().get(path, params)

    payload = verify_publish_entity_rest.EntityDraftPayload(
        schema_version="1.0",
        post_type="ml_briefing",
        source_artifact_path=str(tmp_path / "analysis.json"),
        title="Briefing title",
        slug="briefing-title-rest-check",
        content_html="<article>Briefing</article>",
        excerpt="Briefing",
        status="draft",
    )

    with pytest.raises(RuntimeError, match="does not expose ml_signal"):
        verify_publish_entity_rest.verify_remote_entities(
            MissingSignalTypeClient(),
            briefing_payload=payload,
            signal_payload=payload,
        )
