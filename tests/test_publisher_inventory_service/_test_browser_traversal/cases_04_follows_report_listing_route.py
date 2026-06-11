# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403

def test_discover_publisher_inventory_browser_follows_report_listing_route(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    states = {
        "initial": {
            "payload": {
                "page_url": "https://www.gfk-media-measurement.com/global/en/insights/",
                "page_title": "Insights",
                "anchors": [
                    {
                        "href": "https://www.gfk-media-measurement.com/global/en/insights/commentary/2025/example/",
                        "text": "Commentary",
                        "rel": "",
                    }
                ],
                "report_link_url": "https://www.gfk-media-measurement.com/global/en/insights/report/2025/reports/",
            }
        },
        "report_listing": {
            "payload": {
                "page_url": "https://www.gfk-media-measurement.com/global/en/insights/report/2025/reports/",
                "page_title": "Reports",
                "anchors": [
                    {
                        "href": "https://www.gfk-media-measurement.com/global/en/insights/report/2025/reports/q2-audience-report/",
                        "text": "Q2 Audience Report 2025",
                        "rel": "",
                    }
                ],
            }
        },
    }
    external_boundary_mocks_only.setattr(
        service, "import_module", lambda _name: _runtime_for_states(states)
    )
    external_boundary_mocks_only.setattr(service.asyncio, "sleep", _fast_sleep)

    response = service.discover_publisher_inventory(
        PublisherInventoryServiceRequest(
            schema_version="1.0",
            insights_url="https://www.gfk-media-measurement.com/global/en/insights/",
            settings=_settings(tmp_path),
            route_kind_hint="browser_render",
        ),
        run_context,
    )

    assert response.route_kind == "browser_render"
    assert (
        response.final_page_url
        == "https://www.gfk-media-measurement.com/global/en/insights/report/2025/reports"
    )
    assert (
        response.candidates[0].url
        == "https://www.gfk-media-measurement.com/global/en/insights/report/2025/reports/q2-audience-report"
    )
    assert "report listing route" in response.route_summary

def test_discover_publisher_inventory_browser_follows_whitepaper_listing_route(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    states = {
        "initial": {
            "payload": {
                "page_url": "https://onclusive.com/fr/expertise/insights/",
                "page_title": "Insights",
                "anchors": [
                    {
                        "href": "https://onclusive.com/fr/expertise/insights/article-one/",
                        "text": "Article",
                        "rel": "",
                    }
                ],
                "report_link_url": "https://onclusive.com/fr/ressources/livres-blancs/",
            }
        },
        "report_listing": {
            "payload": {
                "page_url": "https://onclusive.com/fr/ressources/livres-blancs/",
                "page_title": "Livres Blancs",
                "anchors": [
                    {
                        "href": "https://onclusive.com/fr/ressources/livres-blancs/barometre-medias-2026/",
                        "text": "Baromètre médias 2026",
                        "rel": "",
                    }
                ],
            }
        },
    }
    external_boundary_mocks_only.setattr(
        service, "import_module", lambda _name: _runtime_for_states(states)
    )
    external_boundary_mocks_only.setattr(service.asyncio, "sleep", _fast_sleep)

    response = service.discover_publisher_inventory(
        PublisherInventoryServiceRequest(
            schema_version="1.0",
            insights_url="https://onclusive.com/fr/expertise/insights/",
            settings=_settings(tmp_path),
            route_kind_hint="browser_render",
        ),
        run_context,
    )

    assert response.route_kind == "browser_render"
    assert (
        response.final_page_url == "https://onclusive.com/fr/ressources/livres-blancs"
    )
    assert (
        response.candidates[0].url
        == "https://onclusive.com/fr/ressources/livres-blancs/barometre-medias-2026"
    )

def test_increment_browser_traversal_metrics_updates_only_requested_counter() -> None:
    baseline = service._new_browser_traversal_metrics()

    updated = service._increment_browser_traversal_metrics(
        baseline,
        load_more_clicks=2,
    )

    assert updated.cookies_dismissed == 0
    assert updated.report_route_clicks == 0
    assert updated.report_filter_applied == 0
    assert updated.tab_clicks == 0
    assert updated.load_more_clicks == 2
    assert updated.next_page_visits == 0
    assert updated.archive_expansion_clicks == 0
    assert updated.button_pagination_clicks == 0

__all__ = [
    "test_discover_publisher_inventory_browser_follows_report_listing_route",
    "test_discover_publisher_inventory_browser_follows_whitepaper_listing_route",
    "test_increment_browser_traversal_metrics_updates_only_requested_counter",
]
