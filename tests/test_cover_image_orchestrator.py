from __future__ import annotations

from pathlib import Path

import pytest

from src.contracts.cover_images import (
    CoverImageOrchestratorRequest,
    CoverImageRenderResponse,
)
from src.contracts.report_store import ReportMetadataUpsertRequest
from src.contracts.run_context import RunContext
from src.orchestrators.cover_image_orchestrator import run_cover_image_generation
from src.services import cover_image_service
from src.services.report_store_service import upsert_metadata
from src.utils.errors import AppError


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


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
