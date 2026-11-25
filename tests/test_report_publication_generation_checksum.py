from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from src.contracts.publish import PublishSettings, WordPressAuthSettings
from src.contracts.report_analysis import (
    AnalysisGenerationCommitRequest,
    AnalysisGenerationReadRequest,
)
from src.contracts.report_store import ReportMetadataUpsertRequest
from src.orchestrators._publish_orchestrator import routing
from src.orchestrators._publish_orchestrator.routing import (
    report_publish_package_checksum,
)
from src.orchestrators.publish_orchestrator import run_publish
from src.services import report_analysis_store_service
from src.services.report_store_service import upsert_metadata
from src.utils.cache_utils import sha256_json
from src.utils.errors import AppError
from tests._test_report_analysis_generator._shared import _runtime
from tests.test_promotion_process_recovery import _promotion_worker
from tests.test_workflow_queue_registry import _ctx


def test_generation_binding_preserves_legacy_checksum_and_distinguishes_generations(
    tmp_path: Path,
) -> None:
    html = tmp_path / "report.html"
    readiness = tmp_path / "readiness.json"
    html.write_bytes(b"report")
    readiness.write_bytes(b"ready")
    legacy_payload = {
        "schema_version": "1.0",
        "entity_type": "report",
        "html_sha256": hashlib.sha256(b"report").hexdigest(),
        "readiness_sha256": hashlib.sha256(b"ready").hexdigest(),
    }
    legacy = hashlib.sha256(
        json.dumps(legacy_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    kwargs = {
        "html_path": str(html),
        "readiness_reference": str(readiness),
        "ctx": _ctx(),
    }
    assert report_publish_package_checksum(**kwargs) == legacy
    first = report_publish_package_checksum(
        **kwargs, package_version="2.0", analysis_generation="a" * 64
    )
    second = report_publish_package_checksum(
        **kwargs, package_version="2.0", analysis_generation="b" * 64
    )
    assert first != legacy
    assert first != second


def test_legacy_package_resolution_rejects_different_report_identity(tmp_path: Path):
    html = tmp_path / "report.html"
    readiness = tmp_path / "readiness.json"
    html.write_text("report", encoding="utf-8")
    readiness.write_text(
        json.dumps({"schema_version": "1.0", "report_id": "report-a"}), encoding="utf-8"
    )
    checksum = report_publish_package_checksum(
        html_path=str(html), readiness_reference=str(readiness), ctx=_ctx()
    )
    assert routing.resolve_report_publication_package(
        html_path=str(html),
        readiness_reference=str(readiness),
        checksum=checksum,
        expected_report_id="report-a",
        ctx=_ctx(),
    ) == str(readiness)
    with pytest.raises(AppError):
        routing.resolve_report_publication_package(
            html_path=str(html),
            readiness_reference=str(readiness),
            checksum=checksum,
            expected_report_id="report-b",
            ctx=_ctx(),
        )


def test_generation_binding_rejects_invalid_identity(tmp_path: Path) -> None:
    html = tmp_path / "report.html"
    readiness = tmp_path / "readiness.json"
    html.write_bytes(b"report")
    readiness.write_bytes(b"ready")
    with pytest.raises(AppError):
        report_publish_package_checksum(
            html_path=str(html),
            readiness_reference=str(readiness),
            package_version="2.0",
            analysis_generation="not-a-generation",
            ctx=_ctx(),
        )


def test_generation_package_version_cannot_omit_generation(tmp_path: Path) -> None:
    html = tmp_path / "report.html"
    readiness = tmp_path / "readiness.json"
    html.write_bytes(b"report")
    readiness.write_bytes(b"ready")
    with pytest.raises(AppError):
        report_publish_package_checksum(
            html_path=str(html),
            readiness_reference=str(readiness),
            package_version="2.0",
            ctx=_ctx(),
        )


def test_generation_package_rejects_mixed_generation_paths(tmp_path: Path) -> None:
    ctx = _ctx()
    first = report_analysis_store_service.commit_generation(
        AnalysisGenerationCommitRequest(
            schema_version="1.0",
            output_dir=str(tmp_path),
            report_id="report",
            report_slug="report",
            packs={"first": {"a": 1}, "second": {}},
        ),
        ctx,
    )
    second = report_analysis_store_service.commit_generation(
        AnalysisGenerationCommitRequest(
            schema_version="1.0",
            output_dir=str(tmp_path),
            report_id="report",
            report_slug="report",
            expected_generation=first.generation,
            packs={"first": {"a": 2}, "second": {}},
        ),
        ctx,
    )
    paths = dict(first.pack_paths)
    validate = getattr(routing, "validate_report_generation_binding", None)
    assert callable(validate), "publication must verify the pinned committed generation"
    validate(
        output_dir=str(tmp_path),
        report_id="report",
        report_slug="report",
        generation=first.generation,
        pack_paths=paths,
        ctx=ctx,
    )
    paths["first"] = second.pack_paths["first"]
    with pytest.raises(AppError):
        validate(
            output_dir=str(tmp_path),
            report_id="report",
            report_slug="report",
            generation=first.generation,
            pack_paths=paths,
            ctx=ctx,
        )


def test_publication_package_pins_generation_and_snapshots(tmp_path: Path) -> None:
    _promotion_worker(tmp_path, "never", include_evidence=True)
    runtime = _runtime(tmp_path)
    generation = report_analysis_store_service.read_generation(
        AnalysisGenerationReadRequest(
            schema_version="1.0",
            output_dir=runtime.settings.output_dir,
            report_id=runtime.file.file_id,
            report_slug=runtime.report_name,
        ),
        runtime.ctx,
    )
    html = tmp_path / "report.html"
    readiness = tmp_path / "readiness.json"
    html.write_text("report", encoding="utf-8")
    readiness_payload = json.dumps(
        {
            "status": "pass",
            "report_id": runtime.file.file_id,
            "final_html_hash": hashlib.sha256(b"report").hexdigest(),
            "artifact_hashes": {
                name: sha256_json(generation.packs[name])
                for name in ("artifacts", "validation")
            }
            | {"evidence:findings": sha256_json({"findings": []})},
        }
    )
    readiness.write_text(readiness_payload, encoding="utf-8")
    create = getattr(routing, "create_report_publication_package", None)
    assert callable(create), "render must create a versioned immutable package"
    package = create(
        html_path=str(html),
        readiness_reference=str(readiness),
        output_dir=runtime.settings.output_dir,
        report_id=runtime.file.file_id,
        report_slug=runtime.report_name,
        pack_paths=generation.pack_paths,
        ctx=runtime.ctx,
    )
    html.write_text("changed", encoding="utf-8")
    readiness.write_text("changed", encoding="utf-8")
    assert Path(package.html_path).read_text(encoding="utf-8") == "report"
    assert Path(package.readiness_path).read_text(encoding="utf-8") == readiness_payload
    assert package.generation == generation.generation
    resolve = getattr(routing, "resolve_report_publication_package", None)
    assert callable(resolve), "publication must verify the retained package"
    resolved = resolve(
        html_path=package.html_path,
        readiness_reference=package.manifest_path,
        checksum=package.checksum,
        expected_report_id=runtime.file.file_id,
        ctx=runtime.ctx,
    )
    assert resolved == package.readiness_path
    reports_db = tmp_path / "reports.sqlite"
    upsert_metadata(
        ReportMetadataUpsertRequest(
            schema_version="1.0",
            db_path=str(reports_db),
            file_id=runtime.file.file_id,
            title="Report",
            file_name="report.pdf",
            publisher="Publisher",
            categories=[],
            region="Global",
            time_period="2026",
            html_path=str(html),
        ),
        runtime.ctx,
    )
    settings = PublishSettings(
        schema_version="1.0",
        output_dir=str(tmp_path),
        state_db=str(tmp_path / "state.sqlite"),
        reports_db=str(reports_db),
        category_mapping_path=str(tmp_path / "categories.yaml"),
        wp=WordPressAuthSettings(
            schema_version="1.0",
            site_url="",
            username="",
            app_password=None,
            bearer_token=None,
            post_status="publish",
        ),
        run_budget_enabled=True,
        run_budget_max_wordpress_writes=0,
    )
    outcomes = run_publish(
        settings,
        html_paths=[package.html_path],
        ctx=runtime.ctx,
        report_generation_packages={
            package.html_path: (
                runtime.file.file_id,
                package.manifest_path,
                package.checksum,
            )
        },
    )
    assert len(outcomes) == 1
    assert outcomes[0].file_id == runtime.file.file_id
    assert outcomes[0].actual_write_count == 0
    with pytest.raises(AppError):
        resolve(
            html_path=package.html_path,
            readiness_reference=package.manifest_path,
            checksum=package.checksum,
            expected_report_id="another-report",
            ctx=runtime.ctx,
        )
    Path(package.readiness_path).write_text("tampered", encoding="utf-8")
    with pytest.raises(AppError):
        resolve(
            html_path=package.html_path,
            readiness_reference=package.manifest_path,
            checksum=package.checksum,
            ctx=runtime.ctx,
        )


def test_publication_package_rejects_readiness_from_another_generation(
    tmp_path: Path,
) -> None:
    _promotion_worker(tmp_path, "never")
    runtime = _runtime(tmp_path)
    generation = report_analysis_store_service.read_generation(
        AnalysisGenerationReadRequest(
            schema_version="1.0",
            output_dir=runtime.settings.output_dir,
            report_id=runtime.file.file_id,
            report_slug=runtime.report_name,
        ),
        runtime.ctx,
    )
    html = tmp_path / "report.html"
    readiness = tmp_path / "readiness.json"
    html.write_text("report", encoding="utf-8")
    readiness.write_text(
        json.dumps(
            {
                "status": "pass",
                "artifact_hashes": {
                    "artifacts": "wrong-artifacts",
                    "validation": "wrong-validation",
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(AppError):
        routing.create_report_publication_package(
            html_path=str(html),
            readiness_reference=str(readiness),
            output_dir=runtime.settings.output_dir,
            report_id=runtime.file.file_id,
            report_slug=runtime.report_name,
            pack_paths=generation.pack_paths,
            ctx=runtime.ctx,
        )


def test_new_publication_package_requires_generation_evidence(tmp_path: Path) -> None:
    _promotion_worker(tmp_path, "never")
    runtime = _runtime(tmp_path)
    generation = report_analysis_store_service.read_generation(
        AnalysisGenerationReadRequest(
            schema_version="1.0",
            output_dir=runtime.settings.output_dir,
            report_id=runtime.file.file_id,
            report_slug=runtime.report_name,
        ),
        runtime.ctx,
    )
    html = tmp_path / "report.html"
    html.write_text("report", encoding="utf-8")
    readiness = tmp_path / "readiness.json"
    readiness.write_text(
        json.dumps(
            {
                "report_id": runtime.file.file_id,
                "final_html_hash": hashlib.sha256(b"report").hexdigest(),
                "artifact_hashes": {
                    name: sha256_json(generation.packs[name])
                    for name in ("artifacts", "validation")
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(AppError) as exc:
        routing.create_report_publication_package(
            html_path=str(html),
            readiness_reference=str(readiness),
            output_dir=runtime.settings.output_dir,
            report_id=runtime.file.file_id,
            report_slug=runtime.report_name,
            pack_paths=generation.pack_paths,
            ctx=runtime.ctx,
        )
    assert exc.value.code == "report_publish_generation_missing"


@pytest.mark.parametrize("case", ["different", "missing", "extra", "matching"])
def test_publication_package_binds_readiness_to_generation_evidence(
    tmp_path: Path, case: str
) -> None:
    _promotion_worker(tmp_path, "never")
    runtime = _runtime(tmp_path)
    previous = report_analysis_store_service.read_generation(
        AnalysisGenerationReadRequest(
            schema_version="1.0",
            output_dir=runtime.settings.output_dir,
            report_id=runtime.file.file_id,
            report_slug=runtime.report_name,
        ),
        runtime.ctx,
    )
    generation = report_analysis_store_service.commit_generation(
        AnalysisGenerationCommitRequest(
            schema_version="1.0",
            output_dir=runtime.settings.output_dir,
            report_id=runtime.file.file_id,
            report_slug=runtime.report_name,
            expected_generation=previous.generation,
            packs={
                **previous.packs,
                "authoritative_evidence": {"findings": {"value": "correct"}},
            },
        ),
        runtime.ctx,
    )
    html = tmp_path / "report.html"
    html.write_text("report", encoding="utf-8")
    readiness = tmp_path / "readiness.json"
    evidence_hashes = {"evidence:findings": sha256_json({"value": "correct"})}
    if case == "different":
        evidence_hashes["evidence:findings"] = sha256_json({"value": "different"})
    elif case == "missing":
        evidence_hashes.clear()
    elif case == "extra":
        evidence_hashes["evidence:extra"] = sha256_json({})
    readiness.write_text(
        json.dumps(
            {
                "report_id": runtime.file.file_id,
                "final_html_hash": hashlib.sha256(b"report").hexdigest(),
                "artifact_hashes": {
                    "artifacts": sha256_json(generation.packs["artifacts"]),
                    "validation": sha256_json(generation.packs["validation"]),
                    **evidence_hashes,
                },
            }
        ),
        encoding="utf-8",
    )

    def create():
        return routing.create_report_publication_package(
            html_path=str(html),
            readiness_reference=str(readiness),
            output_dir=runtime.settings.output_dir,
            report_id=runtime.file.file_id,
            report_slug=runtime.report_name,
            pack_paths=generation.pack_paths,
            ctx=runtime.ctx,
        )

    if case == "matching":
        package = create()
        assert (
            routing.resolve_report_publication_package(
                html_path=package.html_path,
                readiness_reference=package.manifest_path,
                checksum=package.checksum,
                expected_report_id=runtime.file.file_id,
                ctx=runtime.ctx,
            )
            == package.readiness_path
        )
    else:
        with pytest.raises(AppError):
            create()
