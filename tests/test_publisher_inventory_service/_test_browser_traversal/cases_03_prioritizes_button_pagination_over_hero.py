# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403

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

__all__ = [
    "test_discover_publisher_inventory_browser_prioritizes_button_pagination_over_hero_load_more",
    "test_discover_publisher_inventory_browser_stops_on_load_more_state_change_without_new_unique_candidates",
    "test_discover_publisher_inventory_browser_treats_inert_load_more_as_exhausted",
    "test_discover_publisher_inventory_browser_skips_duplicate_same_url_page_states",
    "test_discover_publisher_inventory_browser_breaks_same_url_load_more_cycles",
    "test_discover_publisher_inventory_browser_breaks_cross_url_signature_cycles",
    "test_discover_publisher_inventory_force_browser_skips_http",
    "test_discover_publisher_inventory_browser_traverses_tabs",
]
