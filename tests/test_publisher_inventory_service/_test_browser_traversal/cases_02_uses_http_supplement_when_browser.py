# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403

def test_discover_publisher_inventory_browser_uses_http_supplement_when_browser_candidates_are_empty(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    def _get(url, timeout, headers, allow_redirects=True):
        assert timeout == 10.0
        assert headers["User-Agent"].startswith("Mozilla/5.0")
        assert headers["Accept-Language"] == "en-US,en;q=0.9"
        return _FakeResponse(
            url="https://wordpress.bluecore.app/resources",
            text=(
                "<html><body>"
                "<a href='https://www.bluecore.com/lp/customer-movement-benchmarks/'>"
                "Benchmarks for Identification, Conversion, and Retention"
                "</a>"
                "</body></html>"
            ),
        )

    external_boundary_mocks_only.setattr(service.requests, "get", _get)
    states = {
        "initial": {
            "payload": {
                "page_url": "https://wordpress.bluecore.app/resources",
                "page_title": "Resources - Bluecore",
                "anchors": [],
            }
        },
        "origin": {
            "payload": {
                "page_url": "https://www.bluecore.com/resources",
                "page_title": "Resources - Bluecore",
                "anchors": [],
            },
        },
    }
    external_boundary_mocks_only.setattr(
        service, "import_module", lambda _name: _runtime_for_states(states)
    )
    external_boundary_mocks_only.setattr(service.asyncio, "sleep", _fast_sleep)

    response = service.discover_publisher_inventory(
        PublisherInventoryServiceRequest(
            schema_version="1.0",
            insights_url="https://www.bluecore.com/resources/",
            settings=_settings(tmp_path),
            route_kind_hint="browser_render",
        ),
        run_context,
    )

    assert response.route_kind == "browser_render"
    assert len(response.pages) == 1
    assert [candidate.url for candidate in response.candidates] == [
        "https://www.bluecore.com/lp/customer-movement-benchmarks"
    ]
    assert response.candidates[0].provenance == "http_supplement"

def test_discover_publisher_inventory_browser_uses_http_supplement_for_archive_root_only_candidate(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    def _get(url, timeout, headers, allow_redirects=True):
        assert timeout == 10.0
        assert headers["User-Agent"].startswith("Mozilla/5.0")
        assert headers["Accept-Language"] == "en-US,en;q=0.9"
        return _FakeResponse(
            url="https://ecdb.com/whitepapers-and-reports",
            text=(
                "<html><body>"
                "<a href='https://ecdb.com/reports/global-marketplaces-report'>"
                "Global Marketplaces Report"
                "</a>"
                "</body></html>"
            ),
        )

    external_boundary_mocks_only.setattr(service.requests, "get", _get)
    states = {
        "initial": {
            "payload": {
                "page_url": "https://ecdb.com/whitepapers-and-reports",
                "page_title": "Whitepapers and Reports",
                "anchors": [
                    {
                        "href": "https://ecdb.com/whitepapers-and-reports",
                        "text": "Whitepapers and Reports",
                        "rel": "",
                    }
                ],
            }
        }
    }
    external_boundary_mocks_only.setattr(
        service, "import_module", lambda _name: _runtime_for_states(states)
    )
    external_boundary_mocks_only.setattr(service.asyncio, "sleep", _fast_sleep)

    response = service.discover_publisher_inventory(
        PublisherInventoryServiceRequest(
            schema_version="1.0",
            insights_url="https://ecdb.com/whitepapers-and-reports",
            settings=_settings(tmp_path),
            route_kind_hint="browser_render",
        ),
        run_context,
    )

    assert response.route_kind == "browser_render"
    assert len(response.pages) == 1
    assert [candidate.url for candidate in response.candidates] == [
        "https://ecdb.com/reports/global-marketplaces-report"
    ]
    assert response.candidates[0].provenance == "http_supplement"

def test_discover_publisher_inventory_browser_invalid_http_supplement_html_fails_cleanly(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
    assert_app_error,
) -> None:
    def _get(url, timeout, headers, allow_redirects=True):
        assert timeout == 10.0
        assert headers["User-Agent"].startswith("Mozilla/5.0")
        assert headers["Accept-Language"] == "en-US,en;q=0.9"
        return _FakeResponse(
            url="https://example.com/insights",
            text='<![\ufffd"\ufffd(\u001c\ufffd\u001c\ufffdB\ufffdo\u0011IRD\ufffd\\\\',
        )

    external_boundary_mocks_only.setattr(service.requests, "get", _get)
    states = {
        "initial": {
            "payload": {
                "page_url": "https://example.com/insights",
                "page_title": "Insights",
                "anchors": [],
            },
        }
    }
    external_boundary_mocks_only.setattr(
        service, "import_module", lambda _name: _runtime_for_states(states)
    )
    external_boundary_mocks_only.setattr(service.asyncio, "sleep", _fast_sleep)

    with pytest.raises(AppError) as err:
        service.discover_publisher_inventory(
            PublisherInventoryServiceRequest(
                schema_version="1.0",
                insights_url="https://example.com/insights",
                settings=_settings(tmp_path),
                route_kind_hint="browser_render",
            ),
            run_context,
        )

    assert_app_error(
        err.value, code="publisher_inventory_browser_incomplete", retryable=True
    )

def test_discover_publisher_inventory_browser_pagination_limit_falls_back_to_http(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    external_boundary_mocks_only.setattr(
        service.requests,
        "get",
        lambda *args, **kwargs: _FakeResponse(
            url="https://example.com/insights",
            text=(
                "<html><body>"
                "<a href='/reports/consumer-benchmark-2026'>Consumer Benchmark 2026</a>"
                "</body></html>"
            ),
        ),
    )
    states = {
        "initial": {
            "payload": {
                "page_url": "https://example.com/insights",
                "page_title": "Insights",
                "anchors": [
                    {
                        "href": "https://example.com/reports/consumer-benchmark-2026",
                        "text": "Consumer Benchmark 2026",
                        "rel": "",
                    }
                ],
                "has_pagination_next": True,
            },
        }
    }
    external_boundary_mocks_only.setattr(
        service, "import_module", lambda _name: _runtime_for_states(states)
    )
    external_boundary_mocks_only.setattr(service.asyncio, "sleep", _fast_sleep)

    response = service.discover_publisher_inventory(
        PublisherInventoryServiceRequest(
            schema_version="1.0",
            insights_url="https://example.com/insights",
            settings=replace(_settings(tmp_path), pagination_max_pages=1),
            route_kind_hint="browser_render",
        ),
        run_context,
    )

    assert response.route_kind == "http_parse"
    assert [candidate.url for candidate in response.candidates] == [
        "https://example.com/reports/consumer-benchmark-2026"
    ]

def test_discover_publisher_inventory_browser_returns_bounded_result_after_multi_page_pagination_limit(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    external_boundary_mocks_only.setattr(
        service.requests,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("http fallback not expected")
        ),
    )
    states = {
        "initial": {
            "payload": {
                "page_url": "https://example.com/insights",
                "page_title": "Insights",
                "anchors": [
                    {
                        "href": "https://example.com/reports/consumer-benchmark-2026",
                        "text": "Consumer Benchmark 2026",
                        "rel": "",
                    }
                ],
                "load_more_labels": ["Load more"],
            },
            "named_clicks": {"load more": "page_2"},
        },
        "page_2": {
            "payload": {
                "page_url": "https://example.com/insights",
                "page_title": "Insights",
                "anchors": [
                    {
                        "href": "https://example.com/reports/consumer-benchmark-2026",
                        "text": "Consumer Benchmark 2026",
                        "rel": "",
                    },
                    {
                        "href": "https://example.com/reports/retail-outlook-2026",
                        "text": "Retail Outlook 2026",
                        "rel": "",
                    },
                ],
                "load_more_labels": ["Load more"],
            },
        },
    }
    external_boundary_mocks_only.setattr(
        service, "import_module", lambda _name: _runtime_for_states(states)
    )
    external_boundary_mocks_only.setattr(service.asyncio, "sleep", _fast_sleep)

    response = service.discover_publisher_inventory(
        PublisherInventoryServiceRequest(
            schema_version="1.0",
            insights_url="https://example.com/insights",
            settings=replace(_settings(tmp_path), pagination_max_pages=2),
            route_kind_hint="browser_render",
        ),
        run_context,
    )

    assert response.route_kind == "browser_render"
    assert len(response.pages) == 2
    assert (
        response.candidates[0].url
        == "https://example.com/reports/consumer-benchmark-2026"
    )
    assert (
        response.candidates[-1].url == "https://example.com/reports/retail-outlook-2026"
    )
    assert {candidate.url for candidate in response.candidates} == {
        "https://example.com/reports/consumer-benchmark-2026",
        "https://example.com/reports/retail-outlook-2026",
    }
    assert "pagination limit" in response.route_summary.lower()

def test_discover_publisher_inventory_browser_uses_rendered_html_supplement_when_visible_anchors_are_empty(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    external_boundary_mocks_only.setattr(
        service.requests,
        "get",
        lambda *args, **kwargs: _FakeResponse(
            url="https://www.bluecore.com/resources",
            text="<html><body><a href='/about'>About</a></body></html>",
        ),
    )
    states = {
        "initial": {
            "payload": {
                "page_url": "https://wordpress.bluecore.app/resources",
                "page_title": "Resources - Bluecore",
                "anchors": [],
            },
            "rendered_html": (
                "<html><body>"
                "<a href='https://www.bluecore.com/lp/customer-movement-benchmarks/'>"
                "Benchmarks for Identification, Conversion, and Retention"
                "</a>"
                "</body></html>"
            ),
        }
    }
    external_boundary_mocks_only.setattr(
        service, "import_module", lambda _name: _runtime_for_states(states)
    )
    external_boundary_mocks_only.setattr(service.asyncio, "sleep", _fast_sleep)

    response = service.discover_publisher_inventory(
        PublisherInventoryServiceRequest(
            schema_version="1.0",
            insights_url="https://www.bluecore.com/resources/",
            settings=_settings(tmp_path),
            route_kind_hint="browser_render",
        ),
        run_context,
    )

    assert response.route_kind == "browser_render"
    assert len(response.pages) == 1
    assert [candidate.url for candidate in response.candidates] == [
        "https://www.bluecore.com/lp/customer-movement-benchmarks"
    ]
    assert response.candidates[0].provenance == "browser_rendered_html_supplement"

def test_discover_publisher_inventory_browser_extracts_custom_component_links_from_rendered_html(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    external_boundary_mocks_only.setattr(
        service.requests,
        "get",
        lambda *args, **kwargs: _FakeResponse(
            url="https://www.juliusbaer.com/en/insights",
            text="<html><body></body></html>",
        ),
    )
    states = {
        "initial": {
            "payload": {
                "page_url": "https://www.juliusbaer.com/en/insights",
                "page_title": "Insights | Julius Baer",
                "anchors": [],
            },
            "rendered_html": (
                "<html><body>"
                "<jb-article-card "
                'link="{&quot;href&quot;:&quot;\\/en\\/insights\\/market-insights\\/market-outlook\\/iran-war-dominates-markets-what-now\\/&quot;}" '
                'teaserHeader="{&quot;headline&quot;:&quot;Iran war dominates markets: What now?&quot;}">'
                "</jb-article-card>"
                "</body></html>"
            ),
        }
    }
    external_boundary_mocks_only.setattr(
        service, "import_module", lambda _name: _runtime_for_states(states)
    )
    external_boundary_mocks_only.setattr(service.asyncio, "sleep", _fast_sleep)

    response = service.discover_publisher_inventory(
        PublisherInventoryServiceRequest(
            schema_version="1.0",
            insights_url="https://www.juliusbaer.com/en/insights/",
            settings=_settings(tmp_path),
            route_kind_hint="browser_render",
        ),
        run_context,
    )

    assert response.route_kind == "browser_render"
    assert [candidate.url for candidate in response.candidates] == [
        "https://www.juliusbaer.com/en/insights/market-insights/market-outlook/iran-war-dominates-markets-what-now"
    ]
    assert response.candidates[0].title == "Iran war dominates markets: What now?"
    assert response.candidates[0].provenance == "browser_rendered_html_supplement"

def test_discover_publisher_inventory_browser_seeds_direct_report_page_when_dom_has_only_navigation(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    states = {
        "initial": {
            "payload": {
                "page_url": "https://example.com/2026-garden-trends-report",
                "page_title": "2026 Garden Trends Report",
                "anchors": [
                    {
                        "href": "https://example.com/expertise",
                        "text": "Expertise",
                        "rel": "",
                    },
                    {"href": "https://example.com/blog", "text": "Blog", "rel": ""},
                ],
            },
        }
    }
    external_boundary_mocks_only.setattr(
        service, "import_module", lambda _name: _runtime_for_states(states)
    )
    external_boundary_mocks_only.setattr(service.asyncio, "sleep", _fast_sleep)

    response = service.discover_publisher_inventory(
        PublisherInventoryServiceRequest(
            schema_version="1.0",
            insights_url="https://example.com/2026-garden-trends-report",
            settings=_settings(tmp_path),
            route_kind_hint="browser_render",
        ),
        run_context,
    )

    assert response.route_kind == "browser_render"
    assert [candidate.url for candidate in response.candidates] == [
        "https://example.com/2026-garden-trends-report"
    ]
    assert response.candidates[0].title == "2026 Garden Trends Report"

def test_discover_publisher_inventory_browser_preserves_pre_cookie_archive_candidates_when_dismissal_degrades_page(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    external_boundary_mocks_only.setattr(
        service.requests,
        "get",
        lambda *args, **kwargs: _FakeResponse(
            url="https://www.bluecore.com/resources",
            text="<html><body><a href='/about'>About</a></body></html>",
        ),
    )
    external_boundary_mocks_only.setattr(service.asyncio, "sleep", _fast_sleep)
    states = {
        "initial": {
            "payload": {
                "page_url": "https://www.bluecore.com/resources",
                "page_title": "Resources - Bluecore",
                "anchors": [
                    {
                        "href": "https://www.bluecore.com/lp/customer-movement-benchmarks/",
                        "text": "Benchmarks for Identification, Conversion, and Retention",
                        "rel": "",
                    }
                ],
            },
            "cookie_banner_next_state": "drifted",
        },
        "drifted": {
            "payload": {
                "page_url": "https://wordpress.bluecore.app/resources",
                "page_title": "Resources - Bluecore",
                "anchors": [],
            },
            "rendered_html": "<html><body></body></html>",
        },
    }
    external_boundary_mocks_only.setattr(
        service, "import_module", lambda _name: _runtime_for_states(states)
    )

    response = service.discover_publisher_inventory(
        PublisherInventoryServiceRequest(
            schema_version="1.0",
            insights_url="https://www.bluecore.com/resources/",
            settings=_settings(tmp_path),
            route_kind_hint="browser_render",
        ),
        run_context,
    )

    assert response.route_kind == "browser_render"
    assert len(response.pages) == 1
    assert response.pages[0].page_url == "https://www.bluecore.com/resources"
    assert [candidate.url for candidate in response.candidates] == [
        "https://www.bluecore.com/lp/customer-movement-benchmarks"
    ]

def test_discover_publisher_inventory_browser_recovers_from_cross_apex_host_drift(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    external_boundary_mocks_only.setattr(
        service.requests,
        "get",
        lambda *args, **kwargs: _FakeResponse(
            url="https://www.bluecore.com/resources",
            text="<html><body><a href='/about'>About</a></body></html>",
        ),
    )
    states = {
        "initial": {
            "payload": {
                "page_url": "https://wordpress.bluecore.app/resources",
                "page_title": "Resources - Bluecore",
                "anchors": [],
            },
        },
        "origin": {
            "payload": {
                "page_url": "https://www.bluecore.com/resources/",
                "page_title": "Resources - Bluecore",
                "anchors": [
                    {
                        "href": "https://www.bluecore.com/lp/customer-movement-benchmarks/",
                        "text": "Benchmarks for Identification, Conversion, and Retention",
                        "rel": "",
                    }
                ],
            },
        },
    }
    external_boundary_mocks_only.setattr(
        service, "import_module", lambda _name: _runtime_for_states(states)
    )
    external_boundary_mocks_only.setattr(service.asyncio, "sleep", _fast_sleep)

    response = service.discover_publisher_inventory(
        PublisherInventoryServiceRequest(
            schema_version="1.0",
            insights_url="https://www.bluecore.com/resources/",
            settings=_settings(tmp_path),
            route_kind_hint="browser_render",
        ),
        run_context,
    )

    assert response.route_kind == "browser_render"
    assert len(response.pages) == 1
    assert response.pages[0].page_url == "https://www.bluecore.com/resources"
    assert [candidate.url for candidate in response.candidates] == [
        "https://www.bluecore.com/lp/customer-movement-benchmarks"
    ]

def test_discover_publisher_inventory_browser_falls_back_to_direct_http_when_browser_path_stays_empty(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    call_counts: dict[str, int] = {}

    def _get(url, timeout, headers, allow_redirects=True):
        key = str(url)
        call_counts[key] = call_counts.get(key, 0) + 1
        assert timeout == 10.0
        assert headers["User-Agent"].startswith("Mozilla/5.0")
        if "wordpress.bluecore.app" in key:
            raise service.requests.ConnectTimeout("mirror timeout")
        if key == "https://www.bluecore.com/resources" and call_counts[key] == 1:
            raise service.requests.ConnectTimeout("origin supplement timeout")
        if key == "https://www.bluecore.com/resources":
            return _FakeResponse(
                url="https://www.bluecore.com/resources",
                text=(
                    "<html><body>"
                    "<a href='https://www.bluecore.com/lp/customer-movement-benchmarks/'>"
                    "Benchmarks for Identification, Conversion, and Retention"
                    "</a>"
                    "</body></html>"
                ),
            )
        raise AssertionError(f"Unexpected URL: {url}")

    external_boundary_mocks_only.setattr(service.requests, "get", _get)
    states = {
        "initial": {
            "payload": {
                "page_url": "https://wordpress.bluecore.app/resources",
                "page_title": "Resources - Bluecore",
                "anchors": [],
            },
            "rendered_html": "<html><body></body></html>",
        },
        "origin": {
            "payload": {
                "page_url": "https://www.bluecore.com/resources",
                "page_title": "Resources - Bluecore",
                "anchors": [],
            },
        },
    }
    external_boundary_mocks_only.setattr(
        service, "import_module", lambda _name: _runtime_for_states(states)
    )
    external_boundary_mocks_only.setattr(service.asyncio, "sleep", _fast_sleep)

    response = service.discover_publisher_inventory(
        PublisherInventoryServiceRequest(
            schema_version="1.0",
            insights_url="https://www.bluecore.com/resources/",
            settings=_settings(tmp_path),
            route_kind_hint="browser_render",
        ),
        run_context,
    )

    assert response.route_kind == "http_parse"
    assert [candidate.url for candidate in response.candidates] == [
        "https://www.bluecore.com/lp/customer-movement-benchmarks"
    ]

__all__ = [
    "test_discover_publisher_inventory_browser_uses_http_supplement_when_browser_candidates_are_empty",
    "test_discover_publisher_inventory_browser_uses_http_supplement_for_archive_root_only_candidate",
    "test_discover_publisher_inventory_browser_invalid_http_supplement_html_fails_cleanly",
    "test_discover_publisher_inventory_browser_pagination_limit_falls_back_to_http",
    "test_discover_publisher_inventory_browser_returns_bounded_result_after_multi_page_pagination_limit",
    "test_discover_publisher_inventory_browser_uses_rendered_html_supplement_when_visible_anchors_are_empty",
    "test_discover_publisher_inventory_browser_extracts_custom_component_links_from_rendered_html",
    "test_discover_publisher_inventory_browser_seeds_direct_report_page_when_dom_has_only_navigation",
    "test_discover_publisher_inventory_browser_preserves_pre_cookie_archive_candidates_when_dismissal_degrades_page",
    "test_discover_publisher_inventory_browser_recovers_from_cross_apex_host_drift",
    "test_discover_publisher_inventory_browser_falls_back_to_direct_http_when_browser_path_stays_empty",
]
