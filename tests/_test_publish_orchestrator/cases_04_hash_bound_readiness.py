# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403


@pytest.mark.parametrize(
    ("readback_status", "expected_status", "expected_readback_verified"),
    [(200, "published", True), (404, "error", False)],
)
def test_readiness_bound_publish_requires_authenticated_readback(
    publish_settings_factory,
    run_context,
    wordpress_http,
    readback_status: int,
    expected_status: str,
    expected_readback_verified: bool,
) -> None:
    from src.contracts.validation import ValidationReport
    from src.generators.publish_readiness_generator import (
        evaluate_publish_readiness,
        publish_readiness_payload,
    )

    settings = publish_settings_factory(validation_policy="block")
    html_path = Path(settings.output_dir) / "report.html"
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html = (
        "<!doctype html><!--\n"
        "marketbearing-build:\n"
        "  git_sha: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n"
        "  generation_run_id: generation-run-1\n"
        "  validation_run_id: validation-run-1\n"
        "  source_id: source:file123\n"
        "  source_md5: bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\n"
        "  artifact_hash: "
        "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc\n"
        "  generation_profile: safe_default\n"
        "  generated_at_utc: 2026-08-26T12:00:00+00:00\n"
        "--><html><head><title>Report 2026 | MarketLense</title>"
        '<link rel="canonical" href="https://marketlense.example/reports/report"></head>'
        "<body><h1>Report 2026</h1><p>Revenue grew in the measured market.</p>"
        '<section id="source"><a href="https://publisher.example/reports/report">'
        "Open original source</a></section></body></html>"
    )
    html_path.write_text(html, encoding="utf-8")
    _write_report_card_manifest(html_path)
    _seed_report_metadata(settings.reports_db, str(html_path), "file123", run_context)
    report_analysis_dir = Path(settings.output_dir) / "report" / "report_analysis"
    report_analysis_dir.mkdir(parents=True, exist_ok=True)
    readiness = evaluate_publish_readiness(
        report_id="file123",
        artifacts={"categories": ["markets"]},
        evidence_packs={},
        validation_report=ValidationReport(schema_version="1.1", status="pass"),
        final_html=html,
        final_html_path=str(html_path),
        report_card_manifest_path=str(html_path.parent / "report-card-manifest.json"),
        category_ids=["markets"],
        provenance={
            "publisher_landing_page_url": "https://publisher.example/reports/report",
            "original_report_url": "",
            "marketlense_article_url": "https://marketlense.example/reports/report",
        },
    )
    assert readiness.status == "pass"
    readiness_path = report_analysis_dir / "publish_readiness.json"
    readiness_path.write_text(
        json.dumps(publish_readiness_payload(readiness)), encoding="utf-8"
    )
    (report_analysis_dir / "validation_regen_attempt_1.json").write_text(
        json.dumps(
            {
                "schema_version": "1.1",
                "status": "fail",
                "severity": "error",
                "issues": [
                    {
                        "schema_version": "1.0",
                        "message": "stale attempt failure",
                        "severity": "error",
                        "affected_section": "summary",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    _record_processed(settings.state_db, "file123", run_context)
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
        payload={"id": 88, "link": "https://example.com/post/88", "status": "publish"},
    )

    def _readback(_call: RecordedHttpRequest) -> FakeHttpResponse:
        if readback_status == 404:
            return FakeHttpResponse.from_payload(
                status_code=404, payload={"code": "rest_post_invalid_id"}
            )
        post = wordpress_http.calls_for(
            "POST", "https://example.com/wp-json/wp/v2/ml_report"
        )[0].json_data
        return FakeHttpResponse.from_payload(
            status_code=200,
            payload={
                "id": 88,
                "type": "ml_report",
                "status": post["status"],
                "link": "https://example.com/post/88",
                "featured_media": post.get("featured_media", 0),
                "categories": post.get("categories", []),
                "tags": post.get("tags", []),
                "content": {"raw": post["content"], "rendered": post["content"]},
                "meta": post["meta"],
            },
        )

    wordpress_http.add(
        "GET", "https://example.com/wp-json/wp/v2/ml_report/88", _readback
    )

    results = orch.run_publish(
        settings,
        limit=1,
        report_readiness_references={str(html_path): str(readiness_path)},
    )

    assert len(results) == 1
    assert results[0].status == expected_status
    assert results[0].validation_status == "pass"
    assert results[0].validation_issues == []
    assert results[0].authenticated_readback_verified is expected_readback_verified
    assert (
        len(
            wordpress_http.calls_for(
                "GET", "https://example.com/wp-json/wp/v2/ml_report/88"
            )
        )
        == 1
    )
    assert (
        len(
            wordpress_http.calls_for(
                "POST", "https://example.com/wp-json/wp/v2/ml_report"
            )
        )
        == 1
    )


__all__ = [
    "test_readiness_bound_publish_requires_authenticated_readback",
]
