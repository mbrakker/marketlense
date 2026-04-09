from __future__ import annotations

from types import SimpleNamespace

from src.ui.app_pages import publisher_operations as pages


def test_publisher_operation_request_builders_trim_inputs() -> None:
    assert pages.build_publisher_discovery_request_payload(
        insights_url=" https://example.com/insights "
    ) == {"insights_url": "https://example.com/insights"}
    assert pages.build_report_download_request_payload(
        url=" https://example.com/report ",
        delivery_email=" ops@example.com ",
    ) == {
        "url": "https://example.com/report",
        "delivery_email": "ops@example.com",
    }
    assert pages.build_acquisition_audit_request_payload(
        publisher_limit=7,
        candidate_limit_per_publisher=3,
        delivery_email=" audit@example.com ",
    ) == {
        "publisher_limit": 7,
        "candidate_limit_per_publisher": 3,
        "delivery_email": "audit@example.com",
    }


def test_selected_run_payload_filters_by_run_type(monkeypatch) -> None:
    monkeypatch.setattr(
        pages,
        "poll_selected_run",
        lambda settings, max_bytes=64000: SimpleNamespace(
            record=SimpleNamespace(run_type="report_download")
        ),
    )

    assert pages._selected_run_payload(object(), run_type="publisher_discovery") is None
    selected = pages._selected_run_payload(object(), run_type="report_download")
    assert selected is not None
    assert selected.record.run_type == "report_download"
