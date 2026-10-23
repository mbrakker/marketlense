from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.contracts.cover_images import (
    CoverImageOrchestratorRequest,
    CoverImageRenderResponse,
)
from src.contracts.report_analysis import AnalysisStorePackRequest
from src.contracts.report_store import ReportMetadataUpsertRequest
from src.contracts.run_context import RunContext
from src.generators.report_card_projection import stable_cover_seed
from src.orchestrators.cover_image_orchestrator import (
    _load_cover_fingerprint,
    run_cover_image_generation,
)
from src.services import cover_image_service
from src.services.report_analysis_store_service import store_pack
from src.services.report_store_service import upsert_metadata
from src.utils.cache_utils import sha256_json
from src.utils.errors import AppError


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def _artifact_payload(*, schema_version: str = "3.0") -> dict:
    return {
        "schema_version": schema_version,
        "toc_topics": [],
        "editorial_plan": {
            "report_thesis": "The retained evidence supports the report thesis.",
            "themes": [
                {"theme": "Trend", "priority": 1, "evidence_ids": ["f1"]},
                {"theme": "Implication", "priority": 2, "evidence_ids": ["f2"]},
            ],
        },
        "summary": {
            "tldr": "Complete standard TLDR.",
            "card_tldr_compact": "Complete compact TLDR.",
            "executive_summary": "Summary",
            "claim_evidence_map": [],
        },
        "cover_semantics": {
            "evidence_shape": "comparison",
            "direction": "diverging",
            "geography_scope": "global",
            "evidence_density": "balanced",
            "domain_layer": "grid",
            "selection_reason": "Regional outlooks diverge across the evidence.",
        },
        "insights_candidates": [],
        "insights_final": [],
        "quotes_final": [],
        "expert_comment": "",
        "linkedin_post": "",
    }


def test_cover_image_orchestrator_loads_grounded_semantics(
    tmp_path: Path, external_boundary_mocks_only
) -> None:
    reports_db = tmp_path / "reports.sqlite"
    output_dir = tmp_path / "out"
    upsert_metadata(
        ReportMetadataUpsertRequest(
            schema_version="1.0",
            db_path=str(reports_db),
            file_id="file-1",
            title="Global Economic Conditions Quarterly Update",
            file_name="report.pdf",
            publisher="Market Lense Research",
            categories=["macroeconomics"],
            region="Global",
            time_period="Q2 2026",
            html_path=str(output_dir / "report.html"),
        ),
        _ctx(),
    )
    artifact_path = output_dir / "report" / "report_analysis" / "artifacts.json"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(
        """{
          "schema_version": "3.0",
          "cover_semantics": {
            "evidence_shape": "comparison",
            "direction": "diverging",
            "geography_scope": "global",
            "evidence_density": "balanced",
            "domain_layer": "grid",
            "selection_reason": "Regional outlooks diverge across the evidence."
          }
        }""",
        encoding="utf-8",
    )
    render_requests = []

    def _render(request, ctx):
        del ctx
        render_requests.append(request)
        return CoverImageRenderResponse(
            schema_version="2.0",
            output_path=request.output_path,
            width=request.layout.width,
            height=request.layout.height,
            title_font_size=request.layout.title_font_max,
        )

    external_boundary_mocks_only.setattr(
        cover_image_service, "render_cover_image", _render
    )

    outcomes = run_cover_image_generation(
        CoverImageOrchestratorRequest(
            schema_version="2.0",
            reports_db=str(reports_db),
            output_dir=str(output_dir),
            style_config_path="",
            file_id="file-1",
        ),
        ctx=_ctx(),
    )

    assert len(outcomes) == 1
    assert outcomes[0].status == "generated"
    assert outcomes[0].assets is not None
    assert [request.fingerprint.geometry_family for request in render_requests] == [
        "divergence_fan",
        "divergence_fan",
        "divergence_fan",
    ]
    assert len({request.fingerprint.seed for request in render_requests}) == 1


def test_cover_image_orchestrator_missing_file_is_typed_error(
    tmp_path: Path,
    assert_app_error,
) -> None:
    with pytest.raises(AppError) as exc_info:
        run_cover_image_generation(
            CoverImageOrchestratorRequest(
                schema_version="1.0",
                reports_db=str(tmp_path / "reports.sqlite"),
                output_dir=str(tmp_path / "out"),
                style_config_path=str(tmp_path / "cover-styles.yaml"),
                file_id="missing-file",
            )
        )

    assert_app_error(
        exc_info.value,
        code="cover_report_not_found",
        retryable=False,
    )


def test_cover_fingerprint_reads_exact_persisted_compacted_artifact(tmp_path: Path):
    output_dir = tmp_path / ("deep-output-root-" + "x" * 20)
    report_slug = "long-report-" + "y" * 105
    pack_name = "artifacts_regen_candidate_" + "z" * 220
    payload = _artifact_payload()
    stored = store_pack(
        AnalysisStorePackRequest(
            schema_version="1.0",
            output_dir=str(output_dir),
            report_id="file-compact",
            pack_name=pack_name,
            payload=payload,
            report_slug=report_slug,
        ),
        _ctx(),
    )
    assert Path(stored.output_path).exists()
    assert Path(stored.output_path).parent.parent.name != report_slug
    assert Path(stored.output_path).stem != pack_name

    metadata = type(
        "Metadata",
        (),
        {
            "file_id": "file-compact",
            "title": "Long report",
            "publisher": "Publisher",
            "region": "Global",
            "html_path": str(output_dir / f"{report_slug}.html"),
            "file_name": "report.pdf",
            "categories": [],
            "time_period": "2026",
            "evidence_pack_paths": {"artifacts": stored.output_path},
        },
    )()

    fingerprint = _load_cover_fingerprint(metadata, str(output_dir), _ctx())

    assert fingerprint.geometry_family == "divergence_fan"
    assert fingerprint.seed == stable_cover_seed("file-compact", sha256_json(payload))

    relative_metadata = type(
        "Metadata",
        (),
        {
            "file_id": "file-compact",
            "title": "Long report",
            "publisher": "Publisher",
            "region": "Global",
            "html_path": str(output_dir / f"{report_slug}.html"),
            "file_name": "report.pdf",
            "categories": [],
            "time_period": "2026",
            "evidence_pack_paths": {
                "artifacts": str(Path(stored.output_path).relative_to(output_dir))
            },
        },
    )()
    relative_fingerprint = _load_cover_fingerprint(
        relative_metadata, str(output_dir), _ctx()
    )
    assert relative_fingerprint.seed == fingerprint.seed


@pytest.mark.parametrize(
    ("content", "expected_code"),
    [
        ("{", "cover_artifacts_invalid"),
        (
            json.dumps(_artifact_payload(schema_version="2.0")),
            "cover_artifacts_invalid",
        ),
        (
            json.dumps({"schema_version": "3.0"}),
            "cover_fingerprint_invalid",
        ),
    ],
)
def test_cover_fingerprint_preserves_persisted_artifact_validation_errors(
    tmp_path: Path, content: str, expected_code: str
):
    output_dir = tmp_path / "out"
    artifact_path = output_dir / "report" / "report_analysis" / "artifacts.json"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_text(content, encoding="utf-8")
    metadata = type(
        "Metadata",
        (),
        {
            "file_id": "file-validation",
            "title": "Report",
            "publisher": "Publisher",
            "region": "Global",
            "html_path": str(output_dir / "report.html"),
            "file_name": "report.pdf",
            "categories": [],
            "time_period": "2026",
            "evidence_pack_paths": {"artifacts": str(artifact_path)},
        },
    )()

    with pytest.raises(AppError) as exc_info:
        _load_cover_fingerprint(metadata, str(output_dir), _ctx())

    assert exc_info.value.code == expected_code
    assert exc_info.value.retryable is False


def test_cover_fingerprint_rejects_stale_persisted_reference_without_fallback(
    tmp_path: Path,
):
    output_dir = tmp_path / "out"
    legacy = output_dir / "report" / "report_analysis" / "artifacts.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_text(json.dumps(_artifact_payload()), encoding="utf-8")
    metadata = type(
        "Metadata",
        (),
        {
            "file_id": "file-stale",
            "title": "Report",
            "publisher": "Publisher",
            "region": "Global",
            "html_path": str(output_dir / "report.html"),
            "file_name": "report.pdf",
            "categories": [],
            "time_period": "2026",
            "evidence_pack_paths": {
                "artifacts": str(output_dir / "other" / "artifacts.json")
            },
        },
    )()

    with pytest.raises(AppError) as exc_info:
        _load_cover_fingerprint(metadata, str(output_dir), _ctx())

    assert exc_info.value.code == "cover_artifacts_missing"
    assert exc_info.value.retryable is False


def test_cover_fingerprint_rejects_persisted_path_outside_output_root(tmp_path: Path):
    outside = tmp_path / "outside-artifacts.json"
    outside.write_text(json.dumps(_artifact_payload()), encoding="utf-8")
    metadata = type(
        "Metadata",
        (),
        {
            "file_id": "file-escape",
            "title": "Report",
            "publisher": "Publisher",
            "region": "Global",
            "html_path": str(tmp_path / "out" / "report.html"),
            "file_name": "report.pdf",
            "categories": [],
            "time_period": "2026",
            "evidence_pack_paths": {"artifacts": str(outside)},
        },
    )()

    with pytest.raises(AppError) as exc_info:
        _load_cover_fingerprint(metadata, str(tmp_path / "out"), _ctx())

    assert exc_info.value.code == "cover_artifacts_invalid"
    assert exc_info.value.retryable is False
