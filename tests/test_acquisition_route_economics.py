from __future__ import annotations

from src.contracts.report_store import (
    AcquisitionAttemptResourceRecordRequest,
    AcquisitionAttemptResourceSummary,
    AcquisitionRouteEconomicsRequest,
)
from src.contracts.run_context import RunContext
from src.services.report_store_service import (
    read_acquisition_route_economics,
    record_acquisition_attempt_resource,
)


def _ctx() -> RunContext:
    return RunContext(
        schema_version="1.0", run_id="route-economics", task_id="test", span_id="span"
    )


def _record(
    tmp_path,
    *,
    attempt_id: str,
    route_family: str,
    outcome: str,
    cost: float,
    incomplete: tuple[str, ...] = (),
) -> None:
    record_acquisition_attempt_resource(
        AcquisitionAttemptResourceRecordRequest(
            schema_version="1.0",
            db_path=str(tmp_path / "reports.sqlite"),
            summary=AcquisitionAttemptResourceSummary(
                schema_version="1.0",
                attempt_id=attempt_id,
                publisher_id="publisher-a",
                source_identity_id="source-a",
                source_identity_status="resolved",
                normalized_url="https://example.com/report.pdf",
                route_family=route_family,
                route_policy_version="v1",
                source_policy_compatibility_hash="policy-a",
                started_at_utc="2026-07-19T10:00:00+00:00",
                completed_at_utc="2026-07-19T10:00:01+00:00",
                elapsed_ms=1000,
                terminal_outcome=outcome,
                estimated_cost_usd=cost,
                incomplete_fields=incomplete,
            ),
        ),
        _ctx(),
    )


def test_route_economics_proposes_only_material_compatible_improvement(
    tmp_path,
) -> None:
    for index in range(3):
        _record(
            tmp_path,
            attempt_id=f"direct-{index}",
            route_family="direct_http",
            outcome="failed",
            cost=2.0,
        )
        _record(
            tmp_path,
            attempt_id=f"browser-{index}",
            route_family="browser_pdf_click",
            outcome="success",
            cost=1.0,
        )

    response = read_acquisition_route_economics(
        AcquisitionRouteEconomicsRequest(
            schema_version="1.0", db_path=str(tmp_path / "reports.sqlite")
        ),
        _ctx(),
    )

    assert [row.route_family for row in response.cohorts] == [
        "browser_pdf_click",
        "direct_http",
    ]
    assert response.recommendations[0].disposition == "proposal"
    assert response.recommendations[0].baseline_route_family == "direct_http"
    assert response.recommendations[0].candidate_route_family == "browser_pdf_click"
    assert "direct-first globally" in response.recommendations[0].proposal


def test_route_economics_abstains_for_incomplete_or_insufficient_evidence(
    tmp_path,
) -> None:
    _record(
        tmp_path,
        attempt_id="direct-incomplete",
        route_family="direct_http",
        outcome="success",
        cost=0.0,
        incomplete=("estimated_cost_usd",),
    )
    _record(
        tmp_path,
        attempt_id="browser-one",
        route_family="browser_pdf_click",
        outcome="success",
        cost=1.0,
    )

    response = read_acquisition_route_economics(
        AcquisitionRouteEconomicsRequest(
            schema_version="1.0", db_path=str(tmp_path / "reports.sqlite")
        ),
        _ctx(),
    )

    assert response.recommendations[0].disposition == "no_recommendation"
    assert response.recommendations[0].reasons == ("insufficient_direct_sample",)


def test_route_economics_empty_report_is_read_only(tmp_path) -> None:
    path = tmp_path / "missing.sqlite"

    response = read_acquisition_route_economics(
        AcquisitionRouteEconomicsRequest(schema_version="1.0", db_path=str(path)),
        _ctx(),
    )

    assert response.cohorts == []
    assert response.recommendations == []
    assert not path.exists()
