from __future__ import annotations

from .builders import *  # noqa: F401,F403


def test_discover_publisher_inventory_direct_pdf_source_short_circuits_browser(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    def _unexpected_runtime(_name: str):
        raise AssertionError(
            "browser runtime should not be loaded for direct PDF sources"
        )

    external_boundary_mocks_only.setattr(service, "import_module", _unexpected_runtime)

    response = service.discover_publisher_inventory(
        PublisherInventoryServiceRequest(
            schema_version="1.0",
            insights_url="https://example.com/reports/state-of-retail-2026.pdf",
            settings=_settings(tmp_path),
        ),
        run_context,
    )

    assert response.route_kind == "http_parse"
    assert len(response.pages) == 1
    assert [candidate.url for candidate in response.candidates] == [
        "https://example.com/reports/state-of-retail-2026.pdf"
    ]
    assert (
        response.candidates[0].pdf_url
        == "https://example.com/reports/state-of-retail-2026.pdf"
    )
    assert response.candidates[0].provenance == "direct_pdf_source"
    assert response.candidates[0].confidence == 1.0


def test_discover_publisher_inventory_http_hint_empty_is_typed_error(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
    assert_app_error,
) -> None:
    external_boundary_mocks_only.setattr(
        service.requests,
        "get",
        lambda *args, **kwargs: _FakeResponse(
            url="https://example.com/insights",
            text="<html><body><a href='/contact'>Contact</a></body></html>",
        ),
    )
    with pytest.raises(AppError) as err:
        service.discover_publisher_inventory(
            PublisherInventoryServiceRequest(
                schema_version="1.0",
                insights_url="https://example.com/insights",
                settings=_settings(tmp_path),
                route_kind_hint="http_parse",
            ),
            run_context,
        )
    assert_app_error(err.value, code="publisher_inventory_http_empty", retryable=False)


def test_discover_publisher_inventory_preflight_short_circuits_direct_detail(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    settings = _settings(tmp_path)
    settings = replace(
        settings,
        force_browser=False,
        enable_preflight_classifier_and_direct_detail=True,
    )

    def _get(url, timeout, headers, allow_redirects=True):
        return _FakeResponse(
            url="https://example.com/research-library/ai-perspectives-2026",
            text=(
                "<html><head><title>AI Perspectives 2026</title></head>"
                "<body><a href='/files/ai-perspectives.pdf'>Download the research brief</a></body></html>"
            ),
        )

    external_boundary_mocks_only.setattr(service.requests, "get", _get)

    response = service.discover_publisher_inventory(
        PublisherInventoryServiceRequest(
            schema_version="1.0",
            insights_url="https://example.com/research-library/ai-perspectives-2026",
            settings=settings,
        ),
        run_context,
    )

    assert response.route_kind == "http_parse"
    assert response.scenario_summary is not None
    assert response.scenario_summary.scenario_class == "direct_detail_html"
    assert response.candidates[0].provenance == "direct_detail_source"


def test_discover_publisher_inventory_preflight_prefers_direct_detail_path_over_archive_terms(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    settings = _settings(tmp_path)
    settings = replace(
        settings,
        force_browser=True,
        enable_preflight_classifier_and_direct_detail=True,
    )

    def _get(url, timeout, headers, allow_redirects=True):
        return _FakeResponse(
            url="https://example.com/insights/research-library/ai-perspectives-2026",
            text=(
                "<html><head><title>AI Perspectives 2026</title></head>"
                "<body><h1>AI Perspectives 2026</h1>"
                "<p>Research library entry with related insights and latest research links.</p>"
                "</body></html>"
            ),
        )

    external_boundary_mocks_only.setattr(service.requests, "get", _get)

    response = service.discover_publisher_inventory(
        PublisherInventoryServiceRequest(
            schema_version="1.0",
            insights_url="https://example.com/insights/research-library/ai-perspectives-2026",
            settings=settings,
        ),
        run_context,
    )

    assert response.route_kind == "http_parse"
    assert response.scenario_summary is not None
    assert response.scenario_summary.scenario_class == "direct_detail_html"
    assert response.candidates[0].provenance == "direct_detail_source"
