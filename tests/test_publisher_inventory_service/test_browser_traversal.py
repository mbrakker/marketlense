from __future__ import annotations

from .builders import *  # noqa: F401,F403


def test_discover_publisher_inventory_browser_applies_generic_report_dropdown_filter(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    external_boundary_mocks_only.setattr(
        service.requests,
        "get",
        lambda *args, **kwargs: _FakeResponse(
            url="https://www.transunion.com/insights",
            text="<html><body><a href='/about'>About</a></body></html>",
        ),
    )
    states = {
        "initial": {
            "payload": {
                "page_url": "https://www.transunion.com/insights",
                "page_title": "Insights | TransUnion",
                "anchors": [
                    {
                        "href": "https://www.transunion.com/blog/example-blog",
                        "text": "Example Blog",
                        "rel": "",
                    }
                ],
                "has_report_filter": True,
                "has_apply_button": False,
                "has_pagination_next": True,
            },
            "apply_filter_next_state": "filtered",
        },
        "filtered": {
            "payload": {
                "page_url": "https://www.transunion.com/insights",
                "page_title": "Insights | TransUnion",
                "anchors": [
                    {
                        "href": "https://www.transunion.com/report/example-industry-report",
                        "text": "Example Industry Report 2026",
                        "rel": "",
                    }
                ],
                "has_report_filter": True,
                "has_apply_button": False,
                "has_pagination_next": False,
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
            insights_url="https://www.transunion.com/insights",
            settings=_settings(tmp_path),
            route_kind_hint="browser_render",
        ),
        run_context,
    )

    assert response.route_kind == "browser_render"
    assert [candidate.url for candidate in response.candidates] == [
        "https://www.transunion.com/report/example-industry-report"
    ]
    assert response.candidates[0].provenance == "browser_dom"
    assert "Applied the report format filter." in response.route_summary


def test_discover_publisher_inventory_browser_fallback_when_http_empty(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
    assert_no_defaulted_required_fields,
) -> None:
    external_boundary_mocks_only.setattr(
        service.requests,
        "get",
        lambda *args, **kwargs: _FakeResponse(
            url="https://example.com/insights",
            text="<html><body><a href='/about'>About</a></body></html>",
        ),
    )
    states = {
        "initial": {
            "payload": {
                "page_url": "https://example.com/insights",
                "page_title": "Insights",
                "anchors": [
                    {
                        "href": "https://example.com/reports/report-one",
                        "text": "Report One 2026",
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
                        "href": "https://example.com/reports/report-one",
                        "text": "Report One 2026",
                        "rel": "",
                    },
                    {
                        "href": "https://example.com/reports/report-two",
                        "text": "Report Two 2026",
                        "rel": "",
                    },
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
            insights_url="https://example.com/insights",
            settings=_settings(tmp_path),
            route_hint="Click the next pagination control after scanning page one.",
            route_kind_hint="browser_render",
        ),
        run_context,
    )

    assert response.route_kind == "browser_render"
    assert response.used_route_hint is True
    assert len(response.pages) == 2
    assert any(
        candidate.url == "https://example.com/reports/report-two"
        and candidate.discovered_on_page_number == 2
        for candidate in response.candidates
    )
    assert_no_defaulted_required_fields(response)


def test_discover_publisher_inventory_browser_closes_stray_blank_pages(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    external_boundary_mocks_only.setattr(
        service.requests,
        "get",
        lambda *args, **kwargs: _FakeResponse(
            url="https://example.com/insights",
            text="<html><body><a href='/about'>About</a></body></html>",
        ),
    )
    states = {
        "initial": {
            "payload": {
                "page_url": "https://example.com/insights",
                "page_title": "Insights",
                "anchors": [
                    {
                        "href": "https://example.com/reports/report-one",
                        "text": "Report One 2026",
                        "rel": "",
                    }
                ],
            }
        }
    }
    external_boundary_mocks_only.setattr(
        service,
        "import_module",
        lambda _name: _runtime_for_states(
            states,
            extra_page_urls=["about:blank", "chrome://newtab"],
        ),
    )
    external_boundary_mocks_only.setattr(service.asyncio, "sleep", _fast_sleep)

    response = service.discover_publisher_inventory(
        PublisherInventoryServiceRequest(
            schema_version="1.0",
            insights_url="https://example.com/insights",
            settings=_settings(tmp_path),
            route_kind_hint="browser_render",
        ),
        run_context,
    )

    assert response.route_kind == "browser_render"
    assert _FakeBrowser.last_instance is not None
    assert _FakeBrowser.last_instance.closed_page_ids == ["aux-1", "aux-2"]


def test_discover_publisher_inventory_browser_scrolls_to_hydrate_load_more(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    external_boundary_mocks_only.setattr(
        service.requests,
        "get",
        lambda *args, **kwargs: _FakeResponse(
            url="https://www.bain.com/insights?filters=|types(424%2C420)",
            text="<html><body><a href='/about'>About</a></body></html>",
        ),
    )
    states = {
        "initial": {
            "payload": {
                "page_url": "https://www.bain.com/insights?filters=|types(424%2C420)",
                "page_title": "Insights",
                "anchors": [
                    {
                        "href": "https://www.bain.com/insights/books",
                        "text": "Bain Books",
                        "rel": "",
                    }
                ],
            },
            "scroll_next_state": "scrolled",
        },
        "scrolled": {
            "payload": {
                "page_url": "https://www.bain.com/insights?filters=|types(424%2C420)",
                "page_title": "Insights",
                "anchors": [
                    {
                        "href": "https://www.bain.com/insights/asia-pacific-private-equity-report-2026",
                        "text": "Asia-Pacific Private Equity Report 2026",
                        "rel": "",
                    }
                ],
                "load_more_labels": ["Load more"],
            },
            "named_clicks": {"load more": "page_2"},
        },
        "page_2": {
            "payload": {
                "page_url": "https://www.bain.com/insights?filters=|types(424%2C420)",
                "page_title": "Insights",
                "anchors": [
                    {
                        "href": "https://www.bain.com/insights/asia-pacific-private-equity-report-2026",
                        "text": "Asia-Pacific Private Equity Report 2026",
                        "rel": "",
                    },
                    {
                        "href": "https://www.bain.com/insights/private-equitys-reality-check-gp-outlook-2026",
                        "text": "Private Equity's Reality Check: The GP Outlook for 2026",
                        "rel": "",
                    },
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
            insights_url="https://www.bain.com/insights?filters=|types(424%2C420)",
            settings=_settings(tmp_path),
            route_kind_hint="browser_render",
        ),
        run_context,
    )

    assert response.route_kind == "browser_render"
    assert len(response.pages) == 2
    assert any(
        candidate.url
        == "https://www.bain.com/insights/private-equitys-reality-check-gp-outlook-2026"
        and candidate.discovered_on_page_number == 2
        for candidate in response.candidates
    )
    assert "Expanded load-more pagination 1 time(s)." in response.route_summary


def test_discover_publisher_inventory_browser_stops_before_recording_inert_duplicate_load_more_states(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    external_boundary_mocks_only.setattr(
        service.requests,
        "get",
        lambda *args, **kwargs: _FakeResponse(
            url="https://www.alixpartners.com/insights",
            text="<html><body><a href='/about'>About</a></body></html>",
        ),
    )
    shared_anchors = [
        {
            "href": "https://www.alixpartners.com/insights/report-one",
            "text": "Report One",
            "rel": "",
        },
        {
            "href": "https://www.alixpartners.com/insights/report-two",
            "text": "Report Two",
            "rel": "",
        },
    ]
    states = {
        "initial": {
            "payload": {
                "page_url": "https://www.alixpartners.com/insights",
                "page_title": "Insights",
                "anchors": shared_anchors[:1],
                "load_more_labels": ["Load more"],
            },
            "named_clicks": {"load more": "page_2"},
        },
        "page_2": {
            "payload": {
                "page_url": "https://www.alixpartners.com/insights",
                "page_title": "Insights",
                "anchors": shared_anchors,
                "load_more_labels": ["Load more"],
            },
            "named_clicks": {"load more": "page_3"},
        },
        "page_3": {
            "payload": {
                "page_url": "https://www.alixpartners.com/insights",
                "page_title": "Insights",
                "anchors": shared_anchors,
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
            insights_url="https://www.alixpartners.com/insights/",
            settings=_settings(tmp_path),
            route_kind_hint="browser_render",
        ),
        run_context,
    )

    assert response.route_kind == "browser_render"
    assert len(response.pages) == 2
    assert [page.page_number for page in response.pages] == [1, 2]
    assert [candidate.url for candidate in response.candidates] == [
        "https://www.alixpartners.com/insights/report-one",
        "https://www.alixpartners.com/insights/report-one",
        "https://www.alixpartners.com/insights/report-two",
    ]
    assert "Expanded load-more pagination 1 time(s)." in response.route_summary


def test_discover_publisher_inventory_browser_prefers_candidate_dense_load_more_surface(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    external_boundary_mocks_only.setattr(
        service.requests,
        "get",
        lambda *args, **kwargs: _FakeResponse(
            url="https://www.algolia.com/resources",
            text="<html><body><a href='/about'>About</a></body></html>",
        ),
    )
    states = {
        "initial": {
            "payload": {
                "page_url": "https://www.algolia.com/resources",
                "page_title": "Resource Center",
                "anchors": [
                    {
                        "href": "https://www.algolia.com/resources/asset/ebook-understanding-ai-transparency",
                        "text": "Understanding AI transparency",
                        "rel": "",
                    },
                    {
                        "href": "https://www.algolia.com/resources/asset/the-roi-of-relevance-algolia-shopify",
                        "text": "The ROI of Relevance: Algolia + Shopify",
                        "rel": "",
                    },
                ],
                "load_more_labels": ["Show more results", "Show More"],
            },
            "named_click_choices": [
                {
                    "label": "show more results",
                    "next_state": "wrong_surface",
                    "candidate_hits": 1,
                    "top": 1100,
                },
                {
                    "label": "show more",
                    "next_state": "page_2",
                    "candidate_hits": 6,
                    "top": 900,
                },
            ],
        },
        "wrong_surface": {
            "payload": {
                "page_url": "https://www.algolia.com/resources",
                "page_title": "Resource Center",
                "anchors": [
                    {
                        "href": "https://www.algolia.com/products/ai-search",
                        "text": "AI Search",
                        "rel": "",
                    }
                ],
            }
        },
        "page_2": {
            "payload": {
                "page_url": "https://www.algolia.com/resources",
                "page_title": "Resource Center",
                "anchors": [
                    {
                        "href": "https://www.algolia.com/resources/asset/ebook-understanding-ai-transparency",
                        "text": "Understanding AI transparency",
                        "rel": "",
                    },
                    {
                        "href": "https://www.algolia.com/resources/asset/the-roi-of-relevance-algolia-shopify",
                        "text": "The ROI of Relevance: Algolia + Shopify",
                        "rel": "",
                    },
                    {
                        "href": "https://www.algolia.com/resources/asset/ebook-why-agentic-ai-is-your-next-priority",
                        "text": "Why agentic AI is your next priority ebook",
                        "rel": "",
                    },
                    {
                        "href": "https://www.algolia.com/resources/asset/ebook-retail-media-trends-2026",
                        "text": "Retail media trends 2026 ebook",
                        "rel": "",
                    },
                    {
                        "href": "https://www.algolia.com/resources/asset/ebook-black-friday-data-playbook",
                        "text": "Black Friday data playbook ebook",
                        "rel": "",
                    },
                    {
                        "href": "https://www.algolia.com/resources/asset/ebook-b2c-ecommerce-ai-trends-2026",
                        "text": "2026 B2C ecommerce AI trends ebook",
                        "rel": "",
                    },
                ],
                "load_more_labels": ["Show more results"],
            },
            "named_click_choices": [
                {
                    "label": "show more results",
                    "next_state": "wrong_surface",
                    "candidate_hits": 1,
                    "top": 1200,
                }
            ],
        },
    }
    external_boundary_mocks_only.setattr(
        service, "import_module", lambda _name: _runtime_for_states(states)
    )
    external_boundary_mocks_only.setattr(service.asyncio, "sleep", _fast_sleep)

    response = service.discover_publisher_inventory(
        PublisherInventoryServiceRequest(
            schema_version="1.0",
            insights_url="https://www.algolia.com/resources?reports",
            settings=_settings(tmp_path),
            route_kind_hint="browser_render",
        ),
        run_context,
    )

    assert response.route_kind == "browser_render"
    assert len(response.pages) == 2
    assert any(
        candidate.url
        == "https://www.algolia.com/resources/asset/ebook-why-agentic-ai-is-your-next-priority"
        and candidate.discovered_on_page_number == 2
        for candidate in response.candidates
    )


def test_discover_publisher_inventory_browser_resets_empty_results_filters(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    external_boundary_mocks_only.setattr(
        service.requests,
        "get",
        lambda *args, **kwargs: _FakeResponse(
            url="https://www.contentful.com/resources/",
            text="<html><body><a href='/about'>About</a></body></html>",
        ),
    )
    states = {
        "initial": {
            "payload": {
                "page_url": "https://www.contentful.com/resources/",
                "page_title": "Resources | Contentful",
                "anchors": [
                    {
                        "href": "https://www.contentful.com/resources/the-great-content-collapse/",
                        "text": "The Great Content Collapse",
                        "rel": "",
                    }
                ],
                "empty_results_visible": True,
                "reset_filter_labels": ["Reset all filters"],
            },
            "named_clicks": {"reset all filters": "listing"},
        },
        "listing": {
            "payload": {
                "page_url": "https://www.contentful.com/resources/",
                "page_title": "Resources | Contentful",
                "anchors": [
                    {
                        "href": "https://www.contentful.com/resources/composable-commerce-for-growth/",
                        "text": "Composable commerce for growth report",
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
            insights_url="https://www.contentful.com/resources/",
            settings=_settings(tmp_path),
            route_kind_hint="browser_render",
        ),
        run_context,
    )

    assert response.route_kind == "browser_render"
    assert len(response.pages) == 1
    assert [candidate.url for candidate in response.candidates] == [
        "https://www.contentful.com/resources/composable-commerce-for-growth"
    ]


def test_discover_publisher_inventory_browser_uses_http_supplement_when_browser_candidates_are_empty(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    def _get(url, timeout, headers):
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
    def _get(url, timeout, headers):
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
    def _get(url, timeout, headers):
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

    def _get(url, timeout, headers):
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


def test_discover_publisher_inventory_browser_prioritizes_button_pagination_over_hero_load_more(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    external_boundary_mocks_only.setattr(
        service.requests,
        "get",
        lambda *args, **kwargs: _FakeResponse(
            url="https://business.adobe.com/resources/reports.html",
            text="<html><body><a href='/about'>About</a></body></html>",
        ),
    )
    states = {
        "initial": {
            "payload": {
                "page_url": "https://business.adobe.com/resources/reports.html",
                "page_title": "Adobe Reports",
                "anchors": [
                    {
                        "href": "https://business.adobe.com/resources/reports/report-one.html",
                        "text": "Read now",
                        "heading_text": "Adobe Report One 2026",
                        "rel": "",
                    }
                ],
                "load_more_labels": ["Load more"],
                "has_pagination_next": True,
            },
            "named_clicks": {"load more": "hero_load_more"},
            "pagination_next_state": "page_2",
        },
        "hero_load_more": {
            "payload": {
                "page_url": "https://business.adobe.com/resources/reports.html",
                "page_title": "Adobe Reports",
                "anchors": [
                    {
                        "href": "https://business.adobe.com/resources/reports/report-one.html",
                        "text": "Read now",
                        "heading_text": "Adobe Report One 2026",
                        "rel": "",
                    },
                    {
                        "href": "https://business.adobe.com/resources/reports/report-hero.html",
                        "text": "Read now",
                        "heading_text": "Hero Spotlight Report",
                        "rel": "",
                    },
                ],
            }
        },
        "page_2": {
            "payload": {
                "page_url": "https://business.adobe.com/resources/reports.html?page=2",
                "page_title": "Adobe Reports",
                "anchors": [
                    {
                        "href": "https://business.adobe.com/resources/reports/report-two.html",
                        "text": "Read now",
                        "heading_text": "Adobe Report Two 2026",
                        "rel": "",
                    }
                ],
                "has_pagination_next": True,
                "result_range_end": 18,
                "result_range_total": 18,
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
            insights_url="https://business.adobe.com/resources/reports.html",
            settings=_settings(tmp_path),
            route_kind_hint="browser_render",
        ),
        run_context,
    )

    assert response.route_kind == "browser_render"
    assert len(response.pages) == 2
    assert (
        response.pages[1].page_url
        == "https://business.adobe.com/resources/reports.html?page=2"
    )
    assert [candidate.title for candidate in response.candidates] == [
        "Adobe Report One 2026",
        "Adobe Report Two 2026",
    ]
    assert "Clicked button pagination 1 time(s)." in response.route_summary
    assert "Expanded load-more pagination" not in response.route_summary


def test_discover_publisher_inventory_browser_stops_on_load_more_state_change_without_new_unique_candidates(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    external_boundary_mocks_only.setattr(
        service.requests,
        "get",
        lambda *args, **kwargs: _FakeResponse(
            url="https://example.com/insights",
            text="<html><body><a href='/about'>About</a></body></html>",
        ),
    )
    states = {
        "initial": {
            "payload": {
                "page_url": "https://example.com/insights",
                "page_title": "Insights",
                "anchors": [
                    {
                        "href": "https://example.com/reports/report-one",
                        "text": "Report One 2026",
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
                        "href": "https://example.com/reports/report-one",
                        "text": "Report One 2026",
                        "rel": "",
                    },
                    {
                        "href": "https://example.com/about",
                        "text": "About",
                        "rel": "",
                    },
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
            insights_url="https://example.com/insights",
            settings=_settings(tmp_path),
            route_kind_hint="browser_render",
        ),
        run_context,
    )

    assert response.route_kind == "browser_render"
    assert len(response.pages) == 1
    assert "Expanded load-more pagination 1 time(s)." in response.route_summary


def test_discover_publisher_inventory_browser_treats_inert_load_more_as_exhausted(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    external_boundary_mocks_only.setattr(
        service.requests,
        "get",
        lambda *args, **kwargs: _FakeResponse(
            url="https://example.com/insights",
            text="<html><body><a href='/about'>About</a></body></html>",
        ),
    )
    states = {
        "initial": {
            "payload": {
                "page_url": "https://example.com/insights",
                "page_title": "Insights",
                "anchors": [
                    {
                        "href": "https://example.com/reports/report-one",
                        "text": "Report One 2026",
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
                        "href": "https://example.com/reports/report-one",
                        "text": "Report One 2026",
                        "rel": "",
                    },
                    {
                        "href": "https://example.com/reports/report-two",
                        "text": "Report Two 2026",
                        "rel": "",
                    },
                ],
                "load_more_labels": ["Load more"],
            },
            "named_clicks": {"load more": "page_2"},
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
            settings=_settings(tmp_path),
            route_kind_hint="browser_render",
        ),
        run_context,
    )

    assert response.route_kind == "browser_render"
    assert len(response.pages) == 2
    assert [candidate.url for candidate in response.candidates] == [
        "https://example.com/reports/report-one",
        "https://example.com/reports/report-one",
        "https://example.com/reports/report-two",
    ]
    assert "Expanded load-more pagination 1 time(s)." in response.route_summary


def test_discover_publisher_inventory_browser_skips_duplicate_same_url_page_states(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    external_boundary_mocks_only.setattr(
        service.requests,
        "get",
        lambda *args, **kwargs: _FakeResponse(
            url="https://www.alixpartners.com/insights",
            text="<html><body><a href='/about'>About</a></body></html>",
        ),
    )
    states = {
        "initial": {
            "payload": {
                "page_url": "https://www.alixpartners.com/insights",
                "page_title": "Insights",
                "anchors": [
                    {
                        "href": "https://www.alixpartners.com/insights/report-one",
                        "text": "Report One",
                        "rel": "",
                    }
                ],
                "load_more_labels": ["Load more"],
            },
            "named_clicks": {"load more": "page_2"},
        },
        "page_2": {
            "payload": {
                "page_url": "https://www.alixpartners.com/insights",
                "page_title": "Insights",
                "anchors": [
                    {
                        "href": "https://www.alixpartners.com/insights/report-one",
                        "text": "Report One",
                        "rel": "",
                    },
                    {
                        "href": "https://www.alixpartners.com/insights/report-two",
                        "text": "Report Two",
                        "rel": "",
                    },
                ],
                "load_more_labels": ["Load more"],
            },
            "named_clicks": {"load more": "page_3"},
        },
        "page_3": {
            "payload": {
                "page_url": "https://www.alixpartners.com/insights",
                "page_title": "Insights",
                "anchors": [
                    {
                        "href": "https://www.alixpartners.com/insights/report-one",
                        "text": "Report One",
                        "rel": "",
                    },
                    {
                        "href": "https://www.alixpartners.com/insights/report-two",
                        "text": "Report Two",
                        "rel": "",
                    },
                    {
                        "href": "https://www.alixpartners.com/about",
                        "text": "About",
                        "rel": "",
                    },
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
            insights_url="https://www.alixpartners.com/insights/",
            settings=_settings(tmp_path),
            route_kind_hint="browser_render",
        ),
        run_context,
    )

    assert response.route_kind == "browser_render"
    assert len(response.pages) == 2
    assert [page.page_number for page in response.pages] == [1, 2]
    assert [candidate.url for candidate in response.candidates] == [
        "https://www.alixpartners.com/insights/report-one",
        "https://www.alixpartners.com/insights/report-one",
        "https://www.alixpartners.com/insights/report-two",
    ]
    assert "Expanded load-more pagination 2 time(s)." in response.route_summary


def test_discover_publisher_inventory_browser_breaks_same_url_load_more_cycles(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    external_boundary_mocks_only.setattr(
        service.requests,
        "get",
        lambda *args, **kwargs: _FakeResponse(
            url="https://www.askattest.com/our-research",
            text="<html><body><a href='/about'>About</a></body></html>",
        ),
    )
    states = {
        "initial": {
            "payload": {
                "page_url": "https://www.askattest.com/our-research",
                "page_title": "Research",
                "anchors": [
                    {
                        "href": "https://www.askattest.com/research/report-one",
                        "text": "Report One",
                        "rel": "",
                    }
                ],
                "load_more_labels": ["Load more"],
            },
            "named_clicks": {"load more": "page_2"},
        },
        "page_2": {
            "payload": {
                "page_url": "https://www.askattest.com/our-research",
                "page_title": "Research",
                "anchors": [
                    {
                        "href": "https://www.askattest.com/research/report-one",
                        "text": "Report One",
                        "rel": "",
                    },
                    {
                        "href": "https://www.askattest.com/research/report-two",
                        "text": "Report Two",
                        "rel": "",
                    },
                ],
                "load_more_labels": ["Load more"],
            },
            "named_clicks": {"load more": "page_3"},
        },
        "page_3": {
            "payload": {
                "page_url": "https://www.askattest.com/our-research",
                "page_title": "Research",
                "anchors": [
                    {
                        "href": "https://www.askattest.com/research/report-one",
                        "text": "Report One",
                        "rel": "",
                    }
                ],
                "load_more_labels": ["Load more"],
            },
            "named_clicks": {"load more": "page_2"},
        },
    }
    external_boundary_mocks_only.setattr(
        service, "import_module", lambda _name: _runtime_for_states(states)
    )
    external_boundary_mocks_only.setattr(service.asyncio, "sleep", _fast_sleep)

    response = service.discover_publisher_inventory(
        PublisherInventoryServiceRequest(
            schema_version="1.0",
            insights_url="https://www.askattest.com/our-research",
            settings=_settings(tmp_path),
            route_kind_hint="browser_render",
        ),
        run_context,
    )

    assert response.route_kind == "browser_render"
    assert len(response.pages) == 2
    assert [page.page_number for page in response.pages] == [1, 2]
    assert [candidate.url for candidate in response.candidates] == [
        "https://www.askattest.com/research/report-one",
        "https://www.askattest.com/research/report-one",
        "https://www.askattest.com/research/report-two",
    ]
    assert "Expanded load-more pagination 2 time(s)." in response.route_summary


def test_discover_publisher_inventory_browser_breaks_cross_url_signature_cycles(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    external_boundary_mocks_only.setattr(
        service.requests,
        "get",
        lambda *args, **kwargs: _FakeResponse(
            url="https://datareportal.com/reports",
            text="<html><body><a href='/reports?offset=34'>Next</a></body></html>",
        ),
    )
    shared_anchors = [
        {
            "href": "https://datareportal.com/reports/report-one",
            "text": "Report One",
            "rel": "",
        },
        {
            "href": "https://datareportal.com/reports/report-two",
            "text": "Report Two",
            "rel": "",
        },
    ]
    states = {
        "initial": {
            "payload": {
                "page_url": "https://datareportal.com/reports",
                "page_title": "Reports",
                "anchors": shared_anchors,
                "rel_next_hrefs": ["/reports?offset=34"],
            },
            "goto_states": {
                "https://datareportal.com/reports?offset=34": "page_2",
            },
        },
        "page_2": {
            "payload": {
                "page_url": "https://datareportal.com/reports?offset=34",
                "page_title": "Reports",
                "anchors": shared_anchors,
                "rel_next_hrefs": ["/reports?offset=68"],
            },
            "goto_states": {
                "https://datareportal.com/reports?offset=68": "page_3",
            },
        },
        "page_3": {
            "payload": {
                "page_url": "https://datareportal.com/reports?offset=68",
                "page_title": "Reports",
                "anchors": shared_anchors,
                "rel_next_hrefs": ["/reports?offset=102"],
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
            insights_url="https://datareportal.com/reports",
            settings=_settings(tmp_path),
            route_kind_hint="browser_render",
        ),
        run_context,
    )

    assert response.route_kind == "browser_render"
    assert len(response.pages) == 1
    assert [page.page_url for page in response.pages] == [
        "https://datareportal.com/reports",
    ]
    assert [candidate.url for candidate in response.candidates] == [
        "https://datareportal.com/reports/report-one",
        "https://datareportal.com/reports/report-two",
    ]


def test_discover_publisher_inventory_force_browser_skips_http(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    settings = _settings(tmp_path)
    settings = PublisherInventorySettings(
        schema_version=settings.schema_version,
        openrouter_api_key=settings.openrouter_api_key,
        model=settings.model,
        temperature=settings.temperature,
        timeout_seconds=settings.timeout_seconds,
        max_steps=settings.max_steps,
        output_dir=settings.output_dir,
        reports_db=settings.reports_db,
        google_sa_path=settings.google_sa_path,
        prompt_namespace=settings.prompt_namespace,
        pagination_max_pages=settings.pagination_max_pages,
        http_timeout_seconds=settings.http_timeout_seconds,
        drive_auth_mode=settings.drive_auth_mode,
        google_oauth_client_path=settings.google_oauth_client_path,
        google_oauth_token_path=settings.google_oauth_token_path,
        openrouter_http_referer=settings.openrouter_http_referer,
        headed=True,
        force_browser=True,
        retry_retries=settings.retry_retries,
        retry_base_delay_seconds=settings.retry_base_delay_seconds,
        retry_backoff_step_seconds=settings.retry_backoff_step_seconds,
        retry_jitter_seconds=settings.retry_jitter_seconds,
    )
    http_calls: list[str] = []
    external_boundary_mocks_only.setattr(
        service.requests,
        "get",
        lambda url, timeout, headers: (
            http_calls.append(url)
            or _FakeResponse(
                url="https://example.com/insights",
                text="<html><body><a href='/reports/report-one'>Report One 2026</a></body></html>",
            )
        ),
    )
    states = {
        "initial": {
            "payload": {
                "page_url": "https://example.com/insights",
                "page_title": "Insights",
                "anchors": [
                    {
                        "href": "https://example.com/reports/report-one",
                        "text": "Report One 2026",
                        "rel": "",
                    }
                ],
            }
        }
    }
    runtime = _runtime_for_states(states)
    vendored_root = str(
        (
            Path(service.__file__).resolve().parents[2] / "tools" / "browser-use"
        ).resolve()
    )
    original_sys_path = list(service.sys.path)
    import_attempts: list[bool] = []

    def _import_module(_name: str):
        has_vendored_root = vendored_root in service.sys.path
        import_attempts.append(has_vendored_root)
        if not has_vendored_root:
            raise ModuleNotFoundError("No module named 'browser_use'")
        return runtime

    external_boundary_mocks_only.setattr(service, "import_module", _import_module)
    external_boundary_mocks_only.setattr(service.asyncio, "sleep", _fast_sleep)

    try:
        service.sys.path[:] = [
            entry for entry in service.sys.path if str(entry) != vendored_root
        ]
        response = service.discover_publisher_inventory(
            PublisherInventoryServiceRequest(
                schema_version="1.0",
                insights_url="https://example.com/insights",
                settings=settings,
            ),
            run_context,
        )
    finally:
        service.sys.path[:] = original_sys_path

    assert response.route_kind == "browser_render"
    assert _FakeBrowser.last_instance is not None
    assert _FakeBrowser.last_instance.headless is False
    assert import_attempts == [False, True]
    assert http_calls == []


def test_discover_publisher_inventory_browser_traverses_tabs(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    states = {
        "initial": {
            "payload": {
                "page_url": "https://www.salesforce.com/eu/company/analyst-reports/#!page=1",
                "page_title": "Analyst Reports | Salesforce EU",
                "anchors": [
                    {
                        "href": "https://www.salesforce.com/eu/form/gartner-report",
                        "text": "2025 Gartner Report",
                        "rel": "",
                    }
                ],
                "tab_labels": ["Gartner", "Forrester", "IDC"],
                "active_tab_label": "Gartner",
            },
            "tab_clicks": {"forrester": "forrester", "idc": "idc"},
        },
        "forrester": {
            "payload": {
                "page_url": "https://www.salesforce.com/eu/company/analyst-reports/#!page=1",
                "page_title": "Analyst Reports | Salesforce EU",
                "anchors": [
                    {
                        "href": "https://www.salesforce.com/eu/form/forrester-report",
                        "text": "2025 Forrester Wave",
                        "rel": "",
                    }
                ],
                "tab_labels": ["Gartner", "Forrester", "IDC"],
                "active_tab_label": "Forrester",
            },
            "tab_clicks": {"idc": "idc"},
        },
        "idc": {
            "payload": {
                "page_url": "https://www.salesforce.com/eu/company/analyst-reports/#!page=1",
                "page_title": "Analyst Reports | Salesforce EU",
                "anchors": [
                    {
                        "href": "https://www.salesforce.com/eu/form/idc-report",
                        "text": "2025 IDC MarketScape",
                        "rel": "",
                    }
                ],
                "tab_labels": ["Gartner", "Forrester", "IDC"],
                "active_tab_label": "IDC",
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
            insights_url="https://www.salesforce.com/eu/company/analyst-reports/#!page=1",
            settings=PublisherInventorySettings(
                schema_version="1.0",
                openrouter_api_key="openrouter-key",
                model="openai/gpt-5-mini",
                temperature=0.0,
                timeout_seconds=30.0,
                max_steps=5,
                output_dir=str(tmp_path / "publisher_inventory_discovery"),
                reports_db=str(tmp_path / "reports.sqlite"),
                google_sa_path=str(tmp_path / "sa.json"),
                prompt_namespace="publisher_inventory/discovery",
                pagination_max_pages=5,
                http_timeout_seconds=10.0,
                openrouter_http_referer="https://marketlense.local",
                headed=True,
                force_browser=True,
                retry_retries=1,
                retry_base_delay_seconds=0.1,
                retry_backoff_step_seconds=0.0,
                retry_jitter_seconds=0.0,
            ),
        ),
        run_context,
    )

    assert response.route_kind == "browser_render"
    assert len(response.pages) == 3
    assert response.route_trace is not None
    assert response.route_trace.selected_tab_labels == ["Gartner", "Forrester", "IDC"]
    assert response.route_trace.pagination_mode == "tabbed"
    assert [candidate.url for candidate in response.candidates] == [
        "https://www.salesforce.com/eu/form/gartner-report",
        "https://www.salesforce.com/eu/form/forrester-report",
        "https://www.salesforce.com/eu/form/idc-report",
    ]
    assert "tabbed publisher section(s)" in response.route_summary


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
