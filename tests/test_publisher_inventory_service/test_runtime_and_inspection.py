from __future__ import annotations

from .builders import *  # noqa: F401,F403


def test_close_unexpected_blank_pages_keeps_active_page_when_target_id_is_missing(
    run_context,
) -> None:
    browser = _FakeBrowser(
        downloads_path=".",
        headless=True,
        auto_download_pdfs=False,
        states={
            "initial": {
                "payload": {
                    "page_url": "about:blank",
                    "page_title": "",
                    "anchors": [],
                }
            }
        },
        start_state="initial",
        extra_page_urls=["about:blank"],
    )
    browser.page = _FakeBrowserPage(browser, "initial", browser._states, target_id="")

    asyncio.run(
        service._close_unexpected_blank_pages(
            browser=browser,
            active_page=browser.page,
            ctx=run_context,
            reason="test_blank_identity_guard",
        )
    )

    assert browser.closed_page_ids == ["aux-1"]


def test_browser_scripts_coerce_non_string_dom_values_before_normalizing() -> None:
    scripts = [
        service._browser_inventory_state_script(),
        service._browser_click_named_control_script(),
        service._browser_click_pagination_next_script(),
        service._browser_click_tab_script(),
        service._browser_apply_report_filter_script(),
    ]
    for script in scripts:
        assert "String(value ?? '')" in script
        assert "(value || '').replace" not in script


def test_wait_for_inventory_growth_probe_detects_same_page_anchor_growth(
    external_boundary_mocks_only,
) -> None:
    external_boundary_mocks_only.setattr(service.asyncio, "sleep", _fast_sleep)

    class _ProbePage:
        def __init__(self) -> None:
            self._counts = [1, 3]

        async def evaluate(self, script: str, *args):
            assert "pageUrl" in script
            count = self._counts.pop(0)
            return json.dumps(
                {
                    "pageUrl": "https://example.com/insights",
                    "anchorCount": count,
                }
            )

    previous_state = service._RenderedInventoryState(
        page_url="https://example.com/insights",
        page_title="Insights",
        anchors=[
            {"href": "https://example.com/report-one", "text": "Report One", "rel": ""}
        ],
        load_more_labels=["Load more"],
        tab_labels=[],
        active_tab_label=None,
        report_link_url=None,
        empty_results_visible=False,
        reset_filter_labels=[],
        has_report_filter=False,
        has_apply_button=False,
        has_pagination_next=False,
        result_range_end=None,
        result_range_total=None,
        page_index_hint=None,
        page_total_hint=None,
    )

    observed = asyncio.run(
        service._wait_for_inventory_growth_probe(
            _ProbePage(),
            previous_state=previous_state,
            delay_seconds=0.1,
            timeout_seconds=0.25,
        )
    )

    assert observed is True


def test_browser_named_control_selector_covers_anchor_button_controls() -> None:
    selector = service._browser_named_control_selector()
    inventory_script = service._browser_inventory_state_script()
    click_script = service._browser_click_named_control_script()
    cookie_click_script = service._browser_click_cookie_banner_script()
    pagination_click_script = service._browser_click_pagination_next_script()
    archive_expander_script = service._browser_click_archive_expander_script()

    assert "a.btn" in selector
    assert 'a[class*="btn"]' in selector
    assert "a.wp-block-button__link" in selector
    assert ".load-more" in selector
    assert "a.btn" in inventory_script
    assert "a.wp-block-button__link" in inventory_script
    assert "a.btn" in click_script
    assert "a.wp-block-button__link" in click_script
    assert "candidate_urls" in click_script
    assert "scrollIntoView" in click_script
    assert "aria-disabled" in inventory_script
    assert "aria-disabled" in click_script
    assert "cookie" in cookie_click_script
    assert "consent" in cookie_click_script
    assert "aria-disabled" in pagination_click_script
    assert "has_pagination_next" in inventory_script
    assert "const pageCountMatch =" in pagination_click_script
    assert "explore" in archive_expander_script
    assert "library" in archive_expander_script


def test_browser_inventory_probe_scripts_emit_expected_runtime_keys() -> None:
    growth_probe_script = service._browser_inventory_growth_probe_script()
    settle_probe_script = service._browser_inventory_settle_probe_script()

    assert "pageUrl" in growth_probe_script
    assert "anchorCount" in growth_probe_script
    assert "readyState" in settle_probe_script
    assert "title" in settle_probe_script
    assert "anchorCount" in settle_probe_script


def test_rendered_inventory_state_from_payload_normalizes_payload() -> None:
    state = service._rendered_inventory_state_from_payload(
        {
            "page_url": "https://example.com/reports",
            "page_title": "  Reports   ",
            "anchors": [
                {
                    "href": "https://example.com/reports/alpha",
                    "text": "Learn more",
                    "heading_text": "Alpha report",
                    "rel": "nofollow",
                },
                {
                    "href": "",
                    "text": "Ignored",
                },
            ],
            "load_more_labels": ["  Load   more  ", ""],
            "tab_labels": [" Reports ", None],
            "active_tab_label": " Reports ",
            "report_link_url": "https://example.com/reports/all",
            "empty_results_visible": 0,
            "reset_filter_labels": [" Reset all filters ", ""],
            "has_report_filter": 1,
            "has_apply_button": 0,
            "has_pagination_next": 1,
            "result_range_end": "24",
            "result_range_total": "96",
            "page_index_hint": "2",
            "page_total_hint": "4",
        },
        page_url_fallback="https://example.com/insights",
    )

    assert state.page_url == "https://example.com/reports"
    assert state.page_title == "Reports"
    assert state.anchors == [
        {
            "href": "https://example.com/reports/alpha",
            "text": "Alpha report",
            "rel": "nofollow",
        }
    ]
    assert state.load_more_labels == ["Load more"]
    assert state.tab_labels == ["Reports"]
    assert state.active_tab_label == "Reports"
    assert state.report_link_url == "https://example.com/reports/all"
    assert state.empty_results_visible is False
    assert state.reset_filter_labels == ["Reset all filters"]
    assert state.has_report_filter is True
    assert state.has_apply_button is False
    assert state.has_pagination_next is True
    assert state.result_range_end == 24
    assert state.result_range_total == 96
    assert state.page_index_hint == 2
    assert state.page_total_hint == 4


def test_discover_publisher_inventory_browser_timeout_is_typed_error(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
    assert_app_error,
) -> None:
    states = {
        "page1": {
            "payload": {
                "page_url": "https://example.com/insights",
                "page_title": "Insights",
                "anchors": [],
            }
        }
    }
    external_boundary_mocks_only.setattr(
        service, "import_module", lambda _name: _runtime_for_states(states)
    )

    def _raise_timeout(_awaitable):
        close = getattr(_awaitable, "close", None)
        if callable(close):
            close()
        raise TimeoutError("timed out")

    external_boundary_mocks_only.setattr(service.asyncio, "run", _raise_timeout)

    with pytest.raises(AppError) as err:
        service.discover_publisher_inventory(
            PublisherInventoryServiceRequest(
                schema_version="1.0",
                insights_url="https://example.com/insights",
                settings=replace(
                    _settings(tmp_path),
                    force_browser=True,
                    timeout_seconds=1.0,
                ),
                route_kind_hint=None,
                route_hint=None,
            ),
            run_context,
        )

    assert_app_error(
        err.value,
        code="publisher_inventory_browser_timeout",
        retryable=True,
    )


def test_discover_publisher_inventory_browser_timeout_falls_back_to_http(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    html = """
    <html><body>
      <a href="/reports/report-one">Report One 2026</a>
    </body></html>
    """

    external_boundary_mocks_only.setattr(
        service.requests,
        "get",
        lambda url, timeout, headers: _FakeResponse(
            url="https://example.com/insights",
            text=html,
        ),
    )

    def _raise_timeout(_awaitable):
        close = getattr(_awaitable, "close", None)
        if callable(close):
            close()
        raise TimeoutError("timed out")

    external_boundary_mocks_only.setattr(service.asyncio, "run", _raise_timeout)

    response = service.discover_publisher_inventory(
        PublisherInventoryServiceRequest(
            schema_version="1.0",
            insights_url="https://example.com/insights",
            settings=replace(
                _settings(tmp_path),
                force_browser=True,
                timeout_seconds=1.0,
            ),
            route_kind_hint=None,
            route_hint=None,
        ),
        run_context,
    )

    assert response.route_kind == "http_parse"
    assert [candidate.url for candidate in response.candidates] == [
        "https://example.com/reports/report-one"
    ]


def test_inspect_publisher_inventory_landing_pages_detects_gated_report_signals(
    run_context,
    external_boundary_mocks_only,
    caplog,
    assert_logs_have_required_fields,
) -> None:
    html = """
    <html>
      <head>
        <title>Greek eGrocery S1 2024 | Convert Group</title>
        <meta property="og:title" content="Greek eGrocery S1 2024" />
      </head>
      <body>
        <h1>Greek eGrocery S1 2024</h1>
        <p>You can download the report by filling out the form.</p>
        <p>Contents of the report include market size, trends, and key findings.</p>
        <form><input type="email" /><input type="submit" value="Download report" /></form>
      </body>
    </html>
    """
    external_boundary_mocks_only.setattr(
        service.requests,
        "get",
        lambda *args, **kwargs: _FakeResponse(
            url="https://convertgroup.com/reports_posts/greek-egrocery-s1-2024/",
            text=html,
        ),
    )
    caplog.set_level(logging.INFO, logger="market_lense.publisher_inventory_service")

    response = service.inspect_publisher_inventory_landing_pages(
        PublisherInventoryLandingPageInspectionRequest(
            schema_version="1.0",
            publisher_name="Convert Group",
            items=[
                PublisherInventoryLandingPageInspectionItem(
                    schema_version="1.0",
                    canonical_url="https://convertgroup.com/reports_posts/greek-egrocery-s1-2024/",
                    title="Download report",
                    discovered_on_page_number=1,
                    source_page_url="https://convertgroup.com/reports",
                )
            ],
            timeout_seconds=5.0,
            max_workers=2,
        ),
        run_context,
    )

    observation = response.observations[0]
    assert observation.h1_title == "Greek eGrocery S1 2024"
    assert observation.has_asset_type_term is True
    assert observation.has_download_language is True
    assert observation.has_gated_form is True
    assert observation.has_document_structure is True
    records = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == "market_lense.publisher_inventory_service"
    ]
    assert_logs_have_required_fields(records)


def test_inspect_publisher_inventory_landing_pages_marks_dead_pages(
    run_context,
    external_boundary_mocks_only,
) -> None:
    html = """
    <html><head><title>Page not found | Example</title></head><body><h1>Page not found</h1></body></html>
    """
    external_boundary_mocks_only.setattr(
        service.requests,
        "get",
        lambda *args, **kwargs: _FakeResponse(
            url="https://example.com/resources/missing-report",
            text=html,
            status_code=404,
        ),
    )

    response = service.inspect_publisher_inventory_landing_pages(
        PublisherInventoryLandingPageInspectionRequest(
            schema_version="1.0",
            publisher_name="Example Publisher",
            items=[
                PublisherInventoryLandingPageInspectionItem(
                    schema_version="1.0",
                    canonical_url="https://example.com/resources/missing-report",
                    title="Missing Report",
                    discovered_on_page_number=1,
                    source_page_url="https://example.com/insights",
                )
            ],
            timeout_seconds=5.0,
            max_workers=1,
        ),
        run_context,
    )

    observation = response.observations[0]
    assert observation.http_status_code == 404
    assert observation.has_dead_page_marker is True


def test_inspect_publisher_inventory_landing_pages_detects_direct_pdf_assets(
    run_context,
    external_boundary_mocks_only,
) -> None:
    external_boundary_mocks_only.setattr(
        service.requests,
        "get",
        lambda *args, **kwargs: _FakeResponse(
            url="https://example.com/report.pdf",
            text="",
            headers={"Content-Type": "application/pdf"},
        ),
    )

    response = service.inspect_publisher_inventory_landing_pages(
        PublisherInventoryLandingPageInspectionRequest(
            schema_version="1.0",
            publisher_name="Example Publisher",
            items=[
                PublisherInventoryLandingPageInspectionItem(
                    schema_version="1.0",
                    canonical_url="https://example.com/report.pdf",
                    title="2026 Outlook",
                    discovered_on_page_number=1,
                    source_page_url="https://example.com/insights",
                )
            ],
            timeout_seconds=5.0,
            max_workers=1,
        ),
        run_context,
    )

    observation = response.observations[0]
    assert observation.is_pdf is True
    assert observation.has_download_language is True
    assert observation.has_dead_page_marker is False


def test_inspect_publisher_inventory_landing_pages_does_not_treat_body_purchase_word_as_product_flow(
    run_context,
    external_boundary_mocks_only,
) -> None:
    html = """
    <html>
      <head><title>Creating Relevance Through the Convergence of Content, Creators & Commerce</title></head>
      <body>
        <h2>Creating Relevance Through the Convergence of Content, Creators & Commerce</h2>
        <h1>KEY TAKEAWAYS</h1>
        <p>Creators and content can guide consumers from awareness all the way through to purchase with just a click.</p>
        <p>Other Articles</p>
        <p>Colleen Hotchkiss</p>
        <p>30 / 06 / 2023</p>
        <button>Subscribe</button>
      </body>
    </html>
    """
    external_boundary_mocks_only.setattr(
        service.requests,
        "get",
        lambda *args, **kwargs: _FakeResponse(
            url="https://www.publiciscommerce.com/insights/creating-relevance-through-the-convergence-of-content-creators-and-commerce",
            text=html,
        ),
    )

    response = service.inspect_publisher_inventory_landing_pages(
        PublisherInventoryLandingPageInspectionRequest(
            schema_version="1.0",
            publisher_name="Publicis Commerce",
            items=[
                PublisherInventoryLandingPageInspectionItem(
                    schema_version="1.0",
                    canonical_url="https://www.publiciscommerce.com/insights/creating-relevance-through-the-convergence-of-content-creators-and-commerce",
                    title="Creating Relevance Through the Convergence of Content",
                    discovered_on_page_number=1,
                    source_page_url="https://www.publiciscommerce.com/insights",
                )
            ],
            timeout_seconds=5.0,
            max_workers=1,
        ),
        run_context,
    )

    observation = response.observations[0]
    assert observation.has_price_or_purchase is False
    assert observation.has_newsletter_cta is True
