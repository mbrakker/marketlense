# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403

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

def test_discover_publisher_inventory_browser_probes_nested_scroll_archive(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
    caplog,
    assert_logs_have_required_fields,
) -> None:
    caplog.set_level(logging.INFO, logger=service.logger.name)
    external_boundary_mocks_only.setattr(
        service.requests,
        "get",
        lambda *args, **kwargs: _FakeResponse(
            url="https://publisher.example/research",
            text="<html><body><a href='/about'>About</a></body></html>",
        ),
    )
    states = {
        "initial": {
            "payload": {
                "page_url": "https://publisher.example/research",
                "page_title": "Research Library",
                "anchors": [
                    {
                        "href": "https://publisher.example/about",
                        "text": "About",
                        "rel": "",
                    }
                ],
            },
            "nested_scroll_next_state": "nested_scrolled",
        },
        "nested_scrolled": {
            "payload": {
                "page_url": "https://publisher.example/research",
                "page_title": "Research Library",
                "anchors": [
                    {
                        "href": "https://publisher.example/research/market-report-2026",
                        "text": "Market Report 2026",
                        "rel": "",
                    },
                    {
                        "href": "https://publisher.example/research/benchmark-study-2026",
                        "text": "Benchmark Study 2026",
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
            insights_url="https://publisher.example/research",
            settings=_settings(tmp_path),
            route_kind_hint="browser_render",
        ),
        run_context,
    )

    assert response.route_kind == "browser_render"
    assert response.route_trace is not None
    assert response.route_trace.scroll_surface == "nested_container"
    assert response.route_trace.scroll_surface_candidate_growth is True
    assert any(
        candidate.url == "https://publisher.example/research/market-report-2026"
        for candidate in response.candidates
    )
    assert "Probed nested container scroll surfaces" in response.route_summary
    scroll_events = [
        event
        for event in _events(caplog)
        if event.get("event") == "publisher_inventory_browser_scroll_probe"
    ]
    assert scroll_events
    assert scroll_events[0]["fields"]["candidate_growth"] is True
    assert_logs_have_required_fields(_events(caplog))

def test_discover_publisher_inventory_browser_stops_virtualized_scroll_without_growth(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    external_boundary_mocks_only.setattr(
        service.requests,
        "get",
        lambda *args, **kwargs: _FakeResponse(
            url="https://publisher.example/resources",
            text="<html><body><a href='/about'>About</a></body></html>",
        ),
    )
    states = {
        "initial": {
            "payload": {
                "page_url": "https://publisher.example/resources",
                "page_title": "Resources",
                "anchors": [
                    {
                        "href": "https://publisher.example/resources/annual-report-2026",
                        "text": "Annual Report 2026",
                        "rel": "",
                    }
                ],
            },
            "nested_scroll_probe_payload": {
                "scrollSurface": "virtualized_list",
                "bestSurfaceLabel": "div.virtual-list:nth-scroll(0)",
                "probedSurfaceCount": 1,
                "consumedSurfaceCount": 1,
                "virtualizedListDetected": True,
                "anchorCountBefore": 1,
                "anchorCountAfter": 1,
                "candidateGrowth": False,
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
            insights_url="https://publisher.example/resources",
            settings=_settings(tmp_path),
            route_kind_hint="browser_render",
        ),
        run_context,
    )

    assert response.route_kind == "browser_render"
    assert len(response.pages) == 1
    assert len(response.candidates) == 1
    assert response.route_trace is not None
    assert response.route_trace.scroll_surface == "virtualized_list"
    assert response.route_trace.scroll_surface_candidate_growth is False
    assert response.route_trace.virtualized_list_detected is True

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

__all__ = [
    "test_discover_publisher_inventory_browser_applies_generic_report_dropdown_filter",
    "test_discover_publisher_inventory_browser_fallback_when_http_empty",
    "test_discover_publisher_inventory_browser_closes_stray_blank_pages",
    "test_discover_publisher_inventory_browser_scrolls_to_hydrate_load_more",
    "test_discover_publisher_inventory_browser_probes_nested_scroll_archive",
    "test_discover_publisher_inventory_browser_stops_virtualized_scroll_without_growth",
    "test_discover_publisher_inventory_browser_stops_before_recording_inert_duplicate_load_more_states",
    "test_discover_publisher_inventory_browser_prefers_candidate_dense_load_more_surface",
    "test_discover_publisher_inventory_browser_resets_empty_results_filters",
]
