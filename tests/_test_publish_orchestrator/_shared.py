# ruff: noqa: F401,F403,F405
from __future__ import annotations

from pathlib import Path as _SplitPath

__file__ = str(
    _SplitPath(__file__).resolve().parent.parent / "test_publish_orchestrator.py"
)

import hashlib
import json
import logging
import re
import sqlite3
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from src.contracts.publish_readiness import PublishReadinessArtifact
from src.contracts.report_store import ReportMetadataUpsertRequest
from src.contracts.state import (
    StatePublishCheckRequest,
    StatePublishRecordRequest,
    StateRecordRequest,
)
from src.contracts.validation_run_manifest import ValidationRunManifestCreateRequest
from src.orchestrators import publish_orchestrator as orch
from src.orchestrators import retry_orchestrator
from src.services.report_store_service import (
    create_validation_run_manifest,
    upsert_metadata,
)
from src.services.state_service import get_publish, record, record_publish
from src.utils.publication_projection import publication_projection_hash
from tests.support.fakes import FakeHttpResponse, RecordedHttpRequest


@pytest.fixture(autouse=True)
def _report_card_media_routes(wordpress_http) -> None:
    proof_meta_schema = {
        "schema": {
            "properties": {
                "meta": {
                    "properties": {
                        "ml_file_id": {"type": "string"},
                        "ml_content_sha256": {"type": "string"},
                        "ml_source_title": {"type": "string"},
                        "ml_source_url": {"type": "string"},
                        "ml_source_note": {"type": "string"},
                        "ml_source_publication_date": {"type": "string"},
                    }
                }
            }
        }
    }
    for post_type in ("ml_report", "ml_signal", "ml_briefing", "posts"):
        wordpress_http.add_json(
            "GET",
            f"https://example.com/wp-json/wp/v2/types/{post_type}",
            status_code=200,
            payload={"rest_base": post_type},
        )
        wordpress_http.add_json(
            "OPTIONS",
            f"https://example.com/wp-json/wp/v2/{post_type}",
            status_code=200,
            payload=proof_meta_schema,
        )

    def upload(call: RecordedHttpRequest) -> FakeHttpResponse:
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
        upload,
    )
    for media_id in (301, 302, 303):
        wordpress_http.add_json(
            "POST",
            f"https://example.com/wp-json/wp/v2/media/{media_id}",
            status_code=200,
            payload={"id": media_id},
        )


def _publish_entity_metadata_script(
    *,
    entity_type: str = "report",
    source_artifact_id: str = "file123",
    canonical_route_intent: str = "wordpress:ml_report",
    publish_eligible: bool = True,
) -> str:
    return (
        '<script type="application/json" '
        'data-market-lense-publish-entity="true">'
        + json.dumps(
            {
                "schema_version": "1.0",
                "entity_type": entity_type,
                "source_artifact_id": source_artifact_id,
                "canonical_route_intent": canonical_route_intent,
                "publish_eligible": publish_eligible,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "</script>"
    )


def _write_html(
    output_dir: str,
    name: str,
    body: str,
    *,
    entity_type: str = "report",
    canonical_route_intent: str = "wordpress:ml_report",
    source_artifact_id: str = "file123",
    include_entity_metadata: bool = True,
) -> Path:
    html_path = Path(output_dir) / name
    html_path.parent.mkdir(parents=True, exist_ok=True)
    marker = re.search(r"Drive fileId:\s*([A-Za-z0-9:_-]+)", body)
    effective_file_id = marker.group(1) if marker else source_artifact_id
    metadata = (
        _publish_entity_metadata_script(
            entity_type=entity_type,
            source_artifact_id=effective_file_id,
            canonical_route_intent=canonical_route_intent,
        )
        if include_entity_metadata
        else ""
    )
    html_text = (
        f"<html><head><title>Report</title>{metadata}</head><body>{body}</body></html>"
    )
    html_path.write_text(html_text, encoding="utf-8")
    if entity_type == "report":
        _write_report_card_manifest(html_path)
        _write_publish_readiness(
            html_path=html_path,
            html_text=html_text,
            file_id=effective_file_id,
        )
    return html_path


def _write_publish_readiness(*, html_path: Path, html_text: str, file_id: str) -> None:
    created_at = datetime.now(UTC)
    artifact = PublishReadinessArtifact(
        report_id=file_id,
        status="pass",
        artifact_hashes={},
        rule_results=[],
        final_html_hash=hashlib.sha256(html_text.encode("utf-8")).hexdigest(),
        publication_projection_hash=publication_projection_hash(html_text),
        configuration_hash=hashlib.sha256(
            b"publish-readiness:configuration:unavailable"
        ).hexdigest(),
        policy_hash=hashlib.sha256(b"publish-readiness:policy:unavailable").hexdigest(),
        producer_revision="workspace",
        created_at_utc=created_at.isoformat(),
        expires_at_utc=(created_at + timedelta(hours=1)).isoformat(),
        staleness_conditions=["final_html_hash_changed"],
        provenance={},
    )
    signature_payload = asdict(replace(artifact, artifact_hash=""))
    artifact = replace(
        artifact,
        artifact_hash=hashlib.sha256(
            json.dumps(
                signature_payload,
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest(),
    )
    readiness_path = (
        html_path.with_suffix("") / "report_analysis" / "publish_readiness.json"
    )
    readiness_path.parent.mkdir(parents=True, exist_ok=True)
    readiness_path.write_text(json.dumps(asdict(artifact)), encoding="utf-8")


def _write_report_card_manifest(html_path: Path) -> None:
    report_dir = html_path.with_suffix("")
    assets_dir = report_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    dimensions = {
        "small": (1600, 900),
        "medium": (1200, 1500),
        "large": (1200, 1600),
    }
    covers: dict[str, object] = {"schema_version": "1.0"}
    for size, (width, height) in dimensions.items():
        filename = f"report-card-{size}.png"
        (assets_dir / filename).write_bytes(f"image:{filename}".encode("utf-8"))
        covers[size] = {
            "schema_version": "1.0",
            "size": size,
            "output_path": f"assets/{filename}",
            "width": width,
            "height": height,
        }
    manifest = {
        "schema_version": "1.0",
        "title": "Report",
        "title_scale": "short",
        "publisher": "Publisher",
        "published_date": "2026-06-09",
        "geography_label": "Global",
        "geography_scope": "global",
        "covered_period": "Q2 2026",
        "tldr_compact": "Complete compact TLDR.",
        "tldr_standard": "Complete standard TLDR with grounded context.",
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
        "covers": covers,
    }
    (report_dir / "report-card-manifest.json").write_text(
        json.dumps(manifest, sort_keys=True),
        encoding="utf-8",
    )


def _record_processed(state_db: str, file_id: str, run_context) -> None:
    record(
        StateRecordRequest(
            schema_version="1.0",
            state_db=state_db,
            file_id=file_id,
            md5="md5",
        ),
        run_context,
    )


def _seed_report_metadata(
    reports_db: str,
    html_path: str,
    file_id: str,
    run_context,
    *,
    publisher: str | None = None,
) -> None:
    upsert_metadata(
        ReportMetadataUpsertRequest(
            schema_version="1.1",
            db_path=reports_db,
            file_id=file_id,
            title="Report",
            file_name="report.pdf",
            publisher=publisher,
            taxonomy=[],
            categories=[],
            region=None,
            time_period=None,
            source_url=None,
            html_path=html_path,
            md5="md5",
            page_count=None,
            contents_page_number=0,
            pdf_metadata={},
            analysis_mode="vector_store",
            vector_store_id=None,
            evidence_pack_paths={},
        ),
        run_context,
    )
    path = Path(html_path)
    _write_publish_readiness(
        html_path=path,
        html_text=path.read_text(encoding="utf-8"),
        file_id=file_id,
    )


def _json_events(caplog, logger_name: str) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for log_record in caplog.records:
        if log_record.name != logger_name:
            continue
        try:
            payload = json.loads(log_record.getMessage())
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            events.append(payload)
    return events


__all__ = [
    name
    for name in globals()
    if name
    not in {
        "__name__",
        "__annotations__",
        "__doc__",
        "__spec__",
        "__file__",
        "__package__",
        "__loader__",
        "__cached__",
        "__builtins__",
        "_SplitPath",
    }
]
