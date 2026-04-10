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


def test_build_publisher_choice_options_filters_empty_urls_and_sorts() -> None:
    options = pages.build_publisher_choice_options(
        [
            SimpleNamespace(name="Zulu", insights_url=" https://zulu.example/reports "),
            SimpleNamespace(name="Alpha", insights_url="https://alpha.example/insights"),
            SimpleNamespace(name="Blank", insights_url=" "),
        ]
    )

    assert options == [
        {
            "label": "Alpha (alpha.example)",
            "name": "Alpha",
            "url": "https://alpha.example/insights",
            "host": "alpha.example",
        },
        {
            "label": "Zulu (zulu.example)",
            "name": "Zulu",
            "url": "https://zulu.example/reports",
            "host": "zulu.example",
        },
    ]


def test_build_saved_delivery_email_options_dedupes_from_fields_and_overrides() -> None:
    browser_settings = SimpleNamespace(
        identity_profile=SimpleNamespace(
            delivery_emails=["ops@example.com", "OPS@example.com"],
            fields=[
                SimpleNamespace(value="ops@example.com"),
                SimpleNamespace(value="analyst@example.com"),
                SimpleNamespace(value="not-an-email"),
            ],
            publisher_overrides=[
                SimpleNamespace(
                    delivery_emails=["publisher@example.com"],
                    field_values=[SimpleNamespace(value="publisher@example.com")],
                )
            ],
        )
    )

    assert pages.build_saved_delivery_email_options(browser_settings) == [
        "ops@example.com",
        "analyst@example.com",
        "publisher@example.com",
    ]


def test_delivery_email_and_path_resolution_helpers() -> None:
    assert (
        pages.resolve_delivery_email_value(
            mode="Use saved email",
            saved_email=" ops@example.com ",
            custom_email="custom@example.com",
        )
        == "ops@example.com"
    )
    assert (
        pages.resolve_delivery_email_value(
            mode="Custom email",
            saved_email="ops@example.com",
            custom_email=" custom@example.com ",
        )
        == "custom@example.com"
    )
    assert (
        pages.resolve_delivery_email_value(
            mode="No email",
            saved_email="ops@example.com",
            custom_email="custom@example.com",
        )
        == ""
    )
    assert (
        pages.resolve_path_choice(
            mode="Configured path",
            configured_path=" C:/configured.json ",
            custom_path="C:/custom.json",
        )
        == "C:/configured.json"
    )
    assert (
        pages.resolve_path_choice(
            mode="Custom path",
            configured_path="C:/configured.json",
            custom_path=" C:/custom.json ",
        )
        == "C:/custom.json"
    )


def test_resolve_audit_limits_uses_presets_and_custom_values() -> None:
    assert pages.resolve_audit_limits(
        preset="Quick",
        custom_publisher_limit=99,
        custom_candidate_limit=88,
    ) == (3, 3)
    assert pages.resolve_audit_limits(
        preset="Standard",
        custom_publisher_limit=99,
        custom_candidate_limit=88,
    ) == (5, 10)
    assert pages.resolve_audit_limits(
        preset="Custom",
        custom_publisher_limit=7,
        custom_candidate_limit=4,
    ) == (7, 4)


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
