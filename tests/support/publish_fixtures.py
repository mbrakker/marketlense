from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tests.support.fakes import FakeHttpResponse, RecordedHttpRequest


def write_report_card_fixture(settings: Any, html_path: str | Path) -> None:
    source = Path(html_path)
    if not source.is_absolute():
        source = Path(settings.output_dir) / source.name
    report_dir = source.with_suffix("")
    assets_dir = report_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    for name in (
        "report-card-small.png",
        "report-card-medium.png",
        "report-card-large.png",
    ):
        (assets_dir / name).write_bytes(f"image:{name}".encode("utf-8"))
    (report_dir / "report-card-manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "title": "Global Economic Conditions Quarterly Update",
                "title_scale": "long",
                "publisher": "McKinsey & Company",
                "published_date": "2026-06-09",
                "source_title": "Global Economic Conditions Quarterly Update",
                "source_url": "https://publisher.example/reports/global-economic-conditions",
                "source_note": "Source: McKinsey & Company — Global Economic Conditions Quarterly Update",
                "source_metadata_hash": "source-metadata-hash",
                "source_identity_status": "resolved",
                "source_publication_date_status": "verified",
                "geography_label": "Global",
                "geography_scope": "global",
                "covered_period": "Q2 2026",
                "tldr_compact": "Complete compact TLDR.",
                "tldr_standard": (
                    "Complete standard TLDR with the required grounded context."
                ),
                "key_insights": ["First insight.", "Second insight."],
                "fingerprint": {
                    "schema_version": "1.0",
                    "geometry_family": "ascending_trajectory",
                    "evidence_shape": "trend",
                    "direction": "rising",
                    "geography_scope": "global",
                    "evidence_density": "balanced",
                    "domain_layer": "grid",
                    "seed": 184221,
                    "selection_reason": "A rising trend dominates the report.",
                },
                "covers": {
                    "schema_version": "1.0",
                    "small": {
                        "schema_version": "1.0",
                        "size": "small",
                        "output_path": "assets/report-card-small.png",
                        "width": 1600,
                        "height": 900,
                    },
                    "medium": {
                        "schema_version": "1.0",
                        "size": "medium",
                        "output_path": "assets/report-card-medium.png",
                        "width": 1200,
                        "height": 1500,
                    },
                    "large": {
                        "schema_version": "1.0",
                        "size": "large",
                        "output_path": "assets/report-card-large.png",
                        "width": 1200,
                        "height": 1600,
                    },
                },
            }
        ),
        encoding="utf-8",
    )


def add_card_media_responses(wordpress_http: Any) -> None:
    def _upload(call: RecordedHttpRequest) -> FakeHttpResponse:
        filename = call.files["file"][0]
        media_id = {
            "report-card-small.png": 301,
            "report-card-medium.png": 302,
            "report-card-large.png": 303,
        }[filename]
        return FakeHttpResponse.from_payload(
            status_code=201,
            payload={
                "id": media_id,
                "source_url": f"https://example.com/uploads/{filename}",
            },
        )

    wordpress_http.add(
        "POST",
        "https://example.com/wp-json/wp/v2/media",
        _upload,
    )
    for media_id in (301, 302, 303):
        wordpress_http.add_json(
            "POST",
            f"https://example.com/wp-json/wp/v2/media/{media_id}",
            status_code=200,
            payload={"id": media_id},
        )
