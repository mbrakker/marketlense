# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403


def test_publish_cohort_manifest_limits_selection_to_cohort_members(
    publish_settings_factory, run_context, wordpress_http, tmp_path, caplog
) -> None:
    settings = publish_settings_factory(validation_policy="warn")
    _write_html(settings.output_dir, "other.html", "Drive fileId: other-file")
    target_path = _write_html(
        settings.output_dir, "target.html", "Drive fileId: target-file"
    )
    _record_processed(settings.state_db, "other-file", run_context)
    _record_processed(settings.state_db, "target-file", run_context)
    cohort_manifest = tmp_path / "cohort.json"
    cohort_manifest.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "cohort_id": "cohort-target-only",
                "validation_run_id": "validation:cohort-target-only",
                "configuration_hash": "configuration-hash",
                "policy_hash": "policy-hash",
                "members": [
                    {
                        "schema_version": "1.0",
                        "file_id": "target-file",
                        "md5_checksum": "target-md5",
                        "html_path": str(target_path),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    create_validation_run_manifest(
        ValidationRunManifestCreateRequest(
            schema_version="1.0",
            db_path=settings.reports_db,
            validation_run_id="validation:cohort-target-only",
            cohort_id="cohort-target-only",
            workflow_run_id=run_context.run_id,
            configuration_hash="configuration-hash",
            policy_hash="policy-hash",
            producer_build_identity="workspace",
            created_at_utc="2026-07-26T12:00:00Z",
        ),
        run_context,
    )
    wordpress_http.add_json(
        "GET",
        "https://example.com/wp-json/wp/v2/ml_report",
        status_code=200,
        payload=[],
    )
    wordpress_http.add_json(
        "POST",
        "https://example.com/wp-json/wp/v2/ml_report",
        status_code=201,
        payload={"id": 10, "link": "https://example.com/post/10", "status": "publish"},
    )

    def readback(_call: RecordedHttpRequest) -> FakeHttpResponse:
        payload = wordpress_http.calls_for(
            "POST", "https://example.com/wp-json/wp/v2/ml_report"
        )[0].json_data
        return FakeHttpResponse.from_payload(
            status_code=200,
            payload={
                "id": 10,
                "type": "ml_report",
                "status": payload["status"],
                "link": "https://example.com/post/10",
                "featured_media": payload.get("featured_media", 0),
                "categories": payload.get("categories", []),
                "tags": payload.get("tags", []),
                "content": {"raw": payload["content"], "rendered": payload["content"]},
                "meta": payload["meta"],
            },
        )

    wordpress_http.add(
        "GET", "https://example.com/wp-json/wp/v2/ml_report/10", readback
    )
    with caplog.at_level(logging.INFO, logger=orch.logger.name):
        outcomes = orch.run_publish(
            settings, ctx=run_context, cohort_manifest=str(cohort_manifest)
        )
    assert [(outcome.file_id, outcome.status) for outcome in outcomes] == [
        ("target-file", "published")
    ]
    assert (
        len(
            wordpress_http.calls_for(
                "POST", "https://example.com/wp-json/wp/v2/ml_report"
            )
        )
        == 1
    )
    assert (
        len(
            wordpress_http.calls_for(
                "GET", "https://example.com/wp-json/wp/v2/ml_report"
            )
        )
        == 1
    )
    assert (
        len(
            wordpress_http.calls_for(
                "GET", "https://example.com/wp-json/wp/v2/ml_report/10"
            )
        )
        == 1
    )
    assert outcomes[0].authenticated_readback_verified is True
    events = _json_events(caplog, orch.logger.name)
    assert not any(
        event.get("event") == "publish_auto_discovery_ordered" for event in events
    )
    cohort_event = next(
        event
        for event in events
        if event.get("event") == "publish_cohort_selection_applied"
    )
    assert cohort_event["fields"] == {
        "cohort_member_count": 1,
        "candidates_before_filter": 1,
        "selected_candidates": 1,
        "excluded_candidates": 0,
    }
